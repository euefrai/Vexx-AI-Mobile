"""Módulo do PC Agent: Preparação/continuação de requisições de IA e sintetizadores de estudo (provas, reforço, aulas)."""
import hermes_bridge
import jdui
import json
import julia_auth as JULIA_auth
import learning
import providers
import re
import threading
import workspace_store

from assistant_identity import system_with_identity

from pc_modules.db_core import (
    agora_iso, DONO_PADRAO, dono_valido, gerar_texto, log, persist_messages,
)
from pc_modules.memory_store import _contexto_local_seguro, _instrucoes_contexto_local
from pc_modules.context_providers import ai_estado, ai_marcar, contexto_conversa, dono_bloqueado
from pc_modules.calendar_projects import analisar_memoria

# Símbolos de módulos posteriores injetados na inicialização do pacote:
_texto_seguro = None  # provido por pc_modules.ai_pipeline

ESTUDO_TERMOS = frozenset((
    "prova", "quiz", "estudo", "estudar", "assunto", "errei", "erros", "erradas",
    "plano", "revisao", "revisão", "flashcard", "nota", "desempenho", "progresso",
    "simulado", "questao", "questão", "questões", "aprender", "aula", "reforco", "reforço",
))


def linha_desempenho(db, owner: str) -> str:
    """Resumo real de estudo para o prompt (V4.2 §8/§9).

    Só números registrados; sem dados → '' (o modelo diz que não há dados).
    """
    try:
        res = learning.resumo_progresso(db, owner)
        perf = learning.desempenho_por_assunto(db, owner)
    except Exception:
        return ""
    if not res.get("respostas") and not res.get("itens_plano"):
        return ""
    partes = [f"provas concluídas {res['concluidas']}, acertos {res['acertos']}/{res['respostas']}"]
    if perf:
        partes.append("por assunto: " + "; ".join(
            f"{p['assunto']} {p['taxa']:.0%} ({p['acertos']}/{p['total']})" for p in perf[:6]))
    if res.get("revisoes_pendentes"):
        partes.append(f"{res['revisoes_pendentes']} cartões vencendo")
    if res.get("itens_plano"):
        partes.append(f"plano: {res['itens_feitos']}/{res['itens_plano']} itens feitos")
    return ("DESEMPENHO REAL DO USUÁRIO (use estes números; não invente outros; "
            "se perguntarem o que não está aqui, diga que ainda não há dados):\n- "
            + "\n- ".join(partes))


_AI_PREPARE_LOCK = threading.RLock()


def ai_preparar(db, payload: dict, cfg: dict) -> dict:
    # The websocket worker and SSE threads must not claim the same message twice.
    with _AI_PREPARE_LOCK:
        return _ai_preparar(db, payload, cfg)


