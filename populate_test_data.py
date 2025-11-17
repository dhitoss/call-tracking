"""
Script para popular o banco com dados de teste realistas.
Simula 3 meses de operação com padrões realistas.
"""
from datetime import datetime, timedelta
import random
import string
from services.database import get_database_service
from models.call import CallRecord
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Configurações realistas
CAMPAIGNS = [
    'meta_ads_saude_nov',
    'google_ads_clinica_geral', 
    'meta_ads_estetica_nov',
    'google_ads_odonto',
    'remarketing_pacientes',
    'organic_direct'
]

DDDS_BR = [
    '11', '21', '61', '85', '71',  # Capitais principais
    '51', '41', '31', '47', '81',  # Outras capitais
    '13', '19', '27', '62', '84'   # Cidades médias
]

# Padrões realistas de comportamento
STATUS_WEIGHTS = {
    'completed': 0.65,      # 65% atendidas
    'no-answer': 0.20,      # 20% não atendeu
    'busy': 0.08,           # 8% ocupado
    'failed': 0.07          # 7% falhou
}

# Distribuição de duração (em segundos) para chamadas completadas
DURATION_PATTERNS = {
    'quick': (10, 60, 0.15),      # 15% são rápidas (10-60s)
    'normal': (60, 300, 0.60),    # 60% normais (1-5min)
    'long': (300, 900, 0.20),     # 20% longas (5-15min)
    'very_long': (900, 1800, 0.05) # 5% muito longas (15-30min)
}

# Horários de pico (distribuição realista)
HOUR_WEIGHTS = {
    0: 0.1, 1: 0.1, 2: 0.1, 3: 0.1, 4: 0.1, 5: 0.2,
    6: 0.5, 7: 1.0, 8: 2.5, 9: 3.5, 10: 3.0, 11: 2.5,
    12: 1.5, 13: 2.0, 14: 3.0, 15: 3.5, 16: 3.0, 17: 2.5,
    18: 2.0, 19: 1.5, 20: 1.0, 21: 0.8, 22: 0.5, 23: 0.3
}


def generate_call_sid() -> str:
    """
    Gera um call_sid válido no formato Twilio (34 caracteres).
    Formato: CA + 32 caracteres hexadecimais
    """
    hex_chars = string.hexdigits[:-6]  # 0-9, a-f (sem uppercase)
    random_part = ''.join(random.choice(hex_chars) for _ in range(32))
    return f"CA{random_part}"


def generate_phone_number(ddd: str) -> str:
    """Gera número de telefone brasileiro."""
    prefix = random.choice(['9', '8'])  # Celular ou fixo
    number = ''.join([str(random.randint(0, 9)) for _ in range(8)])
    return f"+55{ddd}{prefix}{number}"


def generate_call_duration() -> int:
    """Gera duração realista de chamada."""
    # Escolher padrão baseado em probabilidade
    rand = random.random()
    cumulative = 0
    
    for pattern, (min_dur, max_dur, weight) in DURATION_PATTERNS.items():
        cumulative += weight
        if rand <= cumulative:
            return random.randint(min_dur, max_dur)
    
    return random.randint(60, 300)  # Fallback


def generate_call_status() -> str:
    """Gera status baseado em distribuição realista."""
    rand = random.random()
    cumulative = 0
    
    for status, weight in STATUS_WEIGHTS.items():
        cumulative += weight
        if rand <= cumulative:
            return status
    
    return 'completed'  # Fallback


def generate_timestamp(days_ago: int) -> datetime:
    """Gera timestamp realista considerando horários de pico."""
    date = datetime.now() - timedelta(days=days_ago)
    
    # Escolher hora baseado em distribuição
    hours = list(HOUR_WEIGHTS.keys())
    weights = list(HOUR_WEIGHTS.values())
    hour = random.choices(hours, weights=weights)[0]
    
    minute = random.randint(0, 59)
    second = random.randint(0, 59)
    
    return date.replace(hour=hour, minute=minute, second=second, microsecond=0)


