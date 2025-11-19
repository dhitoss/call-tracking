"""
Call Tracking Dashboard v2.0
Dashboard profissional com gerenciamento completo
"""

import streamlit as st
import pandas as pd
from supabase import create_client, Client
import os
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
from urllib.parse import urlencode

# Configuração de Tags e Cores
TAG_OPTIONS = [
    "Agendado", "Reagendado", "Cancelado", 
    "Retornar ligação", "Enviar info", 
    "Sem vaga", "Não Agendou", "Ligação errada"
]

TAG_COLORS = {
    "Agendado": "#28a745",          # Verde
    "Reagendado": "#17a2b8",        # Azul Claro
    "Cancelado": "#dc3545",         # Vermelho
    "Retornar ligação": "#ffc107",  # Amarelo
    "Enviar info": "#6c757d",       # Cinza
    "Sem vaga": "#343a40",          # Cinza Escuro
    "Não Agendou": "#fd7e14",       # Laranja
    "Ligação errada": "#000000"     # Preto
}

# ============================================================================
# CONFIGURAÇÃO
# ============================================================================

st.set_page_config(
    page_title="Call Tracking Dashboard",
    page_icon="📞",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS customizado
st.markdown("""
<style>
    .metric-card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        border-left: 4px solid #1f77b4;
    }
    .success-box {
        background-color: #d4edda;
        padding: 10px;
        border-radius: 5px;
        border-left: 4px solid #28a745;
    }
    .error-box {
        background-color: #f8d7da;
        padding: 10px;
        border-radius: 5px;
        border-left: 4px solid #dc3545;
    }
    .warning-box {
        background-color: #fff3cd;
        padding: 10px;
        border-radius: 5px;
        border-left: 4px solid #ffc107;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 10px 20px;
    }
</style>
""", unsafe_allow_html=True)

# Supabase
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("Configuração ausente: SUPABASE_URL e SUPABASE_KEY devem estar definidos nas variáveis de ambiente")
    st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ============================================================================
# FUNÇÕES AUXILIARES
# ============================================================================

@st.cache_data(ttl=60)
def get_calls(days=30, status=None, campaign=None):
    """Busca chamadas com cache"""
    start_date = datetime.now() - timedelta(days=days)
    query = supabase.table('calls').select('*').gte('created_at', start_date.isoformat())
    
    if status and status != "Todos":
        query = query.eq('status', status)
    
    if campaign:
        query = query.eq('campaign', campaign)
    
    result = query.order('created_at', desc=True).execute()
    df = pd.DataFrame(result.data) if result.data else pd.DataFrame()
    
    # Garantir que colunas essenciais existam
    if len(df) > 0:
        if 'campaign' not in df.columns:
            df['campaign'] = None
        if 'destination_number' not in df.columns:
            df['destination_number'] = None
        if 'recording_url' not in df.columns:
            df['recording_url'] = None
        if 'duration' not in df.columns:
            df['duration'] = 0
        if 'tags' not in df.columns:
            df['tags'] = None
    
    return df

@st.cache_data(ttl=60)
def get_routes():
    """Busca rotas com cache"""
    result = supabase.table('phone_routing').select('*').order('created_at', desc=True).execute()
    return result.data if result.data else []

@st.cache_data(ttl=60)
def get_tracking_sources():
    """Busca tracking sources com cache"""
    result = supabase.table('tracking_sources').select('*').execute()
    return pd.DataFrame(result.data) if result.data else pd.DataFrame()

def update_call_tag(call_sid, tag):
    """Atualiza tag no banco de dados"""
    try:
        val = tag if tag and tag != "Limpar" else None
        supabase.table('calls').update({
            'tags': val,
            'updated_at': datetime.utcnow().isoformat()
        }).eq('call_sid', call_sid).execute()
        return True
    except Exception as e:
        print(f"Erro ao atualizar tag: {e}")
        return False

def format_phone_br(phone):
    """Formata número brasileiro"""
    if not phone:
        return ""
    if phone.startswith('+55'):
        clean = phone[3:]
        if len(clean) == 11:
            return f"({clean[:2]}) {clean[2:7]}-{clean[7:]}"
        elif len(clean) == 10:
            return f"({clean[:2]}) {clean[2:6]}-{clean[6:]}"
    return phone

def format_duration(seconds):
    """Formata duração em segundos para MM:SS"""
    if not seconds or seconds == 0:
        return "00:00"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes:02d}:{secs:02d}"

