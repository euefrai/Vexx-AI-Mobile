# -*- coding: utf-8 -*-
"""
VEXX AI - Serviço em Segundo Plano (Bandeja / System Tray)
Executa de forma 100% oculta no Windows (sem janelas CMD).
Inicia automaticamente com o Windows, gerencia o download e execução do Qwen2.5-VL (7B),
fornece API compatível com OpenAI na porta 8008 e mantém o túnel ativo com vexx-ai.space.
"""

import os
import sys
import time
import json
import socket
import logging
import threading
import subprocess
import webbrowser
import winreg
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw
import pystray
from pystray import MenuItem as item, Menu

# Configuração de caminhos e ambiente
BASE_DIR = Path(r"C:\Users\efrai\Documents\ia-local")
MODELS_DIR = BASE_DIR / "models" / "llm"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

PYTHON_EXE = r"C:\Users\efrai\Documents\very\backend\venv\Scripts\python.exe"
PYTHONW_EXE = r"C:\Users\efrai\Documents\very\backend\venv\Scripts\pythonw.exe"
JULIA_REPO_DIR = Path(r"C:\Users\efrai\Documents\julia-mobile-v0.2-offline-sqlite\julia-mobile-v0.2")

VL_MODEL_FILE = MODELS_DIR / "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf"
VL_PROJ_FILE = MODELS_DIR / "mmproj-F16.gguf"
MODEL_15B_FILE = MODELS_DIR / "qwen2.5-1.5b-instruct-q4_k_m.gguf"
MODEL_3B_FILE = MODELS_DIR / "qwen2.5-3b-instruct-q4_k_m.gguf"

RELAY_URL = "https://vexx-ai.space"
AGENT_TOKEN = "OxnAFLKyv1T5R1GdCpmaGs1tCn9eeMZH7tNalkYCqS8fMR-UDQ4LcMhV-SxY"
PORT = 8008

# Configuração de logging seguro
LOG_FILE = BASE_DIR / "vexx_tray_service.log"
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


# =====================================================================
# 1. AUTO-INICIALIZAÇÃO NO REGISTRO DO WINDOWS (Run)
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
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                cmd = f'"{PYTHONW_EXE}" "{Path(__file__).resolve()}"'
                winreg.SetValueEx(key, REG_NAME, 0, winreg.REG_SZ, cmd)
                log.info("Auto-inicialização ativada no registro: %s", cmd)
            else:
                try:
                    winreg.DeleteValue(key, REG_NAME)
                    log.info("Auto-inicialização desativada no registro.")
                except FileNotFoundError:
                    pass
    except Exception as exc:
        log.warning("Falha ao atualizar registro de auto-inicialização: %s", exc)


# =====================================================================
# 2. GERENCIADOR DE MODELOS LLM LOCAL (llama_cpp)
# =====================================================================
def carregar_llm(solicitado: str = "qwen2.5-vl-7b-instruct"):
    global _loaded_llm, _loaded_model_id
    with _model_lock:
        if _loaded_llm is not None and _loaded_model_id == solicitado:
            return _loaded_llm, _loaded_model_id

        from llama_cpp import Llama

        # 1. Tentativa de carregar Qwen 2.5-VL 7B
        if solicitado in ("qwen2.5-vl-7b-instruct", "qwen2.5-vl-7b", "auto"):
            if VL_MODEL_FILE.exists() and VL_MODEL_FILE.stat().st_size > 1_000_000_000:
                log.info("Carregando Qwen 2.5-VL 7B: %s", VL_MODEL_FILE)
                chat_handler = None
                if VL_PROJ_FILE.exists() and VL_PROJ_FILE.stat().st_size > 100_000_000:
                    try:
                        from llama_cpp.llama_chat_format import Qwen25VLChatHandler
                        chat_handler = Qwen25VLChatHandler(clip_model_path=str(VL_PROJ_FILE))
                        log.info("Projetor multimodal VL ativado: %s", VL_PROJ_FILE)
                    except Exception as exc:
                        log.warning("Falha ao inicializar chat handler VL: %s", exc)

                try:
                    _loaded_llm = Llama(
                        model_path=str(VL_MODEL_FILE),
                        chat_handler=chat_handler,
                        n_ctx=8192,
                        n_threads=4,
                        n_batch=512,
                        verbose=False
                    )
                    _loaded_model_id = "qwen2.5-vl-7b-instruct"
                    app_state["active_model"] = "Qwen 2.5-VL (7B)"
                    log.info("Qwen 2.5-VL 7B carregado com sucesso na memória.")
                    return _loaded_llm, _loaded_model_id
                except Exception as exc:
                    log.warning("Falha ao carregar Qwen 2.5-VL 7B: %s. Tentando modelo secundário...", exc)

        # 2. Fallback para Qwen 2.5 1.5B (ou se solicitado)
        if solicitado == "qwen2.5-1.5b-instruct" or not VL_MODEL_FILE.exists():
            if MODEL_15B_FILE.exists():
                log.info("Carregando Qwen 2.5 1.5B: %s", MODEL_15B_FILE)
                _loaded_llm = Llama(
                    model_path=str(MODEL_15B_FILE),
                    n_ctx=8192,
                    n_threads=4,
                    n_batch=512,
                    verbose=False
                )
                _loaded_model_id = "qwen2.5-1.5b-instruct"
                app_state["active_model"] = "Qwen 2.5 (1.5B) [Fallback]"
                return _loaded_llm, _loaded_model_id

        # 3. Fallback para Qwen 2.5 3B se existir
        if MODEL_3B_FILE.exists():
            log.info("Carregando Qwen 2.5 3B: %s", MODEL_3B_FILE)
            _loaded_llm = Llama(
                model_path=str(MODEL_3B_FILE),
                n_ctx=8192,
                n_threads=4,
                n_batch=512,
                verbose=False
            )
            _loaded_model_id = "qwen2.5-3b-instruct"
            app_state["active_model"] = "Qwen 2.5 (3B) [Fallback]"
            return _loaded_llm, _loaded_model_id

        raise RuntimeError("Nenhum arquivo de modelo GGUF encontrado em " + str(MODELS_DIR))


