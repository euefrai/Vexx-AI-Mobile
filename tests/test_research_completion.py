"""Completion regressions; controlled tests do not certify real model quality."""
import copy
import json
import time
import zlib

import pytest
import evidence_graph as eg
import python_docs_discovery as docs
import research
import research_synthesis as synthesis
import research_agents as agents

QUERY = 'Compare asyncio.TaskGroup e asyncio.gather: cancelamento e exceções, com documentação oficial.'
URL = 'https://docs.python.org/3/library/asyncio-task.html'


def test_nested_method_does_not_steal_its_parent_api_scope():
    html = ('<main><h1>Reference</h1><p>'+'Introduction. '*900+'</p>'
            '<dl><dt>class asyncio.TaskGroup</dt><dd>'
            '<dl><dt>cancel()</dt><dd><p>Pending operations are cancelled.</p></dd></dl>'
            '<p>Exceptions are raised after the tasks finish.</p></dd></dl>'
            '<dl><dt>awaitable asyncio.gather(*aws)</dt><dd><p>Run tasks concurrently.</p>'
            '<p>If gather() is cancelled, submitted tasks are cancelled.</p></dd></dl></main>')
    doc = research.extrair_artigo(html, URL, QUERY, teto=1800)
    rows = doc['answer_passages']
    method = next(p for p in rows if 'Pending operations are cancelled.' in p['text'])
    parent = next(p for p in rows if 'Exceptions are raised' in p['text'])
    assert method['section_path'][-1]['text'] == 'cancel()'
    assert parent['section_path'][-1]['text'] == 'class asyncio.TaskGroup'
    assert parent['section_path'][-1]['level'] == 7
    assert len(doc['texto']) <= 1800


@pytest.mark.parametrize('ambiguous',[False,True])
def test_section_scope_requires_one_formal_api_and_stays_in_that_section(ambiguous):
    extra='<dl><dt>class asyncio.Other</dt><dd>Another API.</dd></dl>' if ambiguous else ''
    html=('<main><h1>Reference</h1><p>'+'Introduction. '*900+'</p><section><h2>Task groups</h2>'
          '<dl><dt>class asyncio.TaskGroup</dt><dd>Structured task group.</dd></dl>'+extra+
          '<p>Exceptions are raised after the tasks finish.</p></section>'
          '<section><h2>Unrelated section</h2><p>Other exceptions are raised here.</p></section></main>')
    doc=research.extrair_artigo(html,URL,QUERY,teto=1800)
    target=next(p for p in doc['answer_passages'] if 'Exceptions are raised after' in p['text'])
    scoped=[h for h in target['section_path'] if h['level']>=7]
    assert bool(scoped) is not ambiguous
    unrelated=next(p for p in doc['answer_passages'] if 'Other exceptions' in p['text'])
    assert not any(h['level']>=7 for h in unrelated['section_path'])


def authority(monkeypatch):
    body = ('asyncio.TaskGroup py:class 1 library/asyncio-task.html#$ -\n'
            'asyncio.gather py:function 1 library/asyncio-task.html#$ -\n')
    blob = (b'# Sphinx inventory version 2\n# Project: Python\n# Version: 3.14\n'
            b'# The remainder of this file is compressed using zlib.\n'+zlib.compress(body.encode()))
    monkeypatch.setenv('JULIA_PYTHON_DOCS_DISCOVERY','1')
    monkeypatch.setattr(docs,'_CACHE',(time.monotonic()+60,docs.parse_inventory(blob)))
    record={'texto':'asyncio.TaskGroup and asyncio.gather reference.', 'texto_lido':True}
    proof=docs.read_authority(QUERY,URL,record)
    assert proof
    return {**record,'source_authority':proof,'url':URL,'content_scope':'page_text'}


def test_authority_requires_inventory_bindings_and_actual_read(monkeypatch):
    source=authority(monkeypatch)
    assert docs.has_read_authority(source,QUERY)
    for updates in ({'texto_lido':False},{'url':'https://example.org/python'},
                    {'source_authority':{'verified':True}}, {'content_scope':'metadata_only'}):
        assert not docs.has_read_authority({**source,**updates},QUERY)
    assert not docs.read_authority(QUERY,URL,{'texto':'generic Python text','texto_lido':True})
    changed=copy.deepcopy(source);changed['source_authority']['api_names']=['asyncio.TaskGroup']
    assert not docs.has_read_authority(changed,QUERY)
    for invalid in (None,{},[{}],True):
        changed=copy.deepcopy(source);changed['source_authority']['api_names']=invalid
        assert not docs.has_read_authority(changed,QUERY)


