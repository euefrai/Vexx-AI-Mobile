"""Pipeline regressions, not evidence of live recall or semantic quality."""
from datetime import datetime
from zoneinfo import ZoneInfo
import sqlite3

import pytest
import research


def test_promising_original_after_six_generic_results_receives_a_read_slot():
    db=sqlite3.connect(':memory:');research.criar_tabelas(db)
    found=[{'titulo':'Guia turístico de Recife','url':f'https://travel{i}.example/recife',
            'trecho':'Turismo em Recife','tipo':'pagina'} for i in range(6)]
    original={'titulo':'Intervenções no trânsito','url':'https://publisher.example/intervencoes',
              'source_recovery':{'method':'publisher_link'},'tipo':'noticia'}
    found.append(original)
    calls=[]
    today=datetime.now(ZoneInfo('America/Bahia')).date().isoformat()
    def read(url):
        calls.append(url)
        return {'titulo':'Recife registra acidente de trânsito' if url==original['url'] else 'Guia turístico de Recife',
                'texto':('Um acidente ocorreu hoje em Recife. '*25 if url==original['url'] else 'Passeios e turismo em Recife. '*25),
                'lida':True,'final':url,'metadados':{'publicado_em':today}}
    result=research.pesquisa_rapida(db,'qa','Notícias sobre acidente em Recife hoje',lambda _:found,read)
    assert original not in found[:6]  # Reproduces the previous positional cut.
    assert original['url'] in calls and len(calls)==6
    assert result['fontes_uteis']==1
    source=next(s for s in result['fontes'] if s['url']==original['url'])
    assert source['status']=='aberta' and source['relevante']
    trace=next(s for s in result['candidate_reservoir']['items'] if s['url']==original['url'])
    assert trace['selected'] and trace['returned'] and trace['extracted_chars']>0
    assert trace['evidence_ref']==source['id'] and trace['content_state']=='READ_PARTIAL'
    db.close()


def test_diversity_uses_same_priority_without_promoting_index_or_expanding_reads():
    candidates=[{'titulo':'Solar news','url':f'https://one.example/article{i}'} for i in range(8)]
    other={'titulo':'Solar news','url':'https://two.example/article'}
    index={'titulo':'Solar news','url':'https://index.example/search?q=solar'}
    result=research.selecionar_candidatos_leitura(candidates+[index,other],'Solar news')
    assert len(result)==6 and other in result and index not in result
    assert result[:2]==[candidates[0],other]


def test_feed_media_and_malformed_targets_do_not_consume_article_read_slots():
    rows=[{'url':'https://news.google.com/rss/articles/x','content_scope':'feed_metadata'},
          {'url':'https://upload.wikimedia.org/p.jpg','origem':'commons','tipo':'imagem'},
          {'url':'https://[invalid','titulo':'Invalid'}]
    assert research.selecionar_candidatos_leitura(rows,'notícias')==[]


@pytest.mark.parametrize('error,loss',[
    ('bloqueado','FETCH_BLOCKED'),('rate_limited','FETCH_BLOCKED'),('rede','FETCH_FAILED')])
def test_read_failure_is_not_mislabelled_as_topic_rejection(error,loss):
    row={'url':'https://publisher.example/report','titulo':'Report'}
    trace=research.candidate_report([row],[],'Report',read_outcomes={row['url']:{'error':error}},
        selected_urls={row['url']},returned_urls=set())['items'][0]
    assert trace['losses']==[loss] and not trace['read']


def test_empty_extraction_budget_omission_and_constraint_rejection_are_distinct():
    rows=[{'url':f'https://publisher.example/{i}','titulo':str(i)} for i in range(3)]
    source={**rows[2],'status':'aberta','relevante':False,
            'vertical':{'reasons':['TEMPORAL_MISMATCH','ENTITY_MISMATCH']}}
    trace=research.candidate_report(rows,[source],'notícias',
        read_outcomes={rows[0]['url']:{'chars':0},rows[2]['url']:{'chars':200}},
        selected_urls={rows[0]['url'],rows[2]['url']},returned_urls=set())['items']
    assert trace[0]['losses']==['EXTRACTION_EMPTY']
    assert trace[1]['losses']==['READ_BUDGET_NOT_SELECTED']
    assert trace[2]['losses']==['DATE_MISMATCH','HARD_CONSTRAINT_MISMATCH']
    assert trace[2]['state']=='REJECTED' and trace[2]['read']


def test_old_retrieval_cache_is_not_reused_after_selection_change():
    db=sqlite3.connect(':memory:');research.criar_tabelas(db)
    research.cache_put(db,'qa','web','solar',{'retrieval_version':'5.9.9','fontes':[]},600)
    calls=[]
    result=research.pesquisa_rapida(db,'qa','solar',lambda q:calls.append(q) or [],lambda _:None)
    assert calls and not result['de_cache'] and result['retrieval_version']=='5.9.9.1'
    db.close()
