"""
Analytics Service - Multi-Tenant
"""
import pandas as pd
from services.database import get_database_service
from datetime import datetime, timedelta, timezone
import logging

db = get_database_service()
logger = logging.getLogger(__name__)

class AnalyticsService:
    
    def get_kpis(self, org_id, days=30):
        """Métricas filtradas pela organização"""
        try:
            start_date = datetime.now(timezone.utc) - timedelta(days=days)
            str_date = start_date.isoformat()
            
            # Note o .eq('organization_id', org_id) em TODAS as queries
            calls = db.client.table('calls').select('call_sid', count='exact').eq('organization_id', org_id).gte('created_at', str_date).execute()
            deals = db.client.table('deals').select('id', count='exact').eq('organization_id', org_id).gte('created_at', str_date).execute()
            
            # Agendados (Adapte conforme o nome real do seu estágio de ganho)
            total_agendados = 0
            # Simplificação: busca deals ganhos ou em estágio avançado
            # Idealmente, buscar o ID do estágio "Agendado" específico desta organização
            
            total_calls = calls.count or 0
            total_leads = deals.count or 0
            conversion_rate = (total_agendados / total_leads * 100) if total_leads > 0 else 0
            
            return {
                "total_calls": total_calls,
                "total_leads": total_leads,
                "total_agendados": total_agendados, # Placeholder
                "conversion_rate": conversion_rate
            }
        except Exception as e:
            logger.error(f"KPI Error: {e}")
            return {"total_calls": 0, "total_leads": 0, "total_agendados": 0, "conversion_rate": 0}

    def get_funnel_data(self, org_id, days=30):
        start = datetime.now(timezone.utc) - timedelta(days=days)
        deals = db.client.table('deals').select('stage_id, pipeline_stages(name, position)')\
            .eq('organization_id', org_id)\
            .gte('created_at', start.isoformat()).execute()
        
        if not deals.data: return pd.DataFrame()
        
        df = pd.DataFrame(deals.data)
        df['stage_name'] = df['pipeline_stages'].apply(lambda x: x['name'] if x else 'Unknown')
        df['position'] = df['pipeline_stages'].apply(lambda x: x['position'] if x else 99)
        
        return df.groupby(['stage_name', 'position']).size().reset_index(name='count').sort_values('position')

    def get_sla_metrics(self, org_id):
        # Busca Inbox desta organização
        # Nota: Pipeline Stages geralmente são globais ou por org. Vamos assumir globais por enquanto ou filtrar se tiver org_id
        inbox = db.client.table('pipeline_stages').select('id').eq('is_default', True).execute()
        if not inbox.data: return {"ok": 0, "warning": 0, "critical": 0}
        
        sid = inbox.data[0]['id']
        deals = db.client.table('deals').select('last_activity_at')\
            .eq('organization_id', org_id)\
            .eq('stage_id', sid).eq('status', 'OPEN').execute()
        
        if not deals.data: return {"ok": 0, "warning": 0, "critical": 0}
        
        now = datetime.now(timezone.utc)
        ok, warn, crit = 0, 0, 0
        for d in deals.data:
            last = pd.to_datetime(d['last_activity_at']).replace(tzinfo=timezone.utc)
            diff = (now - last).total_seconds() / 60
            if diff < 30: ok += 1
            elif diff < 120: warn += 1
            else: crit += 1
        return {"ok": ok, "warning": warn, "critical": crit}