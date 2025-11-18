"""
Camada de acesso ao banco de dados via Supabase.
Implementa singleton pattern e connection pooling.
"""
from supabase import create_client, Client
from typing import List, Optional, Dict, Any
from datetime import datetime, date
import logging
from functools import lru_cache

from config import settings
from models.call import CallRecord


logger = logging.getLogger(__name__)


class DatabaseService:
    """
    Serviço singleton para operações de banco de dados.
    Gerencia conexão com Supabase e queries otimizadas.
    """
    
    _instance: Optional['DatabaseService'] = None
    _client: Optional[Client] = None
    
    def __new__(cls) -> 'DatabaseService':
        """Implementa singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self) -> None:
        """Inicializa conexão com Supabase."""
        try:
            self._client = create_client(
                settings.SUPABASE_URL,
                settings.SUPABASE_KEY
            )
            logger.info("✅ Supabase client initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Supabase: {str(e)}")
            raise
    
    @property
    def client(self) -> Client:
        """Retorna cliente Supabase."""
        if self._client is None:
            raise RuntimeError("Database client not initialized")
        return self._client
    
    # ========================================================================
    # ROUTING - Number Masking
    # ========================================================================
    
    def get_destination_number(
        self, 
        tracking_number: str, 
        campaign: Optional[str] = None
    ) -> Optional[str]:
        """
        Busca número de destino configurado para o número rastreado.
        
        Args:
            tracking_number: Número que recebeu a chamada
            campaign: Campanha específica (opcional)
            
        Returns:
            Número de destino ou None se não encontrado
        """
        try:
            query = self.client.table('phone_routing').select('destination_number')
            
            # Filtros
            query = query.eq('tracking_number', tracking_number)
            query = query.eq('is_active', True)
            
            if campaign:
                # Busca por campanha específica OU genérico (campaign NULL)
                query = query.or_(f'campaign.eq.{campaign},campaign.is.null')
            
            # Ordenar: campanhas específicas primeiro
            query = query.order('campaign', desc=False)
            
            result = query.limit(1).execute()
            
            if result.data:
                destination = result.data[0]['destination_number']
                logger.info(f"✅ Destination found: {tracking_number} → {destination}")
                return destination
            
            logger.warning(f"⚠️ No destination found for {tracking_number}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error fetching destination: {e}")
            return None
    
    
    def add_phone_routing(
        self,
        tracking_number: str,
        destination_number: str,
        campaign: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Adiciona nova rota de número.
        
        Args:
            tracking_number: Número rastreado (ex: +5511999990000)
            destination_number: Número final (ex: +5511888880000)
            campaign: Nome da campanha (opcional)
            
        Returns:
            Dados da rota criada
        """
        try:
            data = {
                'tracking_number': tracking_number,
                'destination_number': destination_number,
                'campaign': campaign,
                'is_active': True,
                'created_at': datetime.utcnow().isoformat()
            }
            
            result = self.client.table('phone_routing').insert(data).execute()
            
            logger.info(f"✅ Route added: {tracking_number} → {destination_number}")
            return result.data[0] if result.data else None
            
        except Exception as e:
            logger.error(f"❌ Error adding route: {e}")
            raise
    
    
    def update_phone_routing(
        self,
        routing_id: str,
        destination_number: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> bool:
        """
        Atualiza rota existente.
        
        Args:
            routing_id: UUID da rota
            destination_number: Novo número (opcional)
            is_active: Ativar/desativar (opcional)
            
        Returns:
            True se atualizado com sucesso
        """
        try:
            data = {'updated_at': datetime.utcnow().isoformat()}
            
            if destination_number:
                data['destination_number'] = destination_number
            
            if is_active is not None:
                data['is_active'] = is_active
            
            result = self.client.table('phone_routing').update(data).eq('id', routing_id).execute()
            
            logger.info(f"✅ Route updated: {routing_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error updating route: {e}")
            return False
    
    
    # ========================================================================
    # TRACKING - UTM/GCLID
    # ========================================================================
    
    def get_or_create_tracking_source(
        self,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Busca ou cria tracking source baseado em UTM/GCLID.
        
        Args:
            data: Dict com tracking_number, utm_*, gclid
            
        Returns:
            Tracking source (existente ou novo)
        """
        try:
            tracking_number = data.get('tracking_number')
            gclid = data.get('gclid')
            utm_campaign = data.get('utm_campaign')
            
            # Tentar encontrar existente
            query = self.client.table('tracking_sources').select('*')
            query = query.eq('tracking_number', tracking_number)
            
            if gclid:
                query = query.eq('gclid', gclid)
            elif utm_campaign:
                query = query.eq('utm_campaign', utm_campaign)
            
            result = query.limit(1).execute()
            
            if result.data:
                # Atualizar last_call_at
                source_id = result.data[0]['id']
                self.client.table('tracking_sources').update({
                    'last_call_at': datetime.utcnow().isoformat()
                }).eq('id', source_id).execute()
                
                logger.info(f"📊 Tracking source found: {source_id}")
                return result.data[0]
            
            # Criar novo
            new_source = {
                'tracking_number': tracking_number,
                'utm_source': data.get('utm_source'),
                'utm_medium': data.get('utm_medium'),
                'utm_campaign': utm_campaign,
                'utm_content': data.get('utm_content'),
                'utm_term': data.get('utm_term'),
                'gclid': gclid,
                'created_at': datetime.utcnow().isoformat(),
                'last_call_at': datetime.utcnow().isoformat()
            }
            
            result = self.client.table('tracking_sources').insert(new_source).execute()
            
            logger.info(f"✅ New tracking source created")
            return result.data[0] if result.data else None
            
        except Exception as e:
            logger.error(f"❌ Error with tracking source: {e}")
            return None
    
    
    # ========================================================================
    # RECORDINGS
    # ========================================================================
    
    def update_call_recording(
        self,
        call_sid: str,
        recording_url: str,
        recording_sid: str,
        recording_duration: int
    ) -> bool:
        """
        Atualiza registro da chamada com dados da gravação.
        
        Args:
            call_sid: ID da chamada
            recording_url: URL da gravação no Twilio
            recording_sid: ID da gravação
            recording_duration: Duração em segundos
            
        Returns:
            True se atualizado com sucesso
        """
        try:
            data = {
                'recording_url': recording_url,
                'recording_sid': recording_sid,
                'recording_duration': recording_duration,
                'updated_at': datetime.utcnow().isoformat()
            }
            
            result = self.client.table('calls').update(data).eq('call_sid', call_sid).execute()
            
            logger.info(f"🎙️ Recording updated for {call_sid}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error updating recording: {e}")
            return False
    
    
    # ========================================================================
    # CALL STATUS
    # ========================================================================
    
    def update_call_status(
        self,
        call_sid: str,
        status: str,
        duration: int = 0
    ) -> bool:
        """
        Atualiza status da chamada.
        
        Args:
            call_sid: ID da chamada
            status: Status (completed, busy, no-answer, etc)
            duration: Duração em segundos
            
        Returns:
            True se atualizado com sucesso
        """
        try:
            data = {
                'status': status,
                'updated_at': datetime.utcnow().isoformat()
            }
            
            if duration > 0:
                data['duration'] = duration
            
            result = self.client.table('calls').update(data).eq('call_sid', call_sid).execute()
            
            logger.info(f"📊 Status updated: {call_sid} → {status}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error updating status: {e}")
            return False
    
    
    # ========================================================================
    # CALL INSERT (atualizado com novos campos)
    # ========================================================================
    
    def insert_call(self, call_data: Dict[str, Any]) -> Optional[str]:
        """
        Insere nova chamada no banco (versão atualizada).
        
        Args:
            call_data: Dict com dados da chamada
            
        Returns:
            Call SID se sucesso, None se erro
        """
        try:
            # Garantir campos obrigatórios
            required = ['call_sid', 'from_number', 'to_number']
            for field in required:
                if field not in call_data:
                    raise ValueError(f"Missing required field: {field}")
            
            # Adicionar timestamp se não existir
            if 'created_at' not in call_data:
                call_data['created_at'] = datetime.utcnow().isoformat()
            
            # Inserir no banco
            result = self.client.table('calls').insert(call_data).execute()
            
            call_sid = call_data['call_sid']
            logger.info(f"✅ Call inserted: {call_sid}")
            
            return call_sid
            
        except Exception as e:
            logger.error(f"❌ Error inserting call: {e}", exc_info=True)
            return None
    
    
    # ========================================================================
    # HEALTH CHECK
    # ========================================================================
    
    def health_check(self) -> bool:
        """
        Verifica se conexão com banco está funcionando.
        
        Returns:
            True se conectado
        """
        try:
            # Tenta fazer uma query simples
            result = self.client.table('calls').select('call_sid').limit(1).execute()
            return True
        except Exception as e:
            logger.error(f"❌ Database health check failed: {e}")
            return False



@lru_cache()
def get_database_service() -> DatabaseService:
    """Factory function para obter instância do serviço."""
    return DatabaseService()