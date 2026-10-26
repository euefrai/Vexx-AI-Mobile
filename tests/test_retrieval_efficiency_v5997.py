"""Cross-front context, persisted document reuse and literal facet retention."""
import copy
import json
import pytest
import pc_agent
import research_agents as ra
import research
import evidence_graph as eg
import search_orchestrator as orch
import query_intelligence as qi


@pytest.fixture
def job(tmp_path):
    db=pc_agent.open_db(tmp_path/'qa.sqlite3')
    j=ra.criar_job(db,'qa-owner','Como usar Object.assign, qual a sintaxe e o que retorna?',conv='chat-a',manual='profunda')
    yield db,j
    db.close()


def test_rejected_document_is_not_downloaded_again_for_another_front(job):
    db,j=job;calls=[]
    source={'titulo':'Object is a physical object','url':'https://example.org/object'}
    def recover(url):
        calls.append(url)
        return {'titulo':source['titulo'],'texto':'A physical object has mass and volume. '*20,'final':url}
    for n in range(2):
        ra.agente_analista(db,j,{'id':f'p{n}','alvo':'Object.assign sintaxe'},[source],recover,teto_paginas=2)
    assert calls == [source['url']]
    assert j['usados']['paginas']==1


def test_internal_provider_retries_preserve_research_constraints(job,monkeypatch):
    db,j=job
    j['objetivo']='Compare dois notebooks Lenovo com 16 GB de RAM, excluindo usados'
    calls=[]
    monkeypatch.setattr(orch.sp,'buscar',lambda name,q,**kw: calls.append(q) or [])
    provider=ra.ProvedorOrquestrado({'max_provedores':1,'max_tentativas':3,'timeout_total':2})
    ra.agente_busca(db,j,{'id':'p1','alvo':j['objetivo']},[provider],set())
    assert calls
    assert all('excluindo usados' in q and '16 GB' in q and 'dois' in q for q in calls)


def test_section_passages_keep_operation_context_without_inventing_quotes():
    q='Como usar Object.assign, qual a sintaxe e o que retorna?'
    text='Object.assign(target, source)\nDescription\nCopies enumerable own properties.\nReturn value\nThe target object.'
    source={'titulo':'Object.assign() - JavaScript','url':'https://example.org/assign','texto':text,'texto_lido':True,
            'secoes':[{'titulo':'Return value','texto':'The target object.'}]}
    coverage=eg.requirement_coverage(q,[source])
    returns=next(r for r in coverage['requirements'] if r['attribute']=='return_value')
    assert returns['state']=='PARTIALLY_SUPPORTED'
    for p in coverage['passages']:
        assert p['text'] in text
    unrelated={**source,'titulo':'Object.keys() - JavaScript'}
    other=eg.requirement_coverage(q,[unrelated])
    assert next(r for r in other['requirements'] if r['attribute']=='return_value')['state']!='SUPPORTED'


def test_cache_preserves_query_parameter_variants_and_owner(job):
    db,j=job;calls=[]
    def recover(url):
        calls.append(url)
        return {'titulo':'Object.assign','texto':'Object.assign(target, source) returns the target object.','final':url}
    for url in ('https://example.org/doc?v=1','https://example.org/doc?v=2'):
        ra.agente_analista(db,j,{'id':url[-1],'alvo':j['objetivo']},[{'titulo':'Object.assign','url':url}],recover,2)
    other=ra.criar_job(db,'other-owner',j['objetivo'],conv='chat-a',manual='profunda')
    ra.agente_analista(db,other,{'id':'other','alvo':other['objetivo']},[{'titulo':'Object.assign','url':calls[0]}],recover,2)
    assert len(calls)==3


def test_cache_expiration_and_redirect_alias(job):
    db,j=job;calls=[]
    def recover(url):
        calls.append(url)
        return {'titulo':'Object.assign','texto':'Object.assign(target, source) returns the target object.',
                'final':'https://example.org/final'}
    for url in ('https://example.org/redirect','https://example.org/final'):
        ra.agente_analista(db,j,{'id':url,'alvo':j['objetivo']},[{'titulo':'Object.assign','url':url}],recover,2)
    assert len(calls)==1
    db.execute("UPDATE research_cache SET expira_em='2000-01-01T00:00:00+00:00'");db.commit()
    ra.agente_analista(db,j,{'id':'stale','alvo':j['objetivo']},[{'titulo':'Object.assign','url':'https://example.org/final'}],recover,2)
    assert len(calls)==2


