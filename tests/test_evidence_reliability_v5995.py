"""Synthetic contrast pairs; not a real-source accuracy benchmark."""
import evidence_graph as eg
import query_intelligence as qi
import web_extract as wx


def coverage(question, text, **extra):
    return eg.requirement_coverage(question,[dict(url='https://example.org/fixture',lida=True,texto=text,**extra)])


def test_two_segment_operation_is_not_language_plus_method():
    req=qi.answer_requirements('Como funciona JavaScript Object.assign, qual sua sintaxe?')
    assert {r['entity'] for r in req}=={'Object.assign'}
    assert coverage('Como funciona JavaScript Object.assign, qual sua sintaxe?',
                    'Object.assign(target, source) returns the target object.')['complete']


def test_causal_heading_retains_partial_with_literal_context_only():
    q='Quais as causas e consequências da Revolta do Vale?'
    text='Principais consequências da Revolta do Vale: Reforma: o conflito resultou na alteração da legislação.'
    cov=coverage(q,text)
    assert {r['attribute']:r['state'] for r in cov['requirements']}=={'causes':'DISCOVERED','consequences':'PARTIALLY_SUPPORTED'}
    assert not cov['complete'] and cov['passages'][0]['text']==text
    assert not coverage(q,text.replace('Revolta do Vale','Revolta do Porto'))['passages']


def test_unkeyed_options_and_question_text_cannot_become_facts():
    q='Quais as causas e consequências da Revolta do Vale?'
    question='Assinale a alternativa correta sobre a Revolta do Vale.'
    option='a) A Revolta do Vale foi causada pela cobrança de novos impostos.'
    for text in (question,option,question+option,'Gabarito: B. '+option):
        assert not coverage(q,text)['passages']
    # An external label cannot promote an unkeyed literal option.
    assert eg._passage_support(qi.answer_requirements(q)[0],{'text':option,'source_role':'CORRECT_ANSWER'}, {}) is None


def test_explicit_explanation_survives_options_and_keeps_offsets():
    q='Quais as causas e consequências da Revolta do Vale?'
    text=('Assinale a alternativa correta. a) A Revolta do Vale foi causada por uma epidemia. '
          'b) A Revolta do Vale foi causada pela mineração. '
          'Explicação: A Revolta do Vale foi causada pela cobrança de novos impostos.')
    passages=wx.passage_candidates(text)
    assert [p['source_role'] for p in passages]==['ANSWER_OPTION','EXPLANATION']
    for p in passages:
        s=p['text_span'];assert text[s['start']:s['end']]==p['text']
    cov=coverage(q,text)
    assert len(cov['passages'])==1 and cov['passages'][0]['source_role']=='EXPLANATION'
    assert 'epidemia' not in cov['passages'][0]['text']


def test_local_operation_alias_is_partial_never_complete_or_cross_interface():
    q='Como funciona Namespace.Buffer.resize?'
    text='resize(newSize) method returns the resized buffer to the caller.'
    cov=coverage(q,text,titulo='Namespace.Buffer.resize - API')
    assert cov['passages'] and not cov['complete']
    assert cov['requirements'][0]['state']=='PARTIALLY_SUPPORTED'
    assert not coverage(q,text,titulo='Other.Buffer.resize - API')['passages']
    assert not coverage(q,'Other.Buffer.resize(newSize) returns the resized buffer.',titulo='Namespace.Buffer.resize')['passages']


def test_html_short_headings_lists_tables_code_and_operators_keep_order():
    html='''<main><h1>Demo.copy()</h1><h2>Syntax</h2><pre><code>Demo.copy(x &lt; 3 &amp;&amp; y != 2)</code></pre>
      <h2>Limits</h2><ul><li>It does <b>not</b> modify the original.</li></ul>
      <table><tr><th>Weight</th><td>2.5 <abbr>kg</abbr></td></tr></table>
      <p>See <a href="https://example.org/reference">the original source</a> for more details.</p></main>'''
    doc=wx.extrair_pagina(html,'https://example.org/fixture',usar_trafilatura=False)
    assert 'Demo.copy(x < 3 && y != 2)' in doc['texto']
    assert 'not modify the original' in doc['texto'] and 'Weight 2.5 kg' in doc['texto']
    assert {'Syntax','Limits'}<={s['titulo'] for s in doc['secoes']}
    assert doc['texto'].count('Demo.copy(x')==1
    assert any(a['url']=='https://example.org/reference' for a in doc['links'])
