"""Documentos + memória que aprende: extração, relevância, comandos e relay."""
import base64
import asyncio
import io
import json
import os
import sqlite3
import sys
import threading
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from starlette.requests import Request
import docs_agent
import pc_agent
import server


def setup_module():
    os.environ['JULIA_USERNAME'] = 'efrai'
    os.environ['JULIA_PASSWORD_HASH'] = PasswordHasher().hash('strong-example-password')
    os.environ['JULIA_SESSION_SECRET'] = 'a' * 64
    os.environ['JULIA_AGENT_TOKEN'] = 'b' * 64
    server.login_failures.clear()


def login(client):
    r = client.post('/api/login', json={'username': 'efrai', 'password': 'strong-example-password'})
    assert r.status_code == 200, r.text
    return r.json()['csrf']


def mem_db(tmp_path):
    db = pc_agent.open_db(tmp_path / 'mem.sqlite3')
    cols = [c[1] for c in db.execute("PRAGMA table_info(documents)").fetchall()]
    assert 'summary' in cols
    return db


# ── Extração ──────────────────────────────────────────────────────────
def test_txt_csv_html(tmp_path):
    db = mem_db(tmp_path)
    m = docs_agent.salvar_documento(db, 'notas.txt', ('Olá mundo. ' * 500).encode('utf-8'), 'conv-1')
    assert m['chunks'] >= 1 and m['chars'] > 100
    assert docs_agent.obter_texto(db, m['doc_id'])[:9] == 'Olá mundo'
    m2 = docs_agent.salvar_documento(db, 'dados.csv', b'nome,idade\nana,30\nbob,25\n', 'conv-1')
    assert 'ana | 30' in docs_agent.obter_texto(db, m2['doc_id'])
    csv_hits = docs_agent.trechos_relevantes(db, 'ana', m2['doc_id'])
    assert csv_hits and csv_hits[0]['table_hint']
    m_tsv = docs_agent.salvar_documento(db, 'dados.tsv', b'item\tvalor\ncaneta\t5\n', 'conv-1')
    assert 'caneta | 5' in docs_agent.obter_texto(db, m_tsv['doc_id'])
    m3 = docs_agent.salvar_documento(db, 'pag.html', b'<html><body><h1>Titulo</h1><script>x()</script><p>Corpo aqui.</p>', 'conv-1')
    txt = docs_agent.obter_texto(db, m3['doc_id'])
    assert 'Titulo' in txt and 'x()' not in txt
    assert len(docs_agent.listar_documentos(db)) == 4
    db.close()


def test_docx_xlsx(tmp_path):
    docx = pytest.importorskip('docx')
    oxl = pytest.importorskip('openpyxl')
    db = mem_db(tmp_path)
    buf = io.BytesIO()
    d = docx.Document()
    d.add_paragraph('Contrato de teste da Júlia')
    d.save(buf)
    m = docs_agent.salvar_documento(db, 'contrato.docx', buf.getvalue(), 'conv-2')
    assert 'Júlia' in docs_agent.obter_texto(db, m['doc_id'])
    wb = oxl.Workbook()
    ws = wb.active
    ws.append(['item', 'valor'])
    ws.append(['caneta', 5])
    buf2 = io.BytesIO()
    wb.save(buf2)
    m2 = docs_agent.salvar_documento(db, 'plan.xlsx', buf2.getvalue(), 'conv-2')
    assert 'caneta | 5' in docs_agent.obter_texto(db, m2['doc_id'])
    db.close()


def test_rejeita_formato_e_tamanho(tmp_path):
    db = mem_db(tmp_path)
    with pytest.raises(docs_agent.DocErro):
        docs_agent.salvar_documento(db, 'foto.png', b'\x89PNG' + b'0' * 100, 'c')
    with pytest.raises(docs_agent.DocErro):
        docs_agent.salvar_documento(db, 'vazio.txt', b'   ', 'c')
    with pytest.raises(docs_agent.DocErro):
        docs_agent.salvar_documento(db, 'grande.txt', b'x' * (docs_agent.MAX_BYTES + 1), 'c')
    with pytest.raises(docs_agent.DocErro) as mismatch:
        docs_agent.salvar_documento(db, 'falso.pdf', b'isso nao e pdf; tem mais de dez caracteres', 'c')
    assert mismatch.value.codigo == 'conteudo_invalido'
    with pytest.raises(docs_agent.DocErro) as binary:
        docs_agent.salvar_documento(db, 'texto.txt', b'conteudo\x00binario suficiente', 'c')
    assert binary.value.codigo == 'conteudo_invalido'
    db.close()


