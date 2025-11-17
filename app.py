"""
Dashboard principal de Call Tracking.
Interface Streamlit para visualização de métricas de chamadas.
"""
import streamlit as st
import pandas as pd
from datetime import datetime, date
import logging
from typing import List, Optional

from config import settings
from services.database import get_database_service
from services.metrics import MetricsService
from utils.helpers import (
    get_default_date_range,
    get_current_and_previous_month,
    get_month_name,
    format_percentage,
    apply_custom_css,
    initialize_session_state,
    display_data_table
)
from utils.charts import (
    create_campaign_bar_chart,
    create_state_pie_chart,
    create_top_missed_chart,
    create_top_answered_chart,
    create_timeline_chart
)
from components.summary import render_executive_summary


# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuração da página
st.set_page_config(
    page_title="Call Tracker Dashboard",
    page_icon="📞",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ==================== CACHING FUNCTIONS ====================

@st.cache_resource
def get_db_service():
    """Retorna instância cached do serviço de banco."""
    return get_database_service()


@st.cache_data(ttl=settings.CACHE_TTL)
def load_calls_data(
    start_date: date,
    end_date: date,
    campaign_ids: Optional[List[str]] = None,
    statuses: Optional[List[str]] = None
) -> pd.DataFrame:
    """
    Carrega dados de chamadas com cache de 5 minutos.
    
    Args:
        start_date: Data inicial
        end_date: Data final
        campaign_ids: IDs de campanhas para filtrar
        statuses: Status para filtrar
        
    Returns:
        DataFrame com chamadas
    """
    try:
        db = get_db_service()
        
        data = db.get_calls(
            start_date=start_date,
            end_date=end_date,
            campaign_ids=campaign_ids if campaign_ids else None,
            statuses=statuses if statuses else None,
            limit=10000
        )
        
        if not data:
            return pd.DataFrame()
        
        df = pd.DataFrame(data)
        df['created_at'] = pd.to_datetime(df['created_at'], format='ISO8601')
        
        logger.info(f"✅ Loaded {len(df)} calls from database")
        return df
        
    except Exception as e:
        logger.error(f"❌ Error loading calls: {str(e)}")
        st.error(f"Erro ao carregar dados: {str(e)}")
        return pd.DataFrame()


@st.cache_data(ttl=600)  # 10 min cache
def get_available_campaigns() -> List[str]:
    """Retorna lista de campanhas disponíveis."""
    try:
        db = get_db_service()
        campaigns = db.get_unique_campaigns()
        return campaigns
    except Exception as e:
        logger.error(f"❌ Error loading campaigns: {str(e)}")
        return []


# ==================== SIDEBAR FILTERS ====================

def render_sidebar() -> dict:
    """
    Renderiza filtros na sidebar.
    
    Returns:
        Dicionário com filtros selecionados
    """
    st.sidebar.title("📊 Filtros")
    
    # Date Range Picker
    st.sidebar.subheader("Período")
    default_start, default_end = get_default_date_range()
    
    col1, col2 = st.sidebar.columns(2)
    with col1:
        start_date = st.date_input(
            "Data Inicial",
            value=default_start,
            max_value=date.today()
        )
    with col2:
        end_date = st.date_input(
            "Data Final",
            value=default_end,
            max_value=date.today()
        )
    
    # Campanhas
    st.sidebar.subheader("Campanhas")
    available_campaigns = get_available_campaigns()
    
    if available_campaigns:
        selected_campaigns = st.sidebar.multiselect(
            "Selecione as campanhas",
            options=available_campaigns,
            default=None,
            placeholder="Todas as campanhas"
        )
    else:
        selected_campaigns = []
        st.sidebar.info("Nenhuma campanha encontrada")
    
    # Status
    st.sidebar.subheader("Status")
    all_statuses = [
        'completed', 'no-answer', 'busy', 
        'failed', 'ringing', 'in-progress'
    ]
    
    status_labels = {
        'completed': 'Atendida',
        'no-answer': 'Não Atendida',
        'busy': 'Ocupado',
        'failed': 'Falhou',
        'ringing': 'Tocando',
        'in-progress': 'Em Andamento'
    }
    
    selected_statuses = st.sidebar.multiselect(
        "Selecione os status",
        options=all_statuses,
        format_func=lambda x: status_labels.get(x, x),
        default=None,
        placeholder="Todos os status"
    )
    
    # Botão atualizar
    st.sidebar.divider()
    refresh_button = st.sidebar.button(
        "🔄 Atualizar Dados",
        use_container_width=True,
        type="primary"
    )
    
    if refresh_button:
        st.cache_data.clear()
        st.session_state.last_refresh = datetime.now()
        st.rerun()
    
    # Última atualização
    if 'last_refresh' in st.session_state:
        last_refresh = st.session_state.last_refresh
        st.sidebar.caption(
            f"Última atualização: {last_refresh.strftime('%H:%M:%S')}"
        )
    
    return {
        'start_date': start_date,
        'end_date': end_date,
        'campaigns': selected_campaigns if selected_campaigns else None,
        'statuses': selected_statuses if selected_statuses else None
    }


# ==================== METRICS CARDS ====================

def render_main_metrics(df: pd.DataFrame):
    """Renderiza cards de métricas principais."""
    metrics = MetricsService.calculate_main_metrics(df)
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric(
            label="📞 Ligações",
            value=metrics.total_calls,
            delta=None
        )
    
    with col2:
        st.metric(
            label="👥 Clientes Únicos",
            value=metrics.unique_callers,
            delta=None
        )
    
    with col3:
        avg_duration_formatted = MetricsService.format_duration(metrics.avg_duration)
        st.metric(
            label="⏱️ Média Atendimento",
            value=avg_duration_formatted,
            delta=None
        )
    
    with col4:
        # Média de espera (placeholder - será implementado quando tivermos tempo de espera)
        st.metric(
            label="⏳ Média Espera",
            value="00:00",
            delta=None,
            help="Funcionalidade em desenvolvimento"
        )
    
    with col5:
        # CallScore (placeholder - será calculado com mais dados)
        call_score = round((metrics.answer_rate / 10), 1)
        st.metric(
            label="⭐ CallScore Médio",
            value=f"{call_score}/10",
            delta=None,
            help="Score baseado em taxa de atendimento"
        )


# ==================== MONTHLY CARDS ====================

def render_monthly_cards(df: pd.DataFrame):
    """Renderiza cards comparativos de meses."""
    st.subheader("📅 Comparativo Mensal")
    
    current, previous = get_current_and_previous_month()
    current_year, current_month = current
    previous_year, previous_month = previous
    
    # Calcular estatísticas
    current_stats = MetricsService.calculate_monthly_stats(
        df, current_year, current_month
    )
    previous_stats = MetricsService.calculate_monthly_stats(
        df, previous_year, previous_month
    )
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown(f"### {get_month_name(current_month)} {current_year}")
        st.markdown(f"""
        - **{current_stats['total_calls']}** Ligações
        - **{format_percentage(current_stats['missed_rate'])}** Perdidas
        - **{format_percentage(current_stats['missed_returned_rate'])}** Perdidas Retornadas
        - **{format_percentage(current_stats['incomplete_rate'])}** Incompletas
        - **{format_percentage(current_stats['incomplete_returned_rate'])}** Incompletas Retornadas
        """)
    
    with col2:
        st.markdown(f"### {get_month_name(previous_month)} {previous_year}")
        st.markdown(f"""
        - **{previous_stats['total_calls']}** Ligações
        - **{format_percentage(previous_stats['missed_rate'])}** Perdidas
        - **{format_percentage(previous_stats['missed_returned_rate'])}** Perdidas Retornadas
        - **{format_percentage(previous_stats['incomplete_rate'])}** Incompletas
        - **{format_percentage(previous_stats['incomplete_returned_rate'])}** Incompletas Retornadas
        """)


# ==================== CHARTS SECTION ====================

def render_charts(df: pd.DataFrame):
    """Renderiza todos os gráficos do dashboard."""
    
    st.subheader("📊 Análises Visuais")
    
    # Row 1: Ligações por Campanha + Ligações por Estado
    col1, col2 = st.columns(2)
    
    with col1:
        # Gráfico 1: Ligações por Campanha
        campaign_data = MetricsService.get_calls_by_campaign(df)
        fig_campaign = create_campaign_bar_chart(campaign_data)
        st.plotly_chart(fig_campaign, use_container_width=True)
    
    with col2:
        # Gráfico 2: Ligações por Estado
        state_data = MetricsService.get_calls_by_state(df)
        fig_state = create_state_pie_chart(state_data)
        st.plotly_chart(fig_state, use_container_width=True)
    
    st.markdown("---")
    
    # Row 2: Top Missed + Top Answered
    col3, col4 = st.columns(2)
    
    with col3:
        # Gráfico 3: Campanhas com mais ligações perdidas
        top_missed = MetricsService.get_top_missed_campaigns(df, top_n=5)
        fig_missed = create_top_missed_chart(top_missed)
        st.plotly_chart(fig_missed, use_container_width=True)
    
    with col4:
        # Gráfico 4: Campanhas com mais ligações atendidas
        top_answered = MetricsService.get_top_answered_campaigns(df, top_n=5)
        fig_answered = create_top_answered_chart(top_answered)
        st.plotly_chart(fig_answered, use_container_width=True)
    
    st.markdown("---")
    
    # Row 3: Timeline + Intervalo selector
    st.subheader("📈 Evolução Temporal")
    
    # Seletor de intervalo
    col_interval, col_spacer = st.columns([1, 3])
    with col_interval:
        interval = st.selectbox(
            "Intervalo",
            options=['daily', 'hourly', 'weekly'],
            format_func=lambda x: {
                'daily': 'Diário',
                'hourly': 'Por Hora',
                'weekly': 'Semanal'
            }[x],
            index=0
        )
    
    # Gráfico 5: Timeline
    timeline_data = MetricsService.get_calls_timeline(df, interval=interval)
    fig_timeline = create_timeline_chart(timeline_data, interval=interval)
    st.plotly_chart(fig_timeline, use_container_width=True)


# ==================== MAIN APP ====================

def main():
    """Função principal do dashboard."""
    
    # Aplicar CSS customizado
    apply_custom_css()
    
    # Inicializar session state
    initialize_session_state()
    
    # Header
    st.title("📞 Call Tracker Dashboard")
    st.markdown("---")
    
    # Renderizar filtros e obter seleções
    filters = render_sidebar()
    
    # Carregar dados
    with st.spinner("Carregando dados..."):
        df = load_calls_data(
            start_date=filters['start_date'],
            end_date=filters['end_date'],
            campaign_ids=filters['campaigns'],
            statuses=filters['statuses']
        )
    
    # Verificar se há dados
    if df.empty:
        st.warning("⚠️ Nenhuma chamada encontrada para os filtros selecionados.")
        st.info("💡 Ajuste os filtros na sidebar ou verifique se há dados no período selecionado.")
        return
    
    # Resumo executivo
    render_executive_summary(df, filters)
    
    st.markdown("---")
    
    # Renderizar métricas principais
    render_main_metrics(df)
    
    st.markdown("---")
    
    # Renderizar cards mensais
    render_monthly_cards(df)
    
    st.markdown("---")
    
    # Renderizar gráficos
    render_charts(df)
    
    st.markdown("---")
    
    # Tabela de dados detalhados
    display_data_table(df, "Chamadas Detalhadas")
    
    # Footer
    st.markdown("---")
    st.caption(f"Dashboard atualizado em {datetime.now().strftime('%d/%m/%Y às %H:%M')}")


if __name__ == "__main__":
    main()