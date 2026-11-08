# Auditoria operacional — 05/11/2026

Pedido: reiniciar o Agent, auditar o sistema com testes de código e uso real, criar cobertura útil e propor refatorações, principalmente da pesquisa. Não executar uma refatoração ampla nesta auditoria.

## Baseline e proteção do trabalho

- Publicado: `origin/main` = `57487fbfc89dea12ee74b909fa192e7c289d5388`.
- Checkout principal: `624068e`, com 35 arquivos rastreados previamente modificados; preservados. Não atualizar esse checkout sobre o trabalho pendente.
- Baseline exportado para diretório privado isolado, sem `.env` e sem dados reais.
- Agent anterior: PID 9552, checkout antigo `e91fc2e`, com alteração local. Parada graciosa via IPC autenticado, sem kill forçado.
- Agent reiniciado: PID 23260, checkout limpo publicado `57487fb`; relay conectado. Banco íntegro, 335 mensagens antes/depois. Backup privado e recibo operacional fora do Git.

## Verificações realizadas

| Camada | Critério |
|---|---|
| Código | Rotas, autenticação, isolamento, contratos, limites, concorrência e persistência |
| Suíte | Resultado terminal do baseline completo; novos testes reproduzindo riscos reais |
| Pesquisa | Descoberta, leitura, síntese e apresentação avaliadas separadamente |
| UI real | Conversa, projetos, pesquisa, cards, reload, mobile, documentos e estados de erro |
| PC | Estado, busca local e permissões sem ampliar acesso real |

## Resultado desta rodada

- Sessão expirada do site deixa histórico no DOM atrás do login; investigar isolamento e acessibilidade.
- Vexx PC 1.4.0 instalado mostra `OperationalError` no índice; busca retorna mensagem de timeout. Investigar erro original e distinguir timeout de falha SQLite.
- Suíte do baseline publicado: 2.755 passaram, 4 pulados, 2 avisos (587,01 s).
- Dez contratos novos executados: 3 passaram, 7 falharam, sem xfail ou skips. Erros preservados e relacionados ao relatório.
- Testes reais de projetos, organização mobile, compras, comparação, notícias, duas pesquisas técnicas, upload e resposta sobre documento. Inspeção de memória, provedores, Meu PC e Vexx PC instalado.
- Treze scripts passaram na sintaxe JavaScript; harness remoto mobile/desktop passou. Não é validação de gestos em celular físico.
- O usuário informou login. Ao selecionar o Brave, a ferramenta interrompeu o controle porque não conseguiu confirmar a URL com segurança. Produção autenticada não foi validada; não contornar esse bloqueio.
- Laboratório local encerrado graciosamente, dados preservados. Agent de produção PID 23260 continua RUNNING.
- Hashes finais confirmam os 35 arquivos anteriores intactos. Sem push/deploy ou mudança do código de aplicação.

Relatório e plano: `RELATORIO_AUDITORIA_SISTEMA_2026-11-05.md`. Contratos: `tools/audit_cases/contracts_20261105.py`. Evidências sintéticas: `qa-artifacts/system-audit-20261105/`.

## Próximos passos

Retomada concluída na aba de produção após login do usuário, a partir das 16:08 BRT. Horário, seis ofertas e três fontes de notícias funcionaram e persistiram após reload. Comparar falhou; pesquisa SQLite teve zero páginas; síntese Python falhou primeiro por modelo removido e depois por timeout com modelo atual. Leitura com URL explícita exibiu dialeto interno Longcat e sugestão de memória indevida. Nenhuma chamada de ferramenta do modelo foi executada.

Novos achados A16–A18 e etapa 0 adicionados ao relatório. Doze contratos executados: 3 passaram e 9 falharam, sem mascaramento. Modelo desta aba selecionado pela UI para `meituan/longcat-2.5:free`; preferência dos demais aparelhos não foi alterada. Agent 23260 segue RUNNING; 35 hashes anteriores preservados; sem push ou mudança do código da aplicação.

Próximo passo exato: corrigir validação de modelo antes do envio, filtro de dialetos de ferramentas e perda de passagem do documento; depois comparação/contexto e demais contratos. Repetir a bateria de produção após correções. A/B/C continuam não aprovados em conjunto. Não repetir a suíte do baseline sem mudança ou preocupação nova que justifique.
