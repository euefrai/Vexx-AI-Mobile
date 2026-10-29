"""Build a validated JDUI 4.0 view from real research records (V5.8).

The model never supplies HTML/JS.  This module maps persisted job data to the
allowlisted components and validates every block with :mod:`jdui`; a component
with invalid data is omitted and the textual summary explains the omission.
"""
from __future__ import annotations

import re

import jdui

MAX_TEXT = 4000
_STEP = {"feita": "done", "pendente": "todo", "falhou": "error",
         "removida": "skipped", "em_andamento": "doing", "pausada": "todo"}
_JOB = {"criada": "planned", "em_andamento": "running", "pausada": "paused",
        "concluida": "completed", "interrompida": "paused",
        "cancelada": "cancelled", "falhou": "failed"}
_STATE = {"SUPPORTED", "CONTRADICTED", "PARTIALLY_SUPPORTED",
          "UNVERIFIED", "INCONCLUSIVE"}


def _text(value, limit=2000) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _block_ok(component: str, props: dict) -> bool:
    ok, _, _ = jdui.validar_mensagem({
        "version": jdui.VERSION,
        "blocks": [{"type": "ui", "component": component, "props": props}],
    })
    return ok


def _plan(resumo: dict) -> dict:
    steps = []
    for step in (resumo.get("etapas") or [])[:24]:
        if not isinstance(step, dict) or not step.get("id"):
            continue
        tipo = _text(step.get("tipo"), 30) or "pesquisa"
        alvo = _text(step.get("alvo"), 160)
        rotulo = {"busca": "Buscar", "ler": "Ler", "analisar": "Analisar",
                  "verificar": "Verificar", "sintetizar": "Sintetizar",
                  "auditar": "Auditar"}.get(tipo, tipo.title())
        title = f"{rotulo}: {alvo}" if alvo else rotulo
        steps.append({
            "id": _text(step.get("id"), 40),
            "title": title[:160],
            "kind": tipo,
            "status": _STEP.get(step.get("status") or "pendente", "todo"),
            "detail": _text(step.get("objetivo_etapa")
                            or step.get("priority_reason"), 500),
            "stop_condition": _text(step.get("regra_parada")
                                    or step.get("criterio_conclusao"), 300),
            "dependencies": step.get("dependencias") or [],
        })
    return {
        "title": "Plano de pesquisa",
        "objective": _text(resumo.get("objetivo"), 500),
        "mode": _text(resumo.get("modo"), 40),
        "status": _JOB.get(resumo.get("status") or "criada", "planned"),
        "steps": steps,
        "budgets": resumo.get("orcamento") or {},
        "used": {key: (resumo.get("usados") or {}).get(key)
                 for key in ("buscas", "paginas", "replans")},
    }


def _claims(resumo: dict) -> dict:
    claims = []
    for item in (resumo.get("achados") or [])[:10]:
        if not isinstance(item, dict):
            continue
        state = _text(item.get("estado"), 40).upper()
        if state == "INSUFFICIENT_EVIDENCE":
            state = "INCONCLUSIVE"
        if state not in _STATE:
            state = "UNVERIFIED"
        sources = []
        for fonte in (item.get("fontes") or [])[:12]:
            if not isinstance(fonte, dict):
                continue
            sources.append({
                "id": _text(fonte.get("evidence_id"), 80),
                "title": _text(fonte.get("title") or fonte.get("domain"), 160),
                "url": _text(fonte.get("url"), 500),
                "domain": _text(fonte.get("domain"), 120),
                "relation": _text(fonte.get("relation"), 40).upper()
                            or "REQUIRES_VERIFICATION",
                "read": bool(fonte.get("read")),
                "access_state": _text(fonte.get("access_state"), 40),
                "excerpt": _text(fonte.get("used_excerpt"), 500),
                "published_at": _text(fonte.get("published_at"), 48),
            })
        has_support = any(s["relation"] in ("SUPPORTS", "PARTIALLY_SUPPORTS")
                          for s in sources)
        if state == "SUPPORTED" and not has_support:
            state = "INCONCLUSIVE" if sources else "UNVERIFIED"
        if state == "CONTRADICTED" and not any(
                s["relation"] == "CONTRADICTS" for s in sources):
            state = "INCONCLUSIVE" if sources else "UNVERIFIED"
        claims.append({
            "statement": _text(item.get("afirmacao"), 1200),
            "state": state,
            "method": _text(item.get("metodo"), 200),
            "coverage": item.get("cobertura_lexica", 0),
            "sources": sources,
        })
    return {"title": "Evidências por afirmação", "claims": claims}


