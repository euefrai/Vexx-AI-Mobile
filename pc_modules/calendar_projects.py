"""Módulo do PC Agent: Agenda/eventos em português, extração de candidatos, projetos e aprendizado contínuo."""
import docs_agent
import re
import unicodedata
import workspace_store

from pathlib import Path

from pc_modules.db_core import (
    _fts_sync, agora_iso, DONO_PADRAO, dono_valido, gerar_texto, log, open_db,
)
from pc_modules.memory_store import (
    _tokens_memoria, aprendizado_ativo, ler_memorias, registrar_memoria, SENSIVEIS,
)

MESES_PT = {"janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4,
            "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
            "outubro": 10, "novembro": 11, "dezembro": 12}
DIAS_PT = {"segunda": 0, "terça": 1, "terca": 1, "quarta": 2, "quinta": 3,
           "sexta": 4, "sábado": 5, "sabado": 5, "domingo": 6}

CONFIRM_RE = re.compile(r"(?i)(pode guardar|pode salvar|pode anotar|confirma|confirmo|isso mesmo|est[áa] certo|correto|t[áa] certo|guarda (isso|a[ií])|salva (isso|a[ií]))")


def parse_data(texto: str, hoje=None):
    """Datas em PT-BR. Retorna (iso|None, raw, precisa_confirmacao).

    Ano explícito ou data relativa = sem ambiguidade. Mês/dia sem ano =
    sempre pede confirmação (nunca presume o ano).
    """
    from datetime import date as _date, timedelta as _td
    hoje = hoje or _date.today()
    t = (texto or "").lower()
    m = re.search(r"\b(\d{1,2})[\/\.](\d{1,2})(?:[\/\.](\d{2,4}))?\b", t)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        ano = m.group(3)
        if ano:
            ano = int(ano) + (2000 if len(ano) == 2 and int(ano) < 50 else 0)
            try:
                return _date(ano, mo, d).isoformat(), m.group(0), False
            except ValueError:
                return None, m.group(0), True
        try:
            cand = _date(hoje.year, mo, d)
        except ValueError:
            return None, m.group(0), True
        iso = cand.isoformat() if cand >= hoje else _date(hoje.year + 1, mo, d).isoformat()
        return iso, m.group(0), True
    m = re.search(r"(?:dia\s+)?(\d{1,2})\s+de\s+([a-zç]+)(?:\s+de\s+(\d{4}))?", t)
    if m and m.group(2) in MESES_PT:
        d, mo, ano = int(m.group(1)), MESES_PT[m.group(2)], m.group(3)
        if ano:
            try:
                return _date(int(ano), mo, d).isoformat(), m.group(0), False
            except ValueError:
                return None, m.group(0), True
        try:
            cand = _date(hoje.year, mo, d)
        except ValueError:
            return None, m.group(0), True
        iso = cand.isoformat() if cand >= hoje else _date(hoje.year + 1, mo, d).isoformat()
        return iso, m.group(0), True
    if "depois de amanh" in t:
        return (hoje + _td(days=2)).isoformat(), "depois de amanhã", False
    if "amanh" in t:
        return (hoje + _td(days=1)).isoformat(), "amanhã", False
    if "semana que vem" in t or "próxima semana" in t or "proxima semana" in t:
        return (hoje + _td(days=7)).isoformat(), "semana que vem", False
    if "mês que vem" in t or "mes que vem" in t:
        mes = hoje.month % 12 + 1
        ano = hoje.year + (1 if mes == 1 else 0)
        try:
            return _date(ano, mes, min(hoje.day, 28)).isoformat(), "mês que vem", False
        except ValueError:
            return None, "mês que vem", True
    m = re.search(r"(segunda|terça|terca|quarta|quinta|sexta|sábado|sabado|domingo)(?:-feira)?", t)
    if m:
        alvo = DIAS_PT[m.group(1)]
        delta = (alvo - hoje.weekday()) % 7 or 7
        return (hoje + _td(days=delta)).isoformat(), m.group(0), False
    return None, "", True


