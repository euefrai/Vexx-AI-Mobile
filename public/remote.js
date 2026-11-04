/* Device hints choose presentation only. All permissions are checked by the agent. */
(function (root) {
  'use strict';
  function isMobile(nav) {
    const ua = nav.userAgent || '';
    return nav.userAgentData?.mobile === true || /Android|iPhone|iPad|iPod|Mobile/i.test(ua)
      || (/Macintosh|MacIntel/.test(ua + ' ' + (nav.platform || '')) && nav.maxTouchPoints > 1);
  }
  function imagePosition(rect, width, height, clientX, clientY) {
    if (!width || !height || !rect.width || !rect.height) return null;
    const scale = Math.min(rect.width / width, rect.height / height);
    const w = width * scale, h = height * scale;
    const x = (clientX - rect.left - (rect.width - w) / 2) / w;
    const y = (clientY - rect.top - (rect.height - h) / 2) / h;
    return x < 0 || x > 1 || y < 0 || y > 1 ? null : { x, y };
  }
  function mount(ctx) {
    const $ = id => document.getElementById(id);
    const mobile = isMobile(navigator);
    let state = null, connected = false, screenBusy = false, statusBusy = false;
    let commandBusy = false, version = 0, identity = '', lastStatus = 0, notice = '';
    let screenAbort, statusAbort, gesture = null, longTimer, lastMove = 0;
    let inputBusy = false, inputAbort, inputTimer, lastInputAt = 0;
    let frameTimer, streamAbort, streaming = false, fallback = false, lastFrame = 0;
    const inputQueue = [];
    const frame = $('remoteFrame'), image = $('screenImg');
    const pageActive = () => !$('page-desktop').hidden && !document.hidden;
    const online = () => ctx.authenticated() && ctx.online() && navigator.onLine;
    const valid = (v, id) => v === version && id === ctx.identity() && online() && pageActive();
    function stop() {
      connected = false;
      screenAbort?.abort(); screenBusy = false; streamAbort?.abort(); clearTimeout(frameTimer);
      streaming = false; lastFrame = 0;
      inputAbort?.abort(); clearTimeout(inputTimer);
      for (const item of inputQueue.splice(0)) item.resolve.forEach(done => done(false));
      $('remoteKeys').value = '';
      image.removeAttribute('src');
      gesture = null;
      clearTimeout(longTimer);
      $('remotePointer').style.display = 'none';
      if (document.fullscreenElement === frame) document.exitFullscreen().catch(() => {});
    }
    function render(message) {
      if (message !== undefined) notice = message;
      $('remoteRetry').disabled = statusBusy || commandBusy || !online();
      $('pcSetup').hidden = connected || (mobile && !state?.pending);
      $('pcConnect').hidden = connected;
      $('remoteViewer').hidden = !connected;
      $('remoteTitle').textContent = mobile ? 'Seu PC, onde você estiver.' : 'Conectar meu computador.';
      $('remoteIntro').textContent = mobile ? 'Acesse a tela do PC autorizado na sua conta.' : 'Prepare o acesso pelo celular, com a sua permissão.';
      $('remoteDeviceName').textContent = state?.device_name || 'Meu computador';
      $('remoteSetupTitle').textContent = state?.approved ? 'Pronto para conectar' : 'Acesse pelo celular';
      $('remoteSetupCopy').textContent = state?.approved
        ? 'No celular, entre nesta mesma conta, abra Meu PC e toque em Conectar. Mantenha o computador ligado e o agente aberto.'
        : 'Autorize este PC uma vez. Depois, entre na mesma conta no celular para ver a tela e usar mouse e teclado.';
      $('remoteSteps').hidden = state?.approved === true;
      $('deviceDetail').textContent = state ? state.platform + ' · ' + (state.view_allowed ? 'Acesso autorizado' : 'Aguardando autorização local') : online() ? 'Agente conectado · verificando acesso remoto' : 'Aguardando PC Agent';
      $('deviceStatus').textContent = online() ? 'Online' : 'Offline';
      $('deviceStatus').classList.toggle('connected', online());
      $('remotePermit').disabled = commandBusy || !online() || !state?.capture_ready || state.approved || state.confirmation_open;
      $('remotePermit').textContent = state?.approved ? 'Acesso permitido' : state?.pending ? 'Confirme no Windows…' : 'Permitir acesso pelo celular';
      $('remoteConnect').disabled = commandBusy || !online() || !state?.view_allowed || !state?.capture_ready || state?.confirmation_open;
      $('remoteRevoke').hidden = !(state?.approved || state?.view_allowed || state?.pending);
      $('remoteRevoke').disabled = commandBusy || !online();
      for (const id of ['keyboardButton', 'remoteEnter', 'remoteBackspace', 'remoteScrollUp', 'remoteScrollDown', 'remoteTab', 'remoteEscape', 'remoteKeys']) {
        $(id).disabled = !connected || !state?.control_allowed || state?.confirmation_open;
      }
      $('remoteAccessStatus').textContent = notice || (!online()
        ? 'Abra o PC Agent no computador e mantenha os dois aparelhos conectados à internet.'
        : !state ? 'Verificando o agente conectado…'
        : !state.supported ? 'O controle está disponível para computadores Windows.'
        : !state.capture_ready ? 'Instale a dependência de captura no computador. Veja o guia do PC Agent.'
        : state.pending ? 'Confirme no Windows do PC ' + state.device_name + '. Código: ' + state.code + '. O pedido expira em 2 minutos.'
        : state.confirmation_open ? 'Feche a confirmação anterior no Windows. O controle fica pausado enquanto ela estiver aberta.'
        : state.approved ? 'Acesso permitido para esta conta. Você pode revogar a qualquer momento.'
        : state.view_allowed ? 'Acesso autorizado pelo administrador' + (state.control_allowed ? '.' : ' · somente visualização.')
        : mobile ? 'No computador, abra Meu PC e permita o acesso usando esta mesma conta.'
        : 'O pedido abre no PC conectado: ' + state.device_name + '. Confirme que é este computador antes de permitir.');
    }
    async function refresh(force = false) {
      if (!online() || !pageActive() || statusBusy || commandBusy) return;
      if (!force && Date.now() - lastStatus < (state?.pending ? 4000 : 12000)) return;
      const v = version, id = ctx.identity();
      statusBusy = true; render();
      const abort = new AbortController(); statusAbort = abort;
      try {
        const timeout = setTimeout(() => abort.abort(), 10000);
        let data;
        try { data = await ctx.api('/api/remote/status', { headers: ctx.headers(), signal: abort.signal }); }
        finally { clearTimeout(timeout); }
        if (!valid(v, id)) return;
        state = data; notice = ''; lastStatus = Date.now();
        if (!state.view_allowed || state.confirmation_open) stop();
        render();
      } catch (err) {
        if (valid(v, id)) {
          state = null; stop(); lastStatus = Date.now();
          render(err.name === 'AbortError' ? 'O agente está conectado, mas não respondeu ao acesso remoto. Tente verificar novamente.' : err.status === 404 || err.status === 503
            ? 'Atualize e reinicie o PC Agent para preparar o acesso. Consulte o guia de instalação.'
            : err.message || 'Não foi possível verificar o acesso.');
        }
      } finally { if (statusAbort === abort) { statusBusy = false; statusAbort = null; render(); } }
    }
    async function action(kind) {
      if (commandBusy || !online()) return;
      if (kind === 'request' && mobile) return;
      if (kind === 'revoke') stop();
      statusAbort?.abort();
      statusBusy = false;
      version++;
      const v = version, id = ctx.identity();
      commandBusy = true; render();
      try {
        const data = await ctx.api('/api/remote/' + kind, { method: 'POST' });
        if (!valid(v, id)) return;
        state = data; notice = ''; lastStatus = Date.now(); render();
      } catch (err) {
        if (valid(v, id)) render(err.message || 'Não foi possível alterar o acesso.');
      } finally { commandBusy = false; if (valid(v, id)) render($('remoteAccessStatus').textContent); }
    }
    async function displayFrame(r, v, id) {
      if (!valid(v, id) || !connected) return;
      if (r.error) { const err = new Error(r.error); err.status = r.status; throw err; }
      if (!r.imagem || !r.largura || !r.altura) throw new Error('Quadro inválido recebido do PC.');
      // Decode offscreen: keep the last frame visible until its replacement is ready.
      const next = new Image(); next.src = 'data:image/jpeg;base64,' + r.imagem;
      await next.decode();
      if (!valid(v, id) || !connected) return;
      image.src = next.src;
      frame.style.aspectRatio = r.largura + ' / ' + r.altura;
      if (state) state.control_allowed = r.remote_enabled === true;
      const now = performance.now();
      $('screenLabel').textContent = lastFrame ? 'AO VIVO · ' + Math.min(99, Math.round(1000 / Math.max(1, now - lastFrame))) + ' fps' : 'AO VIVO';
      lastFrame = now;
      $('screenNote').textContent = r.remote_enabled ? 'Toque para clicar. Segure para o botão direito. Use o teclado abaixo para digitar.' : 'Somente visualização. Permita o controle no computador.';
      render();
    }
    async function pullScreen() {
      if (!connected || !online() || !pageActive() || screenBusy || streaming) return;
      const v = version, id = ctx.identity();
      const abort = new AbortController(); screenAbort = abort;
      screenBusy = true;
      try {
        const width = Math.min(960, Math.max(640, Math.round(frame.clientWidth * (devicePixelRatio || 1))));
        const r = await ctx.api('/api/screen?max_w=' + width + '&q=55', { headers: ctx.headers(), signal: abort.signal });
        await displayFrame(r, v, id);
      } catch (err) {
        if (err.name !== 'AbortError' && valid(v, id)) {
          stop(); render(err.message || 'Conexão interrompida. Conecte novamente.'); lastStatus = 0;
        }
      } finally {
        if (screenAbort === abort) screenBusy = false;
        if (connected && valid(v, id) && !streaming) frameTimer = setTimeout(pullScreen, 150);
      }
    }
    async function startStream() {
      if (fallback) { pullScreen(); return; }
      const v = version, id = ctx.identity(), abort = new AbortController();
      streamAbort = abort; streaming = true;
      let reader, idleTimer;
      const armTimeout = () => {
        clearTimeout(idleTimer);
        idleTimer = setTimeout(() => {
          if (valid(v, id) && connected) { stop(); render('A transmissão parou de responder. Conecte novamente.'); }
        }, 25000);
      };
      armTimeout();
      try {
        const response = await fetch('/api/screen/stream?max_w=960&q=55', {
          headers: ctx.headers(), credentials: 'same-origin', cache: 'no-store', signal: abort.signal
        });
        if (!response.ok) {
          if ([404, 405, 501].includes(response.status)) { fallback = true; return; }
          const data = await response.json().catch(() => ({}));
          throw new Error(data.detail || 'Transmissão indisponível (' + response.status + ').');
        }
        if (!response.body || !response.headers.get('Content-Type')?.includes('application/x-ndjson')) { fallback = true; return; }
        reader = response.body.getReader();
        const decoder = new TextDecoder(); let pending = '';
        while (valid(v, id) && connected) {
          const {value, done} = await reader.read();
          if (done) throw new Error('Transmissão encerrada. Conecte novamente.');
          armTimeout();
          pending += decoder.decode(value, {stream:true});
          if (pending.length > 4000000) throw new Error('Quadro excedeu o limite da transmissão.');
          let newline;
          while ((newline = pending.indexOf('\n')) >= 0) {
            const line = pending.slice(0, newline); pending = pending.slice(newline + 1);
            if (line) await displayFrame(JSON.parse(line), v, id);
          }
        }
      } catch (err) {
        if (err.name !== 'AbortError' && valid(v, id)) { stop(); render(err.message); lastStatus = 0; }
      } finally {
        clearTimeout(idleTimer);
        if (reader) await reader.cancel().catch(() => {});
        abort.abort();
        if (streamAbort === abort) {
          streaming = false;
          if (fallback && valid(v, id) && connected) pullScreen();
        }
      }
    }
    function send(cmd) {
      if (!connected || !online() || !pageActive() || !state?.control_allowed || state.confirmation_open) return Promise.resolve(false);
      return new Promise(resolve => {
        const tail = inputQueue.at(-1);
        if (cmd.kind === 'move' && tail?.cmd.kind === 'move') {
          tail.resolve.forEach(done => done(false)); tail.cmd = cmd; tail.resolve = [resolve];
        } else if (cmd.kind === 'text' && tail?.cmd.kind === 'text' && tail.cmd.text.length + cmd.text.length <= 200) {
          tail.cmd.text += cmd.text; tail.resolve.push(resolve);
        } else if (inputQueue.length < 24) {
          inputQueue.push({cmd, resolve:[resolve], version, identity:ctx.identity()});
        } else { ctx.notify('Aguarde o computador responder antes de enviar mais comandos.'); resolve(false); }
        pumpInput();
      });
    }
    async function pumpInput() {
      if (inputBusy || !inputQueue.length) return;
      clearTimeout(inputTimer);
      const wait = 60 - (Date.now() - lastInputAt);
      if (wait > 0) { inputTimer = setTimeout(pumpInput, wait); return; }
      const item = inputQueue.shift();
      if (!valid(item.version, item.identity) || !connected || !state?.control_allowed || state.confirmation_open) {
        item.resolve.forEach(done => done(false)); pumpInput(); return;
      }
      inputBusy = true;
      lastInputAt = Date.now(); inputAbort = new AbortController();
      try {
        await ctx.api('/api/input', { method: 'POST', body: JSON.stringify(item.cmd), signal:inputAbort.signal });
        item.resolve.forEach(done => done(true));
      }
      catch (err) {
        if (err.name !== 'AbortError' && valid(item.version, item.identity)) { stop(); state = null; render(err.message || 'Controle interrompido.'); }
        item.resolve.forEach(done => done(false));
      } finally { inputBusy = false; pumpInput(); }
    }
    function position(ev) {
      return imagePosition(frame.getBoundingClientRect(), image.naturalWidth, image.naturalHeight, ev.clientX, ev.clientY);
    }
    frame.addEventListener('pointerdown', ev => {
      if (ev.target.closest('button') || !connected || !state?.control_allowed || !ev.isPrimary) return;
      const p = position(ev); if (!p) return;
      ev.preventDefault(); frame.setPointerCapture(ev.pointerId);
      gesture = { start: p, point: p, moved: false, long: false, id: ev.pointerId };
      if (ev.pointerType !== 'mouse') {
        longTimer = setTimeout(() => { if (gesture && !gesture.moved) { gesture.long = true; send({ kind: 'right', ...gesture.point }); } }, 600);
      }
    });
    frame.addEventListener('pointermove', ev => {
      if (!gesture || ev.pointerId !== gesture.id) return;
      const p = position(ev); if (!p) return;
      gesture.point = p;
      const rect = frame.getBoundingClientRect();
      if (Math.hypot((p.x - gesture.start.x) * rect.width, (p.y - gesture.start.y) * rect.height) > 12) {
        gesture.moved = true; clearTimeout(longTimer);
        if (Date.now() - lastMove > 80) { lastMove = Date.now(); send({kind: 'move', ...p}); }
      }
    });
    frame.addEventListener('pointerup', ev => {
      if (!gesture || ev.pointerId !== gesture.id) return;
      const g = gesture; gesture = null; clearTimeout(longTimer);
      if (!g.moved && !g.long) send({kind: ev.button === 2 ? 'right' : 'click', ...g.point});
    });
    const cancelGesture = () => { clearTimeout(longTimer); gesture = null; };
    frame.addEventListener('pointercancel', cancelGesture);
    frame.addEventListener('lostpointercapture', cancelGesture);
    frame.addEventListener('contextmenu', ev => ev.preventDefault());
    $('remoteConnect').addEventListener('click', () => {
      if (!state?.view_allowed || state.confirmation_open || connected) return;
      version++; connected = true; render(); startStream();
    });
    $('remoteDisconnect').addEventListener('click', () => { stop(); render(); });
    $('remotePermit').addEventListener('click', () => action('request'));
    $('remoteRevoke').addEventListener('click', () => action('revoke'));
    $('refreshButton').addEventListener('click', () => { if (connected) { version++; stop(); connected = true; startStream(); render(); } });
    $('remoteRetry').addEventListener('click', () => refresh(true));
    $('touchMode').addEventListener('click', () => ctx.notify('Toque para clicar; segure para o botão direito.'));
    $('remoteScrollUp').addEventListener('click', () => send({kind:'scroll', dy:3}));
    $('remoteScrollDown').addEventListener('click', () => send({kind:'scroll', dy:-3}));
    $('remoteEnter').addEventListener('click', () => send({kind:'key', key:'enter'}));
    $('remoteTab').addEventListener('click', () => send({kind:'key', key:'tab'}));
    $('remoteEscape').addEventListener('click', () => send({kind:'key', key:'esc'}));
    $('remoteBackspace').addEventListener('click', () => send({kind:'key', key:'backspace'}));
    const keys = $('remoteKeys');
    $('keyboardButton').addEventListener('click', () => keys.focus());
    function flushText() {
      const text = keys.value; keys.value = '';
      // Keep Unicode surrogate pairs intact and never silently truncate pasted text.
      let chunk = '';
      for (const char of text) {
        if (chunk.length + char.length > 200) { send({kind:'text', text:chunk}); chunk = ''; }
        chunk += char;
      }
      if (chunk) send({kind:'text', text:chunk});
    }
    keys.addEventListener('input', ev => { if (!ev.isComposing) flushText(); });
    keys.addEventListener('compositionend', flushText);
    keys.addEventListener('beforeinput', ev => {
      if (!ev.isComposing && ev.inputType === 'deleteContentBackward' && !keys.value) {
        ev.preventDefault(); send({kind:'key', key:'backspace'});
      }
    });
    keys.addEventListener('keydown', ev => {
      if (ev.isComposing || ev.ctrlKey || ev.metaKey || ev.altKey) return;
      const names = {Enter:'enter', Backspace:'backspace', Tab:'tab', Escape:'esc',
        ArrowLeft:'left', ArrowRight:'right', ArrowUp:'up', ArrowDown:'down', Delete:'delete', Home:'home', End:'end'};
      if (names[ev.key] && (ev.key !== 'Backspace' || !keys.value)) {
        // Tab remains local so keyboard users can leave the field; use its button remotely.
        if (ev.key === 'Tab') return;
        ev.preventDefault(); flushText(); send({kind:'key', key:names[ev.key]});
      }
    });
    $('fullscreen').addEventListener('click', async () => {
      try {
        if (document.fullscreenElement) await document.exitFullscreen();
        else if (frame.requestFullscreen) await frame.requestFullscreen();
        else ctx.notify('Tela cheia indisponível neste navegador.');
      } catch (_) { ctx.notify('Tela cheia não autorizada.'); }
    });
    $('remoteExitFullscreen').addEventListener('click', () => document.exitFullscreen().catch(() => {}));
    function update() {
      const id = ctx.identity();
      if (identity !== id || !online() || !pageActive()) {
        version++; stop(); statusAbort?.abort(); statusBusy = false;
        if (identity !== id || !online()) { state = null; notice = ''; lastStatus = 0; fallback = false; }
      }
      identity = id; render(); refresh();
    }
    document.addEventListener('visibilitychange', update);
    window.addEventListener('offline', update);
    window.addEventListener('pagehide', () => { version++; stop(); });
    setInterval(() => { if (pageActive()) refresh(); }, 1000);
    render();
    return { update };
  }
  root.VexxRemote = { isMobile, imagePosition, mount };
})(typeof window !== 'undefined' ? window : globalThis);
