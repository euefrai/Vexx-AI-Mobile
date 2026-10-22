"""V594 regressions: isolated SQLite + explicit provider fixtures (no network)."""
from datetime import datetime, timezone
import json
from concurrent.futures import ThreadPoolExecutor
import pytest
import live_data as live
import pc_agent
import conversation_followups as follow
import intent
import docs_agent
import research
import jdui
from weather_fixtures import photon

NOW=datetime(2026,10,22,12,tzinfo=timezone.utc)

@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    live._cache.clear()
    def geometry(url,**kwargs):
        import re
        match=re.search(r'/malhas/municipios/(\d{7})/metadados$',url)
        if not match:pytest.fail('Unmocked external request')
        return '',json.dumps([{'id':match[1],'centroide':{'latitude':-14.0964,'longitude':-39.5219}}])
    monkeypatch.setattr(research,'baixar',geometry)
    yield
    live._cache.clear()

@pytest.mark.parametrize('text,route',[
 ('oi','GREETING'),('oi, tudo bem?','GREETING'),('que horas são agora?','CURRENT_TIME'),
 ('qual temperatura em Ubatã?','WEATHER_CURRENT'),('vai chover amanhã em Ubatã?','WEATHER_FORECAST'),
 ('pesquise a cidade de Oi no Japão','LOCATION_LOOKUP'),('pesquise notebooks','SHOPPING'),
 ('resuma meu TODO.md','DOCUMENT_QUERY'),('leia o arquivo do projeto','PROJECT_FILE_QUERY'),
 ('converta 100 USD para BRL','CURRENCY'),('notícias de tecnologia hoje','NEWS'),
 ('passagens de ônibus de Salvador para Ilhéus','TRANSPORT'),('eventos em Salvador amanhã','EVENTS'),
 ('pesquisa profunda sobre semicondutores','DEEP_RESEARCH'),('pesquise artigos científicos sobre baterias','GENERAL_SEARCH'),
 ('como posso estudar melhor?','GENERAL_CHAT')])
def test_routes(text,route):
    assert intent.analisar(text)['route']==route


def municipal(code,name,uf):
    return dict(id=code,nome=name,microrregiao={'mesorregiao':{'UF':{'sigla':uf}}})


def city(name='Ubatã',state='Bahia',code=3445849,country='BR'):
    return dict(id=code,name=name,admin1=state,country='Brasil' if country=='BR' else 'Japão',country_code=country,
                feature_code='PPL',latitude=-14.20906,longitude=-39.52641,timezone='America/Bahia')

@pytest.mark.parametrize('text', ['Ubatã','Ubata','Ubatã BA','ubatã/Bahia','Ubatã, Bahia, Brasil','2932309'])
def test_brazil_aliases(monkeypatch,text):
    registry=municipal(2932309,'Ubatã','BA')
    monkeypatch.setattr(live,'_ibge',lambda path:registry if path.startswith('municipios/') else [registry])
    monkeypatch.setattr(live,'get_json',lambda *a:pytest.fail('Official municipality must not use hosted geocoder'))
    place,error=live.geocode(text)
    assert not error and place['name']=='Ubatã' and place['state']=='Bahia'
    if '/' in text or 'BA' in text or 'Bahia' in text or text.isdigit():assert place['ibge_id']==2932309

@pytest.mark.parametrize('name,uf,state', [('Ubá','MG','Minas Gerais'),('Salvador','BA','Bahia'),('Feira de Santana','BA','Bahia')])
def test_distinct_municipalities(monkeypatch,name,uf,state):
    monkeypatch.setattr(live,'_ibge',lambda _:[])
    monkeypatch.setattr(live,'get_json',lambda *_:photon([city(),city(name,state)]))
    place,error=live.geocode(name+'/'+uf)
    assert not error and place['name']==name and place['state']==state


def test_ambiguity_and_explicit_state(monkeypatch):
    monkeypatch.setattr(live,'_ibge',lambda _:[])
    monkeypatch.setattr(live,'get_json',lambda *_:photon([city('Santa Luzia','Bahia'),city('Santa Luzia','Minas Gerais')]))
    assert 'mais de uma' in live.geocode('Santa Luzia')[1]
    assert live.geocode('Santa Luzia/BA')[0]['state']=='Bahia'


def test_official_centroid_fallback_not_different_city(monkeypatch):
    monkeypatch.setattr(live,'_ibge',lambda _:[municipal(2932309,'Ubatã','BA')])
    monkeypatch.setattr(live,'get_json',lambda *_:{'results':[city('Salvador')]})
    monkeypatch.setattr(research,'baixar',lambda *a,**k:('',json.dumps([{'id':'2932309','centroide':{'latitude':-14.0964,'longitude':-39.5219}}])))
    place,error=live.geocode('ubata bahia')
    assert not error and place['ibge_id']==2932309 and place['coordinate_scope']=='municipal_centroid'
    assert 'centroide municipal' in place['label'] and place['name']=='Ubatã'