def _ai_preparar(db, payload: dict, cfg: dict) -> dict:
    """Valida e aplica idempotência. Retorna {user_text, model, reply_id} ou {replay|busy|error}."""
    mid = payload.get("message_id", "")
    conv = payload.get("conversation_id", "")
    if not (isinstance(mid, str) and 8 <= len(mid) <= 100):
        return {"error": "message_id inválido.", "codigo": "invalido"}
    if not (isinstance(conv, str) and 3 <= len(conv) <= 100):
        return {"error": "conversation_id inválido.", "codigo": "invalido"}
    modelo = payload.get("model") or cfg["model"]
    if not (isinstance(modelo, str) and 1 <= len(modelo) <= 120):
        return {"error": "Modelo inválido.", "codigo": "invalido"}
    owner = dono_valido(payload.get("owner"))
    if workspace_store.chat_deleted(db, owner, conv):
        return {"error": "Conversa excluída.", "codigo": "excluida"}
    if dono_bloqueado(db, owner):
        return {"error": "Conta indisponível.", "codigo": "bloqueada"}
    identity = db.execute("SELECT conversation_id, role, text FROM messages WHERE id=? "
                          "AND origin='mobile' AND owner_id=?", (mid, owner)).fetchone()
    if identity and identity[:2] != (conv, "user"):
        return {"error": "Identificador da mensagem pertence a outra conversa ou papel.", "codigo": "invalido"}
    if identity and payload.get("text") and identity[2] != payload["text"]:
        return {"error": "Este identificador já está associado a outra mensagem.", "codigo": "conflito"}
    previo = ai_estado(db, mid, owner)
    if previo and previo["state"] == "completed":
        return {"replay": True, "reply_id": previo["reply_id"],
                "response_text": previo["response_text"], "model": previo["model"]}
    if previo and previo["state"] in ("queued", "processing"):
        return {"busy": True}
    proxy = cfg.get('proxy') or hermes_bridge.DEFAULT_PROXY_URL
    if not payload.get('model') and cfg.get('model_implicit'):
        modelo = providers.cached_default(proxy, modelo)
    selection_error = providers.selection_error(modelo, proxy)
    if selection_error:
        return selection_error
    lim = JULIA_auth.limites_usuario(db, owner)
    if JULIA_auth.simultaneas_ia(db, owner) >= lim["max_ia_simult"]:
        return {"error": "Muitas gerações ao mesmo tempo; aguarde.", "codigo": "limite"}
    if JULIA_auth.uso_ia_hora(db, owner) >= lim["max_ai_hora"]:
        return {"error": "Limite de uso da IA por hora atingido.", "codigo": "limite"}
    row = db.execute("SELECT text FROM messages WHERE id=? AND origin='mobile' "
                     "AND owner_id=? AND role='user' AND conversation_id=?", (mid, owner, conv)).fetchone()
    if not row:
        # Anti-corrida sync→IA: o pedido traz o texto; persiste (mesmas regras
        # do /api/sync, INSERT OR IGNORE) e segue. Sem texto válido, aí sim falha.
        texto_pb = payload.get("text", "")
        criado_pb = payload.get("created_at", "") or agora_iso()
        if isinstance(texto_pb, str) and 1 <= len(texto_pb) <= 10000:
            persist_messages(db, [{"id": mid, "conversation_id": conv, "origin": "mobile",
                                   "role": "user", "text": texto_pb,
                                   "created_at": criado_pb[:48]}], owner)
            row = db.execute("SELECT text FROM messages WHERE id=? AND origin='mobile' "
                             "AND owner_id=? AND role='user' AND conversation_id=?",
                             (mid, owner, conv)).fetchone()
            if row:
                log.info("IA com piggyback (msg %s não estava no PC)", mid)
    if not row:
        return {"error": "Mensagem do usuário não encontrada. Sincronize primeiro.",
                "codigo": "sem_mensagem"}
    try:
        salvos, propostas, pergunta = analisar_memoria(db, row[0], owner, conv, mid)
    except Exception:
        salvos, propostas, pergunta = [], [], None
    mem_flag = payload.get("memory", payload.get("memoria_global", None))
    memoria_on = cfg.get("memoria_global", True) if mem_flag is None else (str(mem_flag) == "1")
    ai_marcar(db, mid, conv, modelo, "queued", owner=owner)
    return {"user_text": row[0], "model": modelo,
            "reply_id": f"{mid}-r1", "conversation_id": conv,
            "memoria_global": memoria_on, "owner": owner,
            "pergunta_memoria": pergunta or "",
            "contexto_local": _contexto_local_seguro(payload)}


def ai_guardar_resposta(db, mid, conv, modelo, reply_id, texto, owner=DONO_PADRAO) -> None:
    owner = dono_valido(owner)
    with db:
        if not db.in_transaction:
            db.execute("BEGIN IMMEDIATE")
        if workspace_store.chat_deleted(db, owner, conv):
            return
        db.execute("""INSERT OR IGNORE INTO messages
            (id, conversation_id, origin, role, text, created_at, received_at, model, owner_id)
            VALUES (?, ?, 'mobile', 'assistant', ?, ?, ?, ?, ?)""",
            (reply_id, conv, texto, agora_iso(), agora_iso(), modelo, owner))
        db.execute("""UPDATE messages SET text=?, received_at=? WHERE id=?
                      AND origin='mobile' AND owner_id=?""",
                   (texto, agora_iso(), reply_id, owner))
    ai_marcar(db, mid, conv, modelo, "completed",
              reply_id=reply_id, response_text=texto, owner=owner)


