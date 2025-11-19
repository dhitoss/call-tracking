"""
Database Service - COMPLETO (v2.7)
Inclui: Telefonia, CRM, Logs, Leads Manuais e Relatórios de Marketing.
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
            if campaign:
                res = self.client.table('phone_routing').select('destination_number')\
                    .eq('tracking_number', tracking_number).eq('is_active', True).eq('campaign', campaign).execute()
                if res.data: return res.data[0]['destination_number']

            res = self.client.table('phone_routing').select('destination_number')\
                .eq('tracking_number', tracking_number).eq('is_active', True).is_('campaign', 'null').execute()
            
            return res.data[0]['destination_number'] if res.data else None
        except Exception as e:
            logger.error(f"Routing error: {e}")
            return None

    def add_phone_routing(self, tracking: str, destination: str, campaign: str = None):
        data = {'tracking_number': tracking, 'destination_number': destination, 'campaign': campaign, 'is_active': True}
        return self.client.table('phone_routing').insert(data).execute()

    def get_routes(self):
        """Retorna todas as rotas configuradas."""
        try:
            res = self.client.table('phone_routing').select('*').order('created_at', desc=True).execute()
            return res.data if res.data else []
        except Exception as e:
            logger.error(f"Get routes error: {e}")
            return []

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
    # 3. CRM, KANBAN & INTERAÇÕES
    # ========================================================================

    def update_deal_stage(self, deal_id: str, new_stage_id: str) -> bool:
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
        try:
            result = self.client.table('timeline_events')\
                .select('*')\
                .eq('contact_id', contact_id)\
                .order('created_at', desc=True)\
                .execute()
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"❌ Error fetching timeline: {e}")
            return []

    def create_manual_lead(self, name: str, phone: str, source: str, note: str = None) -> bool:
        try:
            now = datetime.utcnow().isoformat()
            contact_res = self.client.table('contacts').select('id').eq('phone_number', phone).execute()
            
            if contact_res.data:
                contact_id = contact_res.data[0]['id']
                self.client.table('contacts').update({'name': name}).eq('id', contact_id).execute()
            else:
                new_contact = {'phone_number': phone, 'name': name, 'created_at': now}
                res = self.client.table('contacts').insert(new_contact).execute()
                contact_id = res.data[0]['id']

            stage_res = self.client.table('pipeline_stages').select('id').eq('is_default', True).limit(1).execute()
            stage_id = stage_res.data[0]['id'] if stage_res.data else None

            deal_data = {
                'contact_id': contact_id, 'stage_id': stage_id, 'title': f"Lead Manual: {name}",
                'status': 'OPEN', 'source': source, 'last_activity_at': now
            }
            deal_res = self.client.table('deals').insert(deal_data).execute()
            
            self.client.table('timeline_events').insert({
                'contact_id': contact_id, 'deal_id': deal_res.data[0]['id'], 'event_type': 'MANUAL_ENTRY',
                'description': f"Lead criado manualmente ({source}). Nota: {note}", 'created_at': now
            }).execute()
            return True
        except Exception as e:
            logger.error(f"Manual lead error: {e}")
            return False

    def log_interaction(self, deal_id, contact_id, type, description):
        try:
            now = datetime.utcnow().isoformat()
            self.client.table('timeline_events').insert({
                'contact_id': contact_id, 'deal_id': deal_id, 'event_type': type,
                'description': description, 'created_at': now
            }).execute()
            self.client.table('deals').update({'last_activity_at': now}).eq('id', deal_id).execute()
            return True
        except Exception: return False

    # ========================================================================
    # 4. RELATÓRIOS DE MARKETING
    # ========================================================================

    def get_marketing_performance(self) -> List[Dict[str, Any]]:
        """Retorna dados para o relatório de atribuição."""
        try:
            sources = self.client.table('tracking_sources').select('*').execute().data
            if not sources: return []
            
            performance = []
            for s in sources:
                calls = self.client.table('calls').select('call_sid', count='exact').eq('tracking_source_id', s['id']).execute()
                performance.append({
                    "Source": s.get('utm_source', 'Direto'),
                    "Campaign": s.get('utm_campaign', '-'),
                    "Medium": s.get('utm_medium', '-'),
                    "Phone": s.get('tracking_number'),
                    "Calls": calls.count or 0,
                    "Last Active": s.get('last_call_at')
                })
            return sorted(performance, key=lambda x: x['Calls'], reverse=True)
        except Exception as e:
            logger.error(f"Marketing stats error: {e}")
            return []

    def health_check(self) -> bool:
        try:
            self.client.table('calls').select('call_sid').limit(1).execute()
            return True
        except: return False

@lru_cache()
def get_database_service() -> DatabaseService:
    return DatabaseService()