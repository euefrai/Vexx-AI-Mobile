"""Arquivos gerados: criação versionada, leitura e cartão JDUI."""
import base64
import json
import re

import pytest

import docs_agent
import files_agent
import jdui
import pc_agent


@pytest.fixture()
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("JULIA_FILES_PATH", str(tmp_path / "files"))
    monkeypatch.setenv("JULIA_DOCS_PATH", str(tmp_path / "docs"))
    conn = pc_agent.open_db(tmp_path / "agent.sqlite3")
    yield conn
    conn.close()


def _corpo_fence(texto):
    match = re.search(r"```jdui\s*\n(.*?)\n```", texto, re.S)
    assert match, texto
    return json.loads(match.group(1))


def test_codigo_anexado_preserva_indentacao_e_entra_no_prompt(db):
    fonte = (
        "def soma(a, b):\n"
        "    # a indentação faz parte do arquivo\n"
        "    return a + b\n"
    )
    meta = docs_agent.salvar_documento(db, "app.py", fonte.encode("utf-8"), "conv-code")
    texto = docs_agent.obter_texto(db, meta["doc_id"])
    assert "    # a indentação" in texto
    assert "    return a + b" in texto

    pedido = ('sobre o que é esse app.py?\n\n'
              '📎 Documento anexado: "app.py"')
    assert pc_agent.doc_mencionado(db, pedido, "conv-code") == meta["doc_id"]
    assert pc_agent.doc_mencionado(
        db, "e o que tem nesse app.py?", "conv-code") == meta["doc_id"]
    contexto = docs_agent.contexto_documento(db, meta["doc_id"], pedido)
    assert contexto["modo"] == "completo"
    assert "    return a + b" in contexto["texto"]

    cfg = dict(pc_agent.ai_config(), pesquisa_web=False, memoria_global=False)
    mensagens, extras = pc_agent.ai_montar_mensagens(db, "conv-code", cfg, pedido)
    sistema = mensagens[0]["content"]
    assert extras["doc_id"] == meta["doc_id"]
    assert "CONTEÚDO INTEGRAL" in sistema
    assert "    return a + b" in sistema


def test_codigo_desconhecido_e_texto_utf16_preservam_formato(db):
    julia = "function soma(a, b)\n    return a + b\nend\n"
    meta = docs_agent.salvar_documento(db, "script.jl", julia.encode("utf-8"), "conv-jl")
    texto = docs_agent.obter_texto(db, meta["doc_id"])
    assert "\n    return a + b\n" in texto

    utf16 = b"\xff\xfe" + "primeira linha\r\nsegunda linha".encode("utf-16-le")
    meta = docs_agent.salvar_documento(db, "notas.txt", utf16, "conv-utf16")
    texto = docs_agent.obter_texto(db, meta["doc_id"])
    assert "primeira linha\nsegunda linha" in texto


def test_pedido_de_nova_versao_recupera_o_anexo_e_autoriza_arquivo(db):
    fonte = ("# Relatório de vendas\n\nA receita cresceu.\n\n"
             "def soma(a, b):\n    return a + b\n")
    meta = docs_agent.salvar_documento(db, "app.py", fonte.encode("utf-8"), "conv-ver")
    pedido_versao = "crie uma nova versão do relatório de vendas"
    for pedido in ("crie uma nova versão desse arquivo",
                   "crie outro arquivo sobreposto",
                   "sobreponha as correções no app.py",
                   "sobreponha o conteúdo",
                   "crie uma nova versão do que enviei",
                   pedido_versao):
        assert pc_agent.doc_mencionado(db, pedido, "conv-ver") == meta["doc_id"], pedido
        assert pc_agent.quer_criar_arquivo(pedido, meta["doc_id"]), pedido
    contexto = docs_agent.contexto_documento(db, meta["doc_id"], pedido_versao)
    assert contexto["modo"] == "completo"
    assert "A receita cresceu." in contexto["texto"]
    cfg = dict(pc_agent.ai_config(), pesquisa_web=False, memoria_global=False)
    mensagens, extras = pc_agent.ai_montar_mensagens(
        db, "conv-ver", cfg, pedido_versao)
    sistema = mensagens[0]["content"]
    assert extras["doc_id"] == meta["doc_id"]
    assert extras.get("pode_gerar_arquivo") is True
    assert "CONTEÚDO INTEGRAL" in sistema and "    return a + b" in sistema
    assert "A receita cresceu." in sistema
    assert "JULIAFILE" in sistema


