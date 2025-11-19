"""
AI Service - Especialista em Clínicas
Responsável por processar áudio e gerar insights focados em agendamento médico.
"""
import os
import logging
import requests
import tempfile
import json
from openai import OpenAI
from services.database import get_database_service

logger = logging.getLogger(__name__)
db = get_database_service()

class AIService:
    def __init__(self):
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            logger.warning("⚠️ OPENAI_API_KEY not found. AI features disabled.")
            self.client = None
        else:
            self.client = OpenAI(api_key=api_key)

    def process_call(self, call_sid: str, recording_url: str):
        """
        Pipeline completo: Download -> Transcrição -> Análise Clínica -> Salvar DB
        """
        if not self.client or not recording_url:
            return False

        try:
            # 1. Baixar o Áudio
            logger.info(f"🤖 Starting Clinical AI analysis for {call_sid}")
            
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_audio:
                response = requests.get(recording_url, stream=True)
                if response.status_code != 200:
                    logger.error(f"❌ Failed to download audio: {response.status_code}")
                    return False
                
                for chunk in response.iter_content(chunk_size=1024):
                    temp_audio.write(chunk)
                temp_audio_path = temp_audio.name

            # 2. Transcrever (Whisper)
            with open(temp_audio_path, "rb") as audio_file:
                transcript_obj = self.client.audio.transcriptions.create(
                    model="whisper-1", 
                    file=audio_file,
                    language="pt"
                )
            transcription_text = transcript_obj.text
            
            # Limpeza
            os.unlink(temp_audio_path)

            # 3. Analisar (GPT-4o-mini com Contexto de Clínica)
            analysis = self._analyze_text_clinical(transcription_text)

            # 4. Salvar no Banco
            # Importante: Se a IA detectou uma tag, podemos atualizar a chamada principal também?
            # Por enquanto salvamos na tabela de análise.
            data = {
                'call_sid': call_sid,
                'transcription': transcription_text,
                'summary': analysis.get('summary'),
                'sentiment': analysis.get('sentiment'),
                'tags': analysis.get('tags', []),
                'created_at': datetime.utcnow().isoformat()
            }
            db.client.table('ai_analysis').insert(data).execute()
            
            # EXTRA: Se a IA tiver certeza absoluta da tag, atualizar a chamada principal
            # Isso faz o card mudar de cor sozinho no Kanban
            if analysis.get('tags'):
                primary_tag = analysis['tags'][0]
                db.update_call_tag(call_sid, primary_tag)
                logger.info(f"🤖 IA Auto-tagged call as: {primary_tag}")

            logger.info(f"✅ AI Analysis saved for {call_sid}")
            return True

        except Exception as e:
            logger.error(f"❌ AI Processing Error: {e}", exc_info=True)
            return False

    def _analyze_text_clinical(self, text):
        """
        Prompt Engenharia focado em Clínicas e Agendamentos.
        """
        
        # Lista estrita de tags do sistema (igual ao app.py)
        allowed_tags = [
            "Agendado", "Reagendado", "Cancelado", 
            "Retornar ligação", "Enviar info", 
            "Sem vaga", "Não Agendou", "Ligação errada"
        ]
        
        prompt = f"""
        Você é um Auditor de Qualidade e Atendimento especializado em CLÍNICAS MÉDICAS E DE SAÚDE.
        Sua tarefa é analisar a transcrição de uma chamada telefônica entre a recepção e um paciente.

        Transcrição:
        "{text}"

        Objetivos da Análise:
        1. RESUMO: Crie um resumo de 2 linhas focado na intenção do paciente (ex: queria marcar consulta com Dr. X) e no resultado (ex: marcou para dia Y).
        2. CLASSIFICAÇÃO (TAG): Escolha a tag que melhor descreve o desfecho, ESTRITAMENTE da lista abaixo.

        LISTA DE TAGS PERMITIDAS (Escolha apenas as que se aplicam):
        {json.dumps(allowed_tags, ensure_ascii=False)}

        Critérios para Tag:
        - "Agendado": Se confirmou data e hora para consulta/exame.
        - "Reagendado": Se o paciente já tinha horário e mudou para outro.
        - "Cancelado": Se o paciente ligou especificamente para cancelar e não remarcou.
        - "Sem vaga": Se o paciente queria um horário que não estava disponível.
        - "Não Agendou": Se o paciente apenas tirou dúvidas (preço, endereço) e desligou sem marcar.
        - "Enviar info": Se o paciente pediu tabela de preços ou localização por Zap/Email.

        3. SENTIMENTO: Como o paciente estava? (Positive, Neutral, Negative).
        Nota: Paciente com dor ou ansioso conta como 'Negative' se o atendimento não foi acolhedor.

        Retorne APENAS um JSON válido (sem markdown) neste formato:
        {{
            "summary": "texto do resumo...",
            "sentiment": "Neutral",
            "tags": ["Tag Escolhida"]
        }}
        """
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.0 # Temperatura zero para ser bem determinístico nas tags
            )
            
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"GPT Clinical Error: {e}")
            return {"summary": "Erro na análise IA", "sentiment": "Neutral", "tags": []}

# Import necessário para o update_call_tag extra
from datetime import datetime