# =====================================================================
# 3. DOWNLOADER AUTOMÁTICO EM SEGUNDO PLANO (Qwen2.5-VL 7B)
# =====================================================================
def baixar_qwen_vl_background():
    if app_state["is_downloading"]:
        return

    # Se os arquivos já existem completamente, não baixa de novo
    if VL_MODEL_FILE.exists() and VL_PROJ_FILE.exists():
        if VL_MODEL_FILE.stat().st_size > 4_000_000_000 and VL_PROJ_FILE.stat().st_size > 1_000_000_000:
            app_state["download_status"] = "Qwen 2.5-VL 7B Pronto"
            app_state["download_progress"] = 100
            return

    def _worker():
        app_state["is_downloading"] = True
        app_state["download_status"] = "Iniciando download..."
        log.info("Iniciando download do modelo Qwen2.5-VL 7B GGUF...")

        try:
            from huggingface_hub import hf_hub_download
            repo_id = "unsloth/Qwen2.5-VL-7B-Instruct-GGUF"

            # 1. Baixar modelo principal Q4_K_M (~4.36 GB)
            if not VL_MODEL_FILE.exists() or VL_MODEL_FILE.stat().st_size < 4_000_000_000:
                app_state["download_status"] = "Baixando Qwen2.5-VL-7B (Q4_K_M)..."
                log.info("Baixando arquivo principal Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf...")
                hf_hub_download(
                    repo_id=repo_id,
                    filename="Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf",
                    local_dir=str(MODELS_DIR),
                    resume_download=True
                )

            # 2. Baixar projetor multimodal mmproj-F16.gguf (~1.26 GB)
            if not VL_PROJ_FILE.exists() or VL_PROJ_FILE.stat().st_size < 1_000_000_000:
                app_state["download_status"] = "Baixando projetor multimodal mmproj..."
                log.info("Baixando arquivo multimodal mmproj-F16.gguf...")
                hf_hub_download(
                    repo_id=repo_id,
                    filename="mmproj-F16.gguf",
                    local_dir=str(MODELS_DIR),
                    resume_download=True
                )

            app_state["download_status"] = "Download concluído! Carregando..."
            app_state["download_progress"] = 100
            log.info("Download do Qwen 2.5-VL 7B finalizado com sucesso!")

            # Carrega o modelo novo imediatamente
            carregar_llm("qwen2.5-vl-7b-instruct")
            atualizar_tooltip_tray()

        except Exception as exc:
            log.warning("Erro durante download do Qwen 2.5-VL: %s", exc)
            app_state["download_status"] = f"Erro no download: {exc}"
        finally:
            app_state["is_downloading"] = False

    t = threading.Thread(target=_worker, daemon=True, name="QwenVL-Downloader")
    t.start()


