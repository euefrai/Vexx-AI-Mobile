"""Serviço de Visão Computacional (YOLOv8) integrado ao Hugging Face Spaces.

Conecta ao Space ``euefrai/api-visao-yolo`` (``https://euefrai-api-visao-yolo.hf.space``)
via ``gradio_client`` com suporte a URL, caminho de arquivo, bytes ou Base64,
tratamento de timeout/retry (para acordar o Space em caso de hibernação) e
enriquecimento direto do contexto de pesquisa e LLM do VEXX-AI.
"""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import logging
import os
from pathlib import Path
import re
import tempfile
import threading
import time
from typing import Any, Callable
from urllib.parse import urlparse

log = logging.getLogger("JULIA-vision")

DEFAULT_SPACE_ID = "euefrai/api-visao-yolo"
DEFAULT_SPACE_URL = "https://euefrai-api-visao-yolo.hf.space"
DEFAULT_API_NAME = "/predict"
DEFAULT_TIMEOUT_S = 25.0
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF_S = 1.5

_CLIENT_LOCK = threading.Lock()
_CLIENT_CACHE: dict[str, Any] = {}

_DATA_IMAGE_RE = re.compile(
    r"(data:image/(?:png|jpeg|jpg|webp|gif|bmp);base64,[A-Za-z0-9+/=]+)",
    re.IGNORECASE,
)
_MD_IMAGE_RE = re.compile(
    r"!\[[^\]\n]{0,160}\]\(\s*(https?://[^)\s]+|data:image/[^)\s]+)\s*\)",
    re.IGNORECASE,
)
_URL_IMAGE_RE = re.compile(
    r"(https?://[^\s<>\"')]+?\.(?:jpg|jpeg|png|webp|gif|bmp)(?:\?[^\s<>\"')]*)?)",
    re.IGNORECASE,
)
_RAW_BASE64_PREFIXES = (
    "/9j/",       # JPEG
    "iVBORw0KGgo",  # PNG
    "R0lGOD",     # GIF
    "UklGR",      # WEBP
)


def space_url_configurada(space_url: str | None = None) -> str:
    """Retorna a URL base ativa da API de visão no Hugging Face."""
    url = (space_url or os.environ.get("VEXX_VISION_API_URL") or DEFAULT_SPACE_URL).strip()
    return url.rstrip("/") or DEFAULT_SPACE_URL


def vision_habilitada() -> bool:
    """Permite desativar chamadas externas de visão via VEXX_VISION_ENABLED=0."""
    val = os.environ.get("VEXX_VISION_ENABLED", "1").strip().lower()
    return val not in ("0", "false", "no", "off")


def _detectar_extensao_bytes(raw: bytes) -> str:
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if raw.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if raw.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        return ".webp"
    if raw.startswith(b"BM"):
        return ".bmp"
    return ".png"


def _decodificar_base64_imagem(valor: str) -> bytes | None:
    texto = (valor or "").strip()
    if not texto:
        return None
    if texto.lower().startswith("data:image/"):
        _, _, payload = texto.partition(",")
        texto = payload.strip()
    elif not texto.startswith(_RAW_BASE64_PREFIXES):
        return None
    try:
        raw = base64.b64decode(texto, validate=False)
        return raw if len(raw) >= 16 else None
    except Exception:
        return None


def _preparar_entrada_imagem(imagem: Any) -> tuple[str, str | None, str]:
    """Converte URL, caminho local, bytes ou Base64 em entrada para o Gradio Client.

    Retorna ``(alvo_para_handle_file, temp_path_para_limpar, rotulo_origem)``.
    """
    if imagem is None:
        raise ValueError("Nenhuma imagem enviada")

    if isinstance(imagem, (bytes, bytearray)):
        raw = bytes(imagem)
        if not raw:
            raise ValueError("Bytes de imagem vazios")
        ext = _detectar_extensao_bytes(raw)
        fd, tmp_path = tempfile.mkstemp(prefix="vexx_vision_", suffix=ext)
        os.close(fd)
        Path(tmp_path).write_bytes(raw)
        return tmp_path, tmp_path, f"bytes({len(raw)}B)"

    if isinstance(imagem, Path):
        if not imagem.is_file():
            raise ValueError(f"Arquivo de imagem não encontrado: {imagem}")
        resolvido = str(imagem.resolve())
        return resolvido, None, imagem.name

    if isinstance(imagem, str):
        texto = imagem.strip()
        if not texto:
            raise ValueError("Caminho ou URL de imagem vazio")

        raw_b64 = _decodificar_base64_imagem(texto)
        if raw_b64 is not None:
            ext = _detectar_extensao_bytes(raw_b64)
            fd, tmp_path = tempfile.mkstemp(prefix="vexx_vision_b64_", suffix=ext)
            os.close(fd)
            Path(tmp_path).write_bytes(raw_b64)
            return tmp_path, tmp_path, "base64_image"

        parsed = urlparse(texto)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            return texto, None, texto[:200]

        caminho = Path(texto)
        if caminho.is_file():
            resolvido = str(caminho.resolve())
            return resolvido, None, caminho.name

        raise ValueError("Formato de imagem inválido (informe URL, caminho de arquivo ou Base64)")

    raise ValueError(f"Tipo de imagem não suportado: {type(imagem).__name__}")


