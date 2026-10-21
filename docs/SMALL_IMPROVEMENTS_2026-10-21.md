# Melhorias pequenas — 21/10/2026

Base local da primeira rodada: `438f048` (inclui a V5.8 ainda local). A primeira rodada foi concluída sem publicação; o envio conjunto foi autorizado na segunda rodada.

## Alterações

- **Copiar mensagens e código:** busca direta por ID no IndexedDB, sem carregar todo o
  histórico; verificação do dono; método alternativo quando Clipboard API está ausente
  ou recusa a operação; feedback explícito de falha. Código copiado preserva espaços e
  quebras de linha. O método alternativo restaura foco e seleção do rascunho e remove seu
  campo temporário. A área de transferência real do sistema não foi alterada pelos testes.
- **Seleção de modelo:** POST aceita `~` no ID, assim como o agente já aceitava. Espaços,
  quebras de linha e marcação continuam recusados.
- **Links de pesquisa:** portas textuais, negativas, zero ou acima de 65535 geram erro
  controlado antes de consultar DNS. Portas válidas continuam exigindo host público.
- Service worker atualizado para entregar a nova versão do frontend.

Arquivos: `public/app.js`, `public/sw.js`, `server.py`, `research.py` e
`tests/test_small_improvements.py`.

## Validação

- 18 testes focados passaram.
- Suíte completa: **960 passaram, 4 pulados, 2 avisos**, em 85,28 s. Os skips dependem
  de inferência/provedores externos; avisos de depreciação já existentes.
- Chrome com aplicação servida e IndexedDB real em preview descartável: nove cenários
  de cópia passaram, sem erros de página. Clipboard API e retorno de `execCommand`
  foram simulados para não sobrescrever o clipboard do usuário. Não comprova suporte
  a clipboard em todos os aparelhos; sem testes em Android/iOS físicos.
- O primeiro teste detectou perda de seleção após a cópia alternativa; a ordem de
  restauração foi corrigida e o teste reexecutado com sucesso.
- `node --check` em app/service worker e `git diff --check`: aprovados.

Evidências: `qa-artifacts/small-improvements-20261021/` contém logs e o script do Chrome.
Dados, credenciais e permissões remotas reais preservados.


## Segunda rodada e pacote de publicação

- Limpar o cache cancela o timer JDUI, limpa gravações pendentes e invalida contextos
  antigos. Leituras e gravações já iniciadas não restauram o cache nem reagendam sync.
  Novos componentes continuam salvando normalmente.
- A API valida e normaliza datas de estados interativos antes de enviar ao PC.
  Datas inválidas ou sem fuso recebem 422; timestamps equivalentes convergem em UTC.
- Excluir conversa adquire a transação de escrita antes de ler os metadados, impedindo
  que uma renomeação concorrente invalide a exclusão. Testado com duas conexões SQLite.

Validação: 27 testes focados e 12 cenários no Chrome passaram. Suíte completa da
**cópia exata de publicação: 949 passed, 4 skipped, 2 warnings, 89,24 s**.
A contagem difere dos 960 da primeira rodada porque o pacote de publicação parte de
`origin/main` (`9822636`) e não inclui a V5.8 local. Nenhum teste foi removido.
Log: `qa-artifacts/small-improvements-20261021/release-suite.txt`.

Inclui as duas rodadas de melhorias, sem os commits da V5.8. Não foram executados
comandos de deploy nem alteradas credenciais ou dados de produção.
