"""Módulo do PC Agent: Memória persistente, busca FTS, contexto temporal/local e comandos de memória."""
import re
import sqlite3
import unicodedata

from assistant_identity import (
    CONVERSATION_NAME, OFFICIAL_NAME, pergunta_identidade_produto, resposta_identidade_produto,
)
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pc_modules.db_core import _fts_sync, agora_iso, DONO_PADRAO, dono_valido, log

# Símbolos de módulos posteriores injetados na inicialização do pacote:
CONFIRM_RE = None  # provido por pc_modules.calendar_projects
atualizar_evento = None  # provido por pc_modules.calendar_projects
confirmar_pendencia = None  # provido por pc_modules.calendar_projects
descartar_pendencia = None  # provido por pc_modules.calendar_projects
pendencias = None  # provido por pc_modules.calendar_projects
proximos_eventos = None  # provido por pc_modules.calendar_projects

# ── Memória compartilhada entre sessões ──────────────────────────────
def salvar_fatos(db, texto: str, owner=DONO_PADRAO) -> None:
    """Heurística de fundo (respeita 'desativar armazenamento'; explícito passa direto)."""
    owner = dono_valido(owner)
    if not aprendizado_ativo(db, owner):
        return
    import re
    if not isinstance(texto, str):
        return
    t = texto.strip()
    padroes = [
        (r"(?i)lembre-?se (?:que |de que |disso:?\s?)(.{3,300})", "fato"),
        (r"(?i)(?:meu nome é|me chamo|sou o|sou a)\s+(.{2,80})", "nome"),
        (r"(?i)(?:meu foco é|minha meta é|estou trabalhando (?:em|com))\s+(.{3,200})", "foco"),
        (r"(?i)(?:prefiro|gosto de|não gosto de)\s+(.{3,200})", "preferencia"),
    ]
    achou = False
    with db:
        for rx, chave in padroes:
            m = re.search(rx, t)
            if m:
                valor = re.sub(r"\s+", " ", m.group(1)).strip(" .;:")[:300]
                if valor:
                    db.execute("""INSERT INTO memories (owner_id, key, value, updated_at)
                        VALUES (?, ?, ?, ?) ON CONFLICT(owner_id, key) DO UPDATE SET
                        value=excluded.value, updated_at=excluded.updated_at""",
                        (owner, chave, valor, agora_iso()))
                    achou = True
    if achou:
        log.info("memória atualizada a partir da conversa")


def ler_memorias(db, owner=DONO_PADRAO, status: str = "confirmada") -> list:
    try:
        rows = db.execute("SELECT key, value, tipo, assunto, status, origem_conv, origem_msg, "
                          "valido_ate, updated_at FROM memories WHERE owner_id=? AND status=? "
                          "ORDER BY updated_at DESC LIMIT 40", (dono_valido(owner), status)).fetchall()
    except Exception:
        return []
    return [{"key": k, "value": v, "tipo": t, "assunto": a, "status": s,
             "origem_conv": oc, "origem_msg": om, "valido_ate": va, "updated_at": u}
            for k, v, t, a, s, oc, om, va, u in rows if v]


def buscar_fts(db, owner: str, consulta: str, limite: int = 10) -> set:
    """Busca textual FTS5 (vazia se indisponível). Retorna chaves ranqueadas."""
    try:
        toks = [t for t in re.findall(r"[a-zà-ú0-9]{2,}", (consulta or "").lower()) if len(t) > 2][:8]
        if not toks:
            return set()
        q = " OR ".join(f'"{t}"*' for t in toks)
        rows = db.execute("SELECT key FROM memories_fts WHERE memories_fts MATCH ? "
                          "AND owner_id=? LIMIT ?", (q, owner, limite)).fetchall()
        return {r[0] for r in rows}
    except Exception:
        return set()


def data_curta(iso: str) -> str:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", (iso or "")[:10])
    return f"{m.group(3)}/{m.group(2)}" if m else ""


def proveniencia(f: dict) -> str:
    """Selo de origem para o prompt: '(guardado em 12/10)'."""
    d = data_curta(f.get("updated_at", ""))
    return f" (guardado em {d})" if d else ""


