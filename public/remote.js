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
    let commandBusy = false, version = 0, identity = '', lastStatus = 0;
    let screenAbort, statusAbort, gesture = null, longTimer, lastMove = 0;
    let screenTimer, frameLatency = 450, screenFailures = 0, tapTimer, pendingTap;
    const touches = new Map();
    let scrollPoint = null;
    let inputBusy = false, inputAbort, inputTimer, lastInputAt = 0;
    const inputQueue = [];
    const frame = $('remoteFrame'), image = $('screenImg');
    const pageActive = () => !$('page-desktop').hidden && !document.hidden;
    const online = () => ctx.authenticated() && ctx.online() && navigator.onLine;
    const valid = (v, id) => v === version && id === ctx.identity() && online() && pageActive();
    function stop() {
      connected = false; version++;
      clearTimeout(screenTimer); clearTimeout(tapTimer); pendingTap = null;
      touches.clear(); scrollPoint = null;
      screenAbort?.abort(); screenAbort = null; screenBusy = false;
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
      $('pcSetup').hidden = mobile;
      $('pcConnect').hidden = !mobile || connected;
      $('remoteViewer').hidden = !mobile || !connected;
      $('remoteTitle').textContent = mobile ? 'Seu PC, onde você estiver.' : 'Conectar meu computador.';
      $('remoteIntro').textContent = mobile ? 'Acesse a tela do PC autorizado na sua conta.' : 'Prepare o acesso pelo celular, com a sua permissão.';
      $('remoteDeviceName').textContent = state?.device_name || 'Meu computador';
      $('remoteSetupTitle').textContent = state?.approved ? 'Pronto para conectar' : 'Acesse pelo celular';
      $('remoteSetupCopy').textContent = state?.approved
        ? 'No celular, entre nesta mesma conta, abra Meu PC e toque em Conectar. Mantenha o computador ligado e o agente aberto.'
        : 'Autorize este PC uma vez. Depois, entre na mesma conta no celular para ver a tela e usar mouse e teclado.';
      $('remoteSteps').hidden = state?.approved === true;
      $('deviceDetail').textContent = state ? state.platform + ' · PC Agent conectado' : 'Aguardando PC Agent';
      $('remotePermit').disabled = commandBusy || !online() || !state?.capture_ready || state.approved || state.confirmation_open;
      $('remotePermit').textContent = state?.approved ? 'Acesso permitido' : state?.pending ? 'Confirme no Windows…' : 'Permitir acesso pelo celular';
      $('remoteConnect').disabled = commandBusy || !online() || !state?.view_allowed || !state?.capture_ready || state?.confirmation_open;
      $('remoteRevoke').hidden = !(state?.approved || state?.view_allowed || state?.pending);
      $('remoteRevoke').disabled = commandBusy || !online();
      for (const id of ['keyboardButton', 'remoteEnter', 'remoteBackspace', 'remoteScrollUp', 'remoteScrollDown']) {
        $(id).disabled = !connected || !state?.control_allowed || state?.confirmation_open;
      }
      $('remoteAccessStatus').textContent = message || (!online()
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
      statusBusy = true;
      const abort = new AbortController(); statusAbort = abort;
      try {
        const data = await ctx.api('/api/remote/status', { headers: ctx.headers(), signal: abort.signal });
        if (!valid(v, id)) return;
        state = data; lastStatus = Date.now();
        if (!state.view_allowed || state.confirmation_open) stop();
        render();
      } catch (err) {
        if (err.name !== 'AbortError' && valid(v, id)) {
          state = null; stop(); lastStatus = Date.now();
          render(err.status === 404 || err.status === 503
            ? 'Atualize e reinicie o PC Agent para preparar o acesso. Consulte o guia de instalação.'
            : err.message || 'Não foi possível verificar o acesso.');
        }
      } finally { if (statusAbort === abort) statusBusy = false; }
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
        state = data; lastStatus = Date.now(); render();
      } catch (err) {
        if (valid(v, id)) render(err.message || 'Não foi possível alterar o acesso.');
      } finally { commandBusy = false; if (valid(v, id)) render($('remoteAccessStatus').textContent); }
    }
    async function pullScreen() {
      if (!connected || !mobile || !online() || !pageActive() || screenBusy) return;
      const v = version, id = ctx.identity();
      clearTimeout(screenTimer);
      const started = performance.now();
      const abort = new AbortController(); screenAbort = abort;
      screenBusy = true;
      try {
        const width = frameLatency > 1400 ? 960 : frameLatency > 650 ? 1280 : 1920;
        const quality = frameLatency > 1400 ? 62 : 78;
        const r = await ctx.api('/api/screen?max_w=' + width + '&q=' + quality, { headers: ctx.headers(), signal: abort.signal });
        if (!valid(v, id) || !connected) return;
        const next = new Image();
        next.src = 'data:image/jpeg;base64,' + r.imagem;
        await next.decode();
        if (!valid(v, id) || !connected) return;
        image.src = next.src;
        frameLatency = frameLatency * .7 + (performance.now() - started) * .3;
        screenFailures = 0;
        frame.style.aspectRatio = r.largura + ' / ' + r.altura;
        if (state) state.control_allowed = r.remote_enabled === true;
        $('screenLabel').textContent = 'CONECTADO';
        $('screenNote').textContent = r.remote_enabled ? 'Toque para clicar; dois toques para abrir. Arraste para selecionar ou mover. Dois dedos para rolar; segure para o botão direito.' : 'Somente visualização. Permita o controle no computador.';
        render();
      } catch (err) {
        if (err.name !== 'AbortError' && valid(v, id)) {
          screenFailures++;
          if (err.status === 401 || err.status === 403 || screenFailures >= 3) {
            stop(); state = null; render(err.message || 'Conexão interrompida. Conecte novamente.');
            lastStatus = 0;
          } else $('screenLabel').textContent = 'RECONECTANDO…';
        }
      } finally {
        if (screenAbort === abort) {
          screenBusy = false;
          if (valid(v, id) && connected) {
            const delay = screenFailures ? 1000 * screenFailures : Math.max(30, 250 - (performance.now() - started));
            screenTimer = setTimeout(pullScreen, delay);
          }
        }
      }
    }
    function send(cmd) {
      if (!connected || !online() || !pageActive() || !state?.control_allowed || state.confirmation_open) return Promise.resolve(false);
      return new Promise(resolve => {
        const tail = inputQueue.at(-1);
        if (cmd.kind === 'move' && tail?.cmd.kind === 'move') {
          tail.resolve.forEach(done => done(false)); tail.cmd = cmd; tail.resolve = [resolve];
        } else if (cmd.kind === 'scroll' && tail?.cmd.kind === 'scroll') {
          tail.cmd.dx = Math.max(-10, Math.min(10, (tail.cmd.dx || 0) + (cmd.dx || 0)));
          tail.cmd.dy = Math.max(-10, Math.min(10, (tail.cmd.dy || 0) + (cmd.dy || 0)));
          tail.resolve.forEach(done => done(false)); tail.resolve = [resolve];
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
      const wait = 100 - (Date.now() - lastInputAt);
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
    const cancelGesture = () => { clearTimeout(longTimer); gesture = null; touches.clear(); scrollPoint = null; };
    const center = () => {
      const values = [...touches.values()];
      return {x: values.reduce((n,p)=>n+p.x,0)/values.length, y:values.reduce((n,p)=>n+p.y,0)/values.length};
    };
    frame.addEventListener('pointerdown', ev => {
      if (ev.target.closest('button') || !connected || !state?.control_allowed) return;
      const p = position(ev); if (!p) return;
      ev.preventDefault(); frame.setPointerCapture(ev.pointerId);
      touches.set(ev.pointerId, {x:ev.clientX, y:ev.clientY});
      if (touches.size > 1) {
        clearTimeout(longTimer); clearTimeout(tapTimer); pendingTap = null;
        gesture = null; scrollPoint = center(); return;
      }
      gesture = { start: p, point: p, points:[p], moved: false, long: false, id: ev.pointerId };
      if (ev.pointerType !== 'mouse') {
        longTimer = setTimeout(() => { if (gesture && !gesture.moved) { gesture.long = true; send({ kind: 'right', ...gesture.point }); } }, 600);
      }
    });
    frame.addEventListener('pointermove', ev => {
      if (!touches.has(ev.pointerId)) return;
      touches.set(ev.pointerId, {x:ev.clientX, y:ev.clientY});
      if (scrollPoint && touches.size > 1) {
        const c = center(), dx = Math.trunc((scrollPoint.x-c.x)/24), dy = Math.trunc((c.y-scrollPoint.y)/24);
        if ((dx || dy) && Date.now()-lastMove >= 100) {
          lastMove = Date.now(); scrollPoint = c;
          send({kind:'scroll',dx:Math.max(-10,Math.min(10,dx)),dy:Math.max(-10,Math.min(10,dy))});
        }
        return;
      }
      if (!gesture || ev.pointerId !== gesture.id || gesture.long) return;
      const p = position(ev); if (!p) return;
      gesture.point = p;
      const rect = frame.getBoundingClientRect();
      if (Math.hypot((p.x - gesture.start.x) * rect.width, (p.y - gesture.start.y) * rect.height) > 8) {
        gesture.moved = true; clearTimeout(longTimer);
        if (gesture.points.length >= 31) gesture.points = gesture.points.filter((_,i)=>i%2===0);
        gesture.points.push(p);
      }
    });
    frame.addEventListener('pointerup', ev => {
      touches.delete(ev.pointerId);
      if (!touches.size) scrollPoint = null;
      if (!gesture || ev.pointerId !== gesture.id) return;
      const g = gesture; gesture = null; clearTimeout(longTimer);
      const end = position(ev) || g.point;
      if (g.long) return;
      if (g.moved) { send({kind:'drag',points:[...g.points,end]}); return; }
      if (ev.button === 2) { send({kind:'right',...end}); return; }
      if (pendingTap && Math.hypot(pendingTap.x-end.x,pendingTap.y-end.y)<.04) {
        clearTimeout(tapTimer); pendingTap = null; send({kind:'double',...end});
      } else {
        if (pendingTap) { clearTimeout(tapTimer); send({kind:'click',...pendingTap}); }
        pendingTap = end;
        tapTimer = setTimeout(()=>{ const p=pendingTap; pendingTap=null; if(p)send({kind:'click',...p}); },250);
      }
    });
    frame.addEventListener('pointercancel', cancelGesture);
    frame.addEventListener('lostpointercapture', ev => { if(touches.has(ev.pointerId)) cancelGesture(); });
    frame.addEventListener('wheel', ev => {
      if (!connected || !state?.control_allowed) return;
      ev.preventDefault();
      if(Date.now()-lastMove<100)return;
      lastMove=Date.now();
      send({kind:'scroll',dx:Math.sign(ev.deltaX)*3,dy:-Math.sign(ev.deltaY)*3});
    }, {passive:false});
    frame.addEventListener('contextmenu', ev => ev.preventDefault());
    $('remoteConnect').addEventListener('click', () => {
      if (!mobile || !state?.view_allowed || state.confirmation_open) return;
      connected = true; render(); pullScreen();
    });
    $('remoteDisconnect').addEventListener('click', () => { stop(); render(); });
    $('remotePermit').addEventListener('click', () => action('request'));
    $('remoteRevoke').addEventListener('click', () => action('revoke'));
    $('refreshButton').addEventListener('click', pullScreen);
    $('touchMode').addEventListener('click', () => ctx.notify('Toque: clique. Dois toques: abrir. Arraste: mover/selecionar ao soltar. Dois dedos: rolar. Segure: botão direito.'));
    $('remoteScrollUp').addEventListener('click', () => send({kind:'scroll', dy:3}));
    $('remoteScrollDown').addEventListener('click', () => send({kind:'scroll', dy:-3}));
    $('remoteEnter').addEventListener('click', () => send({kind:'key', key:'enter'}));
    $('remoteBackspace').addEventListener('click', () => send({kind:'key', key:'backspace'}));
    const keys = $('remoteKeys');
    $('keyboardButton').addEventListener('click', () => { keys.value = ''; keys.focus(); });
    keys.addEventListener('input', async ev => {
      if (ev.isComposing || !keys.value) return;
      const text = keys.value.slice(0,200); keys.value = '';
      await send({kind:'text', text});
    });
    keys.addEventListener('compositionend', () => keys.dispatchEvent(new Event('input')));
    keys.addEventListener('keydown', ev => {
      if (ev.isComposing) return;
      if (ev.key === 'Enter') { ev.preventDefault(); send({kind:'key',key:'enter'}); }
      else if (ev.key === 'Backspace' && !keys.value) { ev.preventDefault(); send({kind:'key',key:'backspace'}); }
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
        if (identity !== id || !online()) { state = null; lastStatus = 0; }
      }
      identity = id; render(); refresh();
    }
    document.addEventListener('visibilitychange', update);
    window.addEventListener('offline', update);
    window.addEventListener('pagehide', () => { version++; stop(); });
    setInterval(() => { if (pageActive()) refresh(); }, 1600);
    render();
    return { update };
  }
  root.VexxRemote = { isMobile, imagePosition, mount };
})(typeof window !== 'undefined' ? window : globalThis);
