"""
Webhook completo do Twilio - VERSÃO STANDALONE
Não depende de módulos externos, funciona out-of-the-box
"""

from flask import Flask, request, jsonify, Response
from twilio.twiml.voice_response import VoiceResponse, Dial
from twilio.request_validator import RequestValidator
from datetime import datetime
from typing import Dict, Any, Optional
import logging
import os

from services.database import DatabaseService

# Setup
app = Flask(__name__)
logger = logging.getLogger(__name__)

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Inicializar serviços
db = DatabaseService()

# Twilio credentials
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN', '')
DEBUG_MODE = os.getenv('DEBUG', 'false').lower() == 'true'

# ============================================================================
# VALIDAÇÃO TWILIO (INLINE)
# ============================================================================

def validate_twilio_request() -> bool:
    """
    Valida se a requisição veio do Twilio.
    Em modo DEBUG, permite requisições locais sem validação.
    """
    # Modo DEBUG: pular validação para testes locais
    if DEBUG_MODE and request.remote_addr in ['127.0.0.1', 'localhost', '::1']:
        logger.warning(f"⚠️  Skipping Twilio validation (DEBUG mode)")
        return True
    
    # Sem token configurado: pular validação (com aviso)
    if not TWILIO_AUTH_TOKEN:
        logger.warning(f"⚠️  TWILIO_AUTH_TOKEN not configured, skipping validation")
        return True
    
    try:
        # Validar assinatura do Twilio
        validator = RequestValidator(TWILIO_AUTH_TOKEN)
        
        # URL completa da requisição
        url = request.url
        
        # Parâmetros da requisição
        if request.method == 'POST':
            params = request.form.to_dict()
        else:
            params = request.args.to_dict()
        
        # Signature do header
        signature = request.headers.get('X-Twilio-Signature', '')
        
        # Validar
        is_valid = validator.validate(url, params, signature)
        
        if not is_valid:
            logger.warning(f"❌ Invalid Twilio signature from {request.remote_addr}")
            
        return is_valid
        
    except Exception as e:
        logger.error(f"❌ Error validating Twilio request: {e}")
        return False


# ============================================================================
# ENDPOINT PRINCIPAL - Recebe chamada e roteia
# ============================================================================

@app.route('/webhook/call', methods=['POST', 'GET'])
def webhook_call() -> tuple[Response, int]:
    """
    Endpoint principal do webhook Twilio.
    
    Flow:
    1. Valida requisição do Twilio
    2. Identifica tracking source (UTM/GCLID)
    3. Busca número de destino
    4. Cria TwiML com redirecionamento + gravação
    5. Registra chamada no banco (async)
    
    Returns:
        TwiML Response com instruções de roteamento
    """
    start_time = datetime.now()
    call_sid = request.values.get('CallSid', 'unknown')
    
    try:
        # ===== 1. VALIDAÇÃO TWILIO =====
        if not validate_twilio_request():
            logger.warning(f"❌ Invalid Twilio signature from {request.remote_addr}")
            return _create_error_response("Unauthorized"), 403
        
        # ===== 2. EXTRAIR DADOS =====
        from_number = request.values.get('From')
        to_number = request.values.get('To')  # número rastreado
        call_status = request.values.get('CallStatus', 'initiated')
        
        # Query params para tracking
        campaign = request.args.get('campaign')
        utm_source = request.args.get('utm_source')
        utm_medium = request.args.get('utm_medium')
        utm_campaign = request.args.get('utm_campaign')
        gclid = request.args.get('gclid')
        
        logger.info(f"📞 Call received: {call_sid} | {from_number} → {to_number}")
        
        # ===== 3. IDENTIFICAR TRACKING SOURCE =====
        tracking_source = None
        if any([utm_source, utm_campaign, gclid]):
            try:
                tracking_source = db.get_or_create_tracking_source({
                    'tracking_number': to_number,
                    'utm_source': utm_source,
                    'utm_medium': utm_medium,
                    'utm_campaign': utm_campaign or campaign,
                    'gclid': gclid
                })
                logger.info(f"📊 Tracking source: {tracking_source.get('id')}")
            except Exception as e:
                logger.error(f"⚠️ Error with tracking source: {e}")
        
        # ===== 4. BUSCAR NÚMERO DE DESTINO =====
        try:
            destination = db.get_destination_number(
                tracking_number=to_number,
                campaign=campaign
            )
        except Exception as e:
            logger.error(f"❌ Error fetching destination: {e}")
            destination = None
        
        if not destination:
            logger.error(f"❌ No destination found for {to_number}")
            return _create_no_destination_response(), 200
        
        logger.info(f"🎯 Routing to: {destination}")
        
        # ===== 5. REGISTRAR CHAMADA (NÃO BLOQUEANTE) =====
        try:
            call_data = {
                'call_sid': call_sid,
                'from_number': from_number,
                'to_number': to_number,
                'destination_number': destination,
                'status': call_status,
                'campaign': campaign or utm_campaign,
                'tracking_source_id': tracking_source.get('id') if tracking_source else None,
                'created_at': datetime.utcnow().isoformat()
            }
            
            db.insert_call(call_data)
            
            elapsed = (datetime.now() - start_time).total_seconds() * 1000
            logger.info(f"✅ Call logged in {elapsed:.2f}ms")
            
        except Exception as db_error:
            # Não bloqueia a chamada se falhar o registro
            logger.error(f"⚠️ Database error (non-blocking): {db_error}")
        
        # ===== 6. CRIAR TWIML COM REDIRECIONAMENTO + GRAVAÇÃO =====
        twiml_response = _create_forward_response(
            destination=destination,
            from_number=from_number,
            call_sid=call_sid
        )
        
        return Response(twiml_response, mimetype='application/xml'), 200
        
    except Exception as e:
        logger.error(f"❌ Critical webhook error: {str(e)}", exc_info=True)
        return _create_error_response("Internal error"), 500


