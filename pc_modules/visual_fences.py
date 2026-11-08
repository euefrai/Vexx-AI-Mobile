"""Módulo do PC Agent: Fences visuais JDUI (evidências, fontes, gráficos, grafos), dados atuais ao vivo e modelos 3D."""
import conversation_followups
import evidence_graph as evgraph
import intent
import jdui
import json
import live_data
import model3d
import model3d_research
import re
import research
import research_agents

from datetime import datetime, timezone

from pc_modules.research_commands import _JOB_START_RE, _ultimo_job
from pc_modules.memory_store import _resposta_temporal_direta
from pc_modules.context_providers import anexar_fontes
from pc_modules.db_core import dono_valido
from pc_modules.intents_jdui import ultimos_blocos_jdui

def fence_de_evidencias(db, owner: str, conv: str) -> str:
    """Cards das fontes da última pesquisa (links reais, sem números inventados)."""
    job = _ultimo_job(db, owner, (), conv=conv)
    if job is None:
        return ""
    evs = research_agents.listar_evidencias(db, owner, job["id"])[:8]
    if not evs:
        return ""
    itens = [{"title": e["titulo"][:80] or e["dominio"], "desc": (e["trecho"] or "")[:200],
              "badge": e["status"], "url": e["url"]} for e in evs if e["url"].startswith("http")]
    if not itens:
        return ""
    fence = {"version": jdui.VERSION, "blocks": [
        {"type": "text", "content": f"Evidências da pesquisa sobre **{job['objetivo']}**:"},
        {"type": "ui", "component": "cards", "props": {"title": "Fontes", "items": itens}}]}
    ok, norm, _ = jdui.validar_mensagem(fence)
    if not ok:
        return ""
    return "\n\n```jdui\n" + json.dumps(norm, ensure_ascii=False) + "\n```"


def fence_de_fontes(db, owner: str, conv=None) -> str:
    """Componente `sources` da última pesquisa (status honestos, links reais)."""
    job = _ultimo_job(db, owner, (), conv=conv)
    if job is None:
        return ""
    evs = research_agents.listar_evidencias(db, owner, job["id"])[:10]
    if not evs:
        return ""
    itens = []
    for e in evs:
        url = e.get("url", "")
        if not url.startswith("http"):
            continue
        trecho = (e.get("trecho", "") or "")
        import research_view
        itens.append(research_view.source_card(e,bool(e.get('afirmacao'))))
    if not itens:
        return ""
    fence = {"version": jdui.VERSION, "blocks": [
        {"type": "ui", "component": "sources",
         "props": {"title": f"Fontes sobre {(job.get('objetivo') or '')[:80]}",
                   "items": itens}}]}
    ok, norm, _ = jdui.validar_mensagem(fence)
    if not ok:
        return ""
    return "\n\n```jdui\n" + json.dumps(norm, ensure_ascii=False) + "\n```"


def _num_celula(s: str):
    """Número em célula PT-BR/US ('R$ 1.234,56', '12%', '1,234.5') ou None."""
    t = re.sub(r"[R$\s%]", "", str(s or "").strip())
    if not t or not re.fullmatch(r"[+-]?[\d.,]+", t):
        return None
    try:
        if "." in t and "," in t:
            # O último separador é o decimal (1.234,56 | 1,234.5).
            if t.rfind(".") > t.rfind(","):
                return float(t.replace(",", ""))
            return float(t.replace(".", "").replace(",", "."))
        if "," in t:
            return float(t.replace(",", "."))
        if re.fullmatch(r"\d+\.\d{1,2}", t):
            return float(t)
        return float(t.replace(".", "").replace(",", ""))
    except ValueError:
        return None


