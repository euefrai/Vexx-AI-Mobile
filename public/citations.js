/* === PERPLEXITY-STYLE: CITATION POPOVER & SCREEN-TO-RESEARCH === */
function showCitationPopover(targetEl, url, num) {
  const existing = document.getElementById('citationPopover');
  if (existing) existing.remove();
  let domain = '';
  try { domain = new URL(url).hostname.replace(/^www\./, ''); } catch (_) { domain = url; }
  const pop = document.createElement('div');
  pop.id = 'citationPopover';
  pop.className = 'citation-popover';
  const label = rotuloUrl ? rotuloUrl(url) : domain;
  pop.innerHTML = '<div class="citation-popover-head">' +
    '<img src="https://www.google.com/s2/favicons?domain=' + encodeURIComponent(domain) + '&sz=32" alt="" width="16" height="16" />' +
    '<span class="citation-popover-domain">' + esc(domain) + '</span>' +
    '<span style="margin-left:auto;font-size:10px;opacity:0.6">[' + esc(num) + ']</span>' +
    '</div>' +
    '<div class="citation-popover-title">' + esc(label || domain) + '</div>' +
    '<div class="citation-popover-snippet">Fonte citada como evidência para esta resposta na pesquisa profunda.</div>' +
    '<a class="citation-popover-link" href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">Acessar fonte original ↗</a>';
  document.body.appendChild(pop);
  const rect = targetEl.getBoundingClientRect();
  const popRect = pop.getBoundingClientRect();
  let top = rect.bottom + 8;
  if (top + popRect.height > window.innerHeight - 16) {
    top = Math.max(16, rect.top - popRect.height - 8);
  }
  let left = Math.max(16, Math.min(window.innerWidth - popRect.width - 16, rect.left));
  pop.style.top = top + 'px';
  pop.style.left = left + 'px';
  const close = e => {
    if (!pop.contains(e.target) && e.target !== targetEl) {
      pop.remove();
      document.removeEventListener('pointerdown', close);
    }
  };
  setTimeout(() => document.addEventListener('pointerdown', close), 10);
}

document.addEventListener('click', ev => {
  const pill = ev.target.closest('.citation-pill');
  if (!pill) return;
  ev.preventDefault();
  const url = pill.dataset.url;
  const num = pill.dataset.num;
  if (url) showCitationPopover(pill, url, num);
});

// Listener para Screen-to-Research (AnyDesk + Perplexity Deep Research)
window.addEventListener('vexx:screen_research', ev => {
  const src = ev.detail && ev.detail.src;
  const chatNavBtn = document.querySelector('[data-tab="chat"]');
  if (chatNavBtn) chatNavBtn.click();
  else {
    document.querySelectorAll('.page').forEach(p => { p.hidden = (p.id !== 'page-chat'); });
    $('page-chat')?.classList.add('active');
    $('page-desktop')?.setAttribute('hidden', '');
  }
  const input = $('chatInput');
  if (input) {
    input.value = 'Investigue a tela atual do meu computador e faça uma pesquisa profunda investigando os dados, erros e conceitos nela: ';
    input.focus();
  }
  if (typeof notify === 'function') {
    notify('Tela do PC vinculada à Pesquisa Profunda. Clique em Enviar para iniciar a investigação.');
  }
});
