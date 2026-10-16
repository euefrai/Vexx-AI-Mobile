import * as T from './vendor/three-engine.js';

// One GPU context at a time. Kept out of the application shell and its precache.
let active = null;
const scope = (ctx, p) => ctx?.ownerId && ctx?.conversationId ? `${ctx.ownerId}/${ctx.conversationId}/${p.id}` : null;
window.addEventListener('vexx3d:mounted', event => {
  const {root, p, ctx, start} = event.detail;
  // A conversational command produces a new validated snapshot, not executable model code.
  if (active && active.scope && active.scope === scope(ctx,p) && active.root !== root && active.root.isConnected) start.click();
});
const clamp = (n, a, b) => Math.max(a, Math.min(b, n));
const radians = n => n * Math.PI / 180;
function element(tag, cls, text) {
  const e = document.createElement(tag); e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}
function disposeTree(tree) {
  tree.traverse(o => {
    o.geometry?.dispose();
    for (const m of (Array.isArray(o.material) ? o.material : [o.material])) {
      if (!m) continue;
      for (const value of Object.values(m)) if (value?.isTexture) value.dispose();
      m.dispose();
    }
  });
}
async function loadLocalModel(signal, progress) {
  const response = await fetch('/models/demo-cube.glb', {signal, credentials:'same-origin'});
  if (!response.ok || Number(response.headers.get('content-length')) > 65536) throw Error('model');
  const reader = response.body.getReader(), chunks = []; let size = 0;
  try {
    while (true) {
      const {value, done} = await reader.read(); if (done) break;
      size += value.length;
      if (size > 65536) throw Error('size');
      chunks.push(value); progress(size);
    }
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
  const bytes = new Uint8Array(size); let offset = 0;
  chunks.forEach(chunk => {bytes.set(chunk, offset); offset += chunk.length;});
  const view = new DataView(bytes.buffer);
  if (size < 20 || view.getUint32(0,true) !== 0x46546c67 || view.getUint32(4,true) !== 2 || view.getUint32(8,true) !== size || view.getUint32(16,true) !== 0x4e4f534a) throw Error('glb');
  const metadata = JSON.parse(new TextDecoder().decode(bytes.slice(20,20+view.getUint32(12,true))));
  // The catalog contains only our untextured GLB. Never let the loader fetch dependencies.
  function check(value) {
    if (!value || typeof value !== 'object') return;
    for (const [key, child] of Object.entries(value)) {
      if (key === 'uri' || key === 'images' || key === 'extensions') throw Error('dependency');
      check(child);
    }
  }
  check(metadata);
  if (metadata.extensionsRequired?.length || metadata.extensionsUsed?.length) throw Error('extension');
  return (await new T.GLTFLoader().parseAsync(bytes.buffer, '')).scene;
}

export async function mount(root, props, saved, save, preview, status, start, ctx) {
  const p = window.validateModel3D(props);
  active?.dispose();
  const abort = new AbortController(), listeners = [], scene = new T.Scene();
  let renderer, frame = 0, dead = false, visible = true, loaded = false;
  let resizeObserver, visibilityObserver, removalObserver, lastTime = 0, lastPaint = 0;
  const box = element('div','m3-live'), stage = element('div','m3-stage');
  const tools = element('div','m3-tools'), details = element('div','m3-details');
  const canvas = element('canvas','m3-canvas'); canvas.tabIndex = 0;
  canvas.setAttribute('aria-label', p.description + ' Setas giram; mais e menos ajustam o zoom.');
  stage.append(canvas); box.append(stage, tools, details); root.append(box);
  const group = new T.Group(), content = new T.Group(); group.add(content); scene.add(group);
  const camera = new T.PerspectiveCamera(40,1,.1,100);
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const defaultView = {rotation:p.rotation.map(radians), distance:p.camera.distance, playing:p.autoRotate && !reduced.matches};
  let rotation = defaultView.rotation.slice(), distance = defaultView.distance, playing = defaultView.playing;
  if (saved && Array.isArray(saved.rotation) && saved.rotation.length === 3 && saved.rotation.every(n => typeof n === 'number' && Number.isFinite(n))) rotation = saved.rotation.map(n => clamp(n,-Math.PI*2,Math.PI*2));
  if (typeof saved?.distance === 'number' && Number.isFinite(saved.distance)) distance = clamp(saved.distance,3,12);
  if (typeof saved?.playing === 'boolean') playing = saved.playing && !reduced.matches;
  let selected = '', detailsOpen = p.details, pointer = null;
  const ray = new T.Raycaster(), coords = new T.Vector2();
  function listen(target,event,fn,opts) {target.addEventListener(event,fn,opts); listeners.push(() => target.removeEventListener(event,fn,opts));}
  function persist() { if (!dead) save({rotation:rotation.slice(),distance,playing}); }
  const controller = {
    root, scope:scope(ctx,p),
    dispose() {
      if (dead) return;
      persist(); dead = true; abort.abort(); cancelAnimationFrame(frame);
      listeners.forEach(off => off()); resizeObserver?.disconnect(); visibilityObserver?.disconnect(); removalObserver?.disconnect();
      disposeTree(scene); renderer?.dispose(); renderer?.forceContextLoss(); box.remove();
      preview.hidden = false; start.hidden = false;
      status.textContent = 'Visualizador liberado. Abra novamente para explorar.';
      if (active === controller) active = null;
    }
  };
  active = controller;
  function paint(now = performance.now()) {
    frame = 0;
    if (dead || !loaded || !visible || document.hidden) {lastTime = 0; return;}
    if (playing && lastTime) rotation[1] = (rotation[1] + Math.min((now-lastTime)/1000,.1)*.35) % (Math.PI*2);
    lastTime = now;
    group.rotation.set(...rotation); camera.position.set(0,0,distance); camera.lookAt(0,0,0);
    if (!playing || now-lastPaint >= 32) {renderer.render(scene,camera); lastPaint = now;}
    if (playing) frame = requestAnimationFrame(paint);
  }
  function draw() {if (!dead && !frame) frame = requestAnimationFrame(paint);}
  function button(label, fn) {
    const b = element('button','jdui-btn',label); b.type = 'button';
    listen(b,'click',fn); tools.append(b); return b;
  }
  function updateDetails() {
    details.replaceChildren(); details.hidden = !detailsOpen;
    if (!detailsOpen) return;
    const items = p.model ? [{id:'demo-cube',label:'Cubo GLB',description:'Modelo geométrico local original, sem texturas.'}] : p.objects;
    for (const item of items) {
      const b = element('button','m3-part',item.label); b.type = 'button';
      b.setAttribute('aria-pressed', String(selected === item.id));
      b.onclick = () => {selected = item.id; updateDetails(); highlight();};
      details.append(b);
      if (!selected || selected === item.id) {
        details.append(element('p','',item.description || 'Sem descrição adicional.'));
        p.annotations.filter(a => a.objectId === item.id).forEach(a => details.append(element('p','',a.text)));
      }
    }
    details.append(element('small','',p.source));
  }
  function highlight() {
    content.traverse(o => {if (o.isMesh && o.material.emissive) o.material.emissive.setHex(o.userData.objectId === selected ? 0x222244 : 0);}); draw();
  }
  const pause = button(playing ? 'Pausar' : 'Animar', () => {playing = !playing; pause.textContent = playing ? 'Pausar' : 'Animar'; persist(); draw();});
  function zoom(factor) {distance = clamp(distance*factor,3,12); persist(); draw();}
  button('Ampliar', () => zoom(.8)); button('Reduzir', () => zoom(1.25));
  button('Centralizar', () => {distance = defaultView.distance; persist(); draw();});
  button('Restaurar', () => {rotation = defaultView.rotation.slice(); distance = defaultView.distance; playing = defaultView.playing; selected = ''; pause.textContent = playing ? 'Pausar' : 'Animar'; persist(); updateDetails(); highlight();});
  button('Detalhes', () => {detailsOpen = !detailsOpen; updateDetails();});
  const expand = button('Tela ampliada', () => {const value = box.classList.toggle('m3-expanded'); expand.textContent = value ? 'Recolher' : 'Tela ampliada'; expand.setAttribute('aria-expanded',String(value)); size();});
  expand.setAttribute('aria-expanded','false');
  function size() {
    if (!renderer || dead) return;
    const rect = stage.getBoundingClientRect(), width = Math.max(1,Math.min(rect.width,1200)), height = Math.max(1,Math.min(rect.height,640));
    renderer.setPixelRatio(Math.min(devicePixelRatio || 1,1.5,900/width));
    renderer.setSize(width,height,false); camera.aspect = width/height; camera.updateProjectionMatrix(); draw();
  }
  listen(canvas,'pointerdown',e => {if (e.button !== 0) return; pointer = {id:e.pointerId,x:e.clientX,y:e.clientY,moved:0}; canvas.setPointerCapture(e.pointerId);});
  listen(canvas,'pointermove',e => {
    if (!pointer || pointer.id !== e.pointerId) return;
    const dx = e.clientX-pointer.x, dy = e.clientY-pointer.y;
    rotation[1] += dx*.009; rotation[0] = clamp(rotation[0]+dy*.009,-Math.PI/2,Math.PI/2);
    pointer.x = e.clientX; pointer.y = e.clientY; pointer.moved += Math.abs(dx)+Math.abs(dy); draw();
  });
  listen(canvas,'pointerup',e => {
    if (!pointer || pointer.id !== e.pointerId) return;
    if (pointer.moved < 5 && loaded) {
      const r = canvas.getBoundingClientRect(); coords.set((e.clientX-r.left)/r.width*2-1,-(e.clientY-r.top)/r.height*2+1);
      ray.setFromCamera(coords,camera); const hit = ray.intersectObjects(content.children,true)[0];
      if (hit) {selected = hit.object.userData.objectId; detailsOpen = true; updateDetails(); highlight();}
    }
    pointer = null; persist();
  });
  listen(canvas,'pointercancel',() => {pointer = null; persist();});
  listen(canvas,'wheel',e => {e.preventDefault(); zoom(e.deltaY > 0 ? 1.1 : .9);},{passive:false});
  listen(canvas,'keydown',e => {
    if (e.key === '+' || e.key === '=') zoom(.8);
    else if (e.key === '-') zoom(1.25);
    else if (e.key.startsWith('Arrow')) {
      if (e.key === 'ArrowLeft') rotation[1] -= .15;
      if (e.key === 'ArrowRight') rotation[1] += .15;
      if (e.key === 'ArrowUp') rotation[0] -= .15;
      if (e.key === 'ArrowDown') rotation[0] += .15;
      persist(); draw();
    } else return;
    e.preventDefault();
  });
  listen(document,'visibilitychange',() => {if (document.hidden) {cancelAnimationFrame(frame); frame = 0; lastTime = 0;} else draw();});
  listen(reduced,'change',() => {if (reduced.matches) {playing = false; pause.textContent = 'Animar'; persist(); draw();}});
  listen(canvas,'webglcontextlost',e => {e.preventDefault(); controller.dispose(); status.textContent = 'A renderização 3D foi interrompida. Preview 2D disponível; tente abrir novamente.';});
  removalObserver = new MutationObserver(() => {if (!root.isConnected) controller.dispose();});
  removalObserver.observe(document.body,{childList:true,subtree:true});
  try {
    renderer = new T.WebGLRenderer({canvas,antialias:false,alpha:true,powerPreference:'low-power'});
    scene.add(new T.HemisphereLight(0xffffff,0x343449,p.lighting === 'studio' ? 2.5 : 2));
    const light = new T.DirectionalLight(0xffffff,2); light.position.set(3,5,4); scene.add(light);
    if (p.model) {
      status.textContent = 'Carregando modelo local…';
      const glb = await loadLocalModel(abort.signal,n => {status.textContent = `Carregando modelo: ${n} bytes recebidos…`;});
      if (dead || !root.isConnected) {disposeTree(glb); controller.dispose(); return;}
      glb.traverse(o => {if (o.isMesh) {o.userData.objectId = 'demo-cube'; o.material.color.set(p.color);}}); content.add(glb);
    } else {
      for (const item of p.objects) {
        const geometry = item.kind === 'cube' ? new T.BoxGeometry(1.3,1.3,1.3) : item.kind === 'sphere' ? new T.SphereGeometry(.8,20,12) : item.kind === 'cylinder' ? new T.CylinderGeometry(.65,.65,1.5,20) : new T.ConeGeometry(.95,1.5,4);
        const mesh = new T.Mesh(geometry,new T.MeshStandardMaterial({color:p.color,roughness:.6,metalness:.05}));
        mesh.position.set(...item.position); mesh.rotation.set(...item.rotation.map(radians)); mesh.scale.setScalar(item.scale);
        mesh.userData.objectId = item.id; content.add(mesh);
      }
    }
    const bounds = new T.Box3().setFromObject(content), center = bounds.getCenter(new T.Vector3()), extent = bounds.getSize(new T.Vector3());
    // Fit the diagonal so a rotated cube is not clipped in the initial camera view.
    const fit = 2.5/Math.max(extent.length(),.1);
    content.position.copy(center).multiplyScalar(-fit*p.scale); content.scale.setScalar(fit*p.scale);
    loaded = true; preview.hidden = true; start.hidden = true;
    status.textContent = 'Arraste para girar · selecione uma parte · zoom pelos botões';
    resizeObserver = new ResizeObserver(size); resizeObserver.observe(stage);
    visibilityObserver = new IntersectionObserver(entries => {visible = entries[0].isIntersecting; if (!visible) {cancelAnimationFrame(frame); frame = 0; lastTime = 0;} else draw();});
    visibilityObserver.observe(stage); size(); updateDetails(); draw();
  } catch (error) {
    if (!dead) {controller.dispose(); status.textContent = '3D indisponível. Use o preview 2D e a descrição; você pode tentar novamente.';}
  }
  return controller;
}
