"""julia_auth — contas, convites, sessões, papéis, limites e auditoria.

Serviço reutilizável (stdlib pura: sqlite3/hashlib/secrets/hmac) para o
agente do PC e para o painel do Fajulto Studio. NUNCA importar fastapi aqui.

Modelo:
- users: uid PK ('owner' p/ proprietário legado, 'u-<hex>' demais),
  username UNIQUE (minúsculo), display, hash scrypt, role, status, limites.
- O proprietário legado continua podendo entrar pela senha do .env (Argon2,
  verificada no relay); ao ser vinculado, ganha linha admin sem senha padrão.
- Sessões: sid + uid + expiração + revogação (fonte definitiva no SQLite).
- Convites: só hash; consumo atômico de uso único; expiração e revogação.
- Auditoria: eventos administrativos, SEM conteúdo privado/senhas/tokens.
"""
import hashlib
import hmac
import re
import secrets
import time
from datetime import datetime, timezone

DONO_UID = "local"
ROLES = ("admin", "user")
STATUS = ("pendente", "ativo", "bloqueado")
MODOS = ("fechado", "convite", "aberto")

USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,29}$")
SENHA_MIN = 8
SENHA_MAX = 128


class AuthErro(ValueError):
    def __init__(self, mensagem, codigo="erro"):
        super().__init__(mensagem)
        self.codigo = codigo


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Esquema ───────────────────────────────────────────────────────────
def criar_tabelas(db) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS users (
        uid TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, display TEXT NOT NULL,
        hash TEXT NOT NULL DEFAULT '', role TEXT NOT NULL DEFAULT 'user',
        status TEXT NOT NULL DEFAULT 'ativo', aprovado INT NOT NULL DEFAULT 1,
        max_ai_hora INT NOT NULL DEFAULT 120, max_ia_simult INT NOT NULL DEFAULT 3,
        created_at TEXT NOT NULL, last_seen TEXT NOT NULL DEFAULT ''
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS invites (
        id INTEGER PRIMARY KEY AUTOINCREMENT, code_hash TEXT NOT NULL UNIQUE,
        max_usos INT NOT NULL DEFAULT 1, usos INT NOT NULL DEFAULT 0,
        expira_em TEXT NOT NULL DEFAULT '', criado_por TEXT NOT NULL DEFAULT '',
        revogado INT NOT NULL DEFAULT 0, nota TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS reg_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL,
        display TEXT NOT NULL, hash TEXT NOT NULL, invite_usado TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'pendente', created_at TEXT NOT NULL
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS user_sessions (
        sid TEXT PRIMARY KEY, uid TEXT NOT NULL, created_at TEXT NOT NULL,
        expira_em TEXT NOT NULL, revogada INT NOT NULL DEFAULT 0
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_sess_uid ON user_sessions(uid, revogada)")
    db.execute("""CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, ator TEXT NOT NULL,
        acao TEXT NOT NULL, alvo TEXT NOT NULL DEFAULT '', detalhe TEXT NOT NULL DEFAULT ''
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS app_config (
        k TEXT PRIMARY KEY, v TEXT NOT NULL
    )""")
    for _col, _ddl in (("remote_ok", "INT NOT NULL DEFAULT 0"),
                       ("bloqueado_ate", "TEXT NOT NULL DEFAULT ''")):
        try:
            cols = [c[1] for c in db.execute("PRAGMA table_info(users)").fetchall()]
            if _col not in cols:
                db.execute(f"ALTER TABLE users ADD COLUMN {_col} {_ddl}")
        except Exception:
            pass
    db.commit()


def migrar_legado(db) -> None:
    """Usernames avulsos antigos (ex. relay que enviava username) viram 'local'.

    'local' é o dono legado estável; contas novas usam 'u-<hex>'. Idempotente.
    """
    criar_tabelas(db)
    for tabela in ("messages", "ai_requests", "memories", "memory_facts",
                   "documents", "doc_chunks", "ui_state"):
        try:
            cols = [c[1] for c in db.execute(f"PRAGMA table_info({tabela})").fetchall()]
            if "owner_id" not in cols:
                continue
            db.execute(f"UPDATE {tabela} SET owner_id=? WHERE owner_id NOT LIKE 'u-%' "
                       f"AND owner_id != ?", (DONO_UID, DONO_UID))
        except Exception:
            continue
    db.commit()


def config_get(db, chave: str, padrao: str = "") -> str:
    try:
        row = db.execute("SELECT v FROM app_config WHERE k=?", (chave,)).fetchone()
        return row[0] if row else padrao
    except Exception:
        return padrao


def config_set(db, chave: str, valor: str) -> None:
    with db:
        db.execute("INSERT INTO app_config (k, v) VALUES (?, ?) "
                   "ON CONFLICT(k) DO UPDATE SET v=excluded.v", (chave, valor))


def modo_cadastro(db) -> str:
    modo = config_get(db, "modo_cadastro", "convite")
    return modo if modo in MODOS else "convite"


# ── Senhas (scrypt, stdlib) ───────────────────────────────────────────
def hash_senha(senha: str) -> str:
    sal = secrets.token_bytes(16)
    dk = hashlib.scrypt(senha.encode("utf-8"), salt=sal, n=16384, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${sal.hex()}${dk.hex()}"


def confere_senha(senha: str, guardado: str) -> bool:
    try:
        marca, n, r, p, salh, dkhex = (guardado or "").split("$")
        assert marca == "scrypt" and (int(n), int(r), int(p)) == (16384, 8, 1)
        dk = hashlib.scrypt((senha or "").encode("utf-8"), salt=bytes.fromhex(salh),
                            n=16384, r=8, p=1, dklen=32)
        return hmac.compare_digest(dk.hex(), dkhex)
    except Exception:
        return False


def valida_username(username: str) -> str:
    u = (username or "").strip().lower()
    if not USERNAME_RE.match(u):
        raise AuthErro("Usuário: 3–30 letras/números/./_/-.", "username_invalido")
    return u


def valida_senha(senha: str) -> None:
    if not isinstance(senha, str) or not (SENHA_MIN <= len(senha) <= SENHA_MAX):
        raise AuthErro(f"Senha: {SENHA_MIN}–{SENHA_MAX} caracteres.", "senha_fraca")


def valida_display(display: str) -> str:
    d = re.sub(r"\s+", " ", (display or "").strip())[:40]
    if len(d) < 2:
        raise AuthErro("Nome: mínimo 2 letras.", "nome_invalido")
    return d


# ── Auditoria (sem conteúdo privado) ──────────────────────────────────
def auditar(db, ator: str, acao: str, alvo: str = "", detalhe: str = "") -> None:
    try:
        with db:
            db.execute("INSERT INTO audit_log (ts, ator, acao, alvo, detalhe) VALUES (?,?,?,?,?)",
                       (agora_iso(), (ator or "")[:60], (acao or "")[:60],
                        (alvo or "")[:80], (detalhe or "")[:200]))
    except Exception:
        pass


# ── Usuários ───────────────────────────────────────────────────────────
def novo_uid() -> str:
    return "u-" + secrets.token_hex(6)


def buscar_usuario(db, username: str):
    u = (username or "").strip().lower()
    row = db.execute("SELECT uid, username, display, hash, role, status, aprovado, "
                     "max_ai_hora, max_ia_simult FROM users WHERE username=?", (u,)).fetchone()
    if not row:
        return None
    return {"uid": row[0], "username": row[1], "display": row[2], "hash": row[3],
            "role": row[4], "status": row[5], "aprovado": row[6],
            "max_ai_hora": row[7], "max_ia_simult": row[8]}


def buscar_uid(db, uid: str):
    try:
        row = db.execute("SELECT uid, username, display, role, status, remote_ok, bloqueado_ate "
                         "FROM users WHERE uid=?", (uid,)).fetchone()
    except Exception:
        row = db.execute("SELECT uid, username, display, role, status FROM users WHERE uid=?",
                         (uid,)).fetchone()
        if not row:
            return None
        return {"uid": row[0], "username": row[1], "display": row[2], "role": row[3],
                "status": row[4], "remote_ok": False, "bloqueado_ate": ""}
    if not row:
        return None
    return {"uid": row[0], "username": row[1], "display": row[2], "role": row[3],
            "status": row[4], "remote_ok": bool(row[5]), "bloqueado_ate": row[6] or ""}


def status_efetivo(db, uid: str) -> str:
    """'ativo' ou 'bloqueado', com auto-levantamento de suspensão vencida."""
    try:
        row = db.execute("SELECT status, bloqueado_ate FROM users WHERE uid=?", (uid,)).fetchone()
    except Exception:
        return "ativo"
    if not row:
        return "ativo"
    status, ate = row[0], (row[1] or "") if len(row) > 1 else ""
    if status == "bloqueado" and ate:
        try:
            if datetime.now(timezone.utc) >= datetime.fromisoformat(ate):
                with db:
                    db.execute("UPDATE users SET status='ativo', bloqueado_ate='' WHERE uid=?", (uid,))
                auditar(db, "sistema", "suspensao_vencida", uid)
                return "ativo"
        except (ValueError, TypeError):
            pass
    return status or "ativo"


def criar_usuario(db, username: str, display: str, senha: str, *, papel="user",
                  criado_por="sistema", aprovado=True) -> dict:
    """Criação direta (admin). Nunca atribui admin via registro público."""
    u = valida_username(username)
    d = valida_display(display)
    valida_senha(senha)
    if papel not in ROLES:
        raise AuthErro("Papel inválido.", "papel_invalido")
    if buscar_usuario(db, u):
        raise AuthErro("Esse nome de usuário já está em uso.", "duplicado")
    uid = novo_uid()
    with db:
        try:
            db.execute("""INSERT INTO users
                (uid, username, display, hash, role, status, aprovado, created_at)
                VALUES (?,?,?,?,?,?,?,?)""",
                (uid, u, d, hash_senha(senha), papel,
                 "ativo" if aprovado else "pendente", 1 if aprovado else 0, agora_iso()))
        except Exception:
            raise AuthErro("Esse nome de usuário já está em uso.", "duplicado") from None
    auditar(db, criado_por, "usuario_criado", u, f"papel={papel}")
    return {"uid": uid, "username": u, "display": d, "role": papel}


def vincular_proprietario(db, username: str, display: str, senha: str) -> dict:
    """Bootstrap local do admin: liga a conta do dono (uid 'owner'), sem senha padrão."""
    u = valida_username(username)
    d = valida_display(display)
    valida_senha(senha)
    ex = db.execute("SELECT uid, role FROM users WHERE uid=?", (DONO_UID,)).fetchone()
    with db:
        if ex:
            if ex[1] != "admin":
                raise AuthErro("Conta do proprietário já existe com outro papel.", "conflito")
            db.execute("UPDATE users SET username=?, display=?, hash=? WHERE uid=?",
                       (u, d, hash_senha(senha), DONO_UID))
        else:
            if buscar_usuario(db, u):
                raise AuthErro("Esse nome de usuário já está em uso.", "duplicado")
            db.execute("""INSERT INTO users
                (uid, username, display, hash, role, status, aprovado, created_at)
                VALUES (?,?,?,?,?,?,?,?)""",
                (DONO_UID, u, d, hash_senha(senha), "admin", "ativo", 1, agora_iso()))
    auditar(db, "bootstrap-local", "proprietario_vinculado", u)
    return {"uid": DONO_UID, "username": u, "display": d, "role": "admin"}


def login_conta(db, username: str, senha: str) -> dict:
    """Retorna {uid, username, display, role} ou levanta AuthErro genérico."""
    u = (username or "").strip().lower()
    user = buscar_usuario(db, u)
    if user is None or not user["hash"] or not confere_senha(senha or "", user["hash"]):
        # Check if there's a pending registration request with this username
        pend = db.execute("SELECT status FROM reg_requests WHERE username=? "
                          "ORDER BY id DESC LIMIT 1", (u,)).fetchone()
        if pend and pend[0] in ("pendente", "aprovado"):
            if pend[0] == "pendente":
                raise AuthErro("Conta aguardando aprovação.", "pendente")
        raise AuthErro("Usuário ou senha inválidos.", "credenciais")
    if status_efetivo(db, user["uid"]) == "bloqueado":
        raise AuthErro("Usuário ou senha inválidos.", "credenciais")
    if not user["aprovado"] or status_efetivo(db, user["uid"]) != "ativo":
        raise AuthErro("Conta aguardando aprovação.", "pendente")
    with db:
        db.execute("UPDATE users SET last_seen=? WHERE uid=?", (agora_iso(), user["uid"]))
    return {"uid": user["uid"], "username": user["username"],
            "display": user["display"], "role": user["role"]}


def trocar_senha(db, uid: str, atual: str, nova: str) -> None:
    row = db.execute("SELECT hash FROM users WHERE uid=?", (uid,)).fetchone()
    if not row or not row[0] or not confere_senha(atual or "", row[0]):
        raise AuthErro("Senha atual incorreta.", "senha_atual")
    valida_senha(nova)
    with db:
        db.execute("UPDATE users SET hash=? WHERE uid=?", (hash_senha(nova), uid))
    auditar(db, uid, "senha_trocada")


def definir_papel(db, ator_uid: str, alvo_uid: str, papel: str) -> None:
    if papel not in ROLES:
        raise AuthErro("Papel inválido.", "papel_invalido")
    if alvo_uid == ator_uid:
        raise AuthErro("Não é possível alterar o próprio papel.", "auto")
    alvo = buscar_uid(db, alvo_uid)
    if not alvo:
        raise AuthErro("Conta não encontrada.", "ausente")
    if alvo["role"] == "admin" and papel != "admin":
        n = db.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND status='ativo' "
                       "AND uid != ?", (alvo_uid,)).fetchone()[0]
        if not n:
            raise AuthErro("Não é possível rebaixar o último admin ativo.", "ultimo_admin")
    with db:
        db.execute("UPDATE users SET role=? WHERE uid=?", (papel, alvo_uid))
    auditar(db, ator_uid, "papel_alterado", alvo["username"], f"papel={papel}")


def definir_status(db, ator_uid: str, alvo_uid: str, status: str, dias: int = 0) -> None:
    """Bloqueio definitivo (dias=0) ou suspensão temporária (dias 1..365, auto-levanta)."""
    if status not in ("ativo", "bloqueado"):
        raise AuthErro("Status inválido.", "status_invalido")
    if alvo_uid == ator_uid:
        raise AuthErro("Não é possível bloquear a si mesmo.", "auto")
    alvo = buscar_uid(db, alvo_uid)
    if not alvo:
        raise AuthErro("Conta não encontrada.", "ausente")
    ate = ""
    if status == "bloqueado" and dias:
        try:
            dias = min(max(int(dias), 1), 365)
        except (TypeError, ValueError):
            raise AuthErro("Duração inválida.", "invalido") from None
        from datetime import timedelta
        ate = (datetime.now(timezone.utc) + timedelta(days=dias)).isoformat()
    with db:
        db.execute("UPDATE users SET status=?, bloqueado_ate=? WHERE uid=?", (status, ate, alvo_uid))
        if status == "bloqueado":
            db.execute("UPDATE user_sessions SET revogada=1 WHERE uid=?", (alvo_uid,))
    auditar(db, ator_uid, "bloqueado" if status == "bloqueado" else "desbloqueado",
            alvo["username"], f"ate={ate}" if ate else "")


def excluir_usuario(db, ator_uid: str, alvo_uid: str) -> int:
    """Apaga a conta E todos os dados do dono. Retorna mensagens apagadas."""
    if alvo_uid == ator_uid:
        raise AuthErro("Não é possível excluir a própria conta por aqui.", "auto")
    alvo = buscar_uid(db, alvo_uid)
    if not alvo:
        raise AuthErro("Conta não encontrada.", "ausente")
    if alvo["role"] == "admin":
        n = db.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND status='ativo' "
                       "AND uid != ?", (alvo_uid,)).fetchone()[0]
        if not n:
            raise AuthErro("Não é possível excluir o último admin ativo.", "ultimo_admin")
    total = 0
    with db:
        for tabela, col in (("messages", "owner_id"), ("ai_requests", "owner_id"),
                            ("memories", "owner_id"), ("memory_facts", "owner_id"),
                            ("documents", "owner_id"), ("doc_chunks", "owner_id"),
                            ("ui_state", "owner_id"), ("memory_events", "owner_id"),
                            ("memories_fts", "owner_id")):
            try:
                cur = db.execute(f"DELETE FROM {tabela} WHERE {col}=?", (alvo_uid,))
                total += cur.rowcount or 0
            except Exception:
                continue
        db.execute("DELETE FROM user_sessions WHERE uid=?", (alvo_uid,))
        db.execute("DELETE FROM users WHERE uid=?", (alvo_uid,))
    auditar(db, ator_uid, "conta_excluida", alvo["username"], f"registros={total}")
    return total


# ── Sessões ───────────────────────────────────────────────────────────
SESSAO_HORAS = 12


def criar_sessao(db, uid: str) -> dict:
    from datetime import timedelta
    sid = secrets.token_hex(16)
    agora = datetime.now(timezone.utc)
    exp = (agora + timedelta(hours=SESSAO_HORAS)).isoformat()
    with db:
        db.execute("INSERT INTO user_sessions (sid, uid, created_at, expira_em) VALUES (?,?,?,?)",
                   (sid, uid, agora.isoformat(), exp))
        db.execute("UPDATE users SET last_seen=? WHERE uid=?", (agora.isoformat(), uid))
    return {"sid": sid, "expira_em": exp}


def sessao_valida(db, sid: str):
    if not sid or not isinstance(sid, str):
        return None
    row = db.execute("SELECT uid, expira_em, revogada FROM user_sessions WHERE sid=?", (sid,)).fetchone()
    if not row or row[2]:
        return None
    try:
        exp = datetime.fromisoformat(row[1])
        agora = datetime.now(exp.tzinfo)
        if agora >= exp:
            return None
    except (ValueError, TypeError):
        return None
    user = buscar_uid(db, row[0])
    if not user or status_efetivo(db, row[0]) != "ativo":
        return None
    return user


def revogar_sessao(db, sid: str) -> None:
    with db:
        db.execute("UPDATE user_sessions SET revogada=1 WHERE sid=?", (sid,))


def revogar_sessoes(db, ator_uid: str, alvo_uid: str) -> None:
    """Revoga todas as sessões de um usuário (admin)."""
    with db:
        db.execute("UPDATE user_sessions SET revogada=1 WHERE uid=?", (alvo_uid,))
    auditar(db, ator_uid, "sessoes_revogadas", alvo_uid)


def sids_revogados(db, limite: int = 500) -> list:
    try:
        rows = db.execute("SELECT sid FROM user_sessions WHERE revogada=1 "
                          "ORDER BY rowid DESC LIMIT ?", (limite,)).fetchall()
        return [r[0] for r in rows]
    except Exception:
        return []


# ── Convites ──────────────────────────────────────────────────────────
def gerar_convite(db, criado_por: str, max_usos: int = 1, dias: int = 7, nota: str = "") -> dict:
    codigo = "JULIA-" + secrets.token_urlsafe(9).upper().replace("-", "")[:12]
    digest = hashlib.sha256(codigo.encode()).hexdigest()
    from datetime import timedelta
    exp = (datetime.now(timezone.utc) + timedelta(days=max(1, min(dias, 90)))).isoformat()
    with db:
        cur = db.execute("""INSERT INTO invites
            (code_hash, max_usos, expira_em, criado_por, nota, created_at)
            VALUES (?,?,?,?,?,?)""",
            (digest, min(max(int(max_usos), 1), 50), exp, criado_por[:60],
             (nota or "")[:120], agora_iso()))
    auditar(db, criado_por, "convite_criado", f"#{cur.lastrowid}")
    return {"codigo": codigo, "expira_em": exp, "max_usos": max_usos}


def _convite_valido(db, codigo: str):
    digest = hashlib.sha256((codigo or "").strip().upper().encode()).hexdigest()
    row = db.execute("SELECT id, max_usos, usos, expira_em, revogado FROM invites "
                     "WHERE code_hash=?", (digest,)).fetchone()
    if not row:
        return None, "Convite inválido."
    _id, mx, usos, exp, rev = row
    if rev:
        return None, "Convite revogado."
    try:
        if datetime.now(timezone.utc) >= datetime.fromisoformat(exp):
            return None, "Convite expirado."
    except (ValueError, TypeError):
        return None, "Convite inválido."
    if usos >= mx:
        return None, "Convite já utilizado."
    return {"id": _id}, ""


def consumir_convite(db, codigo: str) -> None:
    """Consome UM uso atomicamente; erro se inválido/expirado/esgotado."""
    digest = hashlib.sha256((codigo or "").strip().upper().encode()).hexdigest()
    with db:
        cur = db.execute("""UPDATE invites SET usos = usos + 1 WHERE code_hash=?
                            AND revogado=0 AND usos < max_usos
                            AND datetime(expira_em) > datetime('now')""", (digest,))
        if not cur.rowcount:
            info, motivo = _convite_valido(db, codigo)
            raise AuthErro(motivo, "convite_invalido")


def revogar_convite(db, ator: str, convite_id: int) -> None:
    with db:
        db.execute("UPDATE invites SET revogado=1 WHERE id=?", (int(convite_id),))
    auditar(db, ator, "convite_revogado", f"#{convite_id}")


def listar_convites(db):
    rows = db.execute("SELECT id, max_usos, usos, expira_em, criado_por, revogado, nota, created_at "
                      "FROM invites ORDER BY id DESC LIMIT 100").fetchall()
    return [{"id": i, "max_usos": mx, "usos": u, "expira_em": e, "criado_por": c,
             "revogado": bool(r), "nota": n, "created_at": ca}
            for i, mx, u, e, c, r, n, ca in rows]


# ── Registro ──────────────────────────────────────────────────────────
def registrar(db, display: str, username: str, senha: str, convite: str = "") -> dict:
    """Fluxo público de cadastro conforme o modo. Nunca cria admin."""
    d = valida_display(display)
    u = valida_username(username)
    valida_senha(senha)
    if buscar_usuario(db, u):
        raise AuthErro("Esse nome de usuário já está em uso.", "duplicado")
    modo = modo_cadastro(db)
    if modo == "fechado":
        raise AuthErro("Cadastros fechados. Peça uma conta ao administrador.", "fechado")
    if modo == "convite":
        if not (convite or "").strip():
            raise AuthErro("É necessário um código de convite.", "convite_necessario")
        consumir_convite(db, convite)
        precisa_aprovacao = config_get(db, "exigir_aprovacao", "0") == "1"
        user = criar_usuario(db, u, d, senha, criado_por="convite:" + (convite or "")[:12],
                             aprovado=not precisa_aprovacao)
        return {"uid": user["uid"], "username": u, "display": d,
                "status": "pendente" if precisa_aprovacao else "ativo"}
    # aberto
    precisa_aprovacao = config_get(db, "exigir_aprovacao", "1") == "1"
    if precisa_aprovacao:
        with db:
            db.execute("""INSERT INTO reg_requests (username, display, hash, status, created_at)
                VALUES (?,?,?,?,?)""", (u, d, hash_senha(senha), "pendente", agora_iso()))
        auditar(db, "registro", "cadastro_solicitado", u)
        return {"uid": "", "username": u, "display": d, "status": "pendente"}
    user = criar_usuario(db, u, d, senha, criado_por="aberto", aprovado=True)
    return {"uid": user["uid"], "username": u, "display": d, "status": "ativo"}


def listar_pedidos(db):
    rows = db.execute("SELECT id, username, display, status, created_at FROM reg_requests "
                      "WHERE status='pendente' ORDER BY id DESC LIMIT 100").fetchall()
    return [{"id": i, "username": u, "display": d, "status": s, "created_at": c}
            for i, u, d, s, c in rows]


def decidir_pedido(db, ator_uid: str, pedido_id: int, aprovar: bool) -> None:
    row = db.execute("SELECT username, display, hash, status FROM reg_requests WHERE id=?",
                     (int(pedido_id),)).fetchone()
    if not row or row[3] != "pendente":
        raise AuthErro("Solicitação não encontrada.", "ausente")
    with db:
        if aprovar:
            if buscar_usuario(db, row[0]):
                db.execute("UPDATE reg_requests SET status='recusado' WHERE id=?", (int(pedido_id),))
                raise AuthErro("Nome já está em uso.", "duplicado")
            uid = novo_uid()
            db.execute("""INSERT INTO users
                (uid, username, display, hash, role, status, aprovado, created_at)
                VALUES (?,?,?,?,?,?,?,?)""",
                (uid, row[0], row[1], row[2], "user", "ativo", 1, agora_iso()))
            db.execute("UPDATE reg_requests SET status='aprovado' WHERE id=?", (int(pedido_id),))
            auditar(db, ator_uid, "cadastro_aprovado", row[0])
        else:
            db.execute("UPDATE reg_requests SET status='recusado' WHERE id=?", (int(pedido_id),))
            auditar(db, ator_uid, "cadastro_recusado", row[0])


# ── Limites de IA ─────────────────────────────────────────────────────
def limites_usuario(db, uid: str) -> dict:
    row = db.execute("SELECT max_ai_hora, max_ia_simult FROM users WHERE uid=?", (uid,)).fetchone()
    if not row:
        return {"max_ai_hora": 120, "max_ia_simult": 3}
    return {"max_ai_hora": row[0] or 120, "max_ia_simult": row[1] or 3}


def update_limits(db, ator_uid: str, alvo_uid: str, max_ai_hora: int, max_ia_simult: int,
                  remote_ok=None) -> None:
    """Limites de IA + autorização explícita de controle remoto (grant do admin).

    Zero/ausente preserva o valor atual (nunca grava NULL: coluna é NOT NULL).
    """
    if not buscar_uid(db, alvo_uid):
        raise AuthErro("Conta não encontrada.", "ausente")
    atual = limites_usuario(db, alvo_uid)
    try:
        max_ai_hora = int(max_ai_hora or 0)
    except (TypeError, ValueError):
        max_ai_hora = 0
    try:
        max_ia_simult = int(max_ia_simult or 0)
    except (TypeError, ValueError):
        max_ia_simult = 0
    if max_ai_hora <= 0:
        max_ai_hora = atual["max_ai_hora"]
    if max_ia_simult <= 0:
        max_ia_simult = atual["max_ia_simult"]
    with db:
        db.execute("UPDATE users SET max_ai_hora=?, max_ia_simult=? WHERE uid=?",
                   (max_ai_hora, max_ia_simult, alvo_uid))
        if remote_ok is not None:
            ligado = remote_ok is True or str(remote_ok).strip().lower() in ("1", "true", "sim")
            db.execute("UPDATE users SET remote_ok=? WHERE uid=?",
                       (1 if ligado else 0, alvo_uid))
    auditar(db, ator_uid, "limites_alterados", alvo_uid,
            f"max_ai_hora={max_ai_hora}, max_ia_simult={max_ia_simult}, remote_ok={remote_ok}")


def pode_remoto(db, owner: str) -> bool:
    """Controle remoto/tela: dono local sempre; contas só com grant explícito."""
    if dono_valido_local(owner):
        return True
    try:
        user = buscar_uid(db, owner)
        return bool(user) and user.get("status") == "ativo" and bool(user.get("remote_ok"))
    except Exception:
        return False


def dono_valido_local(owner) -> bool:
    return (str(owner or "").strip().lower() or "local") == "local"


def uso_ia_hora(db, uid: str) -> int:
    try:
        row = db.execute("SELECT COUNT(*) FROM ai_requests WHERE owner_id=? "
                         "AND state IN ('processing','queued','completed') "
                         "AND datetime(created_at) > datetime('now','-1 hour')", (uid,)).fetchone()
        return row[0] if row else 0
    except Exception:
        return 0


def simultaneas_ia(db, uid: str) -> int:
    try:
        row = db.execute("SELECT COUNT(*) FROM ai_requests WHERE owner_id=? AND state='processing'",
                         (uid,)).fetchone()
        return row[0] if row else 0
    except Exception:
        return 0
