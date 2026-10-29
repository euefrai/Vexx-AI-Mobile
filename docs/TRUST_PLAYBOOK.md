# Playbook de confiança e reputação — Vexx AI

Este documento separa o que já está implementado no repositório do que depende
de contas, certificados e decisões externas ao código. Nenhuma etapa garante
classificação automática como "site seguro": Google, Chrome e antivírus usam
sinais técnicos e comportamento observado ao longo do tempo.

## 1. Já implementado no site

- Páginas públicas: `/sobre`, `/privacidade`, `/termos`, `/seguranca` e
  `/contato`.
- Rodapé do app e tela de login com links para os documentos legais.
- `robots.txt` e `sitemap.xml` canônicos em `https://vexx-ai.space`.
- `/.well-known/security.txt` no formato RFC 9116.
- `SECURITY.md` no repositório, com escopo e canal de relato.
- Cabeçalhos de segurança no relay: CSP, HSTS em produção, `nosniff`,
  `Referrer-Policy`, `X-Frame-Options` e `Cache-Control: no-store` nas APIs.
- Sessão `HttpOnly`, `Secure` em produção, `SameSite=Strict` e CSRF.
- Canal oficial de contato: GitHub Issues (sem e-mail ou telefone inventados).

## 2. Google Search Console

1. Acesse <https://search.google.com/search-console> e adicione a propriedade
   de domínio `vexx-ai.space` (verificação por DNS TXT) ou a propriedade de
   prefixo de URL `https://vexx-ai.space/`.
2. Envie `https://vexx-ai.space/sitemap.xml`.
3. Verifique "Segurança e ações manuais" para confirmar que não há malware,
   phishing ou violação de políticas.
4. Use "Inspecionar URL" nas páginas `/sobre`, `/privacidade` e `/termos` e
   solicite indexação.
5. Se houver um alerta de segurança, corrija a causa, confirme a limpeza e
   solicite revisão pelo próprio painel.

O Search Console não é um selo de confiança e não "aprova" o site manualmente;
ele mostra o que o Google rastreou e permite pedir revisão de problemas.

## 3. Merchant Center e Perfil do Negócio

Só faz sentido se houver cobrança, vendas ou atendimento comercial com
identidade verificável. Nesse caso:

- cadastre a marca e o domínio nas plataformas de negócios do Google;
- mantenha os mesmos dados de contato, endereço e política de devolução no site
  e no perfil;
- não crie perfil de empresa sem existir uma entidade ou responsável
  identificável por trás.

Enquanto o projeto não tiver empresa, CNPJ ou endereço declarados, o site deve
continuar dizendo isso com franqueza — como já faz.

## 4. Assinatura de código do PC Agent

O executável/instalador do agente precisa ser assinado para reduzir alertas do
Windows SmartScreen e falsos positivos:

1. Adquira um certificado de assinatura de código (OV ou EV) de uma CA
   reconhecida.
2. Assine o binário e o instalador com timestamp RFC 3161.
3. Verifique a assinatura com `signtool verify /pa /all`.
4. Publique o hash SHA-256 de cada release no GitHub.
5. Envie o binário para o Microsoft Security Intelligence como falso positivo:
   <https://www.microsoft.com/en-us/wdsi/filesubmission>
6. Envie também para o VirusTotal e, se possível, para os principais
   fabricantes de antivírus.
7. Repita o envio a cada nova versão; a reputação é construída com histórico de
   binários assinados e limpos.

Sem certificado, o SmartScreen pode continuar exibindo aviso mesmo que o
programa seja legítimo. Isso não é resolvido apenas por documentação no site.

## 5. Domínio e infraestrutura

- `.space`, `.top` e `.xyz` são baratos e estatisticamente mais usados em
  abusos; migrar para `.com`, `.ai` ou `.com.br` reduz atrito, mas não é
  obrigatório.
- Se migrar, mantenha o domínio antigo com redirecionamento 301 para o novo e
  atualize `sitemap.xml`, `security.txt`, canonical e links internos.
- Use HTTPS em todo o site, renovação automática do certificado e HSTS.
- Monitore disponibilidade, expiração do TLS e cabeçalhos com um verificador
  externo.

## 6. GitHub e verificabilidade

- Confirme que o repositório e os Issues estão públicos. Se o repositório for
  privado, o link de contato publicado nas páginas não funcionará para
  visitantes anônimos; nesse caso, habilite um canal público verificado ou
  publique os documentos em uma página própria.
- Mantenha `SECURITY.md` atualizado.
- Publique releases com notas e hashes; se o código for aberto, inclua uma
  licença explícita.
- Preserve o CI de testes e a checagem de JavaScript.
- Evite binários sem origem, ofuscação desnecessária e coleta oculta de dados.

## 7. Rotina de manutenção

- **Mensal:** revisar dependências, alertas do GitHub e cabeçalhos do site.
- **Trimestral:** revisar permissões, sessões, logs e políticas de privacidade.
- **Anual:** renovar o `Expires` do `security.txt`, revisar termos e testar a
  restauração do domínio/TLS.

## 8. O que não fazer

- Comprar backlinks, avaliações ou selos falsos de "site seguro".
- Esconder a ausência de empresa/CNPJ atrás de texto genérico.
- Prometer que antivírus não alertarão sem assinatura e histórico de envio.
- Publicar e-mail ou telefone que não existam ou não sejam monitorados.
