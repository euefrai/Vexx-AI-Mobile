"""Controlled regressions; fixtures are synthetic, not real web or model tests."""
import json
from pathlib import Path

import evidence_graph as eg
import query_intelligence as qi
import research
import research_agents as ra
import research_view


def src(text, **kw):
    return dict(id='s-one',url='https://example.org/fixture',texto=text,lida=True,**kw)


def states(query, text):
    result=eg.requirement_coverage(query,[src(text)])
    return {r['attribute']:r['state'] for r in result['requirements']}


def test_corpus_schema_and_document_groups_never_cross_splits():
    root=Path(__file__).resolve().parents[1]
    corpus=json.loads((root/'benchmarks/evidence_corpus_v5994.json').read_text(encoding='utf-8'))
    rows=corpus['examples'];assert len(rows)==108
    required={'id','question','requirement','entity','attribute','relation','passage','necessary_context',
              'source','source_type','read_state','label','justification','mandatory_conditions','origin_reference'}
    assert all(required<=r.keys() and r['source_type']=='SYNTHETIC' for r in rows)
    assert len({r['id'] for r in rows})==len(rows)
    groups={}
    for r in rows:groups.setdefault(r['document_group'],set()).add(r['split'])
    assert all(len(s)==1 for s in groups.values())
    assert len({r['label'] for r in rows})==9


def test_subject_predicate_not_homonymous_entity_name():
    q='Fábrica Horizonte, produtos?'
    assert states(q,'A Fábrica Horizonte foi fundada em 1950.')['products']=='DISCOVERED'
    assert states(q,'A Fábrica Horizonte makes cookware and furniture.')['products']=='SUPPORTED'
    assert states(q,'A Fábrica Horizonte informou que a Empresa Azul fabrica motores.')['products']=='DISCOVERED'


def test_roman_product_variant_and_short_entity_boundary():
    assert states('Marca Alfa II, peso?','A Marca Alfa III pesa 500 g.')['weight']=='DISCOVERED'
    assert states('Alfa, peso?','A SuperAlfa pesa 500 g.')['weight']=='DISCOVERED'
    assert states('Marca Alfa II, peso?','A Marca Alfa II é maior que a Marca Alfa III que pesa 500 g.')['weight']=='DISCOVERED'


def test_created_year_question_parses_without_organization_keyword():
    for q in ['Em que ano foi criada a Organização Horizonte?', 'Quando foi criado o Instituto Vale?']:
        req=qi.answer_requirements(q)
        assert len(req)==1 and req[0]['attribute']=='foundation_date'
        assert req[0]['entity'] in ('Organização Horizonte','Instituto Vale')
    assert qi.answer_requirements('Quais foram as causas e as consequências da Revolta do Porto?')[0]['entity']=='Revolta do Porto'


def test_bounded_auxiliary_context_and_negation():
    q='Companhia Boreal, em que ano foi criada?'
    assert states(q,'A Companhia Boreal é uma companhia que foi fundada no Brasil em 1952.')['foundation_date']=='SUPPORTED'
    assert states(q,'A Companhia Boreal não foi fundada em 1952.')['foundation_date']!='SUPPORTED'
    assert states(q,'A Companhia Boreal informou que a Empresa Delta foi fundada em 1952.')['foundation_date']!='SUPPORTED'


def test_local_antecedent_and_adjacent_operation_heading():
    q='Companhia Boreal, produtos?'
    cov=eg.requirement_coverage(q,[src('A Companhia Boreal foi fundada em 1952.\n\nEla fabrica motores e geradores.')])
    assert cov['complete']
    assert any('Ela fabrica' in p['text'] and 'Companhia Boreal' in p['text'] for p in cov['passages'])
    assert not eg.requirement_coverage(q,[src('A Companhia Boreal vende peças. A Empresa Delta foi fundada em 1954.\n\nEla fabrica motores.')])['complete']
    assert states('Pacote.Array.copy comportamento?','Pacote.Array.copy()\nReturns a new array without modifying the original.')['behavior']=='SUPPORTED'


def test_partial_weight_retained_without_completing_required_condition():
    q='Câmera Prisma II, peso com bateria e cartão?'
    cov=eg.requirement_coverage(q,[src('A Câmera Prisma II pesa 658 g.')])
    assert cov['passages'] and not cov['complete']
    assert cov['requirements'][0]['state']=='PARTIALLY_SUPPORTED'
    assert cov['passages'][0]['support_label']=='PARTIAL_SUPPORT'
    assert not cov['requirements'][0]['confirmed_evidence_ids']
    assert states(q,'A Câmera Prisma II pesa 658 g sem bateria e cartão.')['weight']=='PARTIALLY_SUPPORTED'
    assert states(q,'A Câmera Prisma II pesa 658 g com bateria e cartão.')['weight']=='SUPPORTED'


