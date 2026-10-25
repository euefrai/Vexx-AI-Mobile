# Trace parcial de QA

`retrieval_trace.observe(limit=400)` habilita captura local à execução; padrão desligado, máximo 1000 registros, restauração de contexto ao sair e isolamento de observações aninhadas. Não há configuração pública ou persistência automática.

Referências de candidato/job/etapa são hashes. Eventos atuais: duplicado, agregador, seleção com cobrança, texto extraído/vazio, falha de leitura, rejeição de relevância, ausência de passagem, evidência armazenada e descoberta sem leitura.

O leitor `research.baixar` registra status realmente observado, bytes do corpo recebido e MIME validado; ausências continuam `null`. Redirects têm destino novamente validado, com referência protegida separada. O mesmo candidato mantém uma cobrança através dos redirects. Contexto acompanha os leitores concorrentes; sink usa lock, teto e fechamento para impedir eventos tardios após sair da observação. `read` exige o indicador real de texto lido, não HTTP 200. O trace não contém URLs, trechos de páginas, cabeçalhos, cookies ou tokens.

Há eventos de não seleção por prioridade/orçamento, bloqueio, timeout e falha de extração, além de reason_code limitado e requisitos/passagens na evidência armazenada. Não é ainda o contrato completo: faltam ranks/provedor, vínculo por query/requirement e perdas até síntese em todos os caminhos. Leitores alternativos podem não passar por `baixar`. EVIDENCE_STORED não significa verificação factual nem síntese aceita.