def clear_cache():
    """Limpa cache do Streamlit"""
    st.cache_data.clear()

# ============================================================================
# SIDEBAR
# ============================================================================

st.sidebar.title("Call Tracking Dashboard")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navegação",
    [
        "Dashboard Geral",
        "Gerenciar Rotas",
        "Chamadas",
        "Gravações",
        "Analytics Avançado",
        "Tracking UTM",
        "Configurações"
    ]
)

st.sidebar.markdown("---")
if st.sidebar.button("Atualizar Dados", use_container_width=True):
    clear_cache()
    st.rerun()

st.sidebar.caption("v2.0.0 | Call Tracking System")

# ============================================================================
# PÁGINA: DASHBOARD GERAL
# ============================================================================

if page == "Dashboard Geral":
    st.title("Dashboard Geral")
    st.markdown("Visão consolidada do sistema de call tracking")
    
    # Filtros
    col1, col2, col3 = st.columns(3)
    with col1:
        period = st.selectbox("Período", [1, 7, 30, 90, 365], index=2, key="dash_period")
    with col2:
        auto_refresh = st.checkbox("Auto-refresh (60s)", value=False)
    
    if auto_refresh:
        import time
        time.sleep(60)
        st.rerun()
    
    # Buscar dados
    df = get_calls(days=period)
    
    if len(df) > 0:
        # Métricas principais
        st.subheader("Métricas Principais")
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("Total de Chamadas", len(df))
        
        with col2:
            completed = len(df[df['status'] == 'completed'])
            conversion_rate = (completed / len(df) * 100) if len(df) > 0 else 0
            st.metric("Completadas", completed, f"{conversion_rate:.1f}%")
        
        with col3:
            recorded = len(df[df['recording_url'].notna()])
            st.metric("Gravadas", recorded)
        
        with col4:
            if 'duration' in df.columns and df['duration'].notna().any():
                avg_duration = df[df['duration'] > 0]['duration'].mean()
                st.metric("Duração Média", format_duration(avg_duration) if not pd.isna(avg_duration) else "00:00")
            else:
                st.metric("Duração Média", "00:00")
        
        with col5:
            unique_callers = df['from_number'].nunique()
            st.metric("Callers Únicos", unique_callers)
        
        # Gráficos principais
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Chamadas por Dia")
            df['date'] = pd.to_datetime(df['created_at'], format='ISO8601').dt.date
            daily = df.groupby('date').size().reset_index(name='calls')
            fig = px.area(daily, x='date', y='calls', markers=True)
            fig.update_layout(showlegend=False, height=300)
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            st.subheader("Status das Chamadas")
            status_counts = df['status'].value_counts()
            fig = px.pie(values=status_counts.values, names=status_counts.index, hole=0.4)
            fig.update_layout(showlegend=True, height=300)
            st.plotly_chart(fig, use_container_width=True)
        
        # Campanhas
        if 'campaign' in df.columns and df['campaign'].notna().any():
            st.subheader("Performance por Campanha")
            campaign_df = df[df['campaign'].notna()].copy()
            
            if len(campaign_df) > 0:
                campaign_stats = campaign_df.groupby('campaign').agg({
                    'call_sid': 'count',
                    'status': lambda x: (x == 'completed').sum(),
                    'duration': 'mean'
                }).reset_index()
                
                campaign_stats.columns = ['Campanha', 'Total', 'Completadas', 'Duração Média']
                campaign_stats['Taxa de Conversão'] = (campaign_stats['Completadas'] / campaign_stats['Total'] * 100).round(1)
                campaign_stats['Duração Média'] = campaign_stats['Duração Média'].apply(lambda x: format_duration(x) if not pd.isna(x) else "00:00")
                
                st.dataframe(
                    campaign_stats.sort_values('Total', ascending=False),
                    use_container_width=True,
                    hide_index=True
                )
        
        # Últimas chamadas
        st.subheader("Últimas Chamadas (10 mais recentes)")
        
        # Selecionar apenas colunas que existem
        available_cols = ['created_at', 'from_number', 'to_number', 'status', 'duration']
        if 'campaign' in df.columns:
            available_cols.append('campaign')
        
        recent_df = df.head(10)[available_cols].copy()
        recent_df['created_at'] = pd.to_datetime(recent_df['created_at'], format='ISO8601').dt.strftime('%d/%m/%Y %H:%M')
        recent_df['duration'] = recent_df['duration'].apply(format_duration)
        
        # Renomear colunas
        col_names = ['Data/Hora', 'Origem', 'Destino', 'Status', 'Duração']
        if 'campaign' in df.columns:
            col_names.append('Campanha')
        
        recent_df.columns = col_names
        st.dataframe(recent_df, use_container_width=True, hide_index=True)
        
    else:
        st.info("Nenhuma chamada registrada no período selecionado")

