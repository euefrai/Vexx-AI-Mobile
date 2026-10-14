# JÚLIA MOBILE 4.1.5 — Sistema de Autenticação (real, verificado no código)

## Arquitetura

```
Navegador (IndexedDB por conta) ◄──HTTPS──► Relay Render (SEM banco)
        login/register/conta  │                    │  cookie assinado (itsdangerous)
                              │                    │  + CSRF + revogação (TTL 60s)
                              ▼                    ▼
                        PC Agent (SQLite definitivo: FAJULTO_auth.py)
```

## Princípios

- **SQLite definitivo no PC** — nada de usuários no Render Free.
- **Identidade verificada, nunca `owner_id` do cliente** — schemas do relay
  (`SyncBody`, `AIRequest`, `AIContinue`) NÃO têm campo owner; o dono sai
  sempre da sessão assinada (`sessao_dados` → `revogacao_ok`).
- **Sessões com expiração (12h)** — cookie HttpOnly/SameSite=strict + `sid`
  rastreável; revogação server-side com cache de 60s no relay.
- **Logout real** — revoga o `sid` no SQLite (best-effort) + limpa cookie.
- **Offline honesto** — cadastro e login de contas novas exigem o PC online
  (503/401 claros, sem simulação). Sessão válida continua lendo o cache local.

## Entidades SQLite (`FAJULTO_auth.py`, só stdlib)

`users` (uid `local` p/ dono legado, `u-hex` demais; username UNIQUE; hash
**scrypt**; role; status; limites), `user_sessions` (sid, expira_em, revogada),
`reg_requests`, `invites` (**só hash** do código), `audit_log` (sem segredos),
`app_config` (modo_cadastro, exigir_aprovacao).

## Credenciais (reais)

- Contas novas: **scrypt** (`n=16384,r=8,p=1`, salt 16B) — stdlib, sem Argon2.
- Dono legado: Argon2id do `.env`, verificado no relay (inalterado).
- Política: senha 8–128 chars; username 3–30 `[a-z0-9._-]`; display 2–40.
- Mensagens de login genéricas (não vaza existência); `TimingSafe` via compare.

## Fluxos (reais)

- **Login**: legado (env) → sessão `local`/admin; senão `auth_login` no PC →
  sessão `{uid, user, sid}`. Pendente → 403 específico. Bloqueado → 401 genérico.
- **Registro**: modo do PC (`fechado` recusa; `convite` exige código com consumo
  atômico; `aberto` cria ou deixa `pendente`). Ativo → auto-login com sessão.
  Nunca cria admin (papel sempre `user`).
- **Sessão**: `/api/session` retorna uid/role/display; legada não consulta o PC.
- **Troca de senha / exclusão**: com senha atual; exclusão apaga TODOS os dados
  do dono (transação) e derruba a sessão; último admin trava.
- **Revogação**: `sess_revogados` (TTL 60s) + expiração 12h + fallback para
  agentes antigos (2 timeouts → desliga refresh, sem stall).

## Rate limiting (real)

- Login: 5 tentativas / 5 min por IP+username (memória do relay).
- Registro: 3 / hora por IP. Convites: espaço 2^72 + limite por IP.

## Limites de uso (aplicados no agente)

`max_ai_hora` (padrão 120) e `max_ia_simult` (padrão 3) por usuário, verificados
em `ai_preparar`; excedente retorna `codigo=limite`. Bloqueados não usam IA nem
dados (checagem central por RPC).
