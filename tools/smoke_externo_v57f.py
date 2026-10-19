"""Smoke externo leve V5.7 FINAL — rede real, sem contornar bloqueios.

Exercita as camadas determinísticas do pipeline: pesquisa real (orquestrador),
leitura de página pedida pelo usuário, montagem do prompt com fetch real,
shopping real e status do proxy Hermes. Não usa LLM para gerar resposta e NÃO
testa o serviço publicado (deploy proibido nesta rodada).

Uso: python tools/smoke_externo_v57f.py [--salvar]
"""
import json
import socket
import sys
import tempfile
import time
import urllib.request
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
import pc_agent  # noqa: E402
import research  # noqa: E402
import shopping  # noqa: E402

out = {"quando": datetime.now().isoformat(timespec="seconds"), "resultados": {}}


def _db(nome):
    return pc_agent.open_db(Path(tempfile.mkdtemp()) / nome)


def _registra(nome, fn):
    t0 = time.monotonic()
    try:
        dados = fn() or {}
    except Exception as exc:
        dados = {"erro_inesperado": f"{type(exc).__name__}: {exc}"}
    dados["segundos"] = round(time.monotonic() - t0, 1)
    out["resultados"][nome] = dados


# 0) Proxy Hermes: disponível ou bloqueado (sem inventar)
def _hermes():
    h = {"porta_8645": False}
    try:
        with socket.create_connection(("127.0.0.1", 8645), timeout=1.5):
            h["porta_8645"] = True
    except OSError as exc:
        h["erro"] = f"{type(exc).__name__}: {exc}"
        return h
    try:
        r = urllib.request.urlopen("http://127.0.0.1:8645/v1/models", timeout=3)
        h["v1_models_http"] = getattr(r, "status", 0)
        h["v1_models_amostra"] = r.read(300).decode("utf-8", "ignore")
    except Exception as exc:
        h["v1_models_erro"] = f"{type(exc).__name__}: {exc}"
    return h


_registra("hermes", _hermes)

URL_WIKI = "https://pt.wikipedia.org/wiki/Fotoss%C3%ADntese"


# 1) Pesquisa real (orquestrador: Bing/DDG presentes no ambiente)
def _pesquisa():
    db = _db("smoke1.sqlite3")
    try:
        rap = research.pesquisa_rapida(db, "smoke", "fotossíntese rendimento plantas")
        fontes = rap.get("fontes") or []
        bloco = research.bloco_grounding(fontes, "18/10/2026", rap) if fontes else ""
        return {
            "estado": rap.get("estado"),
            "fontes": len(fontes),
            "abertas": sum(1 for f in fontes if f.get("status") == "aberta"),
            "com_texto_lido": sum(1 for f in fontes if (f.get("texto_lido") or "").strip()),
            "amostra": [{"url": f.get("url"), "status": f.get("status"),
                         "texto_lido_chars": len(f.get("texto_lido") or "")}
                        for f in fontes[:3]],
            "grounding_chars": len(bloco),
            "provedores": rap.get("provedores", {}),
        }
    finally:
        db.close()


_registra("pesquisa_rapida", _pesquisa)


# 2) Página pedida: Wikipedia (deve abrir) e Magalu (bloqueio honesto)
def _wiki():
    fonte, erro = research.analisar_url(URL_WIKI, consulta="fotossíntese rendimento")
    texto = (fonte or {}).get("texto_lido") or ""
    return {"erro": erro, "titulo": (fonte or {}).get("titulo", ""),
            "status": (fonte or {}).get("status", ""),
            "texto_lido_chars": len(texto),
            "trecho_amostra": texto[:160]}


def _magalu():
    fonte, erro = research.analisar_url(
        "https://www.magazineluiza.com.br/busca/fone+bluetooth/",
        consulta="fone bluetooth")
    return {"erro": erro, "tem_fonte": bool(fonte)}


_registra("analisar_url_wikipedia", _wiki)
_registra("analisar_url_magalu", _magalu)


# 3) Shopping real (provedores do ambiente; bloqueio não é contornado)
def _shopping():
    db = _db("smoke2.sqlite3")
    try:
        res = shopping.pesquisar(db, "smoke", "fone bluetooth até R$ 300")
        produtos = res.get("produtos") or []
        desc = res.get("descoberta") if isinstance(res.get("descoberta"), dict) else {}
        return {
            "produtos": len(produtos),
            "confirmados_com_url": sum(
                1 for p in produtos
                if (p.get("url_item") or p.get("url") or "").startswith("http")),
            "com_preco_numerico": sum(1 for p in produtos if p.get("preco_valor")),
            "motivo_final": res.get("motivo_final") or desc.get("motivo_final", ""),
            "amostra": [{"nome": (p.get("nome") or "")[:60],
                         "preco": p.get("preco_texto") or p.get("preco"),
                         "url": (p.get("url_item") or p.get("url") or "")[:120]}
                        for p in produtos[:3]],
        }
    finally:
        db.close()


_registra("shopping_real", _shopping)


# 4) Prompt com a página do usuário (fetch real)
def _prompt_pagina():
    db = _db("smoke3.sqlite3")
    try:
        cfg = {"proxy": "http://127.0.0.1:9/v1", "model": "m", "system": "BASE",
               "context": 12, "max_tokens": 500, "memoria_global": True,
               "pesquisa_web": True}
        msgs, extras = pc_agent.ai_montar_mensagens(
            db, "smoke-p", cfg, "analise esta página para mim: " + URL_WIKI)
        sistema = msgs[0]["content"] if msgs else ""
        fontes = extras.get("fontes") or []
        texto = (fontes[0].get("texto_lido") or "") if fontes else ""
        amostra = texto[40:110] if len(texto) > 110 else ""
        return {
            "pagina_usuario": extras.get("pagina_usuario", ""),
            "fontes": len(fontes),
            "prompt_chars": len(sistema),
            "prompt_tem_amostra_do_texto": bool(amostra and amostra in sistema),
            "pesquisa_generica_extra": bool(extras.get("pesquisa_descoberta")),
        }
    finally:
        db.close()


_registra("prompt_pagina_usuario", _prompt_pagina)

saida = json.dumps(out, ensure_ascii=False, indent=1)
print(saida[:7000])
if "--salvar" in sys.argv:
    alvo = (RAIZ / "qa-artifacts" / "v57"
            / f"smoke-externo-v57f-{datetime.now().strftime('%Y-%m-%d')}.json")
    alvo.parent.mkdir(parents=True, exist_ok=True)
    alvo.write_text(saida, encoding="utf-8")
    print("artefato:", alvo)
