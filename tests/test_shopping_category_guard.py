"""Product-type regressions discovered in the real public GPU search."""
import pytest

import shopping


QUERY = ('Pesquise placas de vídeo com 6 GB de VRAM para comprar no Brasil, '
         'com links diretos dos produtos e preços atuais.')


def product(name):
    return {'nome':name,'preco':1499.99,'preco_confirmado':True,'link_veredito':'verificado',
            'url':'https://example.org/produto/1','specs':{},'moeda':'BRL'}


@pytest.mark.parametrize('name',[
    'Tablet Samsung Galaxy Tab A11+, 128GB, 6gb Ram, Tela De 11, Wifi, Android 16',
    'Samsung Galaxy Tab A11+ 6GB RAM',
    'Tablet com GeForce NOW, 6GB RAM',
    'Memória RAM 6GB DDR3 para computador',
    'Memória RAM DDR4 6GB compatível com placa de vídeo RTX 3050',
    'RAM Kingston 6GB DDR3',
    'Notebook RTX 3050 6GB GDDR6',
    'Computador Gamer RTX 3050 6GB',
])
def test_known_device_or_ram_never_becomes_a_gpu(name):
    criteria=shopping.extrair_criterios(QUERY)
    assert criteria['categoria']=='placa de video' and criteria['specs']['vram_gb']==6
    inside,outside=shopping.aplicar_filtros([product(name)],criteria)
    assert not inside and 'tipo_produto_diferente' in outside[0]['excluido_codigos']


@pytest.mark.parametrize('name',[
    'Suporte para Placa de Vídeo RTX 3050 6GB',
    'Cabo PCIe para GPU RTX 3050 6GB',
    'Adaptador HDMI para placa de vídeo GeForce RTX 3050',
    'Ventoinha de reposição para RTX 3050 6GB',
    'Kit 2 Fans para Placa de Vídeo RTX 3050',
    'Riser PCIe GPU RTX 3050',
    'GPU Waterblock para GeForce RTX 3050',
])
def test_gpu_compatibility_does_not_make_an_accessory_a_graphics_card(name):
    inside,outside=shopping.aplicar_filtros([product(name)],shopping.extrair_criterios(QUERY))
    assert not inside and 'acessorio' in outside[0]['excluido_codigos']


@pytest.mark.parametrize('name',[
    'Placa de Vídeo PcYes NVIDIA GeForce RTX 3050 6GB GDDR6',
    'Placa de Vídeo MSI RTX 3050 Ventus 2X OC, 6GB RAM, GDDR6',
    'NVIDIA GeForce GTX 1660 6GB GDDR5 com 2 fans',
    'Placa de Vídeo RTX 3050 6GB com suporte incluso para PC Gamer',
    'Placa de Vídeo RTX 3050 6GB compatível com computador PCIe',
    'Intel Arc A380 6GB GDDR6',
])
def test_real_gpu_names_keep_their_gpu_identity_and_vram(name):
    assert shopping._categoria_comercial(name)=='gpu'
    inside,outside=shopping.aplicar_filtros([product(name)],shopping.extrair_criterios(QUERY))
    assert inside and not outside
    assert not inside[0]['pendencias_do_pedido'] and inside[0]['correspondencia_tipo']=='EXACT_MATCH'


def test_wrong_vram_is_rejected_and_missing_vram_stays_partial():
    criteria=shopping.extrair_criterios(QUERY)
    inside,outside=shopping.aplicar_filtros([product('Placa de Vídeo RTX 3050 8GB GDDR6')],criteria)
    assert not inside and 'vram_diferente' in outside[0]['excluido_codigos']
    inside,outside=shopping.aplicar_filtros([product('Placa de Vídeo RTX 3050')],criteria)
    assert inside and not outside and inside[0]['correspondencia_tipo']=='PARTIAL_MATCH'
    assert shopping._tier(inside[0])=='parcial'


def test_explicit_accessory_request_is_preserved():
    criteria=shopping.extrair_criterios('Pesquise suporte para placa de vídeo RTX 3050')
    inside,outside=shopping.aplicar_filtros([product('Suporte para Placa de Vídeo RTX 3050')],criteria)
    assert inside and not outside


@pytest.mark.parametrize('query',['placa de vídeo com 6GB de VRAM','placas de vídeo com 6GB de VRAM',
                                  'placas de videos com 6GB de VRAM'])
def test_gpu_singular_plural_and_accents_keep_the_same_required_type(query):
    criteria=shopping.extrair_criterios(query)
    assert criteria['categoria']=='placa de video' and criteria['specs']['vram_gb']==6
