/* Project tree and accessible editing dialogs. app.js owns the chat lifecycle. */
let openProjects = new Set();
let organizedTarget = null;
let libraryRenderVersion = 0;

function libraryIcon(name) {
  return '<svg class="icon" aria-hidden="true"><use href="#i-' + name + '"/></svg>';
}

async function renderSessions(filter) {
  if (!db || !workspace) return;
  const version = ++libraryRenderVersion;
  await workspace.load();
  const q = String(filter || '').trim().toLowerCase();
  const all = ownRows(await allMessages());
  let sessions = await allSessions();
  if (!sessions.find(s => s.id === activeConversation)) {
    await ensureSession(activeConversation);
    sessions = await allSessions();
  }
  if (version !== libraryRenderVersion) return;
  sessionsCache = sessions;
  const hay = new Map();
  all.forEach(m => hay.set(m.conversation_id,
    ((hay.get(m.conversation_id) || '') + ' ' + m.text).toLowerCase().slice(-20000)));
  const matches = s => !q || s.title.toLowerCase().includes(q) || (hay.get(s.id) || '').includes(q);
  const available = sessions.filter(s => !isDeleted(s.id) && !s.deleted && (!s.archived || showArchived))
    .sort((a,b) => Number(!!b.pinned)-Number(!!a.pinned) || (b.updated_at || '').localeCompare(a.updated_at || ''));
  const projects = workspace.list('project').sort((a,b) => a.title.localeCompare(b.title, 'pt-BR'));
  const projectIds = new Set(projects.map(p => p.id));
  const tree = $('projectList'), loose = $('sessionList');
  tree.replaceChildren(); loose.replaceChildren();

  function chatRow(s) {
    const row = document.createElement('div');
    row.className = 'session-item' + (s.id === activeConversation ? ' active' : '') + (s.archived ? ' archived' : '');
    row.dataset.conversationId = s.id;
    const button = document.createElement('button'); button.type = 'button'; button.className = 'session-open';
    if (s.id === activeConversation) button.setAttribute('aria-current', 'page');
    button.innerHTML = '<span class="t">' + (s.pinned ? libraryIcon('pin') : '') + '<span class="session-title"></span></span>';
    button.querySelector('.session-title').textContent = s.title || 'Nova conversa';
    button.title = s.title;
    button.addEventListener('click', async () => {
      setActiveConversation(s.id); navigate('chat');
      await renderSessions($('sessionSearch').value); await renderMessages();
      if (window.innerWidth < 900) setDrawer(false);
    });
    const more = document.createElement('button'); more.type = 'button'; more.className = 'session-tool';
    more.textContent = '···'; more.setAttribute('aria-label', 'Organizar ' + s.title);
    more.addEventListener('click', () => openOrganizer('chat', s));
    row.append(button, more);
    return row;
  }
  function empty(parent, text) {
    const p = document.createElement('p'); p.className = 'library-empty'; p.textContent = text; parent.append(p);
  }
  projects.forEach(p => {
    const children = available.filter(s => s.project_id === p.id);
    const projectMatches = q && p.title.toLowerCase().includes(q);
    const visible = children.filter(s => projectMatches || matches(s));
    if (q && !projectMatches && !visible.length) return;
    const group = document.createElement('section'); group.className = 'project-group'; group.dataset.projectId = p.id;
    const heading = document.createElement('div'); heading.className = 'project-heading';
    const toggle = document.createElement('button'); toggle.type = 'button'; toggle.className = 'project-toggle';
    const expanded = !!q || openProjects.has(p.id);
    toggle.setAttribute('aria-expanded', String(expanded));
    toggle.setAttribute('aria-controls', 'project-' + p.id);
    toggle.innerHTML = libraryIcon('arrow') + '<span></span><small></small>';
    toggle.querySelector('span').textContent = p.title;
    toggle.querySelector('small').textContent = String(children.length);
    toggle.setAttribute('aria-label', p.title + ', ' + children.length + ' conversas');
    toggle.addEventListener('click', () => {
      openProjects.has(p.id) ? openProjects.delete(p.id) : openProjects.add(p.id);
      renderSessions($('sessionSearch').value);
    });
    const edit = document.createElement('button'); edit.type = 'button'; edit.className = 'session-tool'; edit.textContent = '···';
    edit.setAttribute('aria-label', 'Renomear projeto ' + p.title);
    edit.addEventListener('click', () => openOrganizer('project', p));
    heading.append(toggle, edit);
    const list = document.createElement('div'); list.id = 'project-' + p.id; list.className = 'project-children'; list.hidden = !expanded;
    visible.forEach(s => list.append(chatRow(s)));
    if (!visible.length) empty(list, q ? 'Nenhuma conversa encontrada.' : 'Seu projeto está pronto. Comece uma conversa.');
    const add = document.createElement('button'); add.type = 'button'; add.className = 'project-add';
    add.innerHTML = libraryIcon('plus') + ' Nova conversa'; add.setAttribute('aria-label', 'Nova conversa em ' + p.title);
    add.addEventListener('click', () => newChat(p.id)); list.append(add);
    group.append(heading, list); tree.append(group);
  });
  if (!projects.length) empty(tree, 'Agrupe suas conversas por assunto.');
  const ungrouped = available.filter(s => !projectIds.has(s.project_id) && matches(s));
  ungrouped.forEach(s => loose.append(chatRow(s)));
  if (!ungrouped.length) empty(loose, q ? 'Nenhuma conversa encontrada.' : 'Nenhuma conversa sem projeto.');
  $('sessionCount').textContent = String(ungrouped.length);
}