def _ooxml_zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return buf.getvalue()


def _minimal_docx_entries(document_xml=b"<document><p>Conteudo valido.</p></document>"):
    return [
        ("[Content_Types].xml", b"<Types/>"),
        ("word/document.xml", document_xml),
    ]


@pytest.mark.parametrize("name,entries,code", [
    ("traversal.docx", _minimal_docx_entries() + [("../outside.txt", b"outside")], "zip_caminho"),
    ("xxe.docx", _minimal_docx_entries(
        b'<!DOCTYPE x [<!ENTITY e SYSTEM "file:///secret">]><document>&e;</document>'),
     "xml_unsafe"),
    ("external.docx", _minimal_docx_entries() + [
        ("word/_rels/document.xml.rels",
         b'<Relationships><Relationship TargetMode="External" Target="file:///secret"/></Relationships>')],
     "xml_unsafe"),
    ("bomb.docx", _minimal_docx_entries(b"<document>" + b"A" * 100_000 + b"</document>"),
     "zip_ratio"),
])
def test_pacote_ooxml_rejeita_traversal_xxe_e_bomb(tmp_path, name, entries, code):
    db = mem_db(tmp_path)
    with pytest.raises(docs_agent.DocErro) as exc:
        docs_agent.salvar_documento(db, name, _ooxml_zip(entries), "conv-sec")
    assert exc.value.codigo == code
    assert db.execute("SELECT count(*) FROM documents").fetchone()[0] == 0
    db.close()


def test_limites_arquivo_zip_e_nome_sem_path_traversal(tmp_path, monkeypatch):
    db = mem_db(tmp_path)
    too_many = _minimal_docx_entries() + [
        (f"word/extra-{i}.bin", b"x") for i in range(docs_agent.MAX_ZIP_ENTRIES)
    ]
    with pytest.raises(docs_agent.DocErro) as exc:
        docs_agent.salvar_documento(db, "muitos.docx", _ooxml_zip(too_many), "conv-sec")
    assert exc.value.codigo == "zip_limite"
    monkeypatch.setenv("JULIA_DOCS_PATH", str(tmp_path / "stored"))
    doc = docs_agent.salvar_documento(db, "../../..\\outside.txt", b"Safe content only.", "conv-safe")
    assert doc["name"] == ".._.._.._outside.txt"
    assert list((tmp_path / "stored").iterdir()) == [
        tmp_path / "stored" / (doc["doc_id"] + ".txt")]
    db.close()


@pytest.mark.parametrize("entries,member_limit,total_limit", [
    (_minimal_docx_entries(b"<document>" + bytes(range(32)) + b"</document>"), 16, 1000),
    (_minimal_docx_entries() + [("word/one.bin", bytes(range(16))),
                                ("word/two.bin", bytes(range(16)))], 100, 30),
])
def test_limites_expandidos_de_arquivo_ooxml(tmp_path, monkeypatch, entries,
                                            member_limit, total_limit):
    db = mem_db(tmp_path)
    monkeypatch.setattr(docs_agent, "MAX_ZIP_MEMBER_BYTES", member_limit)
    monkeypatch.setattr(docs_agent, "MAX_ZIP_TOTAL_BYTES", total_limit)
    with pytest.raises(docs_agent.DocErro) as exc:
        docs_agent.salvar_documento(db, "limits.docx", _ooxml_zip(entries), "conv-sec")
    assert exc.value.codigo == "zip_limite"
    db.close()


def test_upload_limited_incrementally_during_read(monkeypatch):
    calls = []
    payload = b"x" * (15 * 1024 * 1024 + 500_000)

    class StreamUpload:
        filename = "too-large.txt"
        closed = False

        async def read(self, size):
            nonlocal payload
            calls.append(size)
            chunk = payload[:size]
            payload = payload[len(chunk):]
            return chunk

        async def close(self):
            self.closed = True

    async def fake_owner(_request):
        return "local"

    async def should_not_relay(*_args, **_kwargs):
        raise AssertionError("Oversized uploads must be rejected before relay")

    monkeypatch.setattr(server, "require_csrf", lambda _request: None)
    monkeypatch.setattr(server, "revogacao_ok", fake_owner)
    monkeypatch.setattr(server.relay, "exchange", should_not_relay)
    request = Request({"type": "http", "method": "POST", "scheme": "http",
                       "path": "/api/docs/upload", "raw_path": b"/api/docs/upload",
                       "query_string": b"", "headers": [], "server": ("test", 80),
                       "client": ("test", 1234), "path_params": {}})
    upload = StreamUpload()
    with pytest.raises(server.HTTPException) as exc:
        asyncio.run(server.docs_upload(request, upload))
    assert exc.value.status_code == 413
    assert upload.closed
    assert all(0 < size <= 64 * 1024 for size in calls)
    assert sum(calls) == 15 * 1024 * 1024 + 1


