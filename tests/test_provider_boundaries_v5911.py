import research
import search_orchestrator as orch


def test_advertisement_does_not_consume_organic_result_limit(monkeypatch):
 html='<a class="result__a" href="https://duckduckgo.com/y.js?ad_domain=shop.example">Camera ZX7</a><a class="result__a" href="https://example.org/zx7">Camera ZX7 manual</a><a class="result__snippet">Camera ZX7 specifications.</a>'
 monkeypatch.setattr(research,'baixar',lambda *a,**kw:('ok',html))
 rows=research.buscar_ddg('Camera ZX7',max_resultados=1)
 assert len(rows)==1 and rows[0]['url']=='https://example.org/zx7'
 assert 'SEARCH_ADVERTISEMENT' in orch._context_mismatch({'titulo':'Camera ZX7','url':'https://duckduckgo.com/y.js?ad_domain=shop.example'},'Camera ZX7')


def test_snippet_does_not_leak_from_the_next_result(monkeypatch):
 html='<a class="result__a" href="https://example.org/help">Generic help</a><a class="result__a" href="https://example.org/zx7">Camera ZX7</a><a class="result__snippet">Camera ZX7 specifications.</a>'
 monkeypatch.setattr(research,'baixar',lambda *a,**kw:('ok',html))
 rows=research.buscar_ddg('Camera ZX7',max_resultados=2)
 assert rows[0]['trecho']=='' and 'ZX7' in rows[1]['trecho']
