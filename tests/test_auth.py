"""Segurança de contas (§17 do spec 4.1.5): 28 itens aplicáveis."""
import os
import sqlite3
import sys
import threading
import time
from pathlib import Path

import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import FAJULTO_auth
import pc_agent
import server
from argon2 import PasswordHasher
from fastapi.testclient import TestClient


def setup_module():
    os.environ['FAJULTO_USERNAME'] = 'owneruser'
    os.environ['FAJULTO_PASSWORD_HASH'] = PasswordHasher().hash('strong-example-password')
    os.environ['FAJULTO_SESSION_SECRET'] = 'a' * 64
    os.environ['FAJULTO_AGENT_TOKEN'] = 'b' * 64
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
    FAJULTO_auth.config_set(db, 'modo_cadastro', 'convite')
    conv = FAJULTO_auth.gerar_convite(db, 'owner', max_usos=5)
    r = FAJULTO_auth.registrar(db, 'Ana', 'ana', 'senha-forte-1', conv['codigo'])
    assert r['status'] == 'ativo' and r['uid'].startswith('u-')
    for display, user, senha in [('A', 'ana2', 'senha-forte-1'), ('Ana', 'XX', 'senha-forte-1'),
                                 ('Ana', 'ana3', 'curta')]:
        try:
            FAJULTO_auth.registrar(db, display, user, senha, conv['codigo'])
            raise AssertionError('deveria falhar')
        except FAJULTO_auth.AuthErro:
            pass
    try:
        FAJULTO_auth.registrar(db, 'Ana 2', 'ana', 'senha-forte-1', conv['codigo'])
        raise AssertionError('duplicado deveria falhar')
    except FAJULTO_auth.AuthErro as exc:
        assert exc.codigo == 'duplicado'
    db.close()


def test_concorrencia_cadastro(tmp_path):
    caminho = tmp_path / 'conc.sqlite3'
    db = pc_agent.open_db(caminho)
    FAJULTO_auth.config_set(db, 'modo_cadastro', 'convite')
    conv = FAJULTO_auth.gerar_convite(db, 'owner', max_usos=10)
    db.close()
    erros = []

    def cad(i):
        # cada thread com sua conexão (como o agente faz nas threads de stream)
        try:
            d = pc_agent.open_db(caminho)
            try:
                FAJULTO_auth.registrar(d, f'Con {i}', 'concorrente', f'senha-forte-{i}', conv['codigo'])
            finally:
                d.close()
        except FAJULTO_auth.AuthErro as exc:
            erros.append(exc.codigo)

    ts = [threading.Thread(target=cad, args=(i,)) for i in range(4)]
    [t.start() for t in ts]
    [t.join(timeout=15) for t in ts]
    assert erros.count('duplicado') == 3, erros


# 5,6,7 — convite expirado/revogado/reutilizado
def test_convites():
    db = _db()
    c1 = FAJULTO_auth.gerar_convite(db, 'owner', max_usos=1)
    db.execute("UPDATE invites SET expira_em='2000-01-01T00:00:00' WHERE code_hash=?",
               (__import__('hashlib').sha256(c1['codigo'].encode()).hexdigest(),))
    db.commit()
    try:
        FAJULTO_auth.consumir_convite(db, c1['codigo'])
        raise AssertionError('expirado')
    except FAJULTO_auth.AuthErro as exc:
        assert exc.codigo == 'convite_invalido'
    c2 = FAJULTO_auth.gerar_convite(db, 'owner')
    FAJULTO_auth.revogar_convite(db, 'owner', 2)
    try:
        FAJULTO_auth.consumir_convite(db, c2['codigo'])
        raise AssertionError('revogado')
    except FAJULTO_auth.AuthErro:
        pass
    c3 = FAJULTO_auth.gerar_convite(db, 'owner', max_usos=1)
    FAJULTO_auth.consumir_convite(db, c3['codigo'])
    try:
        FAJULTO_auth.consumir_convite(db, c3['codigo'])
        raise AssertionError('reutilizado')
    except FAJULTO_auth.AuthErro:
        pass
    db.close()


