"""JuliaEvidenceGraph (V4.6) — grafo de evidências em SQLite (sem banco externo).

Nós: sources, documents, claims, evidence (referencia `evidence`), runs.
Arestas tipadas: SUPPORTS, PARTIALLY_SUPPORTS, CONTRADICTS, MENTIONS,
DERIVED_FROM, DUPLICATES, REPLACES, REQUIRES_VERIFICATION.

Princípio (§2): rótulo factual NUNCA vem de similaridade pura. Similaridade
gera MENTIONS/DERIVED_FROM/DUPLICATES (provisório, estrutural). SUPPORTS só
por regra determinística válida (quantidade exata); o resto verificável fica
UNVERIFIED até inferência real (BLOQUEADA hoje).
"""
import hashlib
import json
import re
import sqlite3
import urllib.parse
from datetime import datetime, timezone

TIPOS_RELACAO = ("SUPPORTS", "PARTIALLY_SUPPORTS", "CONTRADICTS", "MENTIONS",
                 "DERIVED_FROM", "DUPLICATES", "REPLACES", "REQUIRES_VERIFICATION")
KINDS_NO = ("source", "document", "claim", "evidence", "run")


class GraphErro(ValueError):
    def __init__(self, mensagem, codigo="erro"):
        super().__init__(mensagem)
        self.codigo = codigo


_EXCEPTION_ACTION = r'(?:rais\w*|re-rais\w*|propagat\w*|aggregat\w*|combin\w*|group\w*|lanc\w*|levant\w*|relanc\w*|propag\w*|agreg\w*|agrup\w*|tratad\w*|treated)'
_EXCEPTION_NOUN = r'(?:exceptions?|exceptiongroups?|baseexceptiongroup|excecoes|excecao|return_exceptions)'
_EXCEPTION_RELATION = (r'\b'+_EXCEPTION_ACTION+r'\b[^.!?;]{0,160}\b'+_EXCEPTION_NOUN+r'\b|'
                       r'\b'+_EXCEPTION_NOUN+r'\b[^.!?;]{0,160}\b'+_EXCEPTION_ACTION+r'\b')

_ANSWER_RELATIONS = {
    'founders': r'(?:fundad[ao]s?|criad[ao]s?|founded|established).{0,100}\b(?:por|by)\s+\w+|fundadores?\s*[:—-]\s*\w+',
    'foundation_date': r'(?:fundad[ao]|fundacao|founded|established|criad[ao]).{0,100}\b(?:1[5-9]|20)\d{2}\b|\b(?:1[5-9]|20)\d{2}\b.{0,80}(?:fundad[ao]|fundacao|founded)',
    'creation_date': r'\b(?:criad[ao]|created|desenvolvid[ao])\s+(?:(?:em|in)\s+)?(?:1[5-9]|20)\d{2}\b',
    'products': r'\b(?:produz|fabrica|fabricam|produzem|manufactures?|makes?|manufacturers? of|producers? of|products include|produtos incluem)\b.{4,}',
    'causes': r'\b(?:causad[ao]|causas? (?:foram|incluem)|caused|porque|devido|motivada|motivado|desencadead[ao])\b.{8,}',
    'consequences': r'\b(?:resultou|resultaram|consequencias? (?:foram|incluem)|resulted|levou a|levaram a|provocou)\b.{8,}',
    'syntax': r'\w+\s*\([^)]*\)',
    'return_value': r'\b(?:retorna|returns?(?!\s+value\b))\b.{8,}',
    'behavior': r'\b(?:retorna|returns?(?!\s+value\b)|permite|allows?|cria|creates?|adiciona|adds?|copia|copies|aumenta|increases?|grows?|grow the|aumentar)\b.{8,}',
    'cancellation': r'\b(?:cancel(?:s|led|ed|ling|ing)?|cancelad[ao]s?|cancela)\b.{4,}',
    'exceptions': _EXCEPTION_RELATION,
    'examples': r'\w+\s*\([^)]*\)',
    'limitations': r'\b(?:nao pode|cannot|must not|limitad[ao]|limite de|maximum|exceeds|exception|raises|restricao)\b.{4,}',
    'weight': r'\b\d+(?:[.,]\d+)?\s*(?:g|kg|gramas?|kilograms?)\b',
    'battery': r'\b(?:bateria|battery)\b.{0,60}\b[A-Za-z]+[ -]?[A-Za-z]*\d[\w-]*',
    'price': r'(?:r\$|us\$|usd|eur|brl)\s*\d+[\d.,]*',
    'river_source': r'\b(?:nasce|tem (?:a |sua )?nascente|has its source|rises)\s+(?:em|n[ao]s?|at|in)\s+\w.{4,}',
    'river_mouth': r'\b(?:desagua|tem (?:a |sua )?foz|empties|flows)\s+(?:em|n[ao]s?|into)\s+\w.{4,}',
    'course': r'\b(?:atravessa|percorre|atravessam|runs through|flows through)\s+\w.{4,}',
    'location': r'\b(?:fica|localiza-se|esta localizad[ao]|is located)\s+(?:em|n[ao]s?|in)\s+\w.{4,}',
    'population': r'\b(?:tem|possui|population of|populacao de)\s+(?:uma populacao de )?\d[\d., ]*\s*(?:habitantes|people|residents)\b',
    'alternatives': r'\b(?:alternativas? (?:incluem|sao)|alternatives include)\s+\w.{4,}',
    'definition': r'\b(?:e|is)\s+(?:um[a]?|a|an)\s+(?:tipo de |modalidade de )?(?:curso|graduacao|degree|programa|software|ferramenta)\b.{8,}',
}


def _canonical_operation(text):
    import query_intelligence as qi
    return re.sub(r'\s*\.\s*','.',qi.normalized(text)).replace('.prototype.','.')