def fence_tabela_para_grafico(db, owner: str, conv: str) -> str:
    """'Transforme em gráfico': última tabela da conversa com coluna numérica
    vira chart. Sem números → texto honesto (nunca inventa valores)."""
    blocos = ultimos_blocos_jdui(db, conv, limite=3, owner=owner)
    tabela = None
    for b in blocos:
        for blk in b.get("blocks", []):
            if blk.get("component") == "table":
                tabela = blk.get("props", {})
                break
        if tabela:
            break
    if not tabela or not tabela.get("columns") or not tabela.get("rows"):
        return ("\n\nNão encontrei tabela anterior com dados nesta conversa para "
                "transformar em gráfico. 📊")
    cols, linhas = tabela["columns"], tabela["rows"]
    numericas = []
    for i in range(1, len(cols)):
        vals = [_num_celula(r[i] if i < len(r) else "") for r in linhas]
        if sum(1 for v in vals if v is not None) >= 2:
            numericas.append((i, vals))
    if not numericas:
        return ("\n\nA última tabela não tem coluna numérica com pelo menos 2 "
                "valores — e eu não vou inventar números. 📊")
    rotulos = [(r[0] if r else "")[:24] or f"Linha {k + 1}"
               for k, r in enumerate(linhas)][:24]
    series = []
    for i, vals in numericas[:3]:
        series.append({"label": cols[i][:60],
                       "values": [(v if v is not None else 0.0) for v in vals[:24]]})
    fence = {"version": jdui.VERSION, "blocks": [
        {"type": "ui", "component": "chart",
         "props": {"type": "bar", "title": (tabela.get("title") or "Gráfico")[:160],
                   "labels": rotulos, "series": series,
                   "source": "tabela anterior da conversa"}}]}
    ok, norm, _ = jdui.validar_mensagem(fence)
    if not ok:
        return ""
    return "\n\n```jdui\n" + json.dumps(norm, ensure_ascii=False) + "\n```"


def fence_de_grafo(db, owner: str) -> str:
    """Grafo claim→evidência→fonte da última pesquisa (nós reais, sem invenção)."""
    job = _ultimo_job(db, owner, ("concluida",))
    if job is None:
        return ""
    estados = {}
    try:
        for a in research_agents.carregar_job(db, owner, job["id"]).get("achados", []):
            estados[(a.get("afirmacao") or "")[:200]] = a.get("estado", "")
    except research_agents.AgentErro:
        pass
    nodes = []
    idmap = {}
    for c in evgraph.nos_do_job(db, owner, job["id"], "claim")[:8]:
        nid = "c" + c["id"][:12]
        idmap[c["id"]] = nid
        nodes.append({"id": nid, "label": (c.get("texto") or "")[:60],
                      "kind": "claim", "estado": estados.get((c.get("texto") or "")[:200], ""),
                      "detalhe": ""})
    evs = {e["id"]: e for e in research_agents.listar_evidencias(db, owner, job["id"])}
    for c in evgraph.nos_do_job(db, owner, job["id"], "evidence")[:12]:
        nid = "e" + c["id"][:12]
        idmap[c["id"]] = nid
        ev = evs.get(c.get("evidence_id", ""), {})
        nodes.append({"id": nid, "label": (c.get("titulo") or "")[:60],
                      "kind": "evidence", "estado": ev.get("status", ""),
                      "detalhe": (ev.get("trecho", "") or "")[:200]})
    for s in evgraph.nos_do_job(db, owner, job["id"], "source")[:10]:
        nid = "s" + s["id"][:12]
        idmap[s["id"]] = nid
        nodes.append({"id": nid, "label": (s.get("dominio") or s.get("url", ""))[:60],
                      "kind": "source", "estado": "",
                      "detalhe": (s.get("url", "") or "")[:200]})
    if not nodes:
        return ""
    edges = [{"from": idmap[e["src"]], "to": idmap[e["dst"]], "label": e["tipo"]}
             for e in evgraph.arestas_do_job(db, owner, job["id"])
             if e["src"] in idmap and e["dst"] in idmap][:60]
    fence = {"version": jdui.VERSION, "blocks": [
        {"type": "text", "content": "Mapa das evidências (toque nos nós)."},
        {"type": "ui", "component": "evidencegraph",
         "props": {"title": "Grafo de evidências", "nodes": nodes, "edges": edges}}]}
    ok, norm, _ = jdui.validar_mensagem(fence)
    if not ok:
        return ""
    return "\n\n```jdui\n" + json.dumps(norm, ensure_ascii=False) + "\n```"


TRANSFORM_VERBOS = ("transforma", "transforme", "converter em", "converta em",
                    "mostre em", "mostra em", "em forma de", "visualize")
TRANSFORM_FORMATOS = (("gráfico", "grafico"), ("tabela",), ("dashboard", "painel"),
                      ("cards", "cartões", "cartoes"))


