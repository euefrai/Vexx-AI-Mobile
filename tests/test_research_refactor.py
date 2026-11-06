import pytest
import sqlite3
import time
import hermes_bridge
import providers
import tool_protocol


@pytest.mark.parametrize('width', [1, 2, 3, 7, 19, 200])
def test_native_protocol_preserves_surrounding_text_and_literal_examples(width):
    call = '<longcat_tool_call>browser_navigate<longcat_arg_key>url</longcat_arg_key></longcat_tool_call>'
    raw = 'Antes. ' + call + ' Depois.'
    s = tool_protocol.Sanitizador()
    text = ''.join(s.alimentar(raw[i:i+width]) for i in range(0, len(raw), width))
    end, errors = s.finalizar()
    assert text + end == 'Antes.  Depois.' and len(errors) == 1
    for literal in ('Use `' + call + '` como exemplo.', '```xml\n' + call + '\n```'):
        s = tool_protocol.Sanitizador()
        text = ''.join(s.alimentar(literal[i:i+width]) for i in range(0, len(literal), width))
        end, errors = s.finalizar()
        assert text + end == literal and not errors


def test_oversized_tool_body_never_leaks_its_tail(monkeypatch):
    monkeypatch.setattr(tool_protocol, 'MAX_BUFFER', 64)
    s = tool_protocol.Sanitizador()
    assert not s.alimentar('<longcat_tool_call>browser_navigate')
    assert not s.alimentar('private-argument-' * 20)
    assert not s.alimentar('private-tail</longcat_tool_')
    assert s.alimentar('call>Resposta segura') == 'Resposta segura'
    end, errors = s.finalizar()
    assert not end and errors[0]['codigo'] == 'protocolo_buffer_excedido'


def test_declared_capability_overrides_name_and_nontext_methods_are_excluded(monkeypatch):
    records = hermes_bridge.ModelCatalog([
        {'id': 'vendor/audio-text', 'capabilities': {'chat': True}},
        {'id': 'vendor/unknown', 'supportedGenerationMethods': ['embedContent']},
        {'id': 'vendor/text', 'supportedGenerationMethods': ['generateContent']},
    ])
    monkeypatch.setattr(providers.hermes_bridge, 'listar_modelos', lambda *a, **kw: records)
    monkeypatch.setattr(providers, 'chave', lambda _: '')
    ids = providers.listar_tudo()['models']
    assert 'vendor/audio-text' in ids and 'vendor/text' in ids
    assert 'vendor/unknown' not in ids
    assert providers.selection_error('vendor/audio-text', hermes_bridge.DEFAULT_PROXY_URL) is None


def test_fresh_catalog_rejects_removed_model_without_network_and_expires(monkeypatch):
    monkeypatch.setattr(providers, 'chave', lambda _: '')
    providers._remember_catalog('hermes', ['vendor/current:free'], 'http://127.0.0.1:8645/v1')
    monkeypatch.setattr(providers.hermes_bridge, 'listar_modelos', lambda *a, **kw: pytest.fail('Network on send'))
    assert providers.selection_error('vendor/removed:free', 'http://127.0.0.1:8645/v1')['codigo'] == 'modelo_indisponivel'
    assert providers.selection_error('vendor/current:free', 'http://127.0.0.1:8645/v1') is None
    assert providers.selection_error('vendor/removed:free', 'http://127.0.0.1:1234/v1') is None
    monkeypatch.setattr(providers.time, 'monotonic', lambda: 10**20)
    assert providers.selection_error('vendor/removed:free', 'http://127.0.0.1:8645/v1') is None


