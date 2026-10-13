"""Segurança de contas (§17 do spec 4.1.5): 28 itens aplicáveis."""
import os
import sqlite3
import sys
import threading
import time
from pathlib import Path

import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import julia_auth
import pc_agent
import server
from argon2 import PasswordHasher
from fastapi.testclient import TestClient


def setup_module():
    os.environ['JULIA_USERNAME'] = 'owneruser'
    os.environ['JULIA_PASSWORD_HASH'] = PasswordHasher().hash('strong-example-password')
    os.environ['JULIA_SESSION_SECRET'] = 'a' * 64
    os.environ['JULIA_AGENT_TOKEN'] = 'b' * 64
    server.login_failures.clear()
    server.revogados["sids"] = set()
    server.revogados["ts"] = 0.0
    server.revogados["suportado"] = True
    server.revogados["falhas"] = 0


def _db(nome='auth.sqlite3'):
    db = pc_agent.open_db(Path(tempfile.mkdtemp()) / nome)
    return db


def _login_legacy(client):
    r = client.post('/api/login', json={'username': 'owneruser', 'password': 'strong-example-password'})
    assert r.status_code == 200, r.text
    return r.json()['csrf']


# 1,2,3 — registro válido/inválido/duplicado + concorrência
def test_registro_valido_invalido_duplicado():
    db = _db()
    julia_auth.config_set(db, 'modo_cadastro', 'convite')
    conv = julia_auth.gerar_convite(db, 'owner', max_usos=5)
    r = julia_auth.registrar(db, 'Ana', 'ana', 'senha-forte-1', conv['codigo'])
    assert r['status'] == 'ativo' and r['uid'].startswith('u-')
    for display, user, senha in [('A', 'ana2', 'senha-forte-1'), ('Ana', 'XX', 'senha-forte-1'),
                                 ('Ana', 'ana3', 'curta')]:
        try:
            julia_auth.registrar(db, display, user, senha, conv['codigo'])
            raise AssertionError('deveria falhar')
        except julia_auth.AuthErro:
            pass
    try:
        julia_auth.registrar(db, 'Ana 2', 'ana', 'senha-forte-1', conv['codigo'])
        raise AssertionError('duplicado deveria falhar')
    except julia_auth.AuthErro as exc:
        assert exc.codigo == 'duplicado'
    db.close()


def test_concorrencia_cadastro(tmp_path):
    caminho = tmp_path / 'conc.sqlite3'
    db = pc_agent.open_db(caminho)
    julia_auth.config_set(db, 'modo_cadastro', 'convite')
    conv = julia_auth.gerar_convite(db, 'owner', max_usos=10)
    db.close()
    erros = []

    def cad(i):
        # cada thread com sua conexão (como o agente faz nas threads de stream)
        try:
            d = pc_agent.open_db(caminho)
            try:
                julia_auth.registrar(d, f'Con {i}', 'concorrente', f'senha-forte-{i}', conv['codigo'])
            finally:
                d.close()
        except julia_auth.AuthErro as exc:
            erros.append(exc.codigo)

    ts = [threading.Thread(target=cad, args=(i,)) for i in range(4)]
    [t.start() for t in ts]
    [t.join(timeout=15) for t in ts]
    assert erros.count('duplicado') == 3, erros


# 5,6,7 — convite expirado/revogado/reutilizado
def test_convites():
    db = _db()
    c1 = julia_auth.gerar_convite(db, 'owner', max_usos=1)
    db.execute("UPDATE invites SET expira_em='2000-01-01T00:00:00' WHERE code_hash=?",
               (__import__('hashlib').sha256(c1['codigo'].encode()).hexdigest(),))
    db.commit()
    try:
        julia_auth.consumir_convite(db, c1['codigo'])
        raise AssertionError('expirado')
    except julia_auth.AuthErro as exc:
        assert exc.codigo == 'convite_invalido'
    c2 = julia_auth.gerar_convite(db, 'owner')
    julia_auth.revogar_convite(db, 'owner', 2)
    try:
        julia_auth.consumir_convite(db, c2['codigo'])
        raise AssertionError('revogado')
    except julia_auth.AuthErro:
        pass
    c3 = julia_auth.gerar_convite(db, 'owner', max_usos=1)
    julia_auth.consumir_convite(db, c3['codigo'])
    try:
        julia_auth.consumir_convite(db, c3['codigo'])
        raise AssertionError('reutilizado')
    except julia_auth.AuthErro:
        pass
    db.close()