def test_upload_request_body_bounded_before_multipart_parser():
    async def run():
        response_messages = []
        downstream_called = False

        async def fake_app(scope, receive, send):
            nonlocal downstream_called
            downstream_called = True
            while True:
                message = await receive()
                if not message.get("more_body"):
                    break

        middleware = server.DocumentUploadBodyLimit(fake_app)
        pieces = [
            {"type": "http.request", "body": b"a" * (8 * 1024 * 1024), "more_body": True},
            {"type": "http.request", "body": b"b" * (8 * 1024 * 1024), "more_body": True},
            {"type": "http.request", "body": b"c", "more_body": False},
        ]

        async def receive():
            return pieces.pop(0)

        async def send(message):
            response_messages.append(message)

        scope = {"type": "http", "method": "POST", "path": "/api/docs/upload",
                 "headers": []}
        await middleware(scope, receive, send)
        return response_messages, downstream_called

    messages, downstream_called = asyncio.run(run())
    assert downstream_called
    assert [m["status"] for m in messages if m["type"] == "http.response.start"] == [413]


def test_trechos_relevantes(tmp_path):
    db = mem_db(tmp_path)
    m = docs_agent.salvar_documento(
        db, 'manual.txt',
        ('O reembolso de viagens precisa de nota fiscal. O prazo do reembolso é 30 dias. '
         'O estacionamento é pago à parte.' * 20).encode('utf-8'), 'conv-9')
    got = docs_agent.trechos_relevantes(db, 'qual o prazo do reembolso?', m['doc_id'])
    assert got and 'reembolso' in got[0]['trecho'].lower()
    db.close()


def _pdf_com_texto(texto):
    content = f"BT /F1 12 Tf 72 720 Td ({texto}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" +
        content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(offsets)}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
                  f"startxref\n{xref}\n%%EOF\n".encode())
    return bytes(output)


def test_pdf_textual_e_vazio(tmp_path):
    pytest.importorskip("pypdf")
    db = mem_db(tmp_path)
    doc = docs_agent.salvar_documento(db, "relatorio.pdf", _pdf_com_texto("Texto PDF textual"), "conv-pdf")
    assert "Texto PDF textual" in docs_agent.obter_texto(db, doc["doc_id"])
    provenance = docs_agent.trechos_relevantes(db, "texto PDF", doc["doc_id"])
    assert provenance[0]["page"] == 1
    with pytest.raises(docs_agent.DocErro) as exc:
        docs_agent.salvar_documento(db, "vazio.pdf", _pdf_com_texto(""), "conv-pdf")
    assert exc.value.codigo in {"pdf_ilegivel", "vazio"}
    db.close()


def test_json_seguro_e_metadados(tmp_path):
    db = mem_db(tmp_path)
    raw = json.dumps({
        "title": "Manual de segurança",
        "sections": [{"heading": "Controles", "body": "Não execute conteúdo embutido."}],
        "script": "<script>alert(1)</script>",
    }).encode()
    doc = docs_agent.salvar_documento(db, "manual.json", raw, "conv-json")
    text = docs_agent.obter_texto(db, doc["doc_id"])
    assert doc["title"] == "Manual de segurança"
    assert "Controles" in text and "<script>" in text
    assert "table_hint" in docs_agent.trechos_relevantes(db, "conteúdo embutido", doc["doc_id"])[0]
    assert docs_agent.trechos_relevantes(db, "conteúdo embutido", doc["doc_id"])[0]["content_hash"]
    db.close()


