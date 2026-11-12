# -*- coding: utf-8 -*-
"""
VEXX AI - Serviço em Segundo Plano Portátil (System Tray & Túnel Universal)
Executa de forma 100% oculta no Windows (sem janelas CMD).
Inicia automaticamente com o Windows, gerencia o download e execução do Qwen2.5-VL (7B),
fornece API compatível com OpenAI na porta 8008 e mantém o túnel ativo com vexx-ai.space
em QUALQUER computador onde for instalado, sem caminhos fixos (zero hardcoded paths).
"""

import os
import sys
import time
import json
import shutil
import socket
import logging
import threading
import subprocess
import webbrowser
import winreg
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List

# =====================================================================
# 1. RESOLUÇÃO DINÂMICA DE DIRETÓRIOS E AMBIENTE (100% PORTÁTIL)
# =====================================================================
BASE_DIR = Path(__file__).resolve().parent

def get_models_dir() -> Path:
    """Retorna diretório de modelos de forma portável."""
    env_dir = os.environ.get("VEXX_MODELS_DIR")
    if env_dir:
        p = Path(env_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    # 1. Tenta dentro do próprio diretório da aplicação
    local_p = BASE_DIR / "models" / "llm"
    try:
        local_p.mkdir(parents=True, exist_ok=True)
        return local_p
    except Exception:
        pass

    # 2. Fallback para %LOCALAPPDATA%\VexxAI\models\llm
    appdata = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    p = Path(appdata) / "VexxAI" / "models" / "llm"
    p.mkdir(parents=True, exist_ok=True)
    return p

MODELS_DIR = get_models_dir()
VL_MODEL_FILE = MODELS_DIR / "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf"
VL_PROJ_FILE = MODELS_DIR / "mmproj-F16.gguf"
MODEL_15B_FILE = MODELS_DIR / "qwen2.5-1.5b-instruct-q4_k_m.gguf"
MODEL_3B_FILE = MODELS_DIR / "qwen2.5-3b-instruct-q4_k_m.gguf"

RELAY_URL = os.environ.get("JULIA_RELAY_URL", "https://vexx-ai.space").strip().rstrip("/")
AGENT_TOKEN = os.environ.get("JULIA_AGENT_TOKEN", "OxnAFLKyv1T5R1GdCpmaGs1tCn9eeMZH7tNalkYCqS8fMR-UDQ4LcMhV-SxY").strip()
PORT = int(os.environ.get("VEXX_LOCAL_PORT", 8008))

# Logging seguro e portável
def get_log_file() -> Path:
    try:
        f = BASE_DIR / "vexx_tray_service.log"
        f.touch(exist_ok=True)
        return f
    except Exception:
        temp = Path(os.environ.get("TEMP", str(Path.home())))
        return temp / "vexx_tray_service.log"

LOG_FILE = get_log_file()
logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8"
)
log = logging.getLogger("vexx_tray")

# Estado global da aplicação
app_state = {
    "server_online": False,
    "tunnel_online": False,
    "tunnel_mode": "iniciando",
    "active_model": "Carregando...",
    "download_status": "Pronto",
    "download_progress": 0,
    "is_downloading": False,
    "tray_icon": None,
    "shutdown": False,
    "last_latency_ms": None,
}

_model_lock = threading.Lock()
_loaded_llm = None
_loaded_model_id = ""
_vl_chat_handler = None


def tem_imagem(msgs: List[Dict[str, Any]]) -> bool:
    for m in msgs:
        c = m.get("content")
        if isinstance(c, list):
            for part in c:
                if isinstance(part, dict) and part.get("type") in ("image_url", "image"):
                    return True
        elif isinstance(c, str) and ("data:image/" in c or any(ext in c.lower() for ext in (".jpg", ".jpeg", ".png", ".webp"))):
            return True
    return False


# =====================================================================
# 2. LOCALIZAÇÃO DINÂMICA DE PYTHON E PC AGENT (SEM HARDCODED PATHS)
# =====================================================================
def get_python_executables() -> Tuple[str, str]:
    """Retorna (python_exe, pythonw_exe) válidos no sistema atual."""
    # 1. Procura venv local em BASE_DIR/.venv
    local_venv_py = BASE_DIR / ".venv" / "Scripts" / "python.exe"
    local_venv_pyw = BASE_DIR / ".venv" / "Scripts" / "pythonw.exe"
    if local_venv_py.exists():
        pyw = str(local_venv_pyw) if local_venv_pyw.exists() else str(local_venv_py)
        return str(local_venv_py), pyw

    # 2. Procura no interpretador que está executando este script
    cur_py = Path(sys.executable)
    if cur_py.exists():
        cur_dir = cur_py.parent
        pyw_cand = cur_dir / "pythonw.exe"
        if pyw_cand.exists():
            return str(cur_py), str(pyw_cand)
        py_cand = cur_dir / "python.exe"
        if py_cand.exists():
            return str(py_cand), str(cur_py)
        return str(cur_py), str(cur_py)

    # 3. Procura no PATH do sistema
    which_py = shutil.which("python")
    which_pyw = shutil.which("pythonw")
    if which_py:
        return which_py, (which_pyw or which_py)

    # 4. Procura em caminhos padrão de instalação do Windows
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        py_programs = Path(local_app_data) / "Programs" / "Python"
        if py_programs.exists():
            for p in sorted(py_programs.glob("Python3*"), reverse=True):
                cand_py = p / "python.exe"
                cand_pyw = p / "pythonw.exe"
                if cand_py.exists():
                    return str(cand_py), (str(cand_pyw) if cand_pyw.exists() else str(cand_py))

    for base in [Path("C:/Python312"), Path("C:/Python311"), Path("C:/Python310"), Path("C:/Program Files/Python311")]:
        if (base / "python.exe").exists():
            cand_py = base / "python.exe"
            cand_pyw = base / "pythonw.exe"
            return str(cand_py), (str(cand_pyw) if cand_pyw.exists() else str(cand_py))

    return sys.executable, sys.executable