def generate_realistic_calls(total_calls: int = 500) -> list[CallRecord]:
    """
    Gera chamadas com padrões realistas.
    
    Args:
        total_calls: Total de chamadas a gerar
        
    Returns:
        Lista de CallRecords
    """
    calls = []
    
    # Distribuir chamadas nos últimos 90 dias
    for i in range(total_calls):
        days_ago = random.randint(0, 90)
        campaign = random.choice(CAMPAIGNS)
        ddd = random.choice(DDDS_BR)
        status = generate_call_status()
        
        # Duração só para chamadas completadas
        duration = generate_call_duration() if status == 'completed' else 0
        
        call = CallRecord(
            call_sid=generate_call_sid(),  # CORRIGIDO: usando função que gera 34 chars
            from_number=generate_phone_number(ddd),
            to_number="+551133334444",  # Número fixo da empresa
            status=status,
            duration=duration,
            campaign_id=campaign,
            created_at=generate_timestamp(days_ago)
        )
        
        calls.append(call)
        
        if (i + 1) % 50 == 0:
            logger.info(f"Geradas {i + 1}/{total_calls} chamadas...")
    
    return calls


def insert_calls_batch(calls: list[CallRecord], batch_size: int = 50):
    """
    Insere chamadas em lotes para performance.
    
    Args:
        calls: Lista de chamadas
        batch_size: Tamanho do lote
    """
    db = get_database_service()
    
    total = len(calls)
    for i in range(0, total, batch_size):
        batch = calls[i:i + batch_size]
        
        for call in batch:
            try:
                db.insert_call(call)
            except Exception as e:
                logger.error(f"Erro ao inserir {call.call_sid}: {str(e)}")
        
        logger.info(f"✅ Inseridas {min(i + batch_size, total)}/{total} chamadas")


def generate_and_populate(total_calls: int = 500):
    """
    Função principal para gerar e popular dados.
    
    Args:
        total_calls: Total de chamadas a gerar
    """
    print("=" * 60)
    print("  📞 POPULANDO BANCO COM DADOS DE TESTE")
    print("=" * 60)
    print()
    
    # Verificar conexão
    print("🔌 Verificando conexão com banco...")
    db = get_database_service()
    if not db.health_check():
        print("❌ Erro ao conectar com banco. Verifique suas credenciais.")
        return False
    
    print("✅ Conexão estabelecida")
    print()
    
    # Gerar chamadas
    print(f"🎲 Gerando {total_calls} chamadas realistas...")
    calls = generate_realistic_calls(total_calls)
    print(f"✅ {len(calls)} chamadas geradas")
    print()
    
    # Inserir no banco
    print("💾 Inserindo no banco de dados...")
    insert_calls_batch(calls)
    print()
    
    # Estatísticas
    print("=" * 60)
    print("  📊 ESTATÍSTICAS DOS DADOS GERADOS")
    print("=" * 60)
    
    status_count = {}
    campaign_count = {}
    
    for call in calls:
        status_count[call.status] = status_count.get(call.status, 0) + 1
        campaign_count[call.campaign_id] = campaign_count.get(call.campaign_id, 0) + 1
    
    print("\n📈 Por Status:")
    for status, count in sorted(status_count.items(), key=lambda x: x[1], reverse=True):
        pct = (count / len(calls)) * 100
        print(f"   {status:15} {count:4} ({pct:5.1f}%)")
    
    print("\n📊 Por Campanha:")
    for campaign, count in sorted(campaign_count.items(), key=lambda x: x[1], reverse=True):
        pct = (count / len(calls)) * 100
        print(f"   {campaign:30} {count:4} ({pct:5.1f}%)")
    
    print()
    print("=" * 60)
    print("  🎉 DADOS INSERIDOS COM SUCESSO!")
    print("=" * 60)
    print()
    print("💡 Agora você pode:")
    print("   1. Testar o webhook: python webhook.py")
    print("   2. Ver o dashboard: streamlit run app.py")
    print("   3. Executar testes: pytest tests/ -v")
    print()
    
    return True


if __name__ == "__main__":
    import sys
    
    # Permitir customizar quantidade via argumento
    total = 500
    if len(sys.argv) > 1:
        try:
            total = int(sys.argv[1])
        except ValueError:
            print("⚠️  Argumento inválido. Usando padrão de 500 chamadas.")
    
    success = generate_and_populate(total)
    
    if not success:
        sys.exit(1)