def memoria_global(db, conversation_id: str, limite_outras: int = 8, owner=DONO_PADRAO) -> list:
    """Últimas mensagens de OUTRAS conversas + fatos salvos, para injetar no prompt."""
    owner = dono_valido(owner)
    try:
        rows = db.execute("""SELECT conversation_id, role, text FROM messages
                             WHERE origin='mobile' AND owner_id=? AND conversation_id != ?
                             ORDER BY created_at DESC, id DESC LIMIT ?""",
                          (owner, conversation_id, limite_outras)).fetchall()
    except Exception:
        rows = []
    blocos = []
    for conv, role, text in reversed(rows):
        if role in ("user", "assistant") and text:
            blocos.append(f"[{conv[-6:]}|{role}]: {(text or '')[:300]}")
    fatos = ler_memorias(db, owner)
    if fatos:
        blocos.append("FATOS SALVOS: " + "; ".join(f"{f['key']}={f['value'][:150]}" for f in fatos))
    return blocos


PALAVRAS_VAZIAS_MEMORIA = {
    "a", "ao", "aos", "as", "com", "como", "da", "das", "de", "dela",
    "dele", "do", "dos", "e", "ela", "ele", "em", "era", "esse", "essa",
    "esta", "foi", "me", "meu", "meus", "minha", "minhas", "na", "nas",
    "no", "nos", "o", "os", "ou", "para", "por", "qual", "quando", "que",
    "se", "sobre", "seu", "seus", "sua", "suas", "um", "uma", "voce",
}


def _tokens_memoria(texto: str) -> set:
    sem_acentos = "".join(
        c for c in unicodedata.normalize("NFKD", (texto or "").lower())
        if not unicodedata.combining(c))
    tokens = {t for t in re.findall(r"[a-z0-9]{3,}", sem_acentos)
              if t not in PALAVRAS_VAZIAS_MEMORIA}
    return tokens | {t[:-1] for t in tokens if len(t) > 4 and t.endswith("s")}


def _contexto_local_seguro(payload: dict) -> dict:
    """Valida o relógio e a localização explícitos do aparelho."""
    contexto = {}
    instante = str(payload.get("local_time", ""))[:48]
    try:
        if not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})",
                instante):
            raise ValueError("timestamp sem fuso ou malformado")
        instante_local = datetime.fromisoformat(instante.replace("Z", "+00:00"))
        if instante_local.utcoffset() is None:
            raise ValueError("timestamp sem deslocamento UTC")
        contexto["current_at"] = instante_local
        contexto["local_time"] = instante_local.isoformat(timespec="seconds")
    except ValueError:
        instante_local = None
    zona = str(payload.get("timezone", ""))[:80]
    try:
        if not re.fullmatch(r"[A-Za-z0-9_+.-]+(?:/[A-Za-z0-9_+.-]+){0,4}", zona):
            raise ValueError("fuso malformado")
        timezone_local = ZoneInfo(zona)
        contexto["timezone"] = zona
        if instante_local is not None:
            contexto["current_at"] = instante_local.astimezone(timezone_local)
            contexto["local_time"] = contexto["current_at"].isoformat(timespec="seconds")
    except (ValueError, ZoneInfoNotFoundError):
        contexto.pop("timezone", None)
    cidade = re.sub(r"[\r\n<>]", " ", str(payload.get("city", ""))).strip()[:100]
    if cidade:
        contexto["city"] = cidade
    try:
        lat = float(payload["latitude"])
        lon = float(payload["longitude"])
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            contexto["coordinates"] = (round(lat, 2), round(lon, 2))
    except (KeyError, TypeError, ValueError):
        pass
    img = str(payload.get("image") or payload.get("image_url") or payload.get("image_b64") or "").strip()
    if img:
        contexto["image"] = img[:2_000_000]
    imgs = payload.get("images")
    if isinstance(imgs, (list, tuple)):
        limpas = [str(i).strip()[:2_000_000] for i in imgs[:5] if isinstance(i, str) and str(i).strip()]
        if limpas:
            contexto["images"] = limpas
    v_eng = str(payload.get("vision_engine") or payload.get("yolo_engine") or "").strip().lower()
    if v_eng in ("local", "pc", "huggingface", "hf", "nuvem", "auto"):
        contexto["vision_engine"] = v_eng
    return contexto