# ============================================================================
# PÁGINA: GERENCIAR ROTAS
# ============================================================================

elif page == "Gerenciar Rotas":
    st.title("Gerenciamento de Rotas")
    st.markdown("Configure números rastreados e seus destinos")
    
    tab1, tab2, tab3 = st.tabs(["Rotas Ativas", "Adicionar Rota", "Importar em Lote"])
    
    # TAB 1: Listar rotas
    with tab1:
        routes = get_routes()
        
        # Filtros
        col1, col2 = st.columns(2)
        with col1:
            filter_status = st.selectbox("Filtrar por Status", ["Todos", "Ativo", "Inativo"])
        with col2:
            filter_campaign = st.text_input("Filtrar por Campanha", "")
        
        # Aplicar filtros
        filtered_routes = routes
        if filter_status != "Todos":
            filtered_routes = [r for r in filtered_routes if r['is_active'] == (filter_status == "Ativo")]
        if filter_campaign:
            filtered_routes = [r for r in filtered_routes if filter_campaign.lower() in str(r.get('campaign', '')).lower()]
        
        if filtered_routes:
            st.write(f"**Total de rotas:** {len(filtered_routes)}")
            
            # Tabela de rotas
            for i, route in enumerate(filtered_routes):
                with st.container():
                    col1, col2, col3, col4, col5, col6 = st.columns([2, 2, 2, 1, 1, 1])
                    
                    with col1:
                        st.text(f"Rastreado\n{route['tracking_number']}")
                    
                    with col2:
                        st.text(f"Destino\n{route['destination_number']}")
                    
                    with col3:
                        campaign_text = route['campaign'] if route['campaign'] else "Genérica"
                        st.text(f"Campanha\n{campaign_text}")
                    
                    with col4:
                        status = "Ativo" if route['is_active'] else "Inativo"
                        color = "🟢" if route['is_active'] else "🔴"
                        st.text(f"Status\n{color} {status}")
                    
                    with col5:
                        # Botão ativar/desativar
                        if route['is_active']:
                            if st.button("Desativar", key=f"deact_{route['id']}", use_container_width=True):
                                supabase.table('phone_routing').update({'is_active': False}).eq('id', route['id']).execute()
                                clear_cache()
                                st.success("Rota desativada")
                        else:
                            if st.button("Ativar", key=f"act_{route['id']}", use_container_width=True):
                                supabase.table('phone_routing').update({'is_active': True}).eq('id', route['id']).execute()
                                clear_cache()
                                st.success("Rota ativada")
                    
                    with col6:
                        if st.button("Deletar", key=f"del_{route['id']}", use_container_width=True):
                            supabase.table('phone_routing').delete().eq('id', route['id']).execute()
                            clear_cache()
                            st.success("Rota deletada")
                    
                    st.divider()
        else:
            st.info("Nenhuma rota encontrada com os filtros aplicados")
    
    # TAB 2: Adicionar rota
    with tab2:
        st.subheader("Adicionar Nova Rota")
        
        with st.form("add_route_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                tracking_number = st.text_input(
                    "Número Rastreado (Twilio)",
                    placeholder="+5511999990000",
                    help="Número que receberá as chamadas"
                )
                
                campaign = st.text_input(
                    "Campanha",
                    placeholder="google_ads",
                    help="Deixe vazio para rota genérica (fallback)"
                )
            
            with col2:
                destination_number = st.text_input(
                    "Número de Destino",
                    placeholder="+5511888880000",
                    help="Número para onde redirecionar"
                )
                
                is_active = st.checkbox("Ativar imediatamente", value=True)
            
            submitted = st.form_submit_button("Adicionar Rota", use_container_width=True)
            
            if submitted:
                errors = []
                
                if not tracking_number:
                    errors.append("Número rastreado é obrigatório")
                elif not tracking_number.startswith('+'):
                    errors.append("Número rastreado deve começar com +")
                
                if not destination_number:
                    errors.append("Número de destino é obrigatório")
                elif not destination_number.startswith('+'):
                    errors.append("Número de destino deve começar com +")
                
                if errors:
                    for error in errors:
                        st.error(error)
                else:
                    data = {
                        'tracking_number': tracking_number,
                        'destination_number': destination_number,
                        'campaign': campaign if campaign else None,
                        'is_active': is_active
                    }
                    
                    try:
                        supabase.table('phone_routing').insert(data).execute()
                        clear_cache()
                        st.success("Rota adicionada com sucesso!")
                        st.info("Atualize a página para ver a nova rota")
                    except Exception as e:
                        st.error(f"Erro ao adicionar rota: {str(e)}")
    
    # TAB 3: Importar em lote
    with tab3:
        st.subheader("Importar Rotas em Lote")
        st.markdown("Upload de arquivo CSV com as rotas")
        
        st.markdown("""
        **Formato do CSV:**
        ```
        tracking_number,destination_number,campaign,is_active
        +5511999990000,+5511888880000,google_ads,true
        +5511999990001,+5511888880000,meta_ads,true
        +5511999990002,+5511888880000,,true
        ```
        """)
        
        uploaded_file = st.file_uploader("Selecione o arquivo CSV", type=['csv'])
        
        if uploaded_file:
            try:
                import_df = pd.read_csv(uploaded_file)
                
                st.write("**Preview dos dados:**")
                st.dataframe(import_df.head(), use_container_width=True)
                
                if st.button("Importar Rotas", use_container_width=True):
                    success_count = 0
                    error_count = 0
                    
                    for _, row in import_df.iterrows():
                        try:
                            data = {
                                'tracking_number': row['tracking_number'],
                                'destination_number': row['destination_number'],
                                'campaign': row['campaign'] if pd.notna(row['campaign']) else None,
                                'is_active': bool(row.get('is_active', True))
                            }
                            supabase.table('phone_routing').insert(data).execute()
                            success_count += 1
                        except Exception as e:
                            error_count += 1
                            st.error(f"Erro na linha {_}: {str(e)}")
                    
                    clear_cache()
                    st.success(f"Importação concluída: {success_count} sucesso, {error_count} erros")
                    
            except Exception as e:
                st.error(f"Erro ao ler arquivo: {str(e)}")

