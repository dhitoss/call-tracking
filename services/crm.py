"""
Serviço de CRM - Lógica de Negócio
Gerencia a criação automática de Cards e Contatos baseada nas chamadas.
"""
import logging
from datetime import datetime
from services.database import get_database_service

logger = logging.getLogger(__name__)
db = get_database_service()

class CRMService:
    
    def handle_incoming_call_event(self, call_data):
        """
        Executado toda vez que uma chamada é finalizada.
        1. Cria/Busca Contato
        2. Cria/Atualiza Deal (Card)
        3. Registra na Timeline
        """
        try:
            phone = call_data['from_number']
            
            # 1. BUSCAR OU CRIAR CONTATO (Pessoa)
            contact = self._get_or_create_contact(phone)
            
            # 2. GERENCIAR O DEAL (Card)
            # A regra é: Se ligou, o card vai pro topo (LIFO).
            # Se já tem card aberto, atualiza a data. Se não, cria novo no Inbox.
            self._upsert_deal_from_call(contact['id'], call_data)
            
            logger.info(f"✅ CRM Updated for {phone}")
            
        except Exception as e:
            # IMPORTANTE: Loga o erro mas não quebra a aplicação principal
            logger.error(f"❌ CRM Update Failed: {e}", exc_info=True)

    def _get_or_create_contact(self, phone):
        # Verifica se já existe
        res = db.client.table('contacts').select('*').eq('phone_number', phone).execute()
        if res.data:
            return res.data[0]
        
        # Cria novo
        new_contact = {
            'phone_number': phone,
            'name': f"Lead {phone[-4:]}", # Ex: Lead 8899
            'created_at': datetime.utcnow().isoformat(),
            'last_activity_at': datetime.utcnow().isoformat()
        }
        res = db.client.table('contacts').insert(new_contact).execute()
        return res.data[0]

    def _upsert_deal_from_call(self, contact_id, call_data):
        # Busca se já existe um deal ABERTO para este contato
        existing_deal = db.client.table('deals')\
            .select('*')\
            .eq('contact_id', contact_id)\
            .eq('status', 'OPEN')\
            .execute()
            
        now = datetime.utcnow().isoformat()
        
        if existing_deal.data:
            # CENÁRIO: Já tem negócio aberto.
            # Ação: Traz para o topo (atualiza last_activity_at) e move para Inbox se quiser chamar atenção
            deal_id = existing_deal.data[0]['id']
            
            # Opcional: Se quiser que SEMPRE volte pro Inbox ao ligar, descomente a linha abaixo:
            # default_stage = self._get_default_stage_id()
            
            db.client.table('deals').update({
                'last_activity_at': now,
                # 'stage_id': default_stage # Força volta pro inicio? (Decisão de negócio)
            }).eq('id', deal_id).execute()
            
            self._add_timeline_event(contact_id, deal_id, "CALL_INBOUND", "Cliente ligou novamente", call_data)
            
        else:
            # CENÁRIO: Novo negócio (ou retomada de contato antigo fechado)
            default_stage_id = self._get_default_stage_id()
            
            new_deal = {
                'contact_id': contact_id,
                'stage_id': default_stage_id,
                'title': f"Ligação de {call_data['from_number']}",
                'status': 'OPEN',
                'source': 'voice',
                'last_activity_at': now
            }
            res = db.client.table('deals').insert(new_deal).execute()
            deal_id = res.data[0]['id']
            
            self._add_timeline_event(contact_id, deal_id, "CALL_INBOUND", "Nova chamada recebida (Lead Criado)", call_data)

    def _get_default_stage_id(self):
        # Busca o ID da coluna "Inbox" (is_default = true)
        res = db.client.table('pipeline_stages').select('id').eq('is_default', True).limit(1).execute()
        if res.data:
            return res.data[0]['id']
        # Fallback (pega o primeiro que achar)
        res = db.client.table('pipeline_stages').select('id').limit(1).execute()
        return res.data[0]['id'] if res.data else None

    def _add_timeline_event(self, contact_id, deal_id, event_type, desc, metadata):
        event = {
            'contact_id': contact_id,
            'deal_id': deal_id,
            'event_type': event_type,
            'description': desc,
            'metadata': metadata,
            'created_at': datetime.utcnow().isoformat()
        }
        db.client.table('timeline_events').insert(event).execute()