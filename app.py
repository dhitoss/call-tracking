"""
Call Tracking Dashboard v2.2
- Fix: Query complexa no Modal (AttributeError)
- Fix: Timezones (DeprecationWarning)
- Feat: CRM Interativo e IA
"""

import streamlit as st
import pandas as pd
from supabase import create_client, Client
import os
from datetime import datetime, timedelta, timezone
import plotly.express as px
import time
import pytz 

# --- IMPORTS DOS SERVIÇOS ---
from services.database import get_database_service
from services.ai_service import AIService

# Inicialização
db_service = get_database_service()
ai_service = AIService()

# --- CONFIGURAÇÃO DE FUSO HORÁRIO ---
TZ_NAME = os.getenv('DEFAULT_TIMEZONE', 'America/Sao_Paulo')
try:
    LOCAL_TZ = pytz.timezone(TZ_NAME)
except:
    LOCAL_TZ = pytz.timezone('America/Sao_Paulo')

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
# CONFIGURAÇÃO DA PÁGINA
# ============================================================================

st.set_page_config(
    page_title="Call Tracking",
    page_icon="📞",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .metric-card { background-color: #f0f2f6; padding: 20px; border-radius: 10px; border-left: 4px solid #1f77b4; }
    .tag-badge { padding: 4px 8px; border-radius: 4px; color: white; font-weight: bold; font-size: 0.85em; display: inline-block; }
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    .stTabs [data-baseweb="tab"] { padding: 10px 20px; }
</style>
""", unsafe_allow_html=True)

# Supabase
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("Configuração ausente: SUPABASE_URL/KEY")
    st.stop()
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ============================================================================
# FUNÇÕES AUXILIARES
# ============================================================================

def convert_to_local(df, col_name='created_at'):
    """Converte coluna de data do DataFrame para o fuso local"""
    if df.empty or col_name not in df.columns:
        return df
    # 1. Converte para datetime UTC (mixed para aceitar com/sem microssegundos)
    df[col_name] = pd.to_datetime(df[col_name], format='mixed', utc=True)
    # 2. Converte para o fuso local
    df[col_name] = df[col_name].dt.tz_convert(LOCAL_TZ)
    return df

def format_date_br(dt_obj):
    if pd.isna(dt_obj): return ""
    return dt_obj.strftime('%d/%m/%Y %H:%M')

@st.cache_data(ttl=60)
def get_calls(days=30, status=None, campaign=None):
    start_date = datetime.now(timezone.utc) - timedelta(days=days)
    query = supabase.table('calls').select('*').gte('created_at', start_date.isoformat())
    
    if status and status != "Todos": query = query.eq('status', status)
    if campaign: query = query.eq('campaign', campaign)
    
    result = query.order('created_at', desc=True).execute()
    df = pd.DataFrame(result.data) if result.data else pd.DataFrame()
    
    expected_cols = ['campaign', 'destination_number', 'recording_url', 'duration', 'tags', 'call_sid']
    if len(df) > 0:
        for col in expected_cols:
            if col not in df.columns: df[col] = None
            if col == 'duration': df[col] = df[col].fillna(0)
        
        # APLICA CONVERSÃO DE FUSO
        df = convert_to_local(df, 'created_at')
        
    return df

@st.cache_data(ttl=60)
def get_routes():
    result = supabase.table('phone_routing').select('*').order('created_at', desc=True).execute()
    return result.data if result.data else []

def update_call_tag(call_sid, tag):
    try:
        val = tag if tag and tag != "Limpar" else None
        supabase.table('calls').update({'tags': val, 'updated_at': datetime.utcnow().isoformat()}).eq('call_sid', call_sid).execute()
        return True
    except: return False

def format_duration(seconds):
    try:
        seconds = int(float(seconds or 0))
        return f"{int(seconds//60):02d}:{int(seconds%60):02d}"
    except: return "00:00"

def clear_cache(): st.cache_data.clear()

# ============================================================================
# SIDEBAR
# ============================================================================

st.sidebar.title("Call Tracking")
st.sidebar.markdown(f"🕒 **Fuso:** {TZ_NAME}")
st.sidebar.markdown("---")

page = st.sidebar.radio("Navegação", ["Dashboard Geral", "CRM (Pipeline)", "Chamadas", "Gravações", "Gerenciar Rotas", "Analytics Avançado", "Configurações"])

if st.sidebar.button("Atualizar Dados", use_container_width=True):
    clear_cache()
    st.rerun()

# ============================================================================
# PÁGINA: DASHBOARD GERAL
# ============================================================================

if page == "Dashboard Geral":
    st.title("Dashboard Geral")
    col1, col2, col3 = st.columns(3)
    with col1: period = st.selectbox("Período", [1, 7, 30, 90], index=2, key="dash_p")
    with col2: 
        if st.checkbox("Auto-refresh (60s)"):
            time.sleep(60); st.rerun()
    
    df = get_calls(days=period)
    
    if len(df) > 0:
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total", len(df))
        c2.metric("Completadas", len(df[df['status']=='completed']), f"{(len(df[df['status']=='completed'])/len(df)*100):.1f}%")
        c3.metric("Gravadas", len(df[df['recording_url'].notna()]))
        c4.metric("Duração Méd.", format_duration(df['duration'].mean()))
        c5.metric("Únicos", df['from_number'].nunique())
        
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Evolução Diária")
            daily = df.groupby(df['created_at'].dt.date).size().reset_index(name='calls')
            st.plotly_chart(px.area(daily, x='created_at', y='calls'), use_container_width=True)
        with col2:
            st.subheader("Status")
            st.plotly_chart(px.pie(df, names='status'), use_container_width=True)

        st.subheader("Últimas Chamadas")
        recent = df.head(10).copy()
        recent['Data'] = recent['created_at'].apply(format_date_br)
        recent['Duração'] = recent['duration'].apply(format_duration)
        st.dataframe(recent[['Data', 'from_number', 'status', 'Duração', 'tags']], use_container_width=True, hide_index=True)
    else: st.info("Sem dados.")

# ============================================================================
# PÁGINA: CRM / KANBAN
# ============================================================================

elif page == "CRM (Pipeline)":
    st.title("Pipeline de Atendimento")
    
    stages = supabase.table('pipeline_stages').select('*').order('position').execute().data
    # Busca deals - Importante: contacts(id, ...) para não dar erro
    deals_raw = supabase.table('deals').select('*, contacts(id, phone_number, name)').eq('status', 'OPEN').order('last_activity_at', desc=True).execute().data
    
    # Mapeamentos
    stage_map = {s['name']: s['id'] for s in stages}
    stage_names = [s['name'] for s in stages]
    
    # Processamento de Fuso para os Cards
    deals = []
    for d in deals_raw:
        # Converte a data UTC do banco para o fuso local
        utc_dt = pd.to_datetime(d['last_activity_at']).replace(tzinfo=timezone.utc)
        local_dt = utc_dt.astimezone(LOCAL_TZ)
        d['last_activity_local'] = local_dt
        deals.append(d)

    # Modal
    @st.dialog("Histórico do Lead", width="large")
    def show_lead_details(deal, contact_id):
        contact = deal['contacts']
        phone = contact['phone_number']
        st.subheader(f"{contact.get('name','Lead')} | {phone}")
        
        tab1, tab2 = st.tabs(["⏳ Linha do Tempo", "🤖 IA Intelligence"])
        with tab1:
            timeline = db_service.get_contact_timeline(contact_id)
            if not timeline: st.info("Vazio.")
            for ev in timeline:
                icon = "📞" if ev['event_type']=='CALL_INBOUND' else "🏷️"
                ev_dt = pd.to_datetime(ev['created_at']).replace(tzinfo=timezone.utc).astimezone(LOCAL_TZ)
                
                with st.chat_message("assistant", avatar=icon):
                    st.write(f"**{ev_dt.strftime('%d/%m %H:%M')}** - {ev['description']}")
                    meta = ev.get('metadata', {})
                    if meta.get('recording_url'): st.audio(meta['recording_url'])
                    if meta.get('new_tag'): 
                        c = TAG_COLORS.get(meta['new_tag'], '#333')
                        st.markdown(f":background[{c}] :color[white] **{meta['new_tag']}**")
        
        with tab2:
            # BUSCA SEGURA DE GRAVAÇÃO (Substitui a query complexa que dava erro)
            # 1. Tenta achar onde o LEAD ligou
            calls_res = supabase.table('calls').select('*')\
                .eq('from_number', phone)\
                .ilike('recording_url', 'http%')\
                .order('created_at', desc=True).limit(1).execute()
            
            # 2. Se não achar, tenta onde o LEAD recebeu
            if not calls_res.data:
                calls_res = supabase.table('calls').select('*')\
                    .eq('to_number', phone)\
                    .ilike('recording_url', 'http%')\
                    .order('created_at', desc=True).limit(1).execute()

            if calls_res.data:
                c = calls_res.data[0]
                sid = c['call_sid']
                # Converte data para mostrar
                c_date = pd.to_datetime(c['created_at']).replace(tzinfo=timezone.utc).astimezone(LOCAL_TZ)
                
                st.info(f"Chamada de: {c_date.strftime('%d/%m %H:%M')}")
                st.audio(c['recording_url'])
                
                ana = supabase.table('ai_analysis').select('*').eq('call_sid', sid).execute()
                if ana.data:
                    d = ana.data[0]
                    color = "green" if d['sentiment']=='Positive' else "red" if d['sentiment']=='Negative' else "gray"
                    st.markdown(f"### Sentimento: :{color}[{d['sentiment']}]")
                    st.info(d['summary'])
                    for t in (d['tags'] or []): st.markdown(f"`{t}`")
                elif st.button("✨ Analisar com IA", key="btn_ai_analise"):
                    with st.spinner("Analisando..."):
                        if ai_service.process_call(sid, c['recording_url']): st.rerun()
            else: 
                st.warning("Nenhuma gravação válida encontrada para este lead.")

    # Colunas Kanban
    cols = st.columns(len(stages))
    for i, stage in enumerate(stages):
        with cols[i]:
            s_deals = [d for d in deals if d['stage_id'] == stage['id']]
            st.markdown(f"<div style='border-top:3px solid {stage.get('color','#ccc')};padding:5px;'><b>{stage['name']}</b> ({len(s_deals)})</div>", unsafe_allow_html=True)
            
            for deal in s_deals:
                with st.container(border=True):
                    st.markdown(f"**{deal['contacts']['phone_number']}**")
                    
                    # Exibe hora local
                    dt_local = deal['last_activity_local']
                    # Comparação segura com timezone
                    is_recent = (datetime.now(timezone.utc) - pd.to_datetime(deal['last_activity_at']).replace(tzinfo=timezone.utc)).total_seconds() < 3600
                    icon = "🔥" if is_recent else "🕒"
                    st.caption(f"{icon} {dt_local.strftime('%d/%m %H:%M')}")
                    
                    # Ações
                    curr = stage['name']
                    idx = stage_names.index(curr) if curr in stage_names else 0
                    new_s = st.selectbox("Fase", stage_names, index=idx, key=f"s_{deal['id']}", label_visibility="collapsed")
                    
                    if new_s != curr:
                        db_service.update_deal_stage(deal['id'], stage_map[new_s])
                        st.toast("Movido!")
                        time.sleep(0.5); st.rerun()
                    
                    if st.button("Abrir", key=f"b_{deal['id']}", use_container_width=True):
                        show_lead_details(deal, deal['contacts']['id'])

# ============================================================================
# PÁGINA: CHAMADAS (TABELA)
# ============================================================================

elif page == "Chamadas":
    st.title("Histórico")
    c1, c2, c3, c4 = st.columns(4)
    with c1: period = st.selectbox("Período", [1, 7, 30], index=1)
    with c2: status = st.selectbox("Status", ["Todos", "completed", "missed"])
    with c3: search = st.text_input("Busca")
    
    df = get_calls(days=period, status=status)
    if search and not df.empty:
        df = df[df['from_number'].astype(str).str.contains(search)]
    
    if not df.empty:
        # Preparar dados já convertidos para local
        df['Data'] = df['created_at'].apply(format_date_br)
        df['Duração'] = df['duration'].apply(format_duration)
        
        edited = st.data_editor(
            df[['Data', 'from_number', 'to_number', 'status', 'Duração', 'tags', 'call_sid']],
            column_config={
                "tags": st.column_config.SelectboxColumn("Tag", options=TAG_OPTIONS, width="medium"),
                "call_sid": None,
                "from_number": "Origem",
                "to_number": "Destino"
            },
            hide_index=True, use_container_width=True, key="edit_calls"
        )
        
        if len(edited) == len(df):
            orig = df['tags'].fillna("").astype(str)
            new = edited['tags'].fillna("").astype(str)
            if (orig != new).any():
                for idx in (orig != new).index[orig != new]:
                    row = edited.loc[idx]
                    tag = row['tags'] if row['tags'] and row['tags'].strip() else "Limpar"
                    db_service.update_call_tag(row['call_sid'], tag)
                    st.toast("Salvo!")
                clear_cache(); time.sleep(0.5); st.rerun()
    else: st.info("Vazio.")

# ============================================================================
# PÁGINA: GRAVAÇÕES
# ============================================================================

elif page == "Gravações":
    st.title("Gravações")
    
    start = datetime.now(timezone.utc) - timedelta(days=7)
    res = supabase.table('calls').select('*').not_.is_('recording_url', 'null').gte('created_at', start.isoformat()).order('created_at', desc=True).execute()
    
    if res.data:
        recs = pd.DataFrame(res.data)
        recs = convert_to_local(recs, 'created_at')
        
        st.metric("Total (7 dias)", len(recs))
        
        for _, call in recs.iterrows():
            tag = call.get('tags')
            emoji = "🏷️" if tag in TAG_COLORS else "⬜"
            dt_str = format_date_br(call['created_at'])
            
            with st.expander(f"{emoji} {dt_str} | {call['from_number']}"):
                c1, c2, c3 = st.columns([2,2,1])
                with c1:
                    st.caption(f"Status: {call['status']}")
                    st.write(f"**Para:** {call['to_number']}")
                with c2: st.audio(call['recording_url'])
                with c3:
                    idx = TAG_OPTIONS.index(tag) if tag in TAG_OPTIONS else 0
                    n_tag = st.selectbox("Tag", ["Limpar"]+TAG_OPTIONS, index=idx+1 if tag in TAG_OPTIONS else 0, key=f"r_{call['call_sid']}", label_visibility="collapsed")
                    if n_tag != (tag or "Limpar"):
                        db_service.update_call_tag(call['call_sid'], n_tag if n_tag != "Limpar" else None)
                        st.toast("Salvo!"); time.sleep(0.5); clear_cache(); st.rerun()

# ============================================================================
# PÁGINAS EXTRAS
# ============================================================================

elif page == "Gerenciar Rotas":
    st.title("Rotas")
    with st.form("rota"):
        c1, c2 = st.columns(2)
        t = c1.text_input("Twilio (+55...)")
        d = c2.text_input("Destino (+55...)")
        if st.form_submit_button("Salvar"):
            if t and d: 
                db_service.add_phone_routing(t, d)
                st.success("Ok!"); clear_cache(); st.rerun()
    
    r = get_routes()
    if r: st.dataframe(r)

elif page == "Analytics Avançado":
    st.title("Analytics")
    df = get_calls()
    if not df.empty:
        df['Hora'] = df['created_at'].dt.hour
        st.bar_chart(df['Hora'].value_counts().sort_index())

elif page == "Configurações":
    st.title("Configuração")
    st.info(f"Fuso Horário Ativo: **{TZ_NAME}**")