def ai_resetar(db, payload: dict) -> dict:
    """Regenerar: apaga pedido anterior + resposta para recomputar do zero."""
    owner = dono_valido(payload.get("owner"))
    mid = payload.get("message_id", "")
    conv = payload.get("conversation_id", "")
    if not (isinstance(mid, str) and 8 <= len(mid) <= 100):
        return {"error": "message_id inválido.", "codigo": "invalido"}
    row = db.execute("SELECT 1 FROM messages WHERE id=? AND origin='mobile' AND owner_id=? "
                     "AND role='user' AND conversation_id=?", (mid, owner, conv)).fetchone()
    if not row:
        return {"error": "Mensagem não encontrada.", "codigo": "sem_mensagem"}
    with db:
        db.execute("DELETE FROM ai_requests WHERE user_message_id=? AND owner_id=?", (mid, owner))
        db.execute("DELETE FROM messages WHERE id=? AND origin='mobile' AND owner_id=?",
                   (f"{mid}-r1", owner))
    return {"ok": True, "reply_id": f"{mid}-r1"}


def ai_continuar(db, payload: dict, cfg: dict) -> dict:
    """Continuar: gera a continuação e ANEXA à mesma resposta (mesmo reply_id)."""
    owner = dono_valido(payload.get("owner"))
    mid = payload.get("message_id", "")
    conv = payload.get("conversation_id", "")
    if not (isinstance(mid, str) and 8 <= len(mid) <= 100):
        return {"error": "message_id inválido.", "codigo": "invalido"}
    est = ai_estado(db, mid, owner)
    if not est or not (est.get("response_text") or "").strip():
        return {"error": "Nada para continuar.", "codigo": "sem_resposta"}
    modelo = payload.get("model") or est.get("model") or cfg["model"]
    cfg_eff = dict(cfg, memoria_global=True)
    historico = contexto_conversa(db, conv, min(cfg["context"], 8), owner)
    contexto_local = _contexto_local_seguro(payload)
    sistema = "\n".join([system_with_identity(cfg["system"]), *_instrucoes_contexto_local(contexto_local)])
    messages = ([{"role": "system", "content": sistema}] + historico
                + [{"role": "assistant", "content": (est["response_text"] or "")[-4000:]},
                   {"role": "user", "content": "Continue exatamente de onde parou, sem repetir o que já disse."}])
    ai_marcar(db, mid, conv, modelo, "processing", owner=owner)
    try:
        res = gerar_texto(cfg, messages, preferido=modelo)
    except hermes_bridge.BridgeErro as exc:
        ai_marcar(db, mid, conv, modelo, "failed", error=str(exc), owner=owner)
        return {"error": str(exc), "codigo": exc.codigo}
    modelo = res.get("model_usado", modelo)
    trecho = _texto_seguro((res.get("texto") or "").strip(), mid).strip()
    if not trecho:
        return {"error": "Modelo não continuou.", "codigo": "vazia"}
    anterior = (est["response_text"] or "").rstrip()
    combinado = anterior + ("" if anterior.endswith((" ", "\n")) else " ") + trecho
    ai_guardar_resposta(db, mid, conv, modelo, est["reply_id"] or f"{mid}-r1", combinado, owner)
    return {"reply_id": est["reply_id"], "response_text": combinado, "model": modelo}


PROVA_TRIGGERS = ("prova", "simulado", "avalia", "discursiva", "valendo nota",
                  "teste final", "exame")


def intencao_prova(texto: str) -> bool:
    t = (texto or "").lower()
    return any(k in t for k in PROVA_TRIGGERS)


