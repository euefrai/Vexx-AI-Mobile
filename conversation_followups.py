"""Small, explicit continuation resolver. No cross-chat or permanent memory."""
import re
import live_data
import shopping

ASK_PRODUCT = 'Qual modelo você quer usar como referência?'


def last_answer(db, owner, conv):
    row=db.execute("SELECT text FROM messages WHERE owner_id=? AND conversation_id=? AND role='assistant' ORDER BY created_at DESC,id DESC LIMIT 1",(owner,conv)).fetchone()
    return row[0] if row else ''


def weather_request(text, previous):
    t=live_data.norm(text).strip(' .?!')
    short=bool(re.fullmatch(r'(?:e |e para |e no |e no proximo |no )?(amanha|hoje|depois de amanha|fim de semana|vai chover|vai fazer frio|vai fazer calor)',t))
    req=live_data.request(text)
    if not short and not (req and req['kind']=='weather' and not live_data.place_from(text)):
        return None
    match=re.search(r'^\*\*Clima em (.+?)\*\*',previous)
    if not match or '[Fonte: Open-Meteo]' not in previous:return None
    city=match[1]
    if city=='Sua localização aproximada':return 'Previsão do tempo '+text
    return ('Previsão do tempo ' if short else '')+text+' em '+city


def weather_slots(db, owner, conv, text, message_id=None):
    """Rebuild bounded task slots from this chat, before this request only.

    No global memory; a greeting/new topic ends the pending weather task.
    Row insertion order also prevents a later concurrent request supplying slots.
    """
    params=[owner,conv]
    cutoff=''
    if message_id:
        cutoff=' AND rowid < COALESCE((SELECT rowid FROM messages WHERE owner_id=? AND conversation_id=? AND id=?),0)'
        params += [owner,conv,message_id]
    rows=db.execute("SELECT role,text FROM messages WHERE owner_id=? AND conversation_id=? AND origin='mobile'"+cutoff+" ORDER BY rowid DESC LIMIT 32",params).fetchall()
    state=None
    def advance(value, state):
        req=live_data.request(value)
        t=live_data.norm(value).strip(' .?!')
        short=bool(re.fullmatch(r'(?:e |e para |no )?(?:amanha|hoje|depois de amanha|fim de semana|vai chover)',t))
        if req and req['kind']=='weather':
            city=live_data.place_from(value) or (state or {}).get('city','')
            return dict(intent='weather',city=city,request=value,period='forecast' if re.search(r'amanha|previsao|semana',t) else 'current',unit='°C',source='conversation',pending=[] if city else ['city'])
        if state and short:
            return dict(state,request='Previsão do tempo '+value,period='forecast')
        # Bare place is a slot only in a pending task, or an explicit correction
        # (city/state). Verbs/greetings cannot become geographic entities.
        bare=bool(len(value)<=100 and re.fullmatch(r"[\wÀ-ÿ ,./'-]+[.!]?",value.strip()) and not re.search(r'\b(oi|ola|obrigad\w*|ok|valeu|nao|sim|me|quero|fale|explique|resuma|pesquise|ajude)\b',t))
        qualified=bool(re.search(r'[,/]',value) or live_data.parse_place(value)['state'])
        if state and bare and (state['pending'] or qualified):
            return dict(state,city=value.strip(' .?!'),pending=[],source='clarification')
        return None
    for role,value in reversed(rows):
        if role=='user':state=advance(value,state)
    resolved=advance(text,state)
    if not resolved:return None
    # Preserve the current request wording (current stays current).
    request=resolved['request']
    if resolved['city'] and not live_data.place_from(request):request=request.rstrip(' .?!')+' em '+resolved['city']
    return dict(resolved,resolved_request=request)


