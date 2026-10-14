# Júlia Mobile — Assistente pessoal offline-first

Chat mobile com arquitetura offline-first, sincronização SQLite, comunicação com
agente desktop e futura integração com IA e controle remoto.

## Objetivo

Permitir conversar pelo celular com a Júlia: as mensagens ficam salvas no aparelho
(IndexedDB), sincronizam com o SQLite do computador quando ele está online e o
servidor no Render atua apenas como interface, autenticação e intermediação segura —
sem banco de dados na nuvem.

## Funcionalidades

FUNCIONAL:

- Chat mobile com cache offline (IndexedDB) e status por mensagem.
- Sincronização idempotente com o SQLite do computador (sem duplicatas em retry).
- Banco SQLite durável no PC (WAL, transações, filtro por origem).
- Autenticação com usuário/senha (Argon2id), sessão HttpOnly + CSRF.
- Comunicação segura com o agente desktop (WSS de saída, sem abrir portas).
- PWA instalável com shell cacheado.

AINDA NÃO IMPLEMENTADO:

- Memória/skills nativas do Hermes Agent (o proxy é só inferência).
- Vídeo fluido/WebRTC (a tela ao vivo é polling ~2 fps).

PENDÊNCIAS CONHECIDAS:

- Revogação server-side das sessões.
- Rate limit compartilhado entre processos (hoje é em memória).
- Backoff exponencial de sincronização (hoje é polling de 12 s).
- Criptografia dos dados locais / PIN offline.
- Integração com o banco real da extensão.
- Deploy real no Render (ainda não executado).
- Testes em dispositivos físicos.

## Arquitetura

```text
Celular/PWA  →  IndexedDB local (mensagem pendente)
    │
    └─ PC online? → POST /api/sync autenticado
                    │
                    ▼
             Render FastAPI/WSS (sem banco)
                    │
                    ▼
             Agente Python Windows
                    │
                    ▼
             INSERT OR IGNORE → SQLite → COMMIT
                    │
                    ▼
                ACK ao Render → ACK ao celular
                    │
                    ▼
             IndexedDB marca "sincronizada"
```

O computador é a fonte definitiva dos dados. O Render não guarda conversas.
O IndexedDB é o armazenamento offline do celular.

## Tecnologias