def intencao_transformar_pesquisa(texto: str) -> str:
    """'transforma esses dados em gráfico' → formato, ou ''."""
    t = (texto or "").lower()
    if not any(v in t for v in TRANSFORM_VERBOS):
        return ""
    for grupo in TRANSFORM_FORMATOS:
        if any(k in t for k in grupo):
            return grupo[0]
    return ""


def fence_de_pesquisa(db, owner: str, conv: str, texto_usuario: str) -> str:
    """Transforma a ÚLTIMA pesquisa da conversa em interface (dados reais).

    Sem run/fontes: texto honesto (pesquise antes). Sem números para gráfico:
    texto honesto (não inventa valores).
    """
    run = research.ultima_run(db, owner, conv)
    if not run or not run.get("fontes"):
        return ("\n\nAinda não há pesquisa nesta conversa para transformar. "
                "Peça primeiro a pesquisa (ex.: 'pesquise sobre X') — aí eu monto o visual. 🔍")
    formato = intencao_transformar_pesquisa(texto_usuario)
    fontes = run["fontes"]
    dominios = sorted({f.get("dominio", "") for f in fontes if f.get("dominio")})
    origem = "pesquisa: " + (", ".join(dominios[:3]) or "web")
    blocos = [{"type": "text", "content": "Visual montado com os dados pesquisados. 📊"}]
    if formato == "gráfico":
        fatos = research.extrair_fatos_numericos(fontes, 10)
        if len(fatos) < 2:
            return ("\n\nOs trechos pesquisados não trazem números suficientes para um gráfico "
                    "confiável — e eu não vou inventar valores. Quer uma tabela com as fontes? 📊")
        unidade = fatos[0]["unidade"]
        mesmos = [f for f in fatos if f["unidade"] == unidade][:10] or fatos[:10]
        blocos.append({"type": "ui", "component": "chart",
                       "props": {"type": "bar", "title": "Dados da pesquisa",
                                 "labels": [f["rotulo"][-24:] or "item" for f in mesmos],
                                 "series": [{"label": unidade or "valores",
                                             "values": [f["valor"] for f in mesmos]}],
                                 "source": origem}})
    elif formato == "tabela":
        linhas = [[f.get("titulo", "")[:60], (f.get("trecho", "") or "")[:120]] for f in fontes[:10]]
        blocos.append({"type": "ui", "component": "table",
                       "props": {"title": "Fontes pesquisadas",
                                 "columns": ["Fonte", "Resumo"], "rows": linhas}})
    elif formato == "dashboard":
        fatos = research.extrair_fatos_numericos(fontes, 10)
        dash = {"title": "Painel da pesquisa",
                "metrics": [{"label": "Fontes", "value": str(len(fontes)),
                             "hint": "; ".join(dominios[:3])},
                            {"label": "Divergências", "value": str(len(run.get("divergencias", []))),
                             "hint": "trechos em conflito"}],
                "chart": None, "source": origem}
        if len(fatos) >= 2:
            dash["chart"] = {"type": "bar", "title": "Números citados",
                             "labels": [f["rotulo"][-24:] or "item" for f in fatos[:8]],
                             "series": [{"label": fatos[0]["unidade"] or "valores",
                                         "values": [f["valor"] for f in fatos[:8]]}],
                             "source": origem}
        blocos.append({"type": "ui", "component": "dashboard", "props": dash})
    else:  # cards
        itens = [{"title": f.get("titulo", "")[:80], "desc": (f.get("trecho", "") or "")[:200],
                  "badge": f.get("dominio", "")[:30],
                  "action": {"chat": f"Detalhe a fonte {f.get('id', '')} sobre {run.get('consulta', '')[:60]}"}}
                 for f in fontes[:8]]
        blocos.append({"type": "ui", "component": "cards",
                       "props": {"title": "Fontes pesquisadas", "items": itens}})
    fence = {"version": jdui.VERSION, "blocks": blocos}
    ok, norm, _ = jdui.validar_mensagem(fence)
    if not ok:
        return ""
    return "\n\n```jdui\n" + json.dumps(norm, ensure_ascii=False) + "\n```"


