"""Módulo Voice Service para Vexx-AI: integração bidirecional com a API Kokoro + Whisper.

Conecta ao Hugging Face Space (euefrai/api-voz-kokoro) ou instância local/configurada
via HTTP REST e WebSockets para transcrição instantânea (STT), síntese de fala (TTS),
detecção de voz (VAD) e isolamento de locutor com SpeechBrain.
"""
import asyncio
import base64
import io
import json
import logging
import os
import re
from typing import AsyncGenerator, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger("vexx-voice-service")

# URLs padrão da API de Voz no Hugging Face
DEFAULT_VOICE_SPACE_ID = "euefrai/api-voz-kokoro"
DEFAULT_VOICE_HTTP_URL = "https://euefrai-api-voz-kokoro.hf.space"
DEFAULT_TIMEOUT_S = 30.0

def get_voice_api_url() -> str:
    """Retorna a URL base HTTP da API de Voz configurada."""
    url = (os.environ.get("VEXX_VOICE_API_URL") or DEFAULT_VOICE_HTTP_URL).strip()
    return url.rstrip("/")

def get_voice_ws_url() -> str:
    """Retorna a URL WebSocket correspondente à API de Voz."""
    http_url = get_voice_api_url()
    if http_url.startswith("https://"):
        return http_url.replace("https://", "wss://") + "/ws/conversacao"
    elif http_url.startswith("http://"):
        return http_url.replace("http://", "ws://") + "/ws/conversacao"
    return f"wss://{http_url.lstrip('/')}/ws/conversacao"

def limpar_texto_para_fala(texto: str) -> str:
    """Sanitiza formatações de markdown, links e códigos para fala natural."""
    if not texto:
        return ""
    # Remove blocos de código
    texto = re.sub(r"```[\s\S]*?```", " código omitido na fala. ", texto)
    # Remove código inline
    texto = re.sub(r"`.*?`", "", texto)
    # Converte links markdown [texto](url) em apenas 'texto'
    texto = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", texto)
    # Remove URLs soltas
    texto = re.sub(r"https?://\S+", "", texto)
    # Remove asteriscos, hashtags, tils e pipes
    texto = re.sub(r"[*#_~|>]+", " ", texto)
    # Normaliza espaços
    return re.sub(r"\s+", " ", texto).strip()

class SentenceAccumulator:
    """Acumula deltas de texto do LLM em tempo real e extrai orações completas para o TTS."""
    def __init__(self, min_chars: int = 25, max_chars: int = 160):
        self.min_chars = min_chars
        self.max_chars = max_chars
        self.buffer = ""
        # Delimitadores primários de fim de oração
        self.delimiters = re.compile(r"([.!?;\n]+)")

    def feed(self, delta: str) -> List[str]:
        """Adiciona um trecho de texto e retorna frases completas prontas para síntese."""
        self.buffer += delta
        prontas = []

        while True:
            match = self.delimiters.search(self.buffer)
            if not match:
                # Se acumulou muito texto sem pontuação, tenta quebrar em vírgula ou espaço
                if len(self.buffer) >= self.max_chars:
                    virgula_idx = self.buffer.rfind(",", 0, self.max_chars)
                    if virgula_idx >= self.min_chars:
                        trecho = self.buffer[:virgula_idx].strip()
                        self.buffer = self.buffer[virgula_idx + 1:].lstrip()
                        limpo = limpar_texto_para_fala(trecho)
                        if limpo:
                            prontas.append(limpo)
                        continue
                    # Se nem vírgula achou, quebra no último espaço
                    espaco_idx = self.buffer.rfind(" ", 0, self.max_chars)
                    if espaco_idx >= self.min_chars:
                        trecho = self.buffer[:espaco_idx].strip()
                        self.buffer = self.buffer[espaco_idx + 1:].lstrip()
                        limpo = limpar_texto_para_fala(trecho)
                        if limpo:
                            prontas.append(limpo)
                        continue
                break

            fim = match.end()
            candidata = self.buffer[:fim].strip()
            # Se a candidata for muito curta (ex: 'Sr.'), não quebra ainda
            if len(candidata) < 5 and not match.group(1).startswith("\n"):
                break

            self.buffer = self.buffer[fim:].lstrip()
            limpo = limpar_texto_para_fala(candidata)
            if limpo:
                prontas.append(limpo)

        return prontas

    def flush(self) -> List[str]:
        """Esvazia o buffer remanescente ao final da geração do LLM."""
        sobra = self.buffer.strip()
        self.buffer = ""
        limpo = limpar_texto_para_fala(sobra)
        return [limpo] if limpo else []

