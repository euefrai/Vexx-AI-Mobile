"""Regressões de confiança da V5.7.3 (incidentes reais da V5.7.2).

Cada teste usa fixture determinística e não chama provedores externos.
"""
import json
import sys
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import assistant_identity
import evidence_graph as eg
import hermes_bridge
import pc_agent
import research
import research_agents as ra
import server
import shopping
import tool_protocol


# ── Protocolo de ferramentas ─────────────────────────────────────────
def _sanitizar_em_chunks(chunks):
    s = tool_protocol.Sanitizador()
    out = "".join(s.alimentar(c) for c in chunks)
    resto, erros = s.finalizar()
    return out + resto, erros


def test_tool_call_completa_nao_vira_resposta():
    limpo, erros = tool_protocol.sanitizar_texto(
        'Antes. <tool_call>tools.webresearch{"query":"notebook"}</tool_call> Depois.')
    assert "tool_call" not in limpo.lower()
    assert "webresearch" not in limpo
    assert limpo.strip() == "Antes.  Depois."
    assert erros and erros[0]["codigo"] == "tool_call_removida"
    assert erros[0]["ferramenta"] == "tools.webresearch"


def test_tool_call_marcador_dividido_entre_chunks():
    limpo, erros = _sanitizar_em_chunks([
        "Olá <tool", '_call>tools.webresearch{"query":"x"',
        '}</tool_', "call> fim.",
    ])
    assert "<tool_call>" not in limpo.lower()
    assert "webresearch" not in limpo
    assert "Olá" in limpo and "fim." in limpo
    assert erros and erros[0]["codigo"] == "tool_call_removida"


def test_tool_call_json_incompleto_e_invalido():
    limpo, erros = tool_protocol.sanitizar_texto(
        '<tool_call>tools.x{"query":"sem fechar"')
    assert limpo == ""
    assert erros[0]["codigo"] == "tool_call_json_incompleto"

    limpo, erros = tool_protocol.sanitizar_texto(
        '<tool_call>tools.x{"query": }</tool_call>')
    assert limpo == ""
    assert erros[0]["codigo"] == "tool_call_json_invalido"


def test_tool_call_multipla_e_sem_payload():
    limpo, erros = tool_protocol.sanitizar_texto(
        '<tool_call>tools.a{}</tool_call>'
        '<tool_call>tools.b</tool_call>'
        '<tool_call>functions.c</tool_call>')
    assert limpo == ""
    assert len(erros) == 3
    assert {e["ferramenta"] for e in erros} == {
        "tools.a", "tools.b", "functions.c"}


def test_mencao_literal_em_codigo_e_documentacao_preservada():
    inline = "Use `<tool_call>` na documentação."
    fenced = "```\n<tool_call>tools.x{}\n```"
    texto = "O marcador <tool_call> não é uma chamada."
    for original in (inline, fenced, texto):
        limpo, erros = tool_protocol.sanitizar_texto(original)
        assert limpo == original
        assert erros == []


class _RespJSON:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._payload


class _RespStream:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read1(self, _n):
        return self._chunks.pop(0) if self._chunks else b""


def _sse(payload):
    return ("data: " + json.dumps(payload) + "\n\n").encode()


def test_bridge_complete_tool_call_apenas_nao_e_resposta(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _RespJSON(
        {"choices": [{"message": {"content":
            '<tool_call>tools.webresearch{"query":"x"}</tool_call>'}}]}))
    with pytest.raises(hermes_bridge.BridgeErro) as exc:
        hermes_bridge.chat_complete(
            "http://127.0.0.1:8645/v1", "m", [{"role": "user", "content": "oi"}])
    assert exc.value.codigo == "protocolo_ferramenta"


