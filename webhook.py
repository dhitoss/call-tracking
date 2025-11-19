"""
Webhook Completo - Multi-Tenancy Enabled
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

app = Flask(__name__)
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

db = DatabaseService()
crm = CRMService()

TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN', '')
DEBUG_MODE = os.getenv('DEBUG', 'false').lower() == 'true'

def validate_twilio_request() -> bool:
    if DEBUG_MODE or not TWILIO_AUTH_TOKEN: return True
    try:
        validator = RequestValidator(TWILIO_AUTH_TOKEN)
        url = request.url
        if request.headers.get('X-Forwarded-Proto') == 'https':
            url = url.replace('http://', 'https://', 1)
        params = request.form.to_dict() if request.method == 'POST' else request.args.to_dict()
        signature = request.headers.get('X-Twilio-Signature', '')
        return validator.validate(url, params, signature)
    except: return True

@app.route('/webhook/call', methods=['POST', 'GET'])
def webhook_call():
    call_sid = request.values.get('CallSid', 'unknown')
    
    try:
        validate_twilio_request()
        
        from_number = request.values.get('From')
        to_number = request.values.get('To')
        call_status = request.values.get('CallStatus', 'initiated')
        campaign = request.args.get('campaign')
        utm_campaign = request.args.get('utm_campaign')
        
        logger.info(f"📞 Call: {call_sid} | {from_number} -> {to_number}")

        # 1. Identificar Rota e Organização (O FIX ESTÁ AQUI)
        routing_info = db.get_routing_info(to_number)
        destination = None
        org_id = None

        if routing_info:
            destination = routing_info.get('destination_number')
            org_id = routing_info.get('organization_id')
        else:
            # Fallback legado
            destination = db.get_destination_number(to_number, campaign)

        if not destination:
            return _create_xml_response("Número não configurado.")

        # 2. Tracking
        tracking_source_id = None
        try:
            t_data = {
                'tracking_number': to_number,
                'utm_source': request.args.get('utm_source'),
                'utm_medium': request.args.get('utm_medium'),
                'utm_campaign': utm_campaign or campaign,
                'gclid': request.args.get('gclid'),
                'organization_id': org_id # Vincula tracking à org
            }
            if any(t_data.values()):
                ts = db.get_or_create_tracking_source(t_data)
                tracking_source_id = ts.get('id') if ts else None
        except Exception as e:
            logger.error(f"Tracking error: {e}")

        # 3. Registrar Chamada
        try:
            call_data = {
                'call_sid': call_sid,
                'from_number': from_number,
                'to_number': to_number,
                'destination_number': destination,
                'status': call_status,
                'campaign': campaign or utm_campaign,
                'tracking_source_id': tracking_source_id,
                'organization_id': org_id, # <--- O DADO CRÍTICO
                'created_at': datetime.utcnow().isoformat()
            }
            db.insert_call(call_data)
            logger.info("✅ Call inserted successfully")

            # 4. Acionar CRM (Se tiver dono)
            if org_id:
                try:
                    crm.handle_incoming_call_event(call_data)
                    logger.info(f"✅ CRM triggered for Org {org_id}")
                except Exception as crm_e:
                    logger.error(f"CRM Error: {crm_e}")
            else:
                logger.warning("⚠️ Call skipped CRM (No Organization ID)")

        except Exception as e:
            logger.error(f"Insert error: {e}")
        
        # 5. Conectar Chamada
        return _create_forward_response(destination, from_number)
        
    except Exception as e:
        logger.error(f"Critical: {e}", exc_info=True)
        return _create_xml_response("Erro técnico.")

@app.route('/webhook/call-completed', methods=['POST'])
def webhook_call_completed():
    res = VoiceResponse()
    res.hangup()
    return Response(str(res), mimetype='application/xml'), 200

@app.route('/webhook/recording', methods=['POST'])
def webhook_recording():
    try:
        sid = request.values.get('CallSid')
        url = request.values.get('RecordingUrl')
        if url: url += '.mp3'
        db.update_call_recording(sid, url, request.values.get('RecordingSid'), int(request.values.get('RecordingDuration', 0) or 0))
        return jsonify({'success': True}), 200
    except: return jsonify({'error': 'failed'}), 500

@app.route('/webhook/call-status', methods=['POST'])
def webhook_call_status():
    try:
        sid = request.values.get('CallSid')
        db.update_call_status(sid, request.values.get('CallStatus'), int(request.values.get('CallDuration', 0) or 0))
        return jsonify({'success': True}), 200
    except: return jsonify({'error': 'failed'}), 500

def _create_forward_response(destination, from_number):
    res = VoiceResponse()
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
    dial.number(destination, status_callback_event='initiated ringing answered completed', status_callback='/webhook/call-status', status_callback_method='POST')
    res.append(dial)
    return Response(str(res), mimetype='application/xml'), 200

def _create_xml_response(msg):
    res = VoiceResponse()
    res.say(msg, language='pt-BR')
    res.hangup()
    return Response(str(res), mimetype='application/xml'), 200

@app.route('/health', methods=['GET'])
def health(): return jsonify({'status': 'healthy'}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5001)))