def _passage_support(req, passage, source):
    """One explicit entity/attribute relation; no title-only factual support.

    Limited adjacent context is retained literally. This is not a universal NER
    or semantic truth model, and an unresolved relation remains unconfirmed.
    """
    import query_intelligence as qi
    from web_extract import passage_role
    # Re-evaluate the literal role; stored/model-supplied labels are not proof.
    if passage_role(passage['text']) in ('QUESTION_TEXT','ANSWER_OPTION','UNKNOWN_CORRECTNESS'):
        return None
    entity=_canonical_operation(req['entity']).strip(' .?!')
    anchor=re.compile(r'(?<![\w.])'+re.escape(entity)+r'(?!\w|\.\w)')
    text=qi.normalized(passage['text'])
    text=re.sub(r'^(?:explicacao|comentario|justificativa|resposta correta|gabarito)\s*[:—-]\s*','',text)
    attribute=req['attribute']
    relation_rx=_ANSWER_RELATIONS.get(attribute)
    if not entity or not relation_rx:return None
    # Do not split qualified names or turn prose on another method into evidence
    # merely because the page title contains the desired API.
    qualified=bool(re.fullmatch(r'\w+(?:\.\w+){1,}',qi.normalized(req['entity'])))
    if qualified:
        # Normalize only this API's dots; sentence punctuation stays intact.
        parts=entity.split('.')
        alias=r'\s*\.\s*'.join(re.escape(t) for t in parts[:-1])+r'(?:\s*\.\s*prototype)?\s*\.\s*'+re.escape(parts[-1])
        text=re.sub(alias,lambda _:entity,text)
    clauses=re.split(r'(?<=[!?;])\s+|(?<=[.])\s+(?=[a-z])|\n+',text)
    previous=''; partial_found=False
    heading=passage.get('section') or passage.get('context_heading') or (source.get('document_context') or {}).get('heading','')
    scoped_entity=re.fullmatch(r'\s*'.join(re.escape(c) for c in entity if not c.isspace())+
                              r'(?:\s+(?:digital camera|camera|manual|specifications))?',qi.normalized(heading))
    if attribute in ('weight','battery','price') and passage.get('element_type')=='tr' and scoped_entity:
        labels={'weight':r'(?:weight|peso)', 'battery':r'(?:battery|bateria)', 'price':r'(?:price|preco)'}
        # A literal table row plus its real preceding document heading supplies
        # useful scope, but not a local explicit subject: retain PARTIAL only.
        if re.match(labels[attribute]+r'\b',text) and re.search(relation_rx,text) and not re.search(r'\b(?:unknown|not available|desconhecido)\b',text):
            partial_found=True
    if attribute in ('founders','foundation_date','products') and passage.get('element_type')=='tr':
        # An actual named DOM table owns its fields. This is stronger than a
        # page title: both header and row retain offsets into the same extraction.
        header=qi.normalized(passage.get('table_header',''))
        header=re.sub(r'\s+(?:s\.?a\.?|corporation|inc\.?|ltd\.?)$','',header)
        hs=passage.get('table_header_span') or {};rs=passage.get('source_span') or {}
        verified=(header==entity and hs.get('sha256') and hs.get('sha256')==rs.get('sha256')
                  and type(hs.get('start')) is int and type(hs.get('end')) is int and type(rs.get('start')) is int
                  and 0<=hs['start']<hs['end']<=rs['start'])
        fields={'founders':r'^(?:founder(?:s)?|fundador(?:es|\s*\(es\))?)\s+[^\d]{4,}',
                'foundation_date':r'^(?:founded|funda[cç][aã]o)\s+.{0,90}\b(?:1[5-9]|20)\d{2}\b',
                'products':r'^(?:products|produtos)\s+\w.{3,}'}
        rows=passage.get('table_rows') or [{'start':0,'end':len(passage['text'])}]
        for row in rows[:16]:
            start,end=row.get('start'),row.get('end')
            if type(start) is not int or type(end) is not int or not 0<=start<end<=len(passage['text']):continue
            field_text=qi.normalized(passage['text'][start:end])
            if verified and re.search(fields[attribute],field_text) and not re.search(r'\b(?:unknown|desconhecid\w*|nao confirmado|not known)\b',field_text):
                return 'DIRECT_SUPPORT'
    if passage.get('element_type')=='tr' and scoped_entity and passage.get('table_field')==attribute:
        fields={'founders':r'^(?:fundador(?:es|\s*\(es\))?|criador(?:es)?|founder(?:s)?)\s+[^\d]{4,}',
                'foundation_date':r'^(?:funda[cç][aã]o|founded)\s+.{0,90}\b(?:1[5-9]|20)\d{2}\b',
                'products':r'^(?:produtos|products)\s+\w.{3,}',
                'river_source':r'^(?:nascente|source)\s+\w.{4,}',
                'river_mouth':r'^(?:foz|mouth)\s+\w.{4,}'}
        if attribute in fields and re.search(fields[attribute],text) and not re.search(r'\b(?:unknown|desconhecid\w*|nao confirmado)\b',text):
            partial_found=True
    section=qi.normalized(passage.get('section') or '')
    if qualified and attribute in ('cancellation', 'exceptions'):
        # A literal API signature can scope later paragraphs in its definition.
        # Keep this as partial support: a signature is not the local subject.
        path = passage.get('section_path') or []
        signature = path[-1] if path else {}
        hs, ps = signature.get('source_span') or {}, passage.get('source_span') or {}
        aligned = (signature.get('level') == 7 and hs.get('sha256') == ps.get('sha256')
                   and bool(ps.get('sha256')) and type(hs.get('start')) is int
                   and type(hs.get('end')) is int and type(ps.get('start')) is int
                   and 0 <= hs['start'] < hs['end'] <= ps['start'])
        if (aligned and anchor.search(_canonical_operation(signature.get('text') or ''))
                and re.search(relation_rx, text, re.S)):
            partial_found = True
    section_facets={'return_value':('return value','valor retornado','valor de retorno'),
                    'behavior':('description','descricao')}
    if qualified and section in section_facets.get(attribute,()) and anchor.search(_canonical_operation(source.get('titulo') or '')):
        # The heading is part of the literal span. A title supplies API scope,
        # not the missing subject: this remains partial, never direct support.
        body=re.sub(r'^'+re.escape(section)+r'\s*[:—-]?\s*','',text)
        other_ops=[op for op in re.findall(r'\b\w+(?:\.\w+)+',body) if _canonical_operation(op)!=entity]
        if text.startswith(section) and len(body)>=8 and not other_ops and not re.search(r'\b(?:unknown|desconhecid\w*|nao confirmad\w*)\b',body):
            partial_found=True
    if attribute in ('causes','consequences'):
        # A literal document subject followed by a pertinent section is useful
        # context, not proof of a causal relation. Never promote it to DIRECT.
        path=passage.get('section_path') or []
        if len(path)==2:
            subject,facet=path
            rs=passage.get('source_span') or {}
            previous_end=0;previous_level=0;aligned=bool(rs.get('sha256'))
            for h in path:
                hs=h.get('source_span') or {}
                start,end,level=hs.get('start'),hs.get('end'),h.get('level')
                external=(previous_level==0 and level==1 and hs.get('scope')=='normalized_dom_heading'
                          and h.get('extraction_sha256')==rs.get('sha256') and start==0
                          and hs.get('sha256')==hashlib.sha256(h.get('text','').encode()).hexdigest())
                aligned=aligned and (type(start) is int and type(end) is int and type(level) is int
                    and previous_end<=start<end and 1<=level<=6 and previous_level<level
                    and end-start==len(h.get('text','')) and (external or
                        (hs.get('scope')=='normalized_available_extraction' and hs.get('sha256')==rs.get('sha256'))))
                if not aligned:break
                previous_end=0 if external else end;previous_level=level
            labels={'causes':r'(?:causas?|antecedentes|background|origens|origins)',
                    'consequences':r'(?:consequencias?|desdobramentos|aftermath|outcomes)'}
            body=re.sub(r'^'+re.escape(qi.normalized(facet.get('text','')))+r'\s*','',text)
            if (aligned and type(rs.get('start')) is int and subject.get('level')==1
                    and (previous_end<=rs['start'] or (facet.get('source_span') or {}).get('start')==rs['start'])
                    and qi.normalized(subject.get('text',''))==entity
                    and re.fullmatch(labels[attribute],qi.normalized(facet.get('text','')))
                    and len(body)>=24):
                partial_found=True
        heading = r'(?:principais\s+)?'+('causas?' if attribute=='causes' else 'consequencias?')
        scoped = re.match(heading+r'\s+(?:de|da|do)\s+'+re.escape(entity)+r'\s*:\s*(.+)',text,re.S)
        if scoped and re.search(relation_rx,scoped[1]) and not re.search(
                r'\b(?:nao|nunca|not|never|talvez|hipotese)\b',scoped[1]):
            # A heading supplies useful scope, but the local subject may still
            # be implicit. Preserve as partial, never claim complete coverage.
            partial_found=True
    if qualified and anchor.search(_canonical_operation(source.get('titulo') or '')):
        leaf=entity.split('.')[-1]
        for clause in clauses:
            if re.match(r'(?:the\s+)?'+re.escape(leaf)+r'\s*\([^)]*\)\s*(?:method\s+)?',clause) and re.search(relation_rx,clause):
                if not re.search(r'\b\w+(?:\.\w+)+',clause) and not re.search(r'\b(?:not|never|nao|nunca)\b',clause):
                    partial_found=True
    company_context=False
    for clause in clauses:
        if not clause.strip():continue
        inherited_company=company_context
        subject_match=anchor.search(clause)
        explicit_subject=bool(subject_match and clause[:subject_match.start()].strip() in ('','a','o','the')
                              and re.match(r'\s+(?:was founded|was established|foi fundad[ao]|foi criad[ao]|is (?:a|an)|produz|fabrica)\b',clause[subject_match.end():]))
        # At most one neutral bridge after an explicit entity subject. A new
        # subject, reported speech, negation or arbitrary prose resets scope.
        bridge=bool(re.fullmatch(r'(?:the company|a empresa|a companhia)\s+(?:has operations|operates|tem operacoes|atua)\s+(?:in|em)\s+[^.!?;]{1,100}[.!?]?',clause))
        bridge=bridge and not re.search(r'\b(?:que|which|who|not|never|nao|nunca)\b',clause)
        company_context=explicit_subject or (inherited_company and bridge and bool(anchor.search(previous)))
        if attribute=='causes':
            # Causal direction matters: an antecedent which "led to X" is a
            # cause of X, never a consequence of X. Keep the original span.
            inverse=re.search(r'\b(?:levou a|levaram a|causou|causaram|provocou|provocaram|desencadeou|resultou em)\s+(?:a |o )?'+re.escape(entity)+r'(?!\w|\.\w)',clause)
            if inverse and len(clause[:inverse.start()].strip())>=8 and not re.search(
                r'\b(?:nao|nunca|not|never|poderia|pode|talvez|hipotese)\b',clause[:inverse.start()]):
                return 'DIRECT_SUPPORT'
        named=anchor.search(clause)
        predicate=re.search(relation_rx,clause,re.S)
        if named and attribute in ('syntax','examples') and re.match(r'\s*\([^)]*\)',clause[named.end():]):
            return 'DIRECT_SUPPORT'
        context=False
        if not named and previous and re.match(r"^(?:ela|ele|it(?:'s)?|a empresa|a companhia|the company)\s+",clause):
            # Exactly the immediately preceding short sentence must start with
            # the entity as its own subject. No other entity/sentence in between.
            context=bool(re.fullmatch(r'(?:a |o )?'+re.escape(entity)+r'\s+(?:foi|was|is|e|produz|fabrica)\b[^.!?;]{0,220}[.!?]?',previous))
            context=context or inherited_company
        if qualified and not named and previous:
            context=context or bool(re.fullmatch(re.escape(entity)+r'\s*\([^)]*\)',previous))
        if predicate and (named or context):
            # Entity must precede and own the predicate. A noun in the entity
            # (e.g. Fábrica) must not itself be mistaken for a verb.
            if named and predicate.start()<named.end():
                predicate=re.search(relation_rx,clause[named.end():],re.S)
                if predicate:
                    offset=named.end()
                else:
                    previous=clause;continue
            else:offset=0
            pos=predicate.start()+offset
            gap=clause[named.end():pos] if named else re.sub(r"^(?:ela|ele|it(?:'s)?|a empresa|a companhia|the company)\s+",'',clause[:pos])
            if attribute in ('founders','foundation_date','creation_date','products','causes','consequences',
                             'river_source','river_mouth','course','location','population','definition','alternatives'):
                # Bounded copular/auxiliary modifiers only. Reported facts about
                # another subject are not transferred to this entity.
                allowed=r'\s*(?:(?:foi|was|is|e|a|o|uma|um|an?|the|empresa|companhia|company|public|service|vertically|integrated|que|no|na|brasil|brazil|in)\s+){0,12}'
                if attribute=='products':
                    allowed=r'\s*(?:(?:is|e|a|an|the)\s+)*(?:(?:one of the|uma das|um dos)\s+)?(?:(?:largest|leading|biggest|maiores|principais)\s+)?'
                if attribute in ('river_source','river_mouth','course'):
                    allowed=r'\s*'
                    if (attribute=='river_mouth' and re.fullmatch(r'\s*nasce\s+(?:em|na|no)\s+[^.!?;]{4,100}\s+e\s*',gap)
                            and not re.search(r'\b(?:que|rio|recebe|onde|cujo)\b',gap)):
                        allowed=re.escape(gap)
                if not re.fullmatch(allowed,gap):previous=clause;continue
                if attribute in ('causes','consequences') and named and clause[:named.start()].strip() not in ('','a','o','as','os','the'):
                    previous=clause;continue
            if attribute in ('weight','battery','price'):
                allowed=r'[\s:—-]*(?:(?:pesa|peso|weight|is|of|de|tem|has|bateria|battery|custa|preco|price|approximately|aproximadamente|com|with)\b[\s:—-]*){0,6}'
                if not re.fullmatch(allowed,gap):previous=clause;continue
            if re.search(r'\b(?:nao|nunca|not|never)\b',clause[max(0,pos-25):pos]):
                previous=clause;continue
            if re.search(r'\b(?:nao se sabe|desconhecid\w*|unknown|not known|nao foi confirmad\w*)\b',clause):
                previous=clause;continue
            conditions=(req.get('constraints') or {}).get('mandatory_conditions',[])
            partial='battery_and_card' in conditions and not re.search(r'\b(?:com bateria e (?:o )?cartao|with battery and (?:memory )?card)\b',clause)
            if not partial:return 'DIRECT_SUPPORT'
            partial_found=True
        previous=clause
    return 'PARTIAL_SUPPORT' if partial_found else None