def sintetizar_prova(db, cfg: dict, owner: str, texto_usuario: str) -> str:
    """Gera prova formal via LLM e guarda como assessment. Retorna fence exam ou ''."""
    m = re.search(r"(\d{1,2})\s*(quest|pergunt|itens|items)", texto_usuario or "")
    n = min(max(int(m.group(1)) if m else 5, 1), 10)
    prompt = ("Crie uma avaliação com %d questões em JSON (SÓ o JSON, sem cercas): "
              "[{\"enunciado\": \"...\", \"tipo\": \"multipla|vf|curta|discursiva\", "
              "\"opcoes\": [\"...\"], \"gabarito\": <índice ou texto ou critérios>, "
              "\"explicacao\": \"...\", \"dificuldade\": \"facil|media|dificil\", \"assunto\": \"...\"}]. "
              "multipla/vf: gabarito é o ÍNDICE (número); curta: texto exato; "
              "discursiva: gabarito com critérios de correção (30+ chars). "
              "Assunto: %s" % (n, (texto_usuario or "")[:300]))
    try:
        res = gerar_texto(cfg,
            [{"role": "system", "content": "Você gera avaliações. Responda SÓ JSON válido."},
             {"role": "user", "content": prompt}], max_tokens=2000)
        corpo = (res.get("texto") or "").strip()
        m2 = re.search(r"```(?:json)?\s*\n?([\s\S]*?)```", corpo)
        if m2:
            corpo = m2.group(1).strip()
        obj = json.loads(corpo)
        lista = obj if isinstance(obj, list) else obj.get("questions", [])
        validas = []
        for q in lista if isinstance(lista, list) else []:
            try:
                validas.append(learning.validar_questao(q if isinstance(q, dict) else {}))
            except learning.LearnErro:
                continue
        if len(validas) < 2:
            return ""
        titulo = re.sub(r"\s+", " ", (texto_usuario or "Prova")).strip()[:80] or "Prova"
        av = learning.criar_assessment(db, owner, titulo, validas[0].get("assunto", ""),
                                       validas, origem="ia")
        fence = {"version": jdui.VERSION, "blocks": [
            {"type": "text", "content": f"Prova pronta: **{titulo}** ({len(validas)} questões). Boa prova! 📝"},
            {"type": "ui", "component": "exam",
             "props": {"assessment_id": av["id"], "title": titulo}}]}
        ok, norm, _ = jdui.validar_mensagem(fence)
        if not ok:
            return ""
        return "\n\n```jdui\n" + json.dumps(norm, ensure_ascii=False) + "\n```"
    except Exception as exc:
        log.warning("síntese de prova falhou (%s)", type(exc).__name__)
        return ""


REFORCO_TRIGGERS = ("errei", "errada", "errado", "reforço", "reforco")

def intencao_reforco(texto: str) -> bool:
    """'faz outro simulado só com o que errei' — reforço sobre erros reais."""
    t = (texto or "").lower()
    return intencao_prova(texto) and any(k in t for k in REFORCO_TRIGGERS)


def sintetizar_reforco(db, owner: str, texto_usuario: str) -> str:
    """Monta simulado SÓ com questões que o dono errou (determinístico, sem LLM).

    Retorna fence exam ou '' (sem erros recentes: o chamador informa com texto).
    """
    try:
        m = re.search(r"(\d{1,2})\s*(quest|pergunt|itens|items)", texto_usuario or "")
        n = min(max(int(m.group(1)) if m else 10, 1), 20)
        ref = learning.criar_reforco(db, owner, n)
        av = learning.obter_assessment(db, owner, ref["id"])
        titulo = "Reforço (%d %s)" % (len(av["questions"]),
                                      "questão" if len(av["questions"]) == 1 else "questões")
        fence = {"version": jdui.VERSION, "blocks": [
            {"type": "text", "content": f"Montei um reforço com o que você errou: **{titulo}**. Bora recuperar! 💪"},
            {"type": "ui", "component": "exam",
             "props": {"assessment_id": ref["id"], "title": titulo}}]}
        ok, norm, _ = jdui.validar_mensagem(fence)
        if not ok:
            return ""
        return "\n\n```jdui\n" + json.dumps(norm, ensure_ascii=False) + "\n```"
    except learning.LearnErro as exc:
        if exc.codigo == "sem_dados":
            return ("\n\nNão encontrei questões erradas recentes suas para montar o reforço. "
                    "Faça um quiz ou prova primeiro — aí eu monto um simulado só com o que errou. 📚")
        log.warning("reforço falhou (%s)", type(exc).__name__)
        return ""
    except Exception as exc:
        log.warning("reforço falhou (%s)", type(exc).__name__)
        return ""


AULA_TRIGGERS = ("aula", "me ensina", "me ensine", "curso sobre", "curso de", "licao", "lição")


def intencao_aula(texto: str) -> bool:
    """Pedido explícito de aula persistida (não confundir com explicação avulsa)."""
    t = (texto or "").lower()
    return any(k in t for k in AULA_TRIGGERS)