# ============================================================================
# PÁGINA: CHAMADAS (ATUALIZADA COM EDITOR DE TAGS)
# ============================================================================

elif page == "Chamadas":
    st.title("Histórico de Chamadas")
    st.markdown("Visualize e analise todas as chamadas recebidas")
    
    # Filtros avançados
    st.subheader("Filtros")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        period = st.selectbox("Período", [1, 7, 30, 90, 365], index=2, key="calls_period")
    
    with col2:
        status_filter = st.selectbox("Status", ["Todos", "completed", "busy", "no-answer", "failed", "canceled"])
    
    with col3:
        campaign_filter = st.text_input("Campanha", "")
    
    with col4:
        search_number = st.text_input("Buscar Número", "")
    
    # Buscar chamadas
    df = get_calls(days=period, status=status_filter, campaign=campaign_filter if campaign_filter else None)
    
    # Aplicar filtro de número
    if search_number and len(df) > 0:
        df = df[
            df['from_number'].str.contains(search_number, case=False, na=False) |
            df['to_number'].str.contains(search_number, case=False, na=False)
        ]
    
    if len(df) > 0:
        # Métricas rápidas
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total", len(df))
        with col2:
            completed = len(df[df['status'] == 'completed'])
            st.metric("Completadas", completed)
        with col3:
            with_recording = len(df[df['recording_url'].notna()])
            st.metric("Com Gravação", with_recording)
        with col4:
            if 'duration' in df.columns:
                total_duration = df['duration'].sum()
                st.metric("Tempo Total", format_duration(total_duration))
            else:
                st.metric("Tempo Total", "00:00")
        
        st.divider()
        
        # Preparar DataFrame para exibição
        display_df = df.copy()
        display_df['created_at'] = pd.to_datetime(display_df['created_at']).dt.strftime('%d/%m/%Y %H:%M')
        display_df['duration'] = display_df['duration'].apply(format_duration)
        
        if 'tags' not in display_df.columns:
            display_df['tags'] = None

        st.subheader("Lista de Chamadas")
        st.caption("Dica: Você pode editar a coluna 'Tag' diretamente na tabela abaixo.")

        # Tabela Editável
        edited_df = st.data_editor(
            display_df[['created_at', 'from_number', 'to_number', 'status', 'duration', 'campaign', 'tags', 'call_sid']],
            column_config={
                "tags": st.column_config.SelectboxColumn(
                    "Tag (Classificação)",
                    help="Selecione a classificação da chamada",
                    width="medium",
                    options=TAG_OPTIONS,
                    required=False
                ),
                "call_sid": None, # Ocultar
                "created_at": "Data",
                "from_number": "De",
                "to_number": "Para",
                "status": "Status",
                "duration": "Duração",
                "campaign": "Campanha"
            },
            hide_index=True,
            use_container_width=True,
            key="calls_editor"
        )

        # Lógica de salvamento da tabela
        if len(edited_df) == len(display_df):
            diffs = edited_df['tags'] != display_df['tags']
            if diffs.any():
                changed_rows = edited_df[diffs]
                for index, row in changed_rows.iterrows():
                    new_tag = row['tags']
                    sid = row['call_sid']
                    update_call_tag(sid, new_tag)
                    st.toast(f"Tag atualizada: {new_tag}")
                
                # Limpa cache para atualizar na próxima interação
                clear_cache()
        
        # Exportar
        st.subheader("Exportar Dados")
        col1, col2 = st.columns(2)
        
        with col1:
            csv = df.to_csv(index=False)
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name=f"chamadas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        with col2:
            json_str = df.to_json(orient='records', date_format='iso')
            st.download_button(
                label="Download JSON",
                data=json_str,
                file_name=f"chamadas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
                use_container_width=True
            )
    
    else:
        st.info("Nenhuma chamada encontrada com os filtros selecionados")

