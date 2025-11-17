"""
Componente de resumo executivo do dashboard.
"""
import streamlit as st
import pandas as pd
from datetime import datetime


def render_executive_summary(df: pd.DataFrame, filters: dict):
    """
    Renderiza resumo executivo com insights principais.
    
    Args:
        df: DataFrame com chamadas
        filters: Filtros aplicados
    """
    st.subheader("📋 Resumo Executivo")
    
    if df.empty:
        st.info("Sem dados para gerar resumo")
        return
    
    # Calcular insights
    total_calls = len(df)
    completed = len(df[df['status'] == 'completed'])
    missed = len(df[df['status'].isin(['no-answer', 'busy'])])
    answer_rate = (completed / total_calls * 100) if total_calls > 0 else 0
    
    # Campanha com melhor performance
    campaign_stats = df.groupby('campaign_id').agg({
        'call_sid': 'count',
        'status': lambda x: (x == 'completed').sum()
    }).reset_index()
    campaign_stats.columns = ['campaign_id', 'total', 'completed']
    campaign_stats['rate'] = (campaign_stats['completed'] / campaign_stats['total'] * 100)
    
    best_campaign = campaign_stats.nlargest(1, 'rate')
    worst_campaign = campaign_stats.nsmallest(1, 'rate')
    
    # Horário de pico
    df['hour'] = pd.to_datetime(df['created_at']).dt.hour
    peak_hour = df['hour'].mode()[0] if not df.empty else 0
    
    # Renderizar insights
    st.markdown(f"""
    **Período Analisado:** {filters['start_date'].strftime('%d/%m/%Y')} a {filters['end_date'].strftime('%d/%m/%Y')}
    
    **Principais Insights:**
    
    - 📞 **{total_calls}** ligações registradas no período
    - ✅ **{answer_rate:.1f}%** de taxa de atendimento geral
    - ⏰ **{peak_hour}h** é o horário de maior volume de ligações
    """)
    
    if not best_campaign.empty:
        st.markdown(f"""
    - 🏆 **Melhor campanha:** {best_campaign.iloc[0]['campaign_id']} ({best_campaign.iloc[0]['rate']:.1f}% atendimento)
        """)
    
    if not worst_campaign.empty and len(campaign_stats) > 1:
        st.markdown(f"""
    - ⚠️ **Atenção necessária:** {worst_campaign.iloc[0]['campaign_id']} ({worst_campaign.iloc[0]['rate']:.1f}% atendimento)
        """)
    
    # Recomendações
    if answer_rate < 60:
        st.warning("💡 **Recomendação:** Taxa de atendimento abaixo de 60%. Considere aumentar a equipe ou revisar processos.")
    elif answer_rate < 80:
        st.info("💡 **Recomendação:** Taxa de atendimento pode ser melhorada. Analise horários de pico e distribua recursos.")
    else:
        st.success("💡 **Excelente!** Taxa de atendimento acima de 80%. Continue monitorando.")