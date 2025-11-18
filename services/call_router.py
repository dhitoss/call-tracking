from twilio.twiml.voice_response import VoiceResponse
from services.database import DatabaseService
import logging

logger = logging.getLogger(__name__)

class CallRouter:
    def __init__(self, db_service: DatabaseService):
        self.db = db_service
    
    async def route_call(self, from_number: str, to_number: str, campaign: str = None) -> str:
        """
        Roteia a chamada para o número de destino configurado
        """
        # Buscar número de destino no banco
        destination = await self._get_destination_number(to_number, campaign)
        
        if not destination:
            logger.error(f"❌ Nenhum destino encontrado para {to_number}")
            return self._create_error_response()
        
        logger.info(f"📞 Roteando {from_number} → {destination}")
        return self._create_forward_response(destination)
    
    async def _get_destination_number(self, tracking_number: str, campaign: str = None) -> str:
        """Busca número de destino no banco"""
        query = """
            SELECT destination_number 
            FROM phone_routing 
            WHERE tracking_number = $1 
            AND is_active = true
        """
        if campaign:
            query += " AND (campaign = $2 OR campaign IS NULL)"
            result = await self.db.client.from_('phone_routing').select('destination_number').eq('tracking_number', tracking_number).eq('is_active', True).execute()
        else:
            result = await self.db.client.from_('phone_routing').select('destination_number').eq('tracking_number', tracking_number).eq('is_active', True).execute()
        
        if result.data:
            return result.data[0]['destination_number']
        return None
    
    def _create_forward_response(self, destination: str) -> str:
        """Cria TwiML para encaminhar chamada"""
        response = VoiceResponse()
        response.dial(destination, 
                     caller_id=None,  # mantém caller ID original
                     record='record-from-answer',  # já inicia gravação!
                     recording_status_callback='/webhook/recording')
        return str(response)
    
    def _create_error_response(self) -> str:
        """TwiML de erro"""
        response = VoiceResponse()
        response.say('Desculpe, não foi possível completar sua ligação.', 
                    language='pt-BR', voice='Polly.Camila')
        return str(response)