def test_removed_model_is_rejected_before_search_and_memory_work(tmp_path,monkeypatch):
    import pc_agent
    db=pc_agent.open_db(tmp_path/'chat.sqlite')
    proxy='http://127.0.0.1:8645/v1'
    providers._remember_catalog('hermes',['vendor/current:free'],proxy)
    monkeypatch.setattr(pc_agent,'analisar_memoria',lambda *a,**kw:pytest.fail('Memory work before model validation'))
    monkeypatch.setattr(pc_agent,'cmd_pesquisa',lambda *a,**kw:pytest.fail('Search before model validation'))
    result=pc_agent.ai_completa(db,{'message_id':'audit-model-001','conversation_id':'audit-conv',
        'model':'vendor/removed:free','text':'Pesquise profundamente SQLite'},
        {'model':'vendor/removed:free','proxy':proxy})
    assert result['codigo']=='modelo_indisponivel'
    assert not db.execute('SELECT count(*) FROM ai_requests').fetchone()[0]
    db.close()


def test_implicit_default_uses_live_free_choice_but_explicit_selection_is_not_replaced(tmp_path,monkeypatch):
    import pc_agent
    db=pc_agent.open_db(tmp_path/'chat.sqlite');proxy=hermes_bridge.DEFAULT_PROXY_URL
    providers._remember_catalog('hermes',['vendor/current:free'],proxy)
    cfg={'model':hermes_bridge.DEFAULT_MODEL,'proxy':proxy,'model_implicit':True}
    payload={'message_id':'implicit-model-001','conversation_id':'audit-conv','text':'Olá'}
    assert pc_agent.ai_preparar(db,payload,cfg)['model']=='vendor/current:free'
    explicit={**payload,'message_id':'explicit-model-001','model':hermes_bridge.DEFAULT_MODEL}
    assert pc_agent.ai_preparar(db,explicit,cfg)['codigo']=='modelo_indisponivel'
    db.close()


def test_catalog_does_not_reuse_another_credentials_configuration(monkeypatch):
    monkeypatch.setattr(providers, 'chave', lambda _: 'fixture-key-one')
    providers._remember_catalog('gemini', ['one'])
    assert providers.selection_error('gemini/two')
    monkeypatch.setattr(providers, 'chave', lambda _: 'fixture-key-two')
    assert providers.selection_error('gemini/two') is None


def legacy_index(path, count=1):
    with sqlite3.connect(path) as db:
        db.executescript('''CREATE TABLE files(path TEXT PRIMARY KEY,name TEXT,size INTEGER,
            directory INTEGER,modified REAL,generation TEXT);
            CREATE VIRTUAL TABLE names USING fts5(name,path UNINDEXED,tokenize='trigram');
            CREATE TRIGGER files_ai AFTER INSERT ON files BEGIN
                INSERT INTO names(rowid,name,path) VALUES(new.rowid,new.name,new.path); END;
            CREATE TRIGGER files_ad AFTER DELETE ON files BEGIN DELETE FROM names WHERE rowid=old.rowid; END;
            CREATE TRIGGER files_au AFTER UPDATE ON files WHEN new.name IS NOT old.name BEGIN
                DELETE FROM names WHERE rowid=old.rowid;
                INSERT INTO names(rowid,name,path) VALUES(new.rowid,new.name,new.path); END;''')
        db.executemany('INSERT INTO files VALUES (?,?,1,0,0,?)',
            ((f'/legacy/orbital-parent/document-{i}.txt', f'document-{i}.txt', 'fixture') for i in range(count)))


def test_installed_fts_schema_migrates_and_tracks_rename_delete(tmp_path):
    from pc_companion.indexer import FileIndex
    path = tmp_path/'legacy.sqlite'; legacy_index(path)
    index = FileIndex(path, [])
    try:
        deadline = time.monotonic()+5
        while index.migrating and time.monotonic()<deadline:
            time.sleep(.005)
        assert index.path_search_ready and not index.error
        assert len(index.search('orbital-parent',kind='files')['items']) == 1
        with index.db() as db:
            db.execute("UPDATE files SET name='renamed.txt',path='/legacy/new-parent/renamed.txt'")
            db.commit()
        assert not index.search('orbital-parent')['items']
        assert len(index.search('new-parent')['items']) == 1
        with index.db() as db:
            db.execute('DELETE FROM files');db.commit()
            db.execute("INSERT INTO names(names,rank) VALUES('integrity-check',1)")
        assert not index.search('renamed')['items']
    finally:
        index.stop.set()