def select_answer_passages(coverage, limit=None):
    """Keep multi-requirement bindings and prefer aspect diversity, same budget."""
    if limit is None:
        aspects=len({p['requirement_id'] for p in coverage.get('passages',[])})
        # API behavior includes default/optional and cancellation/error cases;
        # one span per aspect loses those conditions. The same eight-span cap
        # and 1800-character synthesis budget still apply.
        variants=2 if any(r.get('attribute') in ('cancellation','exceptions')
                          for r in coverage.get('requirements',[])) else 1
        limit=min(8,max(3,aspects*variants))
    by_id={}
    for passage in coverage.get('passages',[]):
        saved=by_id.setdefault(passage['id'],{**passage,'requirement_ids':[], 'requirement_support':{}})
        rid=passage['requirement_id']
        if rid not in saved['requirement_ids']:saved['requirement_ids'].append(rid)
        saved['requirement_support'][rid]=passage.get('support_label','DIRECT_SUPPORT')
    selected=[];covered=set()
    while by_id and len(selected)<limit:
        key=max(by_id,key=lambda k:len(set(by_id[k]['requirement_ids'])-covered))
        item=by_id.pop(key);selected.append(item);covered.update(item['requirement_ids'])
    return selected


def _literal_table_passages(source,text,url,requirements):
    """Only real table labels/values found in returned text, scoped by table head."""
    import query_intelligence as qi
    labels={'founders':r'fundador(?:es|\s*\(es\))?|criador(?:es)?|founder(?:s)?',
            'foundation_date':r'funda[cç][aã]o|founded','products':r'produtos|products',
            'river_source':r'nascente|source','river_mouth':r'foz|mouth'}
    entities={qi.normalized(r['entity']) for r in requirements}
    out=[]
    for table in (source.get('tabelas') or [])[:5]:
        if not isinstance(table,list) or not table or not isinstance(table[0],list) or len(table[0])!=1:continue
        heading=str(table[0][0])[:160]
        if qi.normalized(heading) not in entities or heading.casefold() not in text.casefold():continue
        for row in table[1:40]:
            if not isinstance(row,list) or len(row)!=2:continue
            label=str(row[0]).strip();value=re.split(r'[\[(|]',str(row[1]),maxsplit=1)[0].strip()
            field=next((key for key,pattern in labels.items() if re.fullmatch(pattern,qi.normalized(label))),None)
            if not field or len(value)<4:continue
            literal=label+' '+value
            match=re.search(r'\s+'.join(re.escape(p) for p in literal.split()),text,re.I)
            if not match or match.end()-match.start()>1100:continue
            chunk=text[match.start():match.end()]
            out.append({'id':'P-'+hashlib.sha256((url+'|'+str(match.start())+'|'+chunk).encode()).hexdigest()[:16],
                        'source_url':url,'text':chunk,'section':heading,'element_type':'tr','table_field':field,
                        'text_span':{'start':match.start(),'end':match.end(),'scope':'returned_extracted_text'}})
    return out[:12]


