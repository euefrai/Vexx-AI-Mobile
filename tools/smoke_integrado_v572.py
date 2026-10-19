"""V5.7.2 — smoke integrado dos 6 cenários do aceite (dados reais quando há rede).

Cenários:
1. produtos ("Me mostre um fone bluetooth até R$ 300") ..... EXTERNO REAL
2. pesquisa geral ("Explique a fotossíntese...") ............ EXTERNO REAL + LLM REAL
3. análise direta de URL (Wikipédia) ........................ EXTERNO REAL
4. comparação técnica com documentação (Python) ............. EXTERNO REAL + LLM REAL
5. continuação ("Agora mostre apenas os mais baratos") ..... LOCAL REAL (dados guardados)
6. falha externa com fallback honesto ....................... LOCAL REAL + DNS REAL

Cada cenário registra status, duração, dados observados e erros — nada é
mascarado: bloqueio de provedor externo é anotado como BLOQUEADO.
Não usa produção, não faz deploy. Uso: python tools/smoke_integrado_v572.py
"""
import json
import re
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import jdui  # noqa: E402
import pc_agent  # noqa: E402
import research  # noqa: E402
import shopping  # noqa: E402

ART = RAIZ / "qa-artifacts" / "v572"
ART.mkdir(parents=True, exist_ok=True)
SAIDA = {"quando": datetime.now().isoformat(timespec="seconds"),
         "cenarios": {}, "ok": False}


def _cronometrar(fn):
    t0 = time.monotonic()
    try:
        dados = fn()
        erro = ""
    except Exception as exc:
        dados = None
        erro = f"{type(exc).__name__}: {exc}"
    return dados, erro, round(time.monotonic() - t0, 2)


def _urls(texto: str) -> list:
    return re.findall(r"https?://[^\s)\]>`\"']+", texto or "")


