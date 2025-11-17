"""
Componentes de visualização usando Plotly.
Gráficos profissionais e interativos para o dashboard.
"""
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from typing import Optional


# Paleta de cores consistente
COLORS = {
    'primary': '#3b82f6',      # azul
    'success': '#10b981',      # verde
    'warning': '#f59e0b',      # laranja
    'danger': '#ef4444',       # vermelho
    'info': '#06b6d4',         # cyan
    'purple': '#8b5cf6',       # roxo
    'pink': '#ec4899',         # rosa
}

STATUS_COLORS = {
    'completed': COLORS['success'],
    'no-answer': COLORS['warning'],
    'busy': COLORS['warning'],
    'failed': COLORS['danger'],
    'ringing': COLORS['info'],
    'in-progress': COLORS['primary']
}

# Tema padrão para todos os gráficos
DEFAULT_LAYOUT = {
    'template': 'plotly_white',
    'hovermode': 'closest',
    'showlegend': True,
    'height': 400,
    'margin': dict(l=20, r=20, t=40, b=20)
}


def create_campaign_bar_chart(df: pd.DataFrame) -> go.Figure:
    """
    Gráfico de barras horizontais: Ligações por Campanha.
    
    Args:
        df: DataFrame com colunas: campaign_id, total_calls, completed, missed
        
    Returns:
        Figura Plotly
    """
    if df.empty:
        return _create_empty_chart("Nenhum dado disponível")
    
    # Preparar dados
    df_sorted = df.sort_values('total_calls', ascending=True)
    
    # Criar figura com barras empilhadas
    fig = go.Figure()
    
    # Barra de chamadas atendidas
    fig.add_trace(go.Bar(
        name='Atendidas',
        y=df_sorted['campaign_id'],
        x=df_sorted['completed'],
        orientation='h',
        marker=dict(color=STATUS_COLORS['completed']),
        hovertemplate='<b>%{y}</b><br>Atendidas: %{x}<extra></extra>'
    ))
    
    # Barra de chamadas perdidas
    fig.add_trace(go.Bar(
        name='Perdidas',
        y=df_sorted['campaign_id'],
        x=df_sorted['missed'],
        orientation='h',
        marker=dict(color=STATUS_COLORS['no-answer']),
        hovertemplate='<b>%{y}</b><br>Perdidas: %{x}<extra></extra>'
    ))
    
    # Layout
    fig.update_layout(
        title='📊 Ligações por Campanha',
        xaxis_title='Número de Ligações',
        yaxis_title='Campanha',
        barmode='stack',
        **DEFAULT_LAYOUT
    )
    
    return fig


def create_state_pie_chart(df: pd.DataFrame) -> go.Figure:
    """
    Gráfico de pizza: Ligações por Estado.
    
    Args:
        df: DataFrame com colunas: state, total_calls
        
    Returns:
        Figura Plotly
    """
    if df.empty:
        return _create_empty_chart("Nenhum dado disponível")
    
    # Pegar top 10 estados (agrupar resto em "Outros")
    df_sorted = df.sort_values('total_calls', ascending=False)
    
    if len(df_sorted) > 10:
        top_10 = df_sorted.head(10)
        others_sum = df_sorted.iloc[10:]['total_calls'].sum()
        
        if others_sum > 0:
            others_row = pd.DataFrame({
                'state': ['Outros'],
                'total_calls': [others_sum]
            })
            df_plot = pd.concat([top_10, others_row], ignore_index=True)
        else:
            df_plot = top_10
    else:
        df_plot = df_sorted
    
    # Criar gráfico de pizza
    fig = go.Figure(data=[go.Pie(
        labels=df_plot['state'],
        values=df_plot['total_calls'],
        hole=0.4,  # Donut chart
        marker=dict(
            colors=px.colors.qualitative.Set3[:len(df_plot)]
        ),
        hovertemplate='<b>%{label}</b><br>Ligações: %{value}<br>%{percent}<extra></extra>',
        textinfo='label+percent',
        textposition='auto'
    )])
    
    fig.update_layout(
        title='🗺️ Ligações por Estado',
        **DEFAULT_LAYOUT
    )
    
    return fig