def test_query_to_source_links_survive_persistence_and_reuse(job):
    db,j=job
    class Provider:
        nome='controlled'
        def buscar(self,q,limite=6):return [{'titulo':'Object.assign','url':'https://example.org/assign'}]
    def recover(url):return {'titulo':'Object.assign','texto':'Object.assign(target, source) returns the target object.','final':url}
    for n,facet in enumerate(('sintaxe','valor retornado')):
        step={'id':f'p{n}','alvo':'Object.assign '+facet}
        candidates=ra.agente_busca(db,j,step,[Provider()],set())
        ra.agente_analista(db,j,step,candidates,recover,2)
    saved=ra.listar_evidencias(db,j['owner'],j['id'])
    assert len(saved)==1
    provenance=saved[0]['retrieval_provenance']
    assert len(provenance['query_ids'])>=2
    assert set(provenance['query_ids']).issubset(j['ajustes']['queries'])
    assert set(provenance['requirement_ids'])=={r['id'] for r in qi.answer_requirements(j['objetivo']) if r['attribute'] in ('syntax','return_value')}


def test_provider_context_restored_after_failure():
    request=qi.analyze('Notícias de Irecê Bahia nos últimos sete dias')
    with pytest.raises(RuntimeError):
        with qi.discovery_scope(request):
            assert 'Irecê' in qi.constrain_provider_query('saúde')
            raise RuntimeError('controlled')
    assert qi.constrain_provider_query('saúde')=='saúde'


def test_four_disjoint_facets_survive_passage_selection():
    question='Quem fundou WEG, em que ano, quais produtos fabrica e preço?'
    facts=['WEG foi fundada por Werner Voigt.', 'WEG foi fundada em 1961.',
           'WEG fabrica motores e equipamentos elétricos.', 'WEG custa R$ 10.']
    text='\n\n'.join(fact+' '+('Contexto adicional neutro. '*48) for fact in facts)
    coverage=eg.requirement_coverage(question,[{'titulo':'WEG','url':'https://example.org/weg','texto':text,'texto_lido':True}])
    assert len({p['requirement_id'] for p in coverage['passages']})==4
    selected=eg.select_answer_passages(coverage)
    assert {r for p in selected for r in p['requirement_ids']}=={p['requirement_id'] for p in coverage['passages']}


def test_identical_extractions_keep_sources_without_independent_confirmation(job):
    db,j=job
    def recover(url):return {'titulo':'Object.assign','texto':'Object.assign(target, source) returns the target object.','final':url}
    for n,url in enumerate(('https://a.example/assign','https://b.example/assign')):
        ra.agente_analista(db,j,{'id':str(n),'alvo':j['objetivo']},[{'titulo':'Object.assign','url':url}],recover,2)
    sources=ra.listar_evidencias(db,j['owner'],j['id'])
    assert len(sources)==2 and sources[0]['url']!=sources[1]['url']
    assert len({s['document_id'] for s in sources})==1
    coverage=eg.requirement_coverage(j['objetivo'],sources)
    assert all(len(r['confirmed_evidence_ids'])<=1 for r in coverage['requirements'])


def test_deleting_job_removes_its_document_cache(job):
    db,j=job
    ra.agente_analista(db,j,{'id':'read','alvo':j['objetivo']},[{'titulo':'Object.assign','url':'https://example.org/assign'}],
                      lambda url:{'titulo':'Object.assign','texto':'Object.assign(target, source) returns the target object.','final':url},2)
    assert db.execute('SELECT COUNT(*) FROM research_cache WHERE provedor=?',('document:'+j['id'],)).fetchone()[0]>0
    ra.excluir_job(db,j['owner'],j['id'])
    assert db.execute('SELECT COUNT(*) FROM research_cache WHERE provedor=?',('document:'+j['id'],)).fetchone()[0]==0


def test_trace_does_not_label_requested_requirements_as_supported():
    import retrieval_trace as trace
    requested='R-'+'a'*12; supported='R-'+'b'*12
    with trace.observe() as rows:
        trace.record('job','step',{'url':'https://example.org','retrieval_provenance':{'requirement_ids':[requested]}},
                     'EVIDENCE_PARTIAL',coverage={'requirements':[{'id':requested},{'id':supported}],
                                                 'passages':[{'id':'P-'+'c'*16,'requirement_id':supported,'support_label':'PARTIAL_SUPPORT'}]})
    assert rows[0]['requested_requirement_ids']==[requested]
    assert rows[0]['requirement_ids']==[supported]
    assert rows[0]['requirement_support']=={supported:'PARTIAL_SUPPORT'}
