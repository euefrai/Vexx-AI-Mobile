# JÚLIA MOBILE 4.1.5 — Painel Administrativo

## Localização

O painel administrativo está integrado ao **Fajulto Studio**
(`C:\Users\efrai\fajulto-2.0.0\fajulto\studio\controle.py`),
como um **card adicional** na página principal.

A lógica reside em:
`studio/integracoes/julia_mobile.py` → classe `GerenciadorJuliaMobile`.

## Arquitetura de Integração

```
Fajulto Studio (browser) ──HTTP──► controle.py (do_POST)
                                    │
                                    ├─ /api/controle/julia/admin/*
                                    │
                                    └─ _julia() ──► GerenciadorJuliaMobile
                                                       │
                                                       ├─ _open_admin_db()
                                                       │     └─ import julia_auth
                                                       │     └─ sqlite3.connect(sqlite_path)
                                                       │     └─ criar_tabelas() + migrar_legado()
                                                       │
                                                       └─ chamadas julia_auth.* (reutilizáveis)
```

## Endpoints de API

| Rota                                        | Método | Ação                                  |
|---------------------------------------------|--------|---------------------------------------|
| `/api/controle/julia/admin/status`          | GET    | Visão geral (counts, estado, modo)    |
| `/api/controle/julia/admin/users`           | GET    | Lista de usuários                     |
| `/api/controle/julia/admin/users/create`    | POST   | Criar usuário (admin)                 |
| `/api/controle/julia/admin/users/role`      | POST   | Alterar papel                         |
| `/api/controle/julia/admin/users/status`    | POST   | Bloquear/desbloquear                  |
| `/api/controle/julia/admin/users/sessions`  | POST   | Revogar todas as sessões              |
| `/api/controle/julia/admin/users/limits`    | POST   | Atualizar limites                     |
| `/api/controle/julia/admin/users/delete`    | POST   | Excluir conta                         |
| `/api/controle/julia/admin/invites`         | GET    | Listar convites                       |
| `/api/controle/julia/admin/invites/create`  | POST   | Gerar novo convite                    |
| `/api/controle/julia/admin/invites/revoke`  | POST   | Revogar convite                       |
| `/api/controle/julia/admin/regs`            | GET    | Listar pedidos pendentes              |
| `/api/controle/julia/admin/regs/decide`     | POST   | Aprovar/recusar                       |
| `/api/controle/julia/admin/config`          | GET    | Obter config de cadastro              |
| `/api/controle/julia/admin/config/set`      | POST   | Alterar modo / exigir aprovação       |
| `/api/controle/julia/admin/audit`           | POST   | Últimos eventos de auditoria          |

## Componentes do Painel

### Visão Geral
- Total / ativos / bloqueados / pendentes / admins / convites ativos.
- Estado do agente (online/offline via `GerenciadorJuliaMobile.status()`).
- Modo de cadastro + checkbox "exigir aprovação".

### Gerenciar Usuários
- Tabela: ID, exibição, username, papel, status, ações.
- Papel e status editáveis inline (select).
- Botões: revogar sessões, excluir (com confirmação).
- Proteção: não permite excluir/rebaixar o último admin ativo.

### Criar Usuário
- Formulário via `prompt()`: exibição, username, senha, papel.
- Credencial inicial gerada pelo admin (hash Argon2id).

### Convites
- Lista: ID, código (oculto — mostra ●), usos, expira, ativo.
- Criar: max_usos, dias, nota → retorna código para compartilhamento.
- Revogar individual.

### Cadastros Pendentes
- Lista: ID, username, nome, criado.
- Aprovar / recusar com confirmação.

### Logs Administrativos
- Últimos 200 eventos (audit_log).
- Mostra: timestamp, ator, ação, alvo, detalhe.
- Nunca registra conteúdo de conversas, senhas ou tokens.

## Segurança

- Acesso localhost-only (Fajulto Studio roda localmente).
- Autorização validada no backend (`julia_auth.definir_papel`,
  `excluir_usuario`, etc. rejeitam ações não autorizadas).
- Todos os eventos admin auditados (`julia_auth.auditar`).
- Códigos de convite armazenados como hash (`code_hash`).
- `criar_usuario` nunca atribui papel `admin` via registro público.