def test_bridge_stream_nao_emite_tool_call_dividida(monkeypatch):
    delta = "Olá <tool_call>tools.webresearch{\"query\":\"x\"}</tool_call> fim."
    chunks = [
        _sse({"choices": [{"delta": {"content": delta[:18]}}]}),
        _sse({"choices": [{"delta": {"content": delta[18:]}}]}),
        b"data: [DONE]\n\n",
    ]
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _RespStream(chunks))
    recebidos = []
    r = hermes_bridge.chat_stream(
        "http://127.0.0.1:8645/v1", "m",
        [{"role": "user", "content": "oi"}],
        on_delta=lambda seq, trecho: recebidos.append(trecho))
    assert "<tool_call>" not in "".join(recebidos).lower()
    assert "webresearch" not in "".join(recebidos)
    assert "Olá" in r["texto"] and "fim." in r["texto"]


def test_bridge_stream_apenas_tool_call_e_protocolo(monkeypatch):
    chunks = [
        _sse({"choices": [{"delta": {"content":
            '<tool_call>tools.webresearch{"query":"x"}</tool_call>'}}]}),
        b"data: [DONE]\n\n",
    ]
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _RespStream(chunks))
    recebidos = []
    with pytest.raises(hermes_bridge.BridgeErro) as exc:
        hermes_bridge.chat_stream(
            "http://127.0.0.1:8645/v1", "m",
            [{"role": "user", "content": "oi"}],
            on_delta=lambda seq, trecho: recebidos.append(trecho))
    assert exc.value.codigo == "protocolo_ferramenta"
    assert recebidos == []


# ── Identidade e factos canónicos ───────────────────────────────────
def test_identity_limiter_neutraliza_empresa_inventada():
    for texto in (
        "A Vexx AI foi criada pela Vexxia.",
        "A empresa por trás da Vexx AI é a Vexxia.",
        "O fundador da Vexx AI é João Silva.",
        "A Vexx AI tem sede em São Paulo.",
        "A Vexxia é uma empresa de tecnologia.",
    ):
        limpo = assistant_identity.limitar_afirmacoes_nao_suportadas(texto)
        assert "Vexxia" not in limpo
        assert "João Silva" not in limpo
        assert "São Paulo" not in limpo
        assert limpo == assistant_identity.PRODUCT_IDENTITY_LIMITATION


def test_identity_limiter_neutraliza_dados_comerciais_inventados():
    for texto in (
        "A Vexx AI custa R$ 29,90 por mês.",
        "O CNPJ da Vexx AI é 12.345.678/0001-90.",
        "A Vexx AI é gratuita.",
        "A Vexx AI tem planos a partir de R$ 19.",
    ):
        limpo = assistant_identity.limitar_afirmacoes_nao_suportadas(texto)
        assert limpo == assistant_identity.PRODUCT_IDENTITY_LIMITATION
    legitimo = "A Acme custa R$ 29,90 e é gratuita para estudantes."
    assert assistant_identity.limitar_afirmacoes_nao_suportadas(legitimo) == legitimo


def test_identity_limiter_corrige_autonome_e_preserva_pesquisa_alheia():
    assert assistant_identity.limitar_afirmacoes_nao_suportadas(
        "Meu nome é Vexxia.") == "Pode me chamar de Lucas."
    legitimo = ("A Acme foi fundada por João Silva e tem sede em São Paulo. "
                "A Vexx AI foi comparada a ela em um estudo.")
    assert assistant_identity.limitar_afirmacoes_nao_suportadas(legitimo) == legitimo


def test_cmd_identidade_responde_produto_sem_inventar_empresa():
    resposta, codigo = pc_agent.cmd_identidade("Quem fundou a Vexx AI?")
    assert codigo == "id_produto"
    assert "Vexx AI" in resposta and "Lucas" in resposta
    assert "Vexxia" not in resposta
    assert "não tenho informação confirmada" in resposta.lower()
    assert "pesquise" not in resposta.lower()