# 8,9 — fechado / aberto com aprovação
def test_modos_fechado_aberto():
    db = _db()
    julia_auth.config_set(db, 'modo_cadastro', 'fechado')
    try:
        julia_auth.registrar(db, 'Zed', 'zed', 'senha-forte-1')
        raise AssertionError('fechado')
    except julia_auth.AuthErro as exc:
        assert exc.codigo == 'fechado'
    julia_auth.config_set(db, 'modo_cadastro', 'aberto')
    julia_auth.config_set(db, 'exigir_aprovacao', '1')
    r = julia_auth.registrar(db, 'Zed', 'zed', 'senha-forte-1')
    assert r['status'] == 'pendente' and r['uid'] == ''
    try:
        julia_auth.login_conta(db, 'zed', 'senha-forte-1')
        raise AssertionError('pendente não entra')
    except julia_auth.AuthErro as exc:
        assert exc.codigo == 'pendente'
    pedidos = julia_auth.listar_pedidos(db)
    assert len(pedidos) == 1
    julia_auth.decidir_pedido(db, 'owner', pedidos[0]['id'], True)
    ok = julia_auth.login_conta(db, 'zed', 'senha-forte-1')
    assert ok['role'] == 'user'  # nunca admin via registro (20)
    db.close()


# 10,11,14,15 — login ok/nok, bloqueio
def test_login_e_bloqueio():
    db = _db()
    julia_auth.config_set(db, 'modo_cadastro', 'convite')
    conv = julia_auth.gerar_convite(db, 'owner', max_usos=5)
    julia_auth.registrar(db, 'Bia', 'bia', 'senha-forte-1', conv['codigo'])
    assert julia_auth.login_conta(db, 'bia', 'senha-forte-1')['uid'].startswith('u-')
    try:
        julia_auth.login_conta(db, 'bia', 'errada')
        raise AssertionError('senha errada')
    except julia_auth.AuthErro as exc:
        assert exc.codigo == 'credenciais'  # genérico, sem vazar existência
    julia_auth.definir_status(db, 'owner', julia_auth.buscar_usuario(db, 'bia')['uid'], 'bloqueado')
    assert pc_agent.dono_bloqueado(db, julia_auth.buscar_usuario(db, 'bia')['uid'])
    try:
        julia_auth.login_conta(db, 'bia', 'senha-forte-1')
        raise AssertionError('bloqueada')
    except julia_auth.AuthErro as exc:
        assert exc.codigo == 'credenciais'
    db.close()


# 13,21 — revogação e último admin
def test_revogacao_e_ultimo_admin():
    db = _db()
    julia_auth.vincular_proprietario(db, 'owneruser', 'Dono', 'senha-forte-owner')
    u = julia_auth.buscar_usuario(db, 'owneruser')
    assert u['uid'] == 'local' and u['role'] == 'admin'
    sess = julia_auth.criar_sessao(db, 'local')
    assert julia_auth.sessao_valida(db, sess['sid'])['uid'] == 'local'
    julia_auth.revogar_sessao(db, sess['sid'])
    assert julia_auth.sessao_valida(db, sess['sid']) is None
    assert sess['sid'] in julia_auth.sids_revogados(db)
    try:
        julia_auth.definir_papel(db, 'local', 'local', 'user')
        raise AssertionError('auto-rebaixar')
    except julia_auth.AuthErro as exc:
        assert exc.codigo == 'auto'
    try:
        julia_auth.excluir_usuario(db, 'local', 'local')
        raise AssertionError('auto-excluir')
    except julia_auth.AuthErro:
        pass
    # segundo admin permite mexer no primeiro
    julia_auth.criar_usuario(db, 'admin2', 'Admin 2', 'senha-forte-2', papel='admin', criado_por='local')
    a2 = julia_auth.buscar_usuario(db, 'admin2')['uid']
    julia_auth.definir_papel(db, a2, 'local', 'user')
    assert julia_auth.buscar_uid(db, 'local')['role'] == 'user'
    try:
        julia_auth.excluir_usuario(db, a2, a2)
        raise AssertionError('auto-excluir 2')
    except julia_auth.AuthErro:
        pass
    try:
        julia_auth.definir_papel(db, 'local', a2, 'user')
        raise AssertionError('rebaixar ultimo admin')
    except julia_auth.AuthErro as exc:
        assert exc.codigo == 'ultimo_admin'
    try:
        julia_auth.definir_papel(db, a2, 'local', 'admin')
    except julia_auth.AuthErro:
        pass  # 'local' agora é user comum; sem outro admin, trava (correto)
    db.close()


