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
DEFAULT_TIMEOUT = float(os.environ.get("VEXX_QWEN_TIMEOUT", 10.0))
MAX_RETRIES = int(os.environ.get("VEXX_QWEN_MAX_RETRIES", 1))

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



def _post_gradio_api(url: str, endpoint: str, payload_data: Any, timeout: float = 12.0) -> Dict[str, Any]:
    """Chama a API Gradio 5/4 via endpoint /gradio_api/call/<endpoint> + SSE stream com parsing linha a linha."""
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

    # Busca o resultado no stream SSE com leitura linha a linha (não bloqueia por EOF)
    result_url = f"{call_url}/{event_id}"
    req_res = urllib.request.Request(result_url, headers={"User-Agent": "VEXX-AI-Client/1.0", "Accept": "text/event-stream"})
    if token:
        req_res.add_header("Authorization", f"Bearer {token}")

    inicio = time.monotonic()
    with urllib.request.urlopen(req_res, timeout=timeout) as resp_stream:
        evento_atual = ""
        for raw_line in resp_stream:
            if time.monotonic() - inicio > timeout:
                raise TimeoutError("Timeout aguardando conclusão SSE Gradio")
            linha = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
            if linha.startswith("event:"):
                evento_atual = linha[6:].strip()
            elif linha.startswith("data:"):
                payload_str = linha[5:].strip()
                if payload_str == "null" or not payload_str:
                    continue
                try:
                    dados_json = json.loads(payload_str)
                    if evento_atual == "error" or (isinstance(dados_json, dict) and "error" in dados_json):
                        err_msg = dados_json.get("error", "Erro retornado pelo Space") if isinstance(dados_json, dict) else str(dados_json)
                        raise RuntimeError(f"Gradio SSE error: {err_msg}")
                    if isinstance(dados_json, list) and len(dados_json) > 0:
                        return dados_json[0]
                    return dados_json
                except json.JSONDecodeError:
                    continue
            elif not linha:
                evento_atual = ""

    raise ValueError(f"Stream SSE encerrado sem payload final em {result_url}")


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

    # Se o Space retornou erro, indisponibilidade ou falhou, não inventa resposta falsa
    resp_texto = (resultado.get("resposta") or "").strip()
    return {
        "status": "sucesso" if (resultado.get("status") == "sucesso" and resp_texto) else "fallback",
        "modelo": "Qwen2.5-3B-Instruct-VEXX",
        "resposta": resp_texto,
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

    if resp.get("status") == "sucesso" and not queries and resp.get("resposta"):
        # Tenta extrair queries do texto se vieram fora do bloco
        linhas = resp["resposta"].splitlines()
        for l in linhas:
            l_clean = re.sub(r"^[\d\.\-\*\"\']+", "", l).strip().strip('"').strip("'")
            if len(l_clean) >= 4 and not l_clean.startswith("[") and not l_clean.startswith("```") and not any(l_clean.startswith(pref) for pref in ("Análise Qwen", "Você é", "Pergunta", "Contexto", "Erro", "Gere de")):
                queries.append(l_clean)
            if len(queries) >= 3:
                break

    # Fallback seguro combinando pergunta e visão se a IA não gerou lista
    if not queries:
        queries = [clean_p[:300]]
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

VOCAB_HEURISTICAS = {
    "fone": "headphone, earphones, bluetooth headset, earbuds",
    "audio": "speaker, soundbar, headset, audio device",
    "celular": "cell phone, mobile phone, smartphone, screen",
    "smartphone": "smartphone, mobile phone, cell phone",
    "computador": "laptop, computer monitor, keyboard, mouse",
    "notebook": "laptop, keyboard, screen",
    "teclado": "keyboard, keys",
    "mouse": "mouse, computer mouse",
    "botao": "button, clickable button, icon",
    "comprar": "buy button, shopping cart, add to cart, price tag",
    "carrinho": "shopping cart, cart icon, bag",
    "login": "login button, sign in, username, password field, input field",
    "entrar": "sign in button, login button, submit button",
    "pesquisar": "search bar, search input, search button, magnifying glass",
    "busca": "search bar, search input, magnifying glass",
    "fechar": "close button, x icon, cancel button",
    "link": "hyperlink, text link, button",
    "icone": "icon, logo, symbol",
    "imagem": "image, photo, picture, thumbnail",
    "tabela": "table, data grid, spreadsheet",
    "preco": "price, price tag, currency, discount badge",
    "relogio": "smartwatch, watch, clock",
    "livro": "book, document, paper, text",
    "caneca": "cup, mug, coffee cup",
    "garrafa": "bottle, water bottle",
    "carro": "car, vehicle, automobile",
}


def sugerir_classes_visao_qwen(consulta: str) -> str:
    """Traduz o pedido do usuario para classes de vocabulario aberto (YOLO-World v2)."""
    c_limpa = (consulta or "").lower().strip()
    if not c_limpa:
        return "object, button, text, item"

    classes_encontradas: list[str] = []
    for k, v in VOCAB_HEURISTICAS.items():
        if k in c_limpa:
            for item in v.split(","):
                c_norm = item.strip()
                if c_norm and c_norm not in classes_encontradas:
                    classes_encontradas.append(c_norm)

    if classes_encontradas:
        return ", ".join(classes_encontradas[:8])

    try:
        prompt = (
            "Extraia de 2 a 5 nomes de objetos em ingles para deteccao com YOLO-World v2.\n"
            f"Consulta: {consulta}\n"
            "Retorne APENAS os nomes separados por virgula (ex: 'bluetooth headphone, price, buy button')."
        )
        resp = gerar_resposta_qwen(prompt, temperatura=0.1, max_tokens=60, timeout=2.5)
        saida = resp.get("resposta", "").strip().strip(".'\"")
        if saida and len(saida) >= 3 and not saida.startswith("Erro"):
            for item in saida.split(","):
                item_limpo = item.strip().lower()
                if 2 <= len(item_limpo) <= 40 and item_limpo not in classes_encontradas:
                    classes_encontradas.append(item_limpo)
    except Exception:
        pass

    if not classes_encontradas:
        classes_encontradas = ["object", "item", "button", "text"]

    return ", ".join(classes_encontradas[:8])


def sintetizar_pesquisa_multimodal_qwen(
    consulta: str,
    fontes: list[dict[str, Any]],
    imagens: list[dict[str, Any]] | None = None,
    contexto_visao: str = "",
) -> dict[str, Any]:
    """Sintetiza um relatorio de pesquisa profunda com links diretos, imagens e fatos verificados."""
    if not fontes:
        return {
            "status": "vazio",
            "relatorio_markdown": f"Nenhuma fonte factual encontrada para '{consulta}'.",
            "fontes": [],
            "imagens": [],
        }

    linhas_md = [
        f"## Pesquisa e Analise Aprofundada: {consulta}",
        "",
        "### Resumo Executivo",
    ]

    blocos_contexto = []
    for idx, f in enumerate(fontes[:6], start=1):
        titulo = f.get("titulo") or f.get("title") or "Fonte"
        url = f.get("url") or f.get("link") or ""
        trecho = str(f.get("trecho") or f.get("snippet") or f.get("markdown") or "")[:500].replace("\n", " ")
        blocos_contexto.append(f"[{idx}] {titulo} ({url}): {trecho}")

    resumo_gerado = ""
    try:
        evidencias_str = "\n".join(blocos_contexto)
        prompt = (
            f"Topico da pesquisa: {consulta}\n"
            f"Evidencias encontradas:\n{evidencias_str}\n\n"
            "Escreva uma resposta analitica, detalhada e precisa em portugues citando as fontes com [1], [2]..."
        )
        resp_qwen = gerar_resposta_qwen(prompt, temperatura=0.2, max_tokens=1024)
        if resp_qwen.get("status") == "sucesso" and len(resp_qwen.get("resposta", "")) >= 100:
            resumo_gerado = resp_qwen["resposta"].strip()
    except Exception:
        pass

    if resumo_gerado:
        linhas_md.append(resumo_gerado)
    else:
        for idx, f in enumerate(fontes[:4], start=1):
            titulo = f.get("titulo") or f.get("title") or "Fonte"
            trecho = str(f.get("trecho") or f.get("snippet") or "")[:200].replace("\n", " ")
            url = f.get("url") or ""
            linhas_md.append(f"- **[{idx}] [{titulo}]({url}):** {trecho}")

    imgs_validas = []
    if imagens:
        for img in imagens:
            if isinstance(img, dict) and img.get("url"):
                u = str(img["url"]).strip()
                if u.startswith("http://") or u.startswith("https://"):
                    imgs_validas.append(img)
            elif isinstance(img, str) and (img.startswith("http://") or img.startswith("https://")):
                imgs_validas.append({"url": img, "titulo": "Imagem do produto/artigo"})

    if imgs_validas:
        linhas_md.extend([
            "",
            "### Imagens e Evidencias Visuais",
        ])
        for img in imgs_validas[:4]:
            t = img.get("titulo") or img.get("alt") or consulta
            linhas_md.append(f"![{t}]({img['url']})")

    if contexto_visao:
        linhas_md.extend([
            "",
            "### Analise Visual Direta (YOLO-World + RapidOCR)",
            f"{contexto_visao}",
        ])

    linhas_md.extend([
        "",
        "### Fontes e Links Consultados",
    ])
    for idx, f in enumerate(fontes[:8], start=1):
        titulo = f.get("titulo") or f.get("title") or "Fonte"
        url = f.get("url") or f.get("link") or ""
        dominio = f.get("dominio") or f.get("domain") or ""
        linhas_md.append(f"- **[{idx}]** [{titulo}]({url}) {f'({dominio})' if dominio else ''}")

    relatorio = "\n".join(linhas_md)
    return {
        "status": "sucesso",
        "relatorio_markdown": relatorio,
        "total_fontes": len(fontes),
        "fontes": fontes,
        "total_imagens": len(imgs_validas),
        "imagens": imgs_validas,
    }


def enriquecer_pesquisa_com_visao_qwen(
    consulta_texto: str,
    dados_visao: dict | list | None = None,
) -> list[str]:
    """Combina texto do usuario com objetos detectados e textos OCR em queries otimizadas."""
    c_limpa = (consulta_texto or "").strip()
    if not c_limpa:
        return []

    tags = ""
    ocr_texto = ""
    if isinstance(dados_visao, dict):
        tags = str(dados_visao.get("tags_busca") or "")
        ocr_texto = str(dados_visao.get("texto_extraido") or "")
    elif isinstance(dados_visao, list):
        tags_list = []
        for d in dados_visao:
            if isinstance(d, dict) and d.get("tags_busca"):
                tags_list.append(str(d["tags_busca"]))
        tags = ", ".join(tags_list)

    ctx = ""
    if tags:
        ctx += f"Tags identificadas: {tags}. "
    if ocr_texto:
        ctx += f"Texto lido na imagem: {ocr_texto[:140]}."

    return planejar_pesquisa_qwen(c_limpa, contexto_visao=ctx)