def create_top_missed_chart(df: pd.DataFrame) -> go.Figure:
    """
    Gráfico de barras: Top 5 campanhas com mais ligações perdidas.
    
    Args:
        df: DataFrame com colunas: campaign_id, missed_rate, total_calls
        
    Returns:
        Figura Plotly
    """
    if df.empty:
        return _create_empty_chart("Dados insuficientes (mínimo 10 ligações por campanha)")
    
    # Ordenar por taxa de perda
    df_sorted = df.sort_values('missed_rate', ascending=False).head(5)
    
    # Criar gráfico de barras
    fig = go.Figure(data=[
        go.Bar(
            x=df_sorted['campaign_id'],
            y=df_sorted['missed_rate'],
            marker=dict(
                color=df_sorted['missed_rate'],
                colorscale=[
                    [0, COLORS['warning']],
                    [1, COLORS['danger']]
                ],
                showscale=False
            ),
            text=[f"{val:.1f}%" for val in df_sorted['missed_rate']],
            textposition='outside',
            hovertemplate='<b>%{x}</b><br>Taxa de Perda: %{y:.2f}%<br>Total: %{customdata} ligações<extra></extra>',
            customdata=df_sorted['total_calls']
        )
    ])
    
    fig.update_layout(
        title='📉 Top 5 - Maior Índice de Ligações Perdidas',
        xaxis_title='Campanha',
        yaxis_title='Taxa de Perda (%)',
        yaxis=dict(range=[0, min(100, df_sorted['missed_rate'].max() * 1.1)]),
        **DEFAULT_LAYOUT
    )
    
    return fig


def create_top_answered_chart(df: pd.DataFrame) -> go.Figure:
    """
    Gráfico de barras: Top 5 campanhas com mais ligações atendidas.
    
    Args:
        df: DataFrame com colunas: campaign_id, answer_rate, total_calls
        
    Returns:
        Figura Plotly
    """
    if df.empty:
        return _create_empty_chart("Dados insuficientes (mínimo 10 ligações por campanha)")
    
    # Ordenar por taxa de atendimento
    df_sorted = df.sort_values('answer_rate', ascending=False).head(5)
    
    # Criar gráfico de barras
    fig = go.Figure(data=[
        go.Bar(
            x=df_sorted['campaign_id'],
            y=df_sorted['answer_rate'],
            marker=dict(
                color=df_sorted['answer_rate'],
                colorscale=[
                    [0, COLORS['warning']],
                    [1, COLORS['success']]
                ],
                showscale=False
            ),
            text=[f"{val:.1f}%" for val in df_sorted['answer_rate']],
            textposition='outside',
            hovertemplate='<b>%{x}</b><br>Taxa de Atendimento: %{y:.2f}%<br>Total: %{customdata} ligações<extra></extra>',
            customdata=df_sorted['total_calls']
        )
    ])
    
    fig.update_layout(
        title='📈 Top 5 - Maior Índice de Ligações Atendidas',
        xaxis_title='Campanha',
        yaxis_title='Taxa de Atendimento (%)',
        yaxis=dict(range=[0, 100]),
        **DEFAULT_LAYOUT
    )
    
    return fig


def create_timeline_chart(df: pd.DataFrame, interval: str = 'daily') -> go.Figure:
    """
    Gráfico de linha: Ligações por tipo ao longo do tempo.
    
    Args:
        df: DataFrame com colunas: date, status, count
        interval: Intervalo temporal ('daily', 'hourly', 'weekly')
        
    Returns:
        Figura Plotly
    """
    if df.empty:
        return _create_empty_chart("Nenhum dado disponível")
    
    # Criar figura
    fig = go.Figure()
    
    # Mapear status para labels em português
    status_labels = {
        'completed': 'Atendidas',
        'no-answer': 'Não Atendidas',
        'busy': 'Ocupado',
        'failed': 'Falhou',
        'ringing': 'Tocando',
        'in-progress': 'Em Andamento'
    }
    
    # Adicionar linha para cada status
    for status in df['status'].unique():
        df_status = df[df['status'] == status].sort_values('date')
        
        fig.add_trace(go.Scatter(
            x=df_status['date'],
            y=df_status['count'],
            name=status_labels.get(status, status),
            mode='lines+markers',
            line=dict(
                color=STATUS_COLORS.get(status, COLORS['primary']),
                width=2
            ),
            marker=dict(size=6),
            hovertemplate='<b>%{fullData.name}</b><br>%{x|%d/%m/%Y}<br>Ligações: %{y}<extra></extra>'
        ))
    
    # Título dinâmico baseado no intervalo
    interval_labels = {
        'hourly': 'por Hora',
        'daily': 'por Dia',
        'weekly': 'por Semana'
    }
    title = f'📊 Ligações por Tipo {interval_labels.get(interval, "")}'
    
    timeline_layout = DEFAULT_LAYOUT.copy()
    timeline_layout['hovermode'] = 'x unified'  # Sobrescrever hovermode

    fig.update_layout(
        title=title,
        xaxis_title='Data',
        yaxis_title='Número de Ligações',
        **timeline_layout
    )
    return fig


def _create_empty_chart(message: str) -> go.Figure:
    """
    Cria gráfico vazio com mensagem.
    
    Args:
        message: Mensagem a exibir
        
    Returns:
        Figura Plotly vazia
    """
    fig = go.Figure()
    
    fig.add_annotation(
        text=message,
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        showarrow=False,
        font=dict(size=16, color='gray')
    )
    
    fig.update_layout(
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        **DEFAULT_LAYOUT
    )
    
    return fig