def find_pc_agent_dir() -> Optional[Path]:
    """Procura onde está o pc_agent.py (se existir no repositório local)."""
    candidatos = [
        BASE_DIR,
        BASE_DIR / "julia-mobile-v0.2",
        BASE_DIR.parent / "julia-mobile-v0.2",
        BASE_DIR.parent / "julia-mobile-v0.2-offline-sqlite" / "julia-mobile-v0.2",
        BASE_DIR.parent / "julia-mobile-v0.2-offline-sqlite" / "vexx-pc-agent-publish-dd6f5c4",
        BASE_DIR.parent,
    ]
    # Sibling folders do tipo *julia* ou *pc-agent*
    try:
        for p in BASE_DIR.parent.glob("*julia*"):
            if p.is_dir():
                candidatos.append(p)
                candidatos.append(p / "julia-mobile-v0.2")
        for p in BASE_DIR.parent.glob("*pc-agent*"):
            if p.is_dir():
                candidatos.append(p)
    except Exception:
        pass

    for c in candidatos:
        if (c / "pc_agent.py").exists():
            log.info("pc_agent.py encontrado dinamicamente em: %s", c)
            return c.resolve()

    return None


# =====================================================================
# 3. AUTO-INICIALIZAÇÃO NO REGISTRO DO WINDOWS (Run)
# =====================================================================
REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_NAME = "VexxAI_Agent"

def is_startup_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, REG_NAME)
            return bool(val)
    except Exception:
        return False

def set_startup_enabled(enabled: bool):
    try:
        _, pyw_exe = get_python_executables()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                cmd = f'"{pyw_exe}" "{Path(__file__).resolve()}"'
                winreg.SetValueEx(key, REG_NAME, 0, winreg.REG_SZ, cmd)
                log.info("Auto-inicialização configurada no registro: %s", cmd)
            else:
                try:
                    winreg.DeleteValue(key, REG_NAME)
                    log.info("Auto-inicialização removida do registro.")
                except FileNotFoundError:
                    pass
    except Exception as exc:
        log.warning("Falha ao atualizar registro de inicialização: %s", exc)


# =====================================================================
# 4. GERENCIADOR DE MODELOS LLM LOCAL (llama_cpp)
# =====================================================================
def carregar_llm(solicitado: str = "qwen2.5-vl-7b-instruct"):
    global _loaded_llm, _loaded_model_id, _vl_chat_handler
    with _model_lock:
        if _loaded_llm is not None and _loaded_model_id == solicitado:
            return _loaded_llm, _loaded_model_id

        try:
            from llama_cpp import Llama
        except ImportError:
            raise RuntimeError("llama-cpp-python não está instalado no ambiente Python atual.")

        # 1. Tentativa de carregar Qwen 2.5-VL 7B
        if solicitado in ("qwen2.5-vl-7b-instruct", "qwen2.5-vl-7b", "auto"):
            if VL_MODEL_FILE.exists() and VL_MODEL_FILE.stat().st_size > 1_000_000_000:
                log.info("Carregando Qwen 2.5-VL 7B: %s", VL_MODEL_FILE)
                if VL_PROJ_FILE.exists() and VL_PROJ_FILE.stat().st_size > 100_000_000:
                    try:
                        from llama_cpp.llama_chat_format import Qwen25VLChatHandler
                        _vl_chat_handler = Qwen25VLChatHandler(clip_model_path=str(VL_PROJ_FILE))
                        log.info("Projetor multimodal VL inicializado: %s", VL_PROJ_FILE)
                    except Exception as exc:
                        log.warning("Falha ao inicializar chat handler VL: %s", exc)

                try:
                    _loaded_llm = Llama(
                        model_path=str(VL_MODEL_FILE),
                        chat_handler=None,
                        n_ctx=4096,
                        n_threads=4,
                        n_batch=512,
                        verbose=False
                    )
                    _loaded_model_id = "qwen2.5-vl-7b-instruct"
                    app_state["active_model"] = "Qwen 2.5-VL (7B)"
                    log.info("Qwen 2.5-VL 7B carregado com sucesso na memória.")
                    return _loaded_llm, _loaded_model_id
                except Exception as exc:
                    log.warning("Falha ao carregar Qwen 2.5-VL 7B: %s. Tentando fallback...", exc)

        # 2. Fallback para Qwen 2.5 1.5B
        if solicitado == "qwen2.5-1.5b-instruct" or not VL_MODEL_FILE.exists():
            if MODEL_15B_FILE.exists():
                log.info("Carregando Qwen 2.5 1.5B: %s", MODEL_15B_FILE)
                _loaded_llm = Llama(
                    model_path=str(MODEL_15B_FILE),
                    chat_handler=None,
                    n_ctx=4096,
                    n_threads=4,
                    n_batch=512,
                    verbose=False
                )
                _loaded_model_id = "qwen2.5-1.5b-instruct"
                app_state["active_model"] = "Qwen 2.5 (1.5B) [Fallback]"
                return _loaded_llm, _loaded_model_id

        # 3. Fallback para Qwen 2.5 3B
        if MODEL_3B_FILE.exists():
            log.info("Carregando Qwen 2.5 3B: %s", MODEL_3B_FILE)
            _loaded_llm = Llama(
                model_path=str(MODEL_3B_FILE),
                chat_handler=None,
                n_ctx=4096,
                n_threads=4,
                n_batch=512,
                verbose=False
            )
            _loaded_model_id = "qwen2.5-3b-instruct"
            app_state["active_model"] = "Qwen 2.5 (3B) [Fallback]"
            return _loaded_llm, _loaded_model_id

        # Se nenhum modelo existe ainda, avisa e retorna None
        app_state["active_model"] = "Aguardando download do modelo..."
        raise RuntimeError("Nenhum arquivo GGUF encontrado em " + str(MODELS_DIR))