def test_chunking_fts_retrieval_provenance_and_compare(tmp_path):
    db = mem_db(tmp_path)
    text = ("# Política de retenção\n\n"
            "A retenção documental padrão é de trinta dias. " * 100 +
            "\n\n# Exceções\n\nA retenção especial depende de autorização.")
    one = docs_agent.salvar_documento(db, "retencao.md", text.encode(), "conv-chunks")
    two = docs_agent.salvar_documento(db, "outro.txt", b"Este documento descreve o processo de compras internas.", "conv-chunks")
    rows = db.execute("SELECT idx, text, section, content_hash, version, source, owner_id, overlap "
                      "FROM doc_chunks WHERE doc_id=? ORDER BY idx", (one["doc_id"],)).fetchall()
    assert len(rows) > 2
    assert all(len(row[1]) <= docs_agent.TAM_CHUNK and row[3] and row[4] == 1
               and row[5] == "retencao.md" and row[6] == "local" for row in rows)
    assert any(row[2] == "Política de retenção" for row in rows)
    assert any(row[7] == docs_agent.OVERLAP for row in rows[1:])

    results = docs_agent.trechos_relevantes(db, "retenção documental padrão", one["doc_id"], owner="local")
    assert results and results[0]["doc_id"] == one["doc_id"]
    assert results[0]["chunk_id"].startswith(one["doc_id"] + ":")
    assert results[0]["owner_id"] == "local" and results[0]["source"] == "retencao.md"
    assert results[0]["content_hash"] and results[0]["version"] == 1
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='doc_chunks_fts'").fetchone():
        assert db.execute("SELECT count(*) FROM doc_chunks_fts").fetchone()[0] == len(rows) + 1

    compared = docs_agent.comparar_documentos(
        db, "retenção documental padrão", [one["doc_id"], two["doc_id"]], owner="local")
    assert [f["status"] for f in compared["findings"]] == ["located", "proven_absent"]
    assert compared["findings"][0]["evidence"][0]["citacao"]
    assert "não ausência semântica" in compared["note"]
    db.close()


def test_compare_nao_confunde_truncamento_com_ausencia(tmp_path):
    db = mem_db(tmp_path)
    doc = docs_agent.salvar_documento(
        db, "grande.txt", ("Unrelated source text remains available. " * 6000).encode(),
        "conv-large")
    compared = docs_agent.comparar_documentos(
        db, "zebra ultraviolet widget", [doc["doc_id"]], owner="local")
    assert compared["findings"][0]["status"] == "not_located"
    assert compared["findings"][0]["basis"] == "no_matching_evidence_or_incomplete_extraction"
    db.close()


def test_migracao_documental_preserva_dados_existentes(tmp_path):
    db = sqlite3.connect(tmp_path / "legacy.sqlite3")
    db.execute("""CREATE TABLE documents (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, ext TEXT NOT NULL,
        size INTEGER NOT NULL, chars INTEGER NOT NULL, chunks INTEGER NOT NULL,
        summary TEXT, topics TEXT, conversation_id TEXT NOT NULL,
        created_at TEXT NOT NULL, owner_id TEXT NOT NULL DEFAULT 'local'
    )""")
    db.execute("""CREATE TABLE doc_chunks (
        doc_id TEXT NOT NULL, idx INTEGER NOT NULL, text TEXT NOT NULL,
        owner_id TEXT NOT NULL DEFAULT 'local', PRIMARY KEY (doc_id, idx)
    )""")
    db.execute("INSERT INTO documents(id,name,ext,size,chars,chunks,conversation_id,created_at,owner_id) "
               "VALUES ('old-doc','old.txt','.txt',10,10,1,'c','t','alice')")
    db.execute("INSERT INTO doc_chunks(doc_id,idx,text,owner_id) VALUES ('old-doc',0,'old content','alice')")
    docs_agent.criar_tabelas(db)
    assert db.execute("SELECT name, owner_id FROM documents WHERE id='old-doc'").fetchone() == ("old.txt", "alice")
    assert db.execute("SELECT text FROM doc_chunks WHERE doc_id='old-doc'").fetchone() == ("old content",)
    migrated = db.execute("SELECT chunk_id, section, content_hash, version FROM doc_chunks "
                          "WHERE doc_id='old-doc'").fetchone()
    assert migrated[0] == "old-doc:0" and migrated[2] and migrated[3] == 1
    assert docs_agent.obter_texto(db, "old-doc", owner="alice") == "old content"
    db.close()


