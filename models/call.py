"""
Modelos de dados para registros de chamadas.
Usa Pydantic para validação robusta e type safety.
"""
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Literal, Optional
from uuid import UUID, uuid4


CallStatus = Literal[
    'ringing', 
    'in-progress',
    'completed', 
    'no-answer', 
    'busy', 
    'failed',
    'canceled'
]


class CallRecord(BaseModel):
    """
    Modelo completo de uma chamada telefônica.
    Representa dados vindos do Twilio + metadados internos.
    """
    
    # Identifiers
    id: UUID = Field(default_factory=uuid4)
    call_sid: str = Field(..., min_length=34, max_length=34)
    
    # Phone Numbers
    from_number: str = Field(..., description="Número de quem ligou")
    to_number: str = Field(..., description="Número virtual Twilio")
    
    # Call Details
    status: CallStatus
    duration: int = Field(default=0, ge=0, description="Duração em segundos")
    
    # Campaign Attribution
    campaign_id: Optional[str] = Field(None, max_length=100)
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    @field_validator('from_number', 'to_number')
    @classmethod
    def validate_phone_format(cls, v: str) -> str:
        """Valida formato básico de telefone internacional."""
        cleaned = v.strip().replace(' ', '').replace('-', '')
        if not cleaned.startswith('+'):
            raise ValueError('Número deve começar com +')
        if len(cleaned) < 10 or len(cleaned) > 20:
            raise ValueError('Número com tamanho inválido')
        return cleaned
    
    class Config:
        json_schema_extra = {
            "example": {
                "call_sid": "CA1234567890abcdef1234567890abcd",
                "from_number": "+5561999998888",
                "to_number": "+551133334444",
                "status": "completed",
                "duration": 125,
                "campaign_id": "meta_ads_nov_2025"
            }
        }


class TwilioWebhookPayload(BaseModel):
    """
    Payload recebido do webhook Twilio.
    Mapeia exatamente os campos enviados pela API.
    """
    
    CallSid: str
    From: str
    To: str
    CallStatus: str
    CallDuration: Optional[str] = "0"
    
    # Query params
    campaign: Optional[str] = None
    
    def to_call_record(self) -> CallRecord:
        """Converte payload Twilio para nosso modelo interno."""
        return CallRecord(
            call_sid=self.CallSid,
            from_number=self.From,
            to_number=self.To,
            status=self._normalize_status(self.CallStatus),
            duration=int(self.CallDuration or 0),
            campaign_id=self.campaign
        )
    
    @staticmethod
    def _normalize_status(twilio_status: str) -> CallStatus:
        """Normaliza status do Twilio para nossos literais."""
        status_map = {
            'queued': 'ringing',
            'ringing': 'ringing',
            'in-progress': 'in-progress',
            'completed': 'completed',
            'busy': 'busy',
            'no-answer': 'no-answer',
            'failed': 'failed',
            'canceled': 'canceled'
        }
        normalized = status_map.get(twilio_status.lower(), 'failed')
        return normalized  # type: ignore


class CallMetrics(BaseModel):
    """Métricas agregadas de chamadas."""
    
    total_calls: int = 0
    unique_callers: int = 0
    completed_calls: int = 0
    missed_calls: int = 0
    avg_duration: float = 0.0
    answer_rate: float = 0.0
    
    def calculate_answer_rate(self) -> float:
        """Calcula taxa de atendimento."""
        if self.total_calls == 0:
            return 0.0
        return round((self.completed_calls / self.total_calls) * 100, 2)