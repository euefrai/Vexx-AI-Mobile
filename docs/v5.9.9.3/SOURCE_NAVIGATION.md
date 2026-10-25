# Navegação na fonte

Links reais extraídos do HTML agora chegam ao leitor rápido e ao profundo. O extrator considera até duzentos links dentro do HTML já limitado, prioriza os pertinentes e devolve até trinta. Isso corrige o descarte anterior ao leitor; não cria URLs por adivinhação. A detecção de subdomínio também exige fronteira de domínio (`host == base` ou `.base`), sem tratar `evilexample.org` como parte de `example.org`.

`web_extract.navigation_candidates` usa texto/URL declarados e a entidade/requisito, descarta protocolos/credenciais, limita profundidade a dois ou ao limite menor do job, e não prioriza links apenas por estarem no mesmo host. O fetch mantém DNS público, SSRF, validação de redirect, limites de bytes, timeout e políticas de acesso existentes. Não executa scripts nem contorna bloqueios.

O rápido reserva leituras dentro das seis já existentes; o profundo substitui a próxima oportunidade dentro do mesmo orçamento de páginas/tentativas/concorrência. URLs conhecidas e falhas de leitura não são repetidas pelo mesmo job. Links candidatos ficam observáveis como FOLLOW_LINK; fonte relacionada, página lida e passagem que responde continuam estados distintos. O ranking por termos é limitado e não garante descoberta da referência específica em qualquer site.
