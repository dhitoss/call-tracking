"""
AI Service - Híbrido (OpenAI + Fallback Gratuito)
Tenta usar GPT-4o. Se falhar (cota/erro), usa GoogleSpeech + TextBlob (Grátis).
"""
import os
import logging
import requests
import tempfile
import json
from openai import OpenAI, RateLimitError, APIError
from services.database import get_database_service

# Bibliotecas Gratuitas (Fallback)
import speech_recognition as sr
from pydub import AudioSegment
from textblob import TextBlob

logger = logging.getLogger(__name__)
db = get_database_service()

class AIService:
    def __init__(self):
        api_key = os.getenv('OPENAI_API_KEY')
        self.client = OpenAI(api_key=api_key) if api_key else None

    def process_call(self, call_sid: str, recording_url: str):
        """Pipeline principal: Tenta OpenAI -> Falha -> Tenta Gratuito"""
        if not recording_url: return False

        # 1. Download do Áudio
        temp_mp3 = self._download_audio(recording_url)
        if not temp_mp3: return False

        try:
            # TENTATIVA 1: OPENAI (Premium)
            if not self.client: raise Exception("No OpenAI Key")
            
            logger.info(f"🤖 Tentando OpenAI para {call_sid}...")
            result = self._process_openai(temp_mp3)
            
        except (RateLimitError, APIError, Exception) as e:
            # TENTATIVA 2: FALLBACK (Gratuito)
            logger.warning(f"⚠️ OpenAI falhou ({str(e)}). Usando modo GRATUITO.")
            result = self._process_free_tier(temp_mp3)

        finally:
            # Limpeza
            if os.path.exists(temp_mp3): os.unlink(temp_mp3)

        # Salvar no Banco
        if result:
            self._save_result(call_sid, result)
            return True
        return False

    def _download_audio(self, url):
        try:
            response = requests.get(url, stream=True)
            if response.status_code == 200:
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                    for chunk in response.iter_content(1024): f.write(chunk)
                    return f.name
        except Exception as e:
            logger.error(f"Download error: {e}")
        return None

    def _process_openai(self, audio_path):
        # Transcrição Whisper
        with open(audio_path, "rb") as f:
            transcript = self.client.audio.transcriptions.create(
                model="whisper-1", file=f, language="pt"
            )
        text = transcript.text
        
        # Análise GPT-4o
        analysis = self._analyze_text_gpt(text)
        return {
            'text': text,
            'summary': analysis.get('summary'),
            'sentiment': analysis.get('sentiment'),
            'tags': analysis.get('tags', [])
        }

    def _process_free_tier(self, mp3_path):
        """
        Modo Gratuito:
        1. Converte MP3 -> WAV (Pydub)
        2. Transcreve (Google Speech API Public)
        3. Analisa (TextBlob + Regras)
        """
        wav_path = mp3_path.replace(".mp3", ".wav")
        try:
            # 1. Conversão
            audio = AudioSegment.from_mp3(mp3_path)
            audio.export(wav_path, format="wav")
            
            # 2. Transcrição
            recognizer = sr.Recognizer()
            with sr.AudioFile(wav_path) as source:
                audio_data = recognizer.record(source)
                # Google Speech (API Gratuita)
                text = recognizer.recognize_google(audio_data, language="pt-BR")
            
            # 3. Análise Local
            analysis = self._analyze_text_free(text)
            
            return {
                'text': text,
                'summary': "Resumo indisponível no modo gratuito (apenas transcrição).",
                'sentiment': analysis['sentiment'],
                'tags': analysis['tags']
            }
            
        except Exception as e:
            logger.error(f"Free tier error: {e}")
            return None
        finally:
            if os.path.exists(wav_path): os.unlink(wav_path)

    def _analyze_text_gpt(self, text):
        # (Mantém sua lógica original do Prompt Clínico aqui)
        allowed_tags = ["Agendado", "Reagendado", "Cancelado", "Retornar ligação", "Enviar info", "Sem vaga", "Não Agendou", "Ligação errada"]
        prompt = f"""
        Atue como auditor de clínica médica. Analise: "{text}"
        Retorne JSON:
        {{ "summary": "resumo curto", "sentiment": "Positive/Neutral/Negative", "tags": ["tag da lista"] }}
        Lista Tags: {json.dumps(allowed_tags)}
        """
        try:
            res = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0
            )
            return json.loads(res.choices[0].message.content)
        except: return {}

    def _analyze_text_free(self, text):
        """Análise baseada em palavras-chave (Heurística)"""
        text_lower = text.lower()
        tags = []
        sentiment = "Neutral"
        
        # 1. Sentimento via TextBlob (Básico)
        # TextBlob pt funciona melhor se traduzir, mas vamos usar nativo aproximado ou palavras chave
        blob = TextBlob(text)
        if blob.sentiment.polarity > 0.1: sentiment = "Positive"
        elif blob.sentiment.polarity < -0.1: sentiment = "Negative"
        
        # 2. Tags via Palavras-Chave (Regra de Negócio)
        if any(x in text_lower for x in ['marcar', 'agendar', 'confirmado', 'dia', 'horas']):
            tags.append("Agendado")
        elif any(x in text_lower for x in ['cancelar', 'não posso', 'desmarcar']):
            tags.append("Cancelado")
        elif any(x in text_lower for x in ['preço', 'valor', 'quanto', 'informação', 'endereço']):
            tags.append("Enviar info")
        elif any(x in text_lower for x in ['não tem', 'lotado', 'sem vaga', 'cheio']):
            tags.append("Sem vaga")
        else:
            tags.append("Retornar ligação") # Default seguro

        return {"sentiment": sentiment, "tags": tags}

    def _save_result(self, call_sid, data):
        db_data = {
            'call_sid': call_sid,
            'transcription': data['text'],
            'summary': data['summary'],
            'sentiment': data['sentiment'],
            'tags': data['tags'],
            'created_at': datetime.utcnow().isoformat()
        }
        db.client.table('ai_analysis').insert(db_data).execute()
        
        # Auto-Tagging no Kanban
        if data['tags']:
            db.update_call_tag(call_sid, data['tags'][0])

from datetime import datetime