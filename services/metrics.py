"""
Serviço de cálculo de métricas de chamadas.
Todas as regras de negócio e KPIs centralizados aqui.
"""
from typing import List, Dict, Any, Tuple
from datetime import datetime, timedelta
import pandas as pd
from collections import defaultdict
import logging

from models.call import CallMetrics


logger = logging.getLogger(__name__)


class MetricsService:
    """Serviço para calcular métricas e KPIs de chamadas."""
    
    @staticmethod
    def calculate_main_metrics(df: pd.DataFrame) -> CallMetrics:
        """
        Calcula métricas principais do dashboard.
        
        Args:
            df: DataFrame com chamadas
            
        Returns:
            Objeto com métricas calculadas
        """
        if df.empty:
            return CallMetrics()
        
        total_calls = len(df)
        unique_callers = df['from_number'].nunique()
        completed_calls = len(df[df['status'] == 'completed'])
        missed_calls = len(df[df['status'].isin(['no-answer', 'busy'])])
        
        # Média de duração apenas para chamadas completadas
        completed_df = df[df['status'] == 'completed']
        avg_duration = completed_df['duration'].mean() if not completed_df.empty else 0.0
        
        metrics = CallMetrics(
            total_calls=total_calls,
            unique_callers=unique_callers,
            completed_calls=completed_calls,
            missed_calls=missed_calls,
            avg_duration=round(avg_duration, 2)
        )
        
        metrics.answer_rate = metrics.calculate_answer_rate()
        
        return metrics
    
    @staticmethod
    def calculate_monthly_stats(
        df: pd.DataFrame, 
        year: int, 
        month: int
    ) -> Dict[str, Any]:
        """
        Calcula estatísticas de um mês específico.
        
        Args:
            df: DataFrame com chamadas
            year: Ano
            month: Mês (1-12)
            
        Returns:
            Dicionário com estatísticas do mês
        """
        # Filtrar mês específico
        df['created_at'] = pd.to_datetime(df['created_at'])
        mask = (df['created_at'].dt.year == year) & (df['created_at'].dt.month == month)
        month_df = df[mask]
        
        if month_df.empty:
            return {
                'total_calls': 0,
                'missed_rate': 0.0,
                'missed_returned_rate': 0.0,
                'incomplete_rate': 0.0,
                'incomplete_returned_rate': 0.0
            }
        
        total = len(month_df)
        missed = len(month_df[month_df['status'].isin(['no-answer', 'busy'])])
        incomplete = len(month_df[month_df['status'] == 'failed'])
        
        # Calcular ligações perdidas que retornaram
        # (número ligou novamente dentro de 24h)
        missed_returned = MetricsService._calculate_returned_calls(
            month_df[month_df['status'].isin(['no-answer', 'busy'])]
        )
        
        # Calcular ligações incompletas que retornaram
        incomplete_returned = MetricsService._calculate_returned_calls(
            month_df[month_df['status'] == 'failed']
        )
        
        return {
            'total_calls': total,
            'missed_rate': round((missed / total * 100), 2) if total > 0 else 0.0,
            'missed_returned_rate': round((missed_returned / missed * 100), 2) if missed > 0 else 0.0,
            'incomplete_rate': round((incomplete / total * 100), 2) if total > 0 else 0.0,
            'incomplete_returned_rate': round((incomplete_returned / incomplete * 100), 2) if incomplete > 0 else 0.0
        }
    
    @staticmethod
    def _calculate_returned_calls(failed_df: pd.DataFrame) -> int:
        """
        Calcula quantas ligações perdidas/incompletas retornaram.
        Considera retorno se mesmo número ligou novamente em até 24h.
        """
        if failed_df.empty:
            return 0
        
        returned_count = 0
        
        # Agrupar por número de origem
        for from_number, group in failed_df.groupby('from_number'):
            failed_times = sorted(group['created_at'].tolist())
            
            # Para cada falha, verificar se teve sucesso em 24h
            for fail_time in failed_times:
                # Buscar chamadas bem-sucedidas deste número após a falha
                success_mask = (
                    (failed_df['from_number'] == from_number) &
                    (failed_df['created_at'] > fail_time) &
                    (failed_df['created_at'] <= fail_time + timedelta(hours=24)) &
                    (failed_df['status'] == 'completed')
                )
                
                if success_mask.any():
                    returned_count += 1
                    break  # Contar apenas uma vez por número
        
        return returned_count
    
    @staticmethod
    def get_calls_by_campaign(df: pd.DataFrame) -> pd.DataFrame:
        """
        Agrupa chamadas por campanha com contadores.
        
        Returns:
            DataFrame com: campaign_id, total_calls, completed, missed
        """
        if df.empty:
            return pd.DataFrame(columns=['campaign_id', 'total_calls', 'completed', 'missed'])
        
        result = df.groupby('campaign_id').agg(
            total_calls=('call_sid', 'count'),
            completed=('status', lambda x: (x == 'completed').sum()),
            missed=('status', lambda x: (x.isin(['no-answer', 'busy'])).sum())
        ).reset_index()
        
        # Calcular taxa de atendimento
        result['answer_rate'] = (
            result['completed'] / result['total_calls'] * 100
        ).round(2)
        
        return result.sort_values('total_calls', ascending=False)
    
    @staticmethod
    def get_calls_by_state(df: pd.DataFrame) -> pd.DataFrame:
        """
        Extrai DDD do número e agrupa por estado brasileiro.
        
        Returns:
            DataFrame com: state, ddd, total_calls
        """
        if df.empty:
            return pd.DataFrame(columns=['state', 'ddd', 'total_calls'])
        
        # Mapeamento DDD -> Estado
        ddd_to_state = {
            '11': 'SP', '12': 'SP', '13': 'SP', '14': 'SP', '15': 'SP', 
            '16': 'SP', '17': 'SP', '18': 'SP', '19': 'SP',
            '21': 'RJ', '22': 'RJ', '24': 'RJ',
            '27': 'ES', '28': 'ES',
            '31': 'MG', '32': 'MG', '33': 'MG', '34': 'MG', '35': 'MG',
            '37': 'MG', '38': 'MG',
            '41': 'PR', '42': 'PR', '43': 'PR', '44': 'PR', '45': 'PR', '46': 'PR',
            '47': 'SC', '48': 'SC', '49': 'SC',
            '51': 'RS', '53': 'RS', '54': 'RS', '55': 'RS',
            '61': 'DF',
            '62': 'GO', '64': 'GO',
            '63': 'TO',
            '65': 'MT', '66': 'MT',
            '67': 'MS',
            '68': 'AC',
            '69': 'RO',
            '71': 'BA', '73': 'BA', '74': 'BA', '75': 'BA', '77': 'BA',
            '79': 'SE',
            '81': 'PE', '87': 'PE',
            '82': 'AL',
            '83': 'PB',
            '84': 'RN',
            '85': 'CE', '88': 'CE',
            '86': 'PI', '89': 'PI',
            '91': 'PA', '93': 'PA', '94': 'PA',
            '92': 'AM', '97': 'AM',
            '95': 'RR',
            '96': 'AP',
            '98': 'MA', '99': 'MA',
        }
        
        # Extrair DDD (2 dígitos após +55)
        df_copy = df.copy()
        df_copy['ddd'] = df_copy['from_number'].str.extract(r'\+55(\d{2})')
        df_copy['state'] = df_copy['ddd'].map(ddd_to_state)
        
        # Agrupar por estado
        result = df_copy.groupby(['state', 'ddd']).agg(
            total_calls=('call_sid', 'count')
        ).reset_index()
        
        # Remover registros sem estado (números internacionais)
        result = result[result['state'].notna()]
        
        return result.sort_values('total_calls', ascending=False)
    
    @staticmethod
    def get_top_missed_campaigns(df: pd.DataFrame, top_n: int = 5) -> pd.DataFrame:
        """
        Retorna campanhas com maior índice de ligações perdidas.
        
        Args:
            df: DataFrame com chamadas
            top_n: Quantidade de campanhas a retornar
            
        Returns:
            DataFrame com: campaign_id, missed_rate
        """
        if df.empty:
            return pd.DataFrame(columns=['campaign_id', 'missed_rate', 'total_calls'])
        
        campaign_stats = df.groupby('campaign_id').agg(
            total_calls=('call_sid', 'count'),
            missed=('status', lambda x: (x.isin(['no-answer', 'busy'])).sum())
        ).reset_index()
        
        campaign_stats['missed_rate'] = (
            campaign_stats['missed'] / campaign_stats['total_calls'] * 100
        ).round(2)
        
        # Filtrar campanhas com pelo menos 10 ligações (para ter significância)
        campaign_stats = campaign_stats[campaign_stats['total_calls'] >= 10]
        
        return campaign_stats.nlargest(top_n, 'missed_rate')
    
    @staticmethod
    def get_top_answered_campaigns(df: pd.DataFrame, top_n: int = 5) -> pd.DataFrame:
        """
        Retorna campanhas com maior índice de ligações atendidas.
        
        Args:
            df: DataFrame com chamadas
            top_n: Quantidade de campanhas a retornar
            
        Returns:
            DataFrame com: campaign_id, answer_rate
        """
        if df.empty:
            return pd.DataFrame(columns=['campaign_id', 'answer_rate', 'total_calls'])
        
        campaign_stats = df.groupby('campaign_id').agg(
            total_calls=('call_sid', 'count'),
            completed=('status', lambda x: (x == 'completed').sum())
        ).reset_index()
        
        campaign_stats['answer_rate'] = (
            campaign_stats['completed'] / campaign_stats['total_calls'] * 100
        ).round(2)
        
        # Filtrar campanhas com pelo menos 10 ligações
        campaign_stats = campaign_stats[campaign_stats['total_calls'] >= 10]
        
        return campaign_stats.nlargest(top_n, 'answer_rate')
    
    @staticmethod
    def get_calls_timeline(
        df: pd.DataFrame, 
        interval: str = 'daily'
    ) -> pd.DataFrame:
        """
        Agrupa chamadas por intervalo temporal.
        
        Args:
            df: DataFrame com chamadas
            interval: 'daily', 'hourly', 'weekly'
            
        Returns:
            DataFrame com série temporal
        """
        if df.empty:
            return pd.DataFrame(columns=['date', 'status', 'count'])
        
        df_copy = df.copy()
        df_copy['created_at'] = pd.to_datetime(df_copy['created_at'])
        
        # Definir frequência de agrupamento
        freq_map = {
            'hourly': 'H',
            'daily': 'D',
            'weekly': 'W'
        }
        freq = freq_map.get(interval, 'D')
        
        # Agrupar por data e status
        df_copy['date'] = df_copy['created_at'].dt.floor(freq)
        
        result = df_copy.groupby(['date', 'status']).size().reset_index(name='count')
        
        return result.sort_values('date')
    
    @staticmethod
    def format_duration(seconds: float) -> str:
        """
        Formata duração em segundos para MM:SS.
        
        Args:
            seconds: Duração em segundos
            
        Returns:
            String formatada (ex: "02:35")
        """
        if seconds <= 0:
            return "00:00"
        
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        
        return f"{minutes:02d}:{secs:02d}"