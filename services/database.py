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
    
    def insert_call(self, call: CallRecord) -> Dict[str, Any]:
        """
        Insere novo registro de chamada.
        
        Args:
            call: Registro de chamada validado
            
        Returns:
            Registro inserido com ID do banco
        """
        try:
            data = {
                'call_sid': call.call_sid,
                'from_number': call.from_number,
                'to_number': call.to_number,
                'status': call.status,
                'duration': call.duration,
                'campaign_id': call.campaign_id,
                'created_at': call.created_at.isoformat(),
                'updated_at': call.updated_at.isoformat()
            }
            
            result = self.client.table('calls').insert(data).execute()
            
            logger.info(f"✅ Call inserted: {call.call_sid}")
            return result.data[0] if result.data else {}
            
        except Exception as e:
            logger.error(f"❌ Failed to insert call {call.call_sid}: {str(e)}")
            raise
    
    def get_calls(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        campaign_ids: Optional[List[str]] = None,
        statuses: Optional[List[str]] = None,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        Busca chamadas com filtros opcionais.
        Query otimizada com índices.
        
        Args:
            start_date: Data inicial (inclusive)
            end_date: Data final (inclusive)
            campaign_ids: Lista de IDs de campanha
            statuses: Lista de status para filtrar
            limit: Limite de registros
            
        Returns:
            Lista de registros de chamadas
        """
        try:
            query = self.client.table('calls').select('*')
            
            # Date range filter
            if start_date:
                query = query.gte('created_at', start_date.isoformat())
            if end_date:
                # Add 1 day to include end_date
                end_datetime = datetime.combine(
                    end_date, 
                    datetime.max.time()
                )
                query = query.lte('created_at', end_datetime.isoformat())
            
            # Campaign filter
            if campaign_ids:
                query = query.in_('campaign_id', campaign_ids)
            
            # Status filter
            if statuses:
                query = query.in_('status', statuses)
            
            # Order and limit
            query = query.order('created_at', desc=True).limit(limit)
            
            result = query.execute()
            
            logger.info(f"✅ Retrieved {len(result.data)} calls")
            return result.data
            
        except Exception as e:
            logger.error(f"❌ Failed to get calls: {str(e)}")
            raise
    
    def get_unique_campaigns(self) -> List[str]:
        """Retorna lista de campanhas únicas no banco."""
        try:
            result = self.client.table('calls')\
                .select('campaign_id')\
                .not_.is_('campaign_id', 'null')\
                .execute()
            
            campaigns = list(set(
                row['campaign_id'] 
                for row in result.data 
                if row['campaign_id']
            ))
            
            return sorted(campaigns)
            
        except Exception as e:
            logger.error(f"❌ Failed to get campaigns: {str(e)}")
            return []
    
    def health_check(self) -> bool:
        """Verifica se conexão com banco está OK."""
        try:
            self.client.table('calls').select('id').limit(1).execute()
            return True
        except:
            return False


@lru_cache()
def get_database_service() -> DatabaseService:
    """Factory function para obter instância do serviço."""
    return DatabaseService()