def test_empty_provider_does_not_deny_existence(monkeypatch):
    monkeypatch.setattr(live,'_ibge',lambda _:[])
    monkeypatch.setattr(live,'get_json',lambda *_:{})
    assert 'não significa que o município não exista' in live.geocode('Ubata/BA')[1]


def test_same_state_homonyms_do_not_silently_pick_coordinates(monkeypatch):
    monkeypatch.setattr(live,'_ibge',lambda _:[])
    a=city('Santa Luzia');b=dict(a,latitude=-12.0,admin2='Outro município')
    monkeypatch.setattr(live,'get_json',lambda *_:photon([a,b]))
    assert 'mais de uma' in live.geocode('Santa Luzia/BA')[1]


def test_two_project_chats_keep_their_own_slots(tmp_path):
    import workspace_store
    db=pc_agent.open_db(tmp_path/'projects.sqlite3')
    workspace_store.merge_records(db,[dict(id=key,kind=kind,title=key,project_id=project,
        updated_at=NOW.isoformat(),change_id='change-594') for key,kind,project in
        [('proj-one','project',''),('proj-two','project',''),('chat-one','chat','proj-one'),('chat-two','chat','proj-two')]],'u-alice')
    put(db,'project-weather-1','clima em Ubatã BA',conv='chat-one')
    put(db,'project-weather-2','clima em Ubá MG',conv='chat-two')
    assert follow.weather_slots(db,'u-alice','chat-one','e amanhã?')['city']=='Ubatã BA'
    assert follow.weather_slots(db,'u-alice','chat-two','e amanhã?')['city']=='Ubá MG'
    assert follow.weather_slots(db,'u-bob','chat-two','e amanhã?') is None
    db.close()


def put(db,mid,text,conv='chat-one',owner='u-alice',role='user'):
    pc_agent.persist_messages(db,[dict(id=mid,conversation_id=conv,role=role,origin='mobile',text=text,created_at=NOW.isoformat())],owner)


def test_slots_pending_slash_forecast_current_and_topic_reset(tmp_path,monkeypatch):
    db=pc_agent.open_db(tmp_path/'context.sqlite3')
    seen=[]
    monkeypatch.setattr(live,'respond',lambda text,ctx:seen.append(text) or text)
    put(db,'weather-original','qual a temperatura?')
    assert 'ubatã/Bahia' in pc_agent.cmd_dados_atuais(db,'ubatã/Bahia','u-alice','chat-one',{})
    put(db,'weather-city','ubatã/Bahia')
    assert 'ubatã/Bahia' in pc_agent.cmd_dados_atuais(db,'qual a temperatura?','u-alice','chat-one',{})
    assert 'Previsão' not in seen[-1]
    assert 'Previsão' in pc_agent.cmd_dados_atuais(db,'e amanhã?','u-alice','chat-one',{})
    assert 'ubatã/Bahia' in seen[-1]
    monkeypatch.setattr(live,'geocode',lambda _:pytest.fail('Greeting must not geocode'))
    assert pc_agent.cmd_dados_atuais(db,'oi','u-alice','chat-one',{}).startswith('Oi!')
    put(db,'topic-greeting','oi')
    assert pc_agent.cmd_dados_atuais(db,'e amanhã?','u-alice','chat-one',{}) is None
    db.close()


def test_context_scopes_and_concurrent_cutoff(tmp_path):
    path=tmp_path/'scopes.sqlite3';db=pc_agent.open_db(path)
    put(db,'first-weather','clima em Ubatã BA')
    put(db,'current-question','e amanhã?')
    put(db,'later-weather','clima em Ubá MG')
    assert follow.weather_slots(db,'u-alice','chat-one','e amanhã?','current-question')['city']=='Ubatã BA'
    assert follow.weather_slots(db,'u-bob','chat-one','e amanhã?') is None
    assert follow.weather_slots(db,'u-alice','chat-two','e amanhã?') is None
    db.close()
    def get(owner,conv):
        local=pc_agent.open_db(path)
        try:return follow.weather_slots(local,owner,conv,'e amanhã?','current-question')
        finally:local.close()
    with ThreadPoolExecutor(2) as pool:
        good,bad=list(pool.map(lambda x:get(*x),[('u-alice','chat-one'),('u-bob','chat-one')]))
    assert good['city']=='Ubatã BA' and bad is None


