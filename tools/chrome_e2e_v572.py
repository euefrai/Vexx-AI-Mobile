"""V5.7.2 — E2E no Chrome REAL (desktop + mobile emulado) via CDP.

Sobe um stack ISOLADO (relay server:app + pc_agent.py, SQLite temporário,
portas livres), com o Hermes real local (modelo já configurado, free) e
dirige o Chrome instalado por DevTools Protocol — sem Playwright.

Valida, com o navegador de verdade:
1. login pela interface;
2. envio de mensagem e resposta em streaming (texto não vazio);
3. render de um card JDUI (productcard) e de uma fonte com
   `origem_declarada` — mensagem injetada pelo MESMO /api/sync usado pelo app;
4. layout desktop (1280x900) e mobile emulado (390x844), sem overflow
   horizontal; screenshots e console/erros de rede salvos como evidência.

Nunca toca a produção: portas e SQLite próprios, Chrome com perfil temporário.
Uso: python tools/chrome_e2e_v572.py
"""
import base64
import http.cookiejar
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

import jdui  # noqa: E402
import research  # noqa: E402
import shopping  # noqa: E402
from argon2 import PasswordHasher  # noqa: E402
from websockets.sync.client import connect  # noqa: E402

CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
ART = RAIZ / "qa-artifacts" / "v572" / "chrome"
ART.mkdir(parents=True, exist_ok=True)
INICIO = time.monotonic()
ETAPAS = []


def etapa(nome, detalhe="", segundos=None):
    item = {"etapa": nome, "detalhe": detalhe,
            "t": round(time.monotonic() - INICIO, 2)}
    if segundos is not None:
        item["segundos"] = round(segundos, 2)
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


class Processo:
    def __init__(self, cmd, log, env, cwd=RAIZ):
        self.log = Path(log)
        self._fh = self.log.open("wb")
        self.proc = subprocess.Popen(cmd, cwd=str(cwd), env=env,
                                     stdout=self._fh, stderr=subprocess.STDOUT)

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
        self.ws = connect(ws_url, max_size=None, open_timeout=15)
        self.seq = 0
        self.eventos = []
        self.erros = []

    def _evento(self, msg):
        metodo = msg.get("method") or ""
        p = msg.get("params") or {}
        if metodo == "Runtime.consoleAPICalled" and p.get("type") == "error":
            texto = " ".join(str(a.get("value", a.get("description", "")))
                             for a in (p.get("args") or []))[:300]
            self.erros.append({"tipo": "console", "texto": texto})
        elif metodo == "Runtime.exceptionThrown":
            det = p.get("exceptionDetails") or {}
            self.erros.append({"tipo": "exception",
                               "texto": str(det.get("text") or det.get("exception", {}).get("description", ""))[:300]})
        elif metodo == "Log.entryAdded":
            e = p.get("entry") or {}
            if e.get("level") == "error":
                self.erros.append({"tipo": "log", "texto": str(e.get("text", ""))[:300]})
        elif metodo == "Network.loadingFailed":
            self.eventos.append({"tipo": "net_fail",
                                 "texto": str(p.get("errorText", ""))[:200]})

    def cmd(self, metodo, params=None, timeout=60):
        self.seq += 1
        meu = self.seq
        self.ws.send(json.dumps({"id": meu, "method": metodo,
                                 "params": params or {}}))
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
        res = r.get("result") or {}
        if r.get("exceptionDetails"):
            raise RuntimeError(f"JS falhou: {r['exceptionDetails']}")
        return res.get("value")

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
            time.sleep(0.5)
        raise AssertionError(f"{nome} não ocorreu em {timeout}s (último: {ultimo})")

    def screenshot(self, nome):
        r = self.cmd("Page.captureScreenshot", {"format": "png"})
        destino = ART / nome
        destino.write_bytes(base64.b64decode(r.get("data", "")))
        etapa("screenshot", nome, None)
        return str(destino)

    def fechar(self):
        try:
            self.ws.close()
        except Exception:
            pass


def _produto_para_card():
    """Produto REAL (KaBuM) quando acessível; fixture explícita se bloqueado."""
    url = ("https://www.kabum.com.br/produto/927806/"
           "fone-de-ouvido-philips-tat1139-bluetooth-true-wireless-preto")
    try:
        final, html = research.baixar(url, timeout=10)
        ofertas = shopping.extrair_ofertas_jsonld(html)
        if ofertas:
            ext = dict(ofertas[0])
            ext["origem_preco"] = "jsonld"
            p = shopping.montar_produto(ext, url, final or url, "KaBuM")
            p["link_veredito"] = "parcial"
            shopping.verificar_imagens([p], maximo=1)
            return p, url, "real:kabum"
    except Exception as exc:
        etapa("produto_real_falhou", f"{type(exc).__name__}: {exc}"[:160])
    p = {"nome": "Fone de Ouvido Philips (fixture de renderização)",
         "preco": 110.12, "preco_texto": "R$ 110,12", "moeda": "BRL",
         "loja": "KaBuM", "url_item": url, "url": url,
         "imagem": "", "imagem_veredito": "", "link_veredito": "parcial",
         "link_codigo": "ok", "disponibilidade": "desconhecida",
         "specs": {"Conexão": "Bluetooth"}}
    return p, url, "fixture:render"


