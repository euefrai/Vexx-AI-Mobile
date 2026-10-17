import copy
import re
from datetime import datetime, timezone, timedelta
import pytest
import conversation_followups as follow
import live_data
import pc_agent
import shopping

WEATHER='**Clima em Salvador, Bahia, Brasil**\n\n26 °C\n\n[Fonte: Open-Meteo](https://open-meteo.com/)'


@pytest.mark.parametrize('text',['E amanhã?','Vai chover?','E no fim de semana?','E depois de amanhã?'])
def test_weather_ellipsis(text):
    value=follow.weather_request(text,WEATHER)
    assert 'Salvador, Bahia, Brasil' in value
    assert live_data.request(value)['kind']=='weather'


@pytest.mark.parametrize('text,previous',[('E amanhã?','A reunião será hoje.'),('Clima em Recife',WEATHER),('Outro assunto',WEATHER),('Não pesquise o clima',WEATHER)])
def test_weather_no_topic_hijack(text,previous):
    assert follow.weather_request(text,previous) is None


def db_fixture(tmp_path):
    return pc_agent.open_db(tmp_path/'follow.sqlite3')


def product(name,price=800):
    return dict(nome=name,modelo=name,preco=price,preco_texto=f'R$ {price}',preco_confirmado=True,
                specs={},marca='Samsung',url='https://example.org/'+name.replace(' ','-'),verificado_em='2026-10-17T12:00:00Z')


def seed(db,products,owner='u-alice',conv='follow-conv'):
    criteria=shopping.extrair_criterios('Celular Samsung até R$ 1000 com 8 GB RAM novo')
    shopping.salvar_consulta(db,owner,conv,'celular samsung',criteria,{'produtos':products,'criterios':criteria})
    return criteria


def test_new_search_retains_constraints_excludes_reference(tmp_path,monkeypatch):
    db=db_fixture(tmp_path);p=product('Galaxy A15');criteria=seed(db,[p]);calls=[]
    def search(db,owner,text,conv,**kwargs):
        calls.append(kwargs)
        return {'produtos':[p,product('Galaxy A16',900)],'criterios':criteria,'fontes':[]}
    monkeypatch.setattr(shopping,'pesquisar',search)
    reply=follow.product_reply(db,'u-alice','follow-conv','Veja outro modelo parecido com aquele e me dê o preço','Galaxy A15')
    assert 'Galaxy A16' in reply and '900' in reply
    assert calls[0]['criterios_base']['orcamento']['max']==1000
    assert calls[0]['criterios_base']['specs']['ram_fisica_gb']==8
    assert calls[0]['usar_cache'] is False
    assert [p['nome'] for p in shopping.ultima_consulta(db,'u-alice','follow-conv')['resultado']['produtos']]==['Galaxy A16']
    db.close()


def test_ambiguous_and_changed_topic_do_not_search(tmp_path,monkeypatch):
    db=db_fixture(tmp_path);seed(db,[product('Galaxy A15'),product('Galaxy A16')])
    monkeypatch.setattr(shopping,'pesquisar',lambda *a,**k:pytest.fail('Must clarify first'))
    text='Quero outro modelo parecido com aquele'
    assert follow.product_reply(db,'u-alice','follow-conv',text,'Galaxy A15 e Galaxy A16').startswith(follow.ASK_PRODUCT)
    assert follow.product_reply(db,'u-alice','follow-conv',text,'Agora estamos falando de receitas.') is None
    assert 'Qual é o nome' in follow.product_reply(db,'u-bob','follow-conv',text,'Galaxy A15')
    db.close()


def test_named_and_ordinal_selection(tmp_path,monkeypatch):
    db=db_fixture(tmp_path);seed(db,[product('Galaxy A15'),product('Galaxy A16')])
    monkeypatch.setattr(shopping,'pesquisar',lambda *a,**k:{'produtos':[],'criterios':k['criterios_base']})
    answer=follow.product_reply(db,'u-alice','follow-conv','Outro modelo parecido com o segundo e preço','Galaxy A15 e Galaxy A16')
    assert 'Galaxy A16' in answer and 'Não consegui confirmar' in answer
    db.close()


def test_history_cleanup_owner_and_conversation(tmp_path):
    db=db_fixture(tmp_path)
    seed(db,[product('Privado')],'u-bob','other-conv')
    seed(db,[product('Outro projeto')],'u-alice','other-conv')
    for _ in range(shopping.MAX_CONSULTAS_POR_CONV+2):seed(db,[product('Galaxy A15')])
    assert shopping.ultima_consulta(db,'u-bob','other-conv')['resultado']['produtos'][0]['nome']=='Privado'
    assert shopping.ultima_consulta(db,'u-alice','other-conv')
    assert db.execute("SELECT count(*) FROM shopping_consultas WHERE owner_id='u-alice' AND conv='follow-conv'").fetchone()[0]==shopping.MAX_CONSULTAS_POR_CONV
    db.close()