def test_authority_cannot_certify_other_sources_or_answer_content(monkeypatch):
    source=authority(monkeypatch)
    coverage=eg.requirement_coverage(QUERY,[source])
    condition=next(r for r in coverage['requirements'] if r['attribute']=='source_authority')
    assert condition['state']=='SUPPORTED'
    assert not coverage['complete']  # Publisher identity is not an answer.
    other={**source,'url':'https://example.org/unrelated','source_authority':{}}
    coverage=eg.requirement_coverage(QUERY,[source,other])
    assert next(r for r in coverage['requirements'] if r['attribute']=='source_authority')['state']!='SUPPORTED'


def test_review_has_a_bounded_budget_after_a_slow_valid_writer(monkeypatch):
    clock=[100.0];monkeypatch.setattr(synthesis.time,'monotonic',lambda:clock[0])
    text='The tool returns a list of values in the original order.'
    source={'id':'E1','evidence_id':'ev','excerpt':text,'scope':'page_text','url':'https://example.org/api'}
    calls=[]
    def writer(messages,timeout):
        calls.append('write');assert 18<=timeout<=25;clock[0]+=18
        return json.dumps({'points':[{'text':text,'evidence':[{'id':'E1','quote':text}]}]})
    def reviewer(messages,timeout):
        calls.append('review');assert 18<=timeout<=25;clock[0]+=18
        return '{"reviews":[{"paragraph":0,"state":"SUPPORTED","reason":"none"}]}'
    result=synthesis.generate('Explain the returned data', [source],[],writer,timeout=45,verify_fn=reviewer)
    assert result['llm'] and calls==['write','review'] and clock[0]==136


def test_empty_writer_output_is_distinct_from_provider_or_format_failure():
    with pytest.raises(synthesis.ModelOutputError) as error:
        synthesis.generate('Explain data',[{'id':'E1','evidence_id':'ev','excerpt':'A valid literal source excerpt.'}],[],lambda *_:'{"points":[]}')
    assert synthesis.failure_detail(error.value)=='no_supported_points'


def test_api_default_survives_competing_exception_edge_cases():
    default='If return_exceptions is False (default), the first raised exception is propagated.'
    html=('<main><h1>Reference</h1><p>'+'Introduction. '*900+'</p><section>'
          '<h2>Concurrency</h2><dl><dt>awaitable asyncio.gather(*aws, return_exceptions=False)</dt><dd>'+
          ''.join(f'<p>Exception case {i}: exceptions are raised when this edge case is reached.</p>' for i in range(16))+
          '<p>'+default+'</p></dd></dl></section></main>')
    doc=research.extrair_artigo(html,URL,QUERY,teto=1800)
    assert default in doc['texto'] and len(doc['texto'])<=1800


def test_large_evidence_metadata_roundtrips_without_losing_passages_or_offsets():
    text='A literal passage preserving an exact claim and its conditions. '*7
    heading={'level':7,'text':'awaitable asyncio.gather(*aws)',
             'source_span':{'start':0,'end':29,'scope':'normalized_available_extraction','sha256':'a'*64}}
    passages=[{'id':f'P-{i}','text':f'{i}: '+text,'source_url':URL,'source_id':URL,'document_id':'D-'+'b'*24,
               'source_role':'PROSE','reason':'bounded_explicit_entity_attribute_relation',
               'section_id':'gather','section_path':[heading],
               'source_span':{'start':100+i*500,'end':550+i*500,'scope':'normalized_available_extraction','sha256':'a'*64},
               'text_span':{'start':i*500,'end':450+i*500,'scope':'returned_extracted_text'}} for i in range(8)]
    original={'url':URL,'answer_passages':passages,'scientific_sections':[
        {'title':f'Section {i}','text':p['text'],'kind':'body','page':None,'source_url':URL,'extraction_scope':'page_text'}
        for i,p in enumerate(passages)]}
    assert len(json.dumps(original,ensure_ascii=False))>12000
    encoded=agents._encode_evidence_metadata(original)
    restored=agents._restore_evidence_metadata(json.loads(encoded))
    assert len(encoded)<=12000 and restored==original
    assert len(restored['answer_passages'])==8