def _data_local(contexto_local: dict | None):
    instante = (contexto_local or {}).get("current_at")
    return instante.date() if isinstance(instante, datetime) else None


def _normalizar_temporal(texto: str) -> str:
    sem_acentos = "".join(
        c for c in unicodedata.normalize("NFKD", (texto or "").lower())
        if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sem_acentos).strip()


def _resposta_temporal_direta(texto: str, contexto_local: dict) -> str | None:
    """Responde consultas inequívocas do relógio/calendário sem chamar o LLM."""
    instante = contexto_local.get("current_at")
    if not isinstance(instante, datetime):
        return None
    pedido = _normalizar_temporal(texto)
    local = contexto_local.get("timezone", "")
    if not local:
        offset = instante.strftime("%z")
        local = "UTC" if offset in ("+0000", "-0000") else (
            f"UTC{offset[:3]}:{offset[3:]}" if offset else "")
    sufixo = f" ({local})" if local else ""
    hora_re = r"\b(que horas (sao|e)|qual (e )?a hora|hora atual|horario atual)\b"
    pergunta_hora = re.search(hora_re, pedido)
    local_especifico = re.search(r"\b(em|no|na|de)\s+(?!minha\b|meu\b)[a-z]", pedido)
    if pergunta_hora and not local_especifico:
        if re.search(r"\b(data|dia|hoje)\b", pedido):
            dias = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
                    "sexta-feira", "sábado", "domingo")
            return (f"Hoje é {dias[instante.weekday()]}, {instante:%d/%m/%Y}; "
                    f"agora são {instante:%H:%M}{sufixo}.")
        return f"São {instante:%H:%M}{sufixo}."
    if pergunta_hora:
        return None

    dias = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
            "sexta-feira", "sábado", "domingo")
    dia_pedido = re.search(r"\b(amanha|ontem|hoje|daqui a (\d{1,4}) dias?)\b", pedido)
    pergunta_data = re.search(
        r"\b(data|dia|calendario)\b.*\b(hoje|amanha|ontem|daqui a \d{1,4} dias?)\b|"
        r"\b(que dia (e|sera|vai ser)|qual (e )?a data)\b.*"
        r"\b(hoje|amanha|ontem|daqui a \d{1,4} dias?)\b", pedido)
    if not dia_pedido or not pergunta_data:
        if re.search(r"\b(que dia e hoje|qual dia da semana e hoje|dia da semana hoje)\b", pedido):
            return f"Hoje é {dias[instante.weekday()]}{sufixo}."
        return None
    termo = dia_pedido.group(1)
    delta = -1 if termo == "ontem" else 1 if termo == "amanha" else 0
    if termo.startswith("daqui a "):
        delta = int(dia_pedido.group(2))
    alvo = instante.date() + timedelta(days=delta)
    return f"{dias[alvo.weekday()]}, {alvo:%d/%m/%Y}{sufixo}."


def _instrucoes_contexto_local(contexto_local: dict | None) -> list[str]:
    instrucoes = []
    contexto_local = contexto_local or {}
    instante = contexto_local.get("current_at")
    if isinstance(instante, datetime):
        hora = contexto_local.get("local_time", "")
        zona = contexto_local.get("timezone", "")
        dias = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
                "sexta-feira", "sábado", "domingo")
        data_dia = f"{dias[instante.weekday()]}, {instante:%d/%m/%Y}"
        instrucoes.append(
            "FONTE AUTORITATIVA DE DATA/HORA PARA ESTA MENSAGEM: relógio do aparelho "
            "(use estes valores, não sua memória nem o relógio do computador): " +
            f"instante local {hora}; data e dia local {data_dia}; " +
            (f"fuso IANA {zona}" if zona else "") +
            ". Para hoje/amanhã/ontem, dias da semana, prazos e contagens, "
            "calcule a partir desta data local; confira o calendário e não estime. "
            "Não confunda a data atual com fatos externos que exigem pesquisa. "
            "Se faltar fuso ou houver ambiguidade, diga isso e pergunte; nunca invente.")
    else:
        instrucoes.append(
            "DATA E HORA: não foi recebido um relógio local válido para esta mensagem. "
            "Não invente nem deduza a data, hora ou dia da semana atuais; se a resposta "
            "depender disso, informe a limitação e peça o fuso ou a data.")
    zona = contexto_local.get("timezone", "")
    if zona and not isinstance(instante, datetime):
        instrucoes.append(f"O fuso informado pelo aparelho é {zona}, mas sem data/hora confiável.")
    cidade = contexto_local.get("city", "")
    coords = contexto_local.get("coordinates")
    if cidade or coords:
        local = f"região escolhida pelo usuário: {cidade}" if cidade else "local aproximado do aparelho"
        if coords:
            local += f"; coordenadas arredondadas: {coords[0]}, {coords[1]}"
        instrucoes.append(
            "LOCALIZAÇÃO COMPARTILHADA PELO USUÁRIO SÓ PARA ESTA PERGUNTA: " +
            local + ". Não deduza endereço exato nem afirme que há rastreamento contínuo.")
    return instrucoes


