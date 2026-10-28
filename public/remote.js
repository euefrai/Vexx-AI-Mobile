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
    let imageURL, legacyFrames = false, legacyBatch = false;
    let scrollTimer, scrollX=0, scrollY=0, composing=false;
    let screenTimer, frameLatency = 450, screenFailures = 0, tapTimer, pendingTap;
    const touches = new Map();
    let scrollPoint = null;
    let inputBusy = false, inputAbort, inputTimer, lastInputAt = 0, inputBlockedUntil=0;
    const inputQueue = [];
    const frame = $('remoteFrame'), image = $('screenImg');
    const pageActive = () => !$('page-desktop').hidden && !document.hidden;
    const online = () => ctx.authenticated() && ctx.online() && navigator.onLine;
    const valid = (v, id) => v === version && id === ctx.identity() && online() && pageActive();
    function stop() {
      connected = false; version++;
      clearTimeout(scrollTimer); scrollX=0; scrollY=0; composing=false;
      if (imageURL) URL.revokeObjectURL(imageURL); imageURL=null;
      clearTimeout(screenTimer); clearTimeout(tapTimer); pendingTap = null;
      touches.clear(); scrollPoint = null; scrollTimer=null;
      screenAbort?.abort(); screenAbort = null; screenBusy = false;
      inputAbort?.abort(); clearTimeout(inputTimer);
      for (const item of inputQueue.splice(0)) item.resolve.forEach(done => done(false));
      $('remoteKeys').value = ''; $('remoteKeys').hidden = true; $('remoteKeys').blur(); $('keyboardButton').setAttribute('aria-expanded','false');
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
      for (const id of ['keyboardButton', 'remoteEnter', 'remoteBackspace', 'remoteScrollUp', 'remoteScrollDown', 'remoteTab', 'remoteEscape', 'remoteDelete', 'remoteKeys']) {
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
      let nextURL, retryDelay=0, timedOut=false;
      const deadline=setTimeout(()=>{timedOut=true;abort.abort();},10000);
      try {
        const width = frameLatency > 900 ? 960 : frameLatency > 220 ? 1280 : 1920;
        const quality = frameLatency > 900 ? 62 : frameLatency > 220 ? 72 : 78;
        const options = {headers:ctx.headers(),signal:abort.signal};
        let r;
        if (ctx.frame && !legacyFrames) {
          try { r=await ctx.frame('/api/remote/frame?max_w='+width+'&q='+quality, options); }
          catch(err) { if(err.status===404 || err.status===405)legacyFrames=true; else throw err; }
        }
        if (!r) r=await ctx.api('/api/screen?max_w='+width+'&q='+quality,options);
        if (!valid(v, id) || !connected) return;
        const next = new Image();
        next.src = r.blob ? (nextURL=URL.createObjectURL(r.blob)) : 'data:image/jpeg;base64,'+r.imagem;
        await next.decode();
        if (!valid(v, id) || !connected) return;
        image.src = next.src;
        if(imageURL) URL.revokeObjectURL(imageURL);
        imageURL=nextURL; nextURL=null;
        frameLatency = frameLatency * .7 + (performance.now() - started) * .3;
        screenFailures = 0;
        frame.style.aspectRatio = r.largura + ' / ' + r.altura;
        const cursor = r.cursor, marker = $('remotePointer');
        const rect = frame.getBoundingClientRect();
        if (cursor && Number.isFinite(cursor.x) && Number.isFinite(cursor.y)
            && cursor.x >= 0 && cursor.x <= 1 && cursor.y >= 0 && cursor.y <= 1
            && r.largura > 0 && r.altura > 0 && rect.width > 0 && rect.height > 0) {
          const scale = Math.min(rect.width / r.largura, rect.height / r.altura);
          const w = r.largura * scale, h = r.altura * scale;
          marker.style.left = ((rect.width - w) / 2 + cursor.x * w) / rect.width * 100 + '%';
          marker.style.top = ((rect.height - h) / 2 + cursor.y * h) / rect.height * 100 + '%';
          marker.style.display = 'block';
        } else marker.style.display = 'none';
        if (state) state.control_allowed = r.remote_enabled === true;
        $('screenLabel').textContent = 'CONECTADO';
        $('screenNote').textContent = r.remote_enabled ? 'Toque para clicar; dois toques para abrir. Arraste para selecionar ou mover. Dois dedos para rolar; segure para o botão direito.' : 'Somente visualização. Permita o controle no computador.';
        render();
      } catch (err) {
        if ((err.name !== 'AbortError' || timedOut) && valid(v, id)) {
          if(err.status===429) {
            retryDelay=Math.max(1000,Math.min(60000,(err.retryAfter||2)*1000));
            $('screenLabel').textContent='AJUSTANDO TRANSMISSÃO…';
          } else {
          screenFailures++;
          if (err.status === 401 || err.status === 403 || screenFailures >= 3) {
            stop(); state = null; render(err.message || 'Conexão interrompida. Conecte novamente.');
            lastStatus = 0;
          } else $('screenLabel').textContent = 'RECONECTANDO…';
          }
        }
      } finally {
        clearTimeout(deadline);
        if(nextURL) URL.revokeObjectURL(nextURL);
        if (screenAbort === abort) {
          screenBusy = false;
          if (valid(v, id) && connected) {
            const delay = retryDelay || (screenFailures ? 1000 * screenFailures : Math.max(16, 125 - (performance.now() - started)));
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
        } else if (cmd.kind === 'wheel' && tail?.cmd.kind === 'wheel') {
          for(const key of ['delta_x','delta_y'])tail.cmd[key]=Math.max(-1200,Math.min(1200,tail.cmd[key]+cmd[key]));
          tail.resolve.forEach(done=>done(false)); tail.resolve=[resolve];
        } else if (cmd.kind === 'scroll'  && tail?.cmd.kind === 'scroll') {
          tail.cmd.dx = Math.max(-10, Math.min(10, (tail.cmd.dx || 0) + (cmd.dx || 0)));
          tail.cmd.dy = Math.max(-10, Math.min(10, (tail.cmd.dy || 0) + (cmd.dy || 0)));
          tail.resolve.forEach(done => done(false)); tail.resolve = [resolve];
        } else if (cmd.kind === 'text' && tail?.cmd.kind === 'text' && Array.from(tail.cmd.text+cmd.text).length <= 200) {
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
      const wait = Math.max(70-(Date.now()-lastInputAt),inputBlockedUntil-Date.now());
      if (wait > 0) { inputTimer = setTimeout(pumpInput, wait); return; }
      const item = inputQueue.shift();
      if (!valid(item.version, item.identity) || !connected || !state?.control_allowed || state.confirmation_open) {
        item.resolve.forEach(done => done(false)); pumpInput(); return;
      }
      const items=[item];
      if(state.input_batch && !legacyBatch && item.cmd.kind!=='drag') {
        let chars=Array.from(item.cmd.text||'').length;
        while(inputQueue.length && items.length<12) {
          const next=inputQueue[0];
          if(next.version!==item.version || next.identity!==item.identity || next.cmd.kind==='drag'
              || chars+Array.from(next.cmd.text||'').length>400)break;
          chars+=Array.from(next.cmd.text||'').length; items.push(inputQueue.shift());
        }
      }
      inputBusy = true;
      lastInputAt = Date.now(); inputAbort = new AbortController();
      const batch=items.length>1;
      try {
        await ctx.api(batch ? '/api/input/batch' : '/api/input', {method:'POST',body:JSON.stringify(batch ? {commands:items.map(i=>i.cmd)} : item.cmd),signal:inputAbort.signal});
        items.forEach(i=>i.resolve.forEach(done=>done(true)));
      }
      catch (err) {
        if(err.status===429 && valid(item.version,item.identity) && connected) {
          inputBlockedUntil=Date.now()+Math.max(1000,Math.min(60000,(err.retryAfter||2)*1000));
          inputQueue.unshift(...items); return;
        }
        if(batch && (err.status===404 || err.status===405) && valid(item.version,item.identity) && connected) {
          legacyBatch=true; inputQueue.unshift(...items); return;
        }
        if (err.name !== 'AbortError' && valid(item.version, item.identity)) { stop(); state = null; render(err.message || 'Controle interrompido.'); }
        items.forEach(i=>i.resolve.forEach(done=>done(false)));
      } finally { inputBusy = false; pumpInput(); }
    }
    function position(ev) {
      return imagePosition(frame.getBoundingClientRect(), image.naturalWidth, image.naturalHeight, ev.clientX, ev.clientY);
    }
    const cancelGesture = () => { clearTimeout(longTimer); clearTimeout(scrollTimer); scrollTimer=null; scrollX=0; scrollY=0; gesture = null; touches.clear(); scrollPoint = null; };
    const center = () => {
      const values = [...touches.values()];
      return {x: values.reduce((n,p)=>n+p.x,0)/values.length, y:values.reduce((n,p)=>n+p.y,0)/values.length};
    };
    function flushScroll() {
      clearTimeout(scrollTimer); scrollTimer=null;
      const factor=state?.precise_scroll ? 2.5 : 1/24;
      const limit=state?.precise_scroll ? 1200 : 10;
      const dx=Math.max(-limit,Math.min(limit,Math.trunc(scrollX*factor)));
      const dy=Math.max(-limit,Math.min(limit,Math.trunc(scrollY*factor)));
      if(!dx && !dy)return;
      scrollX-=dx/factor; scrollY-=dy/factor;
      send(state?.precise_scroll ? {kind:'wheel',delta_x:dx,delta_y:dy} : {kind:'scroll',dx,dy});
      if(Math.abs(scrollX*factor)>=1 || Math.abs(scrollY*factor)>=1)scrollTimer=setTimeout(flushScroll,35);
    }
    function addScroll(x,y) {
      scrollX+=x; scrollY+=y;
      if(!scrollTimer)scrollTimer=setTimeout(flushScroll,35);
    }
    frame.addEventListener('pointerdown', ev => {
      if (ev.target.closest('button') || !connected || !state?.control_allowed) return;
      const p = position(ev); if (!p) return;
      ev.preventDefault(); frame.setPointerCapture(ev.pointerId);
      touches.set(ev.pointerId, {x:ev.clientX, y:ev.clientY});
      if (touches.size > 1) {
        clearTimeout(longTimer); clearTimeout(tapTimer); pendingTap = null;
        gesture = null; scrollPoint = center(); scrollX=0; scrollY=0; return;
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
        const c = center();
        addScroll(scrollPoint.x-c.x, c.y-scrollPoint.y);
        scrollPoint=c;
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
      if(scrollPoint) flushScroll();
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
      const factor=ev.deltaMode===1 ? 16 : ev.deltaMode===2 ? frame.getBoundingClientRect().height : 1;
      addScroll(ev.deltaX*factor,-ev.deltaY*factor);
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
    $('remoteEnter').addEventListener('click', () => {flushKeys();send({kind:'key',key:'enter'});});
    $('remoteBackspace').addEventListener('click', () => send({kind:'key', key:'backspace'}));
    const keys = $('remoteKeys');
    $('keyboardButton').addEventListener('click', () => {
      keys.hidden=!keys.hidden;
      $('keyboardButton').setAttribute('aria-expanded',String(!keys.hidden));
      if(!keys.hidden) keys.focus(); else keys.blur();
    });
    function flushKeys() {
      if(composing || !keys.value || !connected || !state?.control_allowed)return;
      const chars=Array.from(keys.value);
      const capacity=Math.max(0,24-inputQueue.length)*200;
      const text=chars.splice(0,capacity); keys.value=chars.join('');
      for(let start=0;start<text.length;start+=200)send({kind:'text',text:text.slice(start,start+200).join('')});
      if(keys.value)ctx.notify('Parte do texto ficou no campo. Aguarde e envie o restante.');
    }
    keys.addEventListener('compositionstart',()=>{composing=true;});
    keys.addEventListener('compositionend',()=>{composing=false;flushKeys();});
    keys.addEventListener('input',ev=>{if(!ev.isComposing)flushKeys();});
    keys.addEventListener('beforeinput',ev=>{
      if(composing || ev.isComposing)return;
      if(!keys.value && ['deleteContentBackward','deleteContentForward'].includes(ev.inputType)) {
        ev.preventDefault();send({kind:'key',key:ev.inputType==='deleteContentBackward' ? 'backspace':'delete'});
      }
    });
    keys.addEventListener('keydown', ev => {
      if (ev.isComposing || composing) return;
      const named={Enter:'enter',Tab:'tab',Escape:'esc',ArrowLeft:'left',ArrowRight:'right',ArrowUp:'up',ArrowDown:'down'};
      if(named[ev.key]) {ev.preventDefault();flushKeys();send({kind:'key',key:named[ev.key]});}
      else if((ev.key==='Backspace' || ev.key==='Delete') && !keys.value) {
        ev.preventDefault();send({kind:'key',key:ev.key==='Backspace' ? 'backspace':'delete'});
      }
    });
    for(const [id,key] of [['remoteTab','tab'],['remoteEscape','esc'],['remoteDelete','delete']]) {
      $(id).addEventListener('click',()=>{flushKeys();send({kind:'key',key});});
    }
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