async def health_check(timeout: float = 5.0) -> Dict:
    """Verifica se a API de Voz no Hugging Face está acessível."""
    url = f"{get_voice_api_url()}/health"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return resp.json()
            return {"status": "error", "code": resp.status_code}
    except Exception as e:
        return {"status": "unreachable", "error": str(e)}

async def transcribe_audio_bytes(
    audio_bytes: bytes,
    language: str = "pt",
    filename: str = "input.wav",
    timeout: float = DEFAULT_TIMEOUT_S,
) -> str:
    """Envia áudio binário para a API de Voz (Faster-Whisper STT)."""
    if not audio_bytes:
        return ""
    url = f"{get_voice_api_url()}/stt"
    files = {"file": (filename, audio_bytes, "audio/wav")}
    data = {"language": language}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, files=files, data=data)
            if resp.status_code == 200:
                resultado = resp.json()
                return resultado.get("text", "").strip()
            logger.warning(f"STT retornou código {resp.status_code}: {resp.text}")
            return ""
    except Exception as e:
        logger.error(f"Erro na requisição STT para a API de Voz: {e}")
        return ""

async def synthesize_speech_wav(
    text: str,
    voice: str = "pm_alex",
    speed: float = 1.0,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> bytes:
    """Sintetiza texto em áudio WAV via API Kokoro."""
    texto_limpo = limpar_texto_para_fala(text)
    if not texto_limpo:
        return b""
    url = f"{get_voice_api_url()}/tts"
    payload = {"text": texto_limpo, "voice": voice, "speed": speed}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                return resp.content
            logger.warning(f"TTS retornou código {resp.status_code}: {resp.text}")
            return b""
    except Exception as e:
        logger.error(f"Erro na requisição TTS para a API de Voz: {e}")
        return b""

async def enroll_speaker_profile(
    audio_bytes: bytes,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> Optional[List[float]]:
    """Envia amostra de áudio para calibração de locutor (SpeechBrain)."""
    if not audio_bytes:
        return None
    url = f"{get_voice_api_url()}/speaker/enroll"
    files = {"file": ("enroll.wav", audio_bytes, "audio/wav")}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, files=files)
            if resp.status_code == 200:
                return resp.json().get("embedding")
            return None
    except Exception as e:
        logger.error(f"Erro ao calibrar locutor: {e}")
        return None

async def verify_speaker_audio(
    audio_bytes: bytes,
    reference_embedding: List[float],
    timeout: float = DEFAULT_TIMEOUT_S,
) -> Dict:
    """Verifica se o áudio recebido pertence ao locutor calibrado."""
    if not audio_bytes or not reference_embedding:
        return {"match": True, "similarity": 1.0}
    url = f"{get_voice_api_url()}/speaker/verify"
    payload = {
        "reference_embedding": reference_embedding,
        "audio_base64": base64.b64encode(audio_bytes).decode("ascii"),
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                return resp.json()
            return {"match": True, "similarity": 1.0, "warning": "verify_endpoint_error"}
    except Exception as e:
        logger.warning(f"Erro ao verificar locutor: {e}")
        return {"match": True, "similarity": 1.0, "error": str(e)}
