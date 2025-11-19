"""
Database Service - COMPLETO (Telefonia + CRM + Timeline)
"""
from supabase import create_client, Client
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging
import os
from functools import lru_cache

logger = logging.getLogger(__name__)

class DatabaseService:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        
        if not url or not key:
            logger.error("❌ Supabase credentials missing")
            return

        try:
            self.client = create_client(url, key)
            logger.info("✅ Supabase client initialized")
        except Exception as e:
            logger.error(f"❌ Init error: {e}")

    # ========================================================================
    # 1. TELEFONIA & ROTEAMENTO
    # ========================================================================
    
    def get_destination_number(self, tracking_number: str, campaign: str = None) -> Optional[str]:
        try:
            # 1. Tenta campanha específica
            if campaign:
                res = self.client.table('phone_routing').select('destination_number')\
                    .eq('tracking_number', tracking_number).eq('is_active', True).eq('campaign', campaign).execute()
                if res.data: return res.data[0]['destination_number']

            # 2. Fallback genérico
            res = self.client.table('phone_routing').select('destination_number')\
                .eq('tracking_number', tracking_number).eq('is_active', True).is_('campaign', 'null').execute()
            
            return res.data[0]['destination_number'] if res.data else None
        except Exception as e:
            logger.error(f"Routing error: {e}")
            return None

    def add_phone_routing(self, tracking: str, destination: str, campaign: str = None):
        data = {'tracking_number': tracking, 'destination_number': destination, 'campaign': campaign, 'is_active': True}
        return self.client.table('phone_routing').insert(data).execute()

    # ========================================================================
    # 2. TRACKING & REGISTRO DE CHAMADAS
    # ========================================================================

    def get_or_create_tracking_source(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            t_num = data.get('tracking_number')
            query = self.client.table('tracking_sources').select('*').eq('tracking_number', t_num)
            
            if data.get('gclid'): query = query.eq('gclid', data.get('gclid'))
            elif data.get('utm_campaign'): query = query.eq('utm_campaign', data.get('utm_campaign'))
            
            res = query.limit(1).execute()
            
            if res.data:
                self.client.table('tracking_sources').update({'last_call_at': datetime.utcnow().isoformat()}).eq('id', res.data[0]['id']).execute()
                return res.data[0]
            
            clean_data = {k: v for k, v in data.items() if v is not None}
            clean_data['created_at'] = datetime.utcnow().isoformat()
            return self.client.table('tracking_sources').insert(clean_data).execute().data[0]
        except Exception: return None

    def insert_call(self, call_data: Dict[str, Any]):
        clean = {k: v for k, v in call_data.items() if v is not None}
        return self.client.table('calls').insert(clean).execute()

    def update_call_status(self, call_sid, status, duration=0):
        data = {'status': status, 'updated_at': datetime.utcnow().isoformat()}
        if duration > 0: data['duration'] = duration
        self.client.table('calls').update(data).eq('call_sid', call_sid).execute()

    def update_call_recording(self, call_sid, url, sid, duration):
        data = {'recording_url': url, 'recording_sid': sid, 'recording_duration': duration, 'updated_at': datetime.utcnow().isoformat()}
        self.client.table('calls').update(data).eq('call_sid', call_sid).execute()

    def update_call_tag(self, call_sid: str, tag: str) -> bool:
        try:
            val = tag if tag and tag != "Limpar" else None
            self.client.table('calls').update({'tags': val, 'updated_at': datetime.utcnow().isoformat()}).eq('call_sid', call_sid).execute()
            return True
        except Exception as e:
            logger.error(f"Tag update error: {e}")
            return False

    # ========================================================================
    # 3. CRM & KANBAN (Novas Funções)
    # ========================================================================

    def update_deal_stage(self, deal_id: str, new_stage_id: str) -> bool:
        """Move o card para outra coluna."""
        try:
            self.client.table('deals').update({
                'stage_id': new_stage_id,
                'last_activity_at': datetime.utcnow().isoformat()
            }).eq('id', deal_id).execute()
            return True
        except Exception as e:
            logger.error(f"❌ Error moving deal: {e}")
            return False

    def get_contact_timeline(self, contact_id: str) -> List[Dict[str, Any]]:
        """Busca todo o histórico do contato (Timeline)."""
        try:
            # Busca eventos ordenados do mais recente para o antigo
            result = self.client.table('timeline_events')\
                .select('*')\
                .eq('contact_id', contact_id)\
                .order('created_at', desc=True)\
                .execute()
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"❌ Error fetching timeline: {e}")
            return []

    def health_check(self) -> bool:
        try:
            self.client.table('calls').select('call_sid').limit(1).execute()
            return True
        except: return False

@lru_cache()
def get_database_service() -> DatabaseService:
    return DatabaseService()