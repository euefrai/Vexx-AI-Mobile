# JÚLIA Evidence Inspector (V4.6)

Inspeção sem sair do chat, Minimal Premium, nada permanente:

- **Cards de evidências** (`fence_de_evidencias`, componente `cards`):
  título, trecho, status, link "Abrir ↗" para o documento original.
- **Grafo interativo** (componente `evidencegraph`): camadas
  afirmação→evidência→fonte, zoom, filtro por tipo, seleção com detalhes
  (estado, trecho). Contradições em vermelho, suportes em verde. Teto de
  30 nós (mobile).
- **Painel Live** (§11 V4.5): fontes com links reais durante a execução.
- Comandos de memória: "de onde veio", "quem confirma", "alguma fonte
  contradiz", "o que mudou", "estudo original".

Sem âncora exata quando a localização do trecho é desconhecida (o card
mostra o trecho, não finge scroll). Popovers globais no markdown: AUSENTE
(exigiria cirurgia no renderer; cards + grafo cobrem o caso de uso).