def requirement_coverage(query, sources, *, requirements=None):
    """Traceable, conservative extraction checks; not a statistical truth score."""
    import query_intelligence as qi
    from web_extract import passage_candidates
    contract=qi.requirement_contract(query)
    requirements = [dict(r) for r in (contract['requirements'] if requirements is None else requirements)]
    applicable=any(r.get('type','explicit_attribute')=='explicit_attribute' for r in requirements)
    if not applicable:
        return {'applicable': False, 'requirements': requirements, 'passages': [], 'complete': False,
                'fully_decomposed':False,'unparsed_demands':contract['unparsed_demands'],
                'scope': 'no explicit supported facet parsed; not proof of completeness'}
    matches = []
    diagnostics={'read_documents':0,'generated_passages':0,'stale_passages_rejected':0}
    for source in sources[:80]:
        if source.get('relevante') is False or (source.get('vertical') or {}).get('eligible') is False:
            continue
        text = source.get('texto') or source.get('texto_lido') or source.get('trecho') or ''
        if not isinstance(text, str): text = str(source.get('trecho') or '')
        read = source.get('status') == 'aberta' or source.get('texto_lido') is True or source.get('lida') is True
        if not read or source.get('content_scope') in ('feed_metadata','metadata_only','abstract_only'):
            continue
        url = str(source.get('url_final') or source.get('final') or source.get('url') or '')
        passages = source.get('answer_passages') or []
        if isinstance(source.get('texto'),str) and source['texto']:
            valid=[]
            for passage in passages[:40]:
                span=passage.get('text_span') or {};start,end=span.get('start'),span.get('end')
                if (type(start) is int and type(end) is int and 0<=start<end<=len(text)
                        and text[start:end]==passage.get('text')):valid.append(passage)
                else:diagnostics['stale_passages_rejected']+=1
            passages=valid
        passages = passages or (_literal_table_passages(source,text,url,requirements)+passage_candidates(text, url, source.get('secoes')))[:40]
        diagnostics['read_documents']+=1
        diagnostics['generated_passages']+=len(passages[:40])
        for req in requirements:
            for p in passages[:40]:
                label = _passage_support(req,p,source)
                if label:
                    matches.append({**p, 'requirement_id': req['id'], 'source_id': source.get('id') or source.get('fonte_id') or url,
                                    'document_id':source.get('document_id') or 'D-'+hashlib.sha256((url+'|'+text).encode()).hexdigest()[:24],
                                    'evidence_id': source.get('id') or '', 'support_label':label,
                                    'answerability':'DIRECT_ANSWER' if label=='DIRECT_SUPPORT' else 'PARTIAL_ANSWER',
                                    'reason':'bounded_explicit_entity_attribute_relation'})
    for req in requirements:
        if req.get('attribute')=='source_authority':
            import python_docs_discovery
            read=[s for s in sources if s.get('texto_lido') is True]
            if read and all(python_docs_discovery.has_read_authority(s,query) for s in read):
                req.update(state='SUPPORTED',insufficiency_reason='',confirmed_evidence_ids=[
                    str(s.get('id') or s.get('url') or '') for s in read[:8]])
            continue
        if req.get('type') in ('original_objective','mandatory_constraint'):continue
        found = [p for p in matches if p['requirement_id'] == req['id']]
        direct = [p for p in found if p['support_label']=='DIRECT_SUPPORT']
        ids=[];seen_documents=set()
        sources_by_id={str(s.get('id') or s.get('url') or ''):s for s in sources}
        for p in direct:
            evidence_id=p['evidence_id'] or p['source_id']
            document=sources_by_id.get(str(evidence_id),{}).get('document_id') or evidence_id
            if document not in seen_documents:
                seen_documents.add(document);ids.append(evidence_id)
        ids=ids[:8]
        req.update(state='SUPPORTED' if direct else 'PARTIALLY_SUPPORTED' if found else 'DISCOVERED' if sources else 'NOT_SEARCHED',
                   candidate_evidence_ids=[str(s.get('id') or s.get('url') or '') for s in sources[:8]],
                   confirmed_evidence_ids=ids, passage_ids=list(dict.fromkeys(p['id'] for p in found))[:8],
                   insufficiency_reason=('Condições obrigatórias ausentes no trecho.' if found and not direct else '') if found else 'Nenhuma relação explícita com a entidade foi recuperada para este aspecto.')
    # Conflicts are only flagged for explicit founding years, not arbitrary
    # numbers/dates on the page. This is a request for review, never resolution.
    for req in requirements:
        if req['attribute'] != 'foundation_date': continue
        found = [p for p in matches if p['requirement_id'] == req['id']]
        values = set()
        for p in found:
            value = re.search(r'(?:fundad[ao]|fundacao|founded|established).{0,50}?\b((?:1[5-9]|20)\d{2})\b', qi.normalized(p['text']))
            if value: values.add(value[1])
        if len(values)>1:
            req.update(state='CONTRADICTED', insufficiency_reason='Anos de fundação divergentes em passagens; exige verificação.')
    # Cap the public bindings fairly: a prolific syntax facet must not crowd
    # out the only return/limitation passage before selection even runs.
    groups=[[p for p in matches if p['requirement_id']==r['id']] for r in requirements]
    retained=[]
    for index in range(max((len(g) for g in groups),default=0)):
        for group in groups:
            if index<len(group) and len(retained)<32:retained.append(group[index])
        if len(retained)>=32:break
    diagnostics.update(matched_bindings=len(matches),retained_bindings=len(retained))
    diagnostics.update(recognized_requirements=sum(r.get('type','explicit_attribute')=='explicit_attribute' for r in requirements),
                       undecomposed_objectives=sum(r.get('type')=='original_objective' for r in requirements),
                       direct_requirements=sum(r['state']=='SUPPORTED' for r in requirements),
                       partial_requirements=sum(r['state']=='PARTIALLY_SUPPORTED' for r in requirements),
                       pending_requirements=sum(r['state']!='SUPPORTED' for r in requirements))
    return {'applicable': True, 'requirements': requirements, 'passages': retained, 'diagnostics':diagnostics,
            'fully_decomposed':contract['fully_decomposed'],'unparsed_demands':contract['unparsed_demands'],
            'complete': all(r['state']=='SUPPORTED' for r in requirements),
            'scope': 'explicit relation patterns in bounded literal spans; not independent factual verification'}


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def compact_coverage(coverage):
    """Persist references once; literal passage text already lives with evidence."""
    return {**coverage, 'passages': [{k:p[k] for k in ('id','source_id','document_id','requirement_id','text_span','answerability','support_label') if k in p}
                                    for p in coverage.get('passages',[])[:32]]}