def test_multifacet_passage_retains_all_requirement_bindings_and_sqlite(tmp_path):
    import pc_agent
    q='Quem fundou a Empresa Clara, em que ano e quais produtos fabrica?'
    text='A Empresa Clara foi fundada em 1948 por Ana e Leo. A Empresa Clara fabrica motores e geradores.'
    cov=eg.requirement_coverage(q,[src(text)])
    selected=eg.select_answer_passages(cov)
    assert {r['id'] for r in cov['requirements']}==set().union(*(set(p['requirement_ids']) for p in selected))
    db=pc_agent.open_db(tmp_path/'fixture.sqlite')
    job=ra.criar_job(db,'owner-fixture',q,conv='fixture-chat')
    ra.registrar_evidencia(db,job,dict(id='s-one',url='https://example.org/fixture',texto_lido=True,
        answer_passages=selected,answerability={'state':'PARTIAL_ANSWER'}),text)
    stored=ra.listar_evidencias(db,'owner-fixture',job['id'])
    assert stored[0]['answer_passages']==selected
    assert not ra.listar_evidencias(db,'other-owner',job['id'])
    db.close()


def test_partial_state_is_visible_in_readonly_jdui():
    q='Câmera Prisma II, peso com bateria e cartão?'
    cov=eg.compact_coverage(eg.requirement_coverage(q,[src('A Câmera Prisma II pesa 658 g.')]))
    view=research_view.build_view({'objetivo':q,'usados':{'answer_coverage':cov}})
    table=next(b for b in view['blocks'] if b.get('component')=='table')
    assert table['props']['read_only'] and table['props']['rows'][0][1]=='Parcial'


def test_partial_relation_does_not_disappear_when_other_facets_missing():
    q='Empresa Clara, em que ano foi criada e produtos?'
    source=research._fonte_de({'texto':'A Empresa Clara is a vertically integrated company founded in Brazil in 1911.','lida':True},
        {'url':'https://example.org/clara','titulo':'Empresa Clara'},q)
    assert source['relevante'] and source['answerability']['state']=='PARTIAL_ANSWER'
    assert '1911' in source['answer_passages'][0]['text']


def test_spaced_prototype_name_keeps_behavior_identity():
    text='Array . prototype . toSorted () Returns a new array without modifying the original array.'
    q='Como funciona Array.prototype.toSorted?'
    assert states(q,text)['behavior']=='SUPPORTED'
    wrong=text.replace('Array . prototype . toSorted','Other . prototype . toSorted')
    assert states(q,wrong)['behavior']!='SUPPORTED'
    # A generic API index may contain another method before the requested one.
    body='Array.prototype.copy() Returns a new array. '+text+' Array.prototype.splice() Removes entries.'
    result=states('Array.prototype.toSorted sintaxe e comportamento?',body)
    assert result=={'syntax':'SUPPORTED','behavior':'SUPPORTED'}


def test_provider_audit_is_opt_in_redacted_and_reset(monkeypatch):
    import search_providers as sp
    class Core:
        def _circuito_fechado(self,name):return False
        def baixar(self,url,**kw):return ('https://example.org/final?token=private','<rss/>')
    monkeypatch.setattr(sp,'_research',lambda:Core())
    def provider(query,**kw):
        sp._baixar('https://user:secret@example.org/search?q=Orbe&token=private&api_key=private',1)
        return [dict(titulo='Orbe',url='https://user:secret@example.org/read?token=private')]
    monkeypatch.setitem(sp.PROVEDORES,'audit-fixture',dict(fn=provider,tipo='pagina'))
    events=[]
    with sp.observe_searches(events.append,'Orbe token=private'):
        assert sp.buscar('audit-fixture','Orbe api_key=private')
    sp.buscar('audit-fixture','Orbe')
    assert len(events)==1
    payload=json.dumps(events)
    assert 'private' not in payload and 'secret' not in payload
    event=events[0]
    assert event['classification']=='UNJUDGED_DISCOVERY'
    assert event['requests'][0]['parameters']=={'q':'Orbe'}
    assert event['requests'][0]['http_status'] is None
    assert event['requests'][0]['redirected']


def test_provider_audit_keeps_rate_limit_category(monkeypatch):
    import search_providers as sp
    class Core:
        def _circuito_fechado(self,name):return False
        def _circuito_falha(self,name):pass
    monkeypatch.setattr(sp,'_research',lambda:Core())
    def provider(query,**kw):
        err=sp.ErroProvedor('limited','bloqueado');err.http=429;raise err
    monkeypatch.setitem(sp.PROVEDORES,'audit-fixture',dict(fn=provider,tipo='pagina'))
    import pytest
    events=[]
    with sp.observe_searches(events.append,'Orbe'),pytest.raises(sp.ErroProvedor):sp.buscar('audit-fixture','Orbe')
    assert events[0]['classification']=='PROVIDER_RATE_LIMITED'


def test_causal_direction_never_turns_antecedent_into_consequence():
    q='Quais foram as causas e consequências da Revolta do Porto?'
    # Synthetic regression from the relation-direction failure observed in live QA.
    text='Líderes da Revolta do Porto buscavam reformas. A campanha obrigatória levou à Revolta do Porto.'
    result=states(q,text)
    assert result['causes']=='SUPPORTED'
    assert result['consequences']=='DISCOVERED'
    direct=states(q,'A Revolta do Porto resultou na reforma da legislação.')
    assert direct=={'causes':'DISCOVERED','consequences':'SUPPORTED'}
    for clause in ['A campanha não levou à Revolta do Porto.',
                   'A campanha poderia ter causado a Revolta do Porto.',
                   'Os líderes da Revolta do Porto provocaram uma discussão.']:
        assert states(q,clause)['consequences']!='SUPPORTED'
