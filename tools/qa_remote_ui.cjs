/* Real browser + local static server, explicitly simulated API/desktop frames.
   No native consent or mouse/keyboard execution is claimed by this UI harness. */
async page => {
  if (!page.url().startsWith('http://127.0.0.1:')) throw Error('Disposable loopback QA only');
  const base = new URL(page.url()).origin;
  const browser = page.context().browser();
  const result = {scope:'REAL_CHROME_SIMULATED_API_AND_FRAME_NOT_PHYSICAL_PHONE', checks:[], errors:[]};
  let state = {device_name:'PC de teste',platform:'Windows',supported:true,capture_ready:true,
    approved:false,view_allowed:false,control_allowed:false,pending:false,confirmation_open:false,code:''};
  const requests = [];
  const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="960" height="540"><rect width="960" height="540" fill="#1b1b20"/><text x="480" y="270" text-anchor="middle" fill="white" font-size="22">Tela simulada para teste de interface</text></svg>';
  // JPEG produced with the browser canvas below; never capture the operator screen.
  let jpeg;
  async function configure(context) {
    await context.route('**/api/**', async route => {
      const path = new URL(route.request().url()).pathname;
      requests.push({path,method:route.request().method(),body:route.request().postData()});
      let body = {};
      if (path === '/api/session' || path === '/api/account') body={uid:'u-remote-qa',username:'remote-qa',display:'Teste QA',role:'user',csrf:'qa-csrf'};
      if (path === '/api/auth/config') body={modo:'aberto',exigir_aprovacao:false};
      if (path === '/api/status') body={pc_online:true,agente_ha:0};
      if (path === '/api/diag') body={agente_ha:0};
      if (path === '/api/workspace/sync') body={records:[]};
      if (path === '/api/history') body={messages:[]};
      if (path === '/api/ui-state') body={states:[]};
      if (path === '/api/ai/models') body={models:[],items:[],providers:[]};
      if (path === '/api/docs') body={documents:[]};
      if (path === '/api/remote/status') body=state;
      if (path === '/api/remote/request') {
        state={...state,pending:true,confirmation_open:true,code:'123456'}; body=state;
      }
      if (path === '/api/remote/revoke') {
        state={...state,approved:false,view_allowed:false,control_allowed:false,pending:false,confirmation_open:false,code:''}; body=state;
      }
      if (path === '/api/screen') body={imagem:jpeg,largura:960,altura:540,remote_enabled:state.control_allowed};
      if (path === '/api/input') body={ok:true};
      await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});
    });
  }
  async function ready(p) {
    p.on('pageerror', err=>result.errors.push(err.message));
    p.on('console', msg=>{if(msg.type()==='error')result.errors.push(msg.text());});
    await p.goto(base);
    await p.locator('#loginOverlay').waitFor({state:'hidden'});
  }
  function check(name, condition) {
    if(!condition)throw Error(name); result.checks.push(name);
  }
  await page.setViewportSize({width:1280,height:900});
  await configure(page.context());
  await ready(page);
  jpeg=await page.evaluate(async svg=>{
    const im=new Image();im.src='data:image/svg+xml;base64,'+btoa(svg);await im.decode();
    const c=document.createElement('canvas');c.width=960;c.height=540;c.getContext('2d').drawImage(im,0,0);
    return c.toDataURL('image/jpeg').split(',')[1];
  },svg);
  await page.getByRole('button',{name:'Meu PC',exact:true}).click();
  await page.locator('#remotePermit').waitFor({state:'visible'});
  await page.waitForFunction(()=>!document.getElementById('remotePermit').disabled);
  check('Desktop shows preparation before connecting',await page.locator('#pcSetup').isVisible() && !await page.locator('#remoteViewer').isVisible());
  check('Desktop does not request screen frames',!requests.some(r=>r.path==='/api/screen'));
  await page.locator('#remotePermit').click();
  await page.waitForFunction(()=>document.getElementById('remoteAccessStatus').textContent.includes('123456'));
  check('Request displays local confirmation code',await page.locator('#remotePermit').isDisabled());
  state={...state,approved:true,view_allowed:true,control_allowed:true,pending:false,confirmation_open:false,code:''};
  // Navigate out/back to read the changed consent through the ordinary status path.
  await page.evaluate(()=>navigate('chat'));
  await page.evaluate(()=>navigate('desktop'));
  await page.waitForFunction(()=>document.getElementById('remotePermit').textContent==='Acesso permitido');
  check('Device is online in Meu PC',await page.locator('#deviceStatus').textContent()==='Online');
  check('Desktop can connect too',!await page.locator('#remoteConnect').isDisabled());
  await page.locator('#remoteConnect').click();
  await page.waitForFunction(()=>document.getElementById('screenImg').naturalWidth===960);
  await page.waitForTimeout(900);
  check('Compatibility frames arrive faster than old 1.6 second timer',requests.filter(r=>r.path==='/api/screen').length>=4);
  await page.locator('#remoteDisconnect').click();
  await page.screenshot({path:'output/playwright/remote-access/desktop.png'});
  await page.setViewportSize({width:390,height:844});
  check('Resizing desktop does not turn it into a phone',await page.locator('#pcSetup').isVisible());
  const mobile=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true,
    userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1'});
  try {
    await configure(mobile);
    // Simulated continuous response exercises browser framing and cancellation;
    // backend authentication/revocation are covered separately by Python tests.
    await mobile.addInitScript(() => {
      const original = window.fetch.bind(window);
      window.fetch = async (url, options = {}) => {
        if (String(url).split('?')[0] !== '/api/screen/stream') return original(url, options);
        const encoder = new TextEncoder(); let cancelled = false;
        window.__streamStarts = (window.__streamStarts || 0) + 1;
        const body = new ReadableStream({
          async pull(controller) {
            await new Promise(done => setTimeout(done, 125));
            if (cancelled || options.signal?.aborted) { controller.close(); return; }
            let data;
            if (window.__denyRemoteStream) data = {error:'Acesso revogado no PC', status:403};
            else data = await (await original('/api/screen', options)).json();
            const line = encoder.encode(JSON.stringify(data) + '\n');
            controller.enqueue(line.slice(0, 17)); controller.enqueue(line.slice(17));
          },
          cancel() { cancelled = true; }
        });
        return new Response(body, {headers:{'Content-Type':'application/x-ndjson'}});
      };
    });
    const phone=await mobile.newPage();await ready(phone);
    await phone.getByRole('button',{name:'Abrir menu',exact:true}).click();
    await phone.getByRole('button',{name:'Meu PC',exact:true}).click();
    await phone.waitForFunction(()=>!document.getElementById('remoteConnect').disabled);
    check('Phone shows connect and hides host preparation',await phone.locator('#pcConnect').isVisible() && !await phone.locator('#pcSetup').isVisible());
    await phone.screenshot({path:'output/playwright/remote-access/phone-ready.png'});
    await phone.locator('#remoteConnect').click();
    await phone.waitForFunction(()=>document.getElementById('screenImg').naturalWidth===960);
    check('Phone loads screen only after connecting',await phone.locator('#remoteViewer').isVisible());
    await phone.locator('#remoteFrame').tap();
    await phone.waitForFunction(()=>document.getElementById('screenImg').naturalWidth===960);
    // Allow the relay pacing timer; this is a UI command-routing assertion.
    await phone.waitForTimeout(700);
    check('Touch sends one left click',requests.filter(r=>r.path==='/api/input'&&JSON.parse(r.body).kind==='click').length===1);
    await phone.locator('#keyboardButton').click();
    await phone.locator('#remoteKeys').fill('ação á 🚀');
    await phone.waitForTimeout(700);
    check('Visible keyboard field',await phone.locator('#remoteKeys').isVisible());
    check('Unicode text routes intact',requests.some(r=>r.path==='/api/input'&&JSON.parse(r.body).text==='ação á 🚀'));
    await phone.locator('#remoteKeys').fill('abc'.repeat(150));
    await phone.waitForTimeout(500);
    const text= requests.filter(r=>r.path==='/api/input').map(r=>JSON.parse(r.body)).filter(c=>c.kind==='text').map(c=>c.text).join('');
    check('Long pasted text is not truncated',text.includes('abc'.repeat(150)));
    await phone.locator('#remoteKeys').press('ArrowLeft');
    await phone.locator('#remoteTab').click();
    await phone.waitForTimeout(300);
    check('Arrow and Tab reach remote keyboard',requests.some(r=>r.path==='/api/input'&&JSON.parse(r.body).key==='left') && requests.some(r=>r.path==='/api/input'&&JSON.parse(r.body).key==='tab'));
    for(const width of [390,320]){
      await phone.setViewportSize({width,height:844});
      check('No overflow at '+width,await phone.evaluate(()=>document.documentElement.scrollWidth<=innerWidth && document.getElementById('page-desktop').scrollWidth<=document.getElementById('page-desktop').clientWidth+1));
      await phone.screenshot({path:'output/playwright/remote-access/phone-connected-'+width+'.png'});
    }
    check('Continuous transport is used',await phone.evaluate(()=>window.__streamStarts===1));
    await phone.evaluate(()=>window.__denyRemoteStream=true);
    await phone.locator('#remoteViewer').waitFor({state:'hidden'});
    check('Mid-stream denial stops viewer and keyboard',await phone.locator('#remoteKeys').isDisabled());
    await phone.evaluate(()=>window.__denyRemoteStream=false);
    await phone.locator('#remoteConnect').click();
    await phone.waitForFunction(()=>document.getElementById('screenImg').naturalWidth===960);
    await phone.locator('#remoteDisconnect').click();
    check('Disconnect clears the screen',await phone.locator('#screenImg').getAttribute('src')===null);
    await phone.reload();await phone.locator('#loginOverlay').waitFor({state:'hidden'});
    await phone.getByRole('button',{name:'Abrir menu',exact:true}).click();
    await phone.getByRole('button',{name:'Meu PC',exact:true}).click();
    await phone.waitForFunction(()=>!document.getElementById('remoteConnect').disabled);
    check('Reload retains account access without auto-connecting',!await phone.locator('#remoteViewer').isVisible());
    await phone.locator('#remoteRevoke').click();
    await phone.locator('#remoteRevoke').waitFor({state:'hidden'});
    check('Revoke disables connection',await phone.locator('#remoteRevoke').isHidden());
    await phone.screenshot({path:'output/playwright/remote-access/phone-revoked.png'});
  } finally {await mobile.close();}
  check('No browser errors',result.errors.length===0);
  return result;
}
