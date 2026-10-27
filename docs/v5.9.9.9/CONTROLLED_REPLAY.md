# Replay de documentos

Base 8ccbbe0 versus correção 51b8291. Sete HTMLs públicos idênticos, SHA no corpus congelado bc3bc27. Mesma pergunta/teto de saída 8.000, mesmo extrator opcional disponível. Sem rede ou LLM no replay. Ferramenta tools/replay_document_v5999.py.

| Documento | Passagens selecionadas antes→depois | Caracteres retidos antes→depois |
|---|---|---|
| MDN assign | 3→3 | 6.978→6.978 |
| MDN hypot | 3→3 | 3.260→3.260 |
| Tramontina | 0→0 | 681→681 |
| NASA Artemis | 0→0 | 5.106→5.106 |
| SQLite WAL | 0→0 | 8.000→2.076 |
| Nikon Zf | 0→2 elegíveis | 7.998→767 |
| Yellowstone | 0→0 | 7.999→23 |

Contagem de documentos com passagem: 2→3. Quatro janelas Nikon selecionadas pelo extrator; apenas duas com suporte parcial elegível. Não confundir seleção lexical com evidência. Redução de texto SQLite/Yellowstone sem evidência não é ganho de resposta e pode limitar uso posterior; permanece limitação.

Tempo instrumentado Nikon: extração 0,231→0,248 s; pico de alocação Python 2.742.161→2.494.604 bytes. Outros casos variaram: SQLite 0,102→0,158 s; Yellowstone alocação 920.776→1.265.298 bytes. São amostras tracemalloc, sem afirmar economia global de RAM/RSS ou causalidade estatística. Saída ao redator permanece até 1.800 caracteres por fonte.

WEG/FGV/PDF sem captura HTML acessível não entram no par. Fixtures adicionais cobrem fonte sem resposta e entidade errada, com rótulo explícito. Não existem precisão/recall humanos independentes; testes negativos não provam FPR global zero.