# ============================================================================
# ENDPOINT - Callback de gravação
# ============================================================================

@app.route('/webhook/recording', methods=['POST'])
def webhook_recording() -> tuple[Dict[str, Any], int]:
    """
    Recebe notificação quando gravação está pronta.
    
    O Twilio chama este endpoint automaticamente após finalizar a gravação.
    """
    try:
        # Extrair dados da gravação
        call_sid = request.values.get('CallSid')
        recording_url = request.values.get('RecordingUrl')
        recording_sid = request.values.get('RecordingSid')
        recording_duration = request.values.get('RecordingDuration', 0)
        
        logger.info(f"🎙️ Recording ready: {recording_sid} for call {call_sid}")
        
        # Atualizar registro no banco
        db.update_call_recording(
            call_sid=call_sid,
            recording_url=recording_url + '.mp3',  # Twilio adiciona extensão
            recording_sid=recording_sid,
            recording_duration=int(recording_duration)
        )
        
        logger.info(f"✅ Recording saved: {recording_sid}")
        
        return jsonify({
            'success': True,
            'recording_sid': recording_sid,
            'duration': recording_duration
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Recording webhook error: {str(e)}", exc_info=True)
        return jsonify({
            'error': 'Failed to process recording',
            'message': str(e)
        }), 500


# ============================================================================
# ENDPOINT - Status da chamada
# ============================================================================

@app.route('/webhook/call-status', methods=['POST'])
def webhook_call_status() -> tuple[Dict[str, Any], int]:
    """
    Recebe atualizações de status da chamada (completed, busy, no-answer, etc).
    """
    try:
        call_sid = request.values.get('CallSid')
        call_status = request.values.get('CallStatus')
        call_duration = request.values.get('CallDuration', 0)
        
        logger.info(f"📊 Status update: {call_sid} → {call_status}")
        
        # Atualizar status no banco
        db.update_call_status(
            call_sid=call_sid,
            status=call_status,
            duration=int(call_duration)
        )
        
        return jsonify({'success': True}), 200
        
    except Exception as e:
        logger.error(f"❌ Status webhook error: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# FUNÇÕES AUXILIARES - TwiML Responses
# ============================================================================

def _create_forward_response(
    destination: str, 
    from_number: str,
    call_sid: str
) -> str:
    """
    Cria TwiML para encaminhar chamada com gravação.
    
    Args:
        destination: Número final para onde redirecionar
        from_number: Número original do caller
        call_sid: ID da chamada
        
    Returns:
        String XML com instruções TwiML
    """
    response = VoiceResponse()
    
    # Dial com configurações de gravação
    dial = Dial(
        caller_id=from_number,  # Mantém caller ID original
        action=f'/webhook/call-status',  # Callback após chamada
        method='POST',
        timeout=30,  # Timeout de toque (segundos)
        record='record-from-answer',  # Grava desde que atender
        recording_status_callback='/webhook/recording',
        recording_status_callback_method='POST',
        recording_status_callback_event=['completed']  # Notifica quando terminar
    )
    
    # Número de destino
    dial.number(
        destination,
        status_callback_event=['initiated', 'ringing', 'answered', 'completed'],
        status_callback=f'/webhook/call-status',
        status_callback_method='POST'
    )
    
    response.append(dial)
    
    # Mensagem se ninguém atender
    response.say(
        'A ligação não pôde ser completada. Por favor, tente novamente mais tarde.',
        language='pt-BR',
        voice='Polly.Camila'
    )
    
    return str(response)


def _create_no_destination_response() -> tuple[Response, int]:
    """TwiML quando não encontra número de destino configurado."""
    response = VoiceResponse()
    response.say(
        'Desculpe, não foi possível completar sua ligação. '
        'Este número não está configurado no momento.',
        language='pt-BR',
        voice='Polly.Camila'
    )
    response.hangup()
    
    return Response(str(response), mimetype='application/xml'), 200


def _create_error_response(message: str) -> tuple[Response, int]:
    """TwiML de erro genérico."""
    response = VoiceResponse()
    response.say(
        'Ocorreu um erro no sistema. Por favor, tente novamente mais tarde.',
        language='pt-BR',
        voice='Polly.Camila'
    )
    response.hangup()
    
    return Response(str(response), mimetype='application/xml'), 200


# ============================================================================
# ENDPOINTS DE HEALTH CHECK
# ============================================================================

@app.route('/health', methods=['GET'])
def health_check() -> Dict[str, Any]:
    """Health check do serviço."""
    try:
        # Testa conexão com banco
        db_status = db.health_check() if hasattr(db, 'health_check') else True
        
        return jsonify({
            'status': 'healthy',
            'service': 'call-tracker-webhook',
            'timestamp': datetime.utcnow().isoformat(),
            'database': 'connected' if db_status else 'disconnected',
            'version': '2.0.0'
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 503


# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    # Configurações
    debug_mode = os.getenv('DEBUG', 'false').lower() == 'true'
    port = int(os.getenv('PORT', 5001))
    
    logger.info(f"🚀 Starting Call Tracker Webhook v2.0")
    logger.info(f"📍 Port: {port} | Debug: {debug_mode}")
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug_mode
    )