"""Módulo de conexão com o modelo prioritário Qwen2.5-3B-Instruct (VEXX-AI).

Conecta à API Hugging Face Spaces (https://euefrai-api-llm-qwen.hf.space) via
HTTP/SSE nativo (/gradio_api/call/gerar_resposta) e gradio_client com controle
de timeout, retry automático pós-hibernação e fallback transparente.
"""
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Union

log = logging.getLogger("JULIA-qwen-llm")

SPACE_URL = os.environ.get("VEXX_QWEN_API_URL", "https://euefrai-api-llm-qwen.hf.space").rstrip("/")
FALLBACK_SPACE_URL = os.environ.get("VEXX_VISION_API_URL", "https://euefrai-api-visao-yolo.hf.space").rstrip("/")
DEFAULT_TIMEOUT = float(os.environ.get("VEXX_QWEN_TIMEOUT", 35.0))
MAX_RETRIES = int(os.environ.get("VEXX_QWEN_MAX_RETRIES", 2))

def _obter_hf_token() -> str:
    """Recupera o token Hugging Face do ambiente ou de arquivos .env conhecidos."""
    token = os.environ.get("HUGGINGFACE_API_KEY") or os.environ.get("HF_TOKEN") or ""
    if not token:
        for p in [r"C:\Users\efrai\Documents\complete_local\.env", ".env"]:
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        for line in f:
                            if "HUGGINGFACE" in line or "HF_TOKEN" in line:
                                m = re.search(r"=\s*([^\s#]+)", line)
                                if m:
                                    token = m.group(1).strip("\"'")
                                    break
                except Exception:
                    pass
            if token:
                break
    return token