def fence_transformacao_visual(db, owner: str, conv: str, texto_usuario: str) -> str:
    """V5.2 Visual Response Engine: 'transforme/mostre X em Y' reusa dados
    anteriores sem nova pesquisa. Retorna fence/texto ou ''."""
    formato = intencao_transformar_pesquisa(texto_usuario)
    if formato == "gráfico":
        grafico = fence_tabela_para_grafico(db, owner, conv)
        if "```jdui" in grafico:
            return grafico
    if formato:
        return fence_de_pesquisa(db, owner, conv, texto_usuario)
    return ""


def cmd_dados_atuais(db, texto, owner, conv, contexto, message_id=None):
    """Dados externos reais e continuação de cidade isolada por proprietário/conversa."""
    if _JOB_START_RE.search(texto or ''):
        return None  # Explicit deep research must reach the existing job route.
    analysis=intent.analisar(texto)
    if analysis.get('intencao')=='model3d':return None
    if analysis.get('route')=='GREETING':
        return 'Oi! Tudo bem? Como posso ajudar?'
    slots=conversation_followups.weather_slots(db,dono_valido(owner),conv,texto,message_id)
    if slots:
        return live_data.respond(slots['resolved_request'],contexto)
    anterior = conversation_followups.last_answer(db, dono_valido(owner), conv)
    # Legacy rendered-answer fallback only for old chats without user history.
    has_history=db.execute("SELECT 1 FROM messages WHERE owner_id=? AND conversation_id=? AND role='user' LIMIT 1",(dono_valido(owner),conv)).fetchone()
    continuacao = conversation_followups.weather_request(texto, anterior) if not has_history else None
    if continuacao:
        return live_data.respond(continuacao, contexto)
    produto = conversation_followups.product_reply(db, dono_valido(owner), conv, texto, anterior)
    if produto:
        return produto
    req = live_data.request(texto)
    news_followup=conversation_followups.news_request(db,dono_valido(owner),conv,texto,message_id)
    if news_followup:
        texto=news_followup
        req=live_data.request(texto)
    if not req:
        return None
    if req['kind']=='news':
        result=research.pesquisa_rapida(db,dono_valido(owner),texto)
        sources=research.fontes_relevantes(texto,result.get('fontes') or [],result)
        summary=research.resumo_deterministico(sources,texto)
        return anexar_fontes(summary,sources)
    if req['kind']=='clock' and not live_data.place_from(texto):
        # Device timezone is useful; a stale/manipulated device clock is not.
        contexto=dict(contexto)
        if contexto.get('timezone'):
            from zoneinfo import ZoneInfo
            try:
                contexto['current_at']=datetime.now(timezone.utc).astimezone(ZoneInfo(contexto['timezone']))
            except (ValueError,KeyError):
                return 'Não consegui validar o fuso informado. Informe uma cidade ou fuso IANA válido.'
        else:
            contexto.pop('current_at',None)
        resposta = _resposta_temporal_direta(texto, contexto)
        if resposta:
            return live_data.card(resposta,'Horário atual',contexto['current_at'].strftime('%H:%M'),desc=contexto['current_at'].strftime('%d/%m/%Y')+' · '+contexto.get('timezone',''),badge='Relógio do sistema')
        # No place is inferred from UTC. The existing clock stays the source when available.
        if contexto.get('current_at'):
            instante=contexto['current_at']
            return f"Data local: {instante:%d/%m/%Y}; horário: {instante:%H:%M} ({contexto.get('timezone',instante.strftime('%z'))})."
        return 'Não recebi o relógio/fuso do aparelho. Informe uma cidade, por exemplo: “que horas são em Salvador, Bahia?”.'
    return live_data.respond(texto, contexto)


