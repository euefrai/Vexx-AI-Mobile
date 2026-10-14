# JÚLIA MOBILE 4.1.5 — Segurança Multiusuário

## Princípios

1. **Nunca confiar em `owner_id` do cliente.** A identidade é estabelecida
   pelo sistema de autenticação (sid → uid) e propagada pelo relay.
2. **Isolamento entre usuários.** Cada query de dados filtra por `owner_id`.
3. **RBAC no backend.** Autorização validada em `julia_auth` antes de
   qualquer ação administrativa.
4. **Proteção contra escalada.** Nenhum usuário comum pode elevar para admin.
5. **Senha nunca em texto plano.** scrypt (contas novas); Argon2id só no
   login legado do `.env`, verificado no relay.

## Identificadores

| Tipo              | Formato          | Exemplo      |
|-------------------|------------------|--------------|
| uid interno       | `u-<hex>`        | `u-a1b2c3d4` |
| dono legado       | `local`          | `local`      |
| owner_id em dados | `u-<hex>` / `local` | —         |

- `DONO_UID = "local"` — dono legado estável.
- `novo_uid()` gera `u-` + 12 hex chars (seguro, imutável).
- Migração legada: `migrar_legado(db)` converte `owner_id` antigos para `local`.

## Isolamento de Dados

Tabelas com `owner_id`:
- `messages` (conversas)
- `ai_requests` (requisições de IA)
- `memories` (memórias V4.1)
- `memory_facts` (fatos)
- `documents` (documentos)
- `doc_chunks` (chunks)
- `ui_state` (estado JDUI)
- `memory_events` (eventos temporais V4.1)

Cada query de dados inclui `WHERE owner_id = ?` com o uid do usuário autenticado.

## RBAC (Roles)

### ADMIN
- Consultar usuários
- Criar usuários (`criar_usuario`)
- Alterar papel (`definir_papel`)
- Alterar status (`definir_status`)
- Revogar sessões (`revogar_sessao`, `revogar_sessoes`)
- Gerenciar convites (`gerar_convite`, `revogar_convite`)
- Aprovar/recusar (`decidir_pedido`)
- Alterar limites (`update_limits`)
- Configurar modo de cadastro (`config_set`)
- Auditar eventos
- Excluir conta (com proteção de último admin)

### USER
- Utilizar próprio chat
- Acessar próprias conversas/memórias
- Alterar senha (`trocar_senha`)
- Gerenciar configurações pessoais
- Utilizar ferramentas autorizadas

## Proteções de Segurança

| Ameaça                    | Proteção                                      |
|---------------------------|-----------------------------------------------|
| owner_id falsificado      | Identidade vem do sistema de auth, não do cliente |
| Acesso a dados de outro   | Todas as queries filtram por `owner_id`       |
| Escalação de privilégios  | `criar_usuario` nunca atribui admin via público |
| Último admin removido     | `definir_papel`/`excluir_usuario` rejeitam    |
| Self-alteração            | Bloqueio explícito (`alvo_uid == ator_uid`)   |
| Convite reutilizado       | Consumo atômico (transação)                   |
| Brute force (login)       | 5 / 5 min por IP+username (memória relay)     |
| Brute force (registro)    | 3 / hora por IP                                |
| Senha fraca               | `valida_senha`: 8–128 chars                    |
| Username inválido         | `valida_username`: 3–30, `[a-z0-9._-]`         |
| SQL injection             | Todas as queries usam parameterized `?`       |
| Path traversal            | `agent_path` validado com `is_file()`          |
| SSRF (relay)              | `validar_relay_url`: http(s)://, localhost HTTP→HTTPS |

## Sessões

- `user_sessions`: sid (PK), uid, created_at, expira_em, revogada (0/1).
- `criar_sessao(db, uid)`: gera sid seguro, expira em 12h.
- Relay mantém cache de revogados (TTL 60s) com fallback para agentes
  antigos (2 timeouts → para de perguntar, sem stall).
- `sessao_valida(db, sid)`: retorna dados do usuário ou None (se revogada/expirada).
- `revogar_sessao/sessoes`: marca como revogada (não deleta — preserva auditoria).
- Sessões não revogadas expiram automaticamente por `expira_em`.

## Offline-First

- IndexedDB no browser cache por usuário.
- Cadastro/login requer PC online (SQLite definitivo).
- Sessões expiram localmente mesmo offline (validação por timestamp).
- Mensagens não sinc hoje ficam na fila IndexedDB até reconexão.
- **Nunca** sincronizar dados de uma identidade não validada para outra conta.

## Convites

- Código seguro via `secrets.token_urlsafe(12)`.
- Armazenado como **hash** (`code_hash = sha256(codigo)`).
- Expiração por dias, limite de usos (`max_usos`).
- Consumo atômico em transação (`consumir_convite`).
- Revogação imediata (`revogar_convite`).
- Código só exibido UMA VEZ na criação.

## Auditoria

- `auditar(db, ator, acao, alvo, detalhe)` registra em `audit_log`.
- Eventos: `usuario_criado`, `papel_alterado`, `bloqueado`, `desbloqueado`,
  `sessao_criada`, `sessao_revogada`, `convite_criado`, `convite_revogado`,
  `pedido_decidido`, `usuario_excluido`, `config_alterada`, `senha_trocada`.
- **Nunca** registra conteúdo de conversas, senhas ou tokens.