# =====================================================================
# 4. SERVIDOR FASTAPI LOCAL (Porta 8008 - OpenAI Compatível)
# =====================================================================
def iniciar_servidor_fastapi():
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse, StreamingResponse
    import uvicorn

    server_app = FastAPI(title="VEXX AI Local LLM Server")

    @server_app.get("/v1/models")
    async def get_models():
        items = [
            {"id": "qwen2.5-vl-7b-instruct", "object": "model", "owned_by": "vexx_local"},
            {"id": "qwen2.5-1.5b-instruct", "object": "model", "owned_by": "vexx_local"},
            {"id": "qwen2.5-3b-instruct", "object": "model", "owned_by": "vexx_local"},
        ]
        return {"object": "list", "data": items}

    def _trim_messages(msgs, max_chars=24000):
        total_chars = sum(len(str(m.get("content", ""))) for m in msgs)
        if total_chars <= max_chars or len(msgs) <= 3:
            return msgs
        sys_msgs = [m for m in msgs if m.get("role") == "system"]
        tail = [m for m in msgs if m.get("role") != "system"][-6:]
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

            llm, model_usado = carregar_llm(model_req)

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
            log.exception("Erro na chamada de chat completions: %s", exc)
            return JSONResponse({"error": str(exc)}, status_code=500)

    @server_app.get("/health")
    async def health():
        return {
            "status": "ok",
            "active_model": app_state["active_model"],
            "download_status": app_state["download_status"],
            "tunnel_online": app_state["tunnel_online"],
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
            uvicorn.run(server_app, host="127.0.0.1", port=PORT, log_level="warning")
        except Exception as exc:
            log.error("Falha no servidor FastAPI: %s", exc)
            app_state["server_online"] = False

    t = threading.Thread(target=_run, daemon=True, name="FastAPI-LLM-8008")
    t.start()


# =====================================================================
# 5. GERENCIADOR DO TÚNEL WEBSOCKET DO PC AGENT
# =====================================================================
agent_process = None

def iniciar_tunel_agent():
    global agent_process

    def _monitor():
        global agent_process
        env = os.environ.copy()
        env["JULIA_RELAY_URL"] = RELAY_URL
        env["JULIA_AGENT_TOKEN"] = AGENT_TOKEN
        env["VEXX_AGENT_ROLE"] = "production"
        env["JULIA_REMOTE"] = "1"
        env["PYTHONUTF8"] = "1"

        while not app_state["shutdown"]:
            try:
                log.info("Iniciando processo do túnel PC Agent para %s...", RELAY_URL)
                agent_process = subprocess.Popen(
                    [PYTHONW_EXE, "pc_agent.py"],
                    cwd=str(JULIA_REPO_DIR),
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
                log.warning("Falha ao executar pc_agent: %s", exc)
            app_state["tunnel_online"] = False
            atualizar_tooltip_tray()
            time.sleep(5)

    t = threading.Thread(target=_monitor, daemon=True, name="AgentTunnel-Monitor")
    t.start()


# =====================================================================
# 6. BANDEJA DO SISTEMA (System Tray / pystray)
# =====================================================================
def criar_imagem_icone(verde: bool = True) -> Image.Image:
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
        app_state["tray_icon"].icon = criar_imagem_icone(verde=app_state["tunnel_online"])


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


def main():
    log.info("=== Iniciando VEXX AI Tray Service ===")
    
    # 1. Garante registro de auto-inicialização configurado
    if not is_startup_enabled():
        set_startup_enabled(True)

    # 2. Carrega modelo inicial em thread
    threading.Thread(target=lambda: carregar_llm("qwen2.5-vl-7b-instruct"), daemon=True).start()

    # 3. Inicia servidor FastAPI local na porta 8008
    iniciar_servidor_fastapi()

    # 4. Inicia túnel para vexx-ai.space
    iniciar_tunel_agent()

    # 5. Verifica se o Qwen2.5-VL 7B precisa de download
    if not VL_MODEL_FILE.exists() or not VL_PROJ_FILE.exists():
        log.info("Arquivos do Qwen2.5-VL 7B não encontrados localmente. Iniciando download em segundo plano...")
        baixar_qwen_vl_background()

    # 6. Inicia o ícone na bandeja do sistema
    icon = pystray.Icon(
        name="VexxAI",
        icon=criar_imagem_icone(verde=False),
        title="VEXX AI - Qwen 2.5-VL 7B (Iniciando...)",
        menu=montar_menu()
    )
    app_state["tray_icon"] = icon

    # Timer periódico para atualizar o tooltip
    def _timer_update():
        while not app_state["shutdown"]:
            time.sleep(3)
            try:
                atualizar_tooltip_tray()
            except Exception:
                pass

    threading.Thread(target=_timer_update, daemon=True).start()

    # Roda o loop da bandeja (bloqueante na thread principal da interface)
    icon.run()


if __name__ == "__main__":
    main()