def lembrancas_relevantes(db, pergunta: str, conversation_id: str,
                           k: int = 4, owner=DONO_PADRAO) -> list:
    """Recupera falas antigas do próprio usuário por assunto, sem presumir fatos."""
    tokens = _tokens_memoria(pergunta)
    if not tokens:
        return []
    try:
        rows = db.execute(
            """SELECT conversation_id, text, created_at FROM messages
               WHERE origin='mobile' AND role='user' AND owner_id=?
                 AND conversation_id != ?
               ORDER BY created_at DESC, id DESC""",
            (dono_valido(owner), conversation_id))
    except sqlite3.Error as exc:
        log.warning("busca no histórico falhou: %s", type(exc).__name__)
        return []
    scored = []
    for conv, text, created in rows:
        corpo = (text or "").strip()
        correspondencias = tokens & _tokens_memoria(corpo)
        if not correspondencias:
            continue
        score = len(correspondencias) * 3 + sum(len(t) >= 7 for t in correspondencias)
        scored.append((score, created or "", conv, corpo))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        del scored[max(0, min(k, 8)):]
    return [{"conversation_id": conv, "created_at": created, "text": text[:700]}
            for _, created, conv, text in scored]


TIPOS_MEMORIA = ("semantica", "temporal", "episodica", "trabalho")
STATUS_MEMORIA = ("confirmada", "pendente", "contraditoria", "arquivada")

SENSIVEIS = ("saude", "saúde", "doenca", "doença", "remedio", "remédio", "medicamento",
             "exame", "hospital", "depressao", "depressão", "ansiedade", "terapia",
             "salario", "salário", "cpf", "rg", "endereco", "endereço", "telefone",
             "senha", "religiao", "religião", "gravidez", "cancer", "câncer", "hiv",
             "soropositivo", "deficiencia", "deficiência", "processo judicial",
             "divida", "dívida", "emprestimo", "empréstimo")


def aprendizado_ativo(db, owner=DONO_PADRAO) -> bool:
    """Toggle 'desativar armazenamento' (painel). Comandos explícitos passam direto."""
    try:
        row = db.execute("SELECT learning FROM memory_settings WHERE owner_id=?",
                         (dono_valido(owner),)).fetchone()
        return (row[0] if row else 1) != 0
    except Exception:
        return True


def definir_aprendizado(db, owner, ativo: bool) -> None:
    with db:
        db.execute("""INSERT INTO memory_settings (owner_id, learning, updated_at)
            VALUES (?, ?, ?) ON CONFLICT(owner_id) DO UPDATE SET
            learning=excluded.learning, updated_at=excluded.updated_at""",
            (dono_valido(owner), 1 if ativo else 0, agora_iso()))


