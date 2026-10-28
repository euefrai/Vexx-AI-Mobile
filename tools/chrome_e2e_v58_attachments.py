"""V5.8 real Chrome E2E (desktop + emulated mobile): anexos e links.

Isolated stack: uvicorn server:app + pc_agent.py, temporary SQLite, temporary
Chrome profile and no production data.  The script drives the real composer:

1. escolher um arquivo apenas cria o chip no composer (nenhum upload);
2. o texto continua digitável com o anexo pendente;
3. enviar sobe o documento UMA vez e cria UMA mensagem com o marcador;
4. links de busca/categoria e links não verificados não viram <a> clicável,
   inclusive no viewport móvel.

Usage: python tools/chrome_e2e_v58_attachments.py
"""
import base64
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
_isolated_env = tempfile.TemporaryDirectory(prefix='vexx-attachments-env-')
os.environ['JULIA_ENV_FILE'] = str(Path(_isolated_env.name) / 'disabled.env')

import shopping  # noqa: E402
from argon2 import PasswordHasher  # noqa: E402
from websockets.sync.client import connect  # noqa: E402

CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
ART = RAIZ / "qa-artifacts" / "v58-attachments"
ART.mkdir(parents=True, exist_ok=True)
INICIO = time.monotonic()
ETAPAS = []

TEXTO_DIGITADO = "Segue o contrato para análise."
NOME_ARQUIVO = "contrato-aluguel.txt"
CONTEUDO_ARQUIVO = (
    "CONTRATO DE LOCAÇÃO\n\n"
    "Cláusula 5: a multa por rescisão antecipada é de dois aluguéis.\n"
    "Cláusula 9: o prazo de aviso prévio é de 30 dias.\n"
)


def etapa(nome, detalhe=""):
    item = {"etapa": nome, "detalhe": detalhe,
            "t": round(time.monotonic() - INICIO, 2)}
    ETAPAS.append(item)
    print(f"[{item['t']:6.2f}s] {nome}" + (f": {detalhe}" if detalhe else ""))


def porta_livre():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def esperar_http(url, cond, timeout, nome):
    inicio = time.monotonic()
    ultimo = None
    while time.monotonic() - inicio < timeout:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                dados = json.loads(r.read().decode() or "{}")
            if cond(dados):
                return dados
            ultimo = "resposta sem condição"
        except Exception as exc:
            ultimo = exc
        time.sleep(0.4)
    raise AssertionError(f"{nome} não ficou pronto ({ultimo})")


def _tail(caminho: Path, linhas=25):
    try:
        return "\n".join(caminho.read_text(encoding="utf-8", errors="replace")
                         .splitlines()[-linhas:])[:4000]
    except Exception:
        return ""


class Processo:
    def __init__(self, cmd, log, env, cwd=RAIZ):
        self.log = Path(log)
        self._fh = self.log.open("wb")
        self.proc = subprocess.Popen(cmd, cwd=str(cwd), env=env,
                                     stdout=self._fh, stderr=subprocess.STDOUT,
                                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))

    def parar(self):
        try:
            if self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=12)
                except subprocess.TimeoutExpired:
                    subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.proc.pid)],
                                   capture_output=True)
        finally:
            try:
                self._fh.close()
            except Exception:
                pass