def _criar_cliente_gradio(url: str, timeout: float = DEFAULT_TIMEOUT_S):
    from gradio_client import Client

    try:
        return Client(url, httpx_kwargs={"timeout": timeout}, verbose=False)
    except TypeError:
        try:
            return Client(url, verbose=False)
        except TypeError:
            return Client(url)


def obter_cliente(space_url: str | None = None, timeout: float = DEFAULT_TIMEOUT_S,
                  *, recriar: bool = False):
    """Obtém ou inicializa o cliente ``gradio_client.Client`` para o Space."""
    url = space_url_configurada(space_url)
    with _CLIENT_LOCK:
        if recriar or url not in _CLIENT_CACHE:
            _CLIENT_CACHE[url] = _criar_cliente_gradio(url, timeout=timeout)
        return _CLIENT_CACHE[url]


def _empacotar_arquivo_gradio(alvo: str):
    try:
        from gradio_client import handle_file
        return handle_file(alvo)
    except ImportError:
        return alvo


def _invocar_predicao(cliente: Any, entrada: Any, api_name: str = DEFAULT_API_NAME) -> Any:
    """Chama ``/predict`` com fallback para ``/detectar_objetos`` ou ``fn_index=0``."""
    tentativas_api = [api_name]
    if "/detectar_objetos" not in tentativas_api:
        tentativas_api.append("/detectar_objetos")

    ultimo_erro: Exception | None = None
    for endpoint in tentativas_api:
        try:
            return cliente.predict(entrada, api_name=endpoint)
        except (ValueError, KeyError) as exc:
            ultimo_erro = exc
            continue
    try:
        return cliente.predict(entrada, fn_index=0)
    except Exception:
        if ultimo_erro is not None:
            raise ultimo_erro
        raise


def _normalizar_resposta(bruto: Any, origem: str = "") -> dict[str, Any]:
    """Padroniza o payload retornado pela API YOLOv8 do Space."""
    if isinstance(bruto, (list, tuple)) and len(bruto) == 1 and isinstance(bruto[0], dict):
        bruto = bruto[0]
    if not isinstance(bruto, dict):
        return {
            "status": "erro",
            "mensagem": "Resposta inesperada da API de visão",
            "total_objetos": 0,
            "tags_busca": "",
            "deteccoes": [],
            "origem": origem,
        }

    deteccoes_brutas = bruto.get("deteccoes")
    if not isinstance(deteccoes_brutas, list):
        deteccoes_brutas = []

    deteccoes: list[dict[str, Any]] = []
    classes_confiaveis: list[str] = []
    for item in deteccoes_brutas:
        if not isinstance(item, dict):
            continue
        objeto = str(item.get("objeto") or "").strip()
        if not objeto:
            continue
        try:
            confianca = round(float(item.get("confianca", 0.0)), 2)
        except (TypeError, ValueError):
            confianca = 0.0
        coords_raw = item.get("coordenadas")
        coordenadas: list[float] = []
        if isinstance(coords_raw, (list, tuple)):
            for c in coords_raw[:4]:
                try:
                    coordenadas.append(round(float(c), 2))
                except (TypeError, ValueError):
                    pass
        deteccoes.append({
            "objeto": objeto,
            "confianca": confianca,
            "coordenadas": coordenadas,
        })
        if confianca >= 0.35:
            classes_confiaveis.append(objeto)

    tags_busca = str(bruto.get("tags_busca") or "").strip()
    if not tags_busca and classes_confiaveis:
        tags_unicas = list(dict.fromkeys(classes_confiaveis))
        tags_busca = ", ".join(tags_unicas)

    status = str(bruto.get("status") or "sucesso").strip().lower()
    total_objetos = bruto.get("total_objetos")
    if not isinstance(total_objetos, int):
        total_objetos = len(deteccoes)

    saida: dict[str, Any] = {
        "status": status,
        "total_objetos": total_objetos,
        "tags_busca": tags_busca,
        "deteccoes": deteccoes,
        "origem": origem,
    }
    if bruto.get("mensagem"):
        saida["mensagem"] = str(bruto["mensagem"])
    return saida


