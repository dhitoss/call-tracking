"""
Call Tracking Dashboard v2.9 (Fix UUID Error & Missing Attributes)
"""
import streamlit as st
import pandas as pd
from supabase import create_client, Client
import os
from datetime import datetime, timedelta, timezone
import plotly.express as px
import time
import pytz 
from urllib.parse import urlencode

# --- IMPORTS DOS SERVIÇOS ---
from services.database import get_database_service
from services.ai_service import AIService
from services.auth import AuthService
from services.analytics import AnalyticsService

db_service = get_database_service()
ai_service = AIService()
auth_service = AuthService()
analytics_service = AnalyticsService()

# --- CONFIG ---
st.set_page_config(page_title="Call Tracking CRM", page_icon="🔐", layout="wide", initial_sidebar_state="expanded")
st.markdown("""<style>.metric-card{background:#f0f2f6;padding:20px;border-radius:10px;border-left:4px solid #1f77b4}.tag-badge{padding:4px 8px;border-radius:4px;color:white;font-weight:bold;font-size:0.85em;display:inline-block}.sla-green{border-left:5px solid #22c55e;padding-left:10px}.sla-yellow{border-left:5px solid #eab308;padding-left:10px}.sla-red{border-left:5px solid #ef4444;padding-left:10px;background:#fff5f5}div[data-testid="stForm"]{border:1px solid #ddd;padding:20px;border-radius:10px;max-width:400px;margin:0 auto}</style>""", unsafe_allow_html=True)

SUPABASE_URL = os.getenv('SUPABASE_URL'); SUPABASE_KEY = os.getenv('SUPABASE_KEY')
if not SUPABASE_URL: st.stop()
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- LOGIN ---
if not auth_service.is_logged_in():
    c1,c2,c3=st.columns([1,2,1])
    with c2:
        st.markdown("<br><h1 style='text-align:center'>🔐 Acesso Restrito</h1>",unsafe_allow_html=True)
        with st.form("l"):
            e=st.text_input("Email");p=st.text_input("Senha",type="password")
            if st.form_submit_button("Entrar"):
                if auth_service.login(e,p): st.rerun()
                else: st.error("Erro.")
    st.stop()

# --- CONTEXTO & SEGURANÇA UUID ---
user_role = st.session_state.get('user_role', 'member')
user_org_id = st.session_state.get('user_org_id')
current_org_id = user_org_id

st.sidebar.title("Painel de Controle")

if user_role == 'super_admin':
    all_orgs = db_service.get_all_organizations() # Agora esta função existe no db!
    if all_orgs:
        org_map = {o['name']: o['id'] for o in all_orgs}
        sel_name = st.sidebar.selectbox("📁 Cliente", list(org_map.keys()))
        current_org_id = org_map[sel_name]
        st.sidebar.markdown("---")
else:
    st.sidebar.caption(f"Empresa: {st.session_state.get('org_name')}")

# TRAVA DE SEGURANÇA: Se não tiver ID de organização, não carrega nada
if not current_org_id:
    st.warning("⚠️ Nenhuma organização vinculada a este usuário. Contate o suporte.")
    st.stop()

# Configs Globais
TZ_NAME = os.getenv('DEFAULT_TIMEZONE', 'America/Sao_Paulo')
try: LOCAL_TZ = pytz.timezone(TZ_NAME)
except: LOCAL_TZ = pytz.timezone('America/Sao_Paulo')
TAG_OPTIONS = ["Agendado", "Reagendado", "Cancelado", "Retornar ligação", "Enviar info", "Sem vaga", "Não Agendou", "Ligação errada"]
TAG_COLORS = {"Agendado": "#28a745", "Reagendado": "#17a2b8", "Cancelado": "#dc3545"}

# Helpers
def fmt_dt(d): return d.strftime('%d/%m %H:%M') if not pd.isna(d) else ""
def fmt_dur(s): return f"{int(s//60):02d}:{int(s%60):02d}" if s else "00:00"
def clear_cache(): st.cache_data.clear()

