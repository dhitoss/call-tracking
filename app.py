"""
Call Tracking Dashboard v2.0
Dashboard profissional com gerenciamento completo (CRM + AI + Tracking)
"""

import streamlit as st
import pandas as pd
from supabase import create_client, Client
import os
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
from urllib.parse import urlencode
import time

# --- IMPORTS DOS SERVIÇOS ---
from services.database import get_database_service
from services.ai_service import AIService

# Inicialização dos Serviços
db_service = get_database_service()
ai_service = AIService()

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
    /* Estilo para badges de Tag */
    .tag-badge {
        padding: 4px 8px;
        border-radius: 4px;
        color: white;
        font-weight: bold;
        font-size: 0.85em;
        display: inline-block;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 10px 20px;
    }
</style>
""", unsafe_allow_html=True)

# Supabase (Cliente Direto para compatibilidade com código legado)
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("Configuração ausente: SUPABASE_URL e SUPABASE_KEY devem estar definidos")
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
    
    # Garantir colunas
    expected_cols = ['campaign', 'destination_number', 'recording_url', 'duration', 'tags', 'call_sid']
    if len(df) > 0:
        for col in expected_cols:
            if col not in df.columns:
                df[col] = None
            
            # Garantir numérico para duração
            if col == 'duration':
                df[col] = df[col].fillna(0)
                
    return df

@st.cache_data(ttl=60)
def get_routes():
    result = supabase.table('phone_routing').select('*').order('created_at', desc=True).execute()
    return result.data if result.data else []

@st.cache_data(ttl=60)
def get_tracking_sources():
    result = supabase.table('tracking_sources').select('*').execute()
    return pd.DataFrame(result.data) if result.data else pd.DataFrame()

def format_duration(seconds):
    if not seconds or seconds == 0:
        return "00:00"
    try:
        seconds = int(float(seconds))
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes:02d}:{secs:02d}"
    except:
        return "00:00"

def clear_cache():
    st.cache_data.clear()

# ============================================================================
# SIDEBAR
# ============================================================================

st.sidebar.title("Call Tracking")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navegação",
    [
        "Dashboard Geral",
        "CRM (Pipeline)",
        "Chamadas",
        "Gravações",
        "Gerenciar Rotas",
        "Analytics Avançado",
        "Tracking UTM",
        "Configurações"
    ]
)

st.sidebar.markdown("---")
if st.sidebar.button("Atualizar Dados", use_container_width=True):
    clear_cache()
    st.rerun()

# ============================================================================
# PÁGINA: DASHBOARD GERAL
# ============================================================================

if page == "Dashboard Geral":
    st.title("Dashboard Geral")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        period = st.selectbox("Período", [1, 7, 30, 90, 365], index=2, key="dash_period")
    with col2:
        auto_refresh = st.checkbox("Auto-refresh (60s)", value=False)
    
    if auto_refresh:
        time.sleep(60)
        st.rerun()
    
    df = get_calls(days=period)
    
    if len(df) > 0:
        # Métricas
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1: st.metric("Total", len(df))
        with col2:
            completed = len(df[df['status'] == 'completed'])
            rate = (completed/len(df)*100)
            st.metric("Completadas", completed, f"{rate:.1f}%")
        with col3: st.metric("Gravadas", len(df[df['recording_url'].notna()]))
        with col4: st.metric("Duração Média", format_duration(df['duration'].mean()))
        with col5: st.metric("Callers Únicos", df['from_number'].nunique())
        
        # Gráficos
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Evolução Diária")
            # Fix Data
            df['date'] = pd.to_datetime(df['created_at'], format='mixed').dt.date
            daily = df.groupby('date').size().reset_index(name='calls')
            st.plotly_chart(px.area(daily, x='date', y='calls'), use_container_width=True)
        
        with col2:
            st.subheader("Status")
            st.plotly_chart(px.pie(df, names='status'), use_container_width=True)

        # Últimas
        st.subheader("Últimas Chamadas")
        recent = df.head(10).copy()
        recent['created_at'] = pd.to_datetime(recent['created_at'], format='mixed').dt.strftime('%d/%m %H:%M')
        recent['duration'] = recent['duration'].apply(format_duration)
        st.dataframe(recent[['created_at', 'from_number', 'status', 'duration', 'tags']], use_container_width=True, hide_index=True)
        
    else:
        st.info("Sem dados no período.")

# ============================================================================
# PÁGINA: CRM / KANBAN
# ============================================================================

elif page == "CRM (Pipeline)":
    st.title("Pipeline de Atendimento")
    
    # 1. Carregar Dados
    stages = supabase.table('pipeline_stages').select('*').order('position').execute().data
    deals = supabase.table('deals').select('*, contacts(phone_number, name, lead_score)').eq('status', 'OPEN').order('last_activity_at', desc=True).execute().data
    
    # Mapeamentos
    stage_names = [s['name'] for s in stages]
    stage_map = {s['name']: s['id'] for s in stages}

    # --- MODAL DE DETALHES ---
    @st.dialog("Histórico do Lead", width="large")
    def show_lead_details(deal, contact_id):
        contact = deal['contacts']
        phone = contact['phone_number']
        st.subheader(f"{contact.get('name', 'Lead')} | {phone}")
        
        tab_timeline, tab_ai = st.tabs(["⏳ Linha do Tempo", "🤖 IA Intelligence"])
        
        # ABA TIMELINE
        with tab_timeline:
            timeline = db_service.get_contact_timeline(contact_id)
            if not timeline:
                st.info("Nenhum histórico.")
            
            for event in timeline:
                icon = "🔹"
                if event['event_type'] == 'CALL_INBOUND': icon = "📞"
                elif event['event_type'] == 'TAG_CHANGE': icon = "🏷️"
                
                dt = pd.to_datetime(event['created_at']).strftime('%d/%m %H:%M')
                
                with st.chat_message("user" if event['event_type']=='NOTE' else "assistant", avatar=icon):
                    st.write(f"**{dt}** - {event['description']}")
                    meta = event.get('metadata')
                    if meta and isinstance(meta, dict):
                        if meta.get('recording_url'):
                            st.audio(meta['recording_url'])
                        if meta.get('new_tag'):
                            cor = TAG_COLORS.get(meta['new_tag'], "#333")
                            st.markdown(f":background[{cor}] :color[white] **{meta['new_tag']}**")

        # ABA IA
        with tab_ai:
            st.caption("Análise automática de atendimento clínico.")
            
            # Buscar gravação mais recente deste número
            calls_res = supabase.table('calls')\
                .select('*')\
                .or_(f"from_number.eq.{phone},to_number.eq.{phone}")\
                .not_.is_('recording_url', 'null')\
                .order('created_at', desc=True)\
                .limit(1)\
                .execute()
                
            if not calls_res.data:
                st.warning("Nenhuma gravação disponível para análise.")
            else:
                call_data = calls_res.data[0]
                sid = call_data['call_sid']
                
                # Verificar análise existente
                analysis_res = supabase.table('ai_analysis').select('*').eq('call_sid', sid).execute()
                
                if analysis_res.data:
                    data = analysis_res.data[0]
                    
                    s_color = "green" if data['sentiment'] == 'Positive' else "red" if data['sentiment'] == 'Negative' else "gray"
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"### Sentimento: :{s_color}[{data['sentiment']}]")
                    with col2:
                        st.markdown("**Classificação IA:**")
                        for t in (data['tags'] or []):
                            st.markdown(f"`{t}`")
                    
                    st.divider()
                    st.info(f"**Resumo:** {data['summary']}")
                    with st.expander("Transcrição Completa"):
                        st.text(data['transcription'])
                else:
                    st.info(f"Chamada de: {pd.to_datetime(call_data['created_at']).strftime('%d/%m %H:%M')}")
                    st.audio(call_data['recording_url'])
                    
                    if st.button("✨ Gerar Análise Clínica", use_container_width=True):
                        with st.spinner("IA analisando..."):
                            if ai_service.process_call(sid, call_data['recording_url']):
                                st.success("Concluído!")
                                st.rerun()
                            else:
                                st.error("Erro na análise. Verifique chave OpenAI.")

    # --- KANBAN ---
    cols = st.columns(len(stages))
    
    for i, stage in enumerate(stages):
        with cols[i]:
            # Header
            count = len([d for d in deals if d['stage_id'] == stage['id']])
            b_color = stage.get('color', '#ccc')
            st.markdown(
                f"<div style='border-top: 3px solid {b_color}; padding: 5px 0;'><b>{stage['name']}</b> <small>({count})</small></div>", 
                unsafe_allow_html=True
            )
            
            # Cards
            stage_deals = [d for d in deals if d['stage_id'] == stage['id']]
            for deal in stage_deals:
                contact = deal['contacts']
                phone = contact['phone_number']
                
                with st.container(border=True):
                    st.markdown(f"**{phone}**")
                    
                    # Tempo (Fix UTC Error)
                    last_act = pd.to_datetime(deal['last_activity_at'], format='mixed')
                    if last_act.tzinfo: last_act = last_act.tz_localize(None)
                    
                    is_recent = (datetime.utcnow() - last_act).total_seconds() < 3600
                    time_emoji = "🔥" if is_recent else "🕒"
                    st.caption(f"{time_emoji} {last_act.strftime('%H:%M %d/%m')}")
                    
                    # Mover
                    current_name = stage['name']
                    try: idx = stage_names.index(current_name)
                    except: idx = 0
                    
                    new_stage = st.selectbox("Fase", stage_names, index=idx, key=f"mv_{deal['id']}", label_visibility="collapsed")
                    
                    if new_stage != current_name:
                        db_service.update_deal_stage(deal['id'], stage_map[new_stage])
                        st.toast(f"Movido para {new_stage}")
                        time.sleep(0.5)
                        st.rerun()
                        
                    if st.button("Abrir", key=f"btn_{deal['id']}", use_container_width=True):
                        show_lead_details(deal, contact['id'])

# ============================================================================
# PÁGINA: CHAMADAS (COM EDITOR CORRIGIDO)
# ============================================================================

elif page == "Chamadas":
    st.title("Histórico de Chamadas")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1: period = st.selectbox("Período", [1, 7, 30, 90], index=2, key="cp")
    with col2: status = st.selectbox("Status", ["Todos", "completed", "missed"])
    with col3: camp = st.text_input("Campanha")
    with col4: search = st.text_input("Busca")
    
    df = get_calls(days=period, status=status, campaign=camp if camp else None)
    
    if search and not df.empty:
        df = df[df['from_number'].astype(str).str.contains(search) | df['to_number'].astype(str).str.contains(search)]
    
    if not df.empty:
        display_df = df.copy()
        display_df['created_at'] = pd.to_datetime(display_df['created_at'], format='mixed').dt.strftime('%d/%m/%Y %H:%M')
        display_df['duration'] = display_df['duration'].apply(format_duration)
        if 'tags' not in display_df.columns: display_df['tags'] = None

        st.subheader("Lista Editável")
        st.caption("Edite a Tag diretamente na tabela.")
        
        edited_df = st.data_editor(
            display_df[['created_at', 'from_number', 'to_number', 'status', 'duration', 'tags', 'call_sid']],
            column_config={
                "tags": st.column_config.SelectboxColumn("Tag", options=TAG_OPTIONS, width="medium"),
                "call_sid": None,
                "created_at": "Data",
                "from_number": "De",
                "to_number": "Para"
            },
            hide_index=True, use_container_width=True, key="call_edit"
        )
        
        # Save Logic (Fix Loop)
        if len(edited_df) == len(display_df):
            orig = display_df['tags'].fillna("").astype(str)
            new = edited_df['tags'].fillna("").astype(str)
            
            if (orig != new).any():
                for idx in (orig != new).index[orig != new]:
                    row = edited_df.loc[idx]
                    tag = row['tags'] if row['tags'] and row['tags'].strip() != "" else "Limpar"
                    db_service.update_call_tag(row['call_sid'], tag)
                    st.toast(f"Salvo: {tag}")
                
                clear_cache()
                time.sleep(0.5)
                st.rerun()
    else:
        st.info("Nenhum registro.")

# ============================================================================
# PÁGINA: GRAVAÇÕES
# ============================================================================

elif page == "Gravações":
    st.title("Gravações e Classificação")
    
    col1, col2 = st.columns(2)
    with col1: p_rec = st.selectbox("Dias", [7, 30, 60], index=1, key="prec")
    with col2: min_dur = st.number_input("Min. Segundos", 0)
    
    start = datetime.now() - timedelta(days=p_rec)
    res = supabase.table('calls').select('*').not_.is_('recording_url', 'null').gte('created_at', start.isoformat()).order('created_at', desc=True).execute()
    
    if res.data:
        recs = pd.DataFrame(res.data)
        if min_dur > 0: recs = recs[recs['recording_duration'] >= min_dur]
        
        st.metric("Total", len(recs))
        
        for _, call in recs.iterrows():
            tag = call.get('tags')
            emoji = "🏷️" if tag in TAG_COLORS else "⬜"
            
            head = f"{emoji} {pd.to_datetime(call['created_at']).strftime('%d/%m')} | {call['from_number']}"
            if tag: head += f" [{tag}]"
            
            with st.expander(head):
                c1, c2, c3 = st.columns([2,2,1])
                with c1:
                    st.write(f"**De:** {call['from_number']}")
                    st.write(f"**Para:** {call['to_number']}")
                    st.caption(f"Status: {call['status']}")
                with c2:
                    st.audio(call['recording_url'])
                with c3:
                    idx = TAG_OPTIONS.index(tag) if tag in TAG_OPTIONS else 0
                    new_tag = st.selectbox("Tag", ["Limpar"] + TAG_OPTIONS, index=idx+1 if tag in TAG_OPTIONS else 0, key=f"t_{call['call_sid']}", label_visibility="collapsed")
                    
                    val = new_tag if new_tag != "Limpar" else None
                    if val != tag:
                        db_service.update_call_tag(call['call_sid'], val)
                        st.success("Salvo!")
                        clear_cache()
                        time.sleep(0.5)
                        st.rerun()
                        
                    if tag in TAG_COLORS:
                        st.markdown(f"<span class='tag-badge' style='background:{TAG_COLORS[tag]}'>{tag}</span>", unsafe_allow_html=True)

# ============================================================================
# PÁGINA: ROTAS
# ============================================================================

elif page == "Gerenciar Rotas":
    st.title("Roteamento de Chamadas")
    
    with st.form("nova_rota"):
        c1, c2, c3 = st.columns(3)
        with c1: track = st.text_input("Número Twilio (+55...)")
        with c2: dest = st.text_input("Destino (+55...)")
        with c3: camp = st.text_input("Campanha (Opcional)")
        
        if st.form_submit_button("Salvar Rota"):
            if track and dest:
                try:
                    db_service.add_phone_routing(track, dest, camp if camp else None)
                    st.success("Rota Criada!")
                    clear_cache()
                    st.rerun()
                except Exception as e: st.error(f"Erro: {e}")
            else: st.error("Preencha os números.")
            
    routes = get_routes()
    if routes:
        st.dataframe(pd.DataFrame(routes)[['tracking_number', 'destination_number', 'campaign', 'is_active']], use_container_width=True)

# ============================================================================
# OUTRAS PÁGINAS (Analytics, UTM, Config) - Mantidas simples
# ============================================================================

elif page == "Analytics Avançado":
    st.title("Analytics")
    df = get_calls()
    if not df.empty:
        df['hour'] = pd.to_datetime(df['created_at'], format='mixed').dt.hour
        st.bar_chart(df['hour'].value_counts().sort_index())
    else: st.info("Sem dados.")

elif page == "Tracking UTM":
    st.title("Tracking")
    st.info("Em desenvolvimento: Visualização de UTM e GCLID.")

elif page == "Configurações":
    st.title("Configuração")
    st.text_input("Webhook URL", f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN', 'seu-app.railway.app')}/webhook/call", disabled=True)