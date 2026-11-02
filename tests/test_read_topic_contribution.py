"""Source contribution and a proved answer are distinct contracts."""
import pytest
import evidence_graph
import research

QUERY='Pesquise o que é estoicismo e explique a distinção entre o que depende de nós e o que não depende.'
URL='https://reference.example/stoicism'


def test_read_topic_is_preserved_without_inventing_answer_passages():
    rec={'texto':'O estoicismo valoriza a virtude e o autodomínio. '*8,
         'titulo':'Estoicismo', 'lida':True, 'final':URL,'content_scope':'page_text'}
    source=research._fonte_de(rec,{'url':URL,'titulo':'Estoicismo'},QUERY)
    assert source['relevante'] and source['status']=='aberta'
    assert not source['answer_passages']
    assert source['answerability']['state']=='TOPIC_ONLY'
    assert not evidence_graph.requirement_coverage(QUERY,[source])['complete']


@pytest.mark.parametrize('body', ['', 'Um museu de Paris abriu uma exposição de pinturas. '*8])
def test_subject_in_title_alone_is_not_a_read_contribution(body):
    source=research._fonte_de({'texto':body,'titulo':'Estoicismo','lida':bool(body),
                             'final':URL,'content_scope':'page_text'},
                            {'url':URL,'titulo':'Estoicismo'},QUERY)
    assert not source['relevante']


def test_specific_requested_limitations_still_require_answer_passages():
    source=research._fonte_de({'texto':'WebAssembly is a binary instruction format. Memory management and limitations are important topics.',
                              'lida':True}, {'url':URL,'titulo':'WebAssembly'},
                             'Documentação oficial WebAssembly memory grow limitações')
    assert not source['relevante']
