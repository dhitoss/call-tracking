"""
Configuração global para testes pytest.
"""
import pytest
from datetime import datetime, timedelta
import pandas as pd
import string
import random
from models.call import CallRecord


def generate_call_sid() -> str:
    """Gera call_sid válido para testes (34 caracteres)."""
    hex_chars = string.hexdigits[:-6]  # 0-9, a-f
    random_part = ''.join(random.choice(hex_chars) for _ in range(32))
    return f"CA{random_part}"


@pytest.fixture
def sample_call():
    """Fixture com uma chamada de exemplo."""
    return CallRecord(
        call_sid="CA1234567890abcdef1234567890abcd",  # Exatamente 34 chars
        from_number="+5561999998888",
        to_number="+551133334444",
        status="completed",
        duration=125,
        campaign_id="meta_ads_test",
        created_at=datetime.now()
    )


@pytest.fixture
def sample_calls_list():
    """Fixture com lista de chamadas para testes."""
    base_time = datetime.now()
    
    calls = []
    statuses = ['completed', 'no-answer', 'busy', 'failed']
    campaigns = ['campaign_a', 'campaign_b', 'campaign_c']
    
    for i in range(20):
        call = CallRecord(
            call_sid=generate_call_sid(),  # CORRIGIDO
            from_number=f"+556199999{i:04d}",
            to_number="+551133334444",
            status=statuses[i % len(statuses)],
            duration=60 * (i + 1) if statuses[i % len(statuses)] == 'completed' else 0,
            campaign_id=campaigns[i % len(campaigns)],
            created_at=base_time - timedelta(hours=i)
        )
        calls.append(call)
    
    return calls


@pytest.fixture
def sample_dataframe(sample_calls_list):
    """Fixture com DataFrame de chamadas."""
    data = []
    for call in sample_calls_list:
        data.append({
            'call_sid': call.call_sid,
            'from_number': call.from_number,
            'to_number': call.to_number,
            'status': call.status,
            'duration': call.duration,
            'campaign_id': call.campaign_id,
            'created_at': call.created_at
        })
    
    return pd.DataFrame(data)