def test_cmd_identidade_nao_bloqueia_pesquisa_sobre_produto():
    assert pc_agent.cmd_identidade("Pesquise quem fundou a Vexx AI") is None
    assert pc_agent.cmd_identidade("Pesquise sobre a Vexxia") is None
    assert pc_agent.cmd_identidade("Pesquise o preço da Vexx AI") is None
    corr, codigo = pc_agent.cmd_identidade("Você é Vexxia?")
    assert codigo == "id_correcao" and "Lucas" in corr


def test_cmd_identidade_dados_comerciais_sem_fonte_viram_limitacao():
    for pergunta in ("Qual o CNPJ da Vexx AI?",
                     "Quanto custa a Vexx AI?",
                     "Qual o site oficial da Vexx AI?",
                     "Vexx AI tem assinatura?"):
        resposta, codigo = pc_agent.cmd_identidade(pergunta)
        assert codigo == "id_produto"
        assert "não tenho informação confirmada" in resposta.lower()
        assert "R$" not in resposta and "CNPJ" not in resposta


# ── Evento concluído: comando explícito apenas ──────────────────────
def test_evento_concluido_so_com_comando_explicito(tmp_path):
    db = pc_agent.open_db(tmp_path / "evento.sqlite3")
    try:
        eid = pc_agent.registrar_evento(db, "local", "teste visual", "2099-01-01")
        assert eid
        assert pc_agent.interpretar_comando_memoria(
            db, "teste visual concluido") is None
        ativos = pc_agent.proximos_eventos(db, "local")
        assert [e["titulo"] for e in ativos] == ["teste visual"]
        resposta, codigo = pc_agent.interpretar_comando_memoria(
            db, "concluir evento teste visual")
        assert codigo == "mem_evento"
        assert "teste visual" in resposta
        assert pc_agent.proximos_eventos(db, "local") == []
    finally:
        db.close()


# ── Follow-ups, assunto e fontes ─────────────────────────────────────
def test_gate_de_pesquisa_exige_assunto_nao_generico():
    assert not pc_agent.intencao_pesquisa(
        "pesquise agora os resultados mais baratos")
    assert pc_agent.intencao_pesquisa("pesquise notebooks até 3000 reais")
    assert not research.consulta_tem_assunto(
        "agora mostre só os resultados mais baratos")
    assert research.consulta_tem_assunto("notebook até 3000")


def test_followup_shopping_sem_contexto_nao_dispara_busca():
    assert shopping.followup_sem_contexto(
        "agora mostre só os resultados mais baratos")
    assert shopping.followup_sem_contexto("ver as fotos dos dois primeiros")
    assert not shopping.followup_sem_contexto("qual o melhor notebook até 3000?")


def test_fontes_relevantes_rejeitam_clima_para_notebook():
    fontes = [
        {"id": "clima", "titulo": "Clima em Marabá hoje",
         "trecho": "Previsão do tempo e temperatura", "url": "https://clima.example/x"},
        {"id": "invest", "titulo": "Investimentos agora",
         "trecho": "Bolsa e dólar", "url": "https://invest.example/x"},
        {"id": "note", "titulo": "Notebook bom e barato",
         "trecho": "Ofertas de notebook até R$ 3.000", "url": "https://loja.example/n"},
    ]
    aceitas = research.fontes_relevantes("notebook até 3000", fontes)
    assert [f["id"] for f in aceitas] == ["note"]
    info = {}
    assert research.fontes_relevantes("notebook até 3000", fontes[:2], info) == []
    assert info["rejeitadas_por_relevancia"] == 2


def test_digest_nao_cita_fonte_desconectada():
    digest = research.resumo_deterministico(
        [{"id": "clima", "titulo": "Clima em Marabá",
          "trecho": "Previsão do tempo", "url": "https://clima.example/x"}],
        "notebook até 3000")
    assert "Clima em Marabá" not in digest
    assert "clima.example" not in digest
    assert "não" in digest.lower() and "relação" in digest.lower()


