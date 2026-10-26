"""Regressions from actual MDN extraction; fixtures are not autonomous research."""
import evidence_graph as eg
import web_extract as we


def test_short_return_paragraph_survives_section_and_literal_passage():
    html = '''<title>Object.assign() - JavaScript</title><main><article>
    <h2>Syntax</h2><pre>Object.assign(target, source)</pre>
    <h2>Return value</h2><p>The target object.</p>
    <h2>Description</h2><p>The Object.assign() method copies enumerable own properties from a source object to a target object.</p>
    </article></main>'''
    rec = we.extrair_pagina(html, 'https://example.org/assign', usar_trafilatura=False)
    rec.update(texto_lido=True)
    c = eg.requirement_coverage('Como usar Object.assign, qual a sintaxe e o que retorna?', [rec])
    ret = next(r for r in c['requirements'] if r['attribute']=='return_value')
    assert ret['state']=='PARTIALLY_SUPPORTED'
    assert all(p['text'] in rec['texto'] for p in c['passages'])


def test_normalized_paragraph_spacing_preserves_section_without_synthetic_quote():
    text='Return value The resulting object. It contains the copied properties.'
    sections=[{'titulo':'Return value','texto':'The resulting object.\nIt contains the copied properties.'}]
    passages=we.passage_candidates(text,'https://example.org/assign',sections)
    assert any(p.get('section')=='Return value' and p['text'].startswith('Return value') for p in passages)
    assert all(text[p['text_span']['start']:p['text_span']['end']]==p['text'] for p in passages)


def test_heading_does_not_attach_a_nonadjacent_or_unread_body():
    text='Return value Different operation. The target object.'
    ps=we.passage_candidates(text,'https://example.org/assign',[{'titulo':'Return value','texto':'The target object.'}])
    assert not any(p['text']=='Return value The target object.' for p in ps)
    c=eg.requirement_coverage('O que retorna Object.assign?', [{'titulo':'Object.assign()', 'texto':text,'texto_lido':False}])
    assert not c['passages']


def test_graph_retains_later_return_facet_after_many_syntax_passages(tmp_path):
    import pc_agent,research_agents as ra
    db=pc_agent.open_db(tmp_path/'qa.sqlite')
    try:
        query='Como usar Object.assign, qual a sintaxe e o que retorna?'
        job=ra.criar_job(db,'qa-owner',query,conv='qa-chat',manual='profunda')
        sections=[{'titulo':f'Example {n}','texto':f'Object.assign(target, source{n})'} for n in range(11)]
        sections.append({'titulo':'Return value','texto':'The target object.'})
        text=' '.join(s['titulo']+' '+s['texto'] for s in sections)
        rec={'titulo':'Object.assign()','texto':text,'secoes':sections,'texto_lido':True}
        ra.agente_analista(db,job,{'id':'read','alvo':query},[{'url':'https://example.org/assign'}],lambda url:rec,teto_paginas=1)
        evidence=ra.listar_evidencias(db,job['owner'],job['id'])
        coverage=eg.requirement_coverage(query,evidence)
        ret=next(r for r in coverage['requirements'] if r['attribute']=='return_value')
        assert ret['state']=='PARTIALLY_SUPPORTED'
        assert any(n.get('requirement_id')==ret['id'] for n in eg.nos_do_job(db,job['owner'],job['id'],'claim'))
    finally:db.close()


def test_explicit_copy_behavior_is_retained_but_other_method_is_not():
    query='Como funciona Object.assign?'
    text='The Object.assign() method only copies enumerable and own properties from a source object to a target object.'
    rec={'titulo':'Object.assign()', 'texto':text, 'texto_lido':True}
    assert eg.requirement_coverage(query,[rec])['requirements'][0]['state']=='SUPPORTED'
    assert not eg.requirement_coverage(query,[{**rec,'texto':text.replace('Object.assign','Object.keys')}])['passages']


def test_generic_math_result_does_not_stop_technical_provider_fallback():
    import research_agents as ra
    class Generic:
        nome='generic'
        def buscar(self,q,limit):return [{'titulo':'Math calculator','url':'https://example.org/math','trecho':'Solve math problems'}]
    class Specific:
        nome='specific'
        def buscar(self,q,limit):return [{'titulo':'Math.hypot()','url':'https://example.org/Math/hypot','trecho':'Reference'}]
    results,info=ra.buscar_com_fallback([Generic(),Specific()],'Como usar Math.hypot, qual a sintaxe?',6)
    assert info['provedor']=='specific'
    assert len(results)==1 and results[0]['titulo']=='Math.hypot()'


def test_operation_in_real_path_preserves_incomplete_metadata_candidate():
    import search_orchestrator as orch
    candidate={'titulo':'JavaScript reference','url':'https://example.org/Global_Objects/Math/hypot','trecho':''}
    assert 'ENTITY_MISMATCH' not in orch._context_mismatch(candidate,'Como usar Math.hypot, qual a sintaxe?')
    parent={'titulo':'Object - JavaScript','url':'https://example.org/docs/Reference/Global_Objects/Object','trecho':''}
    assert 'ENTITY_MISMATCH' not in orch._context_mismatch(parent,'Como usar Object.assign, qual a sintaxe?')
    dictionary={**parent,'url':'https://example.org/dictionary/object','titulo':'Object meaning'}
    assert 'ENTITY_MISMATCH' in orch._context_mismatch(dictionary,'Como usar Object.assign, qual a sintaxe?')


def test_compacted_bindings_keep_rare_return_facet():
    import hashlib
    texts=[f'Object.assign(target, source{n})' for n in range(35)]+['Object.assign returns the target object.']
    text='\n'.join(texts);passages=[]
    for line in texts:
        start=text.index(line)
        passages.append({'id':'P-'+hashlib.sha256(line.encode()).hexdigest()[:16],'text':line,
                         'text_span':{'start':start,'end':start+len(line)},'section':''})
    rec={'titulo':'Object.assign()','texto':text,'texto_lido':True,'answer_passages':passages}
    c=eg.requirement_coverage('Como usar Object.assign, qual a sintaxe e o que retorna?',[rec])
    ret=next(r for r in c['requirements'] if r['attribute']=='return_value')
    assert len(c['passages'])<=32
    assert any(p['requirement_id']==ret['id'] for p in c['passages'])


def test_trace_yield_is_bounded_and_does_not_export_document_text():
    import retrieval_trace as trace
    with trace.observe() as rows:
        trace.record('qa','step',{'url':'https://example.org/private'},'PASSAGE_SELECTED',
                     coverage={'diagnostics':{'read_documents':1,'generated_passages':8,'text':'secret','retained_bindings':-1}})
    assert rows[0]['passage_yield']=={'read_documents':1,'generated_passages':8}
    assert 'secret' not in str(rows) and 'https://' not in str(rows)