# ============================================================================
# PÁGINA: GRAVAÇÕES (ATUALIZADA COM CORES E SELETOR)
# ============================================================================

elif page == "Gravações":
    st.title("Gravações de Chamadas")
    st.markdown("Ouça e gerencie as gravações das chamadas")
    
    # Filtros
    col1, col2 = st.columns(2)
    with col1:
        period = st.selectbox("Período", [7, 30, 90], index=1, key="rec_period")
    with col2:
        min_duration = st.number_input("Duração Mínima (segundos)", min_value=0, value=0)
    
    # Buscar chamadas com gravação
    start_date = datetime.now() - timedelta(days=period)
    result = supabase.table('calls').select('*').not_.is_('recording_url', 'null').gte('created_at', start_date.isoformat()).order('created_at', desc=True).execute()
    
    if result.data:
        recordings_df = pd.DataFrame(result.data)
        
        # Filtrar por duração
        if min_duration > 0:
            recordings_df = recordings_df[recordings_df['recording_duration'] >= min_duration]
        
        st.metric("Total de Gravações", len(recordings_df))
        
        # Listar gravações
        for idx, call in recordings_df.iterrows():
            # Proteção
            dest = call.get('destination_number') or 'N/A'
            camp = call.get('campaign') or 'N/A'
            dur = format_duration(call.get('recording_duration', 0))
            current_tag = call.get('tags')
            
            # Header visual
            header_emoji = "⬜"
            if current_tag in TAG_COLORS:
                header_emoji = "🏷️"

            header_text = f"{header_emoji} {call['created_at'][:10]} | {call['from_number']} "
            if current_tag:
                header_text += f"[{current_tag}]"

            with st.expander(header_text, expanded=False):
                col1, col2, col3 = st.columns([2, 1, 1])
                
                with col1:
                    st.markdown(f"**Origem:** `{call['from_number']}`")
                    st.markdown(f"**Destino:** `{call['to_number']}` → `{dest}`")
                    st.text(f"Data: {call['created_at']}")
                    st.text(f"Status: {call['status']}")
                
                with col2:
                    if call.get('recording_url'):
                        st.audio(call['recording_url'])
                        st.link_button("Abrir no Twilio", call['recording_url'], use_container_width=True)

                with col3:
                    # Seletor de Tag
                    st.markdown("### Classificação")
                    
                    # Índice atual
                    tag_index = None
                    if current_tag in TAG_OPTIONS:
                        tag_index = TAG_OPTIONS.index(current_tag)
                    
                    selected_tag = st.selectbox(
                        "Definir Tag",
                        ["Limpar"] + TAG_OPTIONS,
                        index=tag_index + 1 if tag_index is not None else 0,
                        key=f"tag_{call['call_sid']}",
                        label_visibility="collapsed"
                    )
                    
                    # Lógica Update
                    new_val = selected_tag if selected_tag != "Limpar" else None
                    if new_val != current_tag:
                        if update_call_tag(call['call_sid'], new_val):
                            st.success("Salvo!")
                            clear_cache()
                            import time
                            time.sleep(0.5)
                            st.rerun()

                    # Badge colorido
                    if current_tag and current_tag in TAG_COLORS:
                        cor = TAG_COLORS[current_tag]
                        st.markdown(
                            f'<div style="background-color: {cor}; color: white; padding: 5px 10px; border-radius: 5px; text-align: center; font-weight: bold;">{current_tag}</div>', 
                            unsafe_allow_html=True
                        )