def product_reply(db, owner, conv, text, previous):
    t=live_data.norm(text)
    variation=bool(re.search(r'\b(outro|outra|outros|outras|alternativ\w*)\b',t) and re.search(r'\b(modelo\w*|produto\w*|parecid\w*|semelhant\w*|opca\w*|opco\w*)\b',t))
    selecting=previous.startswith(ASK_PRODUCT) and bool(re.fullmatch(r'(?:o |a |quero o |quero a )?(primeiro|primeira|segundo|segunda|terceiro|terceira|[1-6])[.!]?',t.strip()))
    last=None
    if previous.startswith(ASK_PRODUCT) and not selecting:
        last=shopping.ultima_consulta(db,owner,conv)
        selecting=any(t.strip(' .?!') in (live_data.norm(p.get('nome','')),live_data.norm(p.get('modelo',''))) for p in (last or {}).get('resultado',{}).get('produtos',[]) if p.get('nome'))
    if not variation and not selecting:return None
    if re.search(r'\b(nao (busque|pesquise)|sem (pesquisar|buscar|internet))\b',t):return None
    last=last or shopping.ultima_consulta(db,owner,conv)
    if not last:
        if re.search(r'\b(aquele|esse|este|isso|parecid\w*|semelhant\w*)\b',t):
            return 'Qual é o nome do modelo que você quer usar como referência? Preciso identificar o produto para consultar outra opção e seu preço.'
        return None
    products=last.get('resultado',{}).get('produtos',[])
    # Only products actually present in the immediately preceding answer qualify.
    shown=[p for p in products if p.get('nome') and p['nome'].casefold() in previous.casefold()]
    if not shown:return None
    ordinals={'primeiro':0,'primeira':0,'segundo':1,'segunda':1,'terceiro':2,'terceira':2}
    ordinal=re.search(r'\b(primeiro|primeira|segundo|segunda|terceiro|terceira)\b',t)
    number=re.search(r'\b([1-6])[.!]?$',t.strip()) if selecting else None
    index=ordinals[ordinal[1]] if ordinal else int(number[1])-1 if number else None
    named=[p for p in shown if live_data.norm(p['nome']) in t or (p.get('modelo') and len(p['modelo'])>2 and live_data.norm(p['modelo']) in t)]
    reference=shown[index] if index is not None and 0<=index<len(shown) else named[0] if len(named)==1 else shown[0] if len(shown)==1 else None
    if reference is None:
        return ASK_PRODUCT+'\n\n'+'\n'.join(f'{i+1}. {live_data.safe(p["nome"])}' for i,p in enumerate(shown[:6]))+'\n\nDiga o nome ou a posição na lista.'
    reference_name=live_data.safe(reference['nome'])
    criteria=last.get('criterios',{})
    if not criteria.get('categoria'):
        return f'Identifiquei {reference_name}. Qual categoria de produto devo pesquisar para buscar alternativas com preço?'
    # Refresh verified offers; never represent an old price as a fresh quote.
    search_text=text
    if selecting:
        row=db.execute("SELECT id FROM messages WHERE owner_id=? AND conversation_id=? AND role='assistant' ORDER BY created_at DESC,id DESC LIMIT 1",(owner,conv)).fetchone()
        original=db.execute("SELECT text FROM messages WHERE id=? AND owner_id=? AND conversation_id=? AND role='user'",(row[0].removesuffix('-r1'),owner,conv)).fetchone() if row else None
        if original:search_text=original[0]+' '+text
    result=shopping.pesquisar(db,owner,search_text,conv,criterios_base=criteria,usar_cache=False,teto_paginas=3)
    def different(p):
        if p.get('id') and p.get('id')==reference.get('id'):return False
        if live_data.norm(p.get('nome',''))==live_data.norm(reference['nome']):return False
        if reference.get('modelo') and live_data.norm(p.get('modelo',''))==live_data.norm(reference['modelo']):return False
        return True
    result={**result,'produtos':[p for p in result.get('produtos',[]) if different(p)],'alternativas':[]}
    # Save the displayed set so a subsequent ordinal references the visible answer.
    shopping.salvar_consulta(db,owner,conv,last['consulta'],result.get('criterios',criteria),result)
    if not result['produtos']:
        return f'Usei **{reference_name}** como referência, mantendo os critérios da pesquisa. Não consegui confirmar outro modelo e preço nas fontes disponíveis agora.'
    return (f'Busquei alternativas a **{reference_name}**, mantendo categoria, orçamento e requisitos informados. Semelhança por esses critérios; não implica desempenho ou compatibilidade idênticos.\n\n'
            +shopping.resumo_texto(result)+shopping.fence_resultado(result))