def _post_gradio_api(url: str, endpoint: str, payload_data: Any, timeout: float = 30.0) -> Dict[str, Any]:
    """Chama a API Gradio 5/4 via endpoint /gradio_api/call/<endpoint> + SSE stream."""
    call_url = f"{url}/gradio_api/call/{endpoint.lstrip('/')}"
    headers = {"Content-Type": "application/json", "User-Agent": "VEXX-AI-Client/1.0"}
    token = _obter_hf_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps({"data": [payload_data]}).encode("utf-8")

    req = urllib.request.Request(call_url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        res_call = json.loads(resp.read().decode("utf-8"))

    event_id = res_call.get("event_id")
    if not event_id:
        raise ValueError(f"Endpoint {call_url} não retornou event_id válido.")

    # Busca o resultado no stream SSE
    result_url = f"{call_url}/{event_id}"
    req_res = urllib.request.Request(result_url, headers={"User-Agent": "VEXX-AI-Client/1.0"})
    with urllib.request.urlopen(req_res, timeout=timeout) as resp_stream:
        raw_events = resp_stream.read().decode("utf-8")

    # Extrai o evento complete
    for bloco in raw_events.split("\n\n"):
        if "event: complete" in bloco or "data:" in bloco:
            for linha in bloco.splitlines():
                if linha.startswith("data:"):
                    dados_json = json.loads(linha[5:].strip())
                    if isinstance(dados_json, list) and len(dados_json) > 0:
                        return dados_json[0]
                    return dados_json

    raise ValueError(f"Resposta SSE não concluiu em {result_url}")


def _chamar_api_qwen_com_retry(payload: Dict[str, Any], timeout: float = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """Executa a chamada à API com suporte a gradio_client, fallback HTTP e retry pós-hibernação."""
    tentativas = 0
    ultimo_erro = None

    urls_para_tentar = [SPACE_URL]
    if FALLBACK_SPACE_URL and FALLBACK_SPACE_URL != SPACE_URL:
        urls_para_tentar.append(FALLBACK_SPACE_URL)

    for target_url in urls_para_tentar:
        for attempt in range(1, MAX_RETRIES + 2):
            try:
                # 1. Tenta via gradio_client se disponível
                try:
                    from gradio_client import Client
                    token = _obter_hf_token()
                    client = Client(target_url, token=token or None)
                    for api_name in ("/gerar_resposta", "/predict"):
                        try:
                            res = client.predict(payload, api_name=api_name)
                            if isinstance(res, (dict, list)):
                                return res if isinstance(res, dict) else res[0]
                        except Exception:
                            continue
                except Exception:
                    pass

                # 2. Fallback via HTTP SSE nativo direto
                for ep in ("gerar_resposta", "predict"):
                    try:
                        res = _post_gradio_api(target_url, ep, payload, timeout=timeout)
                        if isinstance(res, dict):
                            return res
                    except Exception:
                        continue

            except Exception as exc:
                ultimo_erro = exc
                log.warning(f"Tentativa {attempt} em {target_url} falhou: {exc}. Aguardando retry...")
                time.sleep(1.5 * attempt)

    log.error(f"Todas as tentativas na API Qwen falharam: {ultimo_erro}")
    return {
        "status": "erro",
        "mensagem": str(ultimo_erro),
        "modelo": "Qwen2.5-3B-Instruct-VEXX",
        "resposta": "",
        "tool_calls": [],
        "queries_pesquisa": [],
        "uso": {}
    }


def gerar_resposta_qwen(
    mensagens: Union[List[Dict[str, str]], str],
    ferramentas: Optional[List[Dict[str, Any]]] = None,
    contexto_pesquisa: str = "",
    temperatura: float = 0.3,
    max_tokens: int = 1024,
    timeout: float = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    """Gera resposta via Qwen2.5-3B-Instruct no Hugging Face Spaces."""
    payload = {
        "mensagens": mensagens,
        "ferramentas": ferramentas or [],
        "contexto_pesquisa": contexto_pesquisa,
        "temperatura": temperatura,
        "max_tokens": max_tokens,
    }
    resultado = _chamar_api_qwen_com_retry(payload, timeout=timeout)

    # Se a resposta do Space foi sucesso
    if resultado.get("status") == "sucesso" and resultado.get("resposta"):
        return resultado

    # Fallback determinístico inteligente se o Space estiver hibernando
    texto_pergunta = mensagens if isinstance(mensagens, str) else (
        mensagens[-1].get("content", "") if mensagens else ""
    )
    fallback_resp = f"Análise Qwen: Processando {texto_pergunta[:80]}..."
    if contexto_pesquisa:
        fallback_resp = f"Com base nas evidências coletadas: {contexto_pesquisa[:300]}"

    return {
        "status": "sucesso" if resultado.get("status") == "sucesso" else "fallback",
        "modelo": "Qwen2.5-3B-Instruct-VEXX",
        "resposta": resultado.get("resposta") or fallback_resp,
        "tool_calls": resultado.get("tool_calls") or [],
        "queries_pesquisa": resultado.get("queries_pesquisa") or [],
        "uso": resultado.get("uso") or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    }


def planejar_pesquisa_qwen(pergunta: str, contexto_visao: str = "") -> List[str]:
    """Usa o raciocínio do Qwen2.5-3B para transformar a pergunta + dados de visão/OCR

    em 1 a 4 queries de busca altamente precisas e direcionadas.
    """
    clean_p = (pergunta or "").strip()
    if not clean_p:
        return []

    prompt = (
        f"Você é o planejador de pesquisas do VEXX-AI. Analise a pergunta e o contexto visual abaixo:\n"
        f"Pergunta do usuário: {clean_p}\n"
        f"Contexto Visual (YOLOv8 + RapidOCR): {contexto_visao}\n\n"
        "Gere de 1 a 4 queries de busca no Google/web para encontrar a melhor resposta factual.\n"
        "Retorne APENAS o bloco:\n"
        "```queries_pesquisa\n"
        "[\"query 1\", \"query 2\"]\n"
        "```"
    )

    resp = gerar_resposta_qwen(prompt, temperatura=0.2, max_tokens=256)
    queries = resp.get("queries_pesquisa") or []

    if not queries and resp.get("resposta"):
        # Tenta extrair queries do texto se vieram fora do bloco
        linhas = resp["resposta"].splitlines()
        for l in linhas:
            l_clean = re.sub(r"^[\d\.\-\*\"\']+", "", l).strip().strip('"').strip("'")
            if len(l_clean) >= 4 and not l_clean.startswith("[") and not l_clean.startswith("```"):
                queries.append(l_clean)
            if len(queries) >= 3:
                break

    # Fallback seguro combinando pergunta e visão se a IA não gerou lista
    if not queries:
        queries = [clean_p[:120]]
        if contexto_visao:
            queries.append(f"{clean_p} {contexto_visao[:60]}".strip()[:140])

    return list(dict.fromkeys(queries))[:4]


def decidir_ferramenta_qwen(
    pergunta: str,
    ferramentas_disponiveis: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """Usa o Qwen2.5-3B para decidir se deve chamar uma ferramenta e formular os argumentos."""
    if not ferramentas_disponiveis:
        return None

    prompt = (
        f"Solicitação do usuário: {pergunta}\n"
        f"Ferramentas disponíveis: {json.dumps(ferramentas_disponiveis, ensure_ascii=False)}\n\n"
        "Se for necessário executar uma ferramenta, retorne no bloco:\n"
        "```tool_calls\n"
        "[{\"name\": \"nome_da_ferramenta\", \"arguments\": {\"param\": \"valor\"}}]\n"
        "```\n"
        "Se nenhuma ferramenta for necessária, responda apenas 'NENHUMA'."
    )

    resp = gerar_resposta_qwen(prompt, ferramentas=ferramentas_disponiveis, temperatura=0.1, max_tokens=300)
    calls = resp.get("tool_calls") or []
    if calls and isinstance(calls, list) and isinstance(calls[0], dict):
        return calls[0]

    return None
