"""
Funções auxiliares e utilitárias para o dashboard.
"""
from datetime import datetime, timedelta, date
from typing import Tuple, List
from io import StringIO
import streamlit as st
import pandas as pd


def get_default_date_range() -> Tuple[date, date]:
    """
    Retorna range de data padrão (últimos 30 dias).
    
    Returns:
        Tupla (start_date, end_date)
    """
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    return start_date, end_date


def get_current_and_previous_month() -> Tuple[Tuple[int, int], Tuple[int, int]]:
    """
    Retorna (ano, mês) do mês atual e anterior.
    
    Returns:
        ((ano_atual, mes_atual), (ano_anterior, mes_anterior))
    """
    today = date.today()
    current_month = (today.year, today.month)
    
    # Mês anterior
    if today.month == 1:
        previous_month = (today.year - 1, 12)
    else:
        previous_month = (today.year, today.month - 1)
    
    return current_month, previous_month


def get_month_name(month: int) -> str:
    """
    Retorna nome do mês em português.
    
    Args:
        month: Número do mês (1-12)
        
    Returns:
        Nome do mês
    """
    months = {
        1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
        5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
        9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
    }
    return months.get(month, '')


def format_percentage(value: float, decimals: int = 2) -> str:
    """
    Formata número como percentual.
    
    Args:
        value: Valor numérico
        decimals: Casas decimais
        
    Returns:
        String formatada (ex: "75.5%")
    """
    return f"{value:.{decimals}f}%"


def get_status_color(status: str) -> str:
    """
    Retorna cor baseada no status da chamada.
    
    Args:
        status: Status da chamada
        
    Returns:
        Código de cor hex
    """
    color_map = {
        'completed': '#10b981',  # verde
        'no-answer': '#f59e0b',  # laranja
        'busy': '#f59e0b',       # laranja
        'failed': '#ef4444',     # vermelho
        'ringing': '#3b82f6',    # azul
        'in-progress': '#3b82f6' # azul
    }
    return color_map.get(status, '#6b7280')  # cinza default


def get_status_label(status: str) -> str:
    """
    Retorna label em português para status.
    
    Args:
        status: Status da chamada
        
    Returns:
        Label traduzido
    """
    label_map = {
        'completed': 'Atendida',
        'no-answer': 'Não Atendida',
        'busy': 'Ocupado',
        'failed': 'Falhou',
        'ringing': 'Tocando',
        'in-progress': 'Em Andamento',
        'canceled': 'Cancelada'
    }
    return label_map.get(status, status.title())


def apply_custom_css():
    """Aplica CSS customizado ao dashboard Streamlit."""
    st.markdown("""
        <style>
        /* Remover padding extra */
        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
            max-width: 1400px;
        }
        
        /* Estilizar métricas */
        [data-testid="stMetricValue"] {
            font-size: 2rem;
            font-weight: 600;
            color: #1e293b;
        }
        
        [data-testid="stMetricLabel"] {
            font-size: 0.9rem;
            color: #64748b;
            font-weight: 500;
        }
        
        /* Cards de métricas */
        [data-testid="metric-container"] {
            background-color: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 1rem;
            box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1);
        }
        
        /* Títulos */
        h1 {
            color: #1e293b;
            font-weight: 700;
            margin-bottom: 0.5rem;
        }
        
        h2 {
            color: #334155;
            font-weight: 600;
            margin-top: 2rem;
            margin-bottom: 1rem;
        }
        
        h3 {
            color: #475569;
            font-weight: 600;
        }
        
        /* Sidebar */
        [data-testid="stSidebar"] {
            background-color: #f8fafc;
            border-right: 1px solid #e2e8f0;
        }
        
        [data-testid="stSidebar"] h1 {
            font-size: 1.5rem;
            color: #1e293b;
        }
        
        [data-testid="stSidebar"] h2 {
            font-size: 1.1rem;
            color: #475569;
            margin-top: 1.5rem;
        }
        
        /* Botões */
        .stButton > button {
            border-radius: 6px;
            font-weight: 500;
            transition: all 0.2s;
        }
        
        .stButton > button:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }
        
        /* Dividers */
        hr {
            margin: 2rem 0;
            border: none;
            border-top: 1px solid #e2e8f0;
        }
        
        /* Plotly charts */
        .js-plotly-plot {
            border-radius: 8px;
            border: 1px solid #e2e8f0;
            padding: 0.5rem;
            background-color: white;
        }
        
        /* Data tables */
        [data-testid="stDataFrame"] {
            border: 1px solid #e2e8f0;
            border-radius: 8px;
        }
        
        /* Expanders */
        [data-testid="stExpander"] {
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            background-color: white;
        }
        
        /* Selectbox e Multiselect */
        [data-baseweb="select"] {
            border-radius: 6px;
        }
        
        /* Date inputs */
        [data-testid="stDateInput"] {
            border-radius: 6px;
        }
        
        /* Loading spinner */
        .stSpinner > div {
            border-top-color: #3b82f6 !important;
        }
        
        /* Info/Warning/Error boxes */
        .stAlert {
            border-radius: 8px;
            border-left-width: 4px;
        }
        </style>
    """, unsafe_allow_html=True)


