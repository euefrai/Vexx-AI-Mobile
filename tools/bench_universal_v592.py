"""Frozen-clock request contract coverage. This does not score real retrieval."""
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import query_intelligence

CASES=[
 ('A','Notebook Lenovo 16 GB RAM até R$ 3.000',['Lenovo','16','3.000']),
 ('A','Galaxy A56 256 GB, menor preço',['A56','256']),
 ('A','Tênis de basquete até R$ 300',['basquete','300']),
 ('A','Fones Bluetooth até R$ 200',['Bluetooth','200']),
 ('A','Geladeira frost free 400 litros até R$ 3500',['400','3500']),
 ('A','Livro Dom Casmurro edição física até R$ 50',['Dom Casmurro','50']),
 ('A','Furadeira 220 V até R$ 250',['220','250']),
 ('A','Resistor de 10 kohms 1/4 W',['10','1/4']),
 ('A','Pastilha de freio para Corolla 2018',['Corolla','2018']),
 ('A','Mesa de trabalho 120 cm até R$ 500',['120','500']),
 ('A','Bola de basquete tamanho 7 até R$ 150',['basquete','7','150']),
 ('B','Pesquise voos de Salvador para São Paulo daqui a 30 dias, para um adulto, com o menor preço disponível.',['Salvador','São Paulo']),
 ('C','Pesquise passagens de ônibus de Salvador para Feira de Santana para daqui a sete dias.',['Salvador','Feira de Santana']),
 ('D','Quanto vale 100 dólares em reais agora? Mostre a fonte e o horário da cotação.',['100','dólares','reais']),
 ('D','Como mudou o dólar em relação ao real nos últimos 30 dias?',['dólar','real']),
 ('D','Cotação BRL/JPY agora',['BRL/JPY']),
 ('E','O que aconteceu de mais importante em Salvador nos últimos sete dias?',['Salvador']),
 ('F','Quais eventos culturais acontecerão em Recife nas próximas duas semanas?',['Recife']),
 ('G','Estudos recentes sobre baterias de estado sólido',['baterias','estado sólido']),
 ('G','Estudos recentes sobre materiais semicondutores',['semicondutores']),
 ('H','Compare Ryzen 5 7600 e Intel Core i5-14400',['7600','i5-14400']),
 ('H','Como funciona a arquitetura Transformer?',['Transformer']),
 ('I','Compare FastAPI e Django usando documentação oficial',['FastAPI','Django']),
 ('I','Documentação oficial de asyncio em Python',['asyncio','Python']),
 ('J','Analise o PDF anexado e cite a página 3',['PDF','3']),
 ('J','Compare as colunas da planilha anexada',['planilha']),
 ('K','Procure imagens de baterias com links para as fontes',['imagens','baterias']),
 ('K','Procure vídeos sobre arquitetura Transformer e preserve a origem',['vídeos','Transformer']),
 ('L','Investigue por que fontes discordam sobre consumo de 500 W e 600 W',['500','600']),
 ('I','Cursos públicos gratuitos de Python com certificado',['públicos','Python']),
 ('I','Serviço de emissão de passaporte e documentos necessários',['passaporte']),
 ('I','Quais foram as causas da Revolução de 1930?',['1930']),
]


def main():
    now=datetime(2026,10,22,12,tzinfo=timezone.utc)
    rows=[]
    for group, query, tokens in CASES:
        request=query_intelligence.analyze(query,now)
        preserved=all(t.casefold() in request['resolved_request'].casefold() for t in tokens)
        rows.append({'group':group,'query':query,'request':request,'constraints_preserved':preserved,
                     'evidence_kind':'FIXTURE_REQUEST_CONTRACT','retrieval_quality':'not_measured'})
    result={'clock':now.isoformat(),'rows':rows,'contracts_passed':sum(r['constraints_preserved'] for r in rows),
            'total':len(rows),'limitations':'Parser coverage only. No offers, seats, editorial accuracy or live availability are proved.'}
    out=ROOT/'qa-artifacts/v592/universal-contracts.json'
    out.write_bytes(json.dumps(result,ensure_ascii=False,indent=2).encode('utf-8'))
    print(f"Request contracts {result['contracts_passed']}/{result['total']}; retrieval quality not scored")
    return 0 if result['contracts_passed']==result['total'] else 1


if __name__=='__main__':
    raise SystemExit(main())