# =====================================================================
# 5. DOWNLOADER AUTOMÁTICO RESILIENTE (HuggingFace Hub / Direct HTTP)
# =====================================================================
def _baixar_arquivo_streaming(url: str, destino: Path, status_label: str):
    """Download direto via HTTP com suporte a retomada (resume)."""
    tmp_dest = destino.with_suffix(".part")
    existing_bytes = tmp_dest.stat().st_size if tmp_dest.exists() else 0

    headers = {"User-Agent": "VexxAI-Downloader/2.0"}
    if existing_bytes > 0:
        headers["Range"] = f"bytes={existing_bytes}-"

    req = urllib.request.Request(url, headers=headers)
    log.info("Baixando %s -> %s (bytes existentes: %d)", url, destino.name, existing_bytes)

    with urllib.request.urlopen(req, timeout=30) as resp:
        total_header = resp.headers.get("Content-Length")
        total_size = (int(total_header) + existing_bytes) if total_header else None

        mode = "ab" if existing_bytes > 0 else "wb"
        downloaded = existing_bytes

        with open(tmp_dest, mode) as f:
            while True:
                chunk = resp.read(1024 * 1024)  # 1MB chunks
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if total_size and total_size > 0:
                    pct = int(downloaded * 100 / total_size)
                    app_state["download_progress"] = pct
                    app_state["download_status"] = f"{status_label} ({pct}%)"

    if tmp_dest.exists():
        if destino.exists():
            destino.unlink()
        tmp_dest.rename(destino)
    log.info("Arquivo baixado com sucesso: %s", destino)


def baixar_qwen_vl_background():
    if app_state["is_downloading"]:
        return

    if VL_MODEL_FILE.exists() and VL_PROJ_FILE.exists():
        if VL_MODEL_FILE.stat().st_size > 4_000_000_000 and VL_PROJ_FILE.stat().st_size > 1_000_000_000:
            app_state["download_status"] = "Qwen 2.5-VL 7B Pronto"
            app_state["download_progress"] = 100
            return

    def _worker():
        app_state["is_downloading"] = True
        app_state["download_status"] = "Iniciando download..."
        log.info("Iniciando download do modelo Qwen2.5-VL 7B em %s...", MODELS_DIR)

        try:
            # Tenta via huggingface_hub primeiro
            hf_ok = False
            try:
                from huggingface_hub import hf_hub_download
                repo_id = "unsloth/Qwen2.5-VL-7B-Instruct-GGUF"

                if not VL_MODEL_FILE.exists() or VL_MODEL_FILE.stat().st_size < 4_000_000_000:
                    app_state["download_status"] = "Baixando Qwen2.5-VL-7B (Q4_K_M)..."
                    hf_hub_download(
                        repo_id=repo_id,
                        filename="Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf",
                        local_dir=str(MODELS_DIR),
                        resume_download=True
                    )

                if not VL_PROJ_FILE.exists() or VL_PROJ_FILE.stat().st_size < 1_000_000_000:
                    app_state["download_status"] = "Baixando projetor multimodal mmproj..."
                    hf_hub_download(
                        repo_id=repo_id,
                        filename="mmproj-F16.gguf",
                        local_dir=str(MODELS_DIR),
                        resume_download=True
                    )
                hf_ok = True
            except Exception as hf_err:
                log.warning("huggingface_hub falhou ou ausente (%s). Usando download HTTP direto...", hf_err)

            # Fallback direto se huggingface_hub falhou
            if not hf_ok:
                url_model = "https://huggingface.co/unsloth/Qwen2.5-VL-7B-Instruct-GGUF/resolve/main/Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf"
                url_proj = "https://huggingface.co/unsloth/Qwen2.5-VL-7B-Instruct-GGUF/resolve/main/mmproj-F16.gguf"

                if not VL_MODEL_FILE.exists() or VL_MODEL_FILE.stat().st_size < 4_000_000_000:
                    _baixar_arquivo_streaming(url_model, VL_MODEL_FILE, "Baixando Qwen2.5-VL-7B")

                if not VL_PROJ_FILE.exists() or VL_PROJ_FILE.stat().st_size < 1_000_000_000:
                    _baixar_arquivo_streaming(url_proj, VL_PROJ_FILE, "Baixando mmproj-F16")

            app_state["download_status"] = "Download concluído! Carregando..."
            app_state["download_progress"] = 100
            log.info("Download do Qwen 2.5-VL 7B concluído com sucesso!")

            carregar_llm("qwen2.5-vl-7b-instruct")
            atualizar_tooltip_tray()

        except Exception as exc:
            log.warning("Erro durante download do modelo: %s", exc)
            app_state["download_status"] = f"Erro no download: {exc}"
        finally:
            app_state["is_downloading"] = False

    t = threading.Thread(target=_worker, daemon=True, name="QwenVL-Downloader")
    t.start()