# ============================================================================
# PÁGINA: ANALYTICS AVANÇADO
# ============================================================================

elif page == "Analytics Avançado":
    st.title("Analytics Avançado")
    st.markdown("Análise detalhada do desempenho")
    
    # Período
    period = st.selectbox("Período", [7, 30, 90, 365], index=2)
    
    df = get_calls(days=period)
    
    if len(df) > 0:
        
        # Performance por hora do dia
        st.subheader("Chamadas por Hora do Dia")
        df['hour'] = pd.to_datetime(df['created_at'], format='ISO8601').dt.hour
        hourly = df.groupby('hour').size().reset_index(name='calls')
        
        fig = px.bar(hourly, x='hour', y='calls')
        fig.update_xaxes(title='Hora do Dia', dtick=1)
        fig.update_yaxes(title='Número de Chamadas')
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
        
        # Performance por dia da semana
        st.subheader("Chamadas por Dia da Semana")
        df['weekday'] = pd.to_datetime(df['created_at'], format='ISO8601').dt.day_name()
        weekday_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        weekday_pt = {'Monday': 'Segunda', 'Tuesday': 'Terça', 'Wednesday': 'Quarta', 
                      'Thursday': 'Quinta', 'Friday': 'Sexta', 'Saturday': 'Sábado', 'Sunday': 'Domingo'}
        
        weekday_counts = df['weekday'].value_counts().reindex(weekday_order, fill_value=0)
        weekday_df = pd.DataFrame({
            'day': [weekday_pt[d] for d in weekday_counts.index],
            'calls': weekday_counts.values
        })
        
        fig = px.bar(weekday_df, x='day', y='calls')
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
        
        # Top números que mais ligaram
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Top 10 Números Origem")
            top_from = df['from_number'].value_counts().head(10).reset_index()
            top_from.columns = ['Número', 'Chamadas']
            st.dataframe(top_from, use_container_width=True, hide_index=True)
        
        with col2:
            st.subheader("Top 10 Números Destino")
            top_to = df['to_number'].value_counts().head(10).reset_index()
            top_to.columns = ['Número', 'Chamadas']
            st.dataframe(top_to, use_container_width=True, hide_index=True)
        
        # Análise de duração
        st.subheader("Distribuição de Duração das Chamadas")
        duration_df = df[df['duration'] > 0].copy()
        
        if len(duration_df) > 0:
            fig = px.histogram(duration_df, x='duration', nbins=30)
            fig.update_xaxes(title='Duração (segundos)')
            fig.update_yaxes(title='Número de Chamadas')
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Duração Mínima", format_duration(duration_df['duration'].min()))
            with col2:
                st.metric("Duração Média", format_duration(duration_df['duration'].mean()))
            with col3:
                st.metric("Duração Máxima", format_duration(duration_df['duration'].max()))
    
    else:
        st.info("Sem dados suficientes para analytics no período selecionado")

