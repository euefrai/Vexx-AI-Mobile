"""Challenge markup regressions; fixtures do not certify access to real stores."""
import pytest

import research


ARTICLE = '<p>' + ('This article explains a software configuration and its available settings. ' * 7) + '</p>'
CHALLENGE = ("<script>window._cf_chl_opt = {cType:'managed'};"
             "var script='/cdn-cgi/challenge-platform/h/b/orchestrate/chl_page/v1';</script>")


@pytest.mark.parametrize('tag', ['pre', 'code', 'samp', 'kbd'])
def test_literal_diagnostic_examples_do_not_block_a_readable_article(tag):
    page = ('<main><h1>Database configuration guide</h1>' + ARTICLE +
            f'<{tag}>Access denied; request blocked; checking your browser</{tag}></main>')
    assert not research.pagina_bloqueada(page)


@pytest.mark.parametrize('page', [
    '<pre>Access denied</pre>',
    '<code>Checking your browser</code>',
    '<main><h1>Access denied</h1>' + ARTICLE + '<code>ordinary example</code></main>',
    '<main><h1>Store</h1>' + ARTICLE + '<p>Verify you are human</p></main>',
    CHALLENGE,
    CHALLENGE.replace('window._cf_chl_opt', "window['_cf_chl_opt']"),
    CHALLENGE.replace('<script>', '<script>(function(){').replace('</script>', '})();</script>'),
    CHALLENGE + '<script type="application/ld+json">{"@type":"Product","offers":{"price":"100"}}</script>',
])
def test_real_challenge_indications_are_not_ignored(page):
    assert research.pagina_bloqueada(page)


def test_widget_and_protection_notice_do_not_mean_the_page_is_gated():
    page = ('<main><h1>Product details</h1>' + ARTICLE +
            '<div class="g-recaptcha" data-sitekey="public-key"></div>'
            '<footer>This site is protected by reCAPTCHA and the Google Privacy Policy applies.</footer></main>')
    assert not research.pagina_bloqueada(page)


@pytest.mark.parametrize('kind', ['application/json', 'application/ld+json', 'text/plain',
                                  'text/x-template', 'text/html', 'application/xml',
                                  'importmap', 'speculationrules', 'javascript'])
@pytest.mark.parametrize('quoted',[True,False])
def test_data_script_containing_challenge_example_is_not_executable_challenge(kind,quoted):
    value='"'+kind+'"' if quoted else kind
    page = CHALLENGE.replace('<script>', '<script type=' + value + '>')
    page += '<h1>Documentation</h1>' + ARTICLE
    assert not research.pagina_bloqueada(page)


@pytest.mark.parametrize('kind',['text/javascript','application/javascript','module',
                                 'application/ecmascript','application/x-javascript'])
def test_executable_script_types_keep_real_managed_challenge_detection(kind):
    page=CHALLENGE.replace('<script>','<script type="'+kind+'">')
    assert research.pagina_bloqueada(page)


def test_normal_cloudflare_script_is_not_a_managed_interstitial():
    page = ('<script>window._cf_chl_opt={}; var src="/cdn-cgi/challenge-platform/h/b/scripts/jsd/main.js";</script>'
            '<h1>Product details</h1>' + ARTICLE)
    assert not research.pagina_bloqueada(page)


def test_javascript_bundle_quoting_a_managed_challenge_is_not_itself_a_gate():
    page=('<script>const example="window._cf_chl_opt = {}; /cdn-cgi/challenge-platform/h/b/orchestrate/chl_page/v1";</script>'
          '<h1>Integration documentation</h1>'+ARTICLE)
    assert not research.pagina_bloqueada(page)


@pytest.mark.parametrize('wrapper',['<!-- {} -->','<template>{}</template>','<style>{}</style>'])
def test_managed_challenge_example_in_inactive_markup_does_not_execute(wrapper):
    page=wrapper.format(CHALLENGE)+'<h1>Product details</h1>'+ARTICLE
    assert not research.pagina_bloqueada(page)


@pytest.mark.parametrize('instruction',['Verify you are human','Complete o captcha'])
def test_interactive_instructions_are_not_discarded_as_diagnostic_examples(instruction):
    page='<main><h1>Store</h1>'+ARTICLE+'<code>'+instruction+'</code></main>'
    assert research.pagina_bloqueada(page)


def test_escaped_script_example_does_not_activate_a_challenge_marker():
    page = '<main><h1>Integration guide</h1>' + ARTICLE + '<pre>' + CHALLENGE.replace('<', '&lt;').replace('>', '&gt;') + '</pre></main>'
    assert not research.pagina_bloqueada(page)


def test_escaped_challenge_element_in_documentation_is_not_real_markup():
    page=('<main><h1>Markup reference</h1>'+ARTICLE+
          '<pre>&lt;div id="cf-browser-verification"&gt;&lt;/div&gt;</pre></main>')
    assert not research.pagina_bloqueada(page)


def test_reader_keeps_an_article_with_literal_diagnostics(monkeypatch):
    page='<main><h1>Configuration guide</h1>'+ARTICLE+'<pre>Access denied</pre></main>'
    monkeypatch.setattr(research,'baixar',lambda url,**kwargs:(url,page))
    result=research._recuperar_um({'url':'https://example.org/reference'},None,1)
    assert result['lida'] and result['texto']


def test_reader_reports_script_only_interstitial_as_blocked(monkeypatch):
    monkeypatch.setattr(research,'baixar',lambda url,**kwargs:(url,CHALLENGE))
    with pytest.raises(research.ResearchErro) as error:
        research._recuperar_um({'url':'https://example.org/product'},None,1)
    assert error.value.codigo=='bloqueado'