class CDP:
    def __init__(self, ws_url):
        self.ws = connect(ws_url, max_size=None, open_timeout=15, legacy=True)
        self.seq = 0
        self.erros = []
        self.uploads = []

    def _evento(self, msg):
        p = msg.get("params") or {}
        metodo = msg.get("method")
        if metodo == "Network.requestWillBeSent":
            url = str((p.get("request") or {}).get("url") or "")
            if "/api/docs/upload" in url:
                self.uploads.append(url)
        elif metodo == "Runtime.exceptionThrown":
            det = p.get("exceptionDetails") or {}
            self.erros.append({"tipo": "exception",
                               "texto": str(det.get("text") or
                                            det.get("exception", {}).get("description", ""))[:300]})
        elif metodo == "Log.entryAdded":
            e = p.get("entry") or {}
            texto = str(e.get("text", ""))
            if (e.get("level") == "error" and "favicon" not in texto
                    and "401 (Unauthorized)" not in texto
                    and "503 (Service Unavailable)" not in texto):
                self.erros.append({"tipo": "log", "texto": texto[:300]})

    def cmd(self, metodo, params=None, timeout=60):
        self.seq += 1
        meu = self.seq
        self.ws.send(json.dumps({"id": meu, "method": metodo, "params": params or {}}))
        limite = time.monotonic() + timeout
        while True:
            restante = max(0.5, limite - time.monotonic())
            msg = json.loads(self.ws.recv(timeout=restante))
            if msg.get("id") == meu:
                if "error" in msg:
                    raise RuntimeError(f"CDP {metodo}: {msg['error']}")
                return msg.get("result") or {}
            self._evento(msg)

    def js(self, expressao, timeout=60):
        r = self.cmd("Runtime.evaluate", {
            "expression": expressao, "returnByValue": True,
            "awaitPromise": True, "userGesture": True}, timeout=timeout)
        if r.get("exceptionDetails"):
            raise RuntimeError(f"JS falhou: {r['exceptionDetails']}")
        return (r.get("result") or {}).get("value")

    def esperar_js(self, expressao, cond, timeout, nome):
        inicio = time.monotonic()
        ultimo = None
        while time.monotonic() - inicio < timeout:
            try:
                ultimo = self.js(expressao)
                if cond(ultimo):
                    return ultimo
            except Exception as exc:
                ultimo = exc
            time.sleep(0.4)
        raise AssertionError(f"{nome} não ocorreu em {timeout}s (último: {ultimo})")

    def screenshot(self, nome):
        r = self.cmd("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
        destino = ART / nome
        destino.write_bytes(base64.b64decode(r.get("data", "")))
        etapa("screenshot", str(destino))
        return str(destino)


def texto_links_sanitizado():
    texto = (
        "Oferta verificada: [Produto X](https://loja.com/produto/x). "
        "Busca: [resultados](https://loja.com/busca?q=placa). "
        "Link inventado: https://inventado.example/produto/z."
    )
    resultado = {"produtos": [{"url_item": "https://loja.com/produto/x"}]}
    return shopping.sanitizar_links_resposta(texto, resultado)


def _checar_links(info, viewport, exige_sem_overflow=True):
    assert info, f"mensagens de link ausentes no {viewport}"
    san, raw = info["san"], info["raw"]
    assert san and raw, f"bolhas ausentes no {viewport}: {info}"
    # Texto vindo do backend: só o item comprovado é clicável.
    assert len(san["anchors"]) == 1, san["anchors"]
    href = san["anchors"][0]["href"] or ""
    assert href == "https://loja.com/produto/x", href
    assert san["anchors"][0]["target"] == "_blank"
    for a in san["anchors"]:
        assert "/busca" not in (a["href"] or ""), a
        assert "inventado.example" not in (a["href"] or ""), a
        assert (a["href"] or "").rstrip("/") != "https://loja.com", a
    assert "página de busca/categoria" in san["text"], san["text"][:400]
    assert "link não verificado" in san["text"], san["text"][:400]
    assert san["visible"], f"bolha sanitizada invisível no {viewport}"
    # Markdown geral continua aceitando links de pesquisa/home. A regra de
    # produto pertence ao sanitizador de compras e aos cards JDUI, acima.
    assert {a['href'] for a in raw['anchors']} == {
        'https://loja.com/busca?q=placa', 'https://loja.com/'}, raw['anchors']
    assert raw['blocked'] == [], raw['blocked']
    assert raw["visible"], f"bolha crua invisível no {viewport}"
    for b in (san, raw):
        assert b["rect"]["left"] >= -1, b["rect"]
        assert b["rect"]["right"] <= b["width"] + 1, b["rect"]
        if exige_sem_overflow:
            assert not b["overflow"], f"overflow horizontal no {viewport}"
    return {
        "san_anchors": san["anchors"],
        "san_labels": [b["text"] for b in san["blocked"]],
        "raw_blocked": raw["blocked"],
        "width": san["width"],
        "san_rect": san["rect"],
        "raw_rect": raw["rect"],
    }


def main():
    resultado = {
        "quando": datetime.now().isoformat(timespec="seconds"),
        "tipo_evidencia": "chrome-real-desktop + mobile-emulado; stack local isolado",
        "ambiente": {"chrome": str(CHROME), "python": sys.version.split()[0]},
        "etapas": ETAPAS, "ok": False,
    }
    processos = []
    logs = {}
    cdp = None
    tmp = Path(tempfile.mkdtemp(prefix="vexx-v58-attach-"))
    try:
        if not CHROME.exists():
            raise AssertionError(f"Chrome não encontrado em {CHROME}")
        porta_relay = porta_livre()
        porta_cdp = porta_livre()
        base = f"http://127.0.0.1:{porta_relay}"
        db_path = tmp / "e2e-v58-attach.sqlite3"
        doc_path = tmp / NOME_ARQUIVO
        doc_path.write_text(CONTEUDO_ARQUIVO, encoding="utf-8")
        env = dict(os.environ)
        env.update({
            "JULIA_USERNAME": "efrai",
            "JULIA_PASSWORD_HASH": PasswordHasher().hash("strong-example-password"),
            "JULIA_SESSION_SECRET": "a" * 64,
            "JULIA_AGENT_TOKEN": "b" * 64,
            "JULIA_RELAY_URL": base,
            "JULIA_SQLITE_PATH": str(db_path),
            "HERMES_PROXY_URL": "http://127.0.0.1:9/v1",
            "JULIA_AI_MODEL": "unused/local",
            "JULIA_ENV": "development",
            "JULIA_ENV_FILE": str(tmp / 'disabled.env'),
            "VEXX_AGENT_ROLE": "development",
            "VEXX_AGENT_INSTANCE": "attachments-" + str(porta_relay),
            "VEXX_AGENT_RUNTIME_DIR": str(tmp / 'runtime'),
        })
        for key in ('OPENAI_API_KEY', 'GEMINI_API_KEY', 'ANTHROPIC_API_KEY',
                    'DEEPSEEK_API_KEY', 'GROQ_API_KEY', 'MISTRAL_API_KEY', 'OPENROUTER_API_KEY'):
            env.pop(key, None)
        env.pop("JULIA_AI_FALLBACKS", None)
        resultado["ambiente"].update({
            "app": base, "sqlite": str(db_path), "documento": str(doc_path),
            "viewport_desktop": "1280x900", "viewport_mobile": "390x844"})

        etapa("relay", base)
        relay = Processo([sys.executable, "-m", "uvicorn", "server:app",
                          "--host", "127.0.0.1", "--port", str(porta_relay)],
                         tmp / "relay.log", env)
        processos.append(relay)
        logs["relay"] = relay.log
        esperar_http(base + "/api/diag", lambda c: True, 40, "relay")
        etapa("agente", "pc_agent.py")
        agente = Processo([sys.executable, "pc_agent.py"], tmp / "agent.log", env)
        processos.append(agente)
        logs["agente"] = agente.log
        esperar_http(base + "/api/diag", lambda c: c.get("pc_online") is True, 90, "agente")

        etapa("chrome", f"headless CDP porta {porta_cdp}")
        chrome_proc = subprocess.Popen(
            [str(CHROME), "--headless=new", f"--remote-debugging-port={porta_cdp}",
             f"--user-data-dir={tmp / 'chrome-profile'}", "--no-first-run",
             "--no-default-browser-check", "--disable-gpu", "--disable-extensions",
             "--disable-background-networking", "--disable-sync",
             "--metrics-recording-only", "--window-size=1280,900", "about:blank"],
            stdout=(tmp / "chrome.log").open("wb"), stderr=subprocess.STDOUT)
        processos.append(type("ChromeProc", (), {
            "proc": chrome_proc,
            "parar": lambda self: (subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(chrome_proc.pid)],
                capture_output=True) if chrome_proc.poll() is None else None)})())
        logs["chrome"] = tmp / "chrome.log"
        versao = esperar_http(f"http://127.0.0.1:{porta_cdp}/json/version",
                              lambda c: bool(c.get("webSocketDebuggerUrl")), 30, "chrome")
        resultado["ambiente"]["chrome_versao"] = versao.get("Browser", "")

        pedido = urllib.request.Request(
            f"http://127.0.0.1:{porta_cdp}/json/new?"
            + urllib.parse.quote(base + "/", safe=":/?=&"), method="PUT")
        with urllib.request.urlopen(pedido, timeout=15) as r:
            pagina = json.loads(r.read().decode())
        cdp = CDP(pagina["webSocketDebuggerUrl"])
        for dominio in ("Page", "Runtime", "Log", "Network", "DOM"):
            cdp.cmd(dominio + ".enable")
        cdp.cmd("Page.navigate", {"url": base + "/"})
        cdp.esperar_js("document.readyState", lambda v: v == "complete", 30, "load")
        cdp.esperar_js("!!document.getElementById('loginOverlay')",
                       lambda v: v is True, 20, "login overlay")
        cdp.js("""
          (() => {
            document.getElementById('loginUser').value = 'efrai';
            document.getElementById('loginPassword').value = 'strong-example-password';
            document.getElementById('loginForm').requestSubmit();
            return true;
          })()
        """)
        cdp.esperar_js("(document.getElementById('loginOverlay')||{}).hidden",
                       lambda v: v is True, 30, "login")
        status = cdp.esperar_js(
            "({auth: (typeof authenticated !== 'undefined') ? authenticated : null,"
            " pc: (typeof pcOnline !== 'undefined') ? pcOnline : null})",
            lambda v: isinstance(v, dict) and v.get("auth") is True and v.get("pc") is True,
            60, "login e PC online")
        etapa("login_ok", json.dumps(status, ensure_ascii=False))
        # O foco é anexo/link; a chamada ao modelo (provedor indisponível neste
        # ambiente isolado) não deve segurar nem poluir o envio testado.
        cdp.js("requestAI = async function () { return null; }; true")
        cdp.js("""
          (() => {
            if (window.__vexxFetchWrapper) return true;
            window.__vexxFetchWrapper = true;
            window.__uploadCount = 0;
            const orig = window.fetch.bind(window);
            window.__origFetchVexx = orig;
            window.fetch = (...args) => {
              const u = typeof args[0] === 'string' ? args[0]
                : (args[0] && args[0].url) || '';
              if (String(u).indexOf('/api/docs/upload') >= 0) window.__uploadCount++;
              return orig(...args);
            };
            return true;
          })()
        """)

        # 1) escolher arquivo -> chip, sem upload
        alvo = cdp.cmd("Runtime.evaluate", {
            "expression": "document.getElementById('fileInput')",
            "returnByValue": False})
        object_id = ((alvo.get("result") or {}).get("objectId"))
        assert object_id, alvo
        cdp.cmd("DOM.setFileInputFiles", {"files": [str(doc_path)], "objectId": object_id})
        pendente = cdp.esperar_js("""
          (() => {
            const t = document.getElementById('attachmentTray');
            const chips = t ? t.querySelectorAll('.attachment-chip') : [];
            const r = chips[0] ? chips[0].getBoundingClientRect() : null;
            return {hidden: t ? t.hidden : null, n: chips.length,
              name: chips[0] ? chips[0].querySelector('.attachment-name').textContent : '',
              w: r ? r.width : 0, h: r ? r.height : 0,
              uploads: window.__uploadCount || 0};
          })()
        """, lambda v: isinstance(v, dict) and v.get("n") == 1 and not v.get("hidden"),
            15, "chip do anexo")
        assert pendente["name"] == NOME_ARQUIVO, pendente
        assert pendente["w"] > 0 and pendente["h"] > 0, pendente
        time.sleep(0.8)
        antes = cdp.js("({js: window.__uploadCount || 0, doc: performance.getEntriesByType('resource')"
                       ".filter(e => e.name.indexOf('/api/docs/upload') >= 0).length})")
        assert antes["js"] == 0 and antes["doc"] == 0, antes
        assert not cdp.uploads, cdp.uploads
        etapa("anexo_pendente_sem_upload", json.dumps(pendente, ensure_ascii=False))
        cdp.js("document.getElementById('conversation').scrollTop = "
               "document.getElementById('conversation').scrollHeight; true")
        cdp.screenshot("01-desktop-anexo-pendente.png")

        # 2) ainda dá para digitar com o anexo pendente
        cdp.js("document.getElementById('messageInput').focus(); true")
        cdp.cmd("Input.insertText", {"text": TEXTO_DIGITADO})
        cdp.esperar_js("document.getElementById('messageInput').value",
                       lambda v: v == TEXTO_DIGITADO, 5, "texto digitado")
        etapa("texto_digitavel_com_anexo", TEXTO_DIGITADO)

        # 3) mobile: chip e texto continuam visíveis antes de enviar
        cdp.cmd("Emulation.setDeviceMetricsOverride", {
            "width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": True})
        time.sleep(0.6)
        mobile_pend = cdp.js("""
          (() => {
            const t = document.getElementById('attachmentTray');
            const chip = t ? t.querySelector('.attachment-chip') : null;
            const r = chip ? chip.getBoundingClientRect() : null;
            return {w: innerWidth, h: innerHeight, hidden: t ? t.hidden : null,
              chips: t ? t.querySelectorAll('.attachment-chip').length : 0,
              left: r ? r.left : null, right: r ? r.right : null,
              top: r ? r.top : null, bottom: r ? r.bottom : null,
              value: document.getElementById('messageInput').value,
              overflow: document.documentElement.scrollWidth > innerWidth + 1};
          })()
        """)
        assert mobile_pend["chips"] == 1 and not mobile_pend["hidden"], mobile_pend
        assert mobile_pend["left"] >= -1 and mobile_pend["right"] <= mobile_pend["w"] + 1, mobile_pend
        assert mobile_pend["top"] >= -1 and mobile_pend["bottom"] <= mobile_pend["h"] + 1, mobile_pend
        assert mobile_pend["value"] == TEXTO_DIGITADO, mobile_pend
        etapa("anexo_mobile_pendente", json.dumps(
            {k: mobile_pend[k] for k in ("w", "chips", "left", "right", "top", "bottom", "overflow")},
            ensure_ascii=False))
        cdp.screenshot("02-mobile-anexo-pendente.png")

        # Browser-level cancellation: hold transport before sending any bytes;
        # the actual button must abort its signal and preserve the draft.
        cdp.js("""
          (() => {
            window.__beforeCancelFetch = window.fetch;
            window.__heldCancelSeen = false;
            window.fetch = (...args) => {
              if (String(args[0]).includes('/api/docs/upload')) {
                const signal = args[1].signal;
                window.__cancelSignal = signal;
                window.__heldCancelSeen = true;
                return new Promise((resolve, reject) => signal.addEventListener('abort',
                  () => reject(new DOMException('Aborted', 'AbortError')), {once:true}));
              }
              return window.__beforeCancelFetch(...args);
            };
            document.getElementById('composer').requestSubmit();
            return true;
          })()
        """)
        cdp.esperar_js("window.__heldCancelSeen && !document.getElementById('cancelAttachmentUpload').hidden",
                       lambda v: v is True, 10, 'botão cancelar upload')
        cancel_rect = cdp.js("""
          (() => {const b=document.getElementById('cancelAttachmentUpload');
            const r=b.getBoundingClientRect();return {left:r.left,right:r.right,
              top:r.top,bottom:r.bottom,height:r.height,width:innerWidth};})()
        """)
        assert cancel_rect['height'] >= 44 and cancel_rect['left'] >= 0
        assert cancel_rect['right'] <= cancel_rect['width']
        assert cancel_rect['top'] >= 0 and cancel_rect['bottom'] <= 844
        cdp.screenshot('00-mobile-upload-cancel.png')
        cdp.js("document.getElementById('cancelAttachmentUpload').click(); true")
        cdp.esperar_js("!sendingMessages.has(activeConversation)", lambda v:v is True, 10, 'envio cancelado')
        cancellation = cdp.js("""
          (async () => ({aborted:window.__cancelSignal.aborted,
            chips:document.querySelectorAll('.attachment-chip').length,
            uploads:window.__uploadCount,
            messages:(await allMessages()).filter(m=>m.role==='user').length,
            progressHidden:document.getElementById('uploadStatus').hidden}))()
        """)
        assert cancellation == {'aborted':True,'chips':1,'uploads':0,'messages':0,'progressHidden':True}, cancellation
        resultado['cancelamento'] = {**cancellation,'button_geometry':cancel_rect,
            'scope':'real Chrome button/signal; transport held before request, not server rollback'}
        etapa('cancelamento_mobile_ok', json.dumps(cancellation))
        cdp.js("window.fetch=window.__beforeCancelFetch; true")

        # 4) retry/send (with double click): ONE real upload and ONE message.
        cdp.js("""
          (() => {
            const b = document.querySelector('.send-button');
            b.click();
            b.click();  // o lock de envio precisa ignorar o segundo clique
            return true;
          })()
        """)
        envio = cdp.esperar_js("""
          (() => ({
            uploads: window.__uploadCount || 0,
            trayHidden: document.getElementById('attachmentTray').hidden,
            chips: document.querySelectorAll('.attachment-chip').length,
            input: document.getElementById('messageInput').value
          }))()
        """, lambda v: isinstance(v, dict) and v.get("uploads") == 1
             and v.get("trayHidden") is True and v.get("chips") == 0,
            45, "upload e envio")
        mensagens = cdp.esperar_js("""
          (async () => {
            const rows = await allMessages();
            const conv = localStorage.getItem('julia-active-conversation');
            const us = rows.filter(m => m.conversation_id === conv && m.role === 'user');
            const alvo = us.filter(m => String(m.text || '')
              .indexOf('📎 Documento anexado: "contrato-aluguel.txt"') >= 0);
            return {n: alvo.length, total: us.length,
              text: alvo[0] ? alvo[0].text : '',
              want_ai: alvo[0] ? alvo[0].want_ai : null};
          })()
        """, lambda v: isinstance(v, dict) and v.get("n") == 1, 30, "mensagem com anexo")
        assert mensagens["total"] == 1, mensagens
        assert mensagens["text"].startswith(TEXTO_DIGITADO), mensagens
        assert mensagens["want_ai"] is True, mensagens
        assert envio["input"] == "", envio
        docs = cdp.esperar_js("""
          (async () => {
            const r = await fetch('/api/docs', {cache: 'no-store',
              credentials: 'same-origin'});
            if (!r.ok) return {status: r.status, n: -1};
            const d = await r.json();
            const lista = (d.documents || []).filter(x => x.name === 'contrato-aluguel.txt');
            return {status: r.status, n: lista.length,
              doc_id: lista[0] ? lista[0].doc_id : ''};
          })()
        """, lambda v: isinstance(v, dict) and v.get("n") == 1, 25, "documento no servidor")
        # drena eventos de rede e confirma que não houve segundo upload
        cdp.js("1")
        time.sleep(1.0)
        cdp.js("1")
        perf = cdp.js("({js: window.__uploadCount || 0, doc: performance.getEntriesByType('resource')"
                      ".filter(e => e.name.indexOf('/api/docs/upload') >= 0).length})")
        assert perf["js"] == 1 and perf["doc"] == 1, perf
        assert len(cdp.uploads) == 1, cdp.uploads
        bolha = cdp.js("""
          (() => {
            const b = Array.from(document.querySelectorAll('.message.user .bubble'))
              .find(x => (x.textContent || '').indexOf('Documento anexado') >= 0);
            return b ? {text: b.textContent || '', visible: b.getClientRects().length > 0} : null;
          })()
        """)
        assert bolha and bolha["visible"], bolha
        assert TEXTO_DIGITADO in bolha["text"] and NOME_ARQUIVO in bolha["text"], bolha
        etapa("envio_unico_ok", json.dumps(
            {"uploads_js": perf["js"], "uploads_rede": len(cdp.uploads),
             "mensagens": mensagens["n"], "docs": docs["n"],
             "doc_id": docs.get("doc_id", "")}, ensure_ascii=False))
        cdp.screenshot("03-mobile-enviado.png")

        # volta ao desktop para validar os links nos dois viewports
        cdp.cmd("Emulation.setDeviceMetricsOverride", {
            "width": 1280, "height": 900, "deviceScaleFactor": 1, "mobile": False})
        time.sleep(0.6)
        assert cdp.js("innerWidth") == 1280

        # 5) mensagens sintéticas com o texto REAL do sanitizador + link cru
        sanitizado = texto_links_sanitizado()
        bruto = "[Busca](https://loja.com/busca?q=placa) e https://loja.com/"
        ids = cdp.js("""
          (async () => {
            const stamp = Date.now().toString(36);
            const conv = 'e2e-links-' + stamp;
            const ids = {san: 'e2e-san-' + stamp, raw: 'e2e-raw-' + stamp};
            const now = new Date().toISOString();
            await storeMessages([
              {id: ids.san, conversation_id: conv, origin: 'mobile', role: 'assistant',
               text: %s, created_at: now, status: 'synced', want_ai: false},
              {id: ids.raw, conversation_id: conv, origin: 'mobile', role: 'assistant',
               text: %s, created_at: now, status: 'synced', want_ai: false}
            ]);
            setActiveConversation(conv);
            await renderMessages();
            window.__linkIds = ids;
            return ids;
          })()
        """ % (json.dumps(sanitizado), json.dumps(bruto)))
        assert ids and ids.get("san") and ids.get("raw"), ids
        inspecionar = """
          (() => {
            const ids = window.__linkIds;
            const inspect = id => {
              const b = document.querySelector('.message[data-mid="' + id + '"] .bubble');
              if (!b) return null;
              const anchors = Array.from(b.querySelectorAll('a')).map(a => ({
                href: a.getAttribute('href'), text: (a.textContent || '').trim(),
                target: a.getAttribute('target') || ''}));
              const blocked = Array.from(b.querySelectorAll('.link-blocked')).map(e => ({
                text: (e.textContent || '').trim(),
                visible: e.getClientRects().length > 0}));
              const r = b.getBoundingClientRect();
              return {anchors, blocked, text: b.textContent || '',
                rect: {left: r.left, right: r.right, top: r.top, bottom: r.bottom},
                visible: b.getClientRects().length > 0,
                width: innerWidth,
                overflow: document.documentElement.scrollWidth > innerWidth + 1};
            };
            return {san: inspect(ids.san), raw: inspect(ids.raw)};
          })()
        """
        links_desktop = cdp.js(inspecionar)
        info_desktop = _checar_links(links_desktop, "desktop")
        cdp.js("""
          (() => {
            const el = document.querySelector('.message[data-mid="' + window.__linkIds.san + '"]');
            if (el) el.scrollIntoView({block: 'center'});
            return true;
          })()
        """)
        time.sleep(0.4)
        cdp.screenshot("04-desktop-links.png")
        etapa("links_desktop_ok", json.dumps(
            {"san_anchors": len(links_desktop["san"]["anchors"]),
             "raw_blocked": len(links_desktop["raw"]["blocked"]),
             "width": links_desktop["san"]["width"]}, ensure_ascii=False))

        # 6) mesmo conteúdo no viewport móvel
        cdp.cmd("Emulation.setDeviceMetricsOverride", {
            "width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": True})
        time.sleep(0.6)
        cdp.js("""
          (() => {
            const el = document.querySelector('.message[data-mid="' + window.__linkIds.raw + '"]');
            if (el) el.scrollIntoView({block: 'center'});
            return true;
          })()
        """)
        time.sleep(0.4)
        links_mobile = cdp.js(inspecionar)
        info_mobile = _checar_links(links_mobile, "mobile")
        cdp.screenshot("05-mobile-links.png")
        etapa("links_mobile_ok", json.dumps(
            {"san_anchors": len(links_mobile["san"]["anchors"]),
             "raw_blocked": len(links_mobile["raw"]["blocked"]),
             "width": links_mobile["san"]["width"]}, ensure_ascii=False))

        erros_js = [e for e in cdp.erros if e.get("tipo") == "exception"]
        assert not erros_js, erros_js
        resultado["resumo"] = {
            "anexo_pendente": {"chips": pendente["n"], "upload_antes": antes["js"],
                               "nome": pendente["name"]},
            "mobile_pendente": {k: mobile_pend[k] for k in
                                ("w", "chips", "left", "right", "top", "bottom", "overflow")},
            "envio": {"uploads_js": perf["js"], "uploads_rede": len(cdp.uploads),
                      "mensagens": mensagens["n"], "docs": docs["n"],
                      "doc_id": docs.get("doc_id", ""),
                      "texto": mensagens["text"]},
            "links_desktop": info_desktop,
            "links_mobile": info_mobile,
            "sanitizado": sanitizado,
            "erros_navegador": cdp.erros,
        }
        resultado["ok"] = True
    except Exception as exc:
        resultado["erro"] = f"{type(exc).__name__}: {exc}"[:1500]
        resultado["logs"] = {nome: _tail(caminho) for nome, caminho in logs.items()}
        raise
    finally:
        if cdp:
            try:
                cdp.ws.close()
            except Exception:
                pass
        for processo in reversed(processos):
            try:
                processo.parar()
            except Exception:
                pass
        (ART / "chrome-e2e.json").write_text(
            json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
        (ART / "chrome-e2e.txt").write_text(
            "\n".join(f"[{e['t']:6.2f}s] {e['etapa']}"
                      + (f": {e['detalhe']}" if e["detalhe"] else "")
                      for e in ETAPAS),
            encoding="utf-8")
        print(json.dumps({k: v for k, v in resultado.items()
                          if k not in ("etapas", "logs")},
                         ensure_ascii=False, indent=1)[:5000])


if __name__ == "__main__":
    main()