def test_interrupted_fts_migration_rolls_back_and_can_retry(tmp_path,monkeypatch):
    from pc_companion.indexer import FileIndex
    path=tmp_path/'legacy.sqlite';legacy_index(path,2000)
    monkeypatch.setattr(FileIndex,'_metadata',lambda _:None)
    index=FileIndex(path,[]);index.stop.set()
    with index.db() as db:
        with pytest.raises(sqlite3.OperationalError):
            index._migrate_path_index(db)
        assert 'UNINDEXED' in db.execute("SELECT sql FROM sqlite_master WHERE name='names'").fetchone()[0]
        assert db.execute('SELECT count(*) FROM files').fetchone()[0] == 2000
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='names_next'").fetchone()
        index.stop.clear();index._migrate_path_index(db)
    assert index.path_search_ready
    index.stop.set()


def test_rescan_count_is_confirmed_and_survives_failure(tmp_path,monkeypatch):
    from pc_companion.indexer import FileIndex
    root=tmp_path/'files';root.mkdir();(root/'document.txt').write_text('fixture')
    index=FileIndex(tmp_path/'index.sqlite',[root]);index.scan();index.scan()
    assert index.count == 1
    def unavailable(*a,**kw):raise sqlite3.OperationalError('fixture database unavailable')
    monkeypatch.setattr('os.scandir',unavailable)
    index.scan()
    assert index.count == 1 and index.error_code
    index.stop.set()


def test_card_comparison_uses_displayed_set_without_refresh(tmp_path,monkeypatch):
    import pc_agent,shopping,conversation_followups
    db=pc_agent.open_db(tmp_path/'chat.sqlite')
    products=[{'id':str(i),'nome':f'GPU Modelo {i}','modelo':str(i),'preco_confirmado':True,
               'preco':1000+i,'preco_texto':f'R$ {1000+i}', 'verificado_em':shopping.agora_iso(),
               'url':f'https://example.org/product/{i}'} for i in range(3)]
    criteria=shopping.extrair_criterios('placa de vídeo 6 GB')
    shopping.salvar_consulta(db,'audit','conv','placa de vídeo',criteria,{'produtos':products,'criterios':criteria})
    monkeypatch.setattr(shopping,'pesquisar',lambda *a,**kw:pytest.fail('Unrequested refresh'))
    text=conversation_followups.product_reply(db,'audit','conv',
        'Compare GPU Modelo 0 com as outras opções','GPU Modelo 0, GPU Modelo 1, GPU Modelo 2')
    assert 'productcompare' in text and 'verificação original' in text
    assert len(shopping.ultima_consulta(db,'audit','conv')['resultado']['produtos'])==3
    previous = shopping.fence_comparacao(products[:2],
        [{'id':'S3','titulo':'GPU Modelo 2','url':products[2]['url']}])
    repeated = conversation_followups.product_reply(db,'audit','conv',
        'Compare GPU Modelo 0 com as outras opções', previous)
    assert 'Comparei 2 das 2 opções' in repeated
    import json, jdui
    component = json.loads(jdui.extrair_fences(repeated)[0])['blocks'][0]
    assert len(component['props']['items']) == 2
    single = '```jdui\n' + json.dumps({'version': jdui.VERSION, 'blocks': [
        {'type':'ui','component':'productcard','props':{'produto':products[1]}}]}) + '\n```'
    assert conversation_followups._displayed_products(single, products) == [products[1]]
    db.close()


