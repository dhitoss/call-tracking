"""
Webhook 
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
# VALIDAÇÃO TWILIO (CORRIGIDA PARA RAILWAY/PROXY)
# ============================================================================

def validate_twilio_request() -> bool:
    """
    Valida se a requisição veio do Twilio.
    """
    if DEBUG_MODE:
        return True
    
    if not TWILIO_AUTH_TOKEN:
        logger.warning("⚠️ TWILIO_AUTH_TOKEN not configured")
        return True
    
    try:
        validator = RequestValidator(TWILIO_AUTH_TOKEN)
        
        # FIX PARA RAILWAY/PROXIES:
        # O Railway recebe HTTPS mas passa HTTP para o container.
        # Precisamos reconstruir a URL original que o Twilio chamou.
        url = request.url
        if request.headers.get('X-Forwarded-Proto') == 'https':
            url = url.replace('http://', 'https://', 1)
        
        if request.method == 'POST':
            params = request.form.to_dict()
        else:
            params = request.args.to_dict()
        
        signature = request.headers.get('X-Twilio-Signature', '')
        is_valid = validator.validate(url, params, signature)
        
        if not is_valid:
            logger.warning(f"❌ Invalid Twilio signature. URL: {url}")
            
        return is_valid
        
    except Exception as e:
        logger.error(f"❌ Error validating Twilio request: {e}")
        return False # Em produção, pode alterar para True se estiver tendo problemas de bloqueio

# ============================================================================
# ENDPOINT PRINCIPAL
# ============================================================================

@app.route('/webhook/call', methods=['POST', 'GET'])
def webhook_call() -> Any: # Tipo de retorno genérico para satisfazer Flask
    start_time = datetime.now()
    call_sid = request.values.get('CallSid', 'unknown')
    
    try:
        # 1. Validação (Não bloqueante em erro)
        if not validate_twilio_request():
             if not DEBUG_MODE:
                 logger.warning("⚠️ Request validation failed but proceeding (Production Mode)")

        # 2. Extrair Dados
        from_number = request.values.get('From')
        to_number = request.values.get('To')
        call_status = request.values.get('CallStatus', 'initiated')
        
        # Params
        campaign = request.args.get('campaign')
        utm_source = request.args.get('utm_source')
        utm_medium = request.args.get('utm_medium')
        utm_campaign = request.args.get('utm_campaign')
        gclid = request.args.get('gclid')
        
        logger.info(f"📞 Call received: {call_sid} | {from_number} → {to_number}")
        
        # 3. Tracking (Não bloqueante)
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
            except Exception as e:
                logger.error(f"⚠️ Tracking error: {e}")

        # 4. BUSCAR DESTINO (COM FALLBACK ROBUSTO)
        destination = None
        
        # Tentativa 1: Via Método do Service (que está dando erro de .or_)
        try:
            if hasattr(db, 'get_destination_number'):
                destination = db.get_destination_number(
                    tracking_number=to_number,
                    campaign=campaign
                )
        except Exception as service_error:
            logger.error(f"⚠️ Service method failed ({service_error}), trying direct query...")
            destination = None # Força o fallback

        # Tentativa 2: Fallback direto no banco (se a tentativa 1 falhou ou retornou nada)
        if not destination:
            try:
                logger.info(f"🔍 Attempting fallback query for {to_number}")
                # Query direta simples que funciona
                result = db.client.table('phone_routing')\
                    .select('destination_number')\
                    .eq('tracking_number', to_number)\
                    .eq('is_active', True)\
                    .execute()
                
                if result.data and len(result.data) > 0:
                    destination = result.data[0]['destination_number']
                    logger.info(f"✅ Destination found via fallback: {destination}")
            except Exception as db_err:
                logger.error(f"❌ Fallback query failed: {db_err}")

        # Se ainda não achou destino
        if not destination:
            logger.error(f"❌ No destination found for {to_number}")
            # CORREÇÃO: Retorna apenas a função, sem ", 200" extra
            return _create_no_destination_response()

        logger.info(f"🎯 Routing to: {destination}")
        
        # 5. Registrar Chamada (Async/Não bloqueante)
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
        except Exception as db_error:
            logger.error(f"⚠️ Log call error: {db_error}")
        
        # 6. Retornar TwiML
        xml_response = _create_forward_response(
            destination=destination,
            from_number=from_number,
            call_sid=call_sid
        )
        
        return Response(xml_response, mimetype='application/xml'), 200
        
    except Exception as e:
        logger.error(f"❌ Critical webhook error: {str(e)}", exc_info=True)
        # CORREÇÃO: Retorna apenas a função
        return _create_error_response("System error")


# ============================================================================
# WEBHOOKS AUXILIARES (Recording / Status)
# ============================================================================

@app.route('/webhook/recording', methods=['POST'])
def webhook_recording():
    try:
        call_sid = request.values.get('CallSid')
        recording_url = request.values.get('RecordingUrl')
        recording_sid = request.values.get('RecordingSid')
        duration = request.values.get('RecordingDuration', 0)
        
        if recording_url:
            recording_url += '.mp3'
            
        db.update_call_recording(
            call_sid=call_sid,
            recording_url=recording_url,
            recording_sid=recording_sid,
            recording_duration=int(duration) if duration else 0
        )
        return jsonify({'success': True}), 200
    except Exception as e:
        logger.error(f"Rec error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/webhook/call-status', methods=['POST'])
def webhook_call_status():
    try:
        call_sid = request.values.get('CallSid')
        status = request.values.get('CallStatus')
        duration = request.values.get('CallDuration', 0)
        
        db.update_call_status(
            call_sid=call_sid,
            status=status,
            duration=int(duration) if duration else 0
        )
        return jsonify({'success': True}), 200
    except Exception as e:
        logger.error(f"Status error: {e}")
        return jsonify({'error': str(e)}), 500

# ============================================================================
# FUNÇÕES AUXILIARES (TwiML)
# ============================================================================

def _create_forward_response(destination: str, from_number: str, call_sid: str) -> str:
    """Retorna APENAS a string XML."""
    response = VoiceResponse()
    
    dial = Dial(
        caller_id=from_number,
        action='/webhook/call-status',
        method='POST',
        timeout=30,
        record='record-from-answer',
        recording_status_callback='/webhook/recording',
        recording_status_callback_method='POST',
        recording_status_callback_event=['completed']
    )
    
    dial.number(
        destination,
        status_callback_event=['initiated', 'ringing', 'answered', 'completed'],
        status_callback='/webhook/call-status',
        status_callback_method='POST'
    )
    
    response.append(dial)
    response.say('A ligação caiu. Tente novamente.', language='pt-BR', voice='Polly.Camila')
    
    return str(response)

def _create_no_destination_response() -> tuple[Response, int]:
    """Já retorna o objeto Response e o status code."""
    response = VoiceResponse()
    response.say(
        'Desculpe, número não configurado.',
        language='pt-BR',
        voice='Polly.Camila'
    )
    response.hangup()
    return Response(str(response), mimetype='application/xml'), 200

def _create_error_response(message: str) -> tuple[Response, int]:
    """Já retorna o objeto Response e o status code."""
    response = VoiceResponse()
    response.say(
        'Erro no sistema. Tente mais tarde.',
        language='pt-BR',
        voice='Polly.Camila'
    )
    response.hangup()
    return Response(str(response), mimetype='application/xml'), 200

# ============================================================================
# MAIN
# ============================================================================

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy', 'version': '2.1-fixed'}), 200

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5001))
    app.run(host='0.0.0.0', port=port)