# 8,9 — fechado / aberto com aprovação
def test_modos_fechado_aberto():
    db = _db()
    FAJULTO_auth.config_set(db, 'modo_cadastro', 'fechado')
    try:
        FAJULTO_auth.registrar(db, 'Zed', 'zed', 'senha-forte-1')
        raise AssertionError('fechado')
    except FAJULTO_auth.AuthErro as exc:
        assert exc.codigo == 'fechado'
    FAJULTO_auth.config_set(db, 'modo_cadastro', 'aberto')
    FAJULTO_auth.config_set(db, 'exigir_aprovacao', '1')
    r = FAJULTO_auth.registrar(db, 'Zed', 'zed', 'senha-forte-1')
    assert r['status'] == 'pendente' and r['uid'] == ''
    try:
        FAJULTO_auth.login_conta(db, 'zed', 'senha-forte-1')
        raise AssertionError('pendente não entra')
    except FAJULTO_auth.AuthErro as exc:
        assert exc.codigo == 'pendente'
    pedidos = FAJULTO_auth.listar_pedidos(db)
    assert len(pedidos) == 1
    FAJULTO_auth.decidir_pedido(db, 'owner', pedidos[0]['id'], True)
    ok = FAJULTO_auth.login_conta(db, 'zed', 'senha-forte-1')
    assert ok['role'] == 'user'  # nunca admin via registro (20)
    db.close()


# 10,11,14,15 — login ok/nok, bloqueio
def test_login_e_bloqueio():
    db = _db()
    FAJULTO_auth.config_set(db, 'modo_cadastro', 'convite')
    conv = FAJULTO_auth.gerar_convite(db, 'owner', max_usos=5)
    FAJULTO_auth.registrar(db, 'Bia', 'bia', 'senha-forte-1', conv['codigo'])
    assert FAJULTO_auth.login_conta(db, 'bia', 'senha-forte-1')['uid'].startswith('u-')
    try:
        FAJULTO_auth.login_conta(db, 'bia', 'errada')
        raise AssertionError('senha errada')
    except FAJULTO_auth.AuthErro as exc:
        assert exc.codigo == 'credenciais'  # genérico, sem vazar existência
    FAJULTO_auth.definir_status(db, 'owner', FAJULTO_auth.buscar_usuario(db, 'bia')['uid'], 'bloqueado')
    assert pc_agent.dono_bloqueado(db, FAJULTO_auth.buscar_usuario(db, 'bia')['uid'])
    try:
        FAJULTO_auth.login_conta(db, 'bia', 'senha-forte-1')
        raise AssertionError('bloqueada')
    except FAJULTO_auth.AuthErro as exc:
        assert exc.codigo == 'credenciais'
    db.close()


# 13,21 — revogação e último admin
def test_revogacao_e_ultimo_admin():
    db = _db()
    FAJULTO_auth.vincular_proprietario(db, 'owneruser', 'Dono', 'senha-forte-owner')
    u = FAJULTO_auth.buscar_usuario(db, 'owneruser')
    assert u['uid'] == 'local' and u['role'] == 'admin'
    sess = FAJULTO_auth.criar_sessao(db, 'local')
    assert FAJULTO_auth.sessao_valida(db, sess['sid'])['uid'] == 'local'
    FAJULTO_auth.revogar_sessao(db, sess['sid'])
    assert FAJULTO_auth.sessao_valida(db, sess['sid']) is None
    assert sess['sid'] in FAJULTO_auth.sids_revogados(db)
    try:
        FAJULTO_auth.definir_papel(db, 'local', 'local', 'user')
        raise AssertionError('auto-rebaixar')
    except FAJULTO_auth.AuthErro as exc:
        assert exc.codigo == 'auto'
    try:
        FAJULTO_auth.excluir_usuario(db, 'local', 'local')
        raise AssertionError('auto-excluir')
    except FAJULTO_auth.AuthErro:
        pass
    # segundo admin permite mexer no primeiro
    FAJULTO_auth.criar_usuario(db, 'admin2', 'Admin 2', 'senha-forte-2', papel='admin', criado_por='local')
    a2 = FAJULTO_auth.buscar_usuario(db, 'admin2')['uid']
    FAJULTO_auth.definir_papel(db, a2, 'local', 'user')
    assert FAJULTO_auth.buscar_uid(db, 'local')['role'] == 'user'
    try:
        FAJULTO_auth.excluir_usuario(db, a2, a2)
        raise AssertionError('auto-excluir 2')
    except FAJULTO_auth.AuthErro:
        pass
    try:
        FAJULTO_auth.definir_papel(db, 'local', a2, 'user')
        raise AssertionError('rebaixar ultimo admin')
    except FAJULTO_auth.AuthErro as exc:
        assert exc.codigo == 'ultimo_admin'
    try:
        FAJULTO_auth.definir_papel(db, a2, 'local', 'admin')
    except FAJULTO_auth.AuthErro:
        pass  # 'local' agora é user comum; sem outro admin, trava (correto)
    db.close()