def sintetizar_aula(db, cfg: dict, owner: str, texto_usuario: str) -> str:
    """Gera aula canônica via LLM, valida contra o schema e persiste.

    Falha de geração/validação → '' (o chat responde em texto normalmente).
    Markdown comum nunca vira aula: só fence `lesson` com id persistido.
    """
    prompt = ("Crie uma aula em JSON (SÓ o JSON, sem cercas): "
              "{\"assunto\": \"...\", \"objetivo\": \"...\", "
              "\"nivel\": \"iniciante|basico|intermediario|avancado\", "
              "\"secoes\": [{\"titulo\": \"...\", \"explicacao\": \"...\" (2+ parágrafos), "
              "\"exemplo\": \"...\", \"exercicio\": \"...\"}] (3 a 6 seções, progressivas), "
              "\"resumo\": \"...\"}. "
              "Assunto pedido: %s" % ((texto_usuario or "")[:300]))
    try:
        res = gerar_texto(cfg,
            [{"role": "system", "content": "Você cria aulas. Responda SÓ JSON válido."},
             {"role": "user", "content": prompt}], max_tokens=3000)
        corpo = (res.get("texto") or "").strip()
        m2 = re.search(r"```(?:json)?\s*\n?([\s\S]*?)```", corpo)
        if m2:
            corpo = m2.group(1).strip()
        obj = json.loads(corpo)
        if not isinstance(obj, dict):
            return ""
        aula = learning.criar_aula(db, owner, obj, origem="ia")
        titulo = "Aula: %s" % (obj.get("assunto", "")[:80] or "nova aula")
        fence = {"version": jdui.VERSION, "blocks": [
            {"type": "text", "content": f"Preparei uma aula para você: **{titulo}**. Bons estudos! 📖"},
            {"type": "ui", "component": "lesson",
             "props": {"lesson_id": aula["id"], "title": titulo}}]}
        ok, norm, _ = jdui.validar_mensagem(fence)
        if not ok:
            return ""
        return "\n\n```jdui\n" + json.dumps(norm, ensure_ascii=False) + "\n```"
    except Exception as exc:
        log.warning("síntese de aula falhou (%s)", type(exc).__name__)
        return ""


GRAFICO_TRIGGERS = ("gráfico", "grafico", "evolução", "evolucao", "em barras", "em pizza")
EVOLUCAO_TRIGGERS = ("simulado", "prova", "desempenho", "nota", "progresso", "tentativa",
                     "evolução", "evolucao")


def intencao_grafico_evolucao(texto: str) -> bool:
    """'mostre a evolução dos meus simulados' — gráfico sobre dados reais."""
    t = (texto or "").lower()
    return any(k in t for k in GRAFICO_TRIGGERS) and any(k in t for k in EVOLUCAO_TRIGGERS)


def sintetizar_grafico_evolucao(db, owner: str) -> str:
    """Monta gráfico line dos simulados a partir do histórico real (sem LLM).

    Sem tentativas: texto honesto. Números saem do SQLite, o modelo só explica.
    """
    hist = learning.historico_tentativas(db, owner, 20)
    if not hist:
        return ("\n\nVocê ainda não tem simulados concluídos para mostrar em gráfico. "
                "Faça uma prova primeiro — aí eu desenho sua evolução. 📈")
    cron = list(reversed(hist))
    labels = [(h["em"] or "")[5:10].replace("-", "/") or f"T{i + 1}" for i, h in enumerate(cron)]
    valores = [round((h["nota"] or 0) * 100, 1) for h in cron]
    fence = {"version": jdui.VERSION, "blocks": [
        {"type": "text", "content": "Sua evolução nos simulados: 📈"},
        {"type": "ui", "component": "chart",
         "props": {"type": "line", "title": "Evolução dos simulados",
                   "labels": labels, "series": [{"label": "nota %", "values": valores}],
                   "source": "seu histórico de provas", "y_label": "%"}}]}
    ok, norm, _ = jdui.validar_mensagem(fence)
    if not ok:
        return ""
    return "\n\n```jdui\n" + json.dumps(norm, ensure_ascii=False) + "\n```"