def criar_tabelas(db) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS eg_nodes (
        id TEXT PRIMARY KEY, owner_id TEXT NOT NULL DEFAULT 'local',
        job_id TEXT NOT NULL DEFAULT '', kind TEXT NOT NULL DEFAULT '',
        dados TEXT NOT NULL DEFAULT '{}', criado_em TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS eg_edges (
        id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id TEXT NOT NULL DEFAULT 'local',
        job_id TEXT NOT NULL DEFAULT '', src TEXT NOT NULL DEFAULT '',
        dst TEXT NOT NULL DEFAULT '', tipo TEXT NOT NULL DEFAULT '',
        metodo TEXT NOT NULL DEFAULT '', nota TEXT NOT NULL DEFAULT '',
        criado_em TEXT NOT NULL,
        UNIQUE (job_id, src, dst, tipo))""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_eg_nodes_job ON eg_nodes(owner_id, job_id, kind)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_eg_edges_job ON eg_edges(owner_id, job_id, tipo)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_eg_edges_dst ON eg_edges(owner_id, dst, tipo)")
    db.commit()


def _nid(*partes: str) -> str:
    return hashlib.sha256("\x00".join(partes).encode()).hexdigest()[:16]


def no_id(kind: str, job_id: str, chave: str) -> str:
    return f"{kind}:{_nid(job_id, chave)}"


def criar_no(db, owner: str, job_id: str, kind: str, chave: str, dados: dict) -> str:
    if kind not in KINDS_NO:
        raise GraphErro("kind inválido", "kind")
    nid = no_id(kind, job_id, chave)
    with db:
        db.execute("INSERT OR IGNORE INTO eg_nodes (id, owner_id, job_id, kind, dados, criado_em)"
                   " VALUES (?,?,?,?,?,?)",
                   (nid, owner, job_id, kind, json.dumps(dados, ensure_ascii=False)[:8000],
                    agora_iso()))
    return nid


def ligar(db, owner: str, job_id: str, src: str, dst: str, tipo: str,
          metodo: str = "", nota: str = "") -> None:
    if tipo not in TIPOS_RELACAO:
        raise GraphErro("relação inválida", "relacao")
    with db:
        db.execute("INSERT OR IGNORE INTO eg_edges (owner_id, job_id, src, dst, tipo, metodo,"
                   " nota, criado_em) VALUES (?,?,?,?,?,?,?,?)",
                   (owner, job_id, src, dst, tipo, metodo[:40], nota[:300], agora_iso()))


def criar_nos_lote(db, owner: str, job_id: str, itens: list) -> list:
    """Insere nós em UMA transação (perf: N commits no Windows custam ms cada)."""
    nids = []
    for kind, chave, dados in itens:
        if kind not in KINDS_NO:
            raise GraphErro("kind inválido", "kind")
        nids.append(no_id(kind, job_id, chave))
    agora = agora_iso()
    with db:
        db.executemany(
            "INSERT OR IGNORE INTO eg_nodes (id, owner_id, job_id, kind, dados, criado_em)"
            " VALUES (?,?,?,?,?,?)",
            [(nid, owner, job_id, kind, json.dumps(dados, ensure_ascii=False)[:8000], agora)
             for nid, (kind, chave, dados) in zip(nids, itens)])
    return nids


def ligar_lote(db, owner: str, job_id: str, arestas: list) -> int:
    """Arestas em UMA transação. Retorna quantas foram enviadas (OR IGNORE)."""
    for src, dst, tipo, metodo, nota in arestas:
        if tipo not in TIPOS_RELACAO:
            raise GraphErro("relação inválida", "relacao")
    agora = agora_iso()
    with db:
        db.executemany(
            "INSERT OR IGNORE INTO eg_edges (owner_id, job_id, src, dst, tipo, metodo,"
            " nota, criado_em) VALUES (?,?,?,?,?,?,?,?)",
            [(owner, job_id, src, dst, tipo, (metodo or "")[:40], (nota or "")[:300], agora)
             for src, dst, tipo, metodo, nota in arestas])
    return len(arestas)


def nos_do_job(db, owner: str, job_id: str, kind: str = "") -> list:
    sql = "SELECT id, kind, dados FROM eg_nodes WHERE owner_id=? AND job_id=?"
    args = [owner, job_id]
    if kind:
        sql += " AND kind=?"
        args.append(kind)
    rows = db.execute(sql + " ORDER BY id", args).fetchall()
    out = []
    for nid, k, dados in rows:
        try:
            out.append({"id": nid, "kind": k, **json.loads(dados or "{}")})
        except (TypeError, ValueError):
            continue
    return out


def arestas_do_job(db, owner: str, job_id: str, tipo: str = "") -> list:
    sql = "SELECT src, dst, tipo, metodo, nota FROM eg_edges WHERE owner_id=? AND job_id=?"
    args = [owner, job_id]
    if tipo:
        sql += " AND tipo=?"
        args.append(tipo)
    return [{"src": r[0], "dst": r[1], "tipo": r[2], "metodo": r[3], "nota": r[4]}
            for r in db.execute(sql + " ORDER BY src, dst", args).fetchall()]


# ── Proveniência ────────────────────────────────────────────────────
def canonical_url(url: str) -> str:
    """URL canônica: host minúsculo, sem tracking, sem barra final boba."""
    try:
        p = urllib.parse.urlsplit((url or "").strip())
    except ValueError:
        return (url or "")[:500]
    host = (p.hostname or "").lower()
    if not host:
        return (url or "")[:500]
    qs = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True)
          if not k.lower().startswith(("utm_", "fbclid", "gclid", "mc_", "igshid"))]
    path = p.path.rstrip("/") or "/"
    out = urllib.parse.urlunsplit((p.scheme.lower(), host, path,
                                   urllib.parse.urlencode(qs), ""))
    return out[:500]


def hash_conteudo(texto: str) -> str:
    norm = re.sub(r"\s+", " ", (texto or "").lower()).strip()
    return hashlib.sha256(norm.encode()).hexdigest()[:16]


def contexto_trecho(texto: str, trecho: str, janela: int = 120) -> str:
    i = (texto or "").find(trecho or "")
    if i < 0 or not trecho:
        return ""
    return texto[max(0, i - janela):i + len(trecho) + janela].strip()[:600]


# ── Claims v2 (texto + condições) ───────────────────────────────────
def _rx_qtd():
    import units as _u
    return re.compile(
        r"(\d{1,3}(?:[.\s]\d{3})*(?:[.,]\d+)?|\d+(?:[.,]\d+)?)\s*"
        r"(" + _u.pattern_unidades() + r")?(?![a-zà-ú])", re.IGNORECASE)


_RX_QTD = _rx_qtd()
_RX_COMP = re.compile(r"\b(mais|menos|maior|menor|melhor|pior|superior|inferior|rápido|lento|"
                      r"eficiente|caro|barato)\b\s+(\w+(?:\s+\w+){0,3}?)\s+(?:que|do que|em relação a|vs\.?|comparado a)\s+"
                      r"([\w\s]{2,40}?)(?:[.,;]|$)", re.IGNORECASE)
_RX_DATA = re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}|janeiro|fevereiro|março|abril|maio|"
                      r"junho|julho|agosto|setembro|outubro|novembro|dezembro)\b", re.IGNORECASE)
# Verbo finito suficiente para saber que o primeiro trecho de um "e" já é
# uma oração (evita separar sujeito composto: "X e Y são mais rápidos").
_RX_VERBO_ORACAO = re.compile(
    r"\b(?:é|e|são|sao|foi|foram|será|sera|está|esta|estão|estao|"
    r"consome|consomem|gasta|gastam|tem|têm|tem|possui|possuem|usa|usam|"
    r"oferece|oferecem|entrega|entregam|apresenta|apresentam|"
    r"custa|custam|chega|chegam|atinge|atingem|fica|ficam|"
    r"ganha|ganham|perde|perdem|roda|rodam|funciona|funcionam)\b", re.IGNORECASE)