@pytest.mark.parametrize('selection',['Galaxy A16','o segundo','2','quero o 2'])
def test_clarification_preserves_new_budget(tmp_path,monkeypatch,selection):
    db=db_fixture(tmp_path);seed(db,[product('Galaxy A15'),product('Galaxy A16')]);calls=[]
    clarification=follow.ASK_PRODUCT+'\n1. Galaxy A15\n2. Galaxy A16'
    pc_agent.persist_messages(db,[dict(id='pick-001',owner_id='u-alice',conversation_id='follow-conv',role='user',origin='mobile',text='Outro modelo parecido até R$ 900',created_at='2026-10-17T12:00:00Z'),
                                 dict(id='pick-001-r1',owner_id='u-alice',conversation_id='follow-conv',role='assistant',origin='mobile',text=clarification,created_at='2026-10-17T12:00:01Z')],owner='u-alice')
    def search(db,owner,text,conv,**kwargs):
        calls.append(text)
        return {'produtos':[],'criterios':kwargs['criterios_base']}
    monkeypatch.setattr(shopping,'pesquisar',search)
    answer=follow.product_reply(db,'u-alice','follow-conv',selection,clarification)
    assert 'Galaxy A16' in answer
    assert 'até R$ 900' in calls[0]
    db.close()


@pytest.mark.parametrize('day,text,expected',[(16,'fim de semana',['17/10','18/10']), (17,'fim de semana',['17/10','18/10']), (18,'fim de semana',['18/10']), (17,'depois de amanhã',['19/10'])])
def test_forecast_dates(monkeypatch,day,text,expected):
    live_data._cache.clear()
    data={'timezone':'America/Bahia','current':{'time':f'2026-10-{day}T09:00','temperature_2m':26,'apparent_temperature':28,'relative_humidity_2m':80,'wind_speed_10m':12,'weather_code':2},'daily':{'time':[f'2026-10-{d}' for d in range(day,day+7)],'temperature_2m_min':[24]*7,'temperature_2m_max':[30]*7,'precipitation_probability_max':[15]*7,'weather_code':[2]*7}}
    monkeypatch.setattr(live_data,'get_json',lambda *args:data)
    data['current_units']={'temperature_2m':'°C','wind_speed_10m':'km/h'}
    answer=live_data.weather('Previsão '+text,{'coordinates':(-12.97,-38.5)},datetime(2026,10,day,12,tzinfo=timezone.utc))
    rows=[line.split(' | ')[0].removeprefix('| ') for line in answer.splitlines() if re.match(r'\| \d\d/\d\d',line)]
    assert rows==expected
    live_data._cache.clear()


def test_search_criteria_merge_and_cache_bypass(tmp_path,monkeypatch):
    db=db_fixture(tmp_path);base=seed(db,[product('Galaxy A15')]);original=copy.deepcopy(base)
    monkeypatch.setattr(shopping,'consulta_em_cache',lambda *a:pytest.fail('Must refresh search'))
    monkeypatch.setattr(shopping,'buscar_com_fallback',lambda *a,**k:([],[]))
    result=shopping.pesquisar(db,'u-alice','Outro modelo até R$ 900','follow-conv',criterios_base=base,usar_cache=False)
    assert result['criterios']['orcamento']['max']==900
    assert result['criterios']['specs']==base['specs']
    assert result['criterios']['marcas']==base['marcas']
    assert base==original
    db.close()


def test_durable_weather_chain_and_sse(tmp_path,monkeypatch):
    path=tmp_path/'follow.sqlite3';db=db_fixture(tmp_path)
    monkeypatch.setattr(live_data,'respond',lambda text,context:WEATHER if 'Salvador' in text else None)
    payload=dict(message_id='follow-user-01',owner='u-alice',conversation_id='follow-conv',text='Clima em Salvador, Bahia')
    pc_agent.ai_completa(db,payload,{'model':'test'})
    assert pc_agent.cmd_dados_atuais(db,'E amanhã?','u-bob','follow-conv',{}) is None
    assert pc_agent.cmd_dados_atuais(db,'E amanhã?','u-alice','other-conv',{}) is None
    assert pc_agent.ai_completa(db,dict(payload,message_id='follow-user-02',text='E amanhã?'),{'model':'test'})['response_text']==WEATHER
    db.close();events=[]
    monkeypatch.setattr(pc_agent,'enviar_ws',lambda ws,event:events.append(event))
    pc_agent.ai_stream_worker(path,{'model':'test'},dict(payload,message_id='follow-user-03',text='Vai chover?'),'req-follow',object(),pc_agent.SessaoStream(),{})
    assert events[-1]['type']=='ai_done' and events[-1]['response_text']==WEATHER