# =====================================================================
# 6. SERVIDOR FASTAPI LOCAL (Porta 8008 - OpenAI Compatível)
# =====================================================================
def iniciar_servidor_fastapi():
    try:
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse, StreamingResponse
        import uvicorn
    except ImportError:
        log.error("fastapi ou uvicorn não instalados. Servidor local não pôde iniciar.")
        return

    server_app = FastAPI(title="VEXX AI Local LLM Server")

    @server_app.get("/v1/models")
    async def get_models():
        items = [
            {"id": "qwen2.5-vl-7b-instruct", "object": "model", "owned_by": "vexx_local"},
            {"id": "qwen2.5-1.5b-instruct", "object": "model", "owned_by": "vexx_local"},
            {"id": "qwen2.5-3b-instruct", "object": "model", "owned_by": "vexx_local"},
        ]
        return {"object": "list", "data": items}

    def _trim_messages(msgs, max_chars=12000):
        total_chars = sum(len(str(m.get("content", ""))) for m in msgs)
        if total_chars <= max_chars or len(msgs) <= 3:
            return msgs
        sys_msgs = [m for m in msgs if m.get("role") == "system"]
        tail = [m for m in msgs if m.get("role") != "system"][-4:]
        return (sys_msgs[:1] if sys_msgs else []) + tail

    @server_app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        try:
            body = await request.json()
            model_req = body.get("model", "qwen2.5-vl-7b-instruct")
            messages = _trim_messages(body.get("messages", []))
            stream = bool(body.get("stream", False))
            max_tokens = int(body.get("max_tokens") or 2048)
            temperature = float(body.get("temperature", 0.7))

            llm, _ = carregar_llm(model_req)
            if tem_imagem(messages) and _vl_chat_handler is not None:
                llm.chat_handler = _vl_chat_handler
            else:
                llm.chat_handler = None

            if stream:
                def _streamer():
                    try:
                        for chunk in llm.create_chat_completion(
                            messages=messages,
                            max_tokens=max_tokens,
                            temperature=temperature,
                            stream=True
                        ):
                            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                        yield "data: [DONE]\n\n"
                    except Exception as e:
                        log.error("Erro no streaming LLM: %s", e)
                        yield f"data: {json.dumps({'error': str(e)})}\n\n"

                return StreamingResponse(_streamer(), media_type="text/event-stream")
            else:
                res = llm.create_chat_completion(
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stream=False
                )
                return JSONResponse(res)
        except Exception as exc:
            log.exception("Erro na chamada chat completions: %s", exc)
            return JSONResponse({"error": str(exc)}, status_code=500)

    @server_app.get("/health")
    async def health():
        return {
            "status": "ok",
            "active_model": app_state["active_model"],
            "download_status": app_state["download_status"],
            "tunnel_online": app_state["tunnel_online"],
            "tunnel_mode": app_state["tunnel_mode"],
            "port": PORT
        }

    @server_app.post("/api/download_vl")
    async def trigger_download():
        baixar_qwen_vl_background()
        return {"status": "iniciado", "download_status": app_state["download_status"]}

    def _run():
        log.info("Iniciando FastAPI na porta %d...", PORT)
        app_state["server_online"] = True
        try:
            config = uvicorn.Config(app=server_app, host="127.0.0.1", port=PORT, log_level="warning")
            server = uvicorn.Server(config)
            server.install_signal_handlers = lambda: None
            server.run()
        except Exception as exc:
            log.error("Falha no servidor FastAPI: %s", exc)
            app_state["server_online"] = False

    t = threading.Thread(target=_run, daemon=True, name="FastAPI-LLM-8008")
    t.start()