- Backend: Python, FastAPI, Uvicorn, WebSockets, Argon2id, ItsDangerous.
- Agente: Python (`websockets`), SQLite (WAL).
- Frontend: HTML, CSS, JavaScript, PWA + IndexedDB. Sem frameworks, sem Firebase/Supabase.
- UI/UX: Tema minimalista premium (fundo #0B0B0F, roxo neon #A78BFA). Mensagens com formatação de texto enriquecida (inline code, parágrafos, quebras). Animação de digitação. Layout clean sem textos explicativos redundantes.

## Instalação local

Requisitos: Python 3.11+, `pip`, Node.js (opcional, só para checar o JS).

```bash
pip install -r requirements.txt
```

No Windows há atalhos: `iniciar-servidor.bat` (relay local) e `iniciar-agente.bat`
(agente do PC; exige `fajulto_AGENT_TOKEN`). Modelo de variáveis em `.env.example` —
copie para `.env` local e nunca commite valores reais.

## Configuração do backend

Gere um hash Argon2id para a senha (copie **o hash**, não a senha):

```bash
python -c "from argon2 import PasswordHasher; import getpass; print(PasswordHasher().hash(getpass.getpass('Senha do portal: ')))"
```

Gere dois segredos diferentes:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

| Variável | Conteúdo |
|---|---|
| `fajulto_ENV` | `production` no Render |
| `fajulto_USERNAME` | Nome de usuário escolhido |
| `fajulto_PASSWORD_HASH` | Hash Argon2id gerado acima |
| `fajulto_AGENT_TOKEN` | Segredo forte; **o mesmo no PC** |
| `fajulto_SESSION_SECRET` | Outro segredo forte (somente Render) |

Servidor local:

```bash
uvicorn server:app --host 127.0.0.1 --port 8000
```

Acesse `http://127.0.0.1:8000`, faça login e escreva uma mensagem. Sem o agente ativo,
ela aparece como *pendente*.

## Agente no computador (PowerShell)

```powershell
$env:fajulto_RELAY_URL="https://SEU-SERVICO.onrender.com"
$env:fajulto_AGENT_TOKEN="MESMO-SEGREDO-DO-RENDER"
$env:fajulto_SQLITE_PATH="$env:USERPROFILE\Documents\fajultoMobile\memory.sqlite3"
python pc_agent.py
```

Para teste local, use `http://127.0.0.1:8000` e as mesmas variáveis no servidor.
Conexão externa exige **HTTPS/WSS**; o agente bloqueia `http://` fora de localhost.
Quando aparecer **Conectado ao relay**, reabra o app ou toque em
**Ajustes → Verificar agora**.

## SQLite

Banco próprio do Mobile (`fajulto_SQLITE_PATH`), criado automaticamente com WAL,
`busy_timeout`, índice `(origin, created_at)` e `INSERT OR IGNORE` (idempotente).
Históricos mobile/externos são filtráveis por `origin`. Ainda será necessário o
bridge com a memória real da extensão — nada é gravado no SQLite dela hoje.

## Offline com IndexedDB

Toda mensagem é gravada primeiro no IndexedDB (`pending`). Reabrir o app recupera o
histórico local. Se a rede cair entre o `COMMIT` e o ACK, o retry usa o **mesmo ID**.
PC desligado → servidor responde 503 e o texto permanece no celular.

## Sincronização

Roda com o app aberto: na inicialização, na reconexão, ao voltar do segundo plano,
via polling a cada 12 s ou pelo botão **Verificar agora**. Só marca `synced` após
confirmação de gravação no SQLite. Com o navegador totalmente fechado não há sync em
segundo plano (limitação real de PWA). O cache do navegador não é criptografado nesta
versão — não compartilhe o aparelho desbloqueado.

## Tela ao vivo e controle (Meu PC)

A aba Meu PC exibe a tela real (~2 fps) e envia toque/teclado de verdade
(`GET /api/screen`, `POST /api/input`, ambos com login + CSRF). Controle
exige `fajulto_REMOTE=1` no PC — sem isso, somente visualização. Detalhes,
gestos e limites em `docs/REMOTO_ANYDESK.md`.

## Resposta da IA (Hermes Proxy local)

Com o PC online e o Hermes Proxy rodando (`hermes proxy start`, padrão
`http://127.0.0.1:8645/v1`), cada mensagem sincronizada gera uma resposta real
do modelo (`fajulto_AI_MODEL`, padrão `poolside/laguna-s-2.1:free`), exibida com
streaming progressivo no celular e persistida no SQLite (`ai_requests` +
mensagem `assistant`, idempotente por mensagem).

- `GET /api/ai/models` lista os modelos reais do proxy para o seletor do app.
- `POST /api/ai` devolve a resposta completa; `GET /api/ai/stream` faz SSE com
  deltas; fechar a conexão cancela (parcial preservada, sem retry automático).
- Sem Hermes: a mensagem fica guardada e o app oferece tentar de novo.
- O celular nunca fala com o proxy; o proxy nunca recebe tokens do Render.

## Testes automatizados

```bash
pip install pytest httpx
pytest -q tests
node --check public/app.js
```

9 testes: autenticação, CSRF/origem, brute-force (429 após 5 tentativas), validação de
payloads (422), SQLite idempotente, texto adversarial (XSS/SQLi) armazenado com
segurança, período offline, handshake do agente, ACK via WebSocket e sync duplicado
concorrente. +9 de IA: bridge/SSRF/SSE, idempotência sem rechamada, auth e roteamento
de stream no relay, e E2E com processos reais (relay + agente + Hermes falso).
O CI (GitHub Actions) repete pytest + checagem do JS a cada push.

## Limitações atuais

- Sem resposta da IA com PC offline ou Hermes parado: a mensagem fica guardada e
  o app oferece tentar de novo (sem duplicar a inferência).
- Controle remoto é simulação visual com avisos explícitos na interface.
- Um PC pareado e um usuário; sem tela de cadastro.
- Login depende do Render estar disponível; reabrir a PWA totalmente offline não
  permite novo login (PIN local planejado).
- Render Free pode hibernar; agente e celular reconectam sozinhos.

## Roadmap

1. Bridge extensão Júlia → agente (respostas, memória, roteamento `mobile`/`extension`).
2. Fallback de IA em nuvem com PC desligado (chave só no backend).
3. Controle remoto real (WebRTC, STUN/TURN, consentimento).
4. Criptografia local, PIN offline, backup e monitoramento da PWA.

## Modo direto via Tailscale (recomendado — sem Render, sem Cloudflare)

Se o relay na nuvem der dor de cabeça (bloqueio anti-robô, hibernação),
rode tudo em casa numa rede privada:

1. Instale o **Tailscale** no PC e no celular (plano pessoal gratuito) com a
   mesma conta, e ative o HTTPS dele no PC (`tailscale cert`).
2. No PC, inicie o relay ouvindo a rede: `iniciar-servidor.bat 0.0.0.0`
   (libere a porta 8000 no firewall do Windows se pedir).
3. No PC, aponte o agente para ele mesmo:
   `set fajulto_RELAY_URL=http://127.0.0.1:8000` + `iniciar-agente.bat`.
4. No celular (com Tailscale ativo), abra
   `https://SEU-PC.sua-rede.ts.net:8000` — PWA completa, mesmo app.

Só funciona com o PC ligado (honesto: sem PC não há IA nem banco).
O modo Render continua disponível como alternativa.

## Deploy no Render (preparação)

1. Conecte este repositório (privado) via **New → Blueprint** (`render.yaml`) ou Web
   Service com build `pip install -r requirements.txt` e start
   `uvicorn server:app --host 0.0.0.0 --port $PORT --proxy-headers`.
2. Configure os 4 segredos no Environment. `fajulto_SESSION_SECRET` nunca vai para o PC.
3. Serviço deve ser **Web Service** (HTTP+WebSocket), não Static Site.
4. Deploy real ainda não executado: validar WSS, hibernação do plano Free e health
   checks em produção após a primeira publicação.