def initialize_session_state():
    """Inicializa variáveis de session state."""
    if 'date_range' not in st.session_state:
        st.session_state.date_range = get_default_date_range()
    
    if 'selected_campaigns' not in st.session_state:
        st.session_state.selected_campaigns = []
    
    if 'selected_statuses' not in st.session_state:
        st.session_state.selected_statuses = []
    
    if 'last_refresh' not in st.session_state:
        st.session_state.last_refresh = datetime.now()


def create_download_button(df: pd.DataFrame, filename: str = "calls_data.csv"):
    """
    Cria botão para download de dados em CSV.
    
    Args:
        df: DataFrame para exportar
        filename: Nome do arquivo
    """
    if df.empty:
        return
    
    # Converter para CSV
    csv_buffer = StringIO()
    df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
    csv_data = csv_buffer.getvalue()
    
    st.download_button(
        label="📥 Exportar Dados (CSV)",
        data=csv_data,
        file_name=filename,
        mime="text/csv",
        use_container_width=True
    )


def display_data_table(df: pd.DataFrame, title: str = "Dados Detalhados"):
    """
    Exibe tabela de dados com opções de filtro.
    
    Args:
        df: DataFrame a exibir
        title: Título da seção
    """
    with st.expander(f"📋 {title}", expanded=False):
        if df.empty:
            st.info("Nenhum dado para exibir")
            return
        
        # Formatar colunas
        df_display = df.copy()
        
        # Formatar timestamps
        if 'created_at' in df_display.columns:
            df_display['created_at'] = pd.to_datetime(
                df_display['created_at']
            ).dt.strftime('%d/%m/%Y %H:%M')
        
        # Traduzir status
        if 'status' in df_display.columns:
            status_map = {
                'completed': 'Atendida',
                'no-answer': 'Não Atendida',
                'busy': 'Ocupado',
                'failed': 'Falhou',
                'ringing': 'Tocando',
                'in-progress': 'Em Andamento'
            }
            df_display['status'] = df_display['status'].map(
                lambda x: status_map.get(x, x)
            )
        
        # Renomear colunas para português
        column_names = {
            'call_sid': 'ID Chamada',
            'from_number': 'Número Origem',
            'to_number': 'Número Destino',
            'status': 'Status',
            'duration': 'Duração (s)',
            'campaign_id': 'Campanha',
            'created_at': 'Data/Hora'
        }
        
        df_display = df_display.rename(columns=column_names)
        
        # Selecionar apenas colunas relevantes
        display_columns = [
            col for col in ['Data/Hora', 'Número Origem', 'Número Destino', 
                           'Status', 'Duração (s)', 'Campanha']
            if col in df_display.columns
        ]
        
        # Exibir tabela
        st.dataframe(
            df_display[display_columns],
            use_container_width=True,
            height=400
        )
        
        # Estatísticas rápidas
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total de Registros", len(df_display))
        with col2:
            if 'Duração (s)' in df_display.columns:
                avg_duration = df_display['Duração (s)'].mean()
                st.metric("Duração Média", f"{avg_duration:.0f}s")
        with col3:
            if 'Status' in df_display.columns:
                most_common = df_display['Status'].mode()[0] if not df_display.empty else "N/A"
                st.metric("Status Mais Comum", most_common)
        
        # Botão de download
        st.markdown("---")
        create_download_button(df, filename=f"calls_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")