def _hypotheses(resumo: dict) -> dict:
    items = []
    for hypothesis in (resumo.get("hipoteses") or [])[:8]:
        if not isinstance(hypothesis, dict) or not hypothesis.get("statement"):
            continue
        linhas = []
        for link in hypothesis.get("cadeia") or []:
            if isinstance(link, dict):
                linhas.append(f"**{_text(link.get('rotulo'), 40)}:** "
                              f"{_text(link.get('texto'), 700)}")
        linhas.append("**Testes executados:** não; hipótese e próximos passos "
                      "são propostas, não resultados.")
        items.append({"title": _text(hypothesis.get("statement"), 120),
                      "markdown": "\n\n".join(linhas)[:2800]})
    return {"items": items}


def _media(resumo: dict) -> dict:
    items = []
    for item in (resumo.get("midia") or [])[:12]:
        if not isinstance(item, dict) or not item.get("url"):
            continue
        items.append({
            "type": item.get("type"),
            "title": item.get("title"), "url": item.get("url"),
            "thumb": item.get("thumb") or "",
            "source_title": item.get("source_title") or "",
            "source_url": item.get("source_url") or "",
            "publisher": item.get("publisher") or "",
            "date": item.get("date") or "",
            "rights": item.get("rights") or "não informado",
            **{key:item.get(key) for key in ('attribution','license_url','mime','width','height','duration','metadata_state')},
            "access_state": item.get("access_state") or "link_only",
            "validation_state": item.get("validation_state") or "unverified",
            "analysis_state": item.get("analysis_state") or "not_analyzed",
            "excerpt": item.get("excerpt") or "",
            "alt": item.get("title") or "",
        })
    return {"title": "Mídia descoberta (não é evidência)", "items": items}


def _files(resumo: dict) -> dict:
    ident = _text(resumo.get("id"), 64)
    if not re.fullmatch(r"[A-Za-z0-9_-]{2,64}", ident):
        return {"files": []}
    base = f"/api/research/export?job_id={ident}&formato="
    return {"title": "Exportar pesquisa", "files": [
        {"name": "Relatório completo (Markdown)", "url": base + "md",
         "kind": "md", "size": "limite 2 MB", "source": "gerado no servidor",
         "status": "available"},
        {"name": "Dados estruturados (CSV)", "url": base + "csv",
         "kind": "csv", "size": "limite 2 MB", "source": "gerado no servidor",
         "status": "available"},
        {"name": "Registros completos (JSON)", "url": base + "json",
         "kind": "json", "size": "limite 2 MB", "source": "gerado no servidor",
         "status": "available"},
    ]}


