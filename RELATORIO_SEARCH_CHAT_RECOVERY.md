# Recuperação da pesquisa no chat — 28/10/2026

## Resultado e escopo

Corrigidos erros reproduzidos a partir dos três pedidos das capturas: encaminhamento indevido para galeria, busca não iniciada, consulta mal formada, filtros comerciais falsos e fontes recuperadas ocultadas no resultado. A busca geral, o shopping e o comando de pesquisa profunda são rotas distintas; as capturas não demonstravam falha de todo o motor de jobs. Esta entrega não comprova pesquisa universal completa.

## Causas e correções

1. `pesquisa por Minecraft` não ativava `intencao_pesquisa`. Agora pedidos com `pesquisa por`, `pesquisa sobre` e `pesquisa profunda` ativam o fluxo existente. A limpeza conservadora retira também a preposição do prefixo; `por Minecraft` deixava de encontrar o assunto no teste real.
2. `placas de videos` era interceptado como pedido de vídeos antes do shopping. Detecção de mídia agora distingue o nome do hardware de um pedido de fotos/vídeos. Fotos de placas e vídeos sobre placas continuam sendo mídia; PDFs/documentos continuam disponíveis no anexo da pesquisa.
3. `algumas` continha `lg` e ativava um filtro obrigatório pela marca LG. Identificação de marcas agora exige limites de palavra, usando a regra já existente no módulo.
4. O pedido de 6 de VRAM não chegava aos critérios e às consultas. VRAM agora tem filtro próprio em GB, separado de RAM e armazenamento; capacidade divergente é separada, capacidade ausente fica pendente. A categoria do hardware é preservada no plural; notebook com GPU não é placa avulsa.
5. O título `Fontes` escrito pelo modelo suprimia o card de fontes reais. Finalização de pesquisa agora anexa registros recuperados independentemente desse título. Uma segunda finalização substitui o card, sem duplicá-lo.
6. Pedidos gerais de ofertas na Steam podem usar o catálogo público da própria Steam (BR/BRL), com cache de 60 segundos, no máximo seis destaques, links de app, rejeição de preços inválidos, moeda divergente e descontos vencidos. Não há consulta de conta, carrinho ou compra. Pedidos com gênero, jogo, preço máximo ou outras condições seguem pela pesquisa normal; o catálogo genérico não descarta esses requisitos.
7. A consulta real de GPUs revelou catálogos da Terabyte e NVIDIA apresentados como referências de produto. Um filtro específico de destinos comerciais agora rejeita esses caminhos, também no JDUI. Essas URLs continuam válidas como fontes gerais de pesquisa. Não se declara uma página individual aberta apenas porque o catálogo informa seu ID.

## Evidência real

Smoke executado com rede pública e SQLite temporário, sem conta autenticada de produção:

- Minecraft: pesquisa executada, três fontes encaminhadas ao modelo `poolside/laguna-s-2.1:free`, card `sources`, persistência/replay idênticos, 16,22 s no smoke final. O modelo tentou emitir chamada de ferramenta textual; a proteção existente descartou essa redação e preservou um resumo determinístico com fontes. Portanto, este caso comprova recuperação e entrega de fontes, não síntese completa de todas as informações sobre Minecraft. Os trechos recuperados da página inicial eram promocionais e ainda têm qualidade limitada para uma visão enciclopédica.
- Steam: seis ofertas atuais declaradas no catálogo, card `productgrid`, preços BRL, links individuais e replay idêntico; 0,27 s na execução registrada. Tempo pontual, não benchmark. Links individuais não foram abertos: selo parcial, estoque desconhecido e aviso para conferir no checkout.
- GPUs: consulta comercial real executada. Mercado Livre/loja recusaram acesso automático e o buscador trouxe conteúdo insuficiente. Não houve oferta confirmada. O teste mostrou a diferença entre bug interno corrigido e bloqueio externo persistente. Nenhum CAPTCHA foi contornado, nenhum preço foi estimado.

Artefato resumido: `qa-artifacts/search-chat-recovery-assessment.json`. Capturas completas e logs dos probes permanecem locais em `qa-artifacts/search-chat-*.json/log`.

## Testes

- Primeiro conjunto: 126 aprovações e uma falha no teste novo de leitura da estrutura JDUI; ajustada a leitura do envelope retornado por `normalizar`.
- Em seguida, o teste de GPU reproduziu o filtro falso de LG. Corrigida a causa no extrator de critérios.
- Focados de critérios/rotas/shopping: 146 passed, 2 skipped.
- Fontes e cards: 85 passed.
- Focados finais de links/catálogos/JDUI/shopping: 133 passed.
- Suíte da revisão anterior ao último filtro de catálogos: 1.934 passed, 4 skipped; não representa a revisão final.
- Suíte final: **1.936 passed, 4 skipped, 2 warnings**, 169,47 s, exit 0. Log: `qa-artifacts/search-chat-release-full.log`; avisos existentes de mss/TestClient.
- `node --check public/jdui.js` e `git diff --check`: aprovados. Validação Node executou o JDUI real e confirmou catálogos bloqueados em productcard e preservados em sources.

## Reinício solicitado

Antes da implementação, agente atualizado para a versão já publicada `265844c` e reiniciado por IPC autenticado, sem encerramento forçado. PID 12164 passou a 31528, supervisor preservado, runtime RUNNING e log de conexão ao relay confirmado. Backup e quick_check do banco realizados; 307 mensagens antes/depois, nenhum job ativo no momento do reinício. Configuração/credenciais permaneceram em diretório privado.

As novas correções desta entrega são locais e ainda precisam de publicação e atualização do agente para chegar ao site. O reinício acima não significa que o processo já tenha carregado código editado posteriormente.

## Limitações e próximos passos precisos

- A busca de ofertas de GPU não está resolvida em condições reais: provedores bloqueados e ausência de fontes de item legíveis. Falta integrar/configurar um provedor comercial acessível ou uma busca web de qualidade, mantendo validação por variante e leitura da página.
- O catálogo Steam é uma amostra pública; não cobre toda promoção nem filtros específicos. Preços regionais declarados não garantem checkout/estoque e não há garantia de estabilidade do endpoint público.
- Conteúdo relevante ainda pode ficar fora dos limites de extração; encontrar e ler uma página não prova que ela responde a todas as partes do pedido.
- Falhas/redações inadequadas do modelo continuam possíveis. O fallback mostra evidências recuperadas, mas não equivale a uma síntese factual completa.
- Não houve smoke autenticado no Render, teste visual em navegador, celular físico ou nova avaliação universal de jobs profundos nesta entrega. Não se declara que qualquer pergunta passará a ter resposta completa.

Arquivos: `pc_agent.py`, `query_intelligence.py`, `research.py`, `shopping.py`, `source_check.py`, `live_data.py`, `steam_offers.py`, `public/jdui.js`, `public/sw.js`, `tests/test_search_chat_recovery.py`, `tools/probe_search_chat_recovery.py`, relatório e artefato resumido.
