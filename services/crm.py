"""
CRM Service - Lógica de Negócio (Multi-Tenancy)
"""
import logging
from datetime import datetime
from services.database import get_database_service

logger = logging.getLogger(__name__)
db = get_database_service()

class CRMService:
    
    def handle_incoming_call_event(self, call_data):
        try:
            phone = call_data['from_number']
            org_id = call_data.get('organization_id')
            
            if not org_id:
                logger.warning(f"Skipping CRM for {phone}: No Organization ID")
                return

            # 1. Contato (Scoped by Org)
            contact = self._get_or_create_contact(phone, org_id)
            
            # 2. Deal (Scoped by Org)
            self._upsert_deal_from_call(contact['id'], call_data, org_id)
            
            logger.info(f"✅ CRM Processed for {phone} @ Org {org_id}")
            
        except Exception as e:
            logger.error(f"❌ CRM Failed: {e}", exc_info=True)

    def _get_or_create_contact(self, phone, org_id):
        # Busca considerando ORG
        res = db.client.table('contacts').select('*').eq('phone_number', phone).eq('organization_id', org_id).execute()
        if res.data:
            return res.data[0]
        
        # Cria Novo
        new_contact = {
            'phone_number': phone,
            'name': f"Lead {phone[-4:]}",
            'organization_id': org_id,
            'created_at': datetime.utcnow().isoformat(),
            'last_activity_at': datetime.utcnow().isoformat()
        }
        res = db.client.table('contacts').insert(new_contact).execute()
        return res.data[0]

    def _upsert_deal_from_call(self, contact_id, call_data, org_id):
        # Busca deal aberto
        existing_deal = db.client.table('deals')\
            .select('*')\
            .eq('contact_id', contact_id)\
            .eq('organization_id', org_id)\
            .eq('status', 'OPEN')\
            .execute()
            
        now = datetime.utcnow().isoformat()
        default_stage_id = self._get_default_stage_id()

        if existing_deal.data:
            # RESSURREIÇÃO: Volta pro Inbox
            deal_id = existing_deal.data[0]['id']
            old_stage = existing_deal.data[0]['stage_id']
            
            update_data = {'last_activity_at': now, 'stage_id': default_stage_id}
            db.client.table('deals').update(update_data).eq('id', deal_id).execute()
            
            if old_stage != default_stage_id:
                self._add_timeline_event(contact_id, deal_id, "SYSTEM", "Movido para Inbox (Nova Interação)", {}, org_id)
            
            self._add_timeline_event(contact_id, deal_id, "CALL_INBOUND", "Nova chamada recebida", call_data, org_id)
            
        else:
            # Novo Deal
            new_deal = {
                'contact_id': contact_id,
                'stage_id': default_stage_id,
                'title': f"Ligação de {call_data['from_number']}",
                'status': 'OPEN',
                'source': 'voice',
                'organization_id': org_id,
                'last_activity_at': now
            }
            res = db.client.table('deals').insert(new_deal).execute()
            deal_id = res.data[0]['id']
            
            self._add_timeline_event(contact_id, deal_id, "CALL_INBOUND", "Lead criado via telefone", call_data, org_id)

    def _get_default_stage_id(self):
        # Idealmente filtraria por org se stages fossem customizados por cliente
        # Por enquanto assume stages globais
        res = db.client.table('pipeline_stages').select('id').eq('is_default', True).limit(1).execute()
        if res.data: return res.data[0]['id']
        res = db.client.table('pipeline_stages').select('id').limit(1).execute()
        return res.data[0]['id'] if res.data else None

    def _add_timeline_event(self, contact_id, deal_id, event_type, desc, metadata, org_id=None):
        # Timeline não tem org_id explícito na tabela atual, mas herda do contact.
        # Mantemos simples.
        event = {
            'contact_id': contact_id,
            'deal_id': deal_id,
            'event_type': event_type,
            'description': desc,
            'metadata': metadata,
            'created_at': datetime.utcnow().isoformat()
        }
        db.client.table('timeline_events').insert(event).execute()