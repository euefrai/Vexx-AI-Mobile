"""Serviço de Visão Computacional, Leitura de Fontes (OCR) e Clique por Coordenada (YOLOv8 + RapidOCR).

Conecta ao Space ``euefrai/api-visao-yolo`` (``https://euefrai-api-visao-yolo.hf.space``)
via ``gradio_client`` com suporte a URL, caminho de arquivo, bytes ou Base64,
tratamento de timeout/retry e funções dedicadas:
- ``analisar_imagem(imagem)``: objetos YOLOv8, ``texto_extraido``, ``textos_lidos``, ``tags_busca`` e ``alvos_clique``.
- ``ler_fontes_imagem(imagem)``: todos os textos/fontes lidos na imagem com posições e pontos de clique.
- ``encontrar_coordenada_clique(imagem, alvo_texto_ou_objeto)``: localiza objetos ou textos e retorna ``{x, y, x_norm, y_norm}``.
- ``clicar_alvo_tela(alvo_texto_ou_objeto, imagem=None)``: integra com ``remoto.py`` para clicar no elemento na tela.
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
import unicodedata
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
    "/9j/",         # JPEG
    "iVBORw0KGgo",  # PNG
    "R0lGOD",       # GIF
    "UklGR",        # WEBP
)


def space_url_configurada(space_url: str | None = None) -> str:
    """Retorna a URL base ativa da API de visão no Hugging Face."""
    url = (space_url or os.environ.get("VEXX_VISION_API_URL") or DEFAULT_SPACE_URL).strip()
    return url.rstrip("/") or DEFAULT_SPACE_URL


def vision_habilitada() -> bool:
    """Permite desativar chamadas externas de visão via VEXX_VISION_ENABLED=0."""
    val = os.environ.get("VEXX_VISION_ENABLED", "1").strip().lower()
    return val not in ("0", "false", "no", "off")


def _sem_acentos(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", str(texto or "").lower())
        if not unicodedata.combining(c)
    )


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
    """Converte URL, caminho local, bytes ou Base64 em entrada para o Gradio Client."""
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


def _calcular_ponto_clique(coordenadas: list[float], largura: int, altura: int,
                           ponto_existente: Any = None) -> dict[str, float | int]:
    """Garante cálculo consistente de ``{x, y, x_norm, y_norm}`` a partir da bounding box."""
    if isinstance(ponto_existente, dict) and all(k in ponto_existente for k in ("x", "y", "x_norm", "y_norm")):
        try:
            return {
                "x": int(round(float(ponto_existente["x"]))),
                "y": int(round(float(ponto_existente["y"]))),
                "x_norm": round(float(ponto_existente["x_norm"]), 4),
                "y_norm": round(float(ponto_existente["y_norm"]), 4),
            }
        except (TypeError, ValueError):
            pass

    if len(coordenadas) >= 4:
        x1, y1, x2, y2 = coordenadas[:4]
        cx = int(round((x1 + x2) / 2.0))
        cy = int(round((y1 + y2) / 2.0))
    else:
        cx, cy = 0, 0

    w = max(1, int(largura or 1))
    h = max(1, int(altura or 1))
    nx = round(min(1.0, max(0.0, cx / float(w))), 4) if largura else 0.0
    ny = round(min(1.0, max(0.0, cy / float(h))), 4) if altura else 0.0
    return {"x": cx, "y": cy, "x_norm": nx, "y_norm": ny}


def _normalizar_resposta(bruto: Any, origem: str = "") -> dict[str, Any]:
    """Padroniza o payload retornado pela API YOLOv8 + RapidOCR do Space."""
    if isinstance(bruto, (list, tuple)) and len(bruto) == 1 and isinstance(bruto[0], dict):
        bruto = bruto[0]
    if not isinstance(bruto, dict):
        return {
            "status": "erro",
            "mensagem": "Resposta inesperada da API de visão",
            "dimensoes": {"largura": 0, "altura": 0},
            "total_objetos": 0,
            "total_textos": 0,
            "tags_busca": "",
            "texto_extraido": "",
            "deteccoes": [],
            "textos_lidos": [],
            "alvos_clique": [],
            "origem": origem,
        }

    dim_bruta = bruto.get("dimensoes") if isinstance(bruto.get("dimensoes"), dict) else {}
    try:
        largura = max(0, int(dim_bruta.get("largura") or 0))
        altura = max(0, int(dim_bruta.get("altura") or 0))
    except (TypeError, ValueError):
        largura, altura = 0, 0

    deteccoes_brutas = bruto.get("deteccoes")
    if not isinstance(deteccoes_brutas, list):
        deteccoes_brutas = []

    deteccoes: list[dict[str, Any]] = []
    classes_confiaveis: list[str] = []
    max_x, max_y = largura, altura

    for item in deteccoes_brutas:
        if not isinstance(item, dict):
            continue
        objeto = str(item.get("objeto") or item.get("rotulo") or "").strip()
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
        if len(coordenadas) >= 4:
            max_x = max(max_x, int(round(coordenadas[2])))
            max_y = max(max_y, int(round(coordenadas[3])))
        ponto = _calcular_ponto_clique(coordenadas, max_x or 1, max_y or 1, item.get("ponto_clique"))
        deteccoes.append({
            "tipo": "objeto",
            "objeto": objeto,
            "confianca": confianca,
            "coordenadas": coordenadas,
            "ponto_clique": ponto,
        })
        if confianca >= 0.35:
            classes_confiaveis.append(objeto)

    textos_brutos = bruto.get("textos_lidos")
    if not isinstance(textos_brutos, list):
        textos_brutos = []

    textos_lidos: list[dict[str, Any]] = []
    frases_extraidas: list[str] = []
    for item in textos_brutos:
        if not isinstance(item, dict):
            continue
        txt = str(item.get("texto") or item.get("rotulo") or "").strip()
        if not txt:
            continue
        try:
            confianca = round(float(item.get("confianca", 0.0)), 2)
        except (TypeError, ValueError):
            confianca = 0.0
        coords_raw = item.get("coordenadas")
        coordenadas = []
        if isinstance(coords_raw, (list, tuple)):
            for c in coords_raw[:4]:
                try:
                    coordenadas.append(round(float(c), 2))
                except (TypeError, ValueError):
                    pass
        if len(coordenadas) >= 4:
            max_x = max(max_x, int(round(coordenadas[2])))
            max_y = max(max_y, int(round(coordenadas[3])))
        ponto = _calcular_ponto_clique(coordenadas, max_x or 1, max_y or 1, item.get("ponto_clique"))
        textos_lidos.append({
            "tipo": "texto",
            "texto": txt,
            "confianca": confianca,
            "coordenadas": coordenadas,
            "ponto_clique": ponto,
        })
        frases_extraidas.append(txt)

    if not largura and max_x:
        largura = max_x
    if not altura and max_y:
        altura = max_y

    texto_extraido = str(bruto.get("texto_extraido") or "").strip()
    if not texto_extraido and frases_extraidas:
        texto_extraido = " ".join(frases_extraidas).strip()

    tags_busca = str(bruto.get("tags_busca") or "").strip()
    if not tags_busca:
        palavras_ocr = [
            m.group(0) for m in re.finditer(r"[A-Za-zÀ-ÿ0-9]{3,}", texto_extraido)
        ][:8]
        tags_unicas = list(dict.fromkeys(classes_confiaveis + palavras_ocr))
        tags_busca = ", ".join(tags_unicas)

    alvos_brutos = bruto.get("alvos_clique")
    alvos_clique: list[dict[str, Any]] = []
    if isinstance(alvos_brutos, list) and alvos_brutos:
        for item in alvos_brutos:
            if not isinstance(item, dict):
                continue
            rotulo = str(item.get("rotulo") or item.get("texto") or item.get("objeto") or "").strip()
            if not rotulo:
                continue
            tipo = str(item.get("tipo") or ("texto" if "texto" in item else "objeto"))
            coords = list(item.get("coordenadas") or [])
            ponto = _calcular_ponto_clique(coords, largura or 1, altura or 1, item.get("ponto_clique"))
            alvos_clique.append({
                "tipo": tipo,
                "rotulo": rotulo,
                "confianca": round(float(item.get("confianca", 0.0)), 2),
                "coordenadas": coords,
                "ponto_clique": ponto,
            })
    else:
        for d in deteccoes:
            alvos_clique.append({
                "tipo": "objeto",
                "rotulo": d["objeto"],
                "confianca": d["confianca"],
                "coordenadas": d["coordenadas"],
                "ponto_clique": d["ponto_clique"],
            })
        for t in textos_lidos:
            alvos_clique.append({
                "tipo": "texto",
                "rotulo": t["texto"],
                "confianca": t["confianca"],
                "coordenadas": t["coordenadas"],
                "ponto_clique": t["ponto_clique"],
            })

    status = str(bruto.get("status") or "sucesso").strip().lower()
    total_objetos = bruto.get("total_objetos")
    if not isinstance(total_objetos, int):
        total_objetos = len(deteccoes)
    total_textos = bruto.get("total_textos")
    if not isinstance(total_textos, int):
        total_textos = len(textos_lidos)

    saida: dict[str, Any] = {
        "status": status,
        "dimensoes": {"largura": largura, "altura": altura},
        "total_objetos": total_objetos,
        "total_textos": total_textos,
        "tags_busca": tags_busca,
        "texto_extraido": texto_extraido,
        "deteccoes": deteccoes,
        "textos_lidos": textos_lidos,
        "alvos_clique": alvos_clique,
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
    """Envia uma imagem (URL, arquivo, bytes ou Base64) ao Space YOLOv8 + RapidOCR.

    Retorna objetos detectados, ``texto_extraido``, ``textos_lidos``, ``tags_busca``
    e ``alvos_clique`` com coordenadas exatas e normalizadas de clique.
    """
    if isinstance(imagem, dict) and "deteccoes" in imagem and "status" in imagem:
        return _normalizar_resposta(imagem, origem=str(imagem.get("origem") or "dict"))

    if not vision_habilitada():
        return {
            "status": "desativado",
            "mensagem": "Serviço de visão desativado por configuração",
            "dimensoes": {"largura": 0, "altura": 0},
            "total_objetos": 0,
            "total_textos": 0,
            "tags_busca": "",
            "texto_extraido": "",
            "deteccoes": [],
            "textos_lidos": [],
            "alvos_clique": [],
            "origem": "",
        }

    temp_path: str | None = None
    try:
        alvo, temp_path, origem = _preparar_entrada_imagem(imagem)
    except ValueError as exc:
        return {
            "status": "erro",
            "mensagem": str(exc),
            "dimensoes": {"largura": 0, "altura": 0},
            "total_objetos": 0,
            "total_textos": 0,
            "tags_busca": "",
            "texto_extraido": "",
            "deteccoes": [],
            "textos_lidos": [],
            "alvos_clique": [],
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
            "dimensoes": {"largura": 0, "altura": 0},
            "total_objetos": 0,
            "total_textos": 0,
            "tags_busca": "",
            "texto_extraido": "",
            "deteccoes": [],
            "textos_lidos": [],
            "alvos_clique": [],
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


def ler_fontes_imagem(imagem: Any, **kwargs: Any) -> dict[str, Any]:
    """Retorna todos os textos/fontes lidos na imagem com suas posições e pontos de clique."""
    res = analisar_imagem(imagem, **kwargs)
    return {
        "status": res.get("status", "erro"),
        "dimensoes": res.get("dimensoes", {"largura": 0, "altura": 0}),
        "total_textos": int(res.get("total_textos", 0)),
        "texto_extraido": str(res.get("texto_extraido") or ""),
        "textos_lidos": list(res.get("textos_lidos") or []),
        "origem": res.get("origem", ""),
        **({"mensagem": res["mensagem"]} if res.get("mensagem") else {}),
    }


def encontrar_coordenada_clique(
    imagem: Any,
    alvo_texto_ou_objeto: str,
    **kwargs: Any,
) -> dict[str, Any] | None:
    """Busca nos objetos do YOLO e nos textos do OCR e retorna ``{x, y, x_norm, y_norm}`` para clicar."""
    alvo_limpo = _sem_acentos(alvo_texto_ou_objeto)
    if not alvo_limpo:
        return None

    res = analisar_imagem(imagem, **kwargs)
    if res.get("status") != "sucesso":
        return None

    alvos = list(res.get("alvos_clique") or [])
    if not alvos:
        return None

    melhor: tuple[float, dict[str, Any]] | None = None
    tokens_alvo = [t for t in re.findall(r"[a-z0-9]+", alvo_limpo) if len(t) >= 2]

    for item in alvos:
        rotulo = str(item.get("rotulo") or "")
        rotulo_norm = _sem_acentos(rotulo)
        if not rotulo_norm:
            continue
        conf = float(item.get("confianca") or 0.0)
        score = 0.0
        if rotulo_norm == alvo_limpo:
            score = 100.0 + conf
        elif alvo_limpo in rotulo_norm:
            score = 80.0 + conf
        elif rotulo_norm in alvo_limpo and len(rotulo_norm) >= 3:
            score = 65.0 + conf
        elif tokens_alvo:
            hits = sum(1 for t in tokens_alvo if t in rotulo_norm)
            if hits:
                score = (40.0 * (hits / len(tokens_alvo))) + conf

        if score > 0 and (melhor is None or score > melhor[0]):
            melhor = (score, item)

    if melhor is None:
        return None

    escolhido = melhor[1]
    pt = escolhido.get("ponto_clique") or {}
    return {
        "encontrado": True,
        "tipo": escolhido.get("tipo", "objeto"),
        "rotulo": escolhido.get("rotulo", ""),
        "confianca": escolhido.get("confianca", 0.0),
        "coordenadas": escolhido.get("coordenadas", []),
        "x": int(pt.get("x", 0)),
        "y": int(pt.get("y", 0)),
        "x_norm": float(pt.get("x_norm", 0.0)),
        "y_norm": float(pt.get("y_norm", 0.0)),
        "ponto_clique": pt,
    }


def clicar_alvo_tela(
    alvo_texto_ou_objeto: str,
    imagem: Any = None,
    *,
    tipo_clique: str = "click",
    autorizado: bool = False,
    **kwargs: Any,
) -> dict[str, Any]:
    """Localiza um botão, link, texto ou objeto na tela e executa o clique via ``remoto``."""
    import remoto

    img_entrada = imagem
    if img_entrada is None:
        captura = remoto.capturar()
        img_entrada = "data:image/jpeg;base64," + captura["imagem"]

    coord = encontrar_coordenada_clique(img_entrada, alvo_texto_ou_objeto, **kwargs)
    if not coord:
        return {
            "ok": False,
            "erro": f"Alvo '{alvo_texto_ou_objeto}' não encontrado na imagem/tela.",
            "alvo": alvo_texto_ou_objeto,
        }

    kind = tipo_clique if tipo_clique in ("click", "double", "right", "move") else "click"
    cmd = remoto.validar_comando({
        "kind": kind,
        "x": coord["x_norm"],
        "y": coord["y_norm"],
    })
    exec_res = remoto.executar(cmd, autorizado=autorizado)
    return {
        "ok": True,
        "acao": kind,
        "alvo": coord["rotulo"],
        "tipo": coord["tipo"],
        "coordenada": {
            "x": coord["x"],
            "y": coord["y"],
            "x_norm": coord["x_norm"],
            "y_norm": coord["y_norm"],
        },
        "remoto": exec_res,
    }


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
    """Detecta objetos e lê textos em todas as imagens associadas ao prompt/pesquisa."""
    imagens = extrair_imagens_do_texto(texto, contexto_local)[:max(1, int(max_imagens))]
    if not imagens:
        return []
    resultados: list[dict[str, Any]] = []
    for img in imagens:
        res = analisar_imagem(img, **kwargs)
        resultados.append(res)
    return resultados


def coletar_tags_busca(resultados_visao: list[dict[str, Any]] | dict[str, Any] | None) -> str:
    """Consolida ``tags_busca`` únicas a partir de um ou mais resultados do YOLO + OCR."""
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


def coletar_texto_extraido(resultados_visao: list[dict[str, Any]] | dict[str, Any] | None) -> str:
    """Consolida todo o ``texto_extraido`` (OCR) das imagens analisadas."""
    if not resultados_visao:
        return ""
    lista = [resultados_visao] if isinstance(resultados_visao, dict) else list(resultados_visao)
    textos: list[str] = []
    for res in lista:
        if not isinstance(res, dict) or res.get("status") != "sucesso":
            continue
        txt = str(res.get("texto_extraido") or "").strip()
        if txt and txt not in textos:
            textos.append(txt)
    return " | ".join(textos)


def enriquecer_consulta_com_visao(
    consulta: str,
    resultados_visao: list[dict[str, Any]] | dict[str, Any] | None,
    *,
    max_chars: int = 240,
) -> str:
    """Concatena ``tags_busca`` (objetos) e ``texto_extraido`` (leitura de fontes) à consulta."""
    base = str(consulta or "").strip()
    if base:
        base = _DATA_IMAGE_RE.sub("", base).strip()
    tags = coletar_tags_busca(resultados_visao)
    texto_ocr = coletar_texto_extraido(resultados_visao)

    termos_novos: list[str] = []
    if tags:
        for t in tags.split(","):
            limpo = t.strip()
            if limpo and limpo.lower() not in base.lower() and limpo not in termos_novos:
                termos_novos.append(limpo)
    if texto_ocr:
        for palavra in re.findall(r"[A-Za-zÀ-ÿ0-9]{3,}", texto_ocr):
            if palavra.lower() not in base.lower() and palavra not in termos_novos:
                termos_novos.append(palavra)
                if len(termos_novos) >= 12:
                    break

    if not termos_novos:
        return base[:max_chars]
    complemento = ", ".join(termos_novos)
    combinada = f"{base} {complemento}".strip() if base else complemento
    return combinada[:max_chars]


def formatar_contexto_visao(resultados_visao: list[dict[str, Any]] | dict[str, Any] | None) -> str:
    """Formata ``tags_busca``, ``texto_extraido``, detecções e ``ponto_clique`` para o LLM."""
    if not resultados_visao:
        return ""
    lista = [resultados_visao] if isinstance(resultados_visao, dict) else list(resultados_visao)
    sucessos = [r for r in lista if isinstance(r, dict) and r.get("status") == "sucesso"]
    if not sucessos:
        return ""

    linhas = [
        "ANÁLISE VISUAL (VEXX-AI Vision API / YOLOv8 + RapidOCR — objetos, textos lidos e coordenadas de clique):"
    ]
    tags_globais = coletar_tags_busca(sucessos)
    if tags_globais:
        linhas.append(f"- Tags de busca (tags_busca): {tags_globais}")
    else:
        linhas.append("- Tags de busca (tags_busca): nenhum objeto com confiança >= 0.35")

    texto_global = coletar_texto_extraido(sucessos)
    if texto_global:
        linhas.append(f"- Texto lido nas fontes da imagem (texto_extraido): \"{texto_global[:800]}\"")

    for idx, res in enumerate(sucessos, start=1):
        origem = res.get("origem") or f"imagem_{idx}"
        total_obj = int(res.get("total_objetos") or len(res.get("deteccoes") or []))
        total_txt = int(res.get("total_textos") or len(res.get("textos_lidos") or []))
        deteccoes = res.get("deteccoes") or []
        textos_lidos = res.get("textos_lidos") or []

        if deteccoes:
            itens_fmt = []
            for d in deteccoes[:15]:
                obj = d.get("objeto", "objeto")
                conf = d.get("confianca", 0.0)
                coords = d.get("coordenadas", [])
                pt = d.get("ponto_clique") or {}
                itens_fmt.append(
                    f"{obj} (confiança={conf}, coordenadas={coords}, "
                    f"clique=({pt.get('x', 0)}, {pt.get('y', 0)} | norm={pt.get('x_norm', 0.0)}, {pt.get('y_norm', 0.0)}))"
                )
            linhas.append(
                f"- Imagem {idx} ({origem}, total_objetos={total_obj}): " + "; ".join(itens_fmt)
            )
        else:
            linhas.append(f"- Imagem {idx} ({origem}): nenhum objeto detectado (total_objetos=0).")

        if textos_lidos:
            txts_fmt = []
            for t in textos_lidos[:20]:
                txt = t.get("texto", "")
                conf = t.get("confianca", 0.0)
                pt = t.get("ponto_clique") or {}
                txts_fmt.append(
                    f"\"{txt}\" (conf={conf}, clique=({pt.get('x', 0)}, {pt.get('y', 0)} | norm={pt.get('x_norm', 0.0)}, {pt.get('y_norm', 0.0)}))"
                )
            linhas.append(
                f"- Textos/Fontes lidos na Imagem {idx} (total_textos={total_txt}): " + "; ".join(txts_fmt)
            )

    linhas.append(
        "Use estas tags_busca, o texto_extraido (OCR) e as coordenadas/ponto_clique reais para responder com precisão, "
        "contextualizar a pesquisa e localizar elementos clicáveis."
    )
    return "\n".join(linhas)
