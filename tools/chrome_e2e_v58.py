"""V5.8 real Chrome E2E (desktop + emulated mobile) for the research workspace.

Isolated stack: uvicorn server:app + pc_agent.py, temporary SQLite, temporary
Chrome profile.  The job is persisted before the agent starts, so this exercises
the real relay -> PC -> JDUI path without network providers or production.

Usage: python tools/chrome_e2e_v58.py
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

import hypothesis_engine  # noqa: E402
import media_evidence  # noqa: E402
import pc_agent  # noqa: E402
import research_agents as ra  # noqa: E402
from argon2 import PasswordHasher  # noqa: E402
from websockets.sync.client import connect  # noqa: E402

CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
ART = RAIZ / "qa-artifacts" / "v58"
ART.mkdir(parents=True, exist_ok=True)
INICIO = time.monotonic()
ETAPAS = []


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
        self.ws = connect(ws_url, max_size=None, open_timeout=15, legacy=True)
        self.seq = 0
        self.erros = []

    def _evento(self, msg):
        p = msg.get("params") or {}
        if msg.get("method") == "Runtime.exceptionThrown":
            det = p.get("exceptionDetails") or {}
            self.erros.append({"tipo": "exception",
                               "texto": str(det.get("text") or
                                            det.get("exception", {}).get("description", ""))[:300]})
        elif msg.get("method") == "Log.entryAdded":
            e = p.get("entry") or {}
            texto = str(e.get("text", ""))
            if (e.get("level") == "error" and "favicon" not in texto
                    and "401 (Unauthorized)" not in texto):
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


def preparar_job(db_path: Path) -> str:
    db = pc_agent.open_db(db_path)
    try:
        job = ra.criar_job(db, "local", "A dose de 400 mg de café é segura para adultos?",
                           manual="profunda")
        ra.montar_plano(db, job)
        for step in job["plano"]:
            step["status"] = "feita"
        html = (
            '<html><head><title>Ensaio clínico</title>'
            '<meta property="og:image" content="https://example.com/grafico-cafe.png">'
            '<meta property="article:published_time" content="2026-09-01">'
            '</head><body><a href="https://example.com/estudo.pdf">Estudo completo</a>'
            '<a href="https://www.youtube.com/watch?v=abc123DEF45">Vídeo</a></body></html>'
        )
        job["midia"] = media_evidence.extrair_midia(
            html, "https://example.com/materia-cafe", "Ensaio clínico")
        job["achados"] = [{
            "afirmacao": "O café é seguro em doses de até 400 mg por dia em adultos saudáveis.",
            "estado": "SUPPORTED", "metodo": "verificação lexical determinística",
            "cobertura_lexica": 0.91,
            "evidence_ids": ["ev-v58-1"], "supporting_ids": ["ev-v58-1"],
            "contradicting_ids": [], "fontes_encontradas": 2,
            "fontes_lidas": 1, "fontes_usadas": 1,
            "fontes": [{
                "evidence_id": "ev-v58-1", "title": "Ensaio clínico sobre cafeína",
                "url": "https://example.com/estudo", "domain": "example.com",
                "published_at": "2026-09-01", "relation": "SUPPORTS", "read": True,
                "access_state": "read", "used_excerpt": "Até 400 mg/dia não houve eventos graves.",
            }],
        }]
        ev = ra.registrar_evidencia(
            db, job,
            {"id": "f-v58-1", "titulo": "Ensaio clínico sobre cafeína",
             "url": "https://example.com/estudo", "dominio": "example.com",
             "publicado_em": "2026-09-01", "texto_lido": True,
             "access_state": "read", "trecho_usado": "Até 400 mg/dia não houve eventos graves."},
            "Até 400 mg/dia não houve eventos graves.",
            "O café é seguro em doses de até 400 mg por dia em adultos saudáveis.",
            relacao="sustenta")
        job["achados"][0]["evidence_ids"] = [ev["id"]]
        job["achados"][0]["supporting_ids"] = [ev["id"]]
        job["achados"][0]["fontes"][0]["evidence_id"] = ev["id"]
        job["usados"] = {"buscas": 2, "paginas": 1, "replans": 0}
        job["sintese"] = {"texto": "Síntese extrativa de teste; sem LLM.",
                          "llm": False, "limitacao": "verificação lexical"}
        job["auditoria"] = {"ok": True, "problemas": []}
        job["pendencias"] = []
        job["status"] = "concluida"
        ra.salvar_job(db, job)
        store = hypothesis_engine.HypothesisStore(db)
        store.initialize()
        store.save(hypothesis_engine.Hypothesis(
            hypothesis_id="h-v58-1", owner_id="local", job_id=job["id"],
            statement="A cafeína em 400 mg causa insônia em todos os adultos?",
            status="inconclusive", evidence_ids=("ev-v58-1",),
            missing_evidence=("estudos de sono de longo prazo",),
            next_steps=("buscar ensaios de sono",)))
        return job["id"]
    finally:
        db.close()


def main():
    resultado = {
        "quando": datetime.now().isoformat(timespec="seconds"),
        "tipo_evidencia": "chrome-real-desktop + mobile-emulado; stack local isolado",
        "ambiente": {"chrome": str(CHROME), "python": sys.version.split()[0]},
        "etapas": ETAPAS, "ok": False,
    }
    processos = []
    cdp = None
    tmp = Path(tempfile.mkdtemp(prefix="vexx-v58-chrome-"))
    try:
        if not CHROME.exists():
            raise AssertionError(f"Chrome não encontrado em {CHROME}")
        porta_relay = porta_livre()
        porta_cdp = porta_livre()
        base = f"http://127.0.0.1:{porta_relay}"
        db_path = tmp / "e2e-v58.sqlite3"
        job_id = preparar_job(db_path)
        etapa("job_preparado", job_id)
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
        })
        env.pop("JULIA_AI_FALLBACKS", None)
        resultado["ambiente"].update({
            "app": base, "sqlite": str(db_path), "job_id": job_id,
            "viewport_desktop": "1280x900", "viewport_mobile": "390x844"})

        etapa("relay", base)
        relay = Processo([sys.executable, "-m", "uvicorn", "server:app",
                          "--host", "127.0.0.1", "--port", str(porta_relay)],
                         tmp / "relay.log", env)
        processos.append(relay)
        esperar_http(base + "/api/diag", lambda c: True, 40, "relay")
        etapa("agente", "pc_agent.py")
        agente = Processo([sys.executable, "pc_agent.py"], tmp / "agent.log", env)
        processos.append(agente)
        esperar_http(base + "/api/diag", lambda c: c.get("pc_online") is True, 60, "agente")

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
        versao = esperar_http(f"http://127.0.0.1:{porta_cdp}/json/version",
                              lambda c: bool(c.get("webSocketDebuggerUrl")), 30, "chrome")
        resultado["ambiente"]["chrome_versao"] = versao.get("Browser", "")

        pedido = urllib.request.Request(
            f"http://127.0.0.1:{porta_cdp}/json/new?"
            + urllib.parse.quote(base + "/", safe=":/?=&"), method="PUT")
        with urllib.request.urlopen(pedido, timeout=15) as r:
            pagina = json.loads(r.read().decode())
        cdp = CDP(pagina["webSocketDebuggerUrl"])
        for dominio in ("Page", "Runtime", "Log", "Network"):
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
        etapa("login_ok", "sessão local")

        cdp.js("document.querySelector('.drawer-item[data-tab=\"research\"]').click()")
        cdp.esperar_js("(document.getElementById('page-research')||{}).hidden",
                       lambda v: v is False, 10, "página de pesquisas")
        cdp.esperar_js(
            "Array.from(document.querySelectorAll('#researchJobList .doc-item strong'))"
            ".map(e => e.textContent).join(' | ')",
            lambda v: isinstance(v, str) and "café" in v.lower(), 20, "lista de pesquisas")
        etapa("lista_pesquisas_ok")
        cdp.screenshot("research-workspace-desktop.png")

        cdp.js("""
          (() => {
            const card = document.querySelector('#researchJobList .doc-item');
            const b = Array.from(card.querySelectorAll('button'))
              .find(x => x.textContent.trim() === 'Abrir');
            b.click(); return true;
          })()
        """)
        cdp.esperar_js("document.querySelectorAll('#researchWorkspaceView .jdui-slot').length",
                       lambda v: isinstance(v, int) and v >= 4, 25, "componentes JDUI")
        resumo = cdp.js("""
          (() => ({
            texto: document.getElementById('researchWorkspaceView').textContent || '',
            slots: document.querySelectorAll('#researchWorkspaceView .jdui-slot').length,
            planos: document.querySelectorAll('#researchWorkspaceView .jdui-node').length,
            midia: document.querySelectorAll('#researchWorkspaceView .jdui-pcard').length,
            badges: document.querySelectorAll('#researchWorkspaceView .jdui-badge').length,
            overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
            titulo: document.getElementById('researchWorkspaceTitle').textContent || ''
          }))()
        """)
        assert "Plano de pesquisa" in resumo["texto"], resumo["texto"][:500]
        assert "não é evidência" in resumo["texto"].lower(), resumo["texto"][:500]
        assert resumo["planos"] >= 6 and resumo["midia"] >= 1 and resumo["badges"] >= 1, resumo
        assert "Sustentada" in resumo["texto"], resumo["texto"][:500]
        assert not resumo["overflow"], "overflow horizontal no desktop"
        etapa("workspace_ok", json.dumps({k: v for k, v in resumo.items() if k != "texto"},
                                        ensure_ascii=False))
        cdp.screenshot("research-workspace-desktop-detail.png")
        cdp.js("""
          (() => {
            const slot = Array.from(document.querySelectorAll('#researchWorkspaceView .jdui-slot'))
              .find(s => s.textContent.indexOf('Evidências por afirmação') >= 0);
            if (slot) {
              const det = slot.querySelector('details');
              if (det) det.open = true;
              slot.scrollIntoView({block: 'start'});
            }
            return !!slot;
          })()
        """)
        time.sleep(0.4)
        cdp.screenshot("research-workspace-desktop-evidence.png")
        cdp.js("""
          (() => {
            const cards = document.querySelectorAll('#researchWorkspaceView .jdui-srccard');
            (cards[cards.length - 1] || document.getElementById('researchWorkspaceView'))
              .scrollIntoView({block: 'center'});
            return true;
          })()
        """)
        time.sleep(0.4)
        cdp.screenshot("research-workspace-desktop-evidence-media.png")

        export = cdp.js("""
          (async () => {
            const r = await fetch('/api/research/export?job_id=%s&formato=md',
                                  {cache: 'no-store'});
            const b = await r.arrayBuffer();
            return {status: r.status, type: r.headers.get('content-type'),
              disp: r.headers.get('content-disposition'),
              bytes: b.byteLength, inicio: new TextDecoder().decode(b.slice(0, 80))};
          })()
        """ % job_id)
        assert export["status"] == 200 and export["bytes"] > 500, export
        assert "attachment" in (export["disp"] or "") and "text/markdown" in export["type"]
        assert "Relatório" in export["inicio"]
        etapa("export_bytes_ok", f"{export['bytes']} bytes via Chrome")

        cdp.cmd("Emulation.setDeviceMetricsOverride", {
            "width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": True})
        time.sleep(0.8)
        mobile = cdp.js("""
          (() => ({
            overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
            width: window.innerWidth,
            botoes: Array.from(document.querySelectorAll('#researchWorkspaceView .jdui-btn'))
              .every(b => { const r = b.getBoundingClientRect(); return r.height >= 36; })
          }))()
        """)
        assert not mobile["overflow"], mobile
        assert mobile["width"] == 390 and mobile["botoes"], mobile
        cdp.screenshot("research-workspace-mobile.png")
        etapa("mobile_emulado_ok", json.dumps(mobile))

        assert not cdp.erros, cdp.erros
        resultado["resumo_ui"] = {k: v for k, v in resumo.items() if k != "texto"}
        resultado["export"] = export
        resultado["mobile"] = mobile
        resultado["ok"] = True
    except Exception as exc:
        resultado["erro"] = f"{type(exc).__name__}: {exc}"[:1000]
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
            "\n".join(f"[{e['t']:6.2f}s] {e['etapa']}: {e['detalhe']}" for e in ETAPAS),
            encoding="utf-8")
        print(json.dumps({k: v for k, v in resultado.items() if k != "etapas"},
                         ensure_ascii=False, indent=1)[:3000])


if __name__ == "__main__":
    main()
