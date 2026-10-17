# Continuidade de conversa — 17/10/2026

## Escopo implementado

- Clima: `E amanhã?`, `Vai chover?`, `E depois de amanhã?` e `E no fim de semana?` reutilizam a cidade da resposta imediatamente anterior. Uma cidade explícita prevalece. Datas seguem o fuso da previsão. O fim de semana inclui sábado/domingo; no domingo, somente o dia restante. Falta de dias disponíveis é informada.
- Produtos: `outro modelo parecido com aquele e o preço` aciona nova consulta pelo pipeline existente, preservando categoria, marca, orçamento e especificações. Restrições explícitas novas substituem as anteriores. O cache de resultados comerciais é ignorado e a consulta lê no máximo três páginas de produtos.
- Com vários produtos, solicita referência por nome ou posição. A resposta à clarificação preserva alterações de orçamento feitas no pedido original. O modelo de referência é excluído por ID, nome ou modelo disponível.
- Sem referência estruturada suficiente, pede identificação; não inventa o produto. Similaridade por critérios não garante equivalência de desempenho ou compatibilidade.
- Contexto limitado à conta e conversa, sem gravar nova memória permanente. Integração nos caminhos de resposta completa e streaming existentes.

## Bug adicional corrigido

A limpeza de `shopping_consultas` usava `DELETE ... id NOT IN (subconsulta da conversa)`, podendo remover consultas de outras contas/conversas. O DELETE agora aplica os mesmos filtros de proprietário e conversa. Teste cobre retenção de dados alheios e limite do histórico local. Dados já removidos antes desta correção não são recuperados automaticamente.

## Arquivos desta entrega

- `conversation_followups.py`: resolução contextual explícita.
- `pc_agent.py`: integração antes dos roteadores existentes, em `cmd_dados_atuais`.
- `shopping.py`: critérios herdados, opção de ignorar cache e limpeza isolada.
- `live_data.py`: seleção de dias e aviso de disponibilidade parcial.
- `tests/test_conversation_followups.py`: contexto, ambiguidades, seleção, critérios, datas, isolamento e persistência/SSE.
- `tools/qa-followups.cjs`: navegador real em preview descartável.
- `qa-artifacts/followups/results.json` e `weather-mobile.png`: evidências de navegador.
- `qa-artifacts/followups-tests.txt`: saída da suíte completa.

## Verificações executadas

- Testes focados finais: **42 passed** (`test_conversation_followups.py` e `test_live_data.py`). Preços/produtos desses testes são fixtures sintéticas, não ofertas comerciais.
- Suíte completa do workspace: **663 passed, 4 skipped, 1 failed**, 147,58 s. Executada antes do último ajuste de seleção `quero o 2`, coberto posteriormente pelos testes focados.
- Falha: `test_model3d_v56.py::test_v56_fluxo_de_dispositivo_continuacoes_e_isolamento`, linha 297: `cmd_model3d(..., 'Amplie.', outro_dono, ...)` retorna `None`, mas o teste exige resposta textual. Reproduzida isoladamente. O teste chama diretamente o roteador 3D, não o novo resolvedor. Arquivos 3D mudaram durante esta execução e foram preservados.
- Pulados: dois exigem inferência Hermes real; dois dependem de buscas comerciais externas (DDG sem resultados/bot-wall e Mercado Livre HTTP 403). Não há confirmação E2E de preço comercial nesta entrega.
- Chrome instalado, headless, viewport 390×844: login, menu mobile, nova conversa, clima em Salvador, `E amanhã?`, `E no fim de semana?`, tabelas, links, recarregamento e três respostas persistidas. API Open-Meteo real, sem mocks; nenhum erro JavaScript nem overflow horizontal. Tempos nesta execução: 3.943 ms, 1.167 ms e 128 ms (cache meteorológico existente). Não representam garantia de latência.
- Screenshot inspecionada: conteúdo legível e tabela contida; datas/células podem quebrar linha na largura mobile. Não houve teste em aparelho físico.
- Roteiro inicial de navegador tentou usar botão desktop oculto; foi corrigido para abrir o menu mobile e aguardar seu fechamento automático, sem forçar cliques.
- `git diff --check` dos arquivos de produção desta mudança passou. A checagem geral também encontrou uma linha vazia final em teste 3D alterado paralelamente; não foi sobrescrita.

## Limites e próximos passos

Não é uma resolução semântica universal: cobre continuações explícitas de clima e consultas estruturadas de produtos. Pesquisas livres sem produto estruturado podem precisar do nome do modelo. Fontes comerciais continuam sujeitas a indisponibilidade/bloqueios, e especificações ausentes limitam comparação e identificação de variantes. A resposta não fabrica preço quando a fonte não o confirma.

Sem push/deploy, mudança de credenciais, alteração de identidade, migração de dados reais ou controle remoto. Preview usa banco temporário. O processo já aberto do usuário não foi reiniciado: reiniciar o agente normalmente é necessário para carregar o novo código.