def data_br(iso: str) -> str:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", iso or "")
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else (iso or "")


def registrar_evento(db, owner, titulo: str, data_iso: str = "", data_raw: str = "",
                     assunto: str = "", conv: str = "", msg: str = "", status: str = "ativo") -> int:
    owner = dono_valido(owner)
    titulo = (titulo or "").strip()[:200]
    if not titulo:
        return 0
    with db:
        ex = db.execute("SELECT id FROM memory_events WHERE owner_id=? AND titulo=? AND data_iso=?",
                        (owner, titulo, data_iso or "")).fetchone()
        if ex:
            db.execute("UPDATE memory_events SET status=?, assunto=?, updated_at=? WHERE id=?",
                       (status, (assunto or "")[:80], agora_iso(), ex[0]))
            return ex[0]
        cur = db.execute("""INSERT INTO memory_events
            (owner_id, titulo, data_iso, data_raw, assunto, status, origem_conv, origem_msg,
             created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (owner, titulo, data_iso or "", (data_raw or "")[:120], (assunto or "")[:80],
             status, (conv or "")[:100], (msg or "")[:100], agora_iso(), agora_iso()))
        return cur.lastrowid or 0


def proximos_eventos(db, owner, limite: int = 6, hoje=None) -> list:
    from datetime import date as _date
    owner = dono_valido(owner)
    hoje = hoje or _date.today()
    try:
        rows = db.execute("""SELECT id, titulo, data_iso, assunto FROM memory_events
                             WHERE owner_id=? AND status='ativo' AND data_iso>=?
                             ORDER BY data_iso LIMIT ?""",
                          (owner, (hoje.isoformat()), limite)).fetchall()
    except Exception:
        return []
    out = []
    for i, titulo, iso, assunto in rows:
        try:
            d = _date.fromisoformat(iso)
            out.append({"id": i, "titulo": titulo, "data_iso": iso, "data_br": data_br(iso),
                        "faltam": (d - hoje).days, "assunto": assunto})
        except ValueError:
            continue
    return out


def atualizar_evento(db, owner, ref: str, status: str = "cancelado") -> str:
    """Cancela/conclui por id ou trecho do título. Retorna título ou ''."""
    owner = dono_valido(owner)
    try:
        rows = db.execute("SELECT id, titulo FROM memory_events WHERE owner_id=? AND status='ativo'",
                          (owner,)).fetchall()
    except Exception:
        return ""
    alvo = None
    if str(ref).isdigit():
        alvo = next((r for r in rows if str(r[0]) == str(ref)), None)
    if alvo is None:
        toks = set(re.findall(r"[a-zà-ú0-9]{3,}", str(ref).lower()))
        melhor, n = None, 0
        for i, titulo in rows:
            inter = len(toks & set(re.findall(r"[a-zà-ú0-9]{3,}", titulo.lower())))
            if inter > n:
                melhor, n = (i, titulo), inter
        alvo = melhor
    if alvo is None:
        return ""
    with db:
        db.execute("UPDATE memory_events SET status=?, updated_at=? WHERE id=? AND owner_id=?",
                   (status, agora_iso(), alvo[0], owner))
    return alvo[1]


def eh_sensivel(texto: str) -> bool:
    t = (texto or "").lower()
    if re.search(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b", t):
        return True  # padrão CPF
    return any(s in t for s in SENSIVEIS)


def extrair_candidatos(texto: str) -> list:
    """Candidatos tipados (fato vs hipótese separados pelo chamador)."""
    t = (texto or "").strip()
    out = []
    for rx, chave, tipo, assunto in [
        (r"(?i)(?:meu nome é|me chamo|sou o|sou a)\s+(.{2,80})", "nome", "semantica", "identidade"),
        (r"(?i)(?:meu foco é|minha meta é|estou trabalhando (?:em|com))\s+(.{3,200})", "foco", "trabalho", "objetivos"),
        (r"(?i)(?:prefiro|gosto de|não gosto de)\s+(.{3,200})", "preferencia", "semantica", "gostos"),
        (r"(?i)(?:lembre-?se (?:que |de que |disso:?\s?))(.{3,300})", "fato", "semantica", "geral"),
        (r"(?i)(?:aniversário|aniversario) (?:é |eh |dia )?(.{2,60})", "aniversario", "temporal", "datas"),
        (r"(?i)(?:minha prova|prova) (?:de \w+ )?(?:é|será|vai ser|dia) (.{2,80})", "prova", "temporal", "estudos"),
        (r"(?i)(?:reunião|reuniao|consulta|compromisso|viagem|entrega|prazo)[^.]{0,10}(.{2,80})", "evento", "temporal", "agenda"),
        (r"\b([A-ZÀ-Ú][a-zà-ú]{2,30}) é (?:meu|minha) ([a-zà-ú ]{2,40}?)(?:[.,;]| e |$)", "pessoa", "semantica", "pessoas"),
    ]:
        m = re.search(rx, t)
        if not m:
            continue
        sentence_start = max(t.rfind(mark, 0, m.start()) for mark in ('.', '?', '!', '\n')) + 1
        prefix = t[sentence_start:m.start()]
        if re.search(r'(?i)\b(qual|quais|quando|quantos|quantas|por que|como)\b', prefix):
            continue  # A question about a date/name is not a personal assertion.
        # V5.0: exemplo/hipótese não é fato — "suponha que meu nome seja X"
        # nunca vira memória.
        antes = t[max(0, m.start() - 30):m.start()].lower()
        if re.search(r"(exemplo|suponha|supor|imagine|hipot|e se\b|finge|faz de conta|digamos)", antes):
            continue
        if chave == "pessoa":
            nome = m.group(1).strip()
            rel = m.group(2).strip()
            out.append({"chave": "pessoa_" + nome.lower(), "valor": f"{nome} é meu/minha {rel}",
                        "tipo": tipo, "assunto": assunto,
                        "sensivel": eh_sensivel(t)})
            continue
        valor = re.sub(r"\s+", " ", m.group(1)).strip(" .;:")[:300]
        if valor:
            out.append({"chave": chave, "valor": valor, "tipo": tipo, "assunto": assunto,
                        "sensivel": eh_sensivel(valor) or eh_sensivel(t)})
    if not out and eh_sensivel(t) and re.search(
            r"(?i)\b(eu|meu|minha|tomo|tenho|sou|fa[çc]o|estou|uso|tive|preciso)\b", t):
        slug = "_".join(re.findall(r"[a-zà-ú]{4,}", t.lower())[:4])[:40] or "nota"
        out.append({"chave": "sensivel_" + slug, "valor": t[:300], "tipo": "semantica",
                    "assunto": "sensivel", "sensivel": True})
    return out


# ── Project Memory + orçamento de contexto (V5.0) ─────────────────────
ORCAMENTO_MEMORIA_CHARS = 1500
ORCAMENTO_PROJETO_CHARS = 800


def _ultimas_de_conv(db, conv: str, owner: str, n: int = 2) -> list:
    try:
        rows = db.execute(
            """SELECT role, text FROM messages WHERE origin='mobile' AND owner_id=?
               AND conversation_id=? ORDER BY created_at DESC, id DESC LIMIT ?""",
            (dono_valido(owner), conv, max(1, min(int(n), 4)))).fetchall()
    except Exception:
        return []
    return [(r, (t or "")[:300]) for r, t in reversed(rows) if (t or "").strip()]


def _projetos_relevantes(db, texto: str, owner: str) -> list:
    """[(score, updated_at, projeto)]. Só projetos ativos; por sobreposição de tokens."""
    try:
        recs = workspace_store.list_records(db, dono_valido(owner))
    except Exception:
        return []
    projetos = [r for r in recs if isinstance(r, dict) and r.get("kind") == "project"
                and not r.get("archived") and not r.get("deleted")]
    toks = _tokens_memoria(texto)
    if not toks or not projetos:
        return []

    def _radicais(s: str) -> set:
        sem = "".join(c for c in unicodedata.normalize(
            "NFKD", (s or "").lower()) if not unicodedata.combining(c))
        return {w[:5] for w in re.findall(r"[a-z0-9]{5,}", sem)}
    rad_q = _radicais(texto)
    scored = []
    for p in projetos:
        titulo = p.get("title", "")
        inter = toks & _tokens_memoria(titulo)
        rad = (rad_q & _radicais(titulo)) if not inter else set()
        nota = len(inter) * 2 + len(rad)
        if nota:
            scored.append((nota, str(p.get("updated_at", "")), p))
    scored.sort(key=lambda s: (s[0], s[1]), reverse=True)
    return scored


def _trechos_projeto(db, owner: str, projeto: dict, teto_chats: int = 3) -> list:
    try:
        recs = workspace_store.list_records(db, dono_valido(owner))
    except Exception:
        return []
    pid = projeto.get("id", "")
    chats = [r for r in recs if isinstance(r, dict) and r.get("kind") == "chat"
             and r.get("project_id") == pid and not r.get("deleted")]
    trechos = []
    for c in chats[:teto_chats]:
        for role, txt in _ultimas_de_conv(db, c.get("id", ""), owner):
            trechos.append(f"[{c.get('id', '')[-6:]}|{role}]: {txt[:200]}")
            if len(trechos) >= 4:
                return trechos
    return trechos


def bloco_projetos(db, texto: str, conv: str, owner: str) -> str:
    """Project Memory p/ o prompt: projetos relevantes + trechos reais ligados."""
    scored = _projetos_relevantes(db, texto, owner)
    if not scored:
        return ""
    linhas = []
    for _, _, p in scored[:2]:
        trechos = _trechos_projeto(db, owner, p)
        linhas.append(f"- **{(p.get('title') or '')[:60]}**" +
                      (": " + " ".join(trechos[:3]) if trechos else " (sem mensagens ligadas)"))
    return ("PROJETOS RELACIONADOS (trechos reais de conversas ligadas; "
            "não invente peças, valores ou estado):\n" + "\n".join(linhas)
            )[:ORCAMENTO_PROJETO_CHARS]


def pendencias(db, owner) -> list:
    return ler_memorias(db, owner, status="pendente")

def confirmar_pendencia(db, owner) -> dict:
    """Confirma a pendência mais antiga. Retorna {} se não houver."""
    owner = dono_valido(owner)
    rows = db.execute("SELECT key, value, tipo, assunto, origem_conv, origem_msg FROM memories "
                      "WHERE owner_id=? AND status='pendente' ORDER BY updated_at LIMIT 1",
                      (owner,)).fetchone()
    if not rows:
        return {}
    chave, valor, tipo, assunto, oc, om = rows
    with db:
        db.execute("UPDATE memories SET status='confirmada', updated_at=? "
                   "WHERE owner_id=? AND key=?", (agora_iso(), owner, chave))
        _fts_sync(db, owner, chave, valor, assunto)
    if tipo == "temporal":
        iso, _, _ = parse_data(valor)
        if iso:
            titulo = f"{chave} · {assunto}" if assunto else chave
            registrar_evento(db, owner, titulo[:200], iso, valor[:120], assunto, oc, om)
    return {"key": chave, "value": valor, "tipo": tipo}


def descartar_pendencia(db, owner) -> dict:
    owner = dono_valido(owner)
    row = db.execute("SELECT key FROM memories WHERE owner_id=? AND status='pendente' "
                     "ORDER BY updated_at LIMIT 1", (owner,)).fetchone()
    if not row:
        return {}
    with db:
        db.execute("DELETE FROM memories WHERE owner_id=? AND key=?", (owner, row[0]))
        try:
            db.execute("DELETE FROM memories_fts WHERE owner_id=? AND key=?", (owner, row[0]))
        except Exception:
            pass
    return {"key": row[0]}


def analisar_memoria(db, texto: str, owner, conv: str = "", msg_id: str = "") -> tuple:
    """V4.1: extrai candidatos; sensível/temporal-ambíguo vira PROPOSTA + pergunta.

    Retorna (salvos[], propostas[], pergunta|None). Explícito ('lembre-se',
    'guarde') passa mesmo com aprendizado pausado.
    """
    owner = dono_valido(owner)
    explicito = bool(re.search(r"(?i)(lembre-?se|guarde|guardar|anote|anotar|salve|salvar|registre)", texto or ""))
    if not aprendizado_ativo(db, owner) and not explicito:
        return [], [], None
    salvos, propostas, pergunta = [], [], None
    for c in extrair_candidatos(texto):
        if c["tipo"] == "temporal":
            iso, raw, confirma = parse_data(c["valor"])
            rotulo = (data_br(iso) + " — " + c["valor"]) if iso else c["valor"]
            if iso and not confirma:
                chave = registrar_memoria(db, owner, c["chave"], rotulo, "temporal", c["assunto"],
                                          "confirmada", conv, msg_id)
                titulo = f"{c['chave']} · {c['assunto']}" if c["assunto"] else c["chave"]
                registrar_evento(db, owner, titulo[:200], iso, c["valor"][:120],
                                 c["assunto"], conv, msg_id)
                if chave:
                    salvos.append(chave)
                continue
            chave = registrar_memoria(db, owner, c["chave"], rotulo, "temporal", c["assunto"],
                                      "pendente", conv, msg_id)
            propostas.append(chave)
            if confirma and iso and pergunta is None:
                pergunta = (f"Posso guardar essa data para te ajudar? É {data_br(iso)}? "
                            "Responda \"pode guardar\" para confirmar.")
            elif pergunta is None:
                pergunta = (f"Posso guardar \"{c['valor'][:100]}\"? "
                            "Responda \"pode guardar\" para confirmar.")
        elif c["sensivel"]:
            chave = registrar_memoria(db, owner, c["chave"], c["valor"], c["tipo"], c["assunto"],
                                      "pendente", conv, msg_id)
            propostas.append(chave)
            if pergunta is None:
                pergunta = ("Isso parece sensível, então não guardei ainda. "
                            "Posso guardar? Responda \"pode guardar\" para confirmar.")
        else:
            chave = registrar_memoria(db, owner, c["chave"], c["valor"], c["tipo"], c["assunto"],
                                      "confirmada", conv, msg_id)
            if chave:
                salvos.append(chave)
    return salvos, propostas, pergunta


def aprender_com_conversa(db_path: Path, cfg: dict, texto_usuario: str, texto_resposta: str,
                          owner=DONO_PADRAO) -> None:
    """Thread em 2º plano: pede ao LLM fatos novos (JSON) e guarda. Nunca bloqueia o chat."""
    try:
        if len(texto_usuario or "") < 20:
            return
        _db_chk = open_db(db_path)
        try:
            if not aprendizado_ativo(_db_chk, owner):
                return
        finally:
            _db_chk.close()
        import json as _json
        prompt = ("Extraia FATOS duradouros sobre o usuário desta conversa "
                  "(nome, profissão, projetos, preferências, metas, contexto de vida). "
                  "NÃO extraia hipóteses, exemplos citados ou palpites — só o que o usuário "
                  "afirmou sobre si. Responda SÓ com JSON: "
                  "[{\"key\": \"curta_em_snake\", \"value\": \"...\", \"tipo\": \"semantica|temporal|episodica|trabalho\", "
                  "\"assunto\": \"...\", \"sensivel\": false, \"confianca\": 0.0-1.0}] ou [].\n\n"
                  f"USUÁRIO: {(texto_usuario or '')[:1500]}\nASSISTENTE: {(texto_resposta or '')[:1500]}")
        res = gerar_texto(cfg,
            [{"role": "system", "content": "Você extrai fatos. Responda só JSON válido."},
             {"role": "user", "content": prompt}], max_tokens=300)
        try:
            fatos = _json.loads(res["texto"].strip().strip("`").replace("json", "", 1).strip())
        except Exception:
            m = re.search(r"\[.*\]", res["texto"], re.S)
            fatos = _json.loads(m.group(0)) if m else []
        db = open_db(db_path)
        try:
            for f in fatos if isinstance(fatos, list) else []:
                if not (isinstance(f, dict) and f.get("value")):
                    continue
                chave = str(f.get("key", "fato"))[:60]
                valor = str(f.get("value"))[:500]
                tipo = str(f.get("tipo", "semantica"))[:20]
                assunto = str(f.get("assunto", ""))[:80]
                try:
                    conf = float(f.get("confianca", 0.8))
                except (TypeError, ValueError):
                    conf = 0.8
                if f.get("sensivel") or eh_sensivel(valor) or conf < 0.6:
                    registrar_memoria(db, owner, chave, valor, tipo, assunto, "pendente")
                else:
                    registrar_memoria(db, owner, chave, valor, tipo, assunto, "confirmada")
            n = db.execute("SELECT COUNT(*) FROM memory_facts WHERE owner_id=?",
                           (dono_valido(owner),)).fetchone()[0]
            if n > 60:
                _consolidar_memorias(db, cfg, owner)
        finally:
            db.close()
    except Exception as exc:
        log.warning("aprendizado em 2º plano falhou: %s", exc)


def _consolidar_memorias(db, cfg: dict, owner=DONO_PADRAO) -> None:
    """Junta fatos antigos/duplicados num conjunto enxuto (evolução da memória)."""
    owner = dono_valido(owner)
    try:
        rows = db.execute("SELECT key, value FROM memory_facts WHERE owner_id=? "
                          "ORDER BY created_at DESC LIMIT 60", (owner,)).fetchall()
        bloco = "\n".join(f"- {k}: {v[:200]}" for k, v in rows)
        res = gerar_texto(cfg,
            [{"role": "system", "content": "Você consolida memórias. Responda só JSON válido."},
             {"role": "user", "content": "Junte estes fatos, removendo duplicados e o que for passageiro. "
              "Responda SÓ JSON: [{\"key\": \"...\", \"value\": \"...\"}] (máx 25 itens).\n\n" + bloco}],
            max_tokens=1200)
        import json as _json
        try:
            novos = _json.loads(res["texto"].strip().strip("`").replace("json", "", 1).strip())
        except Exception:
            return
        if not isinstance(novos, list) or not novos:
            return
        with db:
            db.execute("DELETE FROM memories WHERE owner_id=?", (owner,))
            db.execute("DELETE FROM memory_facts WHERE owner_id=?", (owner,))
            for f in novos[:25]:
                if isinstance(f, dict) and f.get("value"):
                    chave = re.sub(r"\s+", "_", str(f.get("key", "fato")).strip().lower())[:60] or "fato"
                    db.execute("INSERT INTO memories (owner_id, key, value, updated_at) VALUES (?, ?, ?, ?)",
                               (owner, chave, str(f["value"])[:500], agora_iso()))
        log.info("memória consolidada: %d fatos", len(novos))
    except Exception as exc:
        log.warning("consolidação falhou: %s", exc)


def doc_mencionado(db, texto: str, conversation_id: str, owner=DONO_PADRAO) -> str:
    """Acha documento citado pelo nome ou o mais recente da conversa."""
    t = (texto or "").lower()
    if re.search(r'\b(n[aã]o (leia|abra|consulte)|sem (ler|abrir|consultar))\b',t):
        return ''
    # Marcador do composer ("📎 Documento anexado: \"nome\"") é pedido explícito:
    # o usuário acabou de enviar o arquivo, mesmo sem palavras de comando.
    anexo = re.search(r'documento anexado\s*:\s*["“]?([^"\n”]+)', t)
    try:
        docs = docs_agent.listar_documentos(db, 50, owner, conversation_id=conversation_id)
    except Exception:
        return ""
    if anexo:
        alvo = anexo.group(1).strip()
        for d in docs:
            nome = (d.get("name") or "").lower().strip()
            base = re.sub(r"\.[a-z0-9]+$", "", nome)
            if alvo and (alvo == nome or alvo == base or
                         (len(base) >= 4 and (base in alvo or alvo in nome))):
                return d["doc_id"]
        return docs[0]["doc_id"] if docs else ""
    # Nome de arquivo citado por extenso em follow-ups ("e esse index.html?").
    # Só o nome completo (com extensão) evita falso positivo com palavras como
    # "todo" (documento TODO.md) em frases comuns.
    for d in docs:
        nome = (d.get("name") or "").lower().strip()
        if "." in nome and re.search(r"(?<!\w)" + re.escape(nome) + r"(?!\w)", t):
            return d["doc_id"]
    pedido=bool(re.search(
        r'\b(resum\w*|leia|abra|analis\w*|compare|consulte|mostre|explique|qual|'
        r'quais|quanto\w*|conte[uú]do|cri\w*|ger\w*|salv\w*|escrev\w*|'
        r'sobrescrev\w*|sobrepon\w*|sobrepost\w*|sobrepor|substitu\w*|'
        r'atualiz\w*|modific\w*|corrij\w*|refa[çc]a|melhor\w*|edit\w*|'
        r'ajust\w*|convert\w*|transform\w*|vers[ãa]o)\b',t))
    if not pedido:
        return ''
    doc_hint=bool(re.search(
        r'\b(documento|arquivo|pdf|contrato|relat[óo]rio|planilha|resum\w*|'
        r'leia|abra|consulte|vers[ãa]o|anex\w*|enviei|enviad\w*|sobrepon\w*|'
        r'sobrepost\w*|sobrescrev\w*|atualiz\w*|modific\w*|corrij\w*|'
        r'refa[çc]a|melhor\w*|edit\w*|ajust\w*|convert\w*|transform\w*|'
        r'conte[uú]do)\b',t))
    for d in docs:
        nome = (d["name"] or "").lower()
        base = re.sub(r"\.[a-z0-9]+$", "", nome)
        if len(base) >= 4 and (nome in t or doc_hint) and re.search(r'(?<!\w)'+re.escape(base)+r'(?!\w)',t):
            return d["doc_id"]
    if re.search(r"\b(documento|arquivo|pdf|contrato|relat[óo]rio|planilha|"
                 r"vers[ãa]o|anex\w*|enviei|enviad\w*|sobrepon\w*|sobrepost\w*|"
                 r"conte[uú]do)\b", t):
        mesmos = docs
        if mesmos:
            return mesmos[0]["doc_id"]
    return ""


def listar_conversas(db, limite: int = 100, owner=DONO_PADRAO) -> list:
    try:
        rows = db.execute("""SELECT conversation_id, COUNT(*), MAX(created_at),
                             substr(MAX(created_at || ' ' || text), 22, 80)
                             FROM messages WHERE origin='mobile' AND owner_id=?
                             GROUP BY conversation_id
                             ORDER BY MAX(created_at) DESC LIMIT ?""",
                          (dono_valido(owner), min(max(int(limite), 1), 200))).fetchall()
    except Exception:
        return []
    return [{"conversation_id": c, "total": n, "ultima": u, "previa": (p or "")[:80]}
            for c, n, u, p in rows]
