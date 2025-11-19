"""
Analytics Service - Inteligência de Dados
Calcula KPIs, Funil de Vendas e Métricas de SLA.
"""
import pandas as pd
from services.database import get_database_service
from datetime import datetime, timedelta, timezone
import logging

db = get_database_service()
logger = logging.getLogger(__name__)

class AnalyticsService:
    
    def get_kpis(self, days=30):
        """Retorna métricas consolidadas para os cards do topo."""
        try:
            start_date = datetime.now(timezone.utc) - timedelta(days=days)
            str_date = start_date.isoformat()
            
            # 1. Total de Chamadas
            calls = db.client.table('calls').select('call_sid', count='exact').gte('created_at', str_date).execute()
            total_calls = calls.count or 0
            
            # 2. Total de Leads (Deals criados)
            deals = db.client.table('deals').select('id', count='exact').gte('created_at', str_date).execute()
            total_leads = deals.count or 0
            
            # 3. Agendamentos (Ganho)
            # Consideramos 'Agendado' como conversão. Precisamos buscar pelo nome do estágio ou tag
            # Aqui vamos simplificar buscando deals onde a TAG atual é 'Agendado' via log ou status
            # Para o MVP, vamos assumir que existe um estágio chamado 'Agendado'
            agendado_stage = db.client.table('pipeline_stages').select('id').ilike('name', '%Agendado%').execute()
            total_agendados = 0
            if agendado_stage.data:
                st_id = agendado_stage.data[0]['id']
                won = db.client.table('deals').select('id', count='exact').eq('stage_id', st_id).gte('created_at', str_date).execute()
                total_agendados = won.count or 0
            
            conversion_rate = (total_agendados / total_leads * 100) if total_leads > 0 else 0
            
            return {
                "total_calls": total_calls,
                "total_leads": total_leads,
                "total_agendados": total_agendados,
                "conversion_rate": conversion_rate
            }
        except Exception as e:
            logger.error(f"KPI Error: {e}")
            return {"total_calls": 0, "total_leads": 0, "total_agendados": 0, "conversion_rate": 0}

    def get_funnel_data(self, days=30):
        """Dados para o gráfico de Funil."""
        start_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        # Busca todos os deals criados no período com seus estágios
        deals = db.client.table('deals').select('stage_id, pipeline_stages(name, position)').gte('created_at', start_date.isoformat()).execute()
        
        if not deals.data: return pd.DataFrame()
        
        df = pd.DataFrame(deals.data)
        # Achatar o JSON do estágio
        df['stage_name'] = df['pipeline_stages'].apply(lambda x: x['name'] if x else 'Desconhecido')
        df['position'] = df['pipeline_stages'].apply(lambda x: x['position'] if x else 99)
        
        # Agrupar
        funnel = df.groupby(['stage_name', 'position']).size().reset_index(name='count')
        return funnel.sort_values('position')

    def get_leads_by_source(self, days=30):
        """Pizza: Origem dos Leads (Voz vs Manual vs Outros)"""
        start_date = datetime.now(timezone.utc) - timedelta(days=days)
        res = db.client.table('deals').select('source').gte('created_at', start_date.isoformat()).execute()
        
        if not res.data: return pd.DataFrame()
        return pd.DataFrame(res.data)

    def get_sla_metrics(self):
        """Analisa tempo de resposta dos leads ABERTOS"""
        # Busca deals que não estão finalizados (assumindo que Agendado/Sem Interesse são finais? 
        # Para simplificar, vamos ver SLA do Inbox)
        
        inbox_stage = db.client.table('pipeline_stages').select('id').eq('is_default', True).execute()
        if not inbox_stage.data: return {"ok": 0, "warning": 0, "critical": 0}
        
        sid = inbox_stage.data[0]['id']
        deals = db.client.table('deals').select('last_activity_at').eq('stage_id', sid).eq('status', 'OPEN').execute()
        
        if not deals.data: return {"ok": 0, "warning": 0, "critical": 0}
        
        now = datetime.now(timezone.utc)
        ok, warn, crit = 0, 0, 0
        
        for d in deals.data:
            last = pd.to_datetime(d['last_activity_at']).replace(tzinfo=timezone.utc)
            diff_min = (now - last).total_seconds() / 60
            
            if diff_min < 30: ok += 1
            elif diff_min < 120: warn += 1
            else: crit += 1
            
        return {"ok": ok, "warning": warn, "critical": crit}