def _tem_verbo_oracao(texto: str) -> bool:
    return bool(_RX_VERBO_ORACAO.search(texto or ""))


def _num_norm(bruto: str):
    b = bruto.replace(" ", "")
    if "." in b and "," in b:
        b = b.replace(".", "").replace(",", ".")
    elif "," in b:
        b = b.replace(",", ".")
    try:
        return float(b)
    except (TypeError, ValueError):
        return None


def extrair_quantidades(texto: str) -> list:
    out = []
    for m in _RX_QTD.finditer(texto or ""):
        v = _num_norm(m.group(1))
        if v is None or not (-1e12 < v < 1e12):
            continue
        out.append({"valor": v, "unidade": (m.group(2) or "").strip()[:12]})
    return out[:8]


def extrair_afirmacoes_v2(texto: str, teto: int = 12, minimo: int = 40) -> list:
    """Divide em afirmações + condições (comparado, métrica, valor, data).

    Sem LLM: condições ausentes → marcadas como desconhecidas e o estado
    factual fica NÃO VERIFICADO (nunca presumido). `minimo` baixa o corte de
    tamanho para frases comparativas curtas ("tuplas são mais rápidas que listas").
    """
    out = []
    for s in re.split(r"(?<=[.!?])\s+", texto or ""):
        s = s.strip()
        if len(s) < minimo or len(s) > 400:
            continue
        if not (re.search(r"\d", s) or re.search(r"\b[A-ZÀ-Ú][a-zà-ú]{3,}\b", s)
                or _RX_COMP.search(s)):
            continue
        grupos, atual = [], ""
        # Em frase comparativa, o "e" só separa orações se o primeiro trecho
        # já tiver verbo. Assim "X consome menos e é mais rápido que Y" vira
        # duas afirmações, mas "X e Y são mais rápidos que Z" preserva o
        # sujeito composto e a comparação inteira.
        pedacos = re.split(r"\s+e\s+|\s+além disso,?\s+|;\s*", s)
        if _RX_COMP.search(s) and len(pedacos) > 1 and \
                not _tem_verbo_oracao(pedacos[0]):
            pedacos = [s]
        for parte in pedacos:
            parte = parte.strip()
            if not parte:
                continue
            if atual and len(parte) < minimo:
                atual = atual + " e " + parte
            else:
                if atual:
                    grupos.append(atual)
                atual = parte
        if atual:
            grupos.append(atual)
        for parte in grupos:
            if len(parte) < minimo:
                continue
            cond = {"comparado_a": "", "metrica": "", "quantidades": extrair_quantidades(parte),
                    "datas": _RX_DATA.findall(parte)[:3]}
            m = _RX_COMP.search(parte)
            if m:
                cond["metrica"] = (m.group(1) + " " + m.group(2)).strip()[:80]
                cond["comparado_a"] = m.group(3).strip()[:80]
            if parte not in [o["texto"] for o in out]:
                out.append({"texto": parte, "condicoes": cond})
            if len(out) >= teto:
                return out
    return out


def detectar_comparacao(texto: str) -> dict | None:
    """Decompõe "X é mais rápido que Y" em sujeito/métrica/comparado.

    Usada para rotular e neutralizar comparações sem evidência; não decide
    sozinha se a frase é verdadeira (isso é `verificar_claim`).
    """
    m = _RX_COMP.search(texto or "")
    if not m:
        return None
    sujeito = (texto or "")[:m.start()].strip(" ,;:-")
    sujeito = re.sub(r"\s+(?:é|e|são|sao|foi|foram|seria|está|esta)\s*$", "",
                     sujeito, flags=re.IGNORECASE).strip(" ,;:-")
    return {"termo": m.group(1).lower(), "metrica": (m.group(1) + " " + m.group(2)).strip()[:80],
            "comparado_a": (m.group(3) or "").strip()[:80], "sujeito": sujeito[:120]}


# ── Independência ───────────────────────────────────────────────────
def _shingles(texto: str, n: int = 5) -> set:
    toks = re.findall(r"[a-zà-ú0-9]{2,}", (texto or "").lower())
    return {" ".join(toks[i:i + n]) for i in range(max(0, len(toks) - n + 1))} or set()


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return round(len(a & b) / len(a | b), 3)


def citacoes_raras_em_comum(a: str, b: str, minimo: int = 60) -> list:
    """Trechos literais longos compartilhados (sinal de republicação)."""
    out = []
    for m in re.finditer(r'"([^"]{40,})"', (a or "") + "\n" + (b or "")):
        frag = m.group(1)
        if frag in (a or "") and frag in (b or "") and len(frag) >= minimo:
            out.append(frag[:120])
    return out[:3]


def analisar_independencia(doc_a: dict, doc_b: dict) -> dict:
    """Domínio diferente NÃO prova independência; conclusão igual NÃO prova
    dependência. Retorna laudo com evidências estruturais."""
    url_a = canonical_url(doc_a.get("url", ""))
    url_b = canonical_url(doc_b.get("url", ""))
    mesmo_doc = url_a == url_b and bool(url_a)
    hash_a, hash_b = hash_conteudo(doc_a.get("texto", "")), hash_conteudo(doc_b.get("texto", ""))
    sim = jaccard(_shingles(doc_a.get("texto", "")), _shingles(doc_b.get("texto", "")))
    citadas = citacoes_raras_em_comum(doc_a.get("texto", ""), doc_b.get("texto", ""))
    dom_a = (urllib.parse.urlsplit(url_a).hostname or "") if url_a else ""
    dom_b = (urllib.parse.urlsplit(url_b).hostname or "") if url_b else ""
    if mesmo_doc or (doc_a.get('texto','').strip() and doc_b.get('texto','').strip() and hash_a == hash_b):
        return {"relacao": "DUPLICATES", "confianca": "estrutural",
                "motivo": "mesmo documento/conteúdo idêntico"}
    if sim >= 0.6 or citadas:
        return {"relacao": "DERIVED_FROM", "confianca": "estrutural",
                "motivo": f"similaridade {sim}" + (" + citação literal" if citadas else "")}
    if dom_a and dom_a == dom_b:
        return {"relacao": "MENTIONS", "confianca": "estrutural",
                "motivo": "mesmo domínio, textos distintos: relação desconhecida"}
    return {"relacao": "MENTIONS", "confianca": "estrutural",
            "motivo": "domínios distintos sem cópia detectada: independência NÃO presumida"}


# ── Contradições: investigação por dimensão ─────────────────────────
UNIDADES_CONVERSIVEIS = {"W", "kW", "km", "m", "kg", "g", "C", "F", "%"}


def _mesma_medida(qa: dict, qb: dict) -> bool:
    ua, ub = (qa.get("unidade") or ""), (qb.get("unidade") or "")
    if ua == ub:
        return True  # inclui ambas vazias: sem unidade declarada, não é divergência de medida
    import units as _u
    return _u.compativeis({"unidade": ua}, {"unidade": ub})


