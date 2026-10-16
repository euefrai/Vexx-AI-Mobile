"""V5.0 Advanced Memory & Luccas Identity: identidade determinística,
perguntas de confirmação no chat, orçamento, projetos e continuidade."""
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pc_agent
import workspace_store
from assistant_identity import CONVERSATION_NAME, IDENTITY_RULES, OFFICIAL_NAME


def _db(nome="mem50.sqlite3"):
    return pc_agent.open_db(Path(tempfile.mkdtemp()) / nome)


def _cfg(**kw):
    base = {"system": "sys", "model": "m", "context": 5, "max_tokens": 50,
            "memoria_global": True, "pesquisa_web": False}
    base.update(kw)
    return base


def _diz(db, owner, conv, mid, texto):
    pc_agent.persist_messages(db, [{
        "id": mid, "conversation_id": conv, "origin": "mobile",
        "role": "user", "text": texto, "created_at": pc_agent.agora_iso()}], owner)
    return {"message_id": mid, "conversation_id": conv, "owner": owner}


# ── Identidade ────────────────────────────────────────────────────────

def test_nomes_oficiais():
    assert CONVERSATION_NAME == "Lucas"
    assert OFFICIAL_NAME == "Luccas Trawman"
    assert "nunca afirme ser humano" in IDENTITY_RULES.lower() or \
        "Não sou humano" in IDENTITY_RULES or "não sou humano" in IDENTITY_RULES


def test_cmd_identidade_nome():
    for q in ("Qual é o seu nome?", "como vc se chama", "se apresente", "quem é você"):
        texto, codigo = pc_agent.cmd_identidade(q)
        assert "Lucas" in texto and "Luccas Trawman" not in texto
        assert codigo == "id_nome"


def test_cmd_identidade_nome_completo():
    texto, codigo = pc_agent.cmd_identidade("qual seu nome completo?")
    assert "Luccas Trawman" in texto
    assert codigo == "id_nome_completo"


def test_cmd_identidade_natureza():
    texto, codigo = pc_agent.cmd_identidade("você é humano?")
    assert "IA" in texto and codigo == "id_natureza"


def test_cmd_identidade_correcao_educada():
    for q in ("obrigado júlia", "Oi Alexa", "Vexx"):
        texto, codigo = pc_agent.cmd_identidade(q)
        assert texto.startswith("Pode me chamar de Lucas")
        assert codigo == "id_correcao"


def test_cmd_identidade_nao_corrige_terceiros():
    assert pc_agent.cmd_identidade("minha filha Júlia mora longe") is None
    assert pc_agent.cmd_identidade("Júlia, resume o capítulo 3 e me conta uma piada") is None
    assert pc_agent.cmd_identidade("oi") is None
    assert pc_agent.cmd_identidade("qual a capital?") is None


def test_ai_completa_identidade_sem_llm(monkeypatch):
    db = _db()

    def _nunca(cfg, messages, **kw):
        raise AssertionError("identidade não usa LLM")

    monkeypatch.setattr(pc_agent, "gerar_texto", _nunca)
    out = pc_agent.ai_completa(
        db, _diz(db, "ana", "conv1", "msg-nome-01", "qual é o seu nome?"), _cfg())
    assert "Lucas" in out["response_text"]


# ── Confirmação no chat ──────────────────────────────────────────────

def test_pergunta_sensivel_vai_ao_chat(monkeypatch):
    db = _db()
    monkeypatch.setattr(pc_agent, "gerar_texto",
                        lambda *a, **k: {"texto": "Entendido.", "model_usado": "m",
                                         "latencia_s": 0.1})
    out = pc_agent.ai_completa(
        db, _diz(db, "ana", "conv1", "msg-sens-01",
                 "lembre-se que tomo remédio controlado para ansiedade"),
        _cfg())
    assert "não guardei ainda" in out["response_text"]
    assert pc_agent.ler_memorias(db, owner="ana") == []
    assert len(pc_agent.pendencias(db, "ana")) == 1


def test_confirmar_pendencia_apos_pergunta():
    db = _db()
    pc_agent.analisar_memoria(db, "lembre-se que tomo remédio X", "ana", "conv1", "m1")
    resp, codigo = pc_agent.interpretar_comando_memoria(db, "pode guardar", "ana")
    assert codigo == "mem_confirmar"
    assert pc_agent.ler_memorias(db, owner="ana")


