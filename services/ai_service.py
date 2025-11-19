"""
AI Service - Native Stream Processing
"""
import os
import logging
import requests
from io import BytesIO
from openai import OpenAI
from services.database import get_database_service

logger = logging.getLogger(__name__)
db = get_database_service()

class AIService:
    def __init__(self):
        # NÃO inicializamos o cliente aqui para evitar erros de Build.
        # A chave será lida apenas no momento da execução (Runtime).
        pass

    def _get_client(self):
        """Lazy Load do Cliente OpenAI"""
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            logger.error("⚠️ OPENAI_API_KEY não configurada no ambiente.")
            return None
        return OpenAI(api_key=api_key)

    def process_call(self, call_sid: str, recording_url: str):
        """
        Pipeline Otimizado:
        Twilio MP3 (Stream) -> Memória (Bytes) -> OpenAI Whisper -> GPT-4o -> Banco
        """
        client = self._get_client()
        if not client or not recording_url:
            return False

        try:
            logger.info(f"🤖 Processando chamada {call_sid}...")

            # 1. Download do áudio em memória (Sem salvar no disco)
            # O Whisper aceita MP3, então não precisamos converter com FFmpeg!
            response = requests.get(recording_url)
            if response.status_code != 200:
                logger.error(f"❌ Erro download áudio: {response.status_code}")
                return False
            
            # Criar um objeto de arquivo em memória
            audio_file = BytesIO(response.content)
            audio_file.name = "audio.mp3" # Necessário para a OpenAI saber o formato

            # 2. Transcrição (Whisper)
            try:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1", 
                    file=audio_file, 
                    language="pt"
                )
                text = transcript.text
            except Exception as e:
                if "429" in str(e):
                    logger.warning("⚠️ Cota OpenAI excedida (429).")
                    # Aqui poderíamos implementar um fallback de texto simples se tivéssemos
                    return False
                raise e

            # 3. Análise de Inteligência (GPT-4o-mini)
            analysis = self._analyze_text(client, text)

            # 4. Persistência
            data = {
                'call_sid': call_sid,
                'transcription': text,
                'summary': analysis.get('summary'),
                'sentiment': analysis.get('sentiment'),
                'tags': analysis.get('tags', []),
                'created_at': 'now()'
            }
            db.client.table('ai_analysis').insert(data).execute()
            
            # Auto-tagging
            if analysis.get('tags'):
                db.update_call_tag(call_sid, analysis['tags'][0])

            logger.info(f"✅ Sucesso: {analysis.get('sentiment')}")
            return True

        except Exception as e:
            logger.error(f"❌ Erro no processamento IA: {e}")
            return False

    def _analyze_text(self, client, text):
        import json
        
        allowed_tags = [
            "Agendado", "Reagendado", "Cancelado", 
            "Retornar ligação", "Enviar info", 
            "Sem vaga", "Não Agendou", "Ligação errada"
        ]
        
        prompt = f"""
        Atue como auditor de clínica médica. Analise:
        "{text}"

        JSON Output Obrigatório:
        {{
            "summary": "Resumo em 1 frase do que o paciente queria.",
            "sentiment": "Positive" | "Neutral" | "Negative",
            "tags": ["Escolha 1 da lista: {allowed_tags}"]
        }}
        """
        
        try:
            res = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0
            )
            return json.loads(res.choices[0].message.content)
        except:
            return {"summary": "Erro na análise", "sentiment": "Neutral", "tags": []}