def test_html_anexado_fornece_a_fonte_e_nao_so_o_texto_visivel(db):
    html = (
        '<!doctype html><html><head><title>Painel</title>'
        '<style>.card { color: red; }</style></head><body>'
        '<h1>Meu painel</h1><script>function abrir() { return 1; }</script>'
        '</body></html>'
    )
    meta = docs_agent.salvar_documento(db, "index.html", html.encode("utf-8"), "conv-html")
    pedido = ('sobre o que é esse index.html?\n\n'
              '📎 Documento anexado: "index.html"')
    contexto = docs_agent.contexto_documento(db, meta["doc_id"], pedido)
    assert contexto["modo"] == "completo"
    assert "<script>" in contexto["texto"]
    assert "function abrir()" in contexto["texto"]
    assert ".card { color: red; }" in contexto["texto"]


def test_criacao_versionada_e_filecard_valido(db):
    texto = (
        "Segue a primeira versão.\n\n"
        '<JULIAFILE name="projeto/app.py">\n'
        "def soma(a, b):\n"
        "    return a + b\n"
        "</JULIAFILE>"
    )
    first = files_agent.processar_texto(db, texto, "conv-1", "local")
    assert first["erros"] == []
    assert first["texto"] == "Segue a primeira versão."
    assert first["arquivos"][0]["name"] == "projeto/app.py"
    assert first["arquivos"][0]["version"] == 1
    assert first["arquivos"][0]["kind"] == "code"
    assert "JULIAFILE" not in first["texto"]

    second = files_agent.processar_texto(
        db, '<JULIAFILE name="projeto/app.py">print(2)</JULIAFILE>',
        "conv-1", "local")
    assert second["arquivos"][0]["version"] == 2
    assert len(files_agent.listar_arquivos(db, owner="local",
                                           conversation_id="conv-1")) == 2

    lido = files_agent.obter_arquivo(db, second["arquivos"][0]["file_id"], "local")
    assert base64.b64decode(lido["data_b64"]) == b"print(2)"

    fence = files_agent.filecard_fence(second["arquivos"])
    ok, norm, erros = jdui.validar_mensagem(_corpo_fence(fence))
    assert ok, erros
    arquivo = norm["blocks"][0]["props"]["files"][0]
    assert arquivo["kind"] == "code"
    assert arquivo["url"] == second["arquivos"][0]["download_url"]


def test_nome_seguro_e_sem_sobrescrever_fora_do_workspace(db):
    with pytest.raises(files_agent.FileErro):
        files_agent.salvar_arquivo(db, "../fora.py", "print(1)", "conv-1", "local")
    with pytest.raises(files_agent.FileErro):
        files_agent.salvar_arquivo(db, "C:/Windows/evil.py", "print(1)", "conv-1", "local")
    with pytest.raises(files_agent.FileErro):
        files_agent.salvar_arquivo(db, "sub/../app.py", "print(1)", "conv-1", "local")
    arquivo = files_agent.salvar_arquivo(db, "sub/app.py", "print(1)", "conv-1", "local")
    assert arquivo["name"] == "sub/app.py"


def test_bloco_sem_autorizacao_e_removido(db):
    texto = 'Resposta.\n<JULIAFILE name="x.py">print(1)</JULIAFILE>'
    limpo = pc_agent._aplicar_arquivos_gerados(db, "conv-1", "local", texto, {})
    assert "<JULIAFILE" not in limpo
    assert not files_agent.listar_arquivos(db, owner="local")

    criado = pc_agent._aplicar_arquivos_gerados(
        db, "conv-1", "local", texto, {"pode_gerar_arquivo": True})
    assert "Arquivo(s) criado(s)" in criado
    assert "```jdui" in criado
    assert len(files_agent.listar_arquivos(db, owner="local")) == 1


def test_base64_e_limites_do_bloco(db):
    dados = b"\x89PNG\r\n\x1a\n"
    bloco = ('<JULIAFILE name="imagem.png" encoding="base64">\n'
             + base64.b64encode(dados).decode("ascii") + "\n</JULIAFILE>")
    res = files_agent.processar_texto(db, bloco, "conv-img", "local")
    assert res["erros"] == []
    meta = res["arquivos"][0]
    assert meta["kind"] == "image"
    lido = files_agent.obter_arquivo(db, meta["file_id"], "local")
    assert base64.b64decode(lido["data_b64"]) == dados
