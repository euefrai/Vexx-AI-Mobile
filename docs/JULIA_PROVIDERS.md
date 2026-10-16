# Provedores de LLM e de busca (configuração no PC)

Tudo abaixo é configurado **no PC** (`.env` local ou variáveis de
ambiente). Nada disso vai para o Render, para o app ou para logs.

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

Com chave, o PC tenta listar `/models` ao vivo e cai na curadoria se
falhar (Anthropic não tem listagem: confira os IDs no console).
Sem chave, o provedor aparece **desabilitado** no seletor.
`JULIA_AI_FALLBACKS` aceita IDs com prefixo (`gemini/...,openai/...`).

## Seletor de modelo (app)

Campo de pesquisa filtra por nome ou provedor; grupos por provedor
(configurados primeiro); escolha salva por aparelho.

## Busca própria (SearXNG)

```bash
docker run -d --name searxng -p 8888:8080 searxng/searxng:latest
```

```env
JULIA_SEARXNG_URL=http://127.0.0.1:8888
```

Sem a variável, o provedor responde `indisponivel` e a cadeia segue
(DDG → Wikipedia). Instâncias públicas de terceiros **não** são usadas.
