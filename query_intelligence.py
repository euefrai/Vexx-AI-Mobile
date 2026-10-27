"""Request parameters for existing research routes; no fetching or model execution."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import re
import hashlib
import unicodedata
from contextlib import contextmanager
from contextvars import ContextVar
from zoneinfo import ZoneInfo

_discovery_context = ContextVar('research_discovery_context', default=None)


@contextmanager
def discovery_scope(request, *, registry=None, job_id='', step_id='', requirement_ids=()):
    token = _discovery_context.set({'request':request,'registry':registry,'job_id':job_id,
                                   'step_id':step_id,'requirement_ids':list(requirement_ids)})
    try:
        yield
    finally:
        _discovery_context.reset(token)


def constrain_provider_query(query):
    scope = _discovery_context.get()
    return constrain_discovery(query, scope['request'], lock_context=True) if scope else query


def provider_provenance(query, provider=''):
    scope=_discovery_context.get()
    if not scope or not scope['job_id']:return {}
    qid='Q-'+hashlib.sha256((scope['job_id']+'|'+scope['step_id']+'|'+query).encode()).hexdigest()[:20]
    registry=scope.get('registry')
    if registry is not None and (qid in registry or len(registry)<120):
        registry[qid]={'query':query,'step_id':scope['step_id'],'requirement_ids':scope['requirement_ids'],
                       'strategy':'provider','provider':provider}
    return {'query_ids':[qid],'requirement_ids':scope['requirement_ids'],'provider':provider}


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(text).casefold())
                   if not unicodedata.combining(c))


_NUMBERS = {'um': 1, 'uma': 1, 'dois': 2, 'duas': 2, 'sete': 7,
            'quinze': 15, 'trinta': 30}
_CURRENCIES = {'USD': r'dolares?|dolar|usd', 'BRL': r'reais|real|brl',
               'EUR': r'euros?|eur', 'JPY': r'ienes?|jpy'}

# Explicit facets only. These are retrieval requirements, not factual answers
# or an assertion that arbitrary natural language has been fully understood.
ANSWER_FACETS = {
    'founders': ('Fundadores', r'quem (?:a |o )?(?:fundou|criou)|fundadores?|fundador[ae]?|founded by|who (?:created|founded)'),
    'foundation_date': ('Data de fundação', r'quando.*(?:fundad|criad)|em que ano|data de funda|ano de funda'),
    'products': ('Produtos', r'produtos|o que.*fabrica|products'),
    'creation_date': ('Data de criação', r'\bdata de criacao\b'),
    'causes': ('Causas', r'causas?|causes?|por que (?:aconteceu|ocorreu|houve)|why did'),
    'consequences': ('Consequências', r'consequencias?|consequences?|o que (?:mudou|aconteceu) depois|what changed afterward'),
    'syntax': ('Sintaxe ou assinatura', r'sintaxe|assinatura|syntax|signature'),
    'return_value': ('Valor retornado', r'o que retorna|valor retornado|return value|\bretorno\b'),
    'behavior': ('Comportamento da operação', r'como (?:usar|utilizar|funciona)|comportamento|behavior|modifica.*original|altera.*original'),
    'examples': ('Exemplos documentados', r'exemplos?|examples?'),
    'limitations': ('Limitações', r'limitacoes|restricoes|limitations?'),
    'weight': ('Peso e unidade', r'\bpeso\b|\bweight\b|\bmais leve\b'),
    'battery': ('Bateria', r'\bbateria\b|\bbattery\b'),
    'price': ('Preço e moeda', r'precos?|\br\$|\busd\b'),
    'river_source': ('Nascente', r'\bnascente\b'),
    'river_mouth': ('Foz', r'\bfoz\b'),
    'course': ('Regiões do percurso', r'por quais regioes|quais regioes.*(?:passa|atravessa)'),
    'location': ('Localização', r'onde (?:fica|se localiza)'),
    'population': ('População e referência', r'\bpopulacao\b'),
    'alternatives': ('Alternativas', r'\balternativas\b'),
    'definition': ('Definição e finalidade', r'\bo que e\b|\bpara que serve\b'),
}


def answer_requirements(text):
    original = str(text or '')[:1000]
    norm = normalized(original)
    # Avoid inventing technical answer requirements for a gallery/search-only
    # intent, or imposing general-purpose facets on scientific research.
    if re.search(r'\b(imagens?|fotos?|videos?|cientific\w*|papers?|estudos|artigos cientificos)\b', norm):
        return []
    facets = [key for key, (_, rx) in ANSWER_FACETS.items() if re.search(rx, norm)]
    if not facets and re.search(r'diferencas entre',norm):facets=['definition']
    if 'battery' in facets and re.match(r'^(?:pesquisa profunda sobre\s+)?bateria\s+\w',norm):
        facets.remove('battery')  # Named subject "Bateria ZX" is not a request for a battery model.
    if 'foundation_date' in facets and not re.search(r'fundad|fundou|fundacao|founded|empresa|criad[ao]', norm):
        facets.remove('foundation_date')
    if re.search(r'quem criou|who created',norm) and re.search(r'\b(?:quando|when|em que ano)\b',norm) and 'foundation_date' not in facets:
        if 'creation_date' not in facets:facets.append('creation_date')
    if not facets:
        return []
    subject = re.sub(r'^(?:pesquise|pesquisa profunda sobre|encontre)\s+', '', original, flags=re.I)
    company = re.match(r'^quando\s+(?:a |o )?(.+?)\s+foi\s+fundad[ao]\b', subject, re.I)
    if company:
        subject = company[1]
    subject = re.sub(r'^(?:em que ano|quando)\s+(?:foi|foram)\s+(?:fundad[ao]s?|criad[ao]s?)\s+', '', subject, flags=re.I)
    subject = re.sub(r'^qual [eé] a origem d[ao] (?:empresa\s+)?', '', subject, flags=re.I)
    # Declarative topics and explicit interrogative relation patterns share the
    # existing Query Intelligence parser; the original remains authoritative.
    match = re.search(r'\b(?:quem (?:fundou|criou)|who (?:created|founded))\s+(?:a |o |the )?([^,?]+)', subject, re.I)
    if match:
        subject = re.split(r'\s+(?:em que|e quando|and when|quando|e quais)\b', match[1], flags=re.I)[0]
    else:
        causal=re.match(r'^por que (?:aconteceu|ocorreu|houve)\s+(.+?)(?:\s+e\s+o que\b|[?,]|$)',subject,re.I)
        if causal:subject=causal[1]
        causal=re.match(r'^quais\s+(?:(?:foram|s[aã]o)\s+)?as?\s+(?:causas?|consequ[eê]ncias?)\s+(?:de|do|da)\s+(.+?)(?:\s+e\s+(?:quais|qual|o que)\b|[?,]|$)',subject,re.I)
        if causal:subject=causal[1]
        subject = re.sub(r'^(?:quais\s+(?:(?:foram|s[aã]o)\s+)?as?\s+|as?\s+)?(?:causas? e (?:as?\s+)?consequ[eê]ncias?)\s+(?:de|do|da)\s+', '', subject, flags=re.I)
        subject = re.sub(r'^(?:como (?:usar|utilizar|funciona)|qual (?:[eé] )?(?:o peso|a bateria) (?:de|do|da))\s+', '', subject, flags=re.I)
        subject = re.sub(r'^(?:peso|bateria)\s+(?:de|do|da)\s+','',subject,flags=re.I)
        subject = re.sub(r'^(?:documenta[cç][aã]o\s+(?:oficial\s+)?|hist[oó]ria\s+(?:de|do|da)\s+(?:empresa\s+)?)', '', subject, flags=re.I)
        subject = re.split(r'[,?]|\s+(?:causas?|consequ[eê]ncias?|limita[cç][oõ]es|documenta[cç][aã]o|exemplos?|sintaxe|comportamento|peso|bateria|fontes?\s+oficiais)\b', subject, maxsplit=1, flags=re.I)[0]
    operations=re.findall(r'\b[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+',original) if set(facets)&{'syntax','behavior','examples','limitations','return_value'} else []
    operations=[op for op in operations if op[0].isupper() or re.search(re.escape(op)+r'\s*\(',original)]
    if len(set(operations))==1:
        subject=operations[0]
    subject = re.sub(r'^(?:o|a|os|as)\s+', '', subject.strip(' .?!'), flags=re.I)[:180]
    subject = re.split(r'\s+e quem\b',subject,maxsplit=1,flags=re.I)[0]
    subject = re.sub(r'\s+(?:na|no|nas|nos|de|da|do|em|com)$','',subject,flags=re.I)
    river=re.search(r'(?:nascente.*?foz|foz.*?nascente)\s+d[oa]\s+(.+?)(?:\s+e\s+(?:por|quais|qual)\b|[?,]|$)',original,re.I)
    if river:subject=river[1]
    place=re.search(r'onde (?:fica|se localiza)\s+(.+?)(?:\s+e\s+(?:qual|quais)\b|[?,]|$)',original,re.I)
    if place:subject=place[1]
    subject=re.split(r'\s+e\s+(?:qual\b|quais\b|quando\b|onde\b|como\b|quant[oa]s?\b|compare\b|divergencias\b)',subject,maxsplit=1,flags=re.I)[0]
    compare=re.search(r'^(?:pesquisa profunda sobre\s+)?(?:compare|entre|quais (?:s[aã]o )?as diferen[cç]as entre)\s+(.+?)(?:\s+(?:quanto|considerando|segundo|em rela[cç][aã]o)\b|[?]|$)',original,re.I)
    entities=[subject]
    if compare:
        section=compare[1].split('?',1)[0]
        section=re.split(r',\s*(?:qual|quais)\b',section,maxsplit=1,flags=re.I)[0]
        entities=[e.strip(' ,.!?') for e in re.split(r',|\s+(?:e|versus|vs\.?)\s+',section,flags=re.I) if e.strip(' ,.!?')]
        if not 2<=len(entities)<=4:entities=[subject]
    constraints = {'reference': 'original_request', 'must_preserve': bool(re.search(
        r'\b(?:nao|sem|exceto|ate|depois|antes|ultimos)\b|\d|r\$', norm))}
    return [{'id': 'R-' + hashlib.sha256((norm+'|'+facet+('|'+normalized(entity) if len(entities)>1 else '')).encode()).hexdigest()[:12],
             'type': 'explicit_attribute', 'description': ANSWER_FACETS[facet][0],
             'entity': entity, 'attribute': facet, 'constraints': {**constraints,
                 'mandatory_conditions': ['battery_and_card'] if facet=='weight' and re.search(r'com bateria e (?:o )?cartao',norm) else []},
             'expected_information': ANSWER_FACETS[facet][0], 'candidate_evidence_ids': [],
             'confirmed_evidence_ids': [], 'state': 'NOT_SEARCHED',
             'insufficiency_reason': 'Ainda não há passagem lida para este requisito.'}
            for entity in entities for facet in facets[:max(1,8//len(entities))]]


def requirement_contract(text):
    """Keep unparsed demands pending; they can never acquire factual support."""
    original=str(text or '')[:1000]
    requirements=answer_requirements(original)
    factual=re.sub(r'\s+e\s+(?:apresente|mostre|organize|exiba)\b.*?\bem\s+(?:cards|tabelas?|cartoes)\b.*$','',normalized(original))
    clauses=re.split(r'[,;?]|\s+e\s+(?=(?:qual|quais|onde|quando|como|quant[oa]s?|por que|o que)\b)',factual)
    ignored=[c.strip() for c in clauses if re.match(r'^(?:qual|quais|onde|quando|como|quant[oa]s?|por que|o que|em que)\b',c.strip())
             and not any(re.search(rx,c) for _,rx in ANSWER_FACETS.values())]
    if re.search(r'\be compare (?:as )?fontes\b|\bdivergencias entre fontes\b',factual):
        ignored.append('Comparação entre fontes ainda exige verificação.')
    # Bare comparative definitions have an explicit per-entity requirement.
    ignored=[c for c in ignored if not (c.startswith(('quais as diferencas','quais sao as diferencas')) and any(r['attribute']=='definition' for r in requirements))]
    if not requirements or ignored:
        requirements.append({'id':'R-'+hashlib.sha256((normalized(original)+'|original_objective').encode()).hexdigest()[:12],
          'type':'original_objective','attribute':'original_objective','entity':'','description':original,
          'expected_information':'Interpretação pendente do pedido original','state':'NOT_SEARCHED',
          'constraints':{'reference':'original_request','must_preserve':True,'mandatory_conditions':[]},
          'candidate_evidence_ids':[],'confirmed_evidence_ids':[],'passage_ids':[],
          'insufficiency_reason':'Pedido não decomposto integralmente; texto temático não comprova resposta.'})
    if re.search(r'fontes? oficiais|fontes? primarias|documentacao oficial',normalized(original)):
        requirements.append({'id':'R-'+hashlib.sha256((normalized(original)+'|source_authority').encode()).hexdigest()[:12],
          'type':'mandatory_constraint','attribute':'source_authority','entity':'','description':'Autoridade da fonte solicitada',
          'expected_information':'Verificação da autoridade para a afirmação, além da pertinência do texto',
          'state':'NOT_SEARCHED','constraints':{'reference':'original_request','must_preserve':True,'mandatory_conditions':[]},
          'candidate_evidence_ids':[],'confirmed_evidence_ids':[],'passage_ids':[],
          'insufficiency_reason':'Domínio ou título isolado não comprova autoridade para a afirmação.'})
    return {'requirements':requirements,'fully_decomposed':not any(r['type']=='original_objective' for r in requirements),
            'unparsed_demands':ignored[:8], 'original_request':original}


def entity_alias_matches(entity,text):
    """Formatting-only aliases; preserve model suffixes and variant identity."""
    name=normalized(entity);body=normalized(text)
    if not re.search(r'\d',name):return False
    tokens=re.findall(r'[a-z]+|\d+',name)
    pattern=r'(?<!\w)'+r'[\s-]*'.join(map(re.escape,tokens))+r'(?!\w)'
    for match in re.finditer(pattern,body):
        if not re.match(r'\s+(?:ii|iii|iv|pro|plus|ultra)\b',body[match.end():]):return True
    return False


def requirement_query(requirement, original):
    # Facet labels are search terms, not part of a capitalized proper name.
    query = requirement['entity'] + ' ' + requirement['description'].lower()
    if requirement.get('constraints', {}).get('must_preserve') and not _model_only_scope(original):
        return str(original)[:190] + ' ' + requirement['description']
    if re.search(r'com bateria e (?:o )?cartao',normalized(original)):
        query+=' com bateria e cartão'
    return query[:240]


def _model_only_scope(original):
    """Only model digits can be compacted; unknown/negative/local scope stays."""
    norm=normalized(original)
    if re.search(r'\b(?:sem|nao|exceto|exclu\w*|ate|abaixo|acima|compare|comparar|dois|duas|versus|vs|hoje|ontem|ultim\w*|semana|em|no|na)\b|r\$|\b(?:gb|kg|km|usd|eur)\b',norm):return False
    reqs=answer_requirements(original)
    if not reqs or not all(r['attribute'] in ('weight','battery') for r in reqs):return False
    entity=normalized(reqs[0]['entity'])
    return bool(entity and set(re.findall(r'\d+',norm))<=set(re.findall(r'\d+',entity)))


def retrieval_context(original):
    """Reuse topic/facet parsing; retain the full request when scope is uncertain.

    This is a conservative context lock, not semantic entity recognition. Only
    an explicit trailing presentation command is removed, never title words.
    """
    text = re.sub(r'\s+', ' ', str(original or '')).strip()
    text = re.split(r'[;.!?]\s*(?:apresente|mostre|exiba|organize)\s+'
                    r'(?:um\s+)?(?:resumo|os resultados|as informa[cç][oõ]es)\b',
                    text, maxsplit=1, flags=re.I)[0].strip()
    profile = topic_profile(text)
    for presentation in profile['presentation_preferences']:
        if text.endswith(presentation):
            text = text[:-len(presentation)].strip()
    requirements = answer_requirements(text)
    # Numerical, negative, geographical and comparison scope stays verbatim.
    # Do not guess how to translate a model identifier or a temporal interval.
    guarded = bool(re.search(
        r'\d|\b(?:sem|nao|exceto|exclu\w*|compare|comparar|versus|vs|'
        r'ultim\w*|hoje|ontem|semana|noticias|eventos)\b', normalized(text)))
    entity = requirements[0]['entity'] if requirements else ''
    return {'original_request': str(original or ''), 'research_request': text,
            'entity': entity, 'requirements': requirements, 'guarded': guarded,
            'source_preference': 'documentação oficial' if re.search(
                r'documentacao oficial', normalized(text)) else '',
            'presentation_preferences': profile['presentation_preferences']}


def context_subqueries(original, fallback, limit=4):
    context = retrieval_context(original)
    text = context['research_request']
    if context['guarded'] and not _model_only_scope(text):
        return [text]
    requirements = context['requirements']
    if requirements and context['entity']:
        queries = [requirement_query(r, text) for r in requirements]
        if context['source_preference']:
            queries = [q + ' ' + context['source_preference'] for q in queries]
        return list(dict.fromkeys(queries))[:max(1, limit)]
    # Splitting unknown proper names or presentation tails is unsafe. The
    # existing independent-topic split remains valid for e.g. café e chá.
    if text != str(original).strip() or topic_profile(text)['entities']:
        return [text]
    return fallback[:max(1, limit)] or [text]


def topic_profile(text):
    """Separate explicit operations from topics without claiming semantic NER.

    The original is authoritative. Unknown names remain unresolved candidates;
    dates, models, exclusions and comparisons are never inferred away.
    """
    original = str(text or '')
    value = re.sub(r'\s+', ' ', original).strip().rstrip('.!?')
    presentation = []
    tail = re.search(r'\s+e\s+(?:apresente|mostre|exiba|organize)\s+(?:(?:as?|os?)\s+)?'
                     r'(?:principais\s+)?(?:informa[cç][oõ]es|resultados|respostas?)\s+'
                     r'em\s+(?:cards|cart[oõ]es|tabelas?)(?:\s+com\s+imagens)?$', value, re.I)
    if tail:
        presentation.append(tail[0].strip())
        value = value[:tail.start()]
    value = re.sub(r'^(?:fa[cç]a\s+)?(?:uma\s+)?pesquisa\s+(?:profunda\s+)?(?:sobre\s+)?', '', value, flags=re.I)
    value = re.sub(r'^(?:pesquise|pesquisar|encontre|busque|procure)\s+(?:profundamente\s+|a fundo\s+)?', '', value, flags=re.I)
    value = re.sub(r'^(?:as?\s+)?(?:[uú]ltimas?\s+)?(?:novidades|informa[cç][oõ]es recentes)\s+sobre\s+', '', value, flags=re.I)
    value = re.sub(r'^(?:a|as|o|os)\s+(?=hist[oó]ria|documenta[cç][aã]o|especifica[cç][oõ]es|relat[oó]rio)', '', value, flags=re.I)
    operation = ''
    prefix = re.match(r'^(hist[oó]ria\s+(?:de|do|da|dos|das)\s+(?:empresa\s+)?|'
                      r'documenta[cç][aã]o\s+(?:oficia(?:l|is)\s+)?|'
                      r'especifica[cç][oõ]es\s+(?:oficia(?:l|is)\s+)?|'
                      r'relat[oó]rio\s+(?:p[uú]blico\s+)?(?:PDF\s+)?)', value, re.I)
    if prefix:
        operation = prefix[0].strip()
        value = value[prefix.end():].strip()
    source_preference = re.search(r'\s+(fontes?\s+(?:oficiais|prim[aá]rias|originais))$', value, re.I)
    preference = source_preference[1] if source_preference else ''
    if source_preference:
        value = value[:source_preference.start()].strip()
    required = ([re.sub(r'\s+(?:de|do|da|dos|das)\s*(?:empresa)?$', '', operation, flags=re.I)] if operation else [])
    required += [m[0] for m in re.finditer(r'\b(?:autonomia|limita[cç][oõ]es|processos|vantagens|custos|data de inaugura[cç][aã]o)\b', value, re.I)]
    entities = []
    for m in re.finditer(r'\b(?:[A-ZÀ-Ý][\w-]*)(?:(?:\s+(?:de|do|da|dos|das))?\s+[A-ZÀ-Ý][\w-]*)*', value):
        name = re.sub(r'^(?:Not[ií]cias|Compare|Pesquisa|Pesquise|Fontes|Documenta[cç][aã]o)\s+(?:(?:de|do|da|sobre|em)\s+)?', '', m[0])
        if normalized(name) in ('compare', 'noticias', 'pesquisa', 'pesquise', 'fontes', 'documentacao',
                                'quem','quais','qual','como','quando','onde'):
            continue
        if name.upper() in ('PDF', 'API', 'GB', 'BRL', 'USD') or len(name) < 3:
            continue
        kind = ('product_model' if re.search(r'[A-Za-z]+-?\d', name) else
                'organization' if re.search(r'\bempresa\b', normalized(original)) else 'unresolved_named_entity')
        entities.append({'name': name, 'kind': kind, 'resolution': 'explicit_text_not_verified'})
    requirements = answer_requirements(original)
    reorder = bool(re.search(r'quem fundou|quais foram as causas',normalized(original)) or (
        re.search(r'como (?:usar|utilizar|funciona)',normalized(original)) and re.search(r'\w+\.\w+',original)))
    if requirements and requirements[0]['entity'] and reorder:
        value = requirements[0]['entity']
    focused = ' '.join(x for x in (value, ' '.join(required[:1]), preference) if x).strip()
    # Discovery can reorder a noun phrase, but must not silently drop a
    # negative/budget/comparison suffix that this deterministic parser cannot model.
    guarded = bool(re.search(r'\b(?:nao|exceto|exclua|sem|ate|abaixo|acima|compare|versus)\b|r\$|\bvs\b', normalized(original)))
    if guarded:
        focused = original.strip()
    return {'original_request': original, 'primary_topic': value or original.strip(),
            'secondary_topics': [], 'entities': entities[:12], 'required_information': required,
            'intent': 'deep_research' if re.search(r'profund|a fundo', normalized(original)) else 'research',
            'hard_constraints': {'unparsed_original_guard': original if guarded else ''},
            'soft_preferences': [preference] if preference else [],
            'presentation_preferences': presentation, 'focused_query': focused,
            'answer_requirements': requirements,
            'scope': 'explicit syntax only; not universal entity disambiguation'}


def analyze(text, now=None, timezone_name='America/Bahia'):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('Relógio precisa de timezone')
    local = now.astimezone(ZoneInfo(timezone_name))
    t = normalized(text)
    domain = 'general'
    if re.search(r'\b(voos?|passage(?:m|ns) aereas?|(?:aviao|avioes)|aeroportos?)\b', t) or (re.search(r'\bpassage(?:m|ns) de .+? para ', t) and 'onibus' not in t):
        domain = 'air_travel'
    elif re.search(r'\b(onibus|rodoviari[ao]s?)\b', t):
        domain = 'bus_travel'
    elif re.search(r'\b(cotacao|cambio|dolar|dolares|usd|eur|jpy)\b', t) and not re.search(r'\b(codigo|programa|implemente)\b', t):
        domain = 'currency'
    elif re.search(r'\b(eventos?|shows?|concertos?|exposicoes)\b', t):
        domain = 'events'
    elif re.search(r'\b(noticias?|manchetes|aconteceu|acontecimentos?|novidades)\b', t):
        domain = 'news'
    elif re.search(r'\b(estudos?|cientific[oa]s?|papers?)\b', t) or re.search(r'\bartigo\b.*\b(doi|pesquisa)\b',t):
        domain = 'science'
    elif re.search(r'\b(documentacao|documentos?|arquivos?|pdf|asyncio)\b', t):
        domain = 'documents'
    params = {}
    resolved = str(text)
    relative = re.search(r'\b(daqui a|ultimos?|ultimas?|proximos?|proximas?)\s+(\d{1,3}|um|uma|dois|duas|sete|quinze|trinta)\s+(dias?|semanas?|horas?)\b', t)
    if relative:
        count = int(relative[2]) if relative[2].isdigit() else _NUMBERS[relative[2]]
        days = count * (7 if relative[3].startswith('semana') else 1)
        if not 1 <= days <= 366:
            raise ValueError('Janela temporal fora do limite de 366 dias')
        past = relative[1].startswith('ultim')
        start = local.date() - timedelta(days=days) if past else local.date()
        end = local.date() if past else local.date() + timedelta(days=days)
        if relative[3].startswith('hora'):
            start_at = local - timedelta(hours=count) if past else local
            end_at = local if past else local + timedelta(hours=count)
            start, end = start_at.date(), end_at.date()
            params.update(start_at=start_at.isoformat(), end_at=end_at.isoformat())
        params.update(start_date=start.isoformat(), end_date=end.isoformat())
        if relative[1] == 'daqui a':
            params['departure_date'] = end.isoformat()
            replacement = 'em ' + end.isoformat()
        else:
            replacement = f'entre {start.isoformat()} e {end.isoformat()}'
        # Normalization preserves character count for ordinary Portuguese accents.
        prefix = re.sub(r'\b(?:nos|nas|para)\s+$', '', str(text)[:relative.start()], flags=re.I)
        resolved = prefix + replacement + str(text)[relative.end():]
    explicit = re.search(r'\b(20\d{2}-\d{2}-\d{2})\b', t)
    if explicit and domain in ('air_travel', 'bus_travel'):
        params['departure_date'] = datetime.strptime(explicit[1], '%Y-%m-%d').date().isoformat()
    if domain in ('air_travel', 'bus_travel'):
        relative_day = re.search(r'\b(depois de amanha|amanha|hoje)\b', t)
        if relative_day and not params.get('departure_date'):
            params['departure_date'] = (local.date() + timedelta(days={'hoje': 0, 'amanha': 1, 'depois de amanha': 2}[relative_day[1]])).isoformat()
        route = re.search(r'\b(?:voos?|passage(?:m|ns)(?:\s+(?:aereas?|de onibus|rodoviarias?))?|onibus)\s+de\s+(.+?)\s+para\s+(.+?)(?=\s+(?:para\s+)?(?:daqui|hoje|amanha|depois de amanha|\d+ adultos?|um adulto)|\s+em\s+20\d\d|,|[.!?]|$)', t)
        if route:
            params.update(origin=str(text)[route.start(1):route.end(1)].strip(),
                          destination=str(text)[route.start(2):route.end(2)].strip())
        passenger = re.search(r'\b(\d+|um|uma|dois|duas)\s+adultos?\b', t)
        if passenger:
            params['adults'] = int(passenger[1]) if passenger[1].isdigit() else _NUMBERS[passenger[1]]
        params['inventory_state'] = 'not_verified'
    if domain == 'currency':
        found = sorted((m.start(), code) for code, rx in _CURRENCIES.items()
                       for m in re.finditer(r'\b(?:' + rx + r')\b', t))
        pair = list(dict.fromkeys(code for _, code in found))
        if pair:
            params.update(base=pair[0], quote=pair[1] if len(pair) > 1 else 'BRL')
        value = re.search(r'\b(\d+(?:[.,]\d+)?)\s*(?:dolares?|usd|euros?|eur|reais|brl|ienes?|jpy)\b', t)
        try:
            amount = Decimal(value[1].replace(',', '.')) if value else Decimal('1')
            if not amount.is_finite() or not 0 <= amount <= Decimal('1000000000000'):
                raise ValueError('Valor fora do limite')
            params['amount'] = str(amount)
        except InvalidOperation:
            raise ValueError('Valor inválido') from None
    if domain in ('news', 'events'):
        # Keep explicit calendar windows out of the entity, including follow-ups.
        if not params.get('start_date'):
            day = re.search(r'\b(anteontem|ontem|hoje)\b', t)
            week = re.search(r'\b(?:na|da|a)?\s*ultima semana\b', t)
            if day:
                chosen = local.date() - timedelta(days={'hoje':0,'ontem':1,'anteontem':2}[day[1]])
                params.update(start_date=chosen.isoformat(), end_date=chosen.isoformat())
            elif week:
                params.update(start_date=(local.date()-timedelta(days=7)).isoformat(), end_date=local.date().isoformat())
        # Only remove terminal presentation instructions with generic objects.
        # Comparisons naming entities, exclusions and budgets remain search text.
        presentation = r'\s+(?:e\s+)?(?:compare|resuma|destaque)\s+(?:os acontecimentos(?: mais relevantes)?|os resultados|as noticias|os destaques|os pontos principais)\s*(?=[.!?]|$)'
        boundary = r'(?=\s+(?:nos|nas|na ultima|ultimos|ultimas|proximos|proximas|recentemente|hoje|ontem|anteontem|sobre)\b|' + presentation + r'|[,.!?]|$)'
        location = re.search(r'\bem\s+(.+?)'+boundary, t)
        if not location:
            location = re.search(r'\bnoticias\s+(?:de|do|da|sobre)\s+(.+?)'+boundary, t)
        if location:
            params['location'] = str(text)[location.start(1):location.end(1)].strip()
            city_state = re.fullmatch(r'(.+?)/([A-Za-z]{2})', params['location'])
            if city_state:
                params.update(location=city_state[1].strip(), region=city_state[2].upper())
            region = re.match(r',\s*([a-z ]{2,30}?)(?=,|\s+(?:nos|nas|ultimos|ultimas)|[.!?]|$)', t[location.end():])
            if region:
                params['region'] = region[1].strip()
        if domain == 'news' and not params.get('start_date') and re.search(r'\b(ultimas?|recentemente|recentes?)\b', t):
            params.update(start_date=(local.date()-timedelta(days=7)).isoformat(),end_date=local.date().isoformat(),window_inferred=True)
        if domain == 'events' and not params.get('start_date') and re.search(r'\b(futuros?|proximos?)\b', t):
            params.update(start_date=local.date().isoformat(), end_date=(local.date()+timedelta(days=90)).isoformat(), window_inferred=True)
        topic = re.search(r'\b(?:sobre|acerca de)\s+(.+?)(?=\s+(?:em|(?:nos|nas)\s+(?:ultimos?|ultimas?|proximos?|proximas?)|na ultima|hoje|ontem|anteontem)\b|' + presentation + r'|[,.!?]|$)', t)
        if topic and (not params.get('location') or not topic[1].strip().startswith(normalized(params['location']))):
            params['topic'] = str(text)[topic.start(1):topic.end(1)].strip()
            params['topic'] = topic_profile(params['topic'])['primary_topic']
    search_query = resolved
    if domain in ('air_travel', 'bus_travel') and params.get('origin') and params.get('destination'):
        mode = 'voos' if domain == 'air_travel' else 'passagens de ônibus'
        search_query = f'"{params["origin"]}" "{params["destination"]}" {mode}'
        if params.get('departure_date'):
            search_query += ' ' + params['departure_date']
        if params.get('adults'):
            search_query += ' ' + str(params['adults']) + ' adulto'
    if domain in ('news', 'events') and (params.get('location') or params.get('topic')):
        search_query = ('"' + params['location'] + '"' if params.get('location') else '') + (' "'+params['region']+'"' if params.get('region') else '') + (' notícias' if domain == 'news' else ' eventos programação')
        # News dates are a verification filter, not literal text that pages must repeat.
        if domain == 'events' and params.get('end_date'):
            search_query += ' ' + params['start_date'] + ' ' + params['end_date']
        if params.get('topic'):
            search_query += ' ' + params['topic']
        # Do not shorten ambiguous restrictions that this parser does not model.
        if re.search(r'\b(?:nao|exceto|exclua|sem|ate|abaixo|acima|menos de|mais de)\b|r\$', t):
            search_query = resolved
        search_query = search_query.strip()
    required = {'air_travel': ['origin','destination','departure_date','adults','operator','departure_time','price','currency','inventory','source','observed_at'],
                'bus_travel': ['origin','destination','departure_date','operator','departure_time','price','currency','inventory','source','observed_at'],
                'news': ['article_url','article_text','published_at','location','source'],
                'events': ['name','location','event_date','organizer','source'],
                'science': ['title','doi','authors','publication_date','content_scope','source']}.get(domain, ['source','content_scope'])
    missing = [key for key in ('origin','destination','departure_date','adults') if domain in ('air_travel','bus_travel') and not params.get(key)]
    return {'version': 1, 'required_data': required, 'missing_parameters': missing, 'search_query': search_query[:240], 'domain': domain, 'original_request': str(text)[:1000],
            'resolved_request': resolved[:1000], 'parameters': params,
            'temporal': bool(params.get('start_date') or relative or explicit or re.search(r'\b(agora|atual|recentes?|hoje)\b', t)),
            'resolved_at': now.isoformat(), 'timezone': timezone_name,
            'requires_live_data': domain in ('air_travel', 'bus_travel', 'currency', 'news', 'events'),
            'constraints': {'hard': {k:v for k,v in params.items() if k in ('location','region','topic','start_date','end_date','start_at','end_at','origin','destination','departure_date','adults')},
                            'soft': {}, 'optional': {}}}


def constrain_discovery(query, request, *, lock_context=False):
    """Reformulation may broaden vocabulary, never drop an explicit news place/topic."""
    context = retrieval_context(request.get('original_request', ''))
    original = context['research_request']
    scientific_expansion = request.get('domain') == 'science' and not re.search(
        r'\d|\b(?:sem|nao|exceto|exclu\w*|desde|antes|depois)\b', normalized(original))
    compact_product=(_model_only_scope(original) and normalized(context['entity']) in normalized(query)
                     and all('battery_and_card' not in r['constraints'].get('mandatory_conditions',[]) or
                             r['attribute']!='weight' or 'com bateria e cartao' in normalized(query)
                             for r in context['requirements']))
    if lock_context and context['guarded'] and original and not scientific_expansion and not compact_product:
        # Keep the authoritative constraints together; providers can tokenize
        # them, but the planner must not silently drop an exclusion or date.
        if normalized(original).rstrip('.?!') not in normalized(query):
            original_words = set(re.findall(r'\w+', normalized(original)))
            # Preserve the new facet of a gap, too. Returning just the original
            # would collapse a methodology/price retry into an already-run query.
            extra = list(dict.fromkeys(word for word in re.findall(r'[\w.]+', str(query))
                                      if len(word) > 2 and normalized(word) not in original_words))
            query = ' '.join([original, *extra]).strip()
    elif (context['entity'] and any(r['attribute'] not in ('price', 'weight', 'battery')
                                   for r in context['requirements'])
          and normalized(context['entity']) not in normalized(query)):
        query = context['entity'] + ' ' + str(query)
    if context['source_preference'] and 'oficial' not in normalized(query):
        query = str(query) + ' ' + context['source_preference']
    if request.get('domain') != 'news': return query
    params=request.get('parameters') or {}
    missing=[]
    for field in ('location','region','topic'):
        value=str(params.get(field) or '').strip()
        if value and not re.search(r'(?<!\w)'+re.escape(normalized(value))+r'(?!\w)',normalized(query)):
            missing.append('"'+value.replace('"','')+'"')
    suffix=' '.join(missing)
    return (str(query)[:max(0,240-len(suffix)-1)]+' '+suffix).strip() if suffix else query
