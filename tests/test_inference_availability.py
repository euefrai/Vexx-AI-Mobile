import pytest

import hermes_bridge as bridge
import inference_status as status
import pc_agent


@pytest.fixture(autouse=True)
def clean_cache():
    status._CACHE.clear()
    yield
    status._CACHE.clear()


def config(**extra):
    return {'model':bridge.DEFAULT_MODEL, 'model_implicit':True,
            'proxy':bridge.DEFAULT_PROXY_URL, 'max_tokens':100, 'fallbacks':[], **extra}


def test_missing_implicit_default_uses_only_a_listed_free_model(monkeypatch):
    calls=[]
    def catalog(base, timeout):
        calls.append(timeout)
        return ['premium/model', 'vendor/current:free']
    monkeypatch.setattr(bridge,'listar_modelos',catalog)
    assert status.effective_models(config(),[bridge.DEFAULT_MODEL])==['vendor/current:free']
    assert status.effective_models(config(),[bridge.DEFAULT_MODEL])==['vendor/current:free']
    assert len(calls)==1 and 0<calls[0]<=2


@pytest.mark.parametrize('cfg,models',[
    (config(model_implicit=False),[bridge.DEFAULT_MODEL]),
    (config(),['user/chosen-model']),
    ({},[bridge.DEFAULT_MODEL]),
])
def test_explicit_models_are_never_changed_or_inspected(monkeypatch,cfg,models):
    monkeypatch.setattr(bridge,'listar_modelos',lambda *_a,**_k:pytest.fail('Unexpected catalog call'))
    assert status.effective_models(cfg,models)==models


@pytest.mark.parametrize('catalog',[[bridge.DEFAULT_MODEL,'other/model:free'],['premium/model'],[],[{},None]])
def test_keep_default_when_available_or_no_free_replacement(monkeypatch,catalog):
    monkeypatch.setattr(bridge,'listar_modelos',lambda *_a,**_k:catalog)
    assert status.effective_models(config(),[bridge.DEFAULT_MODEL])==[bridge.DEFAULT_MODEL]


def test_failed_catalog_keeps_original_generation_path(monkeypatch):
    def failed(*_a,**_k):raise bridge.BridgeErro('private raw body','indisponivel')
    monkeypatch.setattr(bridge,'listar_modelos',failed)
    assert status.effective_models(config(),[bridge.DEFAULT_MODEL])==[bridge.DEFAULT_MODEL]


def test_complete_and_stream_use_the_same_effective_model(monkeypatch):
    monkeypatch.setattr(bridge,'listar_modelos',lambda *_a,**_k:['vendor/current:free'])
    seen=[]
    def generate(base,models,*_a,**_k):
        seen.append(models);return {'texto':'Supported answer', 'model_usado':models[0]}
    monkeypatch.setattr(bridge,'tentar_modelos',generate)
    monkeypatch.setattr(bridge,'chat_stream_fb',generate)
    assert pc_agent.gerar_texto(config(),[])['model_usado']=='vendor/current:free'
    assert pc_agent.gerar_stream(config(),[bridge.DEFAULT_MODEL],[],lambda *_:None)['model_usado']=='vendor/current:free'
    assert seen==[['vendor/current:free']]*2


def test_cancelled_stream_does_not_start_model_discovery(monkeypatch):
    monkeypatch.setattr(bridge,'listar_modelos',lambda *_a,**_k:pytest.fail('Cancelled discovery'))
    monkeypatch.setattr(bridge,'chat_stream_fb',lambda *_a,**_k:{'cancelled':True})
    assert pc_agent.gerar_stream(config(),[bridge.DEFAULT_MODEL],[],lambda *_:None,lambda:True)['cancelled']


@pytest.mark.parametrize('code,expected',[
    ('modelo-nao-encontrado','não está disponível'),('sem_chave','sem chave'),
    ('auth','autenticação'),('rate_limit','limite'),('timeout','prazo'),('vazia','vazia'),
    ('private-token-secret','Não foi possível'),
])
def test_failure_notice_preserves_sources_without_exposing_raw_error(code,expected):
    text='Trecho lido [S1]. https://source.example/article'
    result=status.with_failure_notice(text,code)
    assert expected in result and result.endswith(text)
    assert 'private-token-secret' not in result
    assert status.with_failure_notice('',code)==''


def test_research_fallback_keeps_evidence_and_explains_model_failure():
    sources=[{'id':'S1','url':'https://source.example/article','titulo':'Fotossíntese',
              'trecho':'Fotossíntese converte energia luminosa em energia química.',
              'texto_lido':'Fotossíntese converte energia luminosa em energia química.',
              'status':'aberta','relevante':True}]
    result=pc_agent._fallback_sem_inferencia('fotossíntese',
        {'fontes':sources,'inference_error_code':'modelo-nao-encontrado'},None)
    assert 'modelo selecionado não está disponível' in result
    assert 'source.example/article' in result and 'Fotossíntese' in result


@pytest.mark.parametrize('reply',[
    'A fotossíntese converte energia luminosa.',
    'A fotossíntese converte energia luminosa [S99].',
    ('Uma explicação longa sem fonte. '*10)+'\n\nUma conclusão citada [S1].',
    'Citação em código não é referência: `[S1]`.',
    '"Uma frase inventada atribuída a um autor sem nenhum trecho literal recuperado." — Autor [S1]',
])
def test_unusable_citations_preserve_real_sources_instead_of_unchecked_prose(reply):
    sources=[{'id':'S1','url':'https://source.example/article','titulo':'Fotossíntese',
              'status':'aberta','relevante':True,'texto_lido':'Fotossíntese transforma energia luminosa em energia química.',
              'trecho':'Fotossíntese transforma energia luminosa em energia química.'}]
    result=status.grounded_reply(reply,sources,'fotossíntese')
    assert 'não passou pela conferência' in result
    assert '[S1]' in result and 'source.example/article' in result
    assert 'frase inventada' not in result and '[S99]' not in result


def test_cited_reply_is_preserved_without_claiming_semantic_verification():
    text='Fotossíntese transforma energia luminosa em energia química. [S1]'
    source={'id':'S1','status':'aberta','texto_lido':text,'url':'https://source.example/article'}
    assert status.grounded_reply(text,[source],'fotossíntese')==text
    assert status.grounded_reply('Sem leitura.',[],'fotossíntese')=='Sem leitura.'


def test_unread_or_irrelevant_source_cannot_validate_a_citation():
    read={'id':'S1','status':'aberta','texto_lido':'Apenas fonte lida.',
          'trecho':'Apenas fonte lida.','url':'https://source.example/read'}
    for rejected in (
        {'id':'S2','status':'bloqueada','texto_lido':'Snippet de busca'},
        {'id':'S2','status':'aberta','texto_lido':'Texto alheio','relevante':False},
    ):
        result=status.grounded_reply('Alegação baseada na fonte bloqueada [S2].',
                                     [read,rejected],'fonte')
        assert 'não passou pela conferência' in result
        assert 'Alegação baseada' not in result