def test_tool_survives_model_429_persistence_and_replay(tmp_path,monkeypatch):
    db=pc_agent.open_db(tmp_path/'model.sqlite3')
    monkeypatch.setattr(pc_agent,'gerar_texto',lambda *a,**k:pytest.fail('LLM should not run, including 429'))
    monkeypatch.setattr(live,'weather',lambda text,ctx,now:'Dados reais da ferramenta de teste: '+text)
    payload=dict(owner='u-alice',conversation_id='chat-one',message_id='model-rate-0001',text='clima em Ubatã BA')
    answer=pc_agent.ai_completa(db,payload,{'model':'unavailable-429'})
    assert 'Ubatã BA' in answer['response_text']
    assert pc_agent.ai_completa(db,payload,{'model':'unavailable-429'})['replay']
    assert db.execute("SELECT count(*) FROM messages WHERE role='assistant'").fetchone()[0]==1
    db.close()


def test_provider_429_circuit_and_no_fabrication(monkeypatch):
    monkeypatch.setattr(live,'geocode',lambda _:({'latitude':-14.2,'longitude':-39.5,'label':'Ubatã, Bahia, Brasil'},None))
    calls=[]
    def limited(*a,**k):
        calls.append(a)
        error=research.ResearchErro('blocked','bloqueado');error.http=429
        raise error
    monkeypatch.setattr(research,'baixar',limited)
    for _ in range(2):
        answer=live.respond('clima em Ubatã BA',{})
        assert 'limitou' in answer and '°C' not in answer and 'Salvador' not in answer
    assert len(calls)==1


def test_real_clock_ignores_stale_device_date(tmp_path):
    db=pc_agent.open_db(tmp_path/'clock.sqlite3')
    from zoneinfo import ZoneInfo
    context={'timezone':'America/Bahia','current_at':datetime(2000,1,1,tzinfo=timezone.utc)}
    result=pc_agent.cmd_dados_atuais(db,'que horas são agora?','u-alice','chat-one',context)
    now=datetime.now(ZoneInfo('America/Bahia'))
    assert now.strftime('%d/%m/%Y') in result and now.strftime('%H:%M') in result and '2000' not in result
    assert jdui.extrair_fences(result)
    for raw in jdui.extrair_fences(result):assert jdui.validar_mensagem(json.loads(raw))[0]
    db.close()


def test_explicit_oi_city_is_not_greeting(monkeypatch):
    seen=[]
    monkeypatch.setattr(live,'get_json',lambda base,params:seen.append(params) or photon([city('Oi','Saitama',country='JP')]))
    assert 'Oi' in live.respond('pesquise a cidade de Oi no Japão',{})
    assert 'Oi' in seen[0]['q'] and 'Japão' in seen[0]['q']


@pytest.mark.parametrize('text,expected', [('qual é o código IBGE de Ubatã BA?','Ubatã BA'),('localize código IBGE 2932309','2932309')])
def test_official_lookup_reaches_geocoder(monkeypatch,text,expected):
    seen=[]
    monkeypatch.setattr(live,'geocode',lambda city:(seen.append(city) or None,'consulta de teste'))
    assert live.respond(text,{})=='consulta de teste'
    assert seen==[expected]


def test_location_task_does_not_intercept_3d(tmp_path,monkeypatch):
    db=pc_agent.open_db(tmp_path/'no-3d-intercept.sqlite3')
    put(db,'pending-weather-3d','qual a temperatura?')
    monkeypatch.setattr(live,'geocode',lambda _:pytest.fail('Do not geocode a 3D request'))
    assert pc_agent.cmd_dados_atuais(db,'crie um modelo 3D da cidade de Salvador','u-alice','chat-one',{}) is None
    assert live.request('gosto da cidade de Salvador') is None
    db.close()


def test_document_context_and_project_isolation(tmp_path,monkeypatch):
    monkeypatch.setenv('JULIA_DOCS_PATH',str(tmp_path/'docs'))
    db=pc_agent.open_db(tmp_path/'docs.sqlite3')
    doc=docs_agent.salvar_documento(db,'TODO.md',b'Private remote control checklist.','project-chat','u-alice')
    assert pc_agent.doc_mencionado(db,'resuma a temperatura de amanhã','chat-one','u-alice')==''
    assert pc_agent.doc_mencionado(db,'resuma meu TODO.md','chat-one','u-alice')==''
    assert pc_agent.doc_mencionado(db,'resuma meu TODO.md','project-chat','u-bob')==''
    assert pc_agent.doc_mencionado(db,'resuma meu TODO.md','project-chat','u-alice')==doc['doc_id']
    assert pc_agent.doc_mencionado(db,'todo dia estudo física','project-chat','u-alice')==''
    assert pc_agent.doc_mencionado(db,'qual a temperatura todo dia?','project-chat','u-alice')==''
    assert pc_agent.doc_mencionado(db,'não leia TODO.md','project-chat','u-alice')==''
    db.close()
