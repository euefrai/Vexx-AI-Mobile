# Publicação das correções da auditoria — 21/10/2026

Pacote: correções e evidências do commit 52e3195, mais regra .gitattributes
para preservar LF em public/vendor/three-engine.js. O checkout automático CRLF
no Windows tornava esse arquivo diferente da versão .gz; a regra corrige a causa.

Validação em cópia isolada do pacote: 941 passed, 4 skipped, 2 warnings, 127,68 s.
Os skips dependem de inferência/provedores externos. Log: release-suite.txt.
node --check passou para public/app.js e public/workspace.js; JS e gzip são
idênticos byte a byte no novo checkout. Nenhum teste foi removido.

As evoluções V5.8 posteriores a 52e3195 não fazem parte deste pacote.
O histórico local dessas evoluções é preservado. Este procedimento envia Git;
não executa comandos de deploy nem altera dados ou credenciais de produção.