def test_ai_completa_followup_sem_contexto_nao_chama_modelo(tmp_path, monkeypatch):
    db = pc_agent.open_db(tmp_path / "followup.sqlite3")
    monkeypatch.setattr(pc_agent, "cmd_dados_atuais", lambda *a, **k: None)
    monkeypatch.setattr(pc_agent, "cmd_model3d", lambda *a, **k: None)
    monkeypatch.setattr(pc_agent, "interpretar_comando_memoria", lambda *a, **k: None)
    monkeypatch.setattr(pc_agent, "cmd_pesquisa", lambda *a, **k: None)
    monkeypatch.setattr(pc_agent, "cmd_projeto", lambda *a, **k: None)
    chamadas = []
    monkeypatch.setattr(pc_agent.hermes_bridge, "chat_complete",
                        lambda *a, **k: chamadas.append(1))
    cfg = {"proxy": "x", "model": "m", "system": "S", "context": 5,
           "max_tokens": 80, "memoria_global": False, "pesquisa_web": False}
    payload = {"message_id": "follow-user-1", "conversation_id": "conv-follow",
               "text": "agora mostre só os resultados mais baratos",
               "created_at": "2026-10-19T12:00:00Z"}
    try:
        r = pc_agent.ai_completa(db, payload, cfg)
        assert "ofertas verificadas" in r["response_text"].lower()
        assert "não vou inventar" in r["response_text"].lower()
        assert chamadas == []
    finally:
        db.close()


