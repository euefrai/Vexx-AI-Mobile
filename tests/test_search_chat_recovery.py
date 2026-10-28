"""Regressions from actual chat screenshots; external data fixtures are explicit."""
import json
from datetime import datetime, timezone
import pytest
import pc_agent, research, shopping, query_intelligence as qi, search_orchestrator as orch
import live_data, steam_offers, jdui

@pytest.mark.parametrize('text', ['pesquisa por minecraft','pesquisa sobre Minecraft','pesquisa por jogos em promoção na steam','pesquisa por algumas placas de videos que tem 6 de vram'])
def test_explicit_search_requests_trigger_search(text):
    assert pc_agent.intencao_pesquisa(text)

@pytest.mark.parametrize('text', ['pesquisa por Minecraft','pesquisa sobre Minecraft','faça uma pesquisa por Minecraft'])
def test_search_scaffold_not_sent_as_subject(text):
    assert qi.topic_profile(text)['focused_query'].casefold() == 'minecraft'
    assert orch.query_plan(text)[0]['query'].casefold() == 'minecraft'
    assert research.consulta_de_pesquisa(text).casefold() == 'minecraft'

@pytest.mark.parametrize('text', ['pesquisa por placas de videos com 6GB','pesquise placa de vídeo 6GB','mostre placas de vídeo'])
def test_hardware_is_not_a_video_gallery(text,tmp_path,monkeypatch):
    assert not qi.requested_media(text)
    monkeypatch.setattr(research,'pesquisa_rapida',lambda *a,**kw:pytest.fail('Hardware intercepted by media command'))
    db=pc_agent.open_db(tmp_path/'qa.sqlite')
    try: assert pc_agent.cmd_pesquisa(db,text,'local','qa-chat') == ''
    finally: db.close()
    assert shopping.detectar_intencao(text)
    assert shopping.extrair_criterios(text)['categoria'] in ('placa de vídeo','placa de video')

def test_real_gallery_stays_media():
    assert qi.requested_media('pesquise vídeos sobre placas de vídeo')
    assert qi.requested_media('mostre fotos de placas de videos')
    assert qi.requested_media('pesquise vídeos de jogos na Steam')
    assert qi.requested_media('pesquise documentos PDF',documents=True)
    assert not qi.requested_media('pesquise documentos PDF')

@pytest.fixture
def catalog():
    return {'specials':{'items':[{'id':123,'type':0,'name':'Jogo de teste','discounted':True,
        'final_price':2490,'original_price':4990,'currency':'BRL','discount_expiration':4102444800}]}}

@pytest.mark.parametrize('text', ['pesquisa por jogos em promoção na steam','mostre ofertas atuais da Steam','busque descontos na Steam'])
def test_steam_request(text):
    assert live_data.request(text)['kind']=='steam_offers'

@pytest.mark.parametrize('text', ['pesquisa por jogos de corrida em promoção na steam','ofertas Steam até 50 reais','Minecraft na Steam em promoção','explique promoções na Steam','não pesquise promoções na Steam','pesquise vídeos de ofertas Steam'])
def test_steam_does_not_drop_other_requirements(text):
    assert (live_data.request(text) or {}).get('kind') != 'steam_offers'

@pytest.mark.parametrize('change', [{'currency':'USD'},{'final_price':True},{'final_price':6000}, {'discount_expiration':1},{'id':'123'},{'type':1},{'discounted':False}])
def test_steam_rejects_invalid_or_expired_offers(catalog,change):
    catalog['specials']['items'][0].update(change)
    result=steam_offers.response(lambda *a:catalog)
    assert 'não encontrei ofertas válidas' in result
    assert 'productcard' not in result

def test_steam_product_cards_persist_and_replay(tmp_path,monkeypatch,catalog):
    monkeypatch.setattr(live_data,'get_json',lambda *a:catalog)
    monkeypatch.setattr(live_data,'cached',lambda k,ttl,fn:fn())
    monkeypatch.setattr(pc_agent,'gerar_texto',lambda *a,**kw:pytest.fail('Catalog must not infer prices'))
    path=tmp_path/'qa.sqlite';db=pc_agent.open_db(path)
    payload={'message_id':'steam-user-001','conversation_id':'qa-steam','owner':'u-test','text':'pesquisa por jogos em promoção na steam'}
    result=pc_agent.ai_completa(db,payload,{'model':'test'})
    text=result['response_text']
    assert 'lista completa' in text
    _,blocks,errors=jdui.normalizar(text)
    assert not errors and blocks
    ui=next(b for msg in blocks for b in msg['blocks'] if b.get('component')=='productcard')
    product=ui['props']['produto']
    assert product['url']=='https://store.steampowered.com/app/123/'
    assert product['preco']=='R$ 24,90'
    assert product['link_veredito']=='parcial'
    db.close();db=pc_agent.open_db(path)
    replay=pc_agent.ai_completa(db,payload,{'model':'test'})
    assert replay['replay'] and replay['response_text']==text
    assert db.execute("SELECT count(*) FROM messages WHERE role='assistant' AND owner_id='u-test'").fetchone()[0]==1
    db.close()

