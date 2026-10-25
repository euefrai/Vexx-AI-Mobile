"""Synthetic HTML regressions; document reading order is the oracle."""
import web_extract as w


def extract(body):
    return w.extrair_pagina('<html><body><main>'+body+'</main></body></html>',
                            'https://example.org/synthetic',usar_trafilatura=False)


def test_preserves_inline_subject_predicate_order_once():
    text='A Empresa Clara foi fundada em 1950 por Ana e Leo e fabrica motores.'
    doc=extract('<p>A <strong>Empresa Clara</strong> foi fundada em <em>1950</em> por <a href="/ana">Ana</a> e Leo e fabrica motores.</p>')
    assert doc['texto']==text
    assert doc['paragrafos']==[text]


def test_signature_parameters_never_move_after_parentheses():
    doc=extract('<h1>Map.prototype.set()</h1><p><code>Map.prototype.set(<var>key</var>, <var>value</var>)</code> returns the map.</p>')
    assert 'Map.prototype.set(key, value) returns the map.' in doc['texto']
    assert 'set(, )' not in doc['texto']


def test_inline_negation_and_numeric_units_stay_attached():
    doc=extract('<p>A função <code>Orbe.copy()</code> <strong>não</strong> modifica o original e retorna <span>2,5</span> <abbr>kg</abbr>.</p>')
    assert 'Orbe.copy() não modifica' in doc['texto']
    assert '2,5 kg' in doc['texto']


def test_split_word_inline_does_not_gain_spaces_and_blocks_do():
    doc=extract('<p>to<em>Sorted</em></p><p>Outra linha suficientemente longa para formar um parágrafo separado.</p>')
    assert 'toSorted Outra' in doc['texto']
    assert 'to Sorted' not in doc['texto']


def test_nested_boilerplate_is_not_reintroduced_by_ordered_text():
    doc=extract('<article><p>Texto público <a href="/real">com origem</a> e informação verificável.</p><nav>MENU OCULTO</nav><script>alert(1)</script></article>')
    assert 'Texto público com origem e informação verificável.' in doc['texto']
    assert 'MENU OCULTO' not in doc['texto'] and 'alert(1)' not in doc['texto']


def test_source_passage_offsets_still_refer_to_literal_returned_text():
    doc=extract('<p>A <strong>Companhia Clara</strong> fabrica motores, geradores e equipamentos industriais.</p>')
    p=w.passage_candidates(doc['texto'])[0]
    assert doc['texto'][p['text_span']['start']:p['text_span']['end']]==p['text']
