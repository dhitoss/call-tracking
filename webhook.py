"""
Webhook (Schema Fix)
"""

from flask import Flask, request, jsonify, Response
from twilio.twiml.voice_response import VoiceResponse, Dial
from twilio.request_validator import RequestValidator
from datetime import datetime
from typing import Dict, Any, Optional
import logging
import os

from services.database import DatabaseService
from services.crm import CRMService

# Setup
app = Flask(__name__)
logger = logging.getLogger(__name__)
crm = CRMService()

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
# VALIDAÇÃO TWILIO
# ============================================================================

def validate_twilio_request() -> bool:
    if DEBUG_MODE:
        return True
    if not TWILIO_AUTH_TOKEN:
        return True
    
    try:
        validator = RequestValidator(TWILIO_AUTH_TOKEN)
        url = request.url
        # Fix para Railway (HTTPS proxy)
        if request.headers.get('X-Forwarded-Proto') == 'https':
            url = url.replace('http://', 'https://', 1)
        
        params = request.form.to_dict() if request.method == 'POST' else request.args.to_dict()
        signature = request.headers.get('X-Twilio-Signature', '')
        
        return validator.validate(url, params, signature)
    except Exception as e:
        logger.error(f"Validation Error: {e}")
        return True

# ============================================================================
# ENDPOINT PRINCIPAL
# ============================================================================

@app.route('/webhook/call', methods=['POST', 'GET'])
def webhook_call() -> Any:
    call_sid = request.values.get('CallSid', 'unknown')
    
    try:
        validate_twilio_request()
        
        # Extrair Dados
        from_number = request.values.get('From')
        to_number = request.values.get('To')
        call_status = request.values.get('CallStatus', 'initiated')
        
        # Params
        campaign = request.args.get('campaign')
        utm_campaign = request.args.get('utm_campaign')
        
        logger.info(f"📞 Call: {call_sid} | {from_number} -> {to_number}")

        # 1. Tracking (Silent fail)
        tracking_source_id = None
        try:
            tracking_data = {
                'tracking_number': to_number,
                'utm_source': request.args.get('utm_source'),
                'utm_medium': request.args.get('utm_medium'),
                'utm_campaign': utm_campaign or campaign,
                'gclid': request.args.get('gclid')
            }
            if any(tracking_data.values()):
                ts = db.get_or_create_tracking_source(tracking_data)
                tracking_source_id = ts.get('id') if ts else None
        except Exception as e:
            logger.error(f"Tracking error: {e}")

        # 2. Buscar Destino (Com Fallback)
        destination = None
        try:
            if hasattr(db, 'get_destination_number'):
                destination = db.get_destination_number(to_number, campaign)
        except:
            pass 
            
        # Fallback direto
        if not destination:
            try:
                result = db.client.table('phone_routing')\
                    .select('destination_number')\
                    .eq('tracking_number', to_number)\
                    .eq('is_active', True)\
                    .execute()
                if result.data:
                    destination = result.data[0]['destination_number']
            except Exception as e:
                logger.error(f"DB Fallback error: {e}")

        if not destination:
            return _create_no_destination_response()

        # 3. Registrar Chamada & Atualizar CRM
        try:
            call_data = {
                'call_sid': call_sid,
                'from_number': from_number,
                'to_number': to_number,
                'destination_number': destination,
                'status': call_status,
                'campaign': campaign or utm_campaign,   
                'tracking_source_id': tracking_source_id,
                'created_at': datetime.utcnow().isoformat()
            }
            
            # Salva Log da Chamada
            db.insert_call(call_data)
            logger.info("✅ Call inserted successfully")

            # --- INTEGRAÇÃO CRM (NOVO) ---
            # Tenta atualizar o Kanban, mas não trava a ligação se der erro
            try:
                logger.info(f"🔄 Triggering CRM for {from_number}")
                crm.handle_incoming_call_event(call_data)
                logger.info("✅ CRM updated successfully")
            except Exception as crm_error:
                logger.error(f"⚠️ CRM Update failed (non-blocking): {crm_error}")
            # -----------------------------

        except Exception as db_error:
            logger.error(f"Insert Call Error: {db_error}")
        
        # 4. Retornar TwiML (Isso conecta a chamada)
        xml_response = _create_forward_response(
            destination=destination,
            from_number=from_number
        )
        
        return Response(xml_response, mimetype='application/xml'), 200
        
    except Exception as e:
        logger.error(f"Critical Error: {e}", exc_info=True)
        return _create_error_response("System Error")


# ============================================================================
# WEBHOOK AUXILIAR (Hangup XML)
# ============================================================================

@app.route('/webhook/call-completed', methods=['POST'])
def webhook_call_completed():
    response = VoiceResponse()
    response.hangup()
    return Response(str(response), mimetype='application/xml'), 200


# ============================================================================
# WEBHOOKS STATUS (JSON)
# ============================================================================

@app.route('/webhook/recording', methods=['POST'])
def webhook_recording():
    try:
        call_sid = request.values.get('CallSid')
        recording_url = request.values.get('RecordingUrl')
        if recording_url: recording_url += '.mp3'
        
        db.update_call_recording(
            call_sid=call_sid,
            recording_url=recording_url,
            recording_sid=request.values.get('RecordingSid'),
            recording_duration=int(request.values.get('RecordingDuration', 0) or 0)
        )
        return jsonify({'success': True}), 200
    except Exception:
        return jsonify({'error': 'failed'}), 500

@app.route('/webhook/call-status', methods=['POST'])
def webhook_call_status():
    try:
        call_sid = request.values.get('CallSid')
        
        db.update_call_status(
            call_sid=call_sid,
            status=request.values.get('CallStatus'),
            duration=int(request.values.get('CallDuration', 0) or 0)
        )
        return jsonify({'success': True}), 200
    except Exception as e:
        logger.error(f"Status Error: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# FUNÇÕES TWIML
# ============================================================================

def _create_forward_response(destination: str, from_number: str) -> str:
    response = VoiceResponse()
    
    dial = Dial(
        caller_id=from_number,
        action='/webhook/call-completed', 
        method='POST',
        timeout=30,
        record='record-from-answer',
        recording_status_callback='/webhook/recording',
        recording_status_callback_method='POST',
        recording_status_callback_event='completed' 
    )
    
    dial.number(
        destination,
        status_callback_event='initiated ringing answered completed', 
        status_callback='/webhook/call-status', 
        status_callback_method='POST'
    )
    
    response.append(dial)
    response.say('A ligação não pode ser completada.', language='pt-BR', voice='Polly.Camila')
    return str(response)

def _create_no_destination_response() -> tuple[Response, int]:
    response = VoiceResponse()
    response.say('Número indisponível.', language='pt-BR', voice='Polly.Camila')
    response.hangup()
    return Response(str(response), mimetype='application/xml'), 200

def _create_error_response(msg: str) -> tuple[Response, int]:
    response = VoiceResponse()
    response.say('Erro técnico.', language='pt-BR', voice='Polly.Camila')
    response.hangup()
    return Response(str(response), mimetype='application/xml'), 200

# ============================================================================
# MAIN
# ============================================================================

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy', 'version': '2.3-schema-fix'}), 200

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5001))
    app.run(host='0.0.0.0', port=port)