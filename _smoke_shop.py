import shopping as s

print('intencao:', s.detectar_intencao('Pesquise celulares ate R$ 1000 com 8 GB de RAM'))
print('intencao-neg:', s.detectar_intencao('qual a capital da Franca?'))
print('crit:', s.extrair_criterios('Pesquise celulares ate R$ 1.000 com 8 GB de RAM'))
print('ram-virtual:', s._extrair_ram('Galaxy com 8GB RAM + 8GB RAM Plus virtual'))
print('preco:', s.normalizar_preco('R$ 1.234,56'), s.normalizar_preco('1299,99'), s.normalizar_preco('sem preco'))
print('fmt:', s.formatar_preco(None), '|', s.formatar_preco(1234.56))

LD = ('<html><head><script type="application/ld+json">'
      '{"@context":"https://schema.org","@type":"Product",'
      '"name":"Moto G84 8GB RAM 256GB",'
      '"brand":{"@type":"Brand","name":"Motorola"},'
      '"image":"https://exemplo.com/foto.jpg",'
      '"offers":{"@type":"Offer","price":"1299.99","priceCurrency":"BRL",'
      '"availability":"https://schema.org/InStock","url":"https://loja.com/p"},'
      '"aggregateRating":{"@type":"AggregateRating","ratingValue":"4.5","reviewCount":"123"}}'
      '</script></head></html>')
prods = s.extrair_ofertas_jsonld(LD)
print('ld:', prods)
p = s.montar_produto(prods[0], 'https://loja.com/p', 'https://loja.com/p', 'Loja X')
print('produto:', p['nome'], p['preco_texto'], p['loja'], p['avaliacao'])
fence = s.fence_resultado({'produtos': [p], 'fontes': [], 'criterios': {},
                           'total_bruto': 1, 'excluidos': [], 'de_cache': False,
                           'verificado_em': 'x'})
print('fence-ok:', 'productcard' in fence)
import jdui, json
m = re_match = None
corpo = fence.split('```jdui', 1)[1].rsplit('```', 1)[0]
ok, norm, errs = jdui.validar_mensagem(json.loads(corpo))
print('jdui-valido:', ok, errs)
