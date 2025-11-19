"""
Call Tracking Dashboard v3.6
- Feat: Gestão Avançada de Contatos (Edição, Preferências, Auditoria)
- Fix: Regras de negócio para edição de telefone
- Core: CRM, Ligações, IA, Multi-Tenancy
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

# --- IMPORTS ---
from services.database import get_database_service
from services.ai_service import AIService
from services.auth import AuthService
from services.analytics import AnalyticsService

db_service = get_database_service()
ai_service = AIService()
auth_service = AuthService()
analytics_service = AnalyticsService()

# --- CONFIG ---
st.set_page_config(page_title="Call Tracking", page_icon="📞", layout="wide")
st.markdown("""<style>.metric-card{background:#f0f2f6;padding:20px;border-radius:10px;border-left:4px solid #1f77b4}.tag-badge{padding:4px 8px;border-radius:4px;color:white;font-weight:bold;font-size:0.85em;display:inline-block}.sla-green{border-left:5px solid #22c55e;padding-left:10px}.sla-yellow{border-left:5px solid #eab308;padding-left:10px}.sla-red{border-left:5px solid #ef4444;padding-left:10px;background:#fff5f5}div[data-testid="stForm"]{border:1px solid #ddd;padding:20px;border-radius:10px;max-width:400px;margin:0 auto}</style>""", unsafe_allow_html=True)

SUPABASE_URL = os.getenv('SUPABASE_URL'); SUPABASE_KEY = os.getenv('SUPABASE_KEY')
if not SUPABASE_URL: st.stop()
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- LOGIN ---
if not auth_service.is_logged_in():
    c1,c2,c3=st.columns([1,2,1])
    with c2:
        st.markdown("<br><h1 style='text-align:center'>🔐 Login</h1>",unsafe_allow_html=True)
        with st.form("l"):
            e=st.text_input("Email");p=st.text_input("Senha",type="password")
            if st.form_submit_button("Entrar"):
                if auth_service.login(e,p): st.rerun()
                else: st.error("Erro.")
    st.stop()

# --- CONTEXTO ---
user_role = st.session_state.get('user_role', 'member')
user_org_id = st.session_state.get('user_org_id')
current_org_id = user_org_id

# Sidebar Admin
st.sidebar.title("Painel de Controle")
if user_role == 'super_admin':
    all_orgs = db_service.get_all_organizations()
    if all_orgs:
        org_map = {o['name']: o['id'] for o in all_orgs}
        sel_name = st.sidebar.selectbox("📁 Cliente / Visão", list(org_map.keys()))
        current_org_id = org_map[sel_name]
        st.sidebar.markdown("---")
else:
    st.sidebar.caption(f"Empresa: {st.session_state.get('org_name')}")

if not current_org_id: st.warning("Sem organização."); st.stop()

# --- HELPERS ---
TZ_NAME = os.getenv('DEFAULT_TIMEZONE', 'America/Sao_Paulo')
try: LOCAL_TZ = pytz.timezone(TZ_NAME)
except: LOCAL_TZ = pytz.timezone('America/Sao_Paulo')
TAG_OPTIONS = ["Agendado", "Reagendado", "Cancelado", "Retornar ligação", "Enviar info", "Sem vaga", "Não Agendou", "Ligação errada"]
TAG_COLORS = {"Agendado": "#28a745", "Reagendado": "#17a2b8", "Cancelado": "#dc3545", "Retornar ligação": "#ffc107", "Enviar info": "#6c757d", "Sem vaga": "#343a40", "Não Agendou": "#fd7e14", "Ligação errada": "#000000"}

def convert_to_local(df, col='created_at'):
    if df.empty or col not in df.columns: return df
    df[col] = pd.to_datetime(df[col], format='mixed', utc=True).dt.tz_convert(LOCAL_TZ)
    return df

def format_duration(s): return f"{int(s//60):02d}:{int(s%60):02d}" if s else "00:00"
def format_date_br(dt): return dt.strftime('%d/%m %H:%M') if not pd.isna(dt) else ""
def clear_cache(): st.cache_data.clear()

@st.cache_data(ttl=60)
def get_calls(org_id, days=30):
    s = datetime.now(timezone.utc) - timedelta(days=days)
    q = supabase.table('calls').select('*').eq('organization_id', org_id).gte('created_at', s.isoformat()).order('created_at', desc=True)
    res = q.execute()
    df = pd.DataFrame(res.data) if res.data else pd.DataFrame()
    if not df.empty:
        df = convert_to_local(df)
        for c in ['duration','tags','recording_url']: 
            if c not in df.columns: df[c] = None
        df['duration'] = df['duration'].fillna(0)
    return df

@st.cache_data(ttl=60)
def get_routes():
    return db_service.get_routes(current_org_id)

# --- MENU ---
with st.sidebar:
    st.caption(f"👤 {st.session_state['user'].email}")
    if st.button("Sair"): auth_service.logout(); st.rerun()

with st.sidebar.expander("➕ Novo Lead Manual"):
    with st.form("nl", clear_on_submit=True):
        n=st.text_input("Nome"); p=st.text_input("Tel"); src=st.selectbox("Origem", ["Balcão","Indicação","Outro"]); obs=st.text_area("Nota")
        if st.form_submit_button("Salvar") and n and p:
            db_service.create_manual_lead(n, p, src, current_org_id, obs); st.success("Ok!"); clear_cache(); st.session_state['pg']="CRM"; time.sleep(0.5); st.rerun()

if 'pg' not in st.session_state: st.session_state['pg'] = "Dashboard"
menu_opts = ["Dashboard", "CRM", "Ligações", "Rotas", "Analytics", "Tracking"]
if user_role == 'super_admin': menu_opts.append("Admin Global")
page = st.sidebar.radio("Menu", menu_opts, key="pg")
if st.sidebar.button("Atualizar"): clear_cache(); st.rerun()

# ============================================================================
# PÁGINAS
# ============================================================================

if page == "Dashboard":
    st.title("Visão Geral")
    df = get_calls(current_org_id, 30)
    if not df.empty:
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Chamadas (30d)", len(df))
        c2.metric("Atendidas", len(df[df['status']=='completed']))
        c3.metric("Únicos", df['from_number'].nunique())
        c4.metric("Duração", format_duration(df['duration'].mean()))
        st.plotly_chart(px.area(df.groupby(df['created_at'].dt.date).size().reset_index(name='c'), x='created_at', y='c', title="Volume"), use_container_width=True)
    else: st.info("Sem dados.")

elif page == "CRM":
    st.title("Pipeline")
    stages = supabase.table('pipeline_stages').select('*').order('position').execute().data
    deals = supabase.table('deals').select('*, contacts(id, phone_number, name)').eq('organization_id', current_org_id).eq('status', 'OPEN').order('last_activity_at', desc=True).execute().data
    s_map = {s['name']: s['id'] for s in stages}; s_names = [s['name'] for s in stages]

    @st.dialog("Detalhes do Lead", width="large")
    def details(deal, cid):
        # Busca contato fresco para garantir dados atualizados
        c_data = supabase.table('contacts').select('*').eq('id', cid).single().execute().data
        if not c_data: st.error("Erro ao carregar contato."); return
        
        st.subheader(f"{c_data.get('name','Lead')} | {c_data.get('phone_number')}")
        t1, t2, t3 = st.tabs(["👤 Dados", "⏳ Timeline", "🤖 IA"])
        
        # ABA 1: DADOS (Edição)
        with t1:
            with st.form("edit_contact"):
                c1, c2 = st.columns(2)
                with c1:
                    nn = st.text_input("Nome", value=c_data.get('name',''))
                    ne = st.text_input("Email", value=c_data.get('email',''))
                with c2:
                    is_man = c_data.get('is_manual', False)
                    # Bloqueia telefone se não for manual
                    np = st.text_input("Telefone", value=c_data.get('phone_number',''), disabled=not is_man, help="Editável apenas para leads manuais.")
                    
                    pref_ops = ["whatsapp", "phone", "email"]
                    cur_p = c_data.get('contact_preference', 'whatsapp')
                    idx_p = pref_ops.index(cur_p) if cur_p in pref_ops else 0
                    npref = st.selectbox("Preferência", pref_ops, index=idx_p)
                
                if st.form_submit_button("💾 Salvar"):
                    u_email = st.session_state['user'].email
                    d = {'name':nn, 'email':ne, 'phone_number':np, 'contact_preference':npref}
                    if db_service.update_contact_details(cid, d, u_email):
                        st.success("Salvo!"); time.sleep(0.5); st.rerun()
                    else: st.error("Erro.")

        # ABA 2: TIMELINE
        with t2:
            for e in db_service.get_contact_timeline(cid):
                icon = "📝"
                if 'CALL' in e['event_type']: icon = "📞"
                elif 'WHATS' in e['event_type']: icon = "💬"
                elif 'SYSTEM' in e['event_type']: icon = "⚙️"
                
                dt = pd.to_datetime(e['created_at']).replace(tzinfo=timezone.utc).astimezone(LOCAL_TZ).strftime('%d/%m %H:%M')
                author = f" ({e.get('created_by')})" if e.get('created_by') and e.get('created_by') != 'SYSTEM' else ""
                
                with st.chat_message("assistant", avatar=icon):
                    st.markdown(f"**{dt}**{author}")
                    st.write(e['description'])
                    meta = e.get('metadata') or {}
                    if isinstance(meta, dict):
                        if meta.get('recording_url'): st.audio(meta['recording_url'])
                        if meta.get('new_tag'): 
                            c = TAG_COLORS.get(meta['new_tag'], '#333')
                            st.markdown(f":background[{c}] :color[white] **{meta['new_tag']}**")

        # ABA 3: IA
        with t3:
            # Busca gravação (Origem ou Destino)
            ph = c_data['phone_number']
            c_res = supabase.table('calls').select('*').eq('from_number', ph).ilike('recording_url', 'http%').order('created_at', desc=True).limit(1).execute()
            if not c_res.data: c_res = supabase.table('calls').select('*').eq('to_number', ph).ilike('recording_url', 'http%').order('created_at', desc=True).limit(1).execute()
            
            if c_res.data:
                c = c_res.data[0]; st.audio(c['recording_url'])
                if st.button("Analisar"): ai_service.process_call(c['call_sid'], c['recording_url']); st.rerun()
            else: st.warning("Sem gravação.")

    cols = st.columns(len(stages))
    for i, s in enumerate(stages):
        with cols[i]:
            sd = [d for d in deals if d['stage_id'] == s['id']]
            st.markdown(f"<div style='border-top:3px solid {s.get('color','#ccc')};padding:5px;'><b>{s['name']}</b> ({len(sd)})</div>", unsafe_allow_html=True)
            for d in sd:
                diff = (datetime.now(timezone.utc) - pd.to_datetime(d['last_activity_at']).replace(tzinfo=timezone.utc)).total_seconds()/60
                sla = "sla-green" if diff < 30 else "sla-red" if diff > 120 else "sla-yellow"
                with st.container():
                    st.markdown(f"<div class='{sla}' style='background:white;padding:10px;border-radius:5px;margin-bottom:10px;box-shadow:0 1px 3px rgba(0,0,0,0.1)'><b>{d['contacts']['phone_number']}</b><br><small>{d['contacts'].get('name','')}</small><br><small>{int(diff)}min</small></div>", unsafe_allow_html=True)
                    
                    c1, c2 = st.columns(2)
                    with c1:
                        # Zap
                        pc = d['contacts']['phone_number'].replace('+','').replace('-','')
                        if st.button("💬 Zap", key=f"w_{d['id']}", use_container_width=True):
                            db_service.log_interaction(d['id'], d['contacts']['id'], "OUTBOUND_WHATSAPP", "Abriu WhatsApp")
                            st.link_button("🔗 Link", f"https://wa.me/{pc}")
                            time.sleep(1); st.rerun()
                    with c2:
                        if st.button("📂 Ver", key=f"o_{d['id']}", use_container_width=True): details(d, d['contacts']['id'])
                    
                    ns = st.selectbox("Mover", s_names, index=s_names.index(s['name']), key=f"mv_{d['id']}", label_visibility="collapsed")
                    if ns != s['name']: db_service.update_deal_stage(d['id'], s_map[ns]); st.toast("Movido"); time.sleep(0.5); st.rerun()

elif page == "Ligações":
    st.title("Histórico de Ligações")
    c1, c2, c3, c4 = st.columns(4)
    with c1: period = st.selectbox("Período", [1, 7, 30, 60], index=2)
    with c2: status_filter = st.selectbox("Status", ["Todos", "completed", "missed", "busy"])
    with c3: tag_filter = st.multiselect("Filtrar Tags", TAG_OPTIONS)
    with c4: search = st.text_input("Buscar Número")
    
    df = get_calls(current_org_id, days=period)
    
    if not df.empty:
        if status_filter != "Todos": df = df[df['status'] == status_filter]
        if search: df = df[df['from_number'].astype(str).str.contains(search) | df['to_number'].astype(str).str.contains(search)]
        if tag_filter: df = df[df['tags'].isin(tag_filter)]
    
    if not df.empty:
        k1, k2, k3 = st.columns(3)
        k1.metric("Listadas", len(df))
        k2.metric("Gravadas", len(df[df['recording_url'].notna()]))
        k3.metric("Duração Média", format_duration(df['duration'].mean()))
        st.divider()

        st.caption("Clique para expandir, ouvir e classificar.")
        
        for idx, row in df.iterrows():
            tag = row['tags']
            tag_display = "⬜ Classificar"
            if tag and tag in TAG_COLORS: tag_display = f"🏷️ {tag}"
            
            has_rec = "🎵" if row['recording_url'] else "🔇"
            header_text = f"{has_rec} {format_date_br(row['created_at'])} | {row['from_number']} | {tag_display}"
            
            with st.expander(header_text):
                col1, col2, col3 = st.columns([1, 1, 1])
                with col1:
                    st.markdown(f"**De:** `{row['from_number']}`")
                    st.markdown(f"**Para:** `{row['to_number']}`")
                    st.caption(f"Status: {row['status']} | Duração: {format_duration(row['duration'])}")
                with col2:
                    if row['recording_url']: st.audio(row['recording_url'])
                    else: st.info("Sem gravação")
                with col3:
                    current_idx = TAG_OPTIONS.index(tag) if tag in TAG_OPTIONS else 0
                    new_tag = st.selectbox("Classificação", ["Limpar"] + TAG_OPTIONS, index=current_idx + 1 if tag in TAG_OPTIONS else 0, key=f"tag_{row['call_sid']}", label_visibility="collapsed")
                    val = new_tag if new_tag != "Limpar" else None
                    if val != tag:
                        db_service.update_call_tag(row['call_sid'], val)
                        st.toast(f"Salvo: {val}"); time.sleep(0.5); st.rerun()
                    if tag in TAG_COLORS: st.markdown(f"<span class='tag-badge' style='background:{TAG_COLORS[tag]}'>{tag}</span>", unsafe_allow_html=True)
    else: st.info("Nenhuma chamada encontrada.")

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
        base=st.text_input("Site"); src=st.selectbox("Source", ["google","fb"]); num=st.text_input("Tel")
        if st.button("Gerar"): st.code(f"{base}?utm_source={src}&phone={num}")
    with t2:
        st.code("""<script>
function getP(n){return decodeURIComponent((new RegExp('[?|&]'+n+'=([^&;]+?)(&|#|;|$)').exec(location.search)||[,""])[1].replace(/\+/g,'%20'))||null}
window.onload=function(){
  var p = getP('phone');
  if(p){
    document.querySelectorAll('a[href^="tel:"]').forEach(function(l){l.href="tel:"+p;l.innerText=p});
    document.querySelectorAll('a[href*="wa.me"]').forEach(function(l){l.href=l.href.replace(/phone=\d+/,"phone="+p.replace(/\D/g,''))});
    console.log("DNI: Phone changed to " + p);
  }
}
</script>""", language="html")
    with t3:
        perf = db_service.get_marketing_performance(current_org_id)
        if perf: st.dataframe(pd.DataFrame(perf))

elif page == "Admin Global" and user_role == 'super_admin':
    st.title("Gestão Global")
    orgs = db_service.get_all_organizations()
    if orgs:
        df_o = pd.DataFrame(orgs)
        ed = st.data_editor(df_o, column_config={"id":None}, hide_index=True, key="adm_org")
        if len(ed)==len(df_o):
            if (ed['name']!=df_o['name']).any():
                for i in (ed['name']!=df_o['name']).index[ed['name']!=df_o['name']]:
                    db_service.update_organization_name(ed.loc[i]['id'], ed.loc[i]['name'])
                st.toast("Salvo!"); time.sleep(0.5); st.rerun()
    st.divider()
    with st.form("new_org"):
        nm = st.text_input("Nova Clínica")
        if st.form_submit_button("Criar"):
            res = db_service.create_organization(nm)
            if res: st.success(f"Criado! ID: {res.data[0]['id']}"); st.rerun()

elif page == "Configurações":
    st.title("Configuração")
    st.info(f"Ambiente: {os.getenv('RAILWAY_ENVIRONMENT_NAME','Production')} | Fuso: {TZ_NAME}")