def source_card(item: dict, used=False) -> dict:
    import research_agents
    from web_extract import melhor_trecho
    read=research_agents._evidencia_lida(item)
    abstract=item.get('content_scope')=='abstract_only'
    full=bool(item.get('full_text_fetched'))
    vertical=item.get('vertical') or {}
    data=vertical.get('data') or {}
    details=['Disponibilidade atual não confirmada'] if vertical.get('kind') in ('air_travel','bus_travel') else []
    aspects = (item.get('answerability') or {}).get('aspects') or []
    if aspects:
        details.append('Aspectos com passagem: '+', '.join(str(a) for a in aspects[:6]))
    partials = (item.get('answerability') or {}).get('partial_aspects') or []
    if partials:
        details.append('Suporte parcial: '+', '.join(str(a) for a in partials[:6]))
    sections=list(dict.fromkeys(_text(p.get('section') or p.get('context_heading'),100)
                               for p in (item.get('answer_passages') or [])[:8]
                               if isinstance(p, dict) and (p.get('section') or p.get('context_heading'))))
    if read and sections:
        details.append('Contexto da seção: '+' · '.join(sections[:2]))
    # Show the passage selected to answer the question, not the page's lead.
    # Discovery snippets remain discovery snippets when the page was not read.
    passages = item.get('answer_passages') or []
    excerpt = next((p.get('text') for p in passages[:8]
                    if isinstance(p, dict) and p.get('text')), '') if read else ''
    excerpt = excerpt or item.get('trecho') or ''
    labels={'location':'Local','organizer':'Organizador','provider':'Operadora','airline':'Companhia',
            'departureAirport':'Origem','departureBusStop':'Origem','arrivalAirport':'Destino','arrivalBusStop':'Destino',
            'departureTime':'Partida declarada','arrivalTime':'Chegada declarada'}
    for key,label in labels.items():
        if data.get(key): details.append(label+': '+str(data[key])[:160])
    if data.get('price') and vertical.get('verification')=='MATCHED_DECLARED_FARE':
        details.insert(1, 'Tarifa declarada: '+data['price']+' '+data.get('currency','')+'; disponibilidade não verificada')
    images=item.get('imagens') or []
    image=next((v.get('url') or v.get('src') for v in images if isinstance(v,dict) and (v.get('url') or v.get('src'))),'')
    return {'titulo':item.get('titulo') or item.get('title'),'url':item.get('url'),
            'dominio':item.get('dominio'),'data':item.get('publicado_em') or str(item.get('year') or ''),
            'origem_declarada':item.get('origem_declarada') or '',
            'data_evento':data.get('event_date') or '', 'trecho':melhor_trecho(str(excerpt), '', 300),
            'tipo':item.get('publication_type') or {'news':'Notícia','events':'Evento declarado','air_travel':'Voo · informações encontradas','bus_travel':'Ônibus · informações encontradas'}.get(vertical.get('kind'),item.get('tipo','Fonte')),
            'escopo':'Página não lida; sem suporte factual' if not read else ('Texto de HTML aberto recuperado; extração limitada' if item.get('full_text_format')=='html' else 'Texto de PDF aberto recuperado; extração limitada') if full else 'Somente resumo; texto completo não lido' if abstract else 'Texto recuperado',
            'relacao':'Trecho ligado a uma afirmação' if used and read else 'Fonte de contexto',
            'status':'utilizada' if used and read else 'aberta' if read else 'encontrada',
            'leitura':('PARTIAL' if abstract or full else 'READ') if read else 'UNAVAILABLE' if item.get('access_state')=='blocked' else 'FOUND',
            'publicador':item.get('publicador') or item.get('journal') or item.get('repository') or '',
            'autores':', '.join(str(v) for v in (item.get('authors') or [])[:6]),'doi':item.get('doi') or '',
            'imagem':image if vertical.get('kind')=='news' else '', 'favicon':item.get('favicon') or '',
            'texto_url':item.get('full_text_url') if full else '', 'detalhes':details[:6]}


def media_fence(items: list) -> str:
    """Deterministic media from retrieval, independent of model prose."""
    import json
    props = _media({'midia':items})
    if not props['items']: return ''
    message={'version':jdui.VERSION,'blocks':[{'type':'ui','component':'media','props':props}]}
    ok,normalized,_=jdui.validar_mensagem(message)
    return '\n\n```jdui\n'+json.dumps(normalized,ensure_ascii=False)+'\n```' if ok else ''


def contextual_fence(sources: list) -> str:
    import json
    selected=[s for s in sources if s.get('relevante') is not False and (s.get('metadata_source')=='academic_provider' or s.get('status') in ('aberta','encontrada') or (s.get('vertical') or {}).get('kind') in ('news','events','air_travel','bus_travel'))]
    if not selected: return ''
    message={'version':jdui.VERSION,'blocks':[{'type':'ui','component':'sources','props':{'title':'Fontes e dados recuperados','items':[source_card(s) for s in selected[:6]]}}]}
    ok,normalized,_=jdui.validar_mensagem(message)
    return '\n\n```jdui\n'+json.dumps(normalized,ensure_ascii=False)+'\n```' if ok else ''


def strip_model_research_cards(text: str) -> str:
    """Retrieval owns media/source cards; model URLs are not recovered records."""
    import json
    def replace(match):
        try:
            message=json.loads(match[1])
            blocks=message.get('blocks')
            if not isinstance(blocks,list):return match[0]
            kept=[b for b in blocks if not isinstance(b,dict) or b.get('component') not in ('media','sources')]
            if len(kept)==len(blocks):return match[0]
            if not kept:return ''
            return '```jdui\n'+json.dumps({**message,'blocks':kept},ensure_ascii=False)+'\n```'
        except (ValueError,TypeError,AttributeError):return match[0]
    return re.sub(r'```jdui\s*\n([\s\S]*?)```',replace,text,flags=re.I)