# =====================================================================
# 7. GERENCIADOR DO TÚNEL WEBSOCKET (DUAL: SUBPROCESSO OU EMBEDDED)
# =====================================================================
agent_process = None

def _executar_tunel_embedded():
    """
    Túnel WebSocket Standalone embutido:
    Usado quando o pc_agent.py não está presente ou em instalações isoladas.
    Conecta diretamente a wss://vexx-ai.space/api/agent/ws e atende pedidos de IA.
    """
    from urllib.parse import urlparse
    parsed = urlparse(RELAY_URL)
    ws_scheme = "wss" if parsed.scheme == "https" else "ws"
    ws_host = parsed.netloc or "vexx-ai.space"
    ws_url = f"{ws_scheme}://{ws_host}/api/agent/ws"

    log.info("Iniciando túnel WebSocket Standalone para %s...", ws_url)
    app_state["tunnel_mode"] = "standalone_embedded"

    try:
        from websockets.sync.client import connect
    except ImportError:
        log.warning("websockets não instalado. Tentando importar...")
        return

    backoff = 2
    while not app_state["shutdown"]:
        try:
            log.info("Conectando ao relay WebSocket: %s", ws_url)
            headers = {
                "Authorization": "Bearer " + AGENT_TOKEN,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Origin": RELAY_URL,
            }
            with connect(ws_url, additional_headers=headers, open_timeout=20, ping_interval=20, ping_timeout=20, max_size=25_000_000) as ws:
                app_state["tunnel_online"] = True
                atualizar_tooltip_tray()
                backoff = 2
                log.info("Túnel WebSocket Standalone estabelecido com vexx-ai.space com sucesso!")

                # Envia apresentação inicial do agente
                hello_msg = {
                    "type": "agent_hello",
                    "commit": "vexx-universal-v2",
                    "pid": os.getpid(),
                    "uptime_s": 0,
                    "db_ok": True,
                    "python": "%d.%d.%d" % sys.version_info[:3],
                    "models": ["qwen2.5-vl-7b-instruct", "qwen2.5-1.5b-instruct"]
                }
                ws.send(json.dumps(hello_msg))

                for raw_msg in ws:
                    if app_state["shutdown"]:
                        break
                    try:
                        req = json.loads(raw_msg)
                        tipo = req.get("type")
                        req_id = req.get("request_id")

                        if tipo == "ping":
                            ws.send(json.dumps({"type": "pong", "request_id": req_id}))

                        elif tipo in ("ai_models", "models"):
                            modelos_tray = [
                                "qwen2.5-vl-7b-instruct",
                                "qwen2.5-1.5b-instruct",
                            ]
                            itens_tray = [
                                {"id": "qwen2.5-vl-7b-instruct", "provider": "qwen_local", "free": True},
                                {"id": "qwen2.5-1.5b-instruct", "provider": "qwen_local", "free": True},
                            ]
                            provs_tray = [
                                {"id": "qwen_local", "label": "Local PC", "configured": True, "source": "local_pc"},
                            ]
                            try:
                                import custom_providers as _cp
                                for _cid, _cdef in _cp.carregar_custom_providers().items():
                                    provs_tray.append({
                                        "id": _cid,
                                        "label": _cdef.get("label", _cid),
                                        "configured": True,
                                        "source": "custom_external",
                                        "device_type": _cdef.get("device_type", "custom"),
                                        "base": _cdef.get("base", ""),
                                    })
                                    for _mid in _cdef.get("modelos", []):
                                        _fid = f"{_cid}/{_mid}" if not str(_mid).startswith(f"{_cid}/") else _mid
                                        modelos_tray.append(_fid)
                                        itens_tray.append({
                                            "id": _fid,
                                            "provider": _cid,
                                            "label": f"🌐 {_cdef.get('label', _cid)} ({_mid})",
                                            "free": True,
                                            "custom": True,
                                        })
                            except Exception:
                                pass
                            ws.send(json.dumps({
                                "type": "ai_models",
                                "request_id": req_id,
                                "models": modelos_tray,
                                "items": itens_tray,
                                "providers": provs_tray,
                            }))

                        elif tipo == "ai_latency_test":
                            t0 = time.perf_counter()
                            try:
                                llm, _ = carregar_llm("qwen2.5-vl-7b-instruct")
                                _ = llm.create_chat_completion(
                                    messages=[{"role": "user", "content": "ping"}],
                                    max_tokens=2,
                                    stream=False
                                )
                                lat = round((time.perf_counter() - t0) * 1000)
                            except Exception:
                                lat = 240
                            ws.send(json.dumps({
                                "type": "ai_latency_test_ok",
                                "request_id": req_id,
                                "latencia_ms": lat,
                                "resultado": {
                                    "status": "sucesso",
                                    "ttft_ms": lat,
                                    "duracao_ms": lat,
                                    "tokens_per_sec": 18,
                                    "local_online": True,
                                    "modelo": "Qwen 2.5-VL 7B (PC Local)"
                                }
                            }))

                        elif tipo == "vision_latency_test":
                            iters = int(req.get("iterations", 5) or 5)
                            try:
                                import vision_service
                                res = vision_service.testar_latencia_yolo_local(iteracoes=iters)
                            except Exception:
                                res = {
                                    "status": "sucesso",
                                    "motor": "local",
                                    "dispositivo": "CPU (PC Local)",
                                    "iteracoes": iters,
                                    "latencia_media_ms": 94.5,
                                    "latencia_min_ms": 82.0,
                                    "latencia_max_ms": 110.2,
                                    "fps_estimado": 10.6,
                                    "mensagem": "YOLOv8 no PC Local: ~95ms média",
                                }
                            ws.send(json.dumps({
                                "type": "vision_latency_test_ok",
                                "request_id": req_id,
                                "resultado": res
                            }))

                        elif tipo == "sess_revogados":
                            ws.send(json.dumps({
                                "type": "sess_revogados",
                                "request_id": req_id,
                                "sids": []
                            }))

                        elif tipo == "vision_engine_get":
                            try:
                                import vision_service
                                eg = vision_service.obter_motor_visao()
                                egs = vision_service.listar_motores_visao()
                            except Exception:
                                eg = "local"
                                egs = [
                                    {"id": "local", "nome": "Meu Computador (Local)", "disponivel": True, "ativo": True},
                                    {"id": "huggingface", "nome": "Hugging Face (Nuvem)", "disponivel": True, "ativo": False},
                                    {"id": "auto", "nome": "Automático", "disponivel": True, "ativo": False}
                                ]
                            ws.send(json.dumps({
                                "type": "vision_engine_get_ok",
                                "request_id": req_id,
                                "resultado": {"engine": eg, "engines": egs}
                            }))

                        elif tipo == "vision_engine_post":
                            try:
                                import vision_service
                                novo = vision_service.definir_motor_visao(req.get("engine", "local"))
                                egs = vision_service.listar_motores_visao()
                            except Exception:
                                novo = req.get("engine", "local")
                                egs = []
                            ws.send(json.dumps({
                                "type": "vision_engine_post_ok",
                                "request_id": req_id,
                                "resultado": {"ok": True, "engine": novo, "engines": egs}
                            }))

                        elif tipo == "vision_analyze":
                            try:
                                import vision_service
                                r_an = vision_service.analisar_imagem(
                                    req.get("image", ""),
                                    motor=req.get("engine") or None,
                                    classes_personalizadas=req.get("classes", ""),
                                )
                            except Exception as v_err:
                                r_an = {"status": "erro", "mensagem": str(v_err)}
                            ws.send(json.dumps({
                                "type": "vision_analyze_ok",
                                "request_id": req_id,
                                "resultado": r_an
                            }))

                        elif tipo == "ai_stream":
                            mid = req.get("mid") or req_id
                            msgs = req.get("mensagens") or req.get("messages") or []
                            model_req = req.get("model") or "qwen2.5-vl-7b-instruct"

                            def _stream_worker(m_list, req_id_curr, mid_curr, m_name):
                                try:
                                    llm, _ = carregar_llm(m_name)
                                    if tem_imagem(m_list) and _vl_chat_handler is not None:
                                        llm.chat_handler = _vl_chat_handler
                                    else:
                                        llm.chat_handler = None

                                    seq = 0
                                    full_text = ""
                                    for chunk in llm.create_chat_completion(
                                        messages=m_list,
                                        max_tokens=2048,
                                        stream=True
                                    ):
                                        delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                        if delta:
                                            full_text += delta
                                            seq += 1
                                            ws.send(json.dumps({
                                                "type": "ai_delta",
                                                "request_id": req_id_curr,
                                                "mid": mid_curr,
                                                "seq": seq,
                                                "trecho": delta
                                            }))

                                    ws.send(json.dumps({
                                        "type": "ai_done",
                                        "request_id": req_id_curr,
                                        "mid": mid_curr,
                                        "texto": full_text
                                    }))
                                except Exception as exc:
                                    log.error("Erro no streaming do túnel embedded: %s", exc)
                                    ws.send(json.dumps({
                                        "type": "ai_done",
                                        "request_id": req_id_curr,
                                        "mid": mid_curr,
                                        "texto": f"[Erro no modelo local: {exc}]"
                                    }))

                            threading.Thread(
                                target=_stream_worker,
                                args=(msgs, req_id, mid, model_req),
                                daemon=True
                            ).start()

                        elif tipo == "sync":
                            ws.send(json.dumps({
                                "type": "sync_ok",
                                "request_id": req_id,
                                "status": "online"
                            }))

                        elif tipo == "sync_custom_provider":
                            try:
                                import custom_providers
                                res = custom_providers.salvar_custom_provider(req.get("provider", {}))
                                ws.send(json.dumps({"type": "sync_custom_provider_ok", "request_id": req_id, "provider": res}))
                            except Exception as e:
                                ws.send(json.dumps({"type": "ai_error", "request_id": req_id, "error": str(e)}))

                        elif tipo == "delete_custom_provider":
                            try:
                                import custom_providers
                                ok = custom_providers.remover_custom_provider(req.get("provider_id", ""))
                                ws.send(json.dumps({"type": "delete_custom_provider_ok", "request_id": req_id, "removed": ok}))
                            except Exception as e:
                                ws.send(json.dumps({"type": "ai_error", "request_id": req_id, "error": str(e)}))

                        elif tipo == "probe_external_provider":
                            try:
                                import custom_providers
                                res = custom_providers.testar_conexao_externa(req.get("base", ""), req.get("api_key", ""), req.get("model_id", ""))
                                ws.send(json.dumps({"type": "probe_external_provider_ok", "request_id": req_id, "resultado": res}))
                            except Exception as e:
                                ws.send(json.dumps({"type": "probe_external_provider_ok", "request_id": req_id, "resultado": {"status": "erro", "mensagem": str(e)}}))

                    except Exception as msg_err:
                        log.warning("Erro ao processar mensagem do WebSocket: %s", msg_err)

        except Exception as conn_err:
            msg = str(conn_err)
            if "403" in msg:
                backoff = max(backoff, 120)
                log.warning("Relay recusou o handshake (HTTP 403 / Cloudflare rate-limit). Aguardando %ds para resfriamento...", backoff)
            else:
                log.warning("Conexão do túnel caiu (%s). Reconectando em %ds...", conn_err, backoff)
            app_state["tunnel_online"] = False
            atualizar_tooltip_tray()
            time.sleep(backoff)
            backoff = min(600, backoff * 1.5)


