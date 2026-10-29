"""Source-routing examples; --live-news additionally reads public news in an isolated DB."""
import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

import source_priority

EXAMPLES=('Notícias de hoje de Ubatã e região','Últimas notícias do mundo',
          'Jogos de RPG para PC','Comportamento humano e psicologia',
          'Nietzsche e niilismo','Teorema de Pitágoras exercícios',
          'Saúde e vacinação','Como plantar cacau','Pesquisar notebook gamer')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live-news',action='store_true')
    args=parser.parse_args()
    output={'scope':'ROUTING_EXAMPLES_NOT_LIVE_VALIDATION',
            'topics':len(source_priority.PACKS),
            'examples':[{'question':q,'priority':source_priority.describe(source_priority.detect(q))} for q in EXAMPLES]}
    if args.live_news:
        import os
        os.environ['JULIA_PREFERRED_NEWS_FEEDS']='1'
        import pc_agent
        import research
        query=EXAMPLES[0]
        with tempfile.TemporaryDirectory(prefix='vexx-preferred-news-') as folder:
            db=pc_agent.open_db(Path(folder)/'isolated.sqlite3')
            try:
                started=time.monotonic()
                result=research.pesquisa_rapida(db,'qa-preferred-sources',query,max_fontes=3,
                    orcamento={'max_consultas':2,'max_provedores':2,'max_tentativas':4,
                               'min_resultados':3,'timeout_total':8})
                cached=research.pesquisa_rapida(db,'qa-preferred-sources',query,max_fontes=3)
                sources=[{'title':f.get('titulo'),'url':f.get('url'),'state':f.get('status'),
                          'relevant':f.get('relevante'),'read_chars':len(f.get('texto_lido') or ''),
                          'published':f.get('publicado_em')}
                         for f in result.get('fontes',[])]
                output['live_news']={'scope':'PUBLIC_FEED_ARTICLES_AND_ISOLATED_CACHE_NO_MODEL_SYNTHESIS_NO_PRODUCTION_SESSION',
                    'query':query,'seconds':round(time.monotonic()-started,2),'state':result.get('estado'),
                    'from_cache_on_repeat':cached.get('de_cache'),'sources':sources,'steps':result.get('etapas',[])[:8]}
                assert sources and all(s['state']=='aberta' and s['relevant'] and s['published'] for s in sources),output['live_news']
                assert cached.get('de_cache'),output['live_news']
            finally:db.close()
        target=ROOT/'qa-artifacts/preferred-news-public-probe.json'
        target.write_text(json.dumps(output,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(output,ensure_ascii=False))


if __name__=='__main__':main()
