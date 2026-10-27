# Seleção por estrutura

web_extract._document_windows opera no texto já disponível do extrator escolhido. Alinha corpos de parágrafos, headings h1–h6, listas, tabelas por linha, código, captions e outros blocos existentes. Gaps não alinhados também são examinados, sem receber títulos ou tipos inventados. Preserva ordem de leitura na saída.

Ranking lexical localiza candidatos por faceta; não valida fatos. Heaps guardam até oito candidatos por requisito e seleção alterna requisitos com candidatos, sem preencher facetas ausentes. Saída: até oito janelas não sobrepostas, até 1.100 caracteres por trecho, total até 8.000. Não há novo download, embedding, agente, serviço ou dependência.

Limites: trabalha no melhor bloco/artigo escolhido pelo extrator, não garante varrer todo o HTML fora dele; PDFs conservam o caminho anterior. Rótulos/títulos genéricos, conteúdo fora do bloco e candidatos repetitivos podem reduzir rendimento. Não representa compreensão semântica universal. Mapa completo em TEXT_LIMIT_ANALYSIS.md.
