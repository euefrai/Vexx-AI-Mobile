# Holdout externo

Doze perguntas congeladas ANTES da otimização, commit 8a6cfcc, benchmarks/source_quality_v5998_holdout.json. Todas executadas, nenhuma pergunta alterada ou regra ajustada depois de abrir os resultados.

Tópicos: Array.from; Embraer; Revolta da Vacina; água em Vitória da Conquista; Canon R50; cópia Python; Jaguar automóveis; padStart; notebooks Acer; LGPD; visitantes do MAM; feira do livro Porto Alegre.

Resultado: **0/12 com evidência retida efetivamente lida**. O caso de notícias reteve nove referências de feed com read=false e sem passage_ids/document_id. Não contar como sucesso. Outras páginas foram tentadas e algumas extraídas, mas não produziram evidência elegível. Esquemas de requisitos ausentes ou entidades mal delimitadas também aparecem; não confundir com indisponibilidade do provedor.

external-summary.json distingue tentativas de documentos, documentos extraídos, evidência retida, evidência lida, requisitos parseados e estados. Tempos 6,673–41,590 segundos. Precisão e recall nulos: não há gold humano independente. A contagem de testes verdes não é critério de publicação.

Consulta adicional Array.prototype.flat no chat teve quatro fontes lidas. Não pertence ao holdout congelado; não altera seu denominador nem comprova ganho consistente. Resultado externo exige NO_GO.