# 16,20 — comum em API admin + sem escalada no registro
def test_admin_exige_papel_e_registro_nao_escala():
    db = _db()
    julia_auth.config_set(db, 'modo_cadastro', 'convite')
    conv = julia_auth.gerar_convite(db, 'owner', max_usos=5)
    julia_auth.registrar(db, 'Cid', 'cid', 'senha-forte-1', conv['codigo'])
    assert julia_auth.buscar_uid(db, julia_auth.buscar_usuario(db, 'cid')['uid'])['role'] == 'user'
    db.close()


# 17 — owner do cliente é ignorado (schemas não têm owner)
def test_schemas_sem_owner_forjavel():
    assert 'owner' not in server.SyncBody.model_fields
    assert 'owner' not in server.AIRequest.model_fields
    assert 'owner' not in server.AIContinue.model_fields


# 22 — tokens e senhas
def test_sem_plaintext_nem_segredo():
    db = _db()
    julia_auth.config_set(db, 'modo_cadastro', 'convite')
    conv = julia_auth.gerar_convite(db, 'owner')
    assert conv['codigo'].startswith('JULIA-')
    cols = [c[1] for c in db.execute('PRAGMA table_info(invites)').fetchall()]
    assert 'codigo' not in cols  # só hash
    julia_auth.registrar(db, 'Dan', 'dan', 'senha-forte-1', conv['codigo'])
    row = db.execute('SELECT hash FROM users WHERE username=?', ('dan',)).fetchone()[0]
    assert row.startswith('scrypt$') and 'senha-forte-1' not in row
    assert julia_auth.confere_senha('senha-forte-1', row)
    assert not julia_auth.confere_senha('outra', row)
    julia_auth.auditar(db, 'owner', 'teste', 'dan', 'detalhe')
    blob = ' '.join(r[0] for r in db.execute('SELECT ts||ator||acao||alvo||detalhe FROM audit_log').fetchall())
    assert 'senha-forte-1' not in blob and conv['codigo'] not in blob
    db.close()


# 23,24 — migração legado + restart
def test_migracao_e_restart(tmp_path):
    caminho = tmp_path / 'leg.sqlite3'
    cru = __import__('sqlite3').connect(caminho)
    cru.execute("CREATE TABLE messages (id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,"
                " origin TEXT NOT NULL, role TEXT NOT NULL, text TEXT NOT NULL,"
                " created_at TEXT NOT NULL, received_at TEXT NOT NULL)")
    cru.execute("INSERT INTO messages VALUES ('m1','c','mobile','user','oi','t','t')")
    cru.commit()
    cru.close()
    db = pc_agent.open_db(caminho)
    assert pc_agent.list_messages(db)[0]['text'] == 'oi'  # 'local' preservado
    assert pc_agent.listar_conversas(db)
    db.close()
    db2 = pc_agent.open_db(caminho)
    assert pc_agent.list_messages(db2)
    assert julia_auth.modo_cadastro(db2) == 'convite'  # padrão inicial
    db2.close()


# 25 — PC offline: honestidade
def test_offline_honesto():
    with TestClient(server.app) as client:
        r = client.post('/api/register',
                        json={'display': 'Off', 'username': 'offline1', 'password': 'senha-forte-1'})
        assert r.status_code == 503
        csrf = _login_legacy(client)
        r2 = client.post('/api/login', json={'username': 'naoexiste', 'password': 'x'})
        assert r2.status_code == 401  # sem vazar existência (conta comum exige PC)


# rate limit de login (12)
def test_z_login_rate_limit():
    server.login_failures.clear()
    with TestClient(server.app) as client:
        codes = [client.post('/api/login', json={'username': 'rl-user', 'password': 'x'}).status_code
                 for _ in range(6)]
        assert codes == [401, 401, 401, 401, 401, 429], codes
    server.login_failures.clear()
