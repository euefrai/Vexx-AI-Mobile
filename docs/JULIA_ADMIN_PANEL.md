# JÚLIA MOBILE 4.1.5 — Painel Administrativo

## Localização

O painel administrativo está integrado ao **FAJULTO Studio**
(`C:\Users\efrai\FAJULTO-2.0.0\FAJULTO\studio\controle.py`),
como um **card adicional** na página principal.

A lógica reside em:
`studio/integracoes/FAJULTO_mobile.py` → classe `GerenciadorFAJULTOMobile`.

## Arquitetura de Integração

```
FAJULTO Studio (browser) ──HTTP──► controle.py (do_POST)
                                    │
                                    ├─ /api/controle/FAJULTO/admin/*
                                    │
                                    └─ _FAJULTO() ──► GerenciadorFAJULTOMobile
                                                       │
                                                       ├─ _open_admin_db()
                                                       │     └─ import FAJULTO_auth
                                                       │     └─ sqlite3.connect(sqlite_path)
                                                       │     └─ criar_tabelas() + migrar_legado()
                                                       │
                                                       └─ chamadas FAJULTO_auth.* (reutilizáveis)
```

## Endpoints de API

| Rota                                        | Método | Ação                                  |
|---------------------------------------------|--------|---------------------------------------|
| `/api/controle/FAJULTO/admin/status`          | GET    | Visão geral (counts, estado, modo)    |
| `/api/controle/FAJULTO/admin/users`           | GET    | Lista de usuários                     |
| `/api/controle/FAJULTO/admin/users/create`    | POST   | Criar usuário (admin)                 |
| `/api/controle/FAJULTO/admin/users/role`      | POST   | Alterar papel                         |
| `/api/controle/FAJULTO/admin/users/status`    | POST   | Bloquear/desbloquear                  |
| `/api/controle/FAJULTO/admin/users/sessions`  | POST   | Revogar todas as sessões              |
| `/api/controle/FAJULTO/admin/users/limits`    | POST   | Atualizar limites                     |
| `/api/controle/FAJULTO/admin/users/delete`    | POST   | Excluir conta                         |
| `/api/controle/FAJULTO/admin/invites`         | GET    | Listar convites                       |
| `/api/controle/FAJULTO/admin/invites/create`  | POST   | Gerar novo convite                    |
| `/api/controle/FAJULTO/admin/invites/revoke`  | POST   | Revogar convite                       |
| `/api/controle/FAJULTO/admin/regs`            | GET    | Listar pedidos pendentes              |
| `/api/controle/FAJULTO/admin/regs/decide`     | POST   | Aprovar/recusar                       |
| `/api/controle/FAJULTO/admin/config`          | GET    | Obter config de cadastro              |
| `/api/controle/FAJULTO/admin/config/set`      | POST   | Alterar modo / exigir aprovação       |
| `/api/controle/FAJULTO/admin/audit`           | POST   | Últimos eventos de auditoria          |

## Componentes do Painel

### Visão Geral
- Total / ativos / bloqueados / pendentes / admins / convites ativos.
- Estado do agente (online/offline via `GerenciadorFAJULTOMobile.status()`).
- Modo de cadastro + checkbox "exigir aprovação".

### Gerenciar Usuários
- Tabela: ID, exibição, username, papel, status, ações.
- Papel e status editáveis inline (select).
- Botões: revogar sessões, excluir (com confirmação).
- Proteção: não permite excluir/rebaixar o último admin ativo.

### Bootstrap do proprietário
- Rota `/api/controle/FAJULTO/admin/bootstrap` + formulário "Vincular proprietário"
  (visível só enquanto `vinculado=false`): username do Render + nome + senha.
- Sem senha padrão; senha nunca retorna na resposta; auditoria registra o vínculo.
- Repetir atualiza a credencial sem duplicar a conta.

### Criar Usuário
- Formulário via `prompt()`: exibição, username, senha, papel.
- Credencial inicial definida pelo admin (hash **scrypt**, nunca texto puro).

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

- Acesso localhost-only (FAJULTO Studio roda localmente); esse é o modelo de
  autorização do painel, consistente com os demais botões destrutivos do
  controle (matar PID etc.). Ator registrado como `studio-local`.
- Interpolação do frontend escapada (`escA`) — display names não executam HTML.
- Operador nunca é `local`: travas de auto-operação funcionam ao mirar a
  conta do proprietário.
- Autorização validada no backend (`FAJULTO_auth.definir_papel`,
  `excluir_usuario`, etc. rejeitam ações não autorizadas).
- Todos os eventos admin auditados (`FAJULTO_auth.auditar`).
- Códigos de convite armazenados como hash (`code_hash`).
- `criar_usuario` nunca atribui papel `admin` via registro público.