def test_delete_is_owner_scoped_and_cleans_original_chunks_and_fts(tmp_path, monkeypatch):
    storage = tmp_path / "originals"
    monkeypatch.setenv("JULIA_DOCS_PATH", str(storage))
    db = mem_db(tmp_path)
    doc = docs_agent.salvar_documento(db, "private.txt", b"Conteudo privado do proprietario.", "conv-del",
                                      owner="alice")
    original = storage / (doc["doc_id"] + ".txt")
    assert original.exists()
    assert not docs_agent.excluir_documento(db, doc["doc_id"], owner="bob")
    assert original.exists()
    assert db.execute("SELECT 1 FROM documents WHERE id=?", (doc["doc_id"],)).fetchone()
    assert docs_agent.excluir_documento(db, doc["doc_id"], owner="alice")
    assert not original.exists()
    assert not db.execute("SELECT 1 FROM documents WHERE id=?", (doc["doc_id"],)).fetchone()
    assert not db.execute("SELECT 1 FROM doc_chunks WHERE doc_id=?", (doc["doc_id"],)).fetchone()
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='doc_chunks_fts'").fetchone():
        assert not db.execute("SELECT 1 FROM doc_chunks_fts WHERE doc_id=?", (doc["doc_id"],)).fetchone()
    db.close()


# ── Memória que aprende ───────────────────────────────────────────────
def test_fatos_e_relevancia(tmp_path):
    db = mem_db(tmp_path)
    pc_agent.guardar_fato(db, 'nome', 'Efrain Silva', 'chat')
    pc_agent.guardar_fato(db, 'projeto_alpha', 'app de finanças em Python', 'llm')
    assert any(f['key'] == 'nome' for f in pc_agent.ler_memorias(db))
    rel = pc_agent.memorias_relevantes(db, 'qual é o meu nome?')
    assert rel and rel[0]['key'] == 'nome'
    rel2 = pc_agent.memorias_relevantes(db, 'me conta do projeto de finanças')
    assert any(f['key'] == 'projeto_alpha' for f in rel2)
    db.close()


def test_comandos_de_memoria(tmp_path):
    db = mem_db(tmp_path)
    vazio = pc_agent.interpretar_comando_memoria(db, 'o que você sabe sobre mim?')
    assert vazio and vazio[1] == 'mem_vazia'
    pc_agent.guardar_fato(db, 'foco', 'produtividade')
    lista = pc_agent.interpretar_comando_memoria(db, 'mostre sua memória')
    assert lista and 'produtividade' in lista[0]
    esquecer = pc_agent.interpretar_comando_memoria(db, 'esqueça produtividade')
    assert esquecer and esquecer[1] == 'mem_esquecer'
    assert pc_agent.interpretar_comando_memoria(db, 'qual a capital do Brasil?') is None
    db.close()


def test_ai_responde_memoria_sem_llm(tmp_path, monkeypatch):
    db = mem_db(tmp_path)
    pc_agent.persist_messages(db, [{
        'id': 'mem-user-001', 'origin': 'mobile', 'role': 'user',
        'text': 'o que você sabe sobre mim? Por favor me diga tudo.',
        'created_at': '2026-10-12T12:00:00.000Z', 'conversation_id': 'conv-mem'}])
    pc_agent.guardar_fato(db, 'nome', 'Efrain')
    cfg = {'proxy': 'http://127.0.0.1:9/v1', 'model': 'fake', 'system': 's',
           'context': 5, 'max_tokens': 50}

    def _boom(*a, **k):
        raise AssertionError('LLM não deveria ser chamado para comando de memória')

    monkeypatch.setattr('hermes_bridge.chat_complete', _boom)
    r = pc_agent.ai_completa(db, {'message_id': 'mem-user-001', 'conversation_id': 'conv-mem'}, cfg)
    assert 'Efrain' in r['response_text']
    assert r['reply_id'] == 'mem-user-001-r1'
    db.close()


def test_doc_mencionado_e_intencoes(tmp_path):
    db = mem_db(tmp_path)
    m = docs_agent.salvar_documento(db, 'contrato-aluguel.txt', 'cláusula sobre multa de aluguel'.encode('utf-8'), 'conv-d')
    assert pc_agent.doc_mencionado(db, 'qual a multa no contrato-aluguel?', 'conv-d') == m['doc_id']
    assert pc_agent.doc_mencionado(db, 'resuma o documento pra mim', 'conv-d') == m['doc_id']
    assert pc_agent.doc_mencionado(db, 'qual a capital do Peru?', 'conv-d') == ''
    assert pc_agent.intencao_pesquisa('pesquise o preço do dólar hoje com fontes')
    assert not pc_agent.intencao_pesquisa('me conta uma piada')
    assert pc_agent.intencao_imagem('mostre uma imagem de um gato astronauta')
    db.close()


# ── Relay: docs + memories via agente fake ────────────────────────────
def _agent_loop(ws, handlers):
    while True:
        try:
            req = ws.receive_json()
        except Exception:
            return
        fn = handlers.get(req.get('type'))
        if fn is None:
            continue
        ws.send_json({'request_id': req['request_id'], **fn(req)})