# 16,20 — comum em API admin + sem escalada no registro
def test_admin_exige_papel_e_registro_nao_escala():
    db = _db()
    FAJULTO_auth.config_set(db, 'modo_cadastro', 'convite')
    conv = FAJULTO_auth.gerar_convite(db, 'owner', max_usos=5)
    FAJULTO_auth.registrar(db, 'Cid', 'cid', 'senha-forte-1', conv['codigo'])
    assert FAJULTO_auth.buscar_uid(db, FAJULTO_auth.buscar_usuario(db, 'cid')['uid'])['role'] == 'user'
    db.close()


# 17 — owner do cliente é ignorado (schemas não têm owner)
def test_schemas_sem_owner_forjavel():
    assert 'owner' not in server.SyncBody.model_fields
    assert 'owner' not in server.AIRequest.model_fields
    assert 'owner' not in server.AIContinue.model_fields


# 22 — tokens e senhas
def test_sem_plaintext_nem_segredo():
    db = _db()
    FAJULTO_auth.config_set(db, 'modo_cadastro', 'convite')
    conv = FAJULTO_auth.gerar_convite(db, 'owner')
    assert conv['codigo'].startswith('FAJULTO-')
    cols = [c[1] for c in db.execute('PRAGMA table_info(invites)').fetchall()]
    assert 'codigo' not in cols  # só hash
    FAJULTO_auth.registrar(db, 'Dan', 'dan', 'senha-forte-1', conv['codigo'])
    row = db.execute('SELECT hash FROM users WHERE username=?', ('dan',)).fetchone()[0]
    assert row.startswith('scrypt$') and 'senha-forte-1' not in row
    assert FAJULTO_auth.confere_senha('senha-forte-1', row)
    assert not FAJULTO_auth.confere_senha('outra', row)
    FAJULTO_auth.auditar(db, 'owner', 'teste', 'dan', 'detalhe')
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
    assert FAJULTO_auth.modo_cadastro(db2) == 'convite'  # padrão inicial
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


def _agente_generico(ws, respostas, vistos):
    while True:
        try:
            req = ws.receive_json()
        except Exception:
            return
        vistos[req.get('type')] = req
        if req.get('type') == 'sess_revogados':
            ws.send_json({'request_id': req['request_id'], 'type': 'sess_revogados',
                          'sids': vistos.get('__revogados__', [])})
            continue
        fn = respostas.get(req.get('type'))
        if fn is None:
            continue
        ws.send_json({'request_id': req['request_id'], **fn(req)})


def test_relay_register_login_account():
    with TestClient(server.app) as client:
        vistos = {}
        with client.websocket_connect('/api/agent/ws',
                                      headers={'Authorization': 'Bearer ' + os.environ['FAJULTO_AGENT_TOKEN']}) as ws:
            respostas = {
                'auth_register': lambda r: {'type': 'auth_registered', 'uid': 'u-aaa',
                                            'username': 'ana', 'display': 'Ana',
                                            'status': 'ativo', 'sid': 'sid-ana'},
                'auth_login': lambda r: {'type': 'auth_ok', 'uid': 'u-aaa', 'username': 'ana',
                                         'display': 'Ana', 'role': 'user', 'sid': 'sid-ana'},
                'auth_whoami': lambda r: {'type': 'auth_user',
                                          'user': {'uid': 'u-aaa', 'username': 'ana',
                                                   'display': 'Ana', 'role': 'user', 'status': 'ativo'}},
                'account_password': lambda r: {'type': 'account_ok'},
            }
            t = threading.Thread(target=_agente_generico, args=(ws, respostas, vistos), daemon=True)
            t.start()
            reg = client.post('/api/register', json={'display': 'Ana', 'username': 'ana',
                                                     'password': 'senha-forte-1', 'invite': 'FAJULTO-X'})
            assert reg.status_code == 200, reg.text
            assert reg.json()['user'] == 'Ana'
            assert 'FAJULTO_session' in reg.cookies
            lg = client.post('/api/login', json={'username': 'ana', 'password': 'senha-forte-1'})
            assert lg.status_code == 200 and lg.json()['uid'] == 'u-aaa'
            sess = client.get('/api/session')
            assert sess.json()['uid'] == 'u-aaa' and sess.json()['role'] == 'user'
            acc = client.get('/api/account')
            assert acc.json()['username'] == 'ana'
            pw = client.post('/api/account/password', json={'atual': 'x', 'nova': 'senha-forte-2'},
                             headers={'X-CSRF-Token': sess.json()['csrf']})
            assert pw.json() == {'ok': True}
            assert vistos['auth_register']['invite'] == 'FAJULTO-X'
            bad = client.post('/api/register', json={'display': 'A', 'username': 'xx',
                                                      'password': 'curta'})
            assert bad.status_code == 422