def analisar_imagem(
    imagem: Any,
    *,
    space_url: str | None = None,
    api_name: str = DEFAULT_API_NAME,
    timeout: float = DEFAULT_TIMEOUT_S,
    retries: int = DEFAULT_RETRIES,
    backoff_s: float = DEFAULT_BACKOFF_S,
    client_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Envia uma imagem (URL, arquivo, bytes ou Base64) ao Space YOLOv8 e retorna detecções e tags.

    Inclui tratamento de timeout por tentativa e retry exponencial para lidar com
    cold-start / hibernação do Hugging Face Spaces.
    """
    if not vision_habilitada():
        return {
            "status": "desativado",
            "mensagem": "Serviço de visão desativado por configuração",
            "total_objetos": 0,
            "tags_busca": "",
            "deteccoes": [],
            "origem": "",
        }

    temp_path: str | None = None
    try:
        alvo, temp_path, origem = _preparar_entrada_imagem(imagem)
    except ValueError as exc:
        return {
            "status": "erro",
            "mensagem": str(exc),
            "total_objetos": 0,
            "tags_busca": "",
            "deteccoes": [],
            "origem": "",
        }

    url = space_url_configurada(space_url)
    max_tentativas = max(1, int(retries))
    timeout_efetivo = max(1.0, float(timeout))
    ultimo_erro = ""

    try:
        for tentativa in range(max_tentativas):
            recriar = tentativa > 0
            try:
                def _executar_chamada():
                    if client_factory is not None:
                        cliente = client_factory(url, timeout_efetivo)
                    else:
                        cliente = obter_cliente(url, timeout=timeout_efetivo, recriar=recriar)
                    entrada = _empacotar_arquivo_gradio(alvo)
                    return _invocar_predicao(cliente, entrada, api_name=api_name)

                with ThreadPoolExecutor(max_workers=1) as pool:
                    fut = pool.submit(_executar_chamada)
                    bruto = fut.result(timeout=timeout_efetivo)

                resultado = _normalizar_resposta(bruto, origem=origem)
                if resultado.get("status") == "sucesso":
                    return resultado
                ultimo_erro = resultado.get("mensagem") or "Falha retornada pela API de visão"
            except FuturesTimeoutError:
                ultimo_erro = f"Timeout após {timeout_efetivo:.1f}s aguardando o Space ({url})"
                log.warning("vision timeout (tentativa %d/%d): %s",
                            tentativa + 1, max_tentativas, ultimo_erro)
            except Exception as exc:
                ultimo_erro = f"{type(exc).__name__}: {exc}"
                log.warning("vision falha (tentativa %d/%d): %s",
                            tentativa + 1, max_tentativas, ultimo_erro)

            if tentativa + 1 < max_tentativas and backoff_s > 0:
                time.sleep(backoff_s * (2 ** tentativa))

        return {
            "status": "erro",
            "mensagem": ultimo_erro or "API de visão indisponível",
            "total_objetos": 0,
            "tags_busca": "",
            "deteccoes": [],
            "origem": origem,
        }
    finally:
        if temp_path:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except OSError:
                pass


# Alias semântico compatível com o contrato do Space
detectar_objetos = analisar_imagem


def extrair_imagens_do_texto(texto: str, contexto_local: dict | None = None) -> list[str]:
    """Extrai URLs de imagens, data URIs Base64 ou imagens anexadas em ``contexto_local``."""
    encontradas: list[str] = []

    if isinstance(contexto_local, dict):
        img_unica = contexto_local.get("image") or contexto_local.get("image_url") or contexto_local.get("image_b64")
        if isinstance(img_unica, str) and img_unica.strip():
            encontradas.append(img_unica.strip())
        imgs_lista = contexto_local.get("images")
        if isinstance(imgs_lista, (list, tuple)):
            for item in imgs_lista[:5]:
                if isinstance(item, str) and item.strip():
                    encontradas.append(item.strip())

    corpo = str(texto or "")
    if corpo:
        for m in _MD_IMAGE_RE.finditer(corpo):
            candidato = m.group(1).strip()
            if candidato and "loremflickr.com" not in candidato.lower():
                encontradas.append(candidato)

        for m in _DATA_IMAGE_RE.finditer(corpo):
            encontradas.append(m.group(1).strip())

        for m in _URL_IMAGE_RE.finditer(corpo):
            candidato = m.group(1).strip().rstrip(".,;)")
            if candidato and "loremflickr.com" not in candidato.lower():
                encontradas.append(candidato)

    return list(dict.fromkeys(encontradas))


def analisar_imagens_contexto(
    texto: str,
    contexto_local: dict | None = None,
    *,
    max_imagens: int = 3,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Detecta objetos em todas as imagens associadas ao prompt/pesquisa."""
    imagens = extrair_imagens_do_texto(texto, contexto_local)[:max(1, int(max_imagens))]
    if not imagens:
        return []
    resultados: list[dict[str, Any]] = []
    for img in imagens:
        res = analisar_imagem(img, **kwargs)
        resultados.append(res)
    return resultados


def coletar_tags_busca(resultados_visao: list[dict[str, Any]] | dict[str, Any] | None) -> str:
    """Consolida ``tags_busca`` únicas a partir de um ou mais resultados do YOLO."""
    if not resultados_visao:
        return ""
    lista = [resultados_visao] if isinstance(resultados_visao, dict) else list(resultados_visao)
    tags: list[str] = []
    for res in lista:
        if not isinstance(res, dict) or res.get("status") != "sucesso":
            continue
        bruto = str(res.get("tags_busca") or "")
        for t in bruto.split(","):
            limpa = t.strip()
            if limpa and limpa not in tags:
                tags.append(limpa)
    return ", ".join(tags)


def enriquecer_consulta_com_visao(
    consulta: str,
    resultados_visao: list[dict[str, Any]] | dict[str, Any] | None,
    *,
    max_chars: int = 240,
) -> str:
    """Concatena as ``tags_busca`` detectadas pelo YOLO à consulta de pesquisa."""
    base = str(consulta or "").strip()
    if base:
        base = _DATA_IMAGE_RE.sub("", base).strip()
    tags = coletar_tags_busca(resultados_visao)
    if not tags:
        return base[:max_chars]
    termos_novos = [
        t.strip() for t in tags.split(",")
        if t.strip() and t.strip().lower() not in base.lower()
    ]
    if not termos_novos:
        return base[:max_chars]
    complemento = ", ".join(termos_novos)
    combinada = f"{base} {complemento}".strip() if base else complemento
    return combinada[:max_chars]


def formatar_contexto_visao(resultados_visao: list[dict[str, Any]] | dict[str, Any] | None) -> str:
    """Formata ``tags_busca`` e coordenadas do YOLOv8 para injeção no contexto do LLM/pesquisa."""
    if not resultados_visao:
        return ""
    lista = [resultados_visao] if isinstance(resultados_visao, dict) else list(resultados_visao)
    sucessos = [r for r in lista if isinstance(r, dict) and r.get("status") == "sucesso"]
    if not sucessos:
        return ""

    linhas = [
        "ANÁLISE VISUAL (VEXX-AI Vision API / YOLOv8 — objetos e coordenadas detectados na imagem associada):"
    ]
    tags_globais = coletar_tags_busca(sucessos)
    if tags_globais:
        linhas.append(f"- Tags de busca (tags_busca): {tags_globais}")
    else:
        linhas.append("- Tags de busca (tags_busca): nenhum objeto com confiança >= 0.35")

    for idx, res in enumerate(sucessos, start=1):
        origem = res.get("origem") or f"imagem_{idx}"
        total = int(res.get("total_objetos") or len(res.get("deteccoes") or []))
        deteccoes = res.get("deteccoes") or []
        if not deteccoes:
            linhas.append(f"- Imagem {idx} ({origem}): nenhum objeto detectado (total_objetos=0).")
            continue
        itens_fmt = []
        for d in deteccoes[:15]:
            obj = d.get("objeto", "objeto")
            conf = d.get("confianca", 0.0)
            coords = d.get("coordenadas", [])
            itens_fmt.append(f"{obj} (confiança={conf}, coordenadas={coords})")
        linhas.append(
            f"- Imagem {idx} ({origem}, total_objetos={total}): " + "; ".join(itens_fmt)
        )

    linhas.append(
        "Use estas tags_busca e coordenadas reais detectadas pelo YOLOv8 para responder com precisão "
        "e contextualizar a pesquisa."
    )
    return "\n".join(linhas)
