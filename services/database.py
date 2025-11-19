"""
Database Service - COMPLETO (v2.8 - Fix Missing Methods)
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
        except Exception as e:
            logger.error(f"❌ Init error: {e}")

    # --- ADMIN TOOLS ---
    def get_all_organizations(self):
        """Retorna lista de todas as organizações (Para Super Admin)"""
        try:
            return self.client.table('organizations').select('id, name').execute().data
        except Exception as e:
            logger.error(f"Get orgs error: {e}")
            return []

    # --- TELEFONIA ---
    def get_destination_number(self, tracking_number: str, campaign: str = None) -> Optional[str]:
        try:
            if campaign:
                res = self.client.table('phone_routing').select('destination_number').eq('tracking_number', tracking_number).eq('is_active', True).eq('campaign', campaign).execute()
                if res.data: return res.data[0]['destination_number']
            res = self.client.table('phone_routing').select('destination_number').eq('tracking_number', tracking_number).eq('is_active', True).is_('campaign', 'null').execute()
            return res.data[0]['destination_number'] if res.data else None
        except: return None

    def get_routes(self, org_id):
        if not org_id: return []
        return self.client.table('phone_routing').select('*').eq('organization_id', org_id).order('created_at', desc=True).execute().data or []

    def add_phone_routing(self, tracking, dest, org_id, campaign=None):
        data = {'tracking_number': tracking, 'destination_number': dest, 'campaign': campaign, 'organization_id': org_id, 'is_active': True}
        return self.client.table('phone_routing').insert(data).execute()

    # --- TRACKING ---
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
            clean = {k: v for k, v in data.items() if v is not None}
            clean['created_at'] = datetime.utcnow().isoformat()
            return self.client.table('tracking_sources').insert(clean).execute().data[0]
        except: return None

    def get_marketing_performance(self, org_id) -> List[Dict[str, Any]]:
        if not org_id: return []
        try:
            sources = self.client.table('tracking_sources').select('*').eq('organization_id', org_id).execute().data
            if not sources: return []
            perf = []
            for s in sources:
                calls = self.client.table('calls').select('call_sid', count='exact').eq('tracking_source_id', s['id']).execute()
                perf.append({
                    "Source": s.get('utm_source', 'Direto'), "Campaign": s.get('utm_campaign', '-'),
                    "Phone": s.get('tracking_number'), "Calls": calls.count or 0
                })
            return sorted(perf, key=lambda x: x['Calls'], reverse=True)
        except: return []

    # --- CALLS ---
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
        val = tag if tag and tag != "Limpar" else None
        self.client.table('calls').update({'tags': val}).eq('call_sid', call_sid).execute()
        return True

    # --- CRM ---
    def update_deal_stage(self, deal_id: str, new_stage_id: str) -> bool:
        self.client.table('deals').update({'stage_id': new_stage_id, 'last_activity_at': datetime.utcnow().isoformat()}).eq('id', deal_id).execute()
        return True

    def get_contact_timeline(self, contact_id: str) -> List[Dict[str, Any]]:
        return self.client.table('timeline_events').select('*').eq('contact_id', contact_id).order('created_at', desc=True).execute().data or []

    def create_manual_lead(self, name, phone, source, org_id, note=None):
        if not org_id: return False
        try:
            now = datetime.utcnow().isoformat()
            c_res = self.client.table('contacts').select('id').eq('phone_number', phone).eq('organization_id', org_id).execute()
            if c_res.data: cid = c_res.data[0]['id']
            else:
                cid = self.client.table('contacts').insert({'phone_number': phone, 'name': name, 'organization_id': org_id, 'created_at': now}).execute().data[0]['id']
            
            # Busca estágio padrão
            s_res = self.client.table('pipeline_stages').select('id').eq('is_default', True).limit(1).execute()
            sid = s_res.data[0]['id'] if s_res.data else None
            
            did = self.client.table('deals').insert({'contact_id': cid, 'stage_id': sid, 'title': f"Manual: {name}", 'status': 'OPEN', 'source': source, 'organization_id': org_id, 'last_activity_at': now}).execute().data[0]['id']
            self.client.table('timeline_events').insert({'contact_id': cid, 'deal_id': did, 'event_type': 'MANUAL', 'description': f"Criado: {source}. {note}", 'created_at': now}).execute()
            return True
        except Exception as e:
            logger.error(f"Manual lead error: {e}")
            return False

    def log_interaction(self, deal_id, contact_id, type, description):
        now = datetime.utcnow().isoformat()
        self.client.table('timeline_events').insert({'contact_id': contact_id, 'deal_id': deal_id, 'event_type': type, 'description': description, 'created_at': now}).execute()
        self.client.table('deals').update({'last_activity_at': now}).eq('id', deal_id).execute()
        return True

    def health_check(self) -> bool:
        try: self.client.table('calls').select('call_sid').limit(1).execute(); return True
        except: return False

@lru_cache()
def get_database_service() -> DatabaseService: return DatabaseService()