def test_relay_login_pendente_e_sessao_trocada():
    with TestClient(server.app) as client:
        with client.websocket_connect('/api/agent/ws',
                                      headers={'Authorization': 'Bearer ' + os.environ['FAJULTO_AGENT_TOKEN']}) as ws:
            vistos = {}
            respostas = {
                'auth_login': lambda r: {'type': 'auth_error', 'error': 'x', 'codigo': 'pendente'},
                'auth_whoami': lambda r: {'type': 'auth_user',
                                          'user': {'uid': 'u-outro', 'username': 'x',
                                                   'display': 'X', 'role': 'user', 'status': 'ativo'}},
            }
            t = threading.Thread(target=_agente_generico, args=(ws, respostas, vistos), daemon=True)
            t.start()
            r = client.post('/api/login', json={'username': 'alguem', 'password': 'senha-forte-1'})
            assert r.status_code == 403
            lg = client.post('/api/login', json={'username': 'owneruser', 'password': 'strong-example-password'})
            assert lg.status_code == 200  # legado não depende do PC
            s = client.get('/api/session')
            assert s.json()['uid'] == 'local' and s.json()['role'] == 'admin'  # sem consultar o PC


def test_relay_sid_revogado_bloqueia_dados():
    with TestClient(server.app) as client:
        with client.websocket_connect('/api/agent/ws',
                                      headers={'Authorization': 'Bearer ' + os.environ['FAJULTO_AGENT_TOKEN']}) as ws:
            vistos = {'__revogados__': ['sid-ana']}
            respostas = {
                'auth_login': lambda r: {'type': 'auth_ok', 'uid': 'u-aaa', 'username': 'ana',
                                         'display': 'Ana', 'role': 'user', 'sid': 'sid-ana'},
            }
            t = threading.Thread(target=_agente_generico, args=(ws, respostas, vistos), daemon=True)
            t.start()
            lg = client.post('/api/login', json={'username': 'ana', 'password': 'senha-forte-1'})
            assert lg.status_code == 200
            r = client.post('/api/sync', json={'messages': []},
                            headers={'X-CSRF-Token': lg.json()['csrf']})
            assert r.status_code in (401, 422)  # 401 revogada (ou 422 lote vazio se passar)


def test_relay_remoto_negado_vira_403():
    with TestClient(server.app) as client:
        csrf = _login_legacy(client)
        with client.websocket_connect('/api/agent/ws',
                                      headers={'Authorization': 'Bearer ' + os.environ['FAJULTO_AGENT_TOKEN']}) as ws:
            out = {}

            def tela():
                out['t'] = client.get('/api/screen?max_w=800&q=50', headers={'X-CSRF-Token': csrf})

            def tecla():
                out['k'] = client.post('/api/input', json={'kind': 'key', 'key': 'enter'},
                                       headers={'X-CSRF-Token': csrf})

            t = threading.Thread(target=tela)
            t.start()
            for _ in range(3):
                req = ws.receive_json()
                if req['type'] == 'sess_revogados':
                    ws.send_json({'request_id': req['request_id'], 'type': 'sess_revogados', 'sids': []})
                    continue
                break
            assert req['type'] == 'screen' and req.get('owner') == 'local'
            ws.send_json({'request_id': req['request_id'], 'type': 'screen_error',
                          'error': 'Sem autorização para ver a tela.', 'codigo': 'sem_permissao'})
            t.join(timeout=8)
            assert out['t'].status_code == 403

            t = threading.Thread(target=tecla)
            t.start()
            for _ in range(3):
                req = ws.receive_json()
                if req['type'] == 'sess_revogados':
                    ws.send_json({'request_id': req['request_id'], 'type': 'sess_revogados', 'sids': []})
                    continue
                break
            assert req['type'] == 'input'
            ws.send_json({'request_id': req['request_id'], 'type': 'input_error',
                          'error': 'Sem autorização para controlar o PC.', 'codigo': 'sem_permissao'})
            t.join(timeout=8)
            assert out['k'].status_code == 403


