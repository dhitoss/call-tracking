"""
Camada de acesso ao banco de dados via Supabase.
Implementa singleton pattern e connection pooling.
VERSÃO CORRIGIDA (Fix .or_ error & Insert logic)
"""
from supabase import create_client, Client
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging
import os
from functools import lru_cache

# Se você tiver um arquivo config.py, pode manter o import, 
# mas aqui usamos os.getenv para garantir funcionamento standalone
# from config import settings 

logger = logging.getLogger(__name__)

class DatabaseService:
    """
    Serviço singleton para operações de banco de dados.
    """
    
    _instance: Optional['DatabaseService'] = None
    _client: Optional[Client] = None
    
    def __new__(cls) -> 'DatabaseService':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self) -> None:
        """Inicializa conexão com Supabase."""
        # Tenta pegar do ambiente (mais robusto para Railway/Docker)
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        
        if not url or not key:
            logger.error("❌ Supabase credentials missing (SUPABASE_URL or SUPABASE_KEY)")
            return

        try:
            self._client = create_client(url, key)
            logger.info("✅ Supabase client initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Supabase: {str(e)}")
            raise
    
    @property
    def client(self) -> Client:
        if self._client is None:
            # Tenta reinicializar se perdeu a referência
            self._initialize()
            if self._client is None:
                raise RuntimeError("Database client not initialized")
        return self._client
    
    # ========================================================================
    # ROUTING - Number Masking (LÓGICA CORRIGIDA)
    # ========================================================================
    
    def get_destination_number(
        self, 
        tracking_number: str, 
        campaign: Optional[str] = None
    ) -> Optional[str]:
        """
        Busca número de destino.
        Lógica corrigida para evitar erro de '.or_' no postgrest.
        """
        try:
            # 1. Tenta buscar rota com campanha específica (Prioridade)
            if campaign:
                result = self.client.table('phone_routing')\
                    .select('destination_number')\
                    .eq('tracking_number', tracking_number)\
                    .eq('is_active', True)\
                    .eq('campaign', campaign)\
                    .execute()
                
                if result.data:
                    dest = result.data[0]['destination_number']
                    logger.info(f"✅ Destination found (Campaign '{campaign}'): {dest}")
                    return dest

            # 2. Se não achou ou sem campanha, busca rota genérica (campaign IS NULL)
            # A sintaxe correta para NULL no supabase-py é .is_('coluna', 'null')
            result = self.client.table('phone_routing')\
                .select('destination_number')\
                .eq('tracking_number', tracking_number)\
                .eq('is_active', True)\
                .is_('campaign', 'null')\
                .execute()
            
            if result.data:
                dest = result.data[0]['destination_number']
                logger.info(f"✅ Destination found (Generic): {dest}")
                return dest
            
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
        try:
            data = {
                'tracking_number': tracking_number,
                'destination_number': destination_number,
                'campaign': campaign,
                'is_active': True,
                'created_at': datetime.utcnow().isoformat()
            }
            
            result = self.client.table('phone_routing').insert(data).execute()
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
        try:
            data = {'updated_at': datetime.utcnow().isoformat()}
            if destination_number: data['destination_number'] = destination_number
            if is_active is not None: data['is_active'] = is_active
            
            self.client.table('phone_routing').update(data).eq('id', routing_id).execute()
            return True
        except Exception as e:
            logger.error(f"❌ Error updating route: {e}")
            return False
    
    
    # ========================================================================
    # TRACKING - UTM/GCLID
    # ========================================================================
    
    def get_or_create_tracking_source(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            tracking_number = data.get('tracking_number')
            
            # Query base
            query = self.client.table('tracking_sources').select('*').eq('tracking_number', tracking_number)
            
            # Busca específica
            if data.get('gclid'):
                query = query.eq('gclid', data.get('gclid'))
            elif data.get('utm_campaign'):
                query = query.eq('utm_campaign', data.get('utm_campaign'))
            
            result = query.limit(1).execute()
            
            if result.data:
                # Atualiza timestamp
                sid = result.data[0]['id']
                self.client.table('tracking_sources').update({
                    'last_call_at': datetime.utcnow().isoformat()
                }).eq('id', sid).execute()
                return result.data[0]
            
            # Cria novo (Remove campos nulos)
            clean_data = {k: v for k, v in data.items() if v is not None}
            clean_data['created_at'] = datetime.utcnow().isoformat()
            clean_data['last_call_at'] = datetime.utcnow().isoformat()
            
            result = self.client.table('tracking_sources').insert(clean_data).execute()
            return result.data[0] if result.data else None
            
        except Exception as e:
            logger.error(f"❌ Error with tracking source: {e}")
            return None
    
    
    # ========================================================================
    # RECORDINGS & STATUS
    # ========================================================================
    
    def update_call_recording(
        self,
        call_sid: str,
        recording_url: str,
        recording_sid: str,
        recording_duration: int
    ) -> bool:
        try:
            data = {
                'recording_url': recording_url,
                'recording_sid': recording_sid,
                'recording_duration': recording_duration,
                'updated_at': datetime.utcnow().isoformat()
            }
            self.client.table('calls').update(data).eq('call_sid', call_sid).execute()
            return True
        except Exception as e:
            logger.error(f"❌ Error updating recording: {e}")
            return False
    
    def update_call_status(self, call_sid: str, status: str, duration: int = 0) -> bool:
        try:
            data = {
                'status': status,
                'updated_at': datetime.utcnow().isoformat()
            }
            if duration > 0:
                data['duration'] = duration
            
            self.client.table('calls').update(data).eq('call_sid', call_sid).execute()
            return True
        except Exception as e:
            logger.error(f"❌ Error updating status: {e}")
            return False
    
    
    # ========================================================================
    # CALL INSERT (Lógica robusta)
    # ========================================================================
    
    def insert_call(self, call_data: Dict[str, Any]) -> Optional[str]:
        """
        Insere chamada. Remove chaves com valores None para evitar erros.
        """
        try:
            required = ['call_sid', 'from_number', 'to_number']
            for field in required:
                if field not in call_data:
                    raise ValueError(f"Missing required field: {field}")
            
            if 'created_at' not in call_data:
                call_data['created_at'] = datetime.utcnow().isoformat()
            
            # Limpeza: Remove campos None (o Supabase pode reclamar se a coluna não aceitar null ou se não existir default)
            clean_data = {k: v for k, v in call_data.items() if v is not None}
            
            result = self.client.table('calls').insert(clean_data).execute()
            
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
        try:
            self.client.table('calls').select('call_sid').limit(1).execute()
            return True
        except Exception as e:
            logger.error(f"❌ Database health check failed: {e}")
            return False
    # ========================================================================
    # TAGS
    # ========================================================================
    

    def update_call_tag(self, call_sid: str, tag: str) -> bool:
        """Atualiza a tag de uma chamada."""
        try:
            # Se a tag for "Limpar" ou vazia, salvamos como null
            value = tag if tag and tag != "Limpar" else None
            
            self.client.table('calls').update({
                'tags': value,
                'updated_at': datetime.utcnow().isoformat()
            }).eq('call_sid', call_sid).execute()
            
            logger.info(f"🏷️ Tag updated: {call_sid} -> {value}")
            return True
        except Exception as e:
            logger.error(f"❌ Error updating tag: {e}")
            return False        

@lru_cache()
def get_database_service() -> DatabaseService:
    return DatabaseService()