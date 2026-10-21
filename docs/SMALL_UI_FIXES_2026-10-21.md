# Pequenas correções de interface — 21/10/2026

## Problemas corrigidos

- **Itens salvos duplicados na tela:** renderizações simultâneas limpavam a lista antes da leitura assíncrona e depois acrescentavam os mesmos itens duas vezes. Apenas a renderização mais recente pode preencher a lista. Troca de conta e limpeza do cache também invalidam leituras pendentes. O teste inicial em Chrome reproduziu a duplicação antes da correção; nenhum registro real foi apagado.
- **Histórico mostrando uma busca anterior:** consultas e leituras dos títulos podiam terminar fora de ordem, misturando resultados. A consulta mais recente prevalece; limpar o campo, trocar de conta ou limpar o cache invalida buscas pendentes.
- **Compartilhar e copiar item salvo falhando em alguns navegadores:** esses controles exigiam a Clipboard API, apesar de já existir uma alternativa no aplicativo. Agora reutilizam `copyText`, mantendo o tratamento de falhas e sem copiar quando o usuário cancela o compartilhamento nativo.
- **Nome antigo na interface:** atividades, resultados do histórico, arquivos TXT/CSV/Markdown e impressão agora identificam o assistente como Lucas. O rodapé da exportação usa Vexx AI. Dados das mensagens, chaves de armazenamento e variáveis de ambiente foram preservados.

## Arquivos

- `public/app.js`: controles, concorrência das listas e rótulos.
- `public/sw.js`: nova versão do cache para disponibilizar o JavaScript atualizado.
- `qa-artifacts/ui-bugs-20261021/controls-check.cjs`: verificação reproduzível em Chrome com o ambiente descartável de `tests/preview_workspace.py`.
- `qa-artifacts/ui-bugs-20261021/controls-check.json`: resultados das verificações.

## Validação

- Chrome em viewport de celular (390 × 844): 17 verificações aprovadas, sem erros JavaScript capturados. Inclui botões reais de copiar/compartilhar/exportar, downloads TXT/CSV/Markdown e leituras reais de IndexedDB. Atrasos de consultas foram controlados para reproduzir concorrência.
- Regressão da rodada anterior: 12 verificações de cópia/cache/JDUI aprovadas no Chrome.
- `node --check` em `app.js` e `sw.js`; `git diff --check`: aprovados.
- Conferência estática das referências literais de ícones nos arquivos HTML/JS da pasta `public`: nenhum símbolo ausente encontrado.
- Suíte Python completa: **962 aprovados, 4 ignorados e 2 avisos**, em 122,99 segundos. Log em `qa-artifacts/ui-bugs-20261021/full-suite.txt`. Os avisos tratam da descontinuação de `mss.mss()` e do argumento `timeout` do TestClient; não foram ocultados.

## Limites

Clipboard, compartilhamento nativo e destino de impressão foram simulados; não se afirma validação dos diálogos do sistema operacional. O teste usa Chrome desktop com viewport mobile, não um aparelho físico. Não houve benchmark de LLM nem teste de serviços externos nesta rodada. Sem push ou deploy; mudanças locais de outras etapas preservadas.