def investigar_divergencia(claim_a: dict, claim_b: dict, fonte_a: str, fonte_b: str) -> dict:
    """Classifica a dimensão da divergência; nunca inventa reconciliação."""
    qa = (claim_a.get("condicoes", {}) or {}).get("quantidades", [])
    qb = (claim_b.get("condicoes", {}) or {}).get("quantidades", [])
    da = (claim_a.get("condicoes", {}) or {}).get("datas", [])
    db = (claim_b.get("condicoes", {}) or {}).get("datas", [])
    if qa and qb and not _mesma_medida(qa[0], qb[0]):
        return {"tipo": "unidade_ou_metrica", "status": "em_aberto",
                "explicacao": f"Medidas distintas ({qa[0].get('unidade')} × {qb[0].get('unidade')}): "
                              "podem não falar da mesma coisa.",
                "follow_up": [f"{qa[0].get('unidade')} vs {qb[0].get('unidade')} metodologia medição"]}
    if qa and qb:
        import units as _u
        qa0, qb0 = qa[0], qb[0]
        ua, ub = (qa0.get("unidade") or ""), (qb0.get("unidade") or "")
        qa_n = {"valor": qa0.get("valor"), "unidade": ua}
        qb_n = {"valor": qb0.get("valor"), "unidade": ub}
        converteis = _u.compativeis(qa_n, qb_n)  # mesma dimensão, ambas conhecidas
        if ua == ub or converteis:
            if converteis:
                divergentes = not _u.iguais(qa_n, qb_n)  # 65 W == 0,065 kW: sem falsa divergência
            else:
                divergentes = qa0.get("valor") != qb0.get("valor")  # legado (unidade vazia/igual)
            if divergentes:
                if ua == ub:
                    explicacao = (f"Mesma unidade, valores distintos ({qa0['valor']} × {qb0['valor']}). "
                                  "Verificar metodologia, data e condições.")
                else:
                    explicacao = (f"Mesma dimensão, valores distintos ({qa0['valor']} {ua} × "
                                  f"{qb0['valor']} {ub}). "
                                  "Verificar metodologia, data e condições.")
                return {"tipo": "valor_divergente", "status": "em_aberto",
                        "explicacao": explicacao,
                        "follow_up": ["metodologia medição", "data atualização dado"]}
    if da != db and (da or db):
        return {"tipo": "data_divergente", "status": "em_aberto",
                "explicacao": "Datas distintas: a mais recente pode atualizar a anterior.",
                "follow_up": ["dado atualizado"]}
    ca, cb = (claim_a.get("condicoes", {}) or {}).get("comparado_a", ""), \
        (claim_b.get("condicoes", {}) or {}).get("comparado_a", "")
    if ca and cb and ca.lower() != cb.lower():
        return {"tipo": "contexto_divergente", "status": "em_aberto",
                "explicacao": f"Comparados distintos ('{ca}' × '{cb}'): conclusões podem coexistir.",
                "follow_up": []}
    return {"tipo": "inconclusivo", "status": "em_aberto",
            "explicacao": "Divergência sem dimensão identificável; requer leitura humana.",
            "follow_up": []}


# ── Verificação 2.0 ─────────────────────────────────────────────────
def _tokens_conteudo(texto: str) -> set:
    stop = {"para", "como", "mais", "sobre", "entre", "isso", "esse", "esta",
            "este", "qual", "quais", "onde", "quando", "porque", "pode", "ser",
            "são", "com", "dos", "das", "uma", "que", "não", "sim", "foi",
            "sua", "seu", "por", "nos", "nas", "dos"}
    return {t for t in re.findall(r"[a-zà-ú]{4,}", (texto or "").lower()) if t not in stop}


def verificar_claim(claim: dict, evidencias: list) -> dict:
    """SUPPORTS exige: quantidade exata (unidade compatível) + entidade/
    propriedade em comum + datas e base de comparação compatíveis.

    Número igual sozinho NÃO sustenta (ex.: 'TDP 65 W' ≠ 'consumo máximo').
    """
    import units as _u
    # Fonte apenas encontrada (sem leitura) não sustenta afirmação: o trecho
    # do índice pode estar fora de contexto. `lida` ausente = contrato antigo,
    # preservado; `lida=False` é explícito e só serve para localizar a fonte.
    evidencias = [e for e in (evidencias or []) if e.get("lida") is not False
                  and e.get('texto_lido') is not False and e.get('content_scope') not in ('feed_metadata','metadata_only')]
    cond = claim.get("condicoes", {}) or {}
    cqs = cond.get("quantidades", [])
    toks_claim = _tokens_conteudo(claim["texto"])
    for e in evidencias:
        trecho = e.get("trecho", "") or ""
        eqs = extrair_quantidades(trecho)
        for q in cqs:
            for x in eqs:
                if not _u.compativeis({"unidade": q.get("unidade", "")},
                                      {"unidade": x.get("unidade", "")}):
                    continue
                if not _u.iguais({"valor": q.get("valor"), "unidade": q.get("unidade", "")},
                                 {"valor": x.get("valor"), "unidade": x.get("unidade", "")}):
                    continue
                if len(toks_claim & _tokens_conteudo(trecho)) < 2:
                    continue  # mesma medida, entidade/propriedade distinta
                if not _datas_compativeis(cond.get("datas", []), trecho):
                    continue
                if not _comparado_compativel(cond.get("comparado_a", ""), trecho):
                    continue
                return {"estado": "SUPPORTED", "metodo": "quantidade+contexto",
                        "evidencia": e.get("id", ""), "cobertura_lexica": 1.0,
                        "condicoes_ausentes": _faltas({"texto": claim["texto"],
                                                       "condicoes": cond})}
    neg = any("não " in (e.get("trecho", "") or "").lower() or "nunca " in
              (e.get("trecho", "") or "").lower() for e in evidencias or [])
    if evidencias and not neg:
        from research_agents import cobertura as _cob
        cov = _cob(claim["texto"], [e.get("trecho", "") for e in evidencias])
        if cov >= 0.25:
            return {"estado": "PARTIALLY_SUPPORTED", "metodo": "lexico-provisorio",
                    "evidencia": "", "cobertura_lexica": cov,
                    "condicoes_ausentes": _faltas(claim)}
    if not evidencias:
        return {"estado": "INSUFFICIENT_EVIDENCE", "metodo": "sem-evidencia",
                "evidencia": "", "cobertura_lexica": 0.0}
    return {"estado": "UNVERIFIED", "metodo": "lexico-provisorio",
            "evidencia": "", "cobertura_lexica": 0.0,
            "condicoes_ausentes": _faltas(claim)}


def _datas_compativeis(datas_claim: list, trecho: str) -> bool:
    """Data na afirmação exige a mesma data no trecho; sem data, sem exigência."""
    if not datas_claim:
        return True
    t = (trecho or "").lower()
    return any(str(d).lower() in t for d in datas_claim)


def _comparado_compativel(comparado: str, trecho: str) -> bool:
    """Base de comparação citada exige menção no trecho."""
    toks = {t for t in re.findall(r"[a-zà-ú]{4,}", (comparado or "").lower())}
    if not toks:
        return True
    return len(toks & _tokens_conteudo(trecho)) >= 1


def _faltas(claim: dict) -> list:
    cond = claim.get("condicoes", {}) or {}
    faltas = []
    if not cond.get("comparado_a") and re.search(r"(?i)\b(mais|menos|melhor|pior)\b", claim["texto"]):
        faltas.append("comparado ausente")
    if cond.get("quantidades") and not cond.get("datas"):
        faltas.append("data ausente p/ quantidade")
    return faltas


# ── Classificação explícita das afirmações (V5.7.3) ──────────────────
CLASSIFICACOES_AFIRMACAO = ("FACT", "DERIVED_FROM_DATA", "ESTIMATE",
                            "HYPOTHESIS", "UNVERIFIED")
_RX_ESTIMATIVA = re.compile(
    r"(?i)\b(?:cerca\s+de|aproximad[ao]s?|em\s+torno\s+de|estimad[ao]|"
    r"estimo|ordem\s+de\s+grandeza|talvez\s+uns?)\b")