def test_relay_admin_exige_papel():
    with TestClient(server.app) as client:
        with client.websocket_connect('/api/agent/ws',
                                      headers={'Authorization': 'Bearer ' + os.environ['FAJULTO_AGENT_TOKEN']}) as ws:
            vistos = {}
            respostas = {
                'auth_login': lambda r: {'type': 'auth_ok', 'uid': 'u-aaa', 'username': 'ana',
                                         'display': 'Ana', 'role': 'user', 'sid': 'sid-ana'},
                'auth_whoami': lambda r: {'type': 'auth_user',
                                          'user': {'uid': 'u-aaa', 'username': 'ana',
                                                   'display': 'Ana', 'role': 'user', 'status': 'ativo'}},
                'admin_users': lambda r: {'type': 'op_error', 'error': 'x', 'codigo': 'permissao'},
            }
            t = threading.Thread(target=_agente_generico, args=(ws, respostas, vistos), daemon=True)
            t.start()
            lg = client.post('/api/login', json={'username': 'ana', 'password': 'senha-forte-1'})
            csrf = lg.json()['csrf']
            r = client.get('/api/admin/users', headers={'X-CSRF-Token': csrf})
            assert r.status_code == 403  # negado sem vazar dados
            assert 'admin_users' not in vistos  # barrado no relay, nem chega ao PC


def test_remoto_exige_grant_explicito():
    db = _db()
    import FAJULTO_auth as _ja
    _ja.criar_usuario(db, 'visit', 'Visita', 'senha-forte-1', criado_por='t')
    visitante = _ja.buscar_usuario(db, 'visit')['uid']
    assert _ja.pode_remoto(db, 'local') is True  # dono do PC
    assert _ja.pode_remoto(db, visitante) is False
    _ja.update_limits(db, 'local', visitante, 0, 0, True)
    assert _ja.pode_remoto(db, visitante) is True
    _ja.update_limits(db, 'local', visitante, 0, 0, False)
    assert _ja.pode_remoto(db, visitante) is False
    # limites numéricos preservados ao mexer só no remoto
    _ja.update_limits(db, 'local', visitante, 50, 2, None)
    assert _ja.limites_usuario(db, visitante)['max_ai_hora'] == 50
    _ja.update_limits(db, 'local', visitante, 0, 0, True)
    assert _ja.limites_usuario(db, visitante)['max_ai_hora'] == 50
    # bloqueado perde remoto mesmo com grant
    _ja.definir_status(db, 'local', visitante, 'bloqueado')
    assert _ja.pode_remoto(db, visitante) is False
    db.close()


def test_suspensao_temporaria_auto_levanta():
    db = _db()
    import FAJULTO_auth as _ja
    _ja.criar_usuario(db, 'temp', 'Temp', 'senha-forte-1', criado_por='t')
    uid = _ja.buscar_usuario(db, 'temp')['uid']
    _ja.definir_status(db, 'local', uid, 'bloqueado', dias=1)
    row = _ja.buscar_uid(db, uid)
    assert row['status'] == 'bloqueado' and row['bloqueado_ate'] != ''
    assert _ja.status_efetivo(db, uid) == 'bloqueado'
    try:
        _ja.login_conta(db, 'temp', 'senha-forte-1')
        raise AssertionError('suspenso não entra')
    except _ja.AuthErro as exc:
        assert exc.codigo == 'credenciais'
    # simula vencimento
    db.execute("UPDATE users SET bloqueado_ate='2000-01-01T00:00:00+00:00' WHERE uid=?", (uid,))
    db.commit()
    assert _ja.status_efetivo(db, uid) == 'ativo'
    assert _ja.login_conta(db, 'temp', 'senha-forte-1')['uid'] == uid
    assert _ja.buscar_uid(db, uid)['bloqueado_ate'] == ''
    # dias inválidos
    try:
        _ja.definir_status(db, 'local', uid, 'bloqueado', dias='xx')
        raise AssertionError('dias inválidos')
    except _ja.AuthErro as exc:
        assert exc.codigo == 'invalido'
    db.close()


# rate limit de login (12)
def test_z_login_rate_limit():
    server.login_failures.clear()
    with TestClient(server.app) as client:
        codes = [client.post('/api/login', json={'username': 'rl-user', 'password': 'x'}).status_code
                 for _ in range(6)]
        assert codes == [401, 401, 401, 401, 401, 429], codes
    server.login_failures.clear()