# ============================================================================
# PÁGINA: TRACKING UTM
# ============================================================================

elif page == "Tracking UTM":
    st.title("Tracking UTM/GCLID")
    st.markdown("Análise de origens de tráfego")
    
    # Buscar tracking sources
    sources_df = get_tracking_sources()
    calls_df = get_calls(days=90)
    
    if len(sources_df) > 0 and len(calls_df) > 0:
        
        # Merge com calls
        merged = calls_df.merge(
            sources_df,
            left_on='tracking_source_id',
            right_on='id',
            how='left',
            suffixes=('_call', '_source')
        )
        
        # Estatísticas por fonte
        st.subheader("Performance por Fonte UTM")
        
        source_stats = merged.groupby('utm_source').agg({
            'call_sid': 'count',
            'status': lambda x: (x == 'completed').sum(),
            'duration': 'mean',
            'recording_url': lambda x: x.notna().sum()
        }).reset_index()
        
        source_stats.columns = ['Fonte', 'Total Chamadas', 'Completadas', 'Duração Média', 'Gravações']
        source_stats['Taxa Conversão'] = (source_stats['Completadas'] / source_stats['Total Chamadas'] * 100).round(1)
        source_stats['Duração Média'] = source_stats['Duração Média'].apply(lambda x: format_duration(x) if not pd.isna(x) else "00:00")
        
        st.dataframe(
            source_stats.sort_values('Total Chamadas', ascending=False),
            use_container_width=True,
            hide_index=True
        )
        
        # Gráfico de fontes
        fig = px.bar(
            source_stats.sort_values('Total Chamadas', ascending=False).head(10),
            x='Fonte',
            y='Total Chamadas'
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # Por campanha
        st.subheader("Performance por Campanha UTM")
        
        campaign_stats = merged.groupby('utm_campaign').agg({
            'call_sid': 'count',
            'status': lambda x: (x == 'completed').sum(),
            'duration': 'mean'
        }).reset_index()
        
        campaign_stats.columns = ['Campanha', 'Total Chamadas', 'Completadas', 'Duração Média']
        campaign_stats['Taxa Conversão'] = (campaign_stats['Completadas'] / campaign_stats['Total Chamadas'] * 100).round(1)
        campaign_stats['Duração Média'] = campaign_stats['Duração Média'].apply(lambda x: format_duration(x) if not pd.isna(x) else "00:00")
        
        st.dataframe(
            campaign_stats.sort_values('Total Chamadas', ascending=False),
            use_container_width=True,
            hide_index=True
        )
        
        # GCLID tracking
        st.subheader("Google Ads (GCLID)")
        gclid_df = sources_df[sources_df['gclid'].notna()]
        
        if len(gclid_df) > 0:
            st.metric("Total de Clicks Únicos (GCLID)", len(gclid_df))
            
            # Chamadas por GCLID
            gclid_calls = merged[merged['gclid'].notna()].groupby('gclid').agg({
                'call_sid': 'count',
                'status': lambda x: (x == 'completed').sum()
            }).reset_index()
            
            gclid_calls.columns = ['GCLID', 'Chamadas', 'Completadas']
            st.dataframe(gclid_calls.head(20), use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum tracking GCLID registrado ainda")
    
    else:
        st.info("Nenhum dado de tracking UTM disponível ainda")

# ============================================================================
# PÁGINA: CONFIGURAÇÕES
# ============================================================================

elif page == "Configurações":
    st.title("Configurações do Sistema")
    
    st.subheader("Informações de Conexão")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.text_input("Supabase URL", SUPABASE_URL, disabled=True)
    
    with col2:
        st.text_input("Supabase Key", "***" + SUPABASE_KEY[-4:] if SUPABASE_KEY else "", disabled=True)
    
    st.divider()
    
    st.subheader("Webhook URL")
    webhook_url = "https://call-tracking-production.up.railway.app/webhook/call"
    st.code(webhook_url)
    
    st.markdown("**Configuração no Twilio:**")
    st.markdown(f"""
    1. Acesse: https://console.twilio.com/
    2. Phone Numbers → Manage → Active numbers
    3. Configure o webhook para: `{webhook_url}?campaign=sua_campanha`
    """)
    
    st.divider()
    
    st.subheader("API Endpoints")
    
    endpoints = {
        "Health Check": "/health",
        "Webhook Principal": "/webhook/call",
        "Callback Gravação": "/webhook/recording",
        "Status Chamada": "/webhook/call-status",
        "Listar Rotas": "/api/routing",
        "Criar Rota": "/api/routing (POST)",
        "Tracking Sources": "/api/tracking/sources",
        "Analytics": "/api/analytics/summary"
    }
    
    for name, endpoint in endpoints.items():
        st.text(f"{name}: {endpoint}")
    
    st.divider()
    
    st.subheader("Diagnóstico")
    
    if st.button("Testar Conexão com Banco"):
        try:
            result = supabase.table('calls').select('*').limit(1).execute()
            st.success("Conexão com banco OK")
        except Exception as e:
            st.error(f"Erro na conexão: {str(e)}")
    
    if st.button("Limpar Cache"):
        clear_cache()
        st.success("Cache limpo com sucesso")
        st.rerun()
    
    st.divider()
    
    st.subheader("Sobre")
    st.markdown("""
    **Call Tracking System v2.0**
    
    Sistema completo de rastreamento de chamadas com:
    - Number Masking (redirecionamento dinâmico)
    - Gravação automática
    - Tracking UTM/GCLID
    - Analytics em tempo real
    
    Desenvolvido com Flask, Streamlit, Twilio e Supabase.
    """)