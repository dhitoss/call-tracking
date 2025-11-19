"""
Call Tracking Dashboard v2.5 (MVP Pilot)
- Feat: Sistema de Login (Gatekeeper)
- Core: CRM, IA, Telefonia
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
from services.auth import AuthService

# Inicialização
db_service = get_database_service()
ai_service = AIService()
auth_service = AuthService()

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Call Tracking CRM",
    page_icon="🔐",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS ---
st.markdown("""
<style>
    .metric-card { background-color: #f0f2f6; padding: 20px; border-radius: 10px; border-left: 4px solid #1f77b4; }
    .tag-badge { padding: 4px 8px; border-radius: 4px; color: white; font-weight: bold; font-size: 0.85em; display: inline-block; }
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    .stTabs [data-baseweb="tab"] { padding: 10px 20px; }
    .sla-green { border-left: 5px solid #22c55e; padding-left: 10px; }
    .sla-yellow { border-left: 5px solid #eab308; padding-left: 10px; }
    .sla-red { border-left: 5px solid #ef4444; padding-left: 10px; background-color: #fff5f5; }
    /* Centralizar Login */
    div[data-testid="stForm"] { border: 1px solid #ddd; padding: 20px; border-radius: 10px; max-width: 400px; margin: 0 auto; }
</style>
""", unsafe_allow_html=True)

# Supabase (para queries diretas se necessário)
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
if not SUPABASE_URL: st.stop()
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ============================================================================
# 🔐 LÓGICA DE LOGIN (GATEKEEPER)
# ============================================================================

if not auth_service.is_logged_in():
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("<h1 style='text-align: center;'>🔐 Acesso Restrito</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: gray;'>Call Tracking & CRM Intelligence</p>", unsafe_allow_html=True)
        
        with st.form("login_form"):
            email = st.text_input("E-mail")
            password = st.text_input("Senha", type="password")
            submit = st.form_submit_button("Entrar", use_container_width=True)
            
            if submit:
                user = auth_service.login(email, password)
                if user:
                    st.session_state['user'] = user
                    st.toast("Login realizado com sucesso!")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("Credenciais inválidas.")
    st.stop() # 🛑 PARA AQUI SE NÃO TIVER LOGADO

# ============================================================================
# 🚀 APLICAÇÃO PRINCIPAL (AREA LOGADA)
# ============================================================================

# --- CONFIGURAÇÃO DE FUSO HORÁRIO ---
TZ_NAME = os.getenv('DEFAULT_TIMEZONE', 'America/Sao_Paulo')
try: LOCAL_TZ = pytz.timezone(TZ_NAME)
except: LOCAL_TZ = pytz.timezone('America/Sao_Paulo')

TAG_OPTIONS = ["Agendado", "Reagendado", "Cancelado", "Retornar ligação", "Enviar info", "Sem vaga", "Não Agendou", "Ligação errada"]
TAG_COLORS = {"Agendado": "#28a745", "Reagendado": "#17a2b8", "Cancelado": "#dc3545", "Retornar ligação": "#ffc107", "Enviar info": "#6c757d", "Sem vaga": "#343a40", "Não Agendou": "#fd7e14", "Ligação errada": "#000000"}

# --- FUNÇÕES AUXILIARES ---
def convert_to_local(df, col='created_at'):
    if df.empty or col not in df.columns: return df
    df[col] = pd.to_datetime(df[col], format='mixed', utc=True).dt.tz_convert(LOCAL_TZ)
    return df

def format_date_br(dt): return dt.strftime('%d/%m/%Y %H:%M') if not pd.isna(dt) else ""
def format_duration(s): return f"{int(s//60):02d}:{int(s%60):02d}" if s else "00:00"
def clear_cache(): st.cache_data.clear()

@st.cache_data(ttl=60)
def get_calls(days=30, status=None, campaign=None):
    start = datetime.now(timezone.utc) - timedelta(days=days)
    q = supabase.table('calls').select('*').gte('created_at', start.isoformat())
    if status and status!="Todos": q = q.eq('status', status)
    if campaign: q = q.eq('campaign', campaign)
    res = q.order('created_at', desc=True).execute()
    df = pd.DataFrame(res.data) if res.data else pd.DataFrame()
    if not df.empty:
        for c in ['duration','tags','campaign','destination_number','recording_url']: 
            if c not in df.columns: df[c] = None
        df['duration'] = df['duration'].fillna(0)
        df = convert_to_local(df)
    return df

@st.cache_data(ttl=60)
def get_routes():
    r = supabase.table('phone_routing').select('*').order('created_at', desc=True).execute()
    return r.data if r.data else []

def update_call_tag(call_sid, tag):
    try:
        val = tag if tag and tag != "Limpar" else None
        supabase.table('calls').update({'tags': val, 'updated_at': datetime.utcnow().isoformat()}).eq('call_sid', call_sid).execute()
        return True
    except: return False

# --- SIDEBAR ---
st.sidebar.title("Call Tracking")

# User Info
with st.sidebar:
    user_email = st.session_state['user'].email
    st.caption(f"👤 **{user_email}**")
    if st.button("Sair / Logout", use_container_width=True):
        auth_service.logout()
        st.rerun()

st.sidebar.markdown("---")

# Novo Lead Manual
with st.sidebar.expander("➕ Novo Lead Manual", expanded=False):
    with st.form("new_lead_form", clear_on_submit=True):
        nl_name = st.text_input("Nome")
        nl_phone = st.text_input("Telefone")
        nl_source = st.selectbox("Origem", ["Balcão", "Indicação", "Instagram", "Outro"])
        nl_note = st.text_area("Nota")
        if st.form_submit_button("Salvar"):
            if nl_phone and nl_name:
                if db_service.create_manual_lead(nl_name, nl_phone, nl_source, nl_note):
                    st.success("Criado!"); clear_cache(); st.session_state['nav_page']="CRM (Pipeline)"; time.sleep(0.5); st.rerun()
                else: st.error("Erro.")

if 'nav_page' not in st.session_state: st.session_state['nav_page'] = "Dashboard Geral"

page = st.sidebar.radio("Menu", ["Dashboard Geral", "CRM (Pipeline)", "Chamadas", "Gravações", "Gerenciar Rotas", "Configurações"], key="nav_page")

if st.sidebar.button("Atualizar", use_container_width=True): clear_cache(); st.rerun()

# ============================================================================
# PÁGINAS (Conteúdo Protegido)
# ============================================================================

if page == "Dashboard Geral":
    st.title("Dashboard Geral")
    col1, col2 = st.columns(2)
    with col1: period = st.selectbox("Período", [7, 30, 90], index=1)
    df = get_calls(days=period)
    if not df.empty:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Chamadas", len(df))
        c2.metric("Atendidas", len(df[df['status']=='completed']))
        c3.metric("Únicos", df['from_number'].nunique())
        c4.metric("Duração", format_duration(df['duration'].mean()))
        daily = df.groupby(df['created_at'].dt.date).size().reset_index(name='calls')
        st.plotly_chart(px.area(daily, x='created_at', y='calls', title="Volume"), use_container_width=True)
    else: st.info("Sem dados.")

elif page == "CRM (Pipeline)":
    st.title("Pipeline de Atendimento")
    stages = supabase.table('pipeline_stages').select('*').order('position').execute().data
    deals_raw = supabase.table('deals').select('*, contacts(id, phone_number, name)').eq('status', 'OPEN').order('last_activity_at', desc=True).execute().data
    stage_map = {s['name']: s['id'] for s in stages}
    stage_names = [s['name'] for s in stages]
    deals = []
    for d in deals_raw:
        utc = pd.to_datetime(d['last_activity_at']).replace(tzinfo=timezone.utc)
        d['local_dt'] = utc.astimezone(LOCAL_TZ)
        deals.append(d)

    @st.dialog("Detalhes", width="large")
    def show_lead_details(deal, contact_id):
        contact = deal['contacts']
        st.subheader(f"{contact.get('name')} | {contact['phone_number']}")
        t1, t2 = st.tabs(["Timeline", "IA"])
        with t1:
            tl = db_service.get_contact_timeline(contact_id)
            if not tl: st.info("Vazio")
            for e in tl:
                icon = "📞" if 'CALL' in e['event_type'] else "💬" if 'WHATS' in e['event_type'] else "📝"
                dt = pd.to_datetime(e['created_at']).replace(tzinfo=timezone.utc).astimezone(LOCAL_TZ).strftime('%d/%m %H:%M')
                st.markdown(f"{icon} **{dt}** - {e['description']}")
                if e.get('metadata') and e['metadata'].get('recording_url'): st.audio(e['metadata']['recording_url'])
        with t2:
            phone = contact['phone_number']
            c_res = supabase.table('calls').select('*').eq('from_number', phone).ilike('recording_url', 'http%').order('created_at', desc=True).limit(1).execute()
            if not c_res.data: c_res = supabase.table('calls').select('*').eq('to_number', phone).ilike('recording_url', 'http%').order('created_at', desc=True).limit(1).execute()
            if c_res.data:
                c = c_res.data[0]
                st.audio(c['recording_url'])
                if st.button("Analisar IA"):
                    with st.spinner("..."): ai_service.process_call(c['call_sid'], c['recording_url']); st.rerun()

    cols = st.columns(len(stages))
    for i, stage in enumerate(stages):
        with cols[i]:
            s_deals = [d for d in deals if d['stage_id'] == stage['id']]
            st.markdown(f"<div style='border-top:3px solid {stage.get('color','#ccc')};padding:5px;'><b>{stage['name']}</b> ({len(s_deals)})</div>", unsafe_allow_html=True)
            for deal in s_deals:
                now = datetime.now(timezone.utc)
                diff = (now - pd.to_datetime(deal['last_activity_at']).replace(tzinfo=timezone.utc)).total_seconds()/60
                sla = "sla-green"
                if diff > 120: sla = "sla-red"
                elif diff > 30: sla = "sla-yellow"
                
                with st.container():
                    st.markdown(f"""<div class="{sla}" style="background:white;border-radius:5px;padding:10px;margin-bottom:10px;box-shadow:0 1px 3px rgba(0,0,0,0.1);"><small>{deal['contacts'].get('name')}</small><br><strong>{deal['contacts']['phone_number']}</strong><br><small>{int(diff)} min atrás</small></div>""", unsafe_allow_html=True)
                    c1, c2 = st.columns(2)
                    with c1:
                        pc = deal['contacts']['phone_number'].replace('+','').replace('-','')
                        if st.button("💬 Zap", key=f"w_{deal['id']}", use_container_width=True):
                            db_service.log_interaction(deal['id'], deal['contacts']['id'], "OUTBOUND_WHATSAPP", "Abriu WhatsApp")
                            st.link_button("🔗 Link", f"https://wa.me/{pc}")
                            time.sleep(1); st.rerun()
                    with c2:
                        if st.button("📂 Ver", key=f"o_{deal['id']}", use_container_width=True): show_lead_details(deal, deal['contacts']['id'])
                    
                    cur = stage['name']
                    idx = stage_names.index(cur) if cur in stage_names else 0
                    ns = st.selectbox("Mover", stage_names, index=idx, key=f"mv_{deal['id']}", label_visibility="collapsed")
                    if ns != cur:
                        db_service.update_deal_stage(deal['id'], stage_map[ns]); st.toast("Movido!"); time.sleep(0.5); st.rerun()

elif page == "Chamadas":
    st.title("Histórico")
    df = get_calls(days=30)
    if not df.empty:
        df['Data'] = df['created_at'].apply(format_date_br)
        df['Duração'] = df['duration'].apply(format_duration)
        edited = st.data_editor(df[['Data','from_number','to_number','status','Duração','tags','call_sid']], column_config={"tags":st.column_config.SelectboxColumn("Tag",options=TAG_OPTIONS),"call_sid":None}, hide_index=True, use_container_width=True)
        if len(edited)==len(df):
            orig = df['tags'].fillna("").astype(str)
            new = edited['tags'].fillna("").astype(str)
            if (orig!=new).any():
                for idx in (orig!=new).index[orig!=new]:
                    r = edited.loc[idx]
                    t = r['tags'] if r['tags'] and r['tags'].strip() else "Limpar"
                    update_call_tag(r['call_sid'], t)
                clear_cache(); time.sleep(0.5); st.rerun()

elif page == "Gravações":
    st.title("Gravações")
    start = datetime.now(timezone.utc) - timedelta(days=7)
    res = supabase.table('calls').select('*').not_.is_('recording_url', 'null').gte('created_at', start.isoformat()).order('created_at', desc=True).execute()
    if res.data:
        recs = pd.DataFrame(res.data)
        recs = convert_to_local(recs)
        st.metric("Total (7 dias)", len(recs))
        for _, c in recs.iterrows():
            tag = c.get('tags')
            emoji = "🏷️" if tag in TAG_COLORS else "⬜"
            dt = format_date_br(c['created_at'])
            with st.expander(f"{emoji} {dt} | {c['from_number']}"):
                c1,c2,c3 = st.columns([2,2,1])
                with c1: st.write(f"**Para:** {c['to_number']}"); st.caption(f"Status: {c['status']}")
                with c2: st.audio(c['recording_url'])
                with c3:
                    idx = TAG_OPTIONS.index(tag) if tag in TAG_OPTIONS else 0
                    nt = st.selectbox("Tag", ["Limpar"]+TAG_OPTIONS, index=idx+1 if tag in TAG_OPTIONS else 0, key=f"g_{c['call_sid']}", label_visibility="collapsed")
                    if nt != (tag or "Limpar"):
                        update_call_tag(c['call_sid'], nt if nt!="Limpar" else None)
                        st.toast("Salvo!"); time.sleep(0.5); clear_cache(); st.rerun()

elif page == "Gerenciar Rotas":
    st.title("Rotas")
    with st.form("nr"):
        t = st.text_input("Twilio"); d = st.text_input("Destino")
        if st.form_submit_button("Salvar") and t and d:
            db_service.add_phone_routing(t, d); st.success("Ok!"); clear_cache(); st.rerun()
    r = get_routes()
    if r: st.dataframe(r)

elif page == "Configurações":
    st.title("Configuração")
    st.info(f"Ambiente: {os.getenv('RAILWAY_ENVIRONMENT_NAME','Production')}")