def test_relay_docs_e_memories():
    with TestClient(server.app) as client:
        csrf = login(client)
        with client.websocket_connect('/api/agent/ws',
                                      headers={'Authorization': 'Bearer ' + os.environ['JULIA_AGENT_TOKEN']}) as ws:
            handlers = {
                'sess_revogados': lambda r: {'type': 'sess_revogados', 'sids': []},
                'doc_upload': lambda r: ({'type': 'doc_uploaded', 'doc_id': 'doc-abc123',
                                         'name': 'a.txt', 'ext': '.txt', 'chars': 10,
                                         'chunks': 1, 'paginas_aprox': 1}
                                        if r.get('owner') == 'local' else {'type': 'doc_error',
                                                                          'error': 'dono?', 'codigo': 'x'}),
                'doc_list': lambda r: {'type': 'doc_list', 'documents': []},
                'doc_resumo': lambda r: {'type': 'doc_resumo', 'doc_id': r['doc_id'], 'resumo': 'RES'},
                'doc_search': lambda r: {'type': 'doc_search', 'results': [{
                    'doc_id': r.get('doc_id') or 'doc-abc123', 'chunk_id': 'doc-abc123:0',
                    'owner_id': r['owner'], 'source': 'a.txt', 'section': '', 'page': None,
                    'content_hash': 'hash', 'version': 1, 'citacao': '[doc-abc123:doc-abc123:0]',
                    'trecho': 'conteudo aqui'}]},
                'doc_compare': lambda r: {'type': 'doc_compare', 'query': r['query'],
                                          'findings': [{'doc_id': 'doc-abc123', 'status': 'located'}]},
                'doc_delete': lambda r: ({'type': 'doc_deleted'} if r.get('owner') == 'local' else
                                         {'type': 'doc_error', 'error': 'not found'}),
                'mem_list': lambda r: {'type': 'mem_list',
                                       'memories': [{'key': 'nome', 'value': 'X', 'updated_at': 't'}]},
                'mem_forget': lambda r: {'type': 'mem_forgotten', 'key': r['key']},
            }
            t = threading.Thread(target=_agent_loop, args=(ws, handlers), daemon=True)
            t.start()

            up = client.post('/api/docs/upload', files={'file': ('a.txt', b'conteudo aqui')},
                             data={'conversation_id': 'conv-001'},
                             headers={'X-CSRF-Token': csrf})
            assert up.status_code == 200, up.text
            assert up.json()['doc_id'] == 'doc-abc123'

            docs = client.get('/api/docs')
            assert docs.status_code == 200, docs.text
            search = client.post('/api/docs/search', json={'query': 'conteudo'},
                                 headers={'X-CSRF-Token': csrf})
            assert search.status_code == 200
            assert search.json()['results'][0]['chunk_id'] == 'doc-abc123:0'
            compare = client.post('/api/docs/compare',
                                  json={'query': 'conteudo', 'doc_ids': ['doc-abc123']},
                                  headers={'X-CSRF-Token': csrf})
            assert compare.status_code == 200
            assert compare.json()['findings'][0]['status'] == 'located'

            bad = client.post('/api/docs/resumo', json={'doc_id': '!!'},
                              headers={'X-CSRF-Token': csrf})
            assert bad.status_code == 422

            ok = client.post('/api/docs/resumo', json={'doc_id': 'doc-abc123'},
                             headers={'X-CSRF-Token': csrf})
            assert ok.json() == {'doc_id': 'doc-abc123', 'resumo': 'RES'}

            removed = client.delete('/api/docs/doc-abc123', headers={'X-CSRF-Token': csrf})
            assert removed.status_code == 200 and removed.json()['ok']
            assert client.delete('/api/docs/!!', headers={'X-CSRF-Token': csrf}).status_code == 422

            mem = client.get('/api/memories')
            assert mem.json()['memories'][0]['key'] == 'nome'
            forg = client.delete('/api/memories/nome', headers={'X-CSRF-Token': csrf})
            assert forg.json() == {'ok': True, 'key': 'nome'}
            assert client.delete('/api/memories/IN-VÁLIDA!', headers={'X-CSRF-Token': csrf}).status_code == 422

            empty = client.post('/api/docs/upload', files={'file': ('e.txt', b'')},
                                data={'conversation_id': 'conv-001'},
                                headers={'X-CSRF-Token': csrf})
            assert empty.status_code == 422
