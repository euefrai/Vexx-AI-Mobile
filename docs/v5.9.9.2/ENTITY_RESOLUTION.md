# Tema e identidade explícitos

`query_intelligence.topic_profile` separa texto original, assunto, informações requeridas, preferências de fontes/apresentação e candidatos nominais. Sintaxe reconhecida inclui história, documentação, especificações, relatório e comandos de pesquisa. Não é um NER universal nem uma base de relações entre pessoas, empresas e cidades. Nomes desconhecidos permanecem `explicit_text_not_verified`; nenhuma identidade é confirmada pelo primeiro resultado.

`search_orchestrator._context_mismatch` reaproveita os filtros de modelos/identificadores e acrescenta âncoras nominais explícitas. Palavras de comando não são entidades. Comparações admitem uma página por entidade comparada; exigir as duas em cada documento seria incorreto. Termos negativos, orçamentos e comparações que o parser não modela conservam integralmente a consulta. Regras existentes de localidade, região, período, variante e exclusões comerciais continuam responsáveis pela aprovação final.

Ausência no snippet não proíbe leitura: continua possível abrir candidato desconhecido. A presença literal de um nome não comprova identidade semântica, local do acontecimento ou suporte a uma afirmação. Homônimos e variantes com grafias muito diferentes continuam limites. Sem metadados verificáveis não se inventam aliases, datas, preços ou afiliação oficial.

Regressões úteis: dicionário de história não substitui WEG; WH-CH720 não substitui WH-CH520; `Compare` não é organização; Ubatã/Bahia não inclui a palavra operacional Notícias; FastAPI e Django não precisam coexistir na mesma fonte. Testes em `tests/test_discovery_v5992.py`, comparações antigas preservadas e suíte final registrada no relatório principal.