def test_minecraft_runs_retrieval_before_inference(tmp_path,monkeypatch):
    db=pc_agent.open_db(tmp_path/'qa.sqlite');calls=[]
    source={'id':'S1','titulo':'Minecraft','url':'https://www.minecraft.net/pt-br',
            'status':'aberta','relevante':True,'texto':'Minecraft é um jogo de construção e exploração.'}
    def search(*a,**kw): calls.append(a[2]);return {'fontes':[source]}
    monkeypatch.setattr(research,'pesquisa_rapida',search)
    messages,extras=pc_agent.ai_montar_mensagens(db,'qa-chat',{'system':'Test','context':4,'pesquisa_web':True,'memoria_global':False},'pesquisa por Minecraft','u-test',{})
    assert calls==['pesquisa por Minecraft']
    assert extras['pesquisa_executada'] and extras['fontes']==[source]
    assert 'minecraft.net' in '\n'.join(m['content'] for m in messages)
    db.close()

def test_gpu_vram_requirement_reaches_queries_and_filters():
    text='pesquisa por algumas placas de videos que tem 6 de vram'
    criteria=shopping.extrair_criterios(text)
    assert criteria['specs']['vram_gb']==6
    assert criteria['marcas']==[]
    queries=shopping._consultas_produto(criteria,text)
    assert queries and all('6GB VRAM' in q for q in queries)
    assert queries[0].startswith('GPU 6GB VRAM')
    products=[{'nome':'Placa de vídeo GTX 1660 6GB','specs':{}},
              {'nome':'Placa de vídeo RTX 3060 12GB','specs':{}},
              {'nome':'Placa de vídeo GTX 1660','specs':{}},
              {'nome':'Notebook GPU RTX 8GB RAM','specs':{}}]
    accepted,rejected=shopping.aplicar_filtros(products,criteria)
    assert products[0] in accepted
    assert 'VRAM não informada' in products[2]['pendencias_do_pedido']
    assert products[1] in rejected and 'vram_diferente' in products[1]['excluido_codigos']
    assert products[3] in rejected and 'tipo_produto_diferente' in products[3]['excluido_codigos']

def test_retrieved_source_cards_survive_model_sources_heading():
    source={'id':'S1','titulo':'Minecraft oficial','url':'https://www.minecraft.net/pt-br',
            'status':'aberta','relevante':True,'texto':'Minecraft é um jogo.'}
    draft='Minecraft.\n\n## Fontes:\n- [Site](https://www.minecraft.net/)'
    text=pc_agent.anexar_fontes(draft,[source],pesquisa_executada=True,consulta='Minecraft')
    _,uis,errors=jdui.normalizar(text)
    assert not errors
    cards=[b for ui in uis for b in ui['blocks'] if b.get('component')=='sources']
    assert len(cards)==1 and cards[0]['props']['items'][0]['url']==source['url']
    # A second finalization must replace the recovered card, not duplicate it.
    again=pc_agent.anexar_fontes(text,[source],pesquisa_executada=True,consulta='Minecraft')
    _,uis,errors=jdui.normalizar(again)
    assert sum(b.get('component')=='sources' for ui in uis for b in ui['blocks'])==1

@pytest.mark.parametrize('url',['https://www.terabyteshop.com.br/hardware/placas-de-video','https://www.nvidia.com/pt-br/geforce/graphics-cards/'])
def test_catalogs_remain_research_sources_but_never_product_destinations(url):
    import source_check
    assert source_check.url_de_catalogo_produtos(url)
    assert not shopping.url_exibivel(url)
    assert not shopping._link_do_produto({'url':url})
    # Source rendering uses the regular URL gate; it must preserve research links.
    source={'id':'S1','titulo':'Catálogo de GPUs','url':url,'status':'encontrada','relevante':True}
    import research_view
    fence=research_view.contextual_fence([source])
    assert url in fence
    assert not source_check.url_de_catalogo_produtos(url.rstrip('/')+'/modelo-6gb')