# ── Falsas, duplicadas, contradições ──────────────────────────────────

def test_exemplo_nao_vira_memoria():
    db = _db()
    assert pc_agent.extrair_candidatos("suponha que meu nome seja Carlos") == []
    assert pc_agent.extrair_candidatos("exemplo: meu foco é maratonas") == []
    s, p, q = pc_agent.analisar_memoria(db, "imagine que minha prova seja amanhã",
                                        "ana", "conv1", "m1")
    assert pc_agent.ler_memorias(db, owner="ana") == []


def test_resave_identico_sem_churn():
    db = _db()
    pc_agent.registrar_memoria(db, "ana", "foco", "concursos", "trabalho", "objetivos",
                               "confirmada")
    antes = db.execute("SELECT updated_at FROM memories WHERE owner_id='ana' AND key='foco'"
                       ).fetchone()[0]
    n_antes = db.execute("SELECT COUNT(*) FROM memory_facts WHERE owner_id='ana'"
                         ).fetchone()[0]
    pc_agent.registrar_memoria(db, "ana", "foco", "concursos", "trabalho", "objetivos",
                               "confirmada")
    depois = db.execute("SELECT updated_at FROM memories WHERE owner_id='ana' AND key='foco'"
                        ).fetchone()[0]
    n_depois = db.execute("SELECT COUNT(*) FROM memory_facts WHERE owner_id='ana'"
                          ).fetchone()[0]
    assert antes == depois and n_antes == n_depois


def test_correcao_explicita_preserva_historico():
    db = _db()
    pc_agent.registrar_memoria(db, "ana", "nome", "Marina", "semantica", "identidade",
                               "confirmada")
    pc_agent.registrar_memoria(db, "ana", "nome", "Marina Souza", "semantica", "identidade",
                               "confirmada")
    assert pc_agent.ler_memorias(db, owner="ana")[0]["value"] == "Marina Souza"
    hist = db.execute("SELECT value, source FROM memory_facts WHERE owner_id='ana' AND key='nome'"
                      ).fetchall()
    assert {v for v, _ in hist} == {"Marina", "Marina Souza"}


# ── Orçamento e projetos ──────────────────────────────────────────────

def _projeto(db, owner, pid, titulo, chats=()):
    import datetime
    agora = datetime.datetime.now(datetime.timezone.utc).isoformat()
    recs = [{"id": pid, "kind": "project", "title": titulo, "project_id": "",
             "pinned": False, "archived": False, "deleted": False,
             "updated_at": agora, "change_id": "chg-" + pid}]
    for cid, ctitulo in chats:
        recs.append({"id": cid, "kind": "chat", "title": ctitulo, "project_id": pid,
                     "pinned": False, "archived": False, "deleted": False,
                     "updated_at": agora, "change_id": "chg-" + cid})
    workspace_store.merge_records(db, recs, owner)


def _fala(db, owner, conv, mid, role, texto):
    pc_agent.persist_messages(db, [{
        "id": mid, "conversation_id": conv, "origin": "mobile",
        "role": role, "text": texto, "created_at": pc_agent.agora_iso()}], owner)


def test_orcamento_memoria_no_prompt():
    db = _db()
    for i in range(30):
        pc_agent.registrar_memoria(db, "ana", f"assunto_{i:02d}",
                                   f"detalhe relevante sobre o tema {i:02d} " * 10,
                                   "semantica", "geral", "confirmada")
    msgs, _ = pc_agent.ai_montar_mensagens(db, "convx", _cfg(), "fale do tema", "ana")
    sistema = msgs[0]["content"]
    for chunk in sistema.split("\n\n"):
        if chunk.startswith("O QUE VOCÊ SABE"):
            assert len(chunk) <= 1650
            return
    raise AssertionError("bloco de memórias ausente")


def test_bloco_projetos_com_trechos_reais():
    db = _db()
    _projeto(db, "ana", "proj-pc", "Montagem do computador gamer",
             [("chat-pc1", "Peças do PC")])
    _fala(db, "ana", "chat-pc1", "m-pc-001", "user", "escolhi a placa-mãe B550")
    _fala(db, "ana", "chat-pc1", "m-pc-002", "assistant", "boa, falta o processador")
    bloco = pc_agent.bloco_projetos(db, "vamos continuar aquele computador", "outra", "ana")
    assert "Montagem do computador gamer" in bloco
    assert "B550" in bloco
    assert pc_agent.bloco_projetos(db, "vamos continuar aquele computador", "outra", "bob") == ""


