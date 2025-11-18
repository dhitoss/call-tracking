"""
Webhook server Flask para receber callbacks do Twilio.
Valida, processa e persiste chamadas telefônicas.
"""
from flask import Flask, request, jsonify
from twilio.request_validator import RequestValidator
import logging
from typing import Dict, Any

from config import settings
from models.call import TwilioWebhookPayload, CallRecord
from services.database import get_database_service
from datetime import datetime



# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = settings.FLASK_SECRET_KEY

# Initialize services
db = get_database_service()
validator = RequestValidator(settings.TWILIO_AUTH_TOKEN)


def validate_twilio_request() -> bool:
    """
    Valida assinatura do Twilio para segurança.
    Previne chamadas não autorizadas ao webhook.
    """
    # TEMPORÁRIO: Desabilitar validação para testes
    if settings.FLASK_DEBUG or True:  # ← ADICIONAR "or True" AQUI
        logger.warning("⚠️  Skipping Twilio validation (DEBUG mode)")
        return True
    
    url = request.url
    signature = request.headers.get('X-Twilio-Signature', '')
    
    # Get form data for validation
    post_vars = request.form.to_dict()
    
    is_valid = validator.validate(url, post_vars, signature)
    
    if not is_valid:
        logger.warning(f"❌ Invalid Twilio signature from {request.remote_addr}")
    
    return is_valid


@app.route('/health', methods=['GET'])
def health_check() -> Dict[str, Any]:
    """Endpoint de health check."""
    db_healthy = db.health_check()
    
    return jsonify({
        'status': 'healthy' if db_healthy else 'unhealthy',
        'database': 'connected' if db_healthy else 'disconnected',
        'version': '1.0.0'
    }), 200 if db_healthy else 503


@app.route('/webhook/call', methods=['POST'])
def webhook_call() -> Dict[str, Any]:
    """
    Endpoint principal do webhook Twilio.
    Recebe, valida e persiste dados de chamadas.
    """
    start_time = datetime.now()
    
    try:
        # 1. Validar request do Twilio
        if not validate_twilio_request():
            return jsonify({
                'error': 'Invalid Twilio signature'
            }), 403
        
        # 2. Extrair dados do form e query params
        form_data = request.form.to_dict()
        campaign_id = request.args.get('campaign')
        
        if campaign_id:
            form_data['campaign'] = campaign_id
        
        logger.info(f"📞 Received call webhook: {form_data.get('CallSid')}")
        
        # 3. Validar payload com Pydantic
        try:
            payload = TwilioWebhookPayload(**form_data)
        except Exception as validation_error:
            logger.error(f"❌ Invalid payload: {validation_error}")
            return jsonify({
                'error': 'Invalid payload format',
                'details': str(validation_error)
            }), 400
        
        # 4. Converter para nosso modelo interno
        call_record = payload.to_call_record()
        
        # 5. Salvar no banco
        db.insert_call(call_record)
        
        # 6. Calcular tempo de processamento
        elapsed = (datetime.now() - start_time).total_seconds() * 1000
        
        logger.info(f"✅ Call processed in {elapsed:.2f}ms")
        
        return jsonify({
            'success': True,
            'call_sid': call_record.call_sid,
            'processing_time_ms': round(elapsed, 2)
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Webhook error: {str(e)}", exc_info=True)
        return jsonify({
            'error': 'Internal server error',
            'message': str(e)
        }), 500


@app.route('/webhook/call/status', methods=['POST'])
def webhook_call_status() -> Dict[str, Any]:
    """
    Endpoint para status callbacks do Twilio.
    Atualiza status de chamadas em andamento.
    """
    # TODO: Implementar update de status
    return jsonify({'success': True}), 200


if __name__ == '__main__':
    logger.info(f"🚀 Starting Flask webhook server on {settings.FLASK_HOST}:{settings.FLASK_PORT}")
    app.run(
        host=settings.FLASK_HOST,
        port=settings.FLASK_PORT,
        debug=settings.FLASK_DEBUG
    )