def _mensagem_card(p, url, origem):
    fontes = [{"id": "S1", "titulo": "KaBuM", "url": url}]
    fence_produto = shopping.fence_resultado({"produtos": [p], "fontes": fontes})
    assert fence_produto, "fence do produto não gerou mensagem válida"
    src = {"version": jdui.VERSION, "blocks": [{
        "type": "ui", "component": "sources", "props": {
            "title": "Fontes",
            "items": [{"titulo": "Manual do fabricante",
                       "url": "https://example.com/manual",
                       "dominio": "example.com",
                       "trecho": "Trecho de exemplo para o selo de origem declarada.",
                       "status": "encontrada",
                       "origem_declarada": "Manual do fabricante"}]}}]}
    ok, _, erros = jdui.validar_mensagem(src)
    assert ok, erros
    fence_fonte = "\n\n```jdui\n" + json.dumps(src, ensure_ascii=False) + "\n```"
    texto = ("Verificação de interface V5.7.2 (" + origem + "): card e fonte "
             "renderizados pelo app real." + fence_produto + fence_fonte)
    return texto, p


def _login_api(base):
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

    def call(path, data, csrf=""):
        req = urllib.request.Request(
            base + path, data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        if csrf:
            req.add_header("X-CSRF-Token", csrf)
        with op.open(req, timeout=60) as r:
            return json.loads(r.read().decode() or "{}")

    sess = call("/api/login", {"username": "efrai",
                               "password": "strong-example-password"})
    return sess["csrf"], call


def main():
    resultado = {
        "quando": datetime.now().isoformat(timespec="seconds"),
        "ambiente": {"chrome": str(CHROME), "python": sys.version.split()[0]},
        "etapas": ETAPAS, "ok": False,
    }
    processos = []
    cdp = None
    tmp = Path(tempfile.mkdtemp(prefix="vexx-chrome-"))
    try:
        if not CHROME.exists():
            raise AssertionError(f"Chrome não encontrado em {CHROME}")
        porta_relay = porta_livre()
        porta_cdp = porta_livre()
        base = f"http://127.0.0.1:{porta_relay}"
        env = dict(os.environ)
        env.update({
            "JULIA_USERNAME": "efrai",
            "JULIA_PASSWORD_HASH": PasswordHasher().hash("strong-example-password"),
            "JULIA_SESSION_SECRET": "a" * 64,
            "JULIA_AGENT_TOKEN": "b" * 64,
            "JULIA_RELAY_URL": base,
            "JULIA_SQLITE_PATH": str(tmp / "e2e.sqlite3"),
            "HERMES_PROXY_URL": os.environ.get("HERMES_PROXY_URL",
                                               "http://127.0.0.1:8645/v1"),
            "JULIA_AI_MODEL": os.environ.get("JULIA_AI_MODEL",
                                             "poolside/laguna-s-2.1:free"),
        })
        env.pop("JULIA_AI_FALLBACKS", None)
        resultado["ambiente"].update({
            "app": base, "sqlite": env["JULIA_SQLITE_PATH"],
            "hermes": env["HERMES_PROXY_URL"], "modelo": env["JULIA_AI_MODEL"],
            "viewport_desktop": "1280x900", "viewport_mobile": "390x844"})

        etapa("relay", f"uvicorn server:app em {base}")
        relay = Processo([sys.executable, "-m", "uvicorn", "server:app",
                          "--host", "127.0.0.1", "--port", str(porta_relay)],
                         tmp / "relay.log", env)
        processos.append(relay)
        esperar_http(base + "/api/diag", lambda c: True, 40, "relay")
        etapa("agente", "pc_agent.py conectando ao relay")
        agente = Processo([sys.executable, "pc_agent.py"], tmp / "agent.log", env)
        processos.append(agente)
        esperar_http(base + "/api/diag", lambda c: c.get("pc_online") is True,
                     60, "agente")
        etapa("stack_pronto", "relay + agente online")

        etapa("chrome", f"headless CDP porta {porta_cdp}")
        chrome_proc = subprocess.Popen(
            [str(CHROME), "--headless=new",
             f"--remote-debugging-port={porta_cdp}",
             f"--user-data-dir={tmp / 'chrome-profile'}",
             "--no-first-run", "--no-default-browser-check", "--disable-gpu",
             "--disable-extensions", "--disable-background-networking",
             "--disable-sync", "--metrics-recording-only",
             "--window-size=1280,900", "about:blank"],
            stdout=(tmp / "chrome.log").open("wb"),
            stderr=subprocess.STDOUT)
        processos.append(type("ChromeProc", (), {
            "proc": chrome_proc, "parar": lambda self: (
                subprocess.run(["taskkill", "/T", "/F", "/PID",
                                str(chrome_proc.pid)], capture_output=True)
                if chrome_proc.poll() is None else None)})())
        versao = esperar_http(f"http://127.0.0.1:{porta_cdp}/json/version",
                              lambda c: bool(c.get("webSocketDebuggerUrl")),
                              30, "chrome")
        resultado["ambiente"]["chrome_versao"] = versao.get("Browser", "")

        pedido = urllib.request.Request(
            f"http://127.0.0.1:{porta_cdp}/json/new?"
            + urllib.parse.quote(base + "/", safe=":/?=&"),
            method="PUT")
        with urllib.request.urlopen(pedido, timeout=15) as r:
            pagina = json.loads(r.read().decode())
        cdp = CDP(pagina["webSocketDebuggerUrl"])
        for dominio in ("Page", "Runtime", "Log", "Network"):
            cdp.cmd(dominio + ".enable")

        cdp.cmd("Page.navigate", {"url": base + "/"})
        cdp.esperar_js("document.readyState", lambda v: v == "complete", 30,
                       "load da aplicação")
        cdp.esperar_js("!!document.getElementById('loginOverlay')",
                       lambda v: v is True, 20, "overlay de login")
        etapa("pagina_carregada", base + "/")

        cdp.js("""
          (() => {
            document.getElementById('loginUser').value = 'efrai';
            document.getElementById('loginPassword').value = 'strong-example-password';
            document.getElementById('loginForm').requestSubmit();
            return true;
          })()
        """)
        cdp.esperar_js(
            "({oculto: !!(document.getElementById('loginOverlay')||{}).hidden,"
            " erro: (document.getElementById('loginError')||{}).textContent || ''})",
            lambda v: isinstance(v, dict) and v.get("oculto") is True,
            30, "login pela interface")
        cdp.esperar_js("!!document.getElementById('messageInput')",
                       lambda v: v is True, 15, "compositor")
        conversa = cdp.js(
            "localStorage.getItem('julia-active-conversation') || ''")
        assert conversa, "conversation id ausente após login"
        etapa("login_ok", f"conversa {conversa}")

        base_texto = cdp.js(
            "(document.getElementById('conversation')||{}).textContent || ''")
        pergunta = "Oi, Júlia! Em uma frase curta, o que é fotossíntese?"
        t0 = time.monotonic()
        cdp.js("""
          (() => {
            const i = document.getElementById('messageInput');
            i.value = %s;
            i.dispatchEvent(new Event('input', {bubbles: true}));
            document.getElementById('composer').requestSubmit();
            return true;
          })()
        """ % json.dumps(pergunta, ensure_ascii=False))
        estado = {"txt": base_texto, "estavel": 0}

        def _pronto(v):
            if not isinstance(v, dict):
                return False
            txt = v.get("txt") or ""
            cresceu = len(txt) > len(base_texto) + 40
            estado["estavel"] = estado["estavel"] + 1 if (cresceu and not v.get("busy")) else 0
            return cresceu and not v.get("busy") and estado["estavel"] >= 2

        final = cdp.esperar_js(
            "({txt: (document.getElementById('conversation')||{}).textContent || '',"
            "  busy: !!(document.getElementById('genBar') && !document.getElementById('genBar').hidden)})",
            _pronto, 240, "resposta do chat")
        resposta = final.get("txt") or ""
        latencia = round(time.monotonic() - t0, 2)
        etapa("chat_real", f"{latencia}s, {len(resposta)} chars", latencia)
        assert pergunta[:30] in resposta, "mensagem do usuário não apareceu"
        assert "fotoss" in resposta.lower(), \
            f"resposta não trata de fotossíntese: {resposta[-300:]}"
        cdp.screenshot("desktop-chat.png")
        resultado["chat_real"] = {
            "pergunta": pergunta, "latencia_s": latencia,
            "resposta_chars": len(resposta),
            "resposta_recorte": resposta[-600:],
        }

        produto, url_produto, origem_produto = _produto_para_card()
        texto_card, produto = _mensagem_card(produto, url_produto, origem_produto)
        csrf, call = _login_api(base)
        msg_id = "e2e-card-" + datetime.now().strftime("%H%M%S")
        sincronizado = call("/api/sync", {"messages": [{
            "id": msg_id, "conversation_id": conversa, "role": "assistant",
            "text": texto_card,
            "created_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "origin": "mobile"}]}, csrf)
        assert msg_id in (sincronizado.get("confirmed_ids") or []), sincronizado
        etapa("card_injetado", f"{origem_produto} | {produto.get('preco_texto')}")

        cdp.cmd("Page.reload", {"ignoreCache": False})
        cdp.esperar_js("document.readyState", lambda v: v == "complete", 30,
                       "reload")
        card_txt = cdp.esperar_js(
            "(document.getElementById('conversation')||{}).textContent || ''",
            lambda v: isinstance(v, str) and "original declarado: Manual do fabricante" in v,
            40, "card JDUI na conversa")
        preco = str(produto.get("preco_texto") or "").replace("\u00a0", " ").strip()
        assert preco and preco in card_txt, f"preço do card ausente: {preco}"
        assert "Philips" in card_txt, "nome do produto ausente no card"
        assert cdp.js("!!document.querySelector('.jdui-pcard')") is True, \
            "elemento do productcard ausente no DOM real"
        cdp.js("(() => { const c = document.querySelector('.jdui-pcard');"
               " if (c) c.scrollIntoView({block: 'center'}); return true; })()")
        time.sleep(0.4)
        etapa("card_render_desktop", "preço + card + fonte declarada visíveis")
        cdp.screenshot("desktop-card.png")

        overflow_desktop = cdp.js(
            "({sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth,"
            " iw: window.innerWidth})")
        resultado["desktop"] = {
            "screenshot_chat": str(ART / "desktop-chat.png"),
            "screenshot_card": str(ART / "desktop-card.png"),
            "overflow": overflow_desktop,
            "card": {"origem": origem_produto, "preco": preco,
                     "imagem_veredito": produto.get("imagem_veredito"),
                     "link_veredito": produto.get("link_veredito")},
        }
        assert overflow_desktop["sw"] <= overflow_desktop["cw"] + 1, \
            f"overflow horizontal no desktop: {overflow_desktop}"

        cdp.cmd("Emulation.setDeviceMetricsOverride", {
            "width": 390, "height": 844, "deviceScaleFactor": 2,
            "mobile": True})
        cdp.cmd("Emulation.setTouchEmulationEnabled", {"enabled": True})
        cdp.cmd("Page.reload", {"ignoreCache": False})
        cdp.esperar_js("document.readyState", lambda v: v == "complete", 30,
                       "reload mobile")
        card_mobile = cdp.esperar_js(
            "(document.getElementById('conversation')||{}).textContent || ''",
            lambda v: isinstance(v, str) and "original declarado: Manual do fabricante" in v,
            40, "card no mobile")
        assert preco in card_mobile, "preço ausente no mobile"
        cdp.js("(() => { const c = document.querySelector('.jdui-pcard');"
               " if (c) c.scrollIntoView({block: 'center'}); return true; })()")
        time.sleep(0.4)
        overflow_mobile = cdp.js(
            "({sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth,"
            " iw: window.innerWidth, dpr: window.devicePixelRatio})")
        cdp.screenshot("mobile-card.png")
        etapa("mobile_emulado", f"390x844, overflow {overflow_mobile}")
        resultado["mobile"] = {
            "emulado": "390x844 (mobile=true, touch=true)",
            "screenshot": str(ART / "mobile-card.png"),
            "overflow": overflow_mobile,
            "observacao": "emulação do Chrome — NÃO é teste em Android/iOS físico",
        }
        assert overflow_mobile["sw"] <= overflow_mobile["cw"] + 1, \
            f"overflow horizontal no mobile: {overflow_mobile}"

        erros_relevantes = [e for e in (cdp.erros or [])
                            if "favicon" not in (e.get("texto") or "").lower()]
        resultado["console_erros"] = erros_relevantes
        resultado["rede_falhas"] = [e for e in cdp.eventos
                                     if e.get("tipo") == "net_fail"][:20]
        assert not any(e["tipo"] == "exception" for e in erros_relevantes), \
            f"exceções no navegador: {erros_relevantes}"
        etapa("console", f"{len(erros_relevantes)} erros de console")
        resultado["ok"] = True
    except Exception as exc:
        resultado["erro"] = f"{type(exc).__name__}: {exc}"
        etapa("FALHA", resultado["erro"][:400])
        raise
    finally:
        if cdp is not None:
            cdp.fechar()
        for p in reversed(processos):
            try:
                p.parar()
            except Exception:
                pass
        destino = ART / f"chrome-e2e-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        destino.write_text(json.dumps(resultado, ensure_ascii=False, indent=1),
                           encoding="utf-8")
        print("evidencia:", destino)


if __name__ == "__main__":
    main()