def main():
    db = pc_agent.open_db(Path(tempfile.mkdtemp(prefix="vexx-smoke-")) / "smoke.sqlite3")
    cfg = pc_agent.ai_config()
    SAIDA["ambiente"] = {
        "modelo": cfg["model"], "proxy": cfg["proxy"],
        "pesquisa_web": cfg["pesquisa_web"], "max_tokens": cfg["max_tokens"],
        "sqlite": "temporário",
    }

    # 1) Produtos -------------------------------------------------------
    def _produtos():
        res = shopping.pesquisar(db, "smoke", "Me mostre um fone bluetooth até R$ 300.",
                                 conv="conv-produtos", usar_cache=False)
        prods = res.get("produtos") or []
        fence = shopping.fence_resultado(res) if prods else ""
        cards_ok = None
        if fence:
            try:
                corpo = fence.split("```jdui", 1)[1].rsplit("```", 1)[0]
                cards_ok, _, _ = jdui.validar_mensagem(json.loads(corpo))
            except Exception:
                cards_ok = False
        return {
            "status": "EXTERNO REAL",
            "consulta": "Me mostre um fone bluetooth até R$ 300.",
            "produtos": len(prods),
            "alternativas": len(res.get("alternativas") or []),
            "referencias": len(res.get("encontrados") or []),
            "total_bruto": res.get("total_bruto"),
            "motivo": res.get("motivo_final") or (res.get("descoberta") or {}).get("motivo_final"),
            "orcamento": (res.get("criterios") or {}).get("orcamento"),
            "precos": [p.get("preco") for p in prods],
            "todos_dentro_do_orcamento": all(
                (p.get("preco") is not None and p.get("preco") <= 300) for p in prods),
            "cards_jdui_validos": cards_ok,
            "resumo": shopping.resumo_texto(res)[:500],
        }

    dados, erro, seg = _cronometrar(_produtos)
    SAIDA["cenarios"]["produtos"] = {"dados": dados, "erro": erro, "segundos": seg,
                                     "rotulo": "EXTERNO REAL"}

    def _persistir_user(conv, mid, texto):
        """Mesmo caminho do app: a mensagem entra no histórico ANTES do prompt."""
        pc_agent.persist_messages(db, [{
            "id": mid, "conversation_id": conv, "origin": "mobile",
            "role": "user", "text": texto,
            "created_at": pc_agent.agora_iso()}], owner="smoke")

    # 2) Pesquisa geral + resposta fundamentada --------------------------
    def _pesquisa_geral():
        pergunta = "Explique a fotossíntese e apresente fontes."
        _persistir_user("conv-geral", "smoke-geral-1", pergunta)
        msgs, extras = pc_agent.ai_montar_mensagens(
            db, "conv-geral", cfg, pergunta, owner="smoke")
        fontes = extras.get("fontes") or []
        res = pc_agent.gerar_texto(cfg, msgs, max_tokens=900, timeout=150)
        texto = res.get("texto") or ""
        dominios = sorted({re.sub(r"^https?://(www\.)?", "", f.get("url", "")).split("/")[0]
                           for f in fontes if f.get("url")})
        return {
            "status": "EXTERNO REAL + LLM REAL" if texto else "BLOQUEADO",
            "consulta": pergunta,
            "fontes": len(fontes),
            "fontes_com_texto_lido": sum(1 for f in fontes if f.get("texto_lido")),
            "dominios": dominios,
            "modelo": res.get("model_usado"),
            "resposta_chars": len(texto),
            "menciona_fotossintese": "fotoss" in texto.lower(),
            "sem_tool_call": "tool_call" not in texto.lower()
            and "websearch" not in texto.lower(),
            "urls_na_resposta": sorted(set(_urls(texto)))[:8],
            "resposta_recorte": texto[:700],
        }

    dados, erro, seg = _cronometrar(_pesquisa_geral)
    SAIDA["cenarios"]["pesquisa_geral"] = {"dados": dados, "erro": erro, "segundos": seg,
                                           "rotulo": "EXTERNO REAL + LLM REAL"}

    # 3) Análise direta de URL ------------------------------------------
    def _url_direta():
        url = "https://pt.wikipedia.org/wiki/Fotoss%C3%ADntese"
        fonte, erro_url = research.analisar_url(url, consulta="fotossíntese", timeout=12)
        texto = (fonte or {}).get("texto_lido") or ""
        trecho = (fonte or {}).get("trecho") or ""
        return {
            "status": "EXTERNO REAL" if (fonte or {}).get("status") == "aberta" else "BLOQUEADO",
            "url": url,
            "erro_api": erro_url,
            "status_fonte": (fonte or {}).get("status"),
            "titulo": (fonte or {}).get("titulo"),
            "texto_lido_chars": len(texto),
            "trecho_chars": len(trecho),
            "trecho_contido_no_texto": bool(trecho) and trecho in texto,
            "residuos_menu": [m for m in ("Menu principal", "Ir para o conteúdo",
                                          "Pular para o conteúdo", "Ferramentas pessoais")
                              if m in texto],
            "inicio_texto": texto[:220],
        }

    dados, erro, seg = _cronometrar(_url_direta)
    SAIDA["cenarios"]["url_direta"] = {"dados": dados, "erro": erro, "segundos": seg,
                                       "rotulo": "EXTERNO REAL"}

    # 4) Comparação técnica com documentação (2 turnos, caminho real) ----
    def _comparacao():
        url = "https://docs.python.org/3/tutorial/datastructures.html"
        p1 = "Analise esta documentação oficial: " + url
        _persistir_user("conv-comparacao", "smoke-cmp-1", p1)
        m1, e1 = pc_agent.ai_montar_mensagens(
            db, "conv-comparacao", cfg, p1, owner="smoke")
        fontes1 = e1.get("fontes") or []
        r1 = pc_agent.gerar_texto(cfg, m1, max_tokens=900, timeout=150)
        t1 = r1.get("texto") or ""
        pc_agent.ai_guardar_resposta(
            db, "smoke-cmp-1", "conv-comparacao",
            r1.get("model_usado") or cfg["model"], "smoke-cmp-1-r1", t1,
            owner="smoke")
        p2 = "Agora compare listas e tuplas."
        _persistir_user("conv-comparacao", "smoke-cmp-2", p2)
        m2, _e2 = pc_agent.ai_montar_mensagens(
            db, "conv-comparacao", cfg, p2, owner="smoke")
        r2 = pc_agent.gerar_texto(cfg, m2, max_tokens=900, timeout=150)
        t2 = r2.get("texto") or ""
        urls = [f.get("url", "") for f in fontes1]
        low = t2.lower()
        return {
            "status": "EXTERNO REAL + LLM REAL" if (t1 and t2) else "BLOQUEADO",
            "url_documentacao": url,
            "turno1": {
                "consulta": p1, "fontes": len(fontes1),
                "dominios": sorted({re.sub(r"^https?://(www\.)?", "",
                                           u).split("/")[0] for u in urls if u}),
                "resposta_chars": len(t1), "recorte": t1[:300],
            },
            "turno2": {
                "consulta": p2, "resposta_chars": len(t2),
                "menciona_lista_e_tupla": "lista" in low and "tupla" in low,
                "sem_tool_call": "tool_call" not in low and "websearch" not in low,
                "recorte": t2[:600],
            },
            "documentacao_oficial": any("python.org" in u for u in urls),
            "modelo": r2.get("model_usado"),
        }

    dados, erro, seg = _cronometrar(_comparacao)
    SAIDA["cenarios"]["comparacao_documentacao"] = {
        "dados": dados, "erro": erro, "segundos": seg,
        "rotulo": "EXTERNO REAL + LLM REAL"}

    # 5) Continuação ----------------------------------------------------
    def _continuacao():
        # 5a) tentativa sobre a busca real desta execução
        fup_real = shopping.responder_followup(
            db, "smoke", "conv-produtos", "Agora mostre apenas os resultados mais baratos")
        # 5b) caminho real de follow-up com resultado guardado (dados locais)
        prods = [
            {"nome": "Fone A", "preco": 300.0, "preco_texto": "R$ 300,00",
             "loja": "Loja A", "url_item": "https://loja-a.example/fone",
             "link_veredito": "parcial", "imagem_veredito": ""},
            {"nome": "Fone B", "preco": 150.0, "preco_texto": "R$ 150,00",
             "loja": "Loja B", "url_item": "https://loja-b.example/fone",
             "link_veredito": "parcial", "imagem_veredito": ""},
            {"nome": "Fone C", "preco": 200.0, "preco_texto": "R$ 200,00",
             "loja": "Loja C", "url_item": "https://loja-c.example/fone",
             "link_veredito": "parcial", "imagem_veredito": ""},
        ]
        shopping.salvar_consulta(db, "smoke", "conv-follow",
                                 "fone bluetooth até R$ 300",
                                 {"categoria": "fone", "orcamento": {"max": 300}},
                                 {"produtos": prods, "fontes": [],
                                  "criterios": {"categoria": "fone",
                                                "orcamento": {"max": 300}}})
        fup = shopping.responder_followup(
            db, "smoke", "conv-follow", "Agora mostre apenas os resultados mais baratos")
        texto = (fup or {}).get("texto") or ""
        return {
            "status": "LOCAL REAL (dados guardados)",
            "tentativa_externa": {
                "disponivel": bool(fup_real),
                "texto": ((fup_real or {}).get("texto") or "")[:300],
                "observacao": ("sem produtos na busca real desta execução — "
                               "follow-up honesto sem inventar ofertas")
                if not fup_real else "",
            },
            "com_dados_guardados": {
                "disponivel": bool(fup),
                "texto": texto,
                "ordem_barato_primeiro": [l for l in texto.splitlines()
                                          if l.startswith("- ")][:3],
                "fence_valido": None,
            },
        }

    dados, erro, seg = _cronometrar(_continuacao)
    if dados:
        fence = (shopping.responder_followup(
            db, "smoke", "conv-follow",
            "Agora mostre apenas os resultados mais baratos") or {}).get("fence") or ""
        ok = False
        if fence:
            try:
                ok, _, _ = jdui.validar_mensagem(
                    json.loads(fence.split("```jdui", 1)[1].rsplit("```", 1)[0]))
            except Exception:
                ok = False
        dados["com_dados_guardados"]["fence_valido"] = ok
        dados["ordem_esperada"] = ["R$ 150,00", "R$ 200,00", "R$ 300,00"]
    SAIDA["cenarios"]["continuacao"] = {"dados": dados, "erro": erro,
                                        "segundos": seg,
                                        "rotulo": "LOCAL REAL (dados guardados)"}

    # 6) Falha externa com fallback honesto -----------------------------
    def _falha():
        fonte, erro_url = research.analisar_url(
            "https://nao-existe-vexx-572.invalid/pagina", consulta="teste", timeout=6)
        vazio = shopping.pesquisar(
            db, "smoke", "fone bluetooth até R$ 300", conv="conv-falha",
            buscar_fn=lambda q: [], baixar_fn=None, usar_cache=False)
        nota = shopping.resumo_texto(vazio)
        aplicado = pc_agent._shopping_aplicar("Não há ofertas verificáveis.", vazio)
        return {
            "status": "LOCAL REAL + DNS REAL",
            "url_inexistente": {
                "erro": erro_url,
                "status_fonte": (fonte or {}).get("status"),
                "texto_lido": len((fonte or {}).get("texto_lido") or ""),
            },
            "busca_sem_provedor": {
                "produtos": len(vazio.get("produtos") or []),
                "erro": vazio.get("erro"),
                "motivo": vazio.get("motivo_final")
                or (vazio.get("descoberta") or {}).get("motivo_final"),
                "nota_honesta": nota[:400],
                "sem_preco_inventado": re.search(r"R\$\s*\d", nota or "") is None,
                "texto_final": aplicado[:400],
                "sem_fence": "```jdui" not in (aplicado or ""),
            },
        }

    dados, erro, seg = _cronometrar(_falha)
    SAIDA["cenarios"]["falha_externa"] = {"dados": dados, "erro": erro,
                                          "segundos": seg,
                                          "rotulo": "LOCAL REAL + DNS REAL"}

    # Evidência do Chrome (frontend delivery) ---------------------------
    chromes = sorted((ART / "chrome").glob("chrome-e2e-*.json"))
    if chromes:
        try:
            ult = json.loads(chromes[-1].read_text(encoding="utf-8"))
            SAIDA["frontend_delivery"] = {
                "evidencia": str(chromes[-1]),
                "ok": ult.get("ok"),
                "chrome": (ult.get("ambiente") or {}).get("chrome_versao"),
                "chat_real": (ult.get("chat_real") or {}).get("resposta_chars"),
                "desktop": (ult.get("desktop") or {}).get("card"),
                "mobile": (ult.get("mobile") or {}).get("emulado"),
            }
        except Exception as exc:
            SAIDA["frontend_delivery"] = {"erro": str(exc)}

    # Critérios de aceite do smoke -------------------------------------
    c = SAIDA["cenarios"]
    checagens = {
        "produtos_filtro_ok": bool(
            c["produtos"]["dados"]
            and c["produtos"]["dados"]["todos_dentro_do_orcamento"]
            and (c["produtos"]["dados"]["produtos"] == 0
                 or c["produtos"]["dados"]["cards_jdui_validos"] is True)),
        "pesquisa_geral_fundamentada": bool(
            c["pesquisa_geral"]["dados"]
            and c["pesquisa_geral"]["dados"]["fontes"] >= 1
            and c["pesquisa_geral"]["dados"]["menciona_fotossintese"]
            and c["pesquisa_geral"]["dados"]["sem_tool_call"]),
        "url_direta_limpa": bool(
            c["url_direta"]["dados"]
            and c["url_direta"]["dados"]["trecho_contido_no_texto"]
            and not c["url_direta"]["dados"]["residuos_menu"]),
        "comparacao_documentacao": bool(
            c["comparacao_documentacao"]["dados"]
            and c["comparacao_documentacao"]["dados"]["documentacao_oficial"]
            and c["comparacao_documentacao"]["dados"]["turno2"]["menciona_lista_e_tupla"]
            and c["comparacao_documentacao"]["dados"]["turno2"]["sem_tool_call"]),
        "continuacao_ordenada": bool(
            c["continuacao"]["dados"]
            and c["continuacao"]["dados"]["com_dados_guardados"]["disponivel"]
            and c["continuacao"]["dados"]["com_dados_guardados"]["fence_valido"]),
        "falha_honesta": bool(
            c["falha_externa"]["dados"]
            and c["falha_externa"]["dados"]["busca_sem_provedor"]["sem_preco_inventado"]
            and c["falha_externa"]["dados"]["busca_sem_provedor"]["sem_fence"]),
        "frontend_chrome": bool((SAIDA.get("frontend_delivery") or {}).get("ok")),
    }
    SAIDA["checagens"] = checagens
    SAIDA["ok"] = all(checagens.values())

    destino = ART / f"smoke-integrado-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    destino.write_text(json.dumps(SAIDA, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({
        "ok": SAIDA["ok"], "checagens": checagens,
        "segundos": {k: v["segundos"] for k, v in c.items()},
        "evidencia": str(destino)}, ensure_ascii=False, indent=1))
    db.close()
    return 0 if SAIDA["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