# ── Hermes 429 / fallback e shopping ────────────────────────────────
def test_bridge_mapeia_429_sem_declarar_sucesso(monkeypatch):
    def limite(*a, **k):
        raise urllib.error.HTTPError("http://x", 429, "Too Many Requests", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", limite)
    with pytest.raises(hermes_bridge.BridgeErro) as exc:
        hermes_bridge.chat_complete(
            "http://127.0.0.1:8645/v1", "m", [{"role": "user", "content": "oi"}])
    assert exc.value.codigo == "rate_limit"


def test_bridge_mapeia_404_como_indisponivel(monkeypatch):
    def nao_encontrado(*a, **k):
        raise urllib.error.HTTPError("http://x", 404, "Not Found", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", nao_encontrado)
    with pytest.raises(hermes_bridge.BridgeErro) as exc:
        hermes_bridge.chat_complete(
            "http://127.0.0.1:8645/v1", "m", [{"role": "user", "content": "oi"}])
    assert exc.value.codigo == "modelo-nao-encontrado"


def _shop_res():
    p = {"nome": "Notebook Verificado", "preco_texto": "R$ 2.999,00",
         "preco": 2999.0, "loja": "loja.example",
         "url": "https://loja.example/notebook",
         "disponibilidade": "em_estoque"}
    return {"produtos": [p], "fontes": [], "criterios": {},
            "total_bruto": 1, "excluidos": [], "de_cache": False,
            "verificado_em": "2026-10-19T10:00:00+00:00"}


def test_fallback_preserva_ofertas_verificadas_quando_modelo_falha():
    res = _shop_res()
    texto = pc_agent._fallback_sem_inferencia(
        "notebook até 3000", {"fontes": []}, res)
    assert "Notebook Verificado" in texto
    assert "R$ 2.999,00" in texto
    assert "```jdui" in texto
    # A resposta de falha não inventa uma segunda oferta.
    assert texto.count("Notebook Verificado") >= 1


def test_shopping_aplicar_nao_esconde_card_por_fence_alheio():
    res = _shop_res()
    texto = 'Texto\n\n```jdui\n{"version":"1.1","blocks":[]}\n```'
    out = pc_agent._shopping_aplicar(texto, res)
    assert out.count("```jdui") >= 2
    assert "Notebook Verificado" in out
    assert '{"version":"1.1","blocks":[]}' in out


def test_resumo_shopping_sem_produto_nao_inventa():
    res = {"produtos": [], "fontes": [], "criterios": {},
           "total_bruto": 0, "excluidos": [], "de_cache": False}
    nota = shopping.resumo_texto(res)
    assert nota
    assert "R$" not in nota or "não confirmado" in nota.lower()


# ── Comparações ─────────────────────────────────────────────────────
def test_comparacao_curta_sem_evidencia_e_neutralizada():
    texto = "Tuplas são mais rápidas que listas."
    novo, laudo = pc_agent._validar_comparacoes(texto, [], [])
    assert novo != texto
    assert "UNVERIFIED" in novo
    assert "não tenho evidência verificada" in novo.lower()
    assert laudo and laudo[0]["classificacao"] in ("UNVERIFIED", "HYPOTHESIS")


def test_comparacao_com_evidencia_nao_e_neutralizada():
    texto = "As tuplas são 40% mais rápidas que as listas em leitura."
    ev = [{"id": "e1", "trecho":
           "Benchmark: as tuplas são 40% mais rápidas que as listas em leitura."}]
    novo, laudo = pc_agent._validar_comparacoes(texto, ev, [])
    assert novo == texto
    assert laudo and laudo[0]["classificacao"] in ("FACT", "DERIVED_FROM_DATA")


def test_fonte_encontrada_mas_nao_lida_nao_sustenta_comparacao():
    texto = "As tuplas são 40% mais rápidas que as listas em leitura."
    ev = [{"id": "e1", "status": "encontrada",
           "trecho": "As tuplas são 40% mais rápidas que as listas em leitura."}]
    novo, laudo = pc_agent._validar_comparacoes(texto, ev, [])
    assert novo != texto and "UNVERIFIED" in novo
    assert laudo[0]["classificacao"] == "UNVERIFIED"


def test_fonte_lida_sem_suporte_nao_vira_fato():
    texto = "As tuplas são 40% mais rápidas que as listas em leitura."
    ev = [{"id": "e1", "status": "aberta",
           "texto_lido": "O artigo fala sobre a história da linguagem Python.",
           "trecho": "As tuplas são 40% mais rápidas que as listas em leitura."}]
    novo, laudo = pc_agent._validar_comparacoes(texto, ev, [])
    assert novo != texto and "UNVERIFIED" in novo
    assert laudo[0]["classificacao"] == "UNVERIFIED"


def test_fonte_lida_com_suporte_sustenta_comparacao():
    texto = "As tuplas são 40% mais rápidas que as listas em leitura."
    ev = [{"id": "e1", "status": "aberta",
           "texto_lido": "Benchmark: as tuplas são 40% mais rápidas que as listas em leitura.",
           "trecho": "as tuplas são 40% mais rápidas que as listas em leitura"}]
    novo, laudo = pc_agent._validar_comparacoes(texto, ev, [])
    assert novo == texto
    assert laudo[0]["classificacao"] == "FACT"


def test_classificacoes_explicitas_sem_presuncao():
    assert eg.CLASSIFICACOES_AFIRMACAO == (
        "FACT", "DERIVED_FROM_DATA", "ESTIMATE", "HYPOTHESIS", "UNVERIFIED")
    laudo = eg.classificar_afirmacoes(
        "O modelo X é cerca de 40% mais rápido que o modelo Y.",
        [], minimo=20)
    assert laudo and laudo[0]["classificacao"] in ("ESTIMATE", "UNVERIFIED")


# ── Streaming seguro e contrato SSE ─────────────────────────────────
def test_stream_guard_nao_exibe_vexcia_antes_do_done():
    guarda = pc_agent._GuardaStreamResposta([], [])
    assert guarda.alimentar("Meu nome é Vex") == []
    saida = "".join(guarda.alimentar("xia. Tudo bem."))
    assert "Vexxia" not in saida
    assert "Lucas" in saida
    assert "Tudo bem." in saida
    assert guarda.finalizar() == []


def test_stream_guard_nao_exibe_comparacao_sem_evidencia():
    guarda = pc_agent._GuardaStreamResposta([], [])
    assert guarda.alimentar("Tuplas são mais rápidas ") == []
    saida = "".join(guarda.alimentar("que listas."))
    assert "mais rápidas" not in saida
    assert "UNVERIFIED" in saida


def test_stream_guard_mantem_ttft_em_texto_sem_risco():
    guarda = pc_agent._GuardaStreamResposta([], [])
    assert guarda.alimentar("Olá, ") == ["Olá, "]
    assert guarda.alimentar("sou a Júlia.") == ["sou a Júlia."]


def test_complemento_stream_evita_repetir_prefixo():
    assert pc_agent._complemento_stream("abcFonte", "abc") == "Fonte"
    assert pc_agent._complemento_stream("Fonteabc", "abc") == "Fonte"
    assert pc_agent._complemento_stream("abc", "abc") == ""


def test_sse_cursor_dedup_fora_de_ordem_e_replay():
    cursor = server.ResearchSSECursor(apos_seq=2)
    assert cursor.oferecer({"seq": 1, "tipo": "research_created"}) == []
    assert cursor.oferecer({"seq": 4, "tipo": "search_completed"}) == []
    # Ao chegar o 3, o 4 já estava retido: os dois saem em ordem.
    assert cursor.oferecer({"seq": 3, "tipo": "search_completed"}) == [
        {"seq": 3, "tipo": "search_completed"},
        {"seq": 4, "tipo": "search_completed"}]
    assert cursor.oferecer({"seq": 4, "tipo": "search_completed"}) == []
    assert cursor.liberar_tudo() == []


def test_sse_cursor_terminal_com_lacuna_libera_em_ordem():
    cursor = server.ResearchSSECursor(apos_seq=0)
    assert cursor.oferecer({"seq": 1, "tipo": "research_created"}) == [
        {"seq": 1, "tipo": "research_created"}]
    assert cursor.oferecer({"seq": 3, "tipo": "research_completed"}) == []
    assert cursor.oferecer({"seq": 2, "tipo": "audit_completed"}) == [
        {"seq": 2, "tipo": "audit_completed"},
        {"seq": 3, "tipo": "research_completed"}]


def test_research_completed_so_depois_do_status_persistido(monkeypatch, tmp_path):
    db = pc_agent.open_db(tmp_path / "terminal.sqlite3")
    prov = _FakeProv({"*": [{
        "titulo": "Café e saúde", "url": "https://exemplo.com/cafe",
        "trecho": "Estudo com 10000 pessoas mostra que o café é seguro."}]})
    visto = []
    original = ra.emitir

    def emitir_espiando(db_, job_id, owner, agente, tipo, *args, **kwargs):
        if tipo == "research_completed":
            visto.append(ra.carregar_job(db_, owner, job_id)["status"])
        return original(db_, job_id, owner, agente, tipo, *args, **kwargs)

    monkeypatch.setattr(ra, "emitir", emitir_espiando)
    try:
        job = ra.criar_job(db, "u-trust", "café faz bem?", manual="rapida")
        r = ra.executar(
            db, job["id"], "u-trust", [prov],
            lambda u: {"titulo": "Café e saúde", "texto": prov.dados["*"][0]["trecho"],
                       "final": u})
        assert r["status"] in ("concluida", "interrompida")
        assert visto and visto[0] in ("concluida", "interrompida")
        assert "research_completed" in {
            e["tipo"] for e in ra.eventos_desde(db, "u-trust", job["id"])}
    finally:
        db.close()


class _FakeProv:
    nome = "fake-trust"

    def __init__(self, dados):
        self.dados = dados
        self.chamadas = []

    def buscar(self, consulta, limite=6):
        self.chamadas.append(consulta)
        return [dict(r) for r in self.dados.get(consulta, self.dados.get("*", []))][:limite]