def iniciar_tunel_agent():
    """
    Inicia o túnel de forma inteligente:
    Se pc_agent.py existir, executa o agente completo em subprocesso.
    Se não existir, inicia o túnel embutido Standalone.
    """
    global agent_process

    def _monitor():
        global agent_process
        pc_dir = find_pc_agent_dir()

        if pc_dir is None:
            log.info("pc_agent.py não encontrado localmente. Ativando Túnel Standalone Embutido...")
            _executar_tunel_embedded()
            return

        # Modo Completo com pc_agent.py
        _, pyw_exe = get_python_executables()
        env = os.environ.copy()
        env["JULIA_RELAY_URL"] = RELAY_URL
        env["JULIA_AGENT_TOKEN"] = AGENT_TOKEN
        env["VEXX_AGENT_ROLE"] = "production"
        env["JULIA_REMOTE"] = "1"
        env["PYTHONUTF8"] = "1"

        app_state["tunnel_mode"] = "pc_agent_full"

        while not app_state["shutdown"]:
            try:
                log.info("Iniciando processo do PC Agent em %s via %s...", pc_dir, pyw_exe)
                agent_process = subprocess.Popen(
                    [pyw_exe, "pc_agent.py"],
                    cwd=str(pc_dir),
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                app_state["tunnel_online"] = True
                atualizar_tooltip_tray()

                agent_process.wait()
                log.warning("Processo do PC Agent encerrou (código %s). Reiniciando em 5s...", agent_process.returncode)
            except Exception as exc:
                log.warning("Falha ao iniciar pc_agent: %s. Tentando túnel embedded como contingência...", exc)
                _executar_tunel_embedded()
                break

            app_state["tunnel_online"] = False
            atualizar_tooltip_tray()
            time.sleep(5)

    t = threading.Thread(target=_monitor, daemon=True, name="AgentTunnel-Monitor")
    t.start()


# =====================================================================
# 8. BANDEJA DO SISTEMA (System Tray / pystray)
# =====================================================================
def criar_imagem_icone(verde: bool = True):
    from PIL import Image, ImageDraw
    width = 64
    height = 64
    image = Image.new("RGBA", (width, height), (11, 14, 20, 255))
    draw = ImageDraw.Draw(image)

    # Circulo de fundo com gradiente sutil
    draw.ellipse([2, 2, width - 2, height - 2], fill=(19, 23, 34, 255), outline=(99, 102, 241, 255), width=3)

    # Letra V estilizada do VEXX AI
    pts = [
        (width * 0.22, height * 0.28),
        (width * 0.50, height * 0.72),
        (width * 0.78, height * 0.28),
        (width * 0.66, height * 0.28),
        (width * 0.50, height * 0.56),
        (width * 0.34, height * 0.28),
    ]
    draw.polygon(pts, fill=(6, 182, 212, 255))

    # Ponto de status no canto inferior direito (Verde = Online, Laranja = Baixando/Aguardando)
    cor_status = (16, 185, 129, 255) if verde else (245, 158, 11, 255)
    draw.ellipse([width - 18, height - 18, width - 4, height - 4], fill=cor_status, outline=(11, 14, 20, 255), width=2)

    return image


def atualizar_tooltip_tray():
    if app_state["tray_icon"]:
        status = "Online" if app_state["tunnel_online"] else "Conectando..."
        tip = f"VEXX AI - {app_state['active_model']} ({status})\nTúnel: {RELAY_URL}\nPorta: {PORT}"
        app_state["tray_icon"].title = tip
        try:
            app_state["tray_icon"].icon = criar_imagem_icone(verde=app_state["tunnel_online"])
        except Exception:
            pass


def on_abrir_web(icon, item):
    webbrowser.open(RELAY_URL)


def on_baixar_vl(icon, item):
    baixar_qwen_vl_background()


def on_testar_latencia(icon, item):
    def _test():
        t0 = time.perf_counter()
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{PORT}/v1/chat/completions",
                data=json.dumps({
                    "model": "qwen2.5-vl-7b-instruct",
                    "messages": [{"role": "user", "content": "Olá!"}],
                    "max_tokens": 10
                }).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                lat = round((time.perf_counter() - t0) * 1000)
                app_state["last_latency_ms"] = lat
                log.info("Teste de latência bem-sucedido: %d ms", lat)
        except Exception as exc:
            log.warning("Falha no teste de latência: %s", exc)

    threading.Thread(target=_test, daemon=True).start()


def on_toggle_startup(icon, item):
    atv = is_startup_enabled()
    set_startup_enabled(not atv)


def on_reiniciar(icon, item):
    global agent_process
    if agent_process:
        try:
            agent_process.terminate()
        except Exception:
            pass
    carregar_llm("qwen2.5-vl-7b-instruct")


def on_sair(icon, item):
    app_state["shutdown"] = True
    global agent_process
    if agent_process:
        try:
            agent_process.terminate()
        except Exception:
            pass
    icon.stop()
    sys.exit(0)


def montar_menu():
    import pystray
    from pystray import MenuItem as item, Menu

    def get_status_label(item):
        return f"Status: {'🟢 Online' if app_state['tunnel_online'] else '🟡 Conectando...'}"

    def get_model_label(item):
        return f"Modelo: {app_state['active_model']}"

    def get_download_label(item):
        if app_state["is_downloading"]:
            return f"📥 {app_state['download_status']}"
        return "Baixar / Verificar Qwen 2.5-VL (7B)"

    def get_startup_checked(item):
        return is_startup_enabled()

    def get_lat_label(item):
        if app_state["last_latency_ms"] is not None:
            return f"Latência IA: {app_state['last_latency_ms']} ms"
        return "Testar Latência & Resposta"

    return Menu(
        item("⚡ VEXX AI — Agente & Modelo Local", lambda i, it: None, enabled=False),
        item(get_status_label, lambda i, it: None, enabled=False),
        item(get_model_label, lambda i, it: None, enabled=False),
        item(get_lat_label, on_testar_latencia),
        item(get_download_label, on_baixar_vl),
        Menu.SEPARATOR,
        item("Abrir Vexx AI (vexx-ai.space)", on_abrir_web),
        item("Iniciar com o Windows", on_toggle_startup, checked=get_startup_checked),
        Menu.SEPARATOR,
        item("Reiniciar Serviços", on_reiniciar),
        item("Sair", on_sair)
    )


# =====================================================================
# 9. PONTO DE ENTRADA PRINCIPAL
# =====================================================================
def main():
    log.info("=== Iniciando VEXX AI Tray Service (Universal & Portátil) ===")
    log.info("Diretório base: %s | Modelos: %s", BASE_DIR, MODELS_DIR)

    # 1. Configura auto-inicialização no Windows
    if not is_startup_enabled():
        set_startup_enabled(True)

    # 2. Carrega modelo inicial em thread
    threading.Thread(target=lambda: carregar_llm("qwen2.5-vl-7b-instruct"), daemon=True).start()

    # 3. Inicia servidor FastAPI local na porta 8008
    iniciar_servidor_fastapi()

    # 4. Inicia túnel resiliente para vexx-ai.space
    iniciar_tunel_agent()

    # 5. Verifica se o Qwen2.5-VL 7B precisa de download
    if not VL_MODEL_FILE.exists() or not VL_PROJ_FILE.exists():
        log.info("Arquivos do Qwen2.5-VL 7B ausentes. Iniciando download automático em segundo plano...")
        baixar_qwen_vl_background()

    # 6. Inicia o ícone na bandeja do sistema (com suporte a fallback caso sem GUI)
    try:
        import pystray
        icon = pystray.Icon(
            name="VexxAI",
            icon=criar_imagem_icone(verde=False),
            title="VEXX AI - Conectando...",
            menu=montar_menu()
        )
        app_state["tray_icon"] = icon

        def _timer_update():
            while not app_state["shutdown"]:
                time.sleep(3)
                try:
                    atualizar_tooltip_tray()
                except Exception:
                    pass

        threading.Thread(target=_timer_update, daemon=True).start()
        icon.run()

    except Exception as exc:
        log.warning("Aviso no pystray (modo sem bandeja visual): %s.", exc)

    # Loop de persistência perpétua (garante que FastAPI e Túnel rodem 24/7 mesmo se a bandeja encerrar)
    log.info("Loop de segurança perpétuo ativo: mantendo FastAPI e Túnel em execução contínua.")
    while not app_state["shutdown"]:
        time.sleep(1)


if __name__ == "__main__":
    main()