@pytest.mark.parametrize('answers',[[],[{'requirement_id':'invented','answer':'not published'}]])
def test_nonpublishing_review_can_omit_empty_answers_but_not_assert_coverage(answers):
    points=[{'text':'A statement that is not fully supported.','evidence':[{'id':'E1','quote':'A literal source sentence.'}]}]
    sources=[{'id':'E1','evidence_id':'ev','excerpt':'A literal source sentence.'}]
    def reviewer(*_):
        return json.dumps({'reviews':[{'paragraph':0,'state':'PARTIAL','reason':'insufficient','answers':answers}]})
    if answers:
        with pytest.raises(ValueError,match='invalid support review'):
            synthesis.check_support(points,sources,reviewer,10,requirements=[])
    else:
        result=synthesis.check_support(points,sources,reviewer,10,requirements=[])
        assert result[0]['state']=='PARTIAL' and 'answers' not in result[0]


@pytest.mark.parametrize('failure',[None,'short_names','authority','scope','answers','version','cancellation_only'])
def test_only_reviewed_scoped_primary_apis_resolve_partial_subjects(monkeypatch,tmp_path,failure):
    import query_intelligence as qi
    import pc_agent
    source=authority(monkeypatch)
    objective=QUERY+(' Python 3.11' if failure=='version' else '')
    quotes=['Pending tasks are cancelled when the caller cancels the operation.',
            'An exception is raised after all tasks have finished.',
            'Submitted tasks are cancelled when the operation is cancelled.',
            'Exceptions are aggregated into a result list when the option is enabled.']
    claims=['asyncio.TaskGroup cancels pending tasks when the caller cancels the operation.',
            'asyncio.TaskGroup raises an exception after all tasks have finished.',
            'asyncio.gather cancels submitted tasks when the operation is cancelled.',
            'asyncio.gather aggregates exceptions into a result list when the option is enabled.']
    names=['asyncio.TaskGroup']*2+['asyncio.gather']*2
    if failure=='short_names':claims=[text.replace('asyncio.','') for text in claims]
    facets=['cancellation','exceptions']*2
    excerpt='';ranges=[]
    for i,quote in enumerate(quotes):
        if excerpt:excerpt+='\n\n'
        start=len(excerpt);excerpt+=quote
        signature='class '+names[i] if i<2 else 'awaitable '+names[i]+'(*aws)'
        ranges.append({'id':f'P-{i}','start':start,'end':len(excerpt),'element_type':'p',
            'source_span':{'start':100+i*100,'end':190+i*100,'sha256':'a'*64},
            'section_path':[{'level':7,'text':signature,'source_span':{
                'start':0,'end':len(signature),'sha256':'a'*64}}]})
    offered={'id':'E1','evidence_id':'ev','url':URL,'title':'Asyncio reference',
             'scope':'page_text','excerpt':excerpt,'passage_ranges':ranges,
             'source_authority':source['source_authority']}
    if failure=='authority':offered.pop('source_authority')
    if failure=='scope':
        for p in offered['passage_ranges']:p['section_path'][-1]['source_span']['sha256']='invalid'
    selected=[0,2] if failure=='cancellation_only' else list(range(4))
    def writer(*_):
        return json.dumps({'points':[{'text':claims[i],'evidence':[{'id':'E1','quote':quotes[i]}]} for i in selected]})
    writer.semantic_coverage=True
    def reviewer(messages,timeout):
        payload=json.loads(messages[-1]['content'])
        ids={(r['entity'],r['attribute']):r['id'] for r in payload['requirements']}
        return json.dumps({'reviews':[{'paragraph':index,'state':'SUPPORTED','reason':'none','answers':[] if failure=='answers' else [
            {'requirement_id':ids[(names[i],facet)],'answer':claims[i]}
            for facet in (['cancellation','exceptions'] if failure=='cancellation_only' else [facets[i]])]}
            for index,i in enumerate(selected)]})
    result=synthesis.generate(objective,[offered],[],writer,verify_fn=reviewer)
    assert result['llm']
    assert result['answer_coverage']['complete'] is (failure in (None,'short_names'))
    if failure in (None,'short_names'):
        assert all(r.get('support_method')=='reviewed_scoped_primary_api'
                   for r in result['answer_coverage']['requirements'] if r['type']=='explicit_attribute')
        db=pc_agent.open_db(tmp_path/'completion.sqlite')
        try:
            job=agents.criar_job(db,'qa',objective);job['sintese']=result
            job['pendencias']=['Preliminary lexical gap']
            evidence={**source,'id':'ev','trecho':excerpt,'answer_passages':[
                {**p,'text':excerpt[p['start']:p['end']],'text_span':{'start':p['start'],'end':p['end']}}
                for p in ranges]}
            outcome=agents._completion_outcome(job,[evidence],['Preliminary lexical gap'],True)
            assert outcome['state']=='complete' and not outcome['unresolved_fronts']
            assert job['usados']['answer_coverage']['complete']
        finally:db.close()


