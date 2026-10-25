"""Explicit relations/passages, safe navigation and partial delivery; no network/model."""
import evidence_graph as eg
import query_intelligence as qi
import research
import research_agents as ra
import research_gaps
import web_extract

QUESTION = 'Quem fundou a WEG, em que ano e quais são seus principais produtos?'
FOUNDING = 'A WEG foi fundada em 1961 por Werner Ricardo Voigt, Eggon João da Silva e Geraldo Werninghaus.'
PRODUCTS = 'A WEG fabrica motores elétricos, geradores, transformadores e equipamentos de automação industrial.'


def source(text, ident='ev-one', **extra):
    return dict(id=ident,url='https://example.org/'+ident,texto_lido=True,trecho=text,
                titulo='Fonte de teste',dominio='example.org',**extra)


def test_requirements_separate_entity_attributes_and_keep_stable_ids():
    req=qi.answer_requirements(QUESTION)
    assert {r['attribute'] for r in req}=={'founders','foundation_date','products'}
    assert {r['entity'] for r in req}=={'WEG'}
    assert [r['id'] for r in req]==[r['id'] for r in qi.answer_requirements(QUESTION)]
    assert qi.topic_profile(QUESTION)['primary_topic']=='WEG'
    assert not qi.answer_requirements('Bateria ZX capacidade nominal')
    assert qi.answer_requirements('como funciona o freio ABS')[0]['entity']=='freio ABS'


def test_topic_page_is_read_but_not_an_answer():
    query='Documentação oficial WebAssembly memory grow limitações'
    text='WebAssembly is a binary instruction format for a stack based virtual machine. Memory management and limitations are important topics.'
    result=research._fonte_de({'texto':text,'lida':True},{'url':'https://example.org/wasm','titulo':'WebAssembly'},query)
    assert result['status']=='aberta' and not result['relevante']
    assert result['answerability']['state']=='TOPIC_ONLY'


def test_multi_requirement_coverage_requires_each_relation():
    partial=eg.requirement_coverage(QUESTION,[source(FOUNDING)])
    assert not partial['complete']
    assert {r['attribute'] for r in partial['requirements'] if r['state']=='SUPPORTED'}=={'founders','foundation_date'}
    full=eg.requirement_coverage(QUESTION,[source(FOUNDING),source(PRODUCTS,'ev-two')])
    assert full['complete']
    assert next(r for r in full['requirements'] if r['attribute']=='products')['confirmed_evidence_ids']==['ev-two']


def test_causes_do_not_support_consequences():
    result=eg.requirement_coverage('Quais foram as causas e consequências da Revolta da Chibata?',
        [source('A Revolta da Chibata foi motivada pelos castigos físicos impostos aos marinheiros.')])
    assert not result['complete']
    assert [r['state'] for r in result['requirements']]==['SUPPORTED','DISCOVERED']
    assert qi.answer_requirements('Pesquisa profunda sobre as causas e consequências da Revolta da Chibata.')[0]['entity']=='Revolta da Chibata'


def test_snippets_wrong_entity_and_rejected_filters_never_support():
    records=[source(FOUNDING,content_scope='feed_metadata'),source(FOUNDING,vertical={'eligible':False}),
             source(FOUNDING,relevante=False),source(FOUNDING.replace('WEG','ACME'))]
    unread=source(FOUNDING);unread['texto_lido']=False;records.append(unread)
    for record in records:
        assert not any(r['state']=='SUPPORTED' for r in eg.requirement_coverage(QUESTION,[record])['requirements'])


def test_passage_offsets_are_literal_preserve_numbers_and_do_not_invent_pages():
    text='Introdução sem números.\n\n'+FOUNDING+'\n\n'+PRODUCTS+' Peso: 200,5 kg.'
    for p in web_extract.passage_candidates(text,'https://example.org/a'):
        span=p['text_span'];assert text[span['start']:span['end']]==p['text']
        assert 'page' not in p
    assert '200,5 kg' in ' '.join(p['text'] for p in web_extract.passage_candidates(text))


def test_conflicting_foundation_years_require_review():
    result=eg.requirement_coverage(QUESTION,[source(FOUNDING),source(FOUNDING.replace('1961','1962'),'ev-two')])
    assert next(r for r in result['requirements'] if r['attribute']=='foundation_date')['state']=='CONTRADICTED'
    assert not result['complete']


def test_another_company_and_negation_do_not_answer_founder_question():
    for text in ['A WEG vende motores. A ACME foi fundada em 1990 por João Teste.',
                 'A WEG informou que a ACME foi fundada em 1990 por João Teste.',
                 'A WEG não foi fundada em 1990 por João Teste.']:
        coverage=eg.requirement_coverage(QUESTION,[source(text)])
        assert not any(r['state']=='SUPPORTED' for r in coverage['requirements'] if r['attribute'] in ('founders','foundation_date'))