_RX_HIPOTESE = re.compile(
    r"(?i)\b(?:pode\s+ser|talvez|possivelmente|provavelmente|hip[óo]tese|"
    r"suponho|acredito\s+que|imagino\s+que|é\s+poss[íi]vel\s+que)\b")


def classificar_afirmacoes(texto: str, evidencias: list,
                           teto: int = 12, minimo: int = 40) -> list:
    """Classifica cada afirmação: FACT, DERIVED_FROM_DATA, ESTIMATE,
    HYPOTHESIS ou UNVERIFIED — sempre a partir do veredito real, nunca de
    presunção. Comparações sem base de comparação ficam UNVERIFIED."""
    out = []
    for claim in extrair_afirmacoes_v2(texto or "", teto=teto, minimo=minimo):
        v = verificar_claim(claim, evidencias or [])
        estado = v.get("estado", "UNVERIFIED")
        trecho = claim.get("texto", "")
        if estado == "SUPPORTED":
            classe = "FACT"
        elif estado == "PARTIALLY_SUPPORTED":
            classe = "DERIVED_FROM_DATA"
        elif _RX_ESTIMATIVA.search(trecho):
            classe = "ESTIMATE"
        elif _RX_HIPOTESE.search(trecho):
            classe = "HYPOTHESIS"
        else:
            classe = "UNVERIFIED"
        out.append({"texto": trecho, "classificacao": classe, "veredito": estado,
                    "comparacao": detectar_comparacao(trecho),
                    "cobertura_lexica": v.get("cobertura_lexica", 0.0),
                    "condicoes_ausentes": v.get("condicoes_ausentes", []),
                    "evidencia": v.get("evidencia", "")})
    return out


# ── Auditor 2.0 ─────────────────────────────────────────────────────
SUPERLATIVOS = ("sempre", "nunca", "todos", "todas", "garante", "garantido",
                "com certeza", "impossível", "ninguém", "jamais")


def _ano_de_fonte(ev: dict):
    """Ano declarado na fonte (publicado_em ou year); None quando desconhecido."""
    texto = str((ev or {}).get("publicado_em") or (ev or {}).get("year") or "")
    m = re.search(r"(?:19|20)\d{2}", texto)
    return int(m.group(0)) if m else None


def fonte_desatualizada(ev: dict, ano_ref: int = None, idade_max_anos: int = 2) -> bool:
    """True só com data conhecida E antiga; sem data declarada, NÃO acusa."""
    ano = _ano_de_fonte(ev)
    if ano is None:
        return False
    ref = int(ano_ref) if ano_ref else datetime.now(timezone.utc).year
    return (ref - ano) > int(idade_max_anos)


def auditar_resposta(texto: str, claims: list, vereditos: dict, fontes: list) -> dict:
    """Relatório de auditoria: afirmações × evidências × generalizações × lacunas."""
    ids = {f.get("id") for f in fontes or []}
    citadas = {m.group(0) for m in re.finditer(r"\[(?:E|S)\d+\]", texto or "")}
    fantasmas = sorted(c for c in citadas if c.strip("[]") not in ids)
    generalizacoes = []
    for c in claims or []:
        t = (c.get("texto") or "").lower()
        if any(s in t for s in SUPERLATIVOS):
            v = vereditos.get(c.get("texto", ""), {})
            if v.get("estado") != "SUPPORTED":
                generalizacoes.append(c["texto"][:140])
    sem_evidencia = [c["texto"][:140] for c in claims or []
                     if vereditos.get(c.get("texto", ""), {}).get("estado")
                     in ("UNVERIFIED", "INSUFFICIENT_EVIDENCE")]
    desatualizadas = [f.get("id", "") for f in fontes or []
                      if f.get("id") and fonte_desatualizada(f)]
    return {"afirmacoes": len(claims or []),
            "citacoes_fantasma": fantasmas,
            "generalizacoes_excessivas": generalizacoes,
            "sem_evidencia_suficiente": sem_evidencia,
            "fontes_desatualizadas": sorted(desatualizadas),
            "etapa_semantica": "BLOQUEADA",
            "ok": not fantasmas and not sem_evidencia}


# ── Memória do grafo (perguntas sobre a investigação) ──────────────
def _no_claim_por_texto(db, owner: str, job_id: str, texto: str):
    for n in nos_do_job(db, owner, job_id, "claim"):
        if n.get("texto", "") == texto:
            return n
    return None


def fontes_que_sustentam(db, owner: str, job_id: str, claim_texto: str = "") -> list:
    """Evidências ligadas por SUPPORTS/PARTIALLY à conclusão (ou à última)."""
    claims = nos_do_job(db, owner, job_id, "claim")
    alvos = [c for c in claims if not claim_texto or c.get("texto", "") == claim_texto]
    if not alvos and claims:
        alvos = claims[:1]
    out = []
    for c in alvos:
        for e in arestas_do_job(db, owner, job_id):
            if e["dst"] == c["id"] and e["tipo"] in ("SUPPORTS", "PARTIALLY_SUPPORTS"):
                out.append({"claim": c.get("texto", "")[:200], "evidence_node": e["src"],
                            "tipo": e["tipo"], "metodo": e["metodo"]})
    return out


def contradicoes_do_job(db, owner: str, job_id: str) -> list:
    return [e for e in arestas_do_job(db, owner, job_id) if e["tipo"] == "CONTRADICTS"]

def estudos_originais(db, owner: str, job_id: str) -> list:
    """Documentos sem DERIVED_FROM/DUPLICATES entrando (raízes)."""
    derivados = {e["dst"] for e in arestas_do_job(db, owner, job_id)
                 if e["tipo"] in ("DERIVED_FROM", "DUPLICATES")}
    return [n for n in nos_do_job(db, owner, job_id, "document") if n["id"] not in derivados]


def diff_pesquisas(db, owner: str, job_nova: str, job_antiga: str) -> dict:
    """O que mudou: por URL canônica, hash do documento."""
    def mapa(jid):
        m = {}
        for n in nos_do_job(db, owner, jid, "document"):
            url = canonical_url(n.get("url", ""))
            if url:
                m[url] = n.get("hash", "")
        return m
    nova, antiga = mapa(job_nova), mapa(job_antiga)
    return {"novas": sorted(set(nova) - set(antiga)),
            "removidas": sorted(set(antiga) - set(nova)),
            "alteradas": sorted(u for u in set(nova) & set(antiga) if nova[u] != antiga[u])}


def rank_evidencias(db, owner: str, job_id: str, consulta: str, limite: int = 10) -> list:
    """Baseline lexical honesto: overlap de tokens consulta×(título+trecho).

    Documentado como baseline, não como ranqueamento semântico.
    """
    import sqlite3
    toks_q = {t for t in __import__("re").findall(r"[a-zà-ú0-9]{3,}", (consulta or "").lower())}
    try:
        rows = db.execute("SELECT id, titulo, url, trecho FROM evidence "
                          "WHERE job_id=? AND owner_id=?", (job_id, owner)).fetchall()
    except sqlite3.Error:
        return []
    scored = []
    for eid, titulo, url, trecho in rows:
        toks = {t for t in __import__("re").findall(
            r"[a-zà-ú0-9]{3,}", f"{titulo or ''} {trecho or ''}".lower())}
        inter = toks_q & toks if toks_q else set()
        scored.append((len(inter), eid, titulo, url))
    scored.sort(key=lambda s: (-s[0], s[1]))
    return [{"id": eid, "titulo": titulo, "url": url, "overlap": n}
            for n, eid, titulo, url in scored[:max(1, min(int(limite or 10), 50))]]