@st.cache_data(ttl=60)
def get_calls(org_id, days=30, status=None):
    if not org_id: return pd.DataFrame() # Proteção extra
    s = datetime.now(timezone.utc) - timedelta(days=days)
    q = supabase.table('calls').select('*').eq('organization_id', org_id).gte('created_at', s.isoformat())
    if status and status!="Todos": q = q.eq('status', status)
    df = pd.DataFrame(q.order('created_at', desc=True).execute().data or [])
    if not df.empty:
        df['created_at'] = pd.to_datetime(df['created_at'], format='mixed', utc=True).dt.tz_convert(LOCAL_TZ)
        for c in ['duration','tags']: 
            if c not in df.columns: df[c] = None
        df['duration'] = df['duration'].fillna(0)
    return df

@st.cache_data(ttl=60)
def get_routes():
    if not current_org_id: return []
    return db_service.get_routes(current_org_id) # Passando org_id corretamente

# --- SIDEBAR ---
with st.sidebar:
    st.caption(f"👤 {st.session_state['user'].email}")
    if st.button("Sair"): auth_service.logout(); st.rerun()

with st.sidebar.expander("➕ Novo Lead Manual"):
    with st.form("nl", clear_on_submit=True):
        n=st.text_input("Nome"); p=st.text_input("Tel"); src=st.selectbox("Origem", ["Balcão","Indicação","Outro"]); obs=st.text_area("Nota")
        if st.form_submit_button("Salvar"):
            if n and p:
                db_service.create_manual_lead(n, p, src, current_org_id, obs)
                st.success("Ok!"); clear_cache(); st.session_state['pg']="CRM"; time.sleep(0.5); st.rerun()

if 'pg' not in st.session_state: st.session_state['pg'] = "Dashboard"
page = st.sidebar.radio("Menu", ["Dashboard", "CRM", "Chamadas", "Gravações", "Rotas", "Analytics", "Tracking"], key="pg")
if st.sidebar.button("Atualizar"): clear_cache(); st.rerun()

# --- PÁGINAS ---

if page == "Dashboard":
    st.title("Visão Geral")
    df = get_calls(current_org_id, 30)
    if not df.empty:
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Chamadas", len(df))
        c2.metric("Atendidas", len(df[df['status']=='completed']))
        c3.metric("Únicos", df['from_number'].nunique())
        c4.metric("Duração", fmt_dur(df['duration'].mean()))
        st.plotly_chart(px.area(df.groupby(df['created_at'].dt.date).size().reset_index(name='c'), x='created_at', y='c', title="Volume"), use_container_width=True)
    else: st.info("Sem dados.")

elif page == "CRM":
    st.title("Pipeline")
    stages = supabase.table('pipeline_stages').select('*').order('position').execute().data
    deals = supabase.table('deals').select('*, contacts(id, phone_number, name)').eq('organization_id', current_org_id).eq('status', 'OPEN').order('last_activity_at', desc=True).execute().data
    s_map = {s['name']: s['id'] for s in stages}
    s_names = [s['name'] for s in stages]

    @st.dialog("Detalhes", width="large")
    def details(deal, cid):
        contact = deal['contacts']
        st.subheader(f"{contact.get('name')} | {contact['phone_number']}")
        t1, t2 = st.tabs(["Timeline", "IA"])
        with t1:
            for e in db_service.get_contact_timeline(cid):
                dt = pd.to_datetime(e['created_at']).replace(tzinfo=timezone.utc).astimezone(LOCAL_TZ).strftime('%d/%m %H:%M')
                st.markdown(f"**{dt}** - {e['description']}")
                if e.get('metadata', {}).get('recording_url'): st.audio(e['metadata']['recording_url'])
        with t2:
            c_res = supabase.table('calls').select('*').eq('from_number', contact['phone_number']).ilike('recording_url', 'http%').order('created_at', desc=True).limit(1).execute()
            if not c_res.data: c_res = supabase.table('calls').select('*').eq('to_number', contact['phone_number']).ilike('recording_url', 'http%').order('created_at', desc=True).limit(1).execute()
            if c_res.data:
                c = c_res.data[0]
                st.audio(c['recording_url'])
                if st.button("Analisar"): ai_service.process_call(c['call_sid'], c['recording_url']); st.rerun()

    cols = st.columns(len(stages))
    for i, s in enumerate(stages):
        with cols[i]:
            sd = [d for d in deals if d['stage_id'] == s['id']]
            st.markdown(f"**{s['name']}** ({len(sd)})")
            for d in sd:
                diff = (datetime.now(timezone.utc) - pd.to_datetime(d['last_activity_at']).replace(tzinfo=timezone.utc)).total_seconds()/60
                sla = "sla-green" if diff < 30 else "sla-red" if diff > 120 else "sla-yellow"
                with st.container():
                    st.markdown(f"<div class='{sla}' style='background:white;padding:10px;border-radius:5px;margin-bottom:10px;box-shadow:0 1px 3px rgba(0,0,0,0.1)'><b>{d['contacts']['phone_number']}</b><br><small>{int(diff)}min</small></div>", unsafe_allow_html=True)
                    if st.button("Ver", key=f"v_{d['id']}", use_container_width=True): details(d, d['contacts']['id'])
                    ns = st.selectbox("Mover", s_names, index=s_names.index(s['name']), key=f"mv_{d['id']}", label_visibility="collapsed")
                    if ns != s['name']: db_service.update_deal_stage(d['id'], s_map[ns]); st.toast("Movido"); time.sleep(0.5); st.rerun()

