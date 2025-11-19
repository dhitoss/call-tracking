"""
Database Service - v3.7 (Multi-Tenancy Routing Fix)
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
        if not url: return
        self.client = create_client(url, key)

    # --- ROTEAMENTO INTELIGENTE (CRUCIAL PARA O FIX) ---
    def get_routing_info(self, tracking_number: str) -> Dict[str, Any]:
        """Retorna dados da rota incluindo o ID da Organização dona do número."""
        try:
            res = self.client.table('phone_routing').select('destination_number, organization_id, campaign')\
                .eq('tracking_number', tracking_number)\
                .eq('is_active', True)\
                .execute()
            return res.data[0] if res.data else None
        except Exception as e:
            logger.error(f"Routing info error: {e}")
            return None

    # --- ADMIN ---
    def get_all_organizations(self):
        return self.client.table('organizations').select('id, name').execute().data or []

    def update_organization_name(self, org_id, new_name):
        try:
            self.client.table('organizations').update({'name': new_name}).eq('id', org_id).execute()
            return True
        except: return False

    def create_organization(self, name):
        try: return self.client.table('organizations').insert({'name': name}).execute()
        except: return None

    # --- GESTÃO DE ROTAS ---
    def get_routes(self, org_id):
        if not org_id: return []
        return self.client.table('phone_routing').select('*').eq('organization_id', org_id).order('created_at', desc=True).execute().data or []

    def add_phone_routing(self, t, d, org_id, c=None):
        return self.client.table('phone_routing').insert({'tracking_number': t, 'destination_number': d, 'campaign': c, 'organization_id': org_id, 'is_active': True}).execute()
    
    def get_destination_number(self, tracking_number, campaign=None):
        # Mantido para retrocompatibilidade, mas o webhook usará get_routing_info
        try:
            q = self.client.table('phone_routing').select('destination_number').eq('tracking_number', tracking_number).eq('is_active', True)
            if campaign:
                res = q.eq('campaign', campaign).execute()
                if res.data: return res.data[0]['destination_number']
            res = self.client.table('phone_routing').select('destination_number').eq('tracking_number', tracking_number).eq('is_active', True).is_('campaign', 'null').execute()
            return res.data[0]['destination_number'] if res.data else None
        except: return None

    # --- CRM ---
    def get_contact_timeline(self, cid):
        return self.client.table('timeline_events').select('*').eq('contact_id', cid).order('created_at', desc=True).execute().data or []

    def create_manual_lead(self, name, phone, source, org_id, note=None):
        if not org_id: return False
        try:
            now = datetime.utcnow().isoformat()
            c = self.client.table('contacts').select('id').eq('phone_number', phone).eq('organization_id', org_id).execute()
            cid = c.data[0]['id'] if c.data else self.client.table('contacts').insert({'phone_number': phone, 'name': name, 'organization_id': org_id, 'created_at': now, 'is_manual': True, 'contact_preference': 'whatsapp'}).execute().data[0]['id']
            
            s = self.client.table('pipeline_stages').select('id').eq('is_default', True).limit(1).execute()
            sid = s.data[0]['id'] if s.data else None
            
            did = self.client.table('deals').insert({'contact_id': cid, 'stage_id': sid, 'title': f"Manual: {name}", 'status': 'OPEN', 'source': source, 'organization_id': org_id, 'last_activity_at': now}).execute().data[0]['id']
            self.client.table('timeline_events').insert({'contact_id': cid, 'deal_id': did, 'event_type': 'MANUAL_ENTRY', 'description': f"Criado: {source}. {note}", 'created_at': now}).execute()
            return True
        except Exception as e:
            logger.error(f"Manual lead: {e}")
            return False

    def update_contact_details(self, contact_id, new_data, user_email) -> bool:
        try:
            old = self.client.table('contacts').select('*').eq('id', contact_id).single().execute().data
            if not old: return False
            changes = []
            payload = {}
            for f in ['name', 'email', 'contact_preference']:
                if new_data.get(f) != old.get(f): payload[f] = new_data[f]; changes.append(f"{f}: {old.get(f)}->{new_data[f]}")
            
            np = new_data.get('phone_number')
            if np and np != old.get('phone_number'):
                if old.get('is_manual'): payload['phone_number'] = np; changes.append(f"Tel alterado")
            
            if payload:
                self.client.table('contacts').update(payload).eq('id', contact_id).execute()
                desc = f"Alterado por {user_email}: " + ", ".join(changes)
                self.client.table('timeline_events').insert({'contact_id': contact_id, 'event_type': 'SYSTEM_CHANGE', 'description': desc, 'created_by': user_email, 'created_at': datetime.utcnow().isoformat()}).execute()
            return True
        except Exception as e:
            logger.error(f"Upd contact: {e}"); return False

    def log_interaction(self, did, cid, type, desc):
        now = datetime.utcnow().isoformat()
        self.client.table('timeline_events').insert({'contact_id': cid, 'deal_id': did, 'event_type': type, 'description': desc, 'created_at': now}).execute()
        self.client.table('deals').update({'last_activity_at': now}).eq('id', did).execute()
        return True

    def update_deal_stage(self, did, sid):
        self.client.table('deals').update({'stage_id': sid, 'last_activity_at': datetime.utcnow().isoformat()}).eq('id', did).execute()
        return True

    # --- CALLS ---
    def insert_call(self, data):
        clean = {k: v for k, v in data.items() if v is not None}
        return self.client.table('calls').insert(clean).execute()

    def update_call_tag(self, sid, tag):
        val = tag if tag and tag != "Limpar" else None
        self.client.table('calls').update({'tags': val}).eq('call_sid', sid).execute()
        return True

    def update_call_status(self, sid, status, dur=0):
        d = {'status': status, 'updated_at': datetime.utcnow().isoformat()}
        if dur > 0: d['duration'] = dur
        self.client.table('calls').update(d).eq('call_sid', sid).execute()

    def update_call_recording(self, sid, url, rsid, dur):
        self.client.table('calls').update({'recording_url': url, 'recording_sid': rsid, 'recording_duration': dur}).eq('call_sid', sid).execute()

    def get_marketing_performance(self, org_id):
        if not org_id: return []
        try:
            srcs = self.client.table('tracking_sources').select('*').eq('organization_id', org_id).execute().data
            if not srcs: return []
            perf = []
            for s in srcs:
                c = self.client.table('calls').select('call_sid', count='exact').eq('tracking_source_id', s['id']).execute()
                perf.append({"Source": s.get('utm_source'), "Campaign": s.get('utm_campaign'), "Phone": s.get('tracking_number'), "Calls": c.count or 0})
            return sorted(perf, key=lambda x: x['Calls'], reverse=True)
        except: return []

    def get_or_create_tracking_source(self, data):
        try:
            q = self.client.table('tracking_sources').select('*').eq('tracking_number', data.get('tracking_number'))
            if data.get('gclid'): q = q.eq('gclid', data.get('gclid'))
            elif data.get('utm_campaign'): q = q.eq('utm_campaign', data.get('utm_campaign'))
            res = q.limit(1).execute()
            if res.data:
                self.client.table('tracking_sources').update({'last_call_at': datetime.utcnow().isoformat()}).eq('id', res.data[0]['id']).execute()
                return res.data[0]
            clean = {k: v for k, v in data.items() if v is not None}
            clean['created_at'] = datetime.utcnow().isoformat()
            return self.client.table('tracking_sources').insert(clean).execute().data[0]
        except: return None

    def health_check(self) -> bool:
        try: self.client.table('calls').select('call_sid').limit(1).execute(); return True
        except: return False

@lru_cache()
def get_database_service() -> DatabaseService: return DatabaseService()