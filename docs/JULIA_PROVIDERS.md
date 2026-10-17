# Provedores de LLM e de busca (configuração no PC)

Tudo abaixo é configurado **no PC**: variáveis de ambiente **ou** um arquivo
`.env` na raiz do projeto (carregado automaticamente na inicialização do
agente e do relay; o `.env` **nunca sobrescreve** variável de ambiente já
definida, e valores entram expandindo `%USERPROFILE%` e afins). Nada disso
vai para o Render, para o app ou para logs — chaves não aparecem nem em
mensagens de erro.

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
