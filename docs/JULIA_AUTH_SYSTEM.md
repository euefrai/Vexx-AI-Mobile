# JÚLIA MOBILE 4.1.5 — Sistema de Autenticação

## Arquitetura

```
Navegador (IndexedDB Cache) ◄─── HTTPS Relay (Render) ◄─── PC Agente (SQLite)
       │                               │                          │
       │ login/register                │                      julia_auth.py
       │                               │                      (definitivo)
       └──────────► token JWT          └──────────► identidade verificada
```

### Princípios

- **SQLite definitivo no PC** — não há banco no Render Free.
- **Identidade autenticada e verificável** — o relay encaminha a identidade
  estabelecida pelo sistema de auth, nunca um `owner_id` enviado livremente.
- **Sessões com expiração** — tokens JWT com TTL, revogáveis server-side.
- **Logout real** — revogação de sid no SQLite.
- **Modo offline** — cadastros/logins só conseguem concluir quando o PC
  está disponível. Usuários previamente autenticados continuam com acesso
  enquanto suas sessões são válidas.

## Entidades SQLite (via `julia_auth.py`)

| Tabela              | Propósito                          |
|---------------------|------------------------------------|
| `users`             | Contas (uid, username, display, hash, role, status, limites) |
| `user_sessions`     | Sessões (sid, uid, expira_em, revogada) |
| `reg_requests`      | Pedidos de registro pendentes      |
| `invites`           | Convites (code_hash, usos, revogado) |
| `audit_log`         | Log de auditoria                   |
| `app_config`        | Configurações (modo_cadastro, etc) |
| `messages`          | Mensagens (owner_id migrado)       |
| `memories`          | Memórias (owner_id migrado)        |
| `memory_facts`      | Facts (owner_id migrado)            |

## Credenciais

- Hash: **Argon2id** (`argon2-cffi`).
- Política de senha: mínimo 8 chars, 1 letra, 1 número.
- `valida_username`: 3–20 chars, `[a-z0-9_]`.
- `valida_display`: 1–40 chars, trim.

## Fluxos

### Login
1. Navegador envia `{username, password}` ao relay.
2. Relay encaminha ao PC Agente.
3. Agente resolve → `julia_auth.login_conta(db, username, senha)`.
4. Se válido, cria sessão → `julia_auth.criar_sessao(db, uid)`.
5. Retorna `{ok, sid, uid, display, role, expira_em}`.
6. Relay devolve JWT ao browser.

### Registro
1. Browser envia formulário + código de convite (se modo=convite).
2. Relay encaminha ao agente → `julia_auth.registrar(db, ...)`.
3. Se `exigir_aprovacao`: cria `reg_requests` pendente, usuário aguarda.
4. Se aprovado automaticamente: cria conta e sessão.

### Refresh de Sessão
1. Browser envia sid (ou JWT).
2. Agente → `julia_auth.sessao_valida(db, sid)`.
3. Se revogada ou expirada: 401.

### Logout
1. Browser chama `/api/julia/logout`.
2. Agente → `julia_auth.revogar_sessao(db, sid)`.

## Modos de Cadastro (admin configurável)

| Modo     | Descrição                                      |
|----------|------------------------------------------------|
| `fechado`  | Só admin cria contas (via painel).            |
| `convite`  | Usuário precisa de código válido (padrão).    |
| `aberto`   | Auto-cadastro; admin pode exigir aprovação.   |

## Rate Limiting (brute-force protection)

- Em memória por IP/username: 5 tentativas / 15 min.
- Bloqueio progressivo após falhas consecutivas.

## Limitações Offline

- Cadastro/login só funcionam quando o PC Agente está online.
- Sessões expiram mesmo offline (validação local por timestamp).
- Mensagens enfileiradas no IndexedDB até reconexão.