def test_inline_code_identifiers_are_plain_text_without_accepting_arbitrary_markup():
    plain='asyncio.gather returns a list of results.'
    source={'id':'E1','evidence_id':'ev','excerpt':plain,'scope':'page_text','url':URL}
    writer=lambda *_:json.dumps({'points':[{'text':'`asyncio.gather` returns a list of results.',
                                           'evidence':[{'id':'E1','quote':plain}]}]})
    reviewer=lambda *_:'{"reviews":[{"paragraph":0,"state":"SUPPORTED","reason":"none"}]}'
    result=synthesis.generate('Explain the result',[source],[],writer,verify_fn=reviewer)
    assert '`' not in result['texto'] and 'inline_code_identifiers' in result['format_normalization']
    with pytest.raises(ValueError,match='invalid paragraph'):
        synthesis.generate('Explain the result',[source],[],lambda *_:json.dumps({'points':[
            {'text':'<script>arbitrary code</script>','evidence':[{'id':'E1','quote':plain}]}]}),verify_fn=reviewer)


def test_quote_catalog_keeps_verified_api_subject_separate_from_literal_quote():
    quote='Exceptions are propagated to the calling task.'
    signature='awaitable asyncio.gather(*aws)'
    span={'start':0,'end':len(quote),'source_span':{'start':100,'end':160,'sha256':'a'*64},
          'section_path':[{'level':7,'text':signature,'source_span':{'start':0,'end':len(signature),'sha256':'a'*64}}]}
    source={'excerpt':quote,'passage_ranges':[span]}
    options=synthesis.quote_options(source)
    assert options[0]['text']==quote and options[0]['api_signature']==signature
    span['section_path'][0]['source_span']['sha256']='invalid'
    assert 'api_signature' not in synthesis.quote_options(source)[0]


def test_long_passage_does_not_crowd_out_other_read_api_aspects():
    claims=['asyncio.TaskGroup cancels pending tasks when one task fails.',
            'asyncio.TaskGroup raises an ExceptionGroup after all tasks finish.',
            'asyncio.gather cancels pending tasks when the operation is cancelled.',
            'asyncio.gather propagates the first raised exception to its caller.']
    paragraphs=[claims[0]+' '+('Additional documented context about task scheduling. '*29)]+claims[1:]
    text='';passages=[]
    for i,p in enumerate(paragraphs):
        if text:text+='\n\n'
        start=len(text);text+=p
        passages.append({'id':f'P-{i}','text':p,'text_span':{'start':start,'end':len(text)}})
    evidence={'id':'ev','titulo':'Asyncio reference','url':URL,'dominio':'docs.python.org',
              'trecho':claims[0],'texto':text,'texto_lido':True,'access_state':'read',
              'content_scope':'page_text','answer_passages':passages}
    _,offered=agents._synthesis_context(QUERY,[evidence],{'ev':'E1'})
    assert len(offered[0]['excerpt'])<=1800
    assert all(c in offered[0]['excerpt'] for c in claims)
    for p in offered[0]['passage_ranges']:
        assert offered[0]['excerpt'][p['start']:p['end']] in text
