/* Real browser + real static/CSP server, explicitly simulated API/desktop frames.
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
  check('Desktop shows preparation, hides controller',await page.locator('#pcSetup').isVisible() && !await page.locator('#remoteViewer').isVisible());
  check('Desktop does not request screen frames',!requests.some(r=>r.path==='/api/screen'));
  await page.locator('#remotePermit').click();
  await page.waitForFunction(()=>document.getElementById('remoteAccessStatus').textContent.includes('123456'));
  check('Request displays local confirmation code',await page.locator('#remotePermit').isDisabled());
  state={...state,approved:true,view_allowed:true,control_allowed:true,pending:false,confirmation_open:false,code:''};
  // Navigate out/back to read the changed consent through the ordinary status path.
  await page.evaluate(()=>navigate('chat'));
  await page.evaluate(()=>navigate('desktop'));
  await page.waitForFunction(()=>document.getElementById('remotePermit').textContent==='Acesso permitido');
  await page.screenshot({path:'output/playwright/remote-access/desktop.png'});
  await page.setViewportSize({width:390,height:844});
  check('Resizing desktop does not turn it into a phone',await page.locator('#pcSetup').isVisible());
  const mobile=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true,
    userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1'});
  try {
    await configure(mobile);const phone=await mobile.newPage();await ready(phone);
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
    check('Unicode text routes intact',requests.some(r=>r.path==='/api/input'&&JSON.parse(r.body).text==='ação á 🚀'));
    for(const width of [390,320]){
      await phone.setViewportSize({width,height:844});
      check('No overflow at '+width,await phone.evaluate(()=>document.documentElement.scrollWidth<=innerWidth && document.getElementById('page-desktop').scrollWidth<=document.getElementById('page-desktop').clientWidth+1));
      await phone.screenshot({path:'output/playwright/remote-access/phone-connected-'+width+'.png'});
    }
    await phone.locator('#remoteDisconnect').click();
    check('Disconnect clears the screen',await phone.locator('#screenImg').getAttribute('src')===null);
    await phone.reload();await phone.locator('#loginOverlay').waitFor({state:'hidden'});
    await phone.getByRole('button',{name:'Abrir menu',exact:true}).click();
    await phone.getByRole('button',{name:'Meu PC',exact:true}).click();
    await phone.waitForFunction(()=>!document.getElementById('remoteConnect').disabled);
    check('Reload retains account access without auto-connecting',!await phone.locator('#remoteViewer').isVisible());
    await phone.locator('#remoteRevoke').click();
    await phone.waitForFunction(()=>document.getElementById('remoteConnect').disabled);
    check('Revoke disables connection',await phone.locator('#remoteRevoke').isHidden());
    await phone.screenshot({path:'output/playwright/remote-access/phone-revoked.png'});
  } finally {await mobile.close();}
  check('No browser errors',result.errors.length===0);
  return result;
}
