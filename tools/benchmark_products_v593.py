"""Synthetic JSON-LD -> extraction -> constraints -> JDUI, seven new families.

No external HTTP, offers, or inventory are validated by this fixture benchmark.
"""
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import research
import shopping
import jdui

CASES=[('appliance','Geladeira frost free 400 litros','Geladeira frost free 400 litros'),
       ('washer','Máquina de lavar 10 kg','Máquina de lavar 10 kg'),
       ('tool','Furadeira 220 V','Furadeira 220 V'),
       ('book','Livro Dom Casmurro edição física','Livro Dom Casmurro edição física'),
       ('component','Resistor de 10 kohms','Resistor de 10 kohms'),
       ('vehicle','Pastilha de freio Corolla 2018','Pastilha de freio Corolla 2018'),
       ('sport','Bola de basquete tamanho 7','Bola de basquete tamanho 7')]


def main():
    results=[]
    with patch.object(research,'_ips_globais',lambda host:None):
        for name,query,title in CASES:
            url='https://fixture.example/produto/'+name
            node={'@context':'https://schema.org','@type':'Product','name':title,'url':url,
                  'offers':{'@type':'Offer','price':'999.90','priceCurrency':'BRL','url':url,'availability':'https://schema.org/InStock'}}
            html='<html><head><title>'+title+'</title><meta property="og:type" content="product"><script type="application/ld+json">'+json.dumps(node)+'</script></head><body><h1>'+title+'</h1><button>Adicionar ao carrinho</button></body></html>'
            pages=[]
            products=shopping._recuperar_ofertas(url,title,baixar_fn=lambda u:{'final':u,'texto':html},consulta=query,relatorio=pages)
            inside,outside=shopping.aplicar_filtros(products,shopping.extrair_criterios(query))
            fence=shopping.fence_resultado({'produtos':inside,'alternativas':[],'criterios':shopping.extrair_criterios(query)})
            ok=False
            if '```jdui' in fence:
                message=json.loads(fence.split('```jdui',1)[1].rsplit('```',1)[0]);ok=jdui.validar_mensagem(message)[0]
            results.append({'kind':'DETERMINISTIC','id':name,'query':query,'constraints':shopping.extrair_criterios(query),
                            'extracted':len(products),'accepted':len(inside),'excluded':outside,'page_diagnostics':pages,
                            'jdui_valid':ok,'cards':fence,'external_offer_confirmed':False})
    path=ROOT/'qa-artifacts/v593/products-fixture.json'
    path.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(sum(bool(r['accepted']) and r['jdui_valid'] for r in results),'/',len(results),'synthetic pipelines; external coverage not measured')
    if not all(r['accepted'] and r['jdui_valid'] for r in results):raise SystemExit(1)


if __name__=='__main__':main()