def cmd_model3d(db, texto, owner, conv, scene_state='', pesquisa_web=False):
    """Referências 3D restritas ao dono e à conversa; sem LLM/controle remoto.

    Rede só na geração aproximada opcional (`pesquisa_web`), fora do catálogo."""
    request = model3d.request(texto)
    if not request:
        return None
    previous = None
    if request['action'] != 'create':
        hint = {}
        if scene_state:
            try:
                if not isinstance(scene_state,str) or len(scene_state)>4000: raise ValueError()
                hint=json.loads(scene_state)
                if not isinstance(hint,dict) or set(hint)-{'messageId','scene','interaction','rotation','distance'} or not isinstance(hint.get('messageId'),str): raise ValueError()
            except (ValueError,TypeError):
                return 'Referência 3D inválida; abra novamente a cena desejada.'
        rows=db.execute("SELECT id,text FROM messages WHERE owner_id=? AND conversation_id=? AND role='assistant' AND origin='mobile' ORDER BY created_at DESC LIMIT 50",(dono_valido(owner),conv)).fetchall()
        for message_id, text in rows:
            if hint and message_id!=hint['messageId']: continue
            for raw in jdui.extrair_fences(text):
                try:
                    ok,message,_=jdui.validar_mensagem(json.loads(raw))
                    if ok: previous=next((b['props'] for b in message['blocks'] if b.get('component')=='model3d'),None)
                except ValueError: continue
                if previous: break
            if previous:
                if previous.get('education'):
                    try:
                        state=hint
                        if not state:
                            row=db.execute("SELECT state FROM ui_state WHERE owner_id=? AND message_id=? AND slot LIKE '%:model3d' ORDER BY updated_at DESC LIMIT 1",(dono_valido(owner),message_id)).fetchone()
                            state=json.loads(row[0]) if row else {}
                        if state.get('scene')==previous['id']:
                            previous['interaction']=model3d.validate_interaction(state.get('interaction',{}),[o['id'] for o in previous['objects']],len(previous['steps']))
                            if 'rotation' in state:
                                rotation=state['rotation']
                                if not isinstance(rotation,list) or len(rotation)!=3 or any(type(n) not in (int,float) for n in rotation): raise ValueError()
                                previous['rotation']=[(n*180/3.141592653589793)%360 for n in rotation]
                            if 'distance' in state: previous['camera']={'distance':state['distance']}
                            previous=model3d.validate(previous)
                        elif hint: raise ValueError()
                    except (ValueError,TypeError,AttributeError):
                        return 'Estado 3D inválido; restaure a cena antes de continuar.'
                break
        if hint and previous is None:
            return 'Cena 3D indisponível nesta conversa; nenhuma alteração foi aplicada.'
    if request['action'] == 'rebuild' and previous is None:
        # V5.4.1: sem cena persistida ("isso não está em 3D, reconstrua em 3D"),
        # recria a última cena 3D pedida pelo usuário em vez de deixar o LLM
        # responder com texto/arte ASCII. Sem pedido 3D anterior, limitação honesta.
        for (utext,) in db.execute(
                "SELECT text FROM messages WHERE owner_id=? AND conversation_id=? "
                "AND role='user' ORDER BY created_at DESC LIMIT 40",
                (dono_valido(owner), conv)).fetchall():
            anterior = model3d.request(utext or '')
            if anterior and anterior.get('action') == 'create' and (
                    anterior.get('education') or anterior.get('kinds') or anterior.get('model')
                    or anterior.get('device')):
                request, texto = anterior, utext
                break
        if request['action'] != 'create':
            return ('Ainda não há uma cena 3D nesta conversa para reconstruir. '
                    'Peça, por exemplo: "mostre um computador em 3D" ou "crie um cubo em 3D".')
    result = model3d.respond(texto, previous)
    if not result:
        return None
    text, props = result
    if props is None and pesquisa_web and request.get('action') == 'create' and request.get('topic'):
        # V5.6: assunto fora do catálogo → aproximação rotulada vinda de fontes públicas.
        try:
            aproximado = model3d_research.gerar(request['topic'])
        except Exception:
            aproximado = None
        if aproximado:
            if aproximado.get('precision') == 'aproximado':
                text = ('Preparei um modelo aproximado a partir de referências públicas; as proporções vêm '
                        'de medidas citadas nas fontes e podem conter imprecisões. Não é CAD nem modelo '
                        'oficial. Abra o 3D para explorar as partes.')
            else:
                text = ('Preparei um modelo conceitual: as fontes consultadas não confirmaram medidas, então '
                        'a forma é genérica e educativa. Não é CAD nem modelo oficial. Abra o 3D para '
                        'explorar as partes.')
            props = aproximado
    if props:
        ok, normalized, errors = jdui.validar_mensagem({'version': jdui.VERSION,
            'blocks': [{'type': 'ui', 'component': 'model3d', 'props': props}]})
        if not ok:
            return 'Não foi possível preparar uma visualização 3D válida.'
        text += '\n\n```jdui\n' + json.dumps(normalized, ensure_ascii=False) + '\n```'
    return text