def test_bloco_projetos_ignora_arquivado():
    db = _db()
    _projeto(db, "ana", "proj-velho", "Computador antigo", [])
    import datetime
    agora = datetime.datetime.now(datetime.timezone.utc).isoformat()
    workspace_store.merge_records(db, [{
        "id": "proj-velho", "kind": "project", "title": "Computador antigo",
        "project_id": "", "pinned": False, "archived": True, "deleted": False,
        "updated_at": agora, "change_id": "chg-zzz-arq"}], "ana")
    assert pc_agent.bloco_projetos(db, "continuar o computador antigo", "c", "ana") == ""


def test_cmd_projeto_continuacao_unica():
    db = _db()
    _projeto(db, "ana", "proj-pc", "Montagem do computador",
             [("chat-pc1", "Peças")])
    _fala(db, "ana", "chat-pc1", "m-uniq-1", "user", "fechei o gabinete em R$ 400")
    texto = pc_agent.cmd_projeto(
        db, "Lucas, vamos continuar aquele computador que eu estava montando",
        "ana", "outra")
    assert "Montagem do computador" in texto
    assert "R$ 400" in texto


def test_cmd_projeto_ambiguo_pergunta():
    db = _db()
    _projeto(db, "ana", "prj1", "Site da loja", [])
    _projeto(db, "ana", "prj2", "Site do portfólio", [])
    texto = pc_agent.cmd_projeto(db, "vamos continuar o site", "ana", "c")
    assert "mais de um projeto" in texto and "Qual deles retomamos?" in texto


def test_cmd_projeto_sem_match_lista():
    db = _db()
    _projeto(db, "ana", "prj1", "Horta de casa", [])
    texto = pc_agent.cmd_projeto(db, "vamos continuar o foguete", "ana", "c")
    assert "Horta de casa" in texto


def test_cmd_projeto_onde_paramos():
    db = _db()
    pc_agent.analisar_memoria(db, "lembre-se que tomo remédio X", "ana", "conv1", "m1")
    texto = pc_agent.cmd_projeto(db, "onde paramos?", "ana", "conv1")
    assert "Onde paramos" in texto
    assert pc_agent.cmd_projeto(db, "qual a capital?", "ana", "conv1") == ""


# ── Reinicialização e isolamento ──────────────────────────────────────

def test_recover_preserva_parcial_e_libera():
    db = _db()
    pc_agent.ai_marcar(db, "mid-rec-01", "conv1", "m", "processing",
                       reply_id="mid-rec-01-r1", response_text="parcial...",
                       owner="ana")
    pc_agent.recover_interrupted_ai(db)
    est = pc_agent.ai_estado(db, "mid-rec-01", owner="ana")
    assert est["state"] == "failed" and est["response_text"] == "parcial..."
    prep = pc_agent.ai_preparar(
        db, {"message_id": "mid-rec-02", "conversation_id": "conv1",
             "owner": "ana", "text": "oi", "created_at": pc_agent.agora_iso()},
        _cfg())
    assert "busy" not in prep and prep.get("user_text") == "oi"


def test_isolamento_projeto_e_pergunta():
    db = _db()
    _projeto(db, "ana", "proj-a", "Computador da Ana", [])
    pc_agent.analisar_memoria(db, "lembre-se que tomo remédio X", "ana", "conv1", "m1")
    assert pc_agent.bloco_projetos(db, "continuar o computador", "c", "bob") == ""
    assert "Nada em andamento" in pc_agent.cmd_projeto(db, "onde paramos?", "bob", "c")
    assert "remédio" in pc_agent.cmd_projeto(db, "onde paramos?", "ana", "conv1")
    assert pc_agent.pendencias(db, "bob") == []


def test_nota_continuidade_ao_cortar_contexto():
    db = _db()
    for i in range(20):
        _fala(db, "ana", "longa", f"m-long-{i:02d}", "user", f"mensagem {i:02d} " + "x" * 700)
    msgs, _ = pc_agent.ai_montar_mensagens(db, "longa", _cfg(contexto=50), "resuma tudo", "ana")
    assert "CONTINUIDADE" in msgs[0]["content"]