def test_follow_up_targets_only_missing_attribute_and_keeps_constraints():
    gaps=research_gaps.identify({'objetivo':QUESTION,'plano':[],'orcamento':{'buscas':3},'usados':{}},[source(FOUNDING)])
    assert next(g for g in gaps if g['dimension']=='products')['query']=='WEG Produtos'
    assert all(not g['query'] for g in gaps if g['status']=='RESOLVED')
    question='Notebook Lenovo com 16 GB por até R$ 3.000: quais produtos e preços?'
    assert question in qi.requirement_query(qi.answer_requirements(question)[0],question)


def test_navigation_is_declared_relevant_bounded_and_host_boundary_is_real():
    parent='https://docs.example.org/'
    links=[{'url':parent+'privacy','texto':'Privacy policy'},
           {'url':parent+'memory/grow','texto':'WebAssembly Memory grow reference'},
           {'url':'javascript:alert(1)','texto':'WebAssembly Memory grow'}]
    query='Documentação oficial WebAssembly memory grow limitações'
    assert [p['url'] for p in web_extract.navigation_candidates(links,query,parent)]==[parent+'memory/grow']
    assert not web_extract.navigation_candidates(links,query,parent,depth=2)
    assert not web_extract.extrair_links('<a href="https://evilexample.org/a">A</a>','https://example.org/')[0]['interno']


def test_model_timeout_partial_is_delivered_once_cancel_never_posts(tmp_path):
    import pc_agent
    db=pc_agent.open_db(tmp_path/'qa.sqlite')
    job=ra.criar_job(db,'local',QUESTION,conv='qa-chat')
    ra.registrar_evidencia(db,job,{'id':'s-one','url':'https://example.org/founding','texto_lido':True},FOUNDING)
    job['status']='interrompida';job['usados'].update(partial_delivery_ready=True,research_outcome={'state':'blocked'})
    job['sintese']={'texto':'Resultado parcial; redação indisponível. '+FOUNDING,'llm':False}
    ra.salvar_job(db,job)
    result=pc_agent._persistir_resultado_pesquisa(db,job,'local')
    assert result==job['id']+'-result'
    assert pc_agent._persistir_resultado_pesquisa(db,job,'local')==result
    assert db.execute('select count(*) from messages').fetchone()[0]==1
    job['status']='cancelada'
    assert not pc_agent._persistir_resultado_pesquisa(db,job,'local')
    db.close()


def test_quick_reader_follows_real_document_link_within_six_reads():
    import sqlite3
    db=sqlite3.connect(':memory:');research.criar_tabelas(db)
    query='Como funciona WebAssembly.Memory.grow?'
    home='https://docs.example.org/';specific=home+'memory/grow'
    calls=[]
    def read(url):
        calls.append(url)
        if url==home:
            return {'titulo':'WebAssembly','texto':'WebAssembly describes a virtual machine and memory.',
                    'links':[{'url':specific,'texto':'WebAssembly Memory grow reference'}]}
        return {'titulo':'WebAssembly.Memory.grow','texto':'WebAssembly.Memory.grow increases the memory by the requested number of pages and returns its previous size.'}
    result=research.pesquisa_rapida(db,'qa',query,buscar_fn=lambda q:[{'url':home,'titulo':'WebAssembly','trecho':'Memory'}],recuperar_fn=read)
    assert calls==[home,specific] and len(calls)<=6
    assert any(s['url']==specific and s['relevante'] for s in result['fontes'])
    assert result['answer_coverage']['complete']
    db.close()


def test_coverage_table_cannot_be_edited_and_validates_in_backend():
    import research_view,jdui
    coverage=eg.compact_coverage(eg.requirement_coverage(QUESTION,[source(FOUNDING)]))
    message=research_view.build_view({'objetivo':QUESTION,'usados':{'answer_coverage':coverage}})
    table=next(b for b in message['blocks'] if b.get('component')=='table')
    assert table['props']['read_only'] is True and len(table['props']['rows'])==3
    assert jdui.validar_mensagem(message)[0]


def test_quote_may_not_bridge_distant_passages():
    import json,pytest,research_synthesis as rs
    first=FOUNDING;second=PRODUCTS
    excerpt=first+'\n\n'+second
    crossed=first[-35:]+' '+second[:35]
    sources=[{'id':'E1','evidence_id':'ev-one','url':'https://example.org/one','excerpt':excerpt,
              'passage_ranges':[{'start':0,'end':len(first)},{'start':len(first)+2,'end':len(excerpt)}]}]
    output=json.dumps({'points':[{'text':FOUNDING,'evidence':[{'id':'E1','quote':crossed}]}]})
    with pytest.raises(ValueError,match='crosses'):
        rs.generate(QUESTION,sources,[],lambda *a:output)