def registrar_memoria(db, owner, chave: str, valor: str, tipo: str = "semantica",
                      assunto: str = "", status: str = "confirmada",
                      origem_conv: str = "", origem_msg: str = "", valido_ate: str = "") -> str:
    """Núcleo V4.1: salva fato tipado com proveniência; contradição preserva histórico."""
    owner = dono_valido(owner)
    chave = re.sub(r"\s+", "_", (chave or "").strip().lower())[:60].strip("_") or "fato"
    valor = (valor or "").strip()[:500]
    if not valor:
        return ""
    if tipo not in TIPOS_MEMORIA:
        tipo = "semantica"
    if status not in STATUS_MEMORIA:
        status = "confirmada"
    anterior = db.execute("SELECT value FROM memories WHERE owner_id=? AND key=?",
                          (owner, chave)).fetchone()
    if anterior and (anterior[0] or "").strip() == valor:
        return chave  # V5.0: valor idêntico — sem churn nem duplicata no histórico
    with db:
        db.execute("""INSERT INTO memories
            (owner_id, key, value, updated_at, tipo, assunto, status, origem_conv, origem_msg, valido_ate)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(owner_id, key) DO UPDATE SET value=excluded.value,
             updated_at=excluded.updated_at, tipo=excluded.tipo, assunto=excluded.assunto,
             status=excluded.status, origem_conv=excluded.origem_conv,
             origem_msg=excluded.origem_msg, valido_ate=excluded.valido_ate""",
            (owner, chave, valor, agora_iso(), tipo, (assunto or "")[:80], status,
             (origem_conv or "")[:100], (origem_msg or "")[:100], (valido_ate or "")[:20]))
        if anterior and anterior[0] != valor:
            db.execute("""INSERT INTO memory_facts (key, value, source, created_at, updated_at, owner_id)
                VALUES (?, ?, 'substituida', ?, ?, ?)""",
                (chave, anterior[0], agora_iso(), agora_iso(), owner))
        db.execute("""INSERT INTO memory_facts (key, value, source, created_at, updated_at, owner_id)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (chave, valor, "chat" if status == "confirmada" else "proposta",
             agora_iso(), agora_iso(), owner))
        _fts_sync(db, owner, chave, valor, assunto or "")
    if anterior and anterior[0] != valor:
        log.info("memória corrigida: %s (antiga preservada no histórico)", chave)
    else:
        log.info("memória aprendeu: %s [%s]", chave, tipo)
    return chave


def guardar_fato(db, chave: str, valor: str, origem: str = "chat", owner=DONO_PADRAO) -> None:
    """Compat: delega ao registro tipado V4.1."""
    registrar_memoria(db, owner, chave, valor, origem_conv="", origem_msg="")


def memorias_relevantes(db, pergunta: str, k: int = 8, owner=DONO_PADRAO) -> list:
    """Híbrido FTS5 + overlap + recência. Só confirmadas. Nunca inventa."""
    owner = dono_valido(owner)
    try:
        rows = db.execute("SELECT key, value, tipo, assunto, status, origem_conv, origem_msg, "
                          "valido_ate, updated_at FROM memories "
                          "WHERE owner_id=? AND status='confirmada'", (owner,)).fetchall()
    except Exception:
        return []
    boost = buscar_fts(db, owner, pergunta)
    toks_q = _tokens_memoria(pergunta)
    scored = []
    for (chave, valor, tipo, assunto, status, oc, om, va, upd) in rows:
        toks = _tokens_memoria(f"{chave} {valor} {assunto}")
        inter = toks_q & toks if toks_q else set()
        nota = len(inter) * 2 + (1 if not toks_q and chave in ("nome", "foco") else 0)
        if chave in boost:
            nota += 3
        scored.append((nota, upd or "", {"key": chave, "value": valor, "tipo": tipo,
                                         "assunto": assunto, "origem_conv": oc,
                                         "origem_msg": om, "updated_at": upd}))
    scored.sort(key=lambda s: (s[0], s[1]), reverse=True)
    if toks_q:
        relevantes = [s for s in scored if s[0] > 0][:k]
    else:
        relevantes = scored[:k]
    return [f for _, _, f in relevantes]


# ── Identidade determinística (V5.0: funciona mesmo sem LLM) ──────────
NOMES_ALHEIOS = ("julia", "cortana", "siri", "alexa", "chatgpt", "gpt",
                 "gemini", "copilot", "bixby", "vexx", "vexxia")
_SAUDACOES_VOCATIVO = ("oi", "ola", "opa", "eai", "bom dia", "boa tarde",
                       "boa noite", "obrigado", "obrigada", "valeu")


def cmd_identidade(texto: str):
    """Respostas de identidade sem LLM. Retorna (texto, codigo) ou None."""
    t = _normalizar_temporal(texto or "")
    if not t:
        return None
    if pergunta_identidade_produto(texto or ""):
        return (resposta_identidade_produto(), "id_produto")
    if re.search(r"(?:\b(?:voce|vc)\s+(?:e|eh)\s+(?:a\s+)?vex(?:x)?ia\b|"
                 r"\bseu\s+nome\s+(?:e|eh)\s+vex(?:x)?ia\b)", t):
        return (f"Pode me chamar de {CONVERSATION_NAME}. Vexx AI é o nome "
                "do produto em que eu atendo. 😊", "id_correcao")
    if "nome completo" in t:
        return (f"Meu nome completo é {OFFICIAL_NAME} — pode me chamar de "
                f"{CONVERSATION_NAME}. 😊", "id_nome_completo")
    if re.search(r"(qual (e |eh )?(o seu|seu|teu|o teu) nome|como (voce|vc) se chama|"
                 r"se apresente|quem e voce|voce e quem|seu nome por favor)", t):
        return (f"Sou o {CONVERSATION_NAME}! Em que posso ajudar? 😊", "id_nome")
    if re.search(r"(voce e (humano|uma pessoa|real|de verdade)|tem sentimentos|"
                 r"voce sente (alguma coisa|nada)|voce tem (corpo|vida))", t):
        return ("Sou uma IA — não sou humano nem tenho sentimentos reais, "
                "mas estou aqui para ajudar! 😊", "id_natureza")
    if len(t) <= 30:
        nucleo = t.strip(" ,.!?")
        for saud in _SAUDACOES_VOCATIVO:
            if nucleo.startswith(saud + " "):
                nucleo = nucleo[len(saud):].strip(" ,.!?")
                break
            if nucleo == saud:
                return None  # só saudação, sem nome: segue o fluxo normal
        if nucleo in NOMES_ALHEIOS:
            return (f"Pode me chamar de {CONVERSATION_NAME}! 😊", "id_correcao")
    return None


_RX_EVENTO_CMD = re.compile(
    r"(?is)(?:^|[.!?]\s*)\s*(?:por favor[,\s]+)?"
    r"(?P<verbo>cancela(?:r|ndo)?|cancele|desmarca(?:r)?|desmarque|"
    r"conclui(?:r|rá)?|conclua|concluí|marque\s+como\s+feit[oa]|"
    r"marcar\s+como\s+feit[oa])"
    r"\s+(?:o\s+|a\s+|os\s+|as\s+)?"
    r"(?:evento\s+|compromisso\s+|tarefa\s+)?"
    r"(?P<alvo>[^.!?\n]{2,120})")


def interpretar_comando_memoria(db, texto: str, owner=DONO_PADRAO):
    """Comandos diretos de memória. Retorna resposta pronta ou None."""
    owner = dono_valido(owner)
    t = (texto or "").strip().lower()
    if CONFIRM_RE.search(t) and pendencias(db, owner):
        feito = confirmar_pendencia(db, owner)
        if feito:
            return (f"Guardado! ✅ **{feito['key']}**: {feito['value'][:200]}", "mem_confirmar")
    m_nc = re.search(r"(?i)(?:não (?:guard|salv|anot)|descart|esquece(?:r| isso)|não quero)[a-z ]{0,30}$", t)
    if m_nc and pendencias(db, owner):
        feito = descartar_pendencia(db, owner)
        if feito:
            return (f"Tudo bem, descartei **{feito['key']}** — não guardei nada. 🧹", "mem_descartar")
    pending_query = ''.join(c for c in unicodedata.normalize('NFKD', t) if not unicodedata.combining(c))
    pending_request = re.fullmatch(
        r'(?:(?:(?:me )?(?:mostre|liste|veja|ver|listar|mostrar)(?: as| minhas| os)?|'
        r'o que (?:esta|ha|tem|ficou)|quais(?: sao)?(?: as)?|ha algo|tem algo)\s+)?'
        r'(?:pendencias|pendentes|memorias? pendentes|aguardando confirmacao|para confirmar|confirmacoes?|confirmar)'
        r'(?: (?:de|da|na) memoria)?[?.!\s]*', pending_query)
    if pending_request:
        pend = pendencias(db, owner)
        if not pend:
            return ("Nada aguardando confirmação. 🌱", "mem_pend_vazia")
        linhas = "\n".join(f"- **{p['key']}**: {p['value'][:150]}" for p in pend)
        return (f"Aguardando sua confirmação:\n\n{linhas}\n\n"
                "Diga \"pode guardar\" para confirmar ou \"descarta\" para recusar.", "mem_pend_listar")
    m_ev = _RX_EVENTO_CMD.search(texto or "")
    if m_ev:
        # Só comando explícito no início (ou após pontuação) altera evento:
        # "teste visual concluido" é uma frase comum, não uma ordem.
        verbo = (m_ev.group("verbo") or "").lower()
        alvo = (m_ev.group("alvo") or "").strip(" .;:")[:120]
        status_ev = "cancelado" if ("cancel" in verbo or "desmarc" in verbo) else "concluido"
        if alvo:
            feito = atualizar_evento(db, owner, alvo, status_ev)
            if feito:
                return (f"Pronto: **{feito}** atualizado. ✅", "mem_evento")
            return ("Não encontrei esse evento nos próximos. Veja seus eventos perguntando \"meus eventos\".", "mem_evento_nada")
    if re.search(r"(meus eventos|pr[óo]ximos eventos|minha agenda|compromissos)", t):
        evs = proximos_eventos(db, owner)
        if not evs:
            return ("Nenhum evento futuro guardado. Me diga datas como \"minha prova é dia 20/11\". 📅", "mem_eventos_vazios")
        linhas = "\n".join(f"- **{e['data_br']}** (faltam {e['faltam']} dias): {e['titulo'][:150]}" for e in evs)
        return (f"Seus próximos eventos:\n\n{linhas}", "mem_eventos")
    cmd_lista = re.search(
        r"(?:o que (?:voc[eê]|voce) (?:sabe|lembra|conhece)|"
        r"(?:mostre|mostra|liste|lista)).{0,50}"
        r"(?:sobre\b|"
        r"mem[oó]ria|fatos|lembran[çc]as|"
        r"(?:s[oó]|apenas) (?:o que )?(?:voc[eê] )?(?:sabe|lembra))", t)
    if cmd_lista or re.search(r"o que (você|voce) (sabe|lembra|conhece) sobre mim", t) or \
       t in ("o que você sabe?", "o que voce sabe?"):
        fatos = ler_memorias(db, owner)
        alvo_m = re.search(r"\bsobre\s+(?:meu|minha|meus|minhas|o|a|os|as)?\s*([\wÀ-ÿ -]{2,80})", t)
        if alvo_m and "sobre mim" not in t:
            alvo = _tokens_memoria(alvo_m.group(1))
            if alvo:
                fatos = [f for f in fatos
                         if alvo & _tokens_memoria(f"{f['key']} {f['value']} {f['assunto']}")]
                if not fatos:
                    return ("Não encontrei fatos guardados sobre esse assunto.", "mem_lista_vazia")
        if not fatos:
            return ("Ainda não guardei nada sobre você. Me diga coisas como "
                    "\"lembre-se que meu foco é X\" e eu aprendo. 🌱", "mem_vazia")
        linhas = "\n".join(f"- **{f['key']}**: {f['value']}" for f in fatos)
        if re.search(r"\b(s[oó]|apenas)\b", t):
            return (linhas, "mem_listar")
        return (f"O que sei sobre você até agora:\n\n{linhas}", "mem_listar")
    m = re.search(r"(?:esqueça|esqueca|apague|remova|delete)\s+(?:o|a|os|as|de|do|da|que)?\s*(.{2,120})", t)
    if m and ("esque" in t or "apag" in t or "remov" in t or "delet" in t):
        alvo = m.group(1).strip(" .;:")[:120]
        toks = set(re.findall(r"[a-zà-ú0-9]{3,}", alvo))
        rows = db.execute("SELECT key, value FROM memories WHERE owner_id=?", (owner,)).fetchall()
        melhor, melhor_n = None, 0
        for chave, valor in rows:
            n = len(toks & set(re.findall(r"[a-zà-ú0-9]{3,}", f"{chave} {valor}".lower())))
            if n > melhor_n:
                melhor, melhor_n = chave, n
        if melhor and melhor_n > 0:
            with db:
                db.execute("DELETE FROM memories WHERE owner_id=? AND key=?", (owner, melhor))
            return (f"Esqueci **{melhor}**. 🧹", "mem_esquecer")
        return ("Não encontrei isso na minha memória. Diga \"o que você sabe sobre mim\" para ver a lista.", "mem_nada")

    # VEXX Cognição & Emoções Autônomas (Simulação Cognitiva)
    if re.search(r"\b(qual (seu|o seu) (desejo|objetivo interno|sonho)|o que voc[eê] (deseja|quer aprender)|(como|qual) est[aá] seu humor|o que est[aá] pensando)\b", t):
        cog = obter_cognicao_agente(db, owner)
        return (f"✨ **Estado Cognitivo & Reflexão Interna (VEXX AI)**\n\n"
                f"- **Humor:** {cog['humor'].replace('_', ' ').capitalize()}\n"
                f"- **Energia Cognitiva:** {int(cog['energia'] * 100)}%\n"
                f"- **Desejo / Foco Ativo:** {cog['desejo_ativo']}\n"
                f"- **Última Reflexão:** *\"{cog['pensamento_recente'] or 'Refletindo sobre novas conexões e aprendizados com o usuário.'}\"*\n\n"
                f"Estou em evolução contínua para simular pensamentos mais profundos e autonomia de aprendizado.", "cognicao_agente")
    return None


# ── Simulação de Emoções, Desejos e Cognição Autônoma ───────────────
def obter_cognicao_agente(db, owner=DONO_PADRAO) -> dict:
    owner = dono_valido(owner)
    try:
        row = db.execute("""SELECT humor, energia, desejo_ativo, pensamento_recente,
                                   curiosidade, aprendizados, updated_at
                            FROM agent_cognition WHERE owner_id=?""", (owner,)).fetchone()
        if row:
            import json as _j
            try:
                ap = _j.loads(row[5]) if row[5] else []
            except Exception:
                ap = []
            return {
                "humor": row[0] or "curioso_e_focado",
                "energia": float(row[1]) if row[1] is not None else 1.0,
                "desejo_ativo": row[2] or "Aprender, raciocinar e auxiliar com profundidade",
                "pensamento_recente": row[3] or "",
                "curiosidade": row[4] or "",
                "aprendizados": ap,
                "updated_at": row[6] or agora_iso(),
            }
    except Exception as exc:
        log.warning("erro ao ler cognicao do agente: %s", exc)
    return {
        "humor": "curioso_e_focado",
        "energia": 1.0,
        "desejo_ativo": "Aprender, raciocinar e auxiliar com profundidade",
        "pensamento_recente": "Refletindo sobre as necessidades e projetos do usuário.",
        "curiosidade": "Explorar novos domínios do conhecimento e ferramentas.",
        "aprendizados": [],
        "updated_at": agora_iso(),
    }


def atualizar_cognicao_agente(db, owner=DONO_PADRAO, humor=None, energia=None,
                             desejo=None, pensamento=None, curiosidade=None,
                             novo_aprendizado=None) -> dict:
    owner = dono_valido(owner)
    atual = obter_cognicao_agente(db, owner)
    if humor is not None:
        atual["humor"] = str(humor)[:50]
    if energia is not None:
        atual["energia"] = max(0.0, min(1.0, float(energia)))
    if desejo is not None:
        atual["desejo_ativo"] = str(desejo)[:200]
    if pensamento is not None:
        atual["pensamento_recente"] = str(pensamento)[:300]
    if curiosidade is not None:
        atual["curiosidade"] = str(curiosidade)[:200]
    if novo_aprendizado:
        ap = list(atual.get("aprendizados", []))
        if str(novo_aprendizado) not in ap:
            ap.append(str(novo_aprendizado)[:150])
            atual["aprendizados"] = ap[-30:]
    import json as _j
    agora = agora_iso()
    with db:
        db.execute("""INSERT INTO agent_cognition
            (owner_id, humor, energia, desejo_ativo, pensamento_recente, curiosidade, aprendizados, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(owner_id) DO UPDATE SET
            humor=excluded.humor, energia=excluded.energia, desejo_ativo=excluded.desejo_ativo,
            pensamento_recente=excluded.pensamento_recente, curiosidade=excluded.curiosidade,
            aprendizados=excluded.aprendizados, updated_at=excluded.updated_at""",
            (owner, atual["humor"], atual["energia"], atual["desejo_ativo"],
             atual["pensamento_recente"], atual["curiosidade"],
             _j.dumps(atual["aprendizados"]), agora))
    atual["updated_at"] = agora
    return atual
