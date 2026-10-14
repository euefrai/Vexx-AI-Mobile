# JÚLIA MOBILE 4.1.5 — Painel Administrativo

## Localização

O painel administrativo está integrado ao **Fajulto Studio**
(`C:\Users\efrai\fajulto-2.0.0\fajulto\studio\controle.py`),
como um **card adicional** na página principal.

A lógica reside em:
`studio/integracoes/fajulto_mobile.py` → classe `GerenciadorfajultoMobile`.

## Arquitetura de Integração

```
Fajulto Studio (browser) ──HTTP──► controle.py (do_POST)
                                    │
                                    ├─ /api/controle/fajulto/admin/*
                                    │
                                    └─ _fajulto() ──► GerenciadorfajultoMobile
                                                       │
                                                       ├─ _open_admin_db()
                                                       │     └─ import fajulto_auth
                                                       │     └─ sqlite3.connect(sqlite_path)
                                                       │     └─ criar_tabelas() + migrar_legado()
                                                       │
                                                       └─ chamadas fajulto_auth.* (reutilizáveis)
```

## Endpoints de API

| Rota                                        | Método | Ação                                  |
|---------------------------------------------|--------|---------------------------------------|
| `/api/controle/fajulto/admin/status`          | GET    | Visão geral (counts, estado, modo)    |
| `/api/controle/fajulto/admin/users`           | GET    | Lista de usuários                     |
| `/api/controle/fajulto/admin/users/create`    | POST   | Criar usuário (admin)                 |
| `/api/controle/fajulto/admin/users/role`      | POST   | Alterar papel                         |
| `/api/controle/fajulto/admin/users/status`    | POST   | Bloquear/desbloquear                  |
| `/api/controle/fajulto/admin/users/sessions`  | POST   | Revogar todas as sessões              |
| `/api/controle/fajulto/admin/users/limits`    | POST   | Atualizar limites                     |
| `/api/controle/fajulto/admin/users/delete`    | POST   | Excluir conta                         |
| `/api/controle/fajulto/admin/invites`         | GET    | Listar convites                       |
| `/api/controle/fajulto/admin/invites/create`  | POST   | Gerar novo convite                    |
| `/api/controle/fajulto/admin/invites/revoke`  | POST   | Revogar convite                       |
| `/api/controle/fajulto/admin/regs`            | GET    | Listar pedidos pendentes              |
| `/api/controle/fajulto/admin/regs/decide`     | POST   | Aprovar/recusar                       |
| `/api/controle/fajulto/admin/config`          | GET    | Obter config de cadastro              |
| `/api/controle/fajulto/admin/config/set`      | POST   | Alterar modo / exigir aprovação       |
| `/api/controle/fajulto/admin/audit`           | POST   | Últimos eventos de auditoria          |

## Componentes do Painel

### Visão Geral
- Total / ativos / bloqueados / pendentes / admins / convites ativos.
- Estado do agente (online/offline via `GerenciadorfajultoMobile.status()`).
- Modo de cadastro + checkbox "exigir aprovação".

### Gerenciar Usuários
- Tabela: ID, exibição, username, papel, status, ações.
- Papel e status editáveis inline (select).
- Botões: revogar sessões, excluir (com confirmação).
- Proteção: não permite excluir/rebaixar o último admin ativo.

### Bootstrap do proprietário
- Rota `/api/controle/fajulto/admin/bootstrap` + formulário "Vincular proprietário"
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

- Acesso localhost-only (Fajulto Studio roda localmente); esse é o modelo de
  autorização do painel, consistente com os demais botões destrutivos do
  controle (matar PID etc.). Ator registrado como `studio-local`.
- Interpolação do frontend escapada (`escA`) — display names não executam HTML.
- Operador nunca é `local`: travas de auto-operação funcionam ao mirar a
  conta do proprietário.
- Autorização validada no backend (`fajulto_auth.definir_papel`,
  `excluir_usuario`, etc. rejeitam ações não autorizadas).
- Todos os eventos admin auditados (`fajulto_auth.auditar`).
- Códigos de convite armazenados como hash (`code_hash`).
- `criar_usuario` nunca atribui papel `admin` via registro público.