def test_synthesis_omitting_an_explicit_requirement_is_not_complete(tmp_path):
    import pc_agent
    from test_research_synthesis import answer,approved_review
    db=pc_agent.open_db(tmp_path/'qa.sqlite');job=ra.criar_job(db,'local',QUESTION)
    evidence=[source(FOUNDING),source(PRODUCTS,'ev-two')]
    result=ra.agente_sintetizador(db,job,evidence,[],lambda *a:answer(text=FOUNDING,quote=FOUNDING),verificar_fn=approved_review)
    assert result['llm'] and not result['answer_coverage']['complete']
    job['sintese']=result
    assert ra._completion_outcome(job,evidence,[],True)['state']=='partial'
    db.close()


def test_new_research_and_another_chat_cannot_intervene_in_previous_job(tmp_path,monkeypatch):
    import pc_agent
    db=pc_agent.open_db(tmp_path/'qa.sqlite');old=ra.criar_job(db,'local','Empresa anterior',conv='old-chat')
    old['status']='interrompida';ra.salvar_job(db,old)
    monkeypatch.setattr(ra,'intervir',lambda *a: (_ for _ in ()).throw(AssertionError('wrong previous job')))
    assert pc_agent._cmd_intervencao(db,'local','somente fontes públicas','new-chat')==''
    captured=[]
    monkeypatch.setattr(pc_agent,'rjob_start',lambda db,req,owner:captured.append(req) or {'type':'research_job','job_id':'rj-fixture'})
    text='Pesquisa profunda sobre '+('contexto público detalhado '*9)+'somente fontes públicas e sem preços históricos'
    response=pc_agent.cmd_pesquisa(db,text,'local','new-chat')
    assert 'rj-fixture' in response and captured[0]['objetivo'].endswith('sem preços históricos')
    assert len(captured[0]['objetivo'])>200
    db.close()


def test_text_chat_does_not_present_discovered_metadata_as_answer_gallery(tmp_path):
    import pc_agent,jdui,json
    db=pc_agent.open_db(tmp_path/'qa.sqlite');job=ra.criar_job(db,'local',QUESTION,conv='qa-chat')
    job.update(status='concluida',midia=[{'type':'image','url':'https://example.org/logo.jpg',
        'title':'WEG logo','source_url':'https://example.org/','analysis_state':'not_analyzed'}])
    result=pc_agent._persistir_resultado_pesquisa(db,job,'local')
    text=db.execute('select text from messages where id=?',(result,)).fetchone()[0]
    view=json.loads(jdui.extrair_fences(text)[0])
    assert not any(b.get('component')=='media' for b in view['blocks'])
    db.close()


def test_extractive_result_survives_skipped_final_steps_and_reload(tmp_path):
    import pc_agent
    db=pc_agent.open_db(tmp_path/'qa.sqlite');job=ra.criar_job(db,'local','Quem fundou a WEG?',conv='qa-chat')
    ra.montar_plano(db,job)
    job['plano']=[s for s in job['plano'] if s['tipo'] in ('busca','ler')]
    job['orcamento']['replans']=0;ra.salvar_job(db,job)
    class Provider:
        nome='fixture'
        def buscar(self,*args):return [{'id':'s','titulo':'WEG','url':'https://example.org/weg','trecho':FOUNDING}]
    result=ra.executar(db,job['id'],'local',[Provider()],lambda url:{'titulo':'WEG','texto':FOUNDING,'texto_lido':True})
    assert '1961' in result['sintese']['texto'] and not result['sintese']['llm']
    restored=ra._resumo(db,ra.carregar_job(db,'local',job['id']))
    assert restored['sintese']['texto']==result['sintese']['texto']
    db.close()


def test_qualified_operation_does_not_inherit_another_interfaces_behavior():
    query='Como funciona Namespace.Buffer.resize?'
    correct=source('Namespace.Buffer.resize increases the buffer and returns its previous size.')
    wrong=source('Namespace Buffer resize instruction returns a different failure value in this virtual machine.')
    assert eg.requirement_coverage(query,[correct])['complete']
    assert not eg.requirement_coverage(query,[wrong])['passages']
    alias=source('resize(delta) returns its previous size.')
    alias['titulo']='Namespace.Buffer.prototype.resize'
    # A title can establish the qualified page context, but never creates the
    # missing entity/relation inside an otherwise unrelated extracted passage.
    assert not eg.requirement_coverage(query,[alias])['complete']
