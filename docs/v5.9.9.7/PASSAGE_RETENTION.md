# Retenção de passagens

Bug reproduzido: seleção padrão de três passagens perdia a quarta faceta disjunta. O padrão agora considera requisitos com passagens e varia de três até oito; limite explícito continua respeitado. Teste exige os quatro vínculos, não apenas contagem de objetos.

`web_extract.passage_candidates` preserva seção literal somente quando heading e corpo existem juntos no texto extraído. Retorno “The target object.” sob “Return value” em página titulada Object.assign pode dar suporte **parcial**, nunca direto pelo título. Método diferente e linguagem incerta não são promovidos. Aspas são substrings reais do conteúdo; não se inventa contexto na citação.

Replay de texto já extraído: sintaxe permaneceu SUPPORTED, retorno DISCOVERED → PARTIALLY_SUPPORTED, comportamento continuou DISCOVERED. Isso demonstra retenção limitada, não resposta completa. A queda de três para duas linhas de evidência não é por si ganho nem perda factual; aliases e concorrência afetam linhas. O replay HTML público semeado manteve apenas sintaxe SUPPORTED, sem ganho nas outras facetas. Portanto não demonstramos recuperação integral de seções no extrator real.

Fontes duplicadas preservam referências e passagens; evidências reusadas unem Q/R. Limites existentes da persistência de evidência permanecem. Próximo diagnóstico deve comparar extração literal, identidade da entidade e faceta sem usar o conjunto externo como alvo de ajustes.