async function openOrganizer(kind, record) {
  if (!db) { showToast('Armazenamento local indisponível'); return; }
  await workspace.load();
  organizedTarget = {kind, id: record ? record.id : newId(), record};
  const project = kind === 'project';
  $('organizeTitle').textContent = project ? (record ? 'Renomear projeto' : 'Criar projeto') : 'Organizar conversa';
  $('organizeDescription').textContent = project ? 'Reúna uma ou mais conversas sobre o mesmo assunto.' : 'Renomeie, mova para um projeto ou organize esta conversa.';
  $('organizeName').value = record ? record.title : '';
  $('organizeName').placeholder = project ? 'Ex.: Meu projeto, Estudos…' : 'Nome da conversa';
  $('organizeDestination').hidden = project; $('organizeChatActions').hidden = project;
  $('organizeDelete').hidden = project; $('organizeError').textContent = '';
  $('organizeSave').textContent = project && !record ? 'Criar projeto' : 'Salvar';
  $('organizePinned').checked = !!(record && record.pinned);
  $('organizeArchived').checked = !!(record && record.archived);
  const select = $('organizeProject'); select.replaceChildren(new Option('Sem projeto', ''));
  workspace.list('project').sort((a,b) => a.title.localeCompare(b.title, 'pt-BR'))
    .forEach(p => select.add(new Option(p.title, p.id)));
  select.value = record && record.project_id || '';
  if (!select.value) select.value = '';
  $('organizeDialog').showModal(); $('organizeName').focus(); $('organizeName').select();
}

function bindOrganizer() {
$('newProject').addEventListener('click', () => openOrganizer('project'));
$('chatOptions').addEventListener('click', async () => {
  const s = (await allSessions()).find(s => s.id === activeConversation);
  if (s) openOrganizer('chat', s);
});
['organizeClose', 'organizeCancel'].forEach(id => $(id).addEventListener('click', () => $('organizeDialog').close()));
$('organizeDialog').addEventListener('click', e => { if (e.target === $('organizeDialog')) {
  const r = e.target.getBoundingClientRect();
  if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) e.target.close();
}});
$('organizeForm').addEventListener('submit', async e => {
  e.preventDefault();
  if (!organizedTarget) return;
  const title = $('organizeName').value.trim().replace(/\s+/g, ' ');
  if (!title) { $('organizeError').textContent = 'Informe um nome.'; $('organizeName').focus(); return; }
  const target = organizedTarget, save = $('organizeSave'); save.disabled = true;
  try {
    if (target.kind === 'project') {
      await workspace.change('project', target.id, {title}); openProjects.add(target.id);
    } else {
      const s = (await allSessions()).find(s => s.id === target.id);
      if (!s) throw Error('Esta conversa não está mais disponível.');
      s.title = title; s.project_id = $('organizeProject').value;
      s.pinned = $('organizePinned').checked; s.archived = $('organizeArchived').checked;
      s.updated_at = new Date().toISOString();
      await putSession(s);
      if (s.project_id) openProjects.add(s.project_id);
    }
    $('organizeDialog').close();
    await renderSessions($('sessionSearch').value); await renderMessages();
    showToast(target.kind === 'project' ? (target.record ? 'Projeto renomeado' : 'Projeto criado') : 'Conversa organizada');
  } catch (err) { $('organizeError').textContent = err.message || 'Não foi possível salvar. Tente novamente.'; }
  finally { save.disabled = false; }
});
$('organizeDelete').addEventListener('click', async () => {
  if (!organizedTarget || organizedTarget.kind !== 'chat') return;
  const id = organizedTarget.id;
  if (!window.confirm('Excluir esta conversa e suas mensagens? Esta ação não pode ser desfeita.')) return;
  const button = $('organizeDelete'); button.disabled = true;
  try {
    // Keep a synced metadata tombstone so other devices do not recreate the entry.
    await workspace.change('chat', id, {deleted: true});
    await tombstone(id); await deleteMessagesOf(id); await delSession(id);
    if (pcOnline && authenticated) {
      try { await api('/api/conversations/' + encodeURIComponent(id), {method:'DELETE'}); } catch (_) {}
    }
    if (activeConversation === id) { setActiveConversation(newId()); await ensureSession(activeConversation); }
    $('organizeDialog').close(); await renderSessions($('sessionSearch').value); await renderMessages();
    showToast('Conversa excluída');
  } catch (err) { $('organizeError').textContent = err.message || 'Não foi possível excluir.'; }
  finally { button.disabled = false; }
});
}
