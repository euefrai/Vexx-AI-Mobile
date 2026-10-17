# Provedores de LLM e de busca (configuração no PC)

Tudo abaixo é configurado **no PC**: variáveis de ambiente **ou** um arquivo
`.env` na raiz do projeto (carregado automaticamente na inicialização do
agente e do relay). Regras do `.env` (V5.4.3):

- Chave de **provedor** no `.env` (inclusive as salvas pelo app) **vence** a
  variável de sistema: é assim que salvar/trocar/remover pela interface vale
  de verdade, mesmo com um `setx` antigo no PC. Remova no app para a variável
  do sistema voltar a valer.
- Qualquer **outra** variável segue “sistema manda” (o `.env` só preenche o
  que estiver vazio/ausente).
- Valores entram expandindo `%USERPROFILE%` e afins. Nada disso vai para o
  Render, para o app ou para logs — chaves não aparecem nem em mensagens de
  erro. (Avançado: `JULIA_ENV_FILE` aponta o `.env` para outro caminho —
  usado nos testes/E2E com arquivo descartável.)

## Gerenciar chaves direto na interface (V5.4.3)

No app: menu (☰) → **Provedores de IA** (ou toque em *Conexão* no topo →
linha **Provedores**). Cada provedor mostra o estado real:

| Estado | Significado |
|---|---|
| **Sem chave** | não há chave no PC; cole uma e salve |
| **Chave OK** | chave presente e aceita na última listagem ao vivo |
| **Chave recusada no PC** | o provedor respondeu 401/403 — troque a chave |

Como funciona (sem mentir):

- A chave é enviada pelo relay autenticado **só como transporte** (sem
  persistência, sem log) e gravada pelo agente no `.env` local do PC —
  o servidor e o aplicativo **nunca guardam nem mostram de volta** (a
  resposta não devolve a chave nem fragmento; o campo é limpo após salvar).
- **Efeito imediato**: o agente aplica a chave em memória; toque no seletor
  em *Atualizar* para ver os modelos reais do provedor. Não precisa reiniciar.
- **Origem** aparece na linha: *Salva neste PC* (editável aqui, tem
  **Remover**) ou *Definida fora do app* (variável do sistema; salvar aqui
  passa a ter prioridade).
- Depois de salvar, escolha o modelo (`provedor/modelo`) no seletor — a
  próxima mensagem já usa o provedor novo.
- Validações: só provedores conhecidos; chave ASCII de 8 a 400 caracteres
  (sem espaços/quebras de linha — nada de injeção no `.env`).

## Provedores de IA (inferência)

Modelo com prefixo usa o provedor (`gemini/gemini-2.0-flash`); sem
prefixo continua no Hermes (proxy local `http://127.0.0.1:8645/v1`).

| Provedor | Variável | Modelos iniciais |
|---|---|---|
| Hermes (proxy local) | — | os do `hermes proxy` |
| OpenAI | `OPENAI_API_KEY` | gpt-4o-mini, gpt-4o |
| Google Gemini | `GEMINI_API_KEY` | gemini-2.0-flash, gemini-2.5-flash |
| Anthropic | `ANTHROPIC_API_KEY` | claude-3-5-sonnet/haiku |
| DeepSeek | `DEEPSEEK_API_KEY` | deepseek-chat, deepseek-reasoner |
| Groq | `GROQ_API_KEY` | llama-3.3-70b-versatile |
| Mistral | `MISTRAL_API_KEY` | mistral-large/small-latest |
| OpenRouter | `OPENROUTER_API_KEY` | vários (prefixo do site) |

### Como ativar uma chave (de verdade)

**Jeito fácil (no app):** menu (☰) → **Provedores de IA** → cole → *Salvar*
(veja a seção acima). 

**Pelo PC (alternativa):**

```powershell
setx OPENAI_API_KEY "sua-chave"   # ou outro provedor; sem aspas extras
```

Depois **feche e reabra o agente** (as variáveis são lidas na inicialização
do processo) — ou coloque a chave no `.env` da raiz, que é lido do mesmo
jeito. No app, toque em **Atualizar** no seletor para recarregar a lista.

Com chave, o PC tenta listar `/models` ao vivo; se a listagem falhar por
rede, cai na curadoria. Se o provedor **recusar a chave (401/403)**, o
grupo aparece como **“chave recusada no PC”** e as opções ficam
desabilitadas — sem fingir que funciona (Anthropic não tem listagem:
confira os IDs no console).

### Provar que é real (sem mentir)

```powershell
python tools\ia_smoke.py                          # 1º modelo de cada provedor com chave
python tools\ia_smoke.py openai/gpt-4o-mini       # modelo específico
```

O smoke faz uma chamada e um stream **reais**, mostra latência e texto
mínimo devolvido, e nunca imprime chaves. Se a chave estiver recusada, ele
diz o código (`auth`) em vez de inventar sucesso.

### Trocar o modelo que responde a qualquer momento

- **Chat aberto, sem recomeçar**: menu (☰) → *Conexão e memória* → **Modelo**
  → pesquise e escolha. Vale já para a **próxima mensagem**; mensagens
  antigas continuam com o modelo com que foram geradas.
- **Atalho**: toque em *Conexão* (canto superior) → linha **Modelo** abre o
  seletor direto. O rodapé mostra `IA pronta · modelo` (com aviso se o
  provedor estiver sem chave/recusado).
- **Regenerar** e **Continuar** usam o modelo **escolhido no momento do
  toque** (não o antigo).
- `JULIA_AI_FALLBACKS` aceita IDs com prefixo (`gemini/...,openai/...`):
  a fila é `[escolhido, *fallbacks]`. Se o escolhido falhar por chave
  (401/sem chave) e ainda houver candidato de **outro** provedor na fila,
  a resposta vem dele — o cartão da resposta mostra qual modelo respondeu.
  Se só restarem modelos do mesmo provedor, para (a credencial vale para
  todos eles).

## Seletor de modelo (app)

Campo de pesquisa filtra por nome ou provedor; grupos por provedor
(configurados primeiro); escolha salva por aparelho; botão **Atualizar**
recarrega catalogo/provedores sem reiniciar o app.

## Busca própria (SearXNG)

```bash
docker run -d --name searxng -p 8888:8080 searxng/searxng:latest
```

```env
JULIA_SEARXNG_URL=http://127.0.0.1:8888
```

Sem a variável, o provedor responde `indisponivel` e a cadeia segue
(DDG → Wikipedia). Instâncias públicas de terceiros **não** são usadas.