elif page == "Chamadas":
    st.title("Histórico")
    df = get_calls(current_org_id, 30)
    if not df.empty:
        df['Data'] = df['created_at'].apply(fmt_dt)
        df['Duração'] = df['duration'].apply(fmt_dur)
        edited = st.data_editor(df[['Data','from_number','status','Duração','tags','call_sid']], key="ed", hide_index=True, use_container_width=True, column_config={"call_sid":None,"tags":st.column_config.SelectboxColumn("Tag",options=TAG_OPTIONS)})
        if len(edited) == len(df):
            orig = df['tags'].fillna("").astype(str); new = edited['tags'].fillna("").astype(str)
            if (orig!=new).any():
                for idx in (orig!=new).index[orig!=new]:
                    db_service.update_call_tag(edited.loc[idx]['call_sid'], edited.loc[idx]['tags'])
                clear_cache(); st.toast("Salvo"); time.sleep(0.5); st.rerun()

elif page == "Gravações":
    st.title("Gravações")
    start = datetime.now(timezone.utc) - timedelta(days=7)
    res = supabase.table('calls').select('*').eq('organization_id', current_org_id).not_.is_('recording_url', 'null').gte('created_at', start.isoformat()).order('created_at', desc=True).execute()
    if res.data:
        df = pd.DataFrame(res.data)
        df['created_at'] = pd.to_datetime(df['created_at'], format='mixed', utc=True).dt.tz_convert(LOCAL_TZ)
        for _, r in df.iterrows():
            with st.expander(f"{fmt_dt(r['created_at'])} | {r['from_number']}"):
                st.audio(r['recording_url'])

elif page == "Rotas":
    st.title("Rotas")
    with st.form("nr"):
        t = st.text_input("Twilio"); d = st.text_input("Destino"); c = st.text_input("Campanha")
        if st.form_submit_button("Salvar") and t and d:
            db_service.add_phone_routing(t, d, current_org_id, c); st.success("Ok"); clear_cache(); st.rerun()
    r = db_service.get_routes(current_org_id)
    if r: st.dataframe(r)

elif page == "Analytics":
    st.title("Analytics")
    kpis = analytics_service.get_kpis(current_org_id, 30)
    c1,c2,c3 = st.columns(3)
    c1.metric("Leads", kpis['total_leads']); c2.metric("Agendados", kpis['total_agendados']); c3.metric("Chamadas", kpis['total_calls'])
    funnel = analytics_service.get_funnel_data(current_org_id, 30)
    if not funnel.empty: st.plotly_chart(px.funnel(funnel, x='count', y='stage_name'), use_container_width=True)

elif page == "Tracking":
    st.title("Tracking UTM")
    t1, t2, t3 = st.tabs(["Link", "Script", "Relatório"])
    with t1:
        base=st.text_input("Site"); src=st.selectbox("Src", ["google","fb"]); num=st.text_input("Tel")
        if st.button("Gerar"): st.code(f"{base}?utm_source={src}&phone={num}")
    with t3:
        perf = db_service.get_marketing_performance(current_org_id)
        if perf: st.dataframe(pd.DataFrame(perf), use_container_width=True)