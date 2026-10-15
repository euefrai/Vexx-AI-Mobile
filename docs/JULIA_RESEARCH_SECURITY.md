# JÚLIA Research Security (V4.4)

Modelo de ameaça: conteúdo externo é **dado**, nunca instrução; rede é
hostil; um dono nunca alcança dados de outro.

## Controles implementados (todos com teste)

| Ameaça | Controle |
|---|---|
| SSRF / localhost / redes privadas / metadata | `url_segura`: scheme http/https, sem credenciais, porta válida, **resolve todos os IPs e exige `is_global`**, revalidado a **cada redirect** (≤3) |
| DNS rebinding | Revalidação por hop (janela residual documentada; sem cache DNS próprio) |
| Redirect malicioso | Handler sem redirect automático + revalidação + teto |
| HTML perigoso / prompt injection | Parser próprio (sem script/style), texto puro; wrapper anti-instrução no prompt; sem execução de JS |
| URLs maliciosas / executáveis | Bloqueio por extensão + Content-Type textual obrigatório |
| Docs gigantes / lentidão | Content-Length + leitura capada em 2 MB; timeouts 6–12 s; orçamentos por modo |
| Vazamento entre usuários | Cache e runs com `owner_id`; consultas nunca incluem valores de memória |
| Memória em busca externa | Só termos de tópico com gatilho explícito; valores/dados pessoais nunca enviados |
| Citação forjada | `validar_citacoes`; modelo só recebe IDs existentes |
| Resultados imutáveis | Transforms não tocam tentativas; runs são append-only |

## Residuais (declarados)

- Janela TOCTOU DNS entre validar e conectar (stdlib, sem pin de IP).
- `update_of`/fences externos seguem validação JDUI existente.
- Status operacional ao vivo ("Pesquisando…") AUSENTE: o texto do stream é
  canônico; progresso falso seria desonesto.
- Provedor único (DuckDuckGo, grátis, sem chave); queda = pesquisa degradada
  com mensagem honesta, nunca fontes inventadas.