def build_view(resumo: dict, evidencias: list = None, hypotheses: list = None) -> dict:
    """Return ``JULIA-ui-message/v1`` with only validated, real data."""
    resumo = resumo if isinstance(resumo, dict) else {}
    blocks, omitted = [], []
    candidatos = [
        ("researchplan", _plan(resumo)),
        ("evidence", _claims(resumo)),
        ("accordion", _hypotheses(resumo)),
        ("media", _media(resumo)),
        ("filecard", _files(resumo)),
    ]
    used = {eid for claim in resumo.get("achados", []) for eid in
            claim.get("supporting_ids", []) + claim.get("contradicting_ids", [])}
    import research_agents
    synthesis=resumo.get('sintese') or {}
    if synthesis.get('llm'):
        cited={eid for finding in synthesis.get('findings',[]) for eid in finding.get('evidence_ids',[])}
        provenance={p.get('evidence_id') for p in synthesis.get('provenance',[])}
        read={e.get('id') for e in (evidencias or []) if research_agents._evidencia_lida(e)}
        used.update(cited & provenance & read)
    source_items = []
    # Keep cited sources visible even when they were discovered after the first
    # ten records. Stable ordering within each group preserves discovery order.
    ordered = sorted((evidencias or []), key=lambda item: (
        not (item.get('id') in used and research_agents._evidencia_lida(item)),
        not research_agents._evidencia_lida(item)))
    for item in ordered[:10]:
        source_items.append(source_card(item,item.get('id') in used))
    if source_items:
        candidatos.append(("sources", {"title": "Fontes e estado da leitura", "items": source_items}))
    gaps = (resumo.get('usados') or {}).get('research_gaps') or []
    coverage = (resumo.get('usados') or {}).get('answer_coverage') or {}
    if coverage.get('applicable'):
        labels = {'SUPPORTED':'Trecho pertinente recuperado', 'PARTIALLY_SUPPORTED':'Parcial',
                  'CONTRADICTED':'Fontes divergem; verificar', 'DISCOVERED':'Ainda não confirmado',
                  'NOT_SEARCHED':'Ainda não confirmado', 'UNAVAILABLE':'Indisponível'}
        rows = [[_text(' · '.join(filter(None, [r.get('entity'), r.get('description')])),180),
                 'Identidade da fonte verificada' if r.get('attribute')=='source_authority' and r.get('state')=='SUPPORTED'
                 else labels.get(r.get('state'),'Ainda não confirmado')]
                for r in coverage.get('requirements',[])[:8]]
        if ((resumo.get('usados',{}).get('research_outcome') or {}).get('source_authority_unverified')
                and not any(r.get('attribute') == 'source_authority' for r in coverage.get('requirements',[]))):
            rows.append(['Fonte oficial ou primária','Autoridade ainda não verificada'])
        if rows:
            candidatos.append(('table',{'title':'Aspectos da pergunta','columns':['Aspecto','Evidência recuperada'],
                                        'rows':rows,'read_only':True}))
    open_gaps = [g for g in gaps[:6] if g.get('status') == 'OPEN']
    if open_gaps and not coverage.get('applicable'):
        candidatos.append(('accordion', {'items': [{
            'title': 'O que ainda falta confirmar (' + str(len(open_gaps)) + ')',
            'markdown': '\n\n'.join('- ' + _text(g.get('description'), 120)
                + ': ' + str(int(g.get('observed_publications') or 0)) + '/'
                + str(int(g.get('required_publications') or 1)) + ' publicação(ões) com o dado extraído.'
                for g in open_gaps)
                + '\n\nAusente no trecho recuperado não significa ausente no estudo inteiro.'}]}))
    papers=[item for item in (evidencias or []) if item.get('doi') and item.get('full_text_fetched')]
    if len(papers)>=2 and any(p.get('scientific_sections') for p in papers):
        rows=[]
        for paper in papers[:6]:
            sections=paper.get('scientific_sections') or []
            row=[_text(paper.get('titulo') or paper.get('title'),160)]
            for kind in ('methods','results','limitations'):
                section=next((s for s in sections if s.get('kind')==kind),{})
                row.append(_text(section.get('text'),180) or 'Não recuperado')
            rows.append(row)
        candidatos.append(('table',{'title':'Estudos: trechos extraídos, condições não normalizadas',
            'columns':['Estudo','Métodos','Resultados','Limitações'],'rows':rows}))
    elif len(papers)>=2:
        candidatos.append(('table',{'title':'Publicações recuperadas — sem comparação experimental aprovada',
            'columns':['Publicação','Ano','Escopo','DOI'], 'rows':[
                [_text(p.get('titulo') or p.get('title'),150),str(p.get('year') or ''),
                 'Extração limitada; texto integral não confirmado',_text(p.get('doi'),160)] for p in papers[:6]]}))
    # Promote actual result content before diagnostic/export controls. Different
    # intents use their existing components, without inventing empty cards.
    media_intent=bool(re.search(r'\b(imagens?|fotos?|v[ií]deos?)\b',resumo.get('objetivo',''),re.I))
    if source_items and not media_intent:
        # Keep all discovery metadata in the job/export, but do not turn a
        # paper's navigation/references into a second gallery of unread files.
        candidatos=[entry for entry in candidatos if entry[0]!='media']
    priority=['media','sources','evidence'] if media_intent else ['evidence','table','sources','media']
    if media_intent or source_items:
        candidatos.sort(key=lambda entry: priority.index(entry[0]) if entry[0] in priority else 10)
    for component, props in candidatos:
        if component == "evidence" and not props.get("claims"):
            continue
        if component == "accordion" and not props.get("items"):
            continue
        if component in ("media", "filecard") and not props.get("items") and not props.get("files"):
            continue
        if _block_ok(component, props):
            blocks.append({"type": "ui", "component": component, "props": props})
        else:
            omitted.append(component)
    resumo_midia = resumo.get("midia_resumo") or {}
    status_rot = {"criada": "criada", "em_andamento": "em andamento",
                  "pausada": "pausada", "concluida": "concluída",
                  "interrompida": "interrompida", "cancelada": "cancelada",
                  "falhou": "falhou"}
    outcome = (resumo.get('usados') or {}).get('research_outcome', {})
    if resumo.get('status') == 'concluida' and outcome.get('state') == 'partial':
        status_rot['concluida'] = 'etapas finalizadas; resultado com lacunas'
    coverage = {'partial': 'parcial; há dados pendentes',
                'blocked': 'bloqueada pelo provedor; evidências preservadas; retomada explícita disponível',
                'complete': 'etapas concluídas no escopo recuperado; consulte as limitações'}
    linhas = [
        f"**Objetivo:** {_text(resumo.get('objetivo'), 500) or '(não informado)'}",
        f"**Status:** {status_rot.get(resumo.get('status'), _text(resumo.get('status'), 40) or '-')} · "
        f"**Modo:** {_text(resumo.get('modo'), 40) or '-'} · "
        f"**Evidências:** {int(resumo.get('evidencias') or 0)}",
        '**Cobertura dos dados:** ' + coverage.get(outcome.get('state'), 'consulte evidências e limitações'),
        f"**Mídia descoberta:** {int(resumo_midia.get('total') or 0)} item(ns); "
        "imagens não são evidência e vídeos não foram assistidos ou analisados.",
        "**Limite epistêmico:** a verificação é lexical/determinística; "
        "estados não estabelecem causalidade e lacunas permanecem explícitas.",
    ]
    if omitted:
        linhas.append("**Componentes omitidos por dados inválidos:** "
                      + ", ".join(sorted(set(omitted))) + ".")
    texto = "\n".join(linhas)[:MAX_TEXT]
    answer = str((resumo.get("sintese") or {}).get("texto") or "").strip()[:3500]
    text_blocks = [{"type": "text", "content": answer}] if answer else []
    mensagem = {"version": jdui.VERSION,
                "blocks": text_blocks + [{"type": "text", "content": texto}] + blocks}
    ok, normalizado, erros = jdui.validar_mensagem(mensagem)
    if not ok:
        # Last-resort honest fallback: text only, never raw invalid JSON.
        minimo = {"version": jdui.VERSION, "blocks": [{
            "type": "text",
            "content": (texto + "\n\nInterface estruturada indisponível: "
                        + "; ".join(erros[:3]))[:MAX_TEXT]}]}
        _, normalizado, _ = jdui.validar_mensagem(minimo)
    return normalizado