def test_long_explicit_read_question_is_read_but_incidental_and_negated_links_are_not():
    import research
    url='https://www.sqlite.org/wal.html'
    assert research.urls_pedidas('Leia '+url+' e responda: em quais situações consultas em WAL podem retornar SQLITE_BUSY? Cite o trecho da página.') == [url]
    assert research.urls_pedidas('Analise esta documentação oficial: '+url+' e explique quando ocorre SQLITE_BUSY.') == [url]
    for text in ['Não leia '+url, 'Sem abrir '+url, 'O texto cita '+url+' como exemplo, explique o assunto.',
                 'Explique o código `leia '+url+'` sem abrir links.']:
        assert not research.urls_pedidas(text)


def test_identifier_survives_requirement_windows_and_source_projection(monkeypatch):
    import web_extract as w
    import research
    checkpoint = '<p>Automatic checkpoint occurs because the WAL file reaches a threshold. Writers checkpoint the WAL because it grows. </p>' * 35
    answer = 'A connection with an exclusive lock can cause SQLITE_BUSY while another process reads the WAL database.'
    html = '<html><body><div class="fancy"><h1>Write-Ahead Logging</h1><h2>Checkpoint causes</h2>' + checkpoint + '<h2>Sometimes Queries Return SQLITE_BUSY In WAL Mode</h2><p>' + answer + '</p></div></body></html>'
    query = 'When can WAL return SQLITE_BUSY? What causes the busy error?'
    doc = w.extrair_pagina(html,'https://www.sqlite.org/wal.html',query,teto=1600,usar_trafilatura=False)
    assert answer in doc['texto'] and len(doc['texto']) <= 1600
    for passage in doc['answer_passages']:
        span = passage['text_span']
        assert doc['texto'][span['start']:span['end']] == passage['text']
    source = research._fonte_de({**doc,'lida':True,'final':'https://www.sqlite.org/wal.html'},
        {'url':'https://www.sqlite.org/wal.html'},query,avaliar_relevancia=False)
    assert 'SQLITE_BUSY' in source['texto_lido'] and len(source['texto_lido']) <= 3600
    monkeypatch.setattr(research,'baixar',lambda url,**kw:(url,html))
    read,error=research.analisar_url('https://www.sqlite.org/wal.html',query)
    assert not error and 'SQLITE_BUSY' in read['texto_lido']
    import research_view
    assert 'SQLITE_BUSY' in research_view.source_card(read)['trecho']


def test_named_error_read_keeps_all_cases_and_source_scope(monkeypatch):
    import research
    cases = ['EXCLUSIVE locking mode prevents queries.',
             'CLEANUP of the last connection can block another connection.',
             'RECOVERY after a crash can temporarily lock the database.']
    context = ' Cases where SQLITE_BUSY may occur: ' + ' '.join(
        case + ' Explanation of the bounded case. ' * 12 for case in cases)
    article = {'titulo': 'Database locking', 'texto': 'Unrelated background. ' * 80 + context,
               'trecho_usado': context[:400], 'content_scope': 'abstract_only',
               'extrator': 'fixture', 'metadados': {}}
    monkeypatch.setattr(research, 'baixar', lambda url, **kw: (url, '<html>public fixture</html>'))
    monkeypatch.setattr(research, 'extrair_artigo', lambda *a, **kw: article)
    read, error = research.analisar_url('https://example.org/locking', 'When can SQLITE_BUSY occur?')
    assert not error and all(case in read['texto_lido'] for case in cases)
    assert len(read['texto_lido']) <= 3600
    assert read['content_scope'] == 'abstract_only' and read['full_text_fetched'] is False


def test_error_excerpt_prefers_explanation_over_numbered_contents():
    from web_extract import melhor_trecho
    toc = '1. Overview 2. WAL file 3. Automatic checkpoint 4. Checkpoint behavior 5. Persistence 6. Shared memory 7. Read only 8. SQLITE_BUSY 9. References 10. Summary.'
    answer = 'An exclusive connection causes SQLITE_BUSY. During cleanup another connection can also get SQLITE_BUSY.'
    excerpt = melhor_trecho(toc + '\n\n' + answer, 'When does SQLITE_BUSY occur?', 300)
    assert answer in excerpt
