"""Owned headless Chrome, emulated mobile, simulated screen/input endpoint."""
import json, tempfile, threading, subprocess, time, urllib.request, re, io, os, base64
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from websockets.sync.client import connect
from PIL import Image, ImageDraw
ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'qa-artifacts/remote-touchpad-browser';ART.mkdir(exist_ok=True)
source=(ROOT/'public/remote.js').read_text(encoding='utf-8')
csp=re.search(r'response.headers\["Content-Security-Policy"\] = "([^"]+)"',(ROOT/'server.py').read_text(encoding='utf-8'))[1]
ids=set(re.findall(r"\$\('([a-zA-Z0-9]+)'\)",source))|{'remoteEnter','remoteBackspace','remoteScrollUp','remoteScrollDown','remoteTab','remoteEscape','remoteDelete','keyboardButton','screenImg','remoteFrame','page-desktop'}
index=(ROOT/'public/index.html').read_text(encoding='utf-8')
viewer=index[index.index('<div id="remoteViewer" hidden>'):index.index('<div class="access-card">',index.index('<div id="remoteViewer" hidden>'))]
viewer_ids=set(re.findall(r'id="([a-zA-Z0-9]+)"',viewer))
markup=''.join(f'<div id="{id}"></div>' for id in ids-viewer_ids)+viewer
js='''
window.commands=[];window.arrivals=[];window.frameUrls=[];
const $=id=>document.getElementById(id);
const context={authenticated:()=>true,online:()=>true,identity:()=> 'qa',headers:()=>({}),notify(){},
 api:async(path,options)=>{if(path.includes('/status'))return {approved:true,view_allowed:true,control_allowed:true,capture_ready:true,supported:true,input_batch:true,precise_scroll:true};
 if(path.startsWith('/api/input'))commands.push(JSON.parse(options.body));return {};},
 frame:async(path,opts)=>{frameUrls.push(path);const response=await fetch('/frame',opts);arrivals.push(performance.now());
 return {blob:await response.blob(),largura:1280,altura:720,remote_enabled:true,cursor:{x:.5,y:.5}};}};
window.remote=VexxRemote.mount(context);remote.update();
setTimeout(()=>$('remoteConnect').click(),100);
'''
html=('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{margin:0;background:#18181b;color:white}#remoteFrame{position:relative;width:100%;aspect-ratio:16/9;touch-action:none}#screenImg{width:100%;height:100%;object-fit:contain}#remotePointer{position:absolute;width:10px;height:10px;border-radius:50%;background:black;border:2px solid white;transform:translate(-50%,-50%);pointer-events:none}#remoteKeys{font-size:16px;width:90%}</style>'+markup+'<script src="/remote.js"></script><script>'+js+'</script>').encode()
# Exercise the actual production CSP: fixture code/styles also use external assets.
html_text=html.decode('utf-8')
css=re.search(r'<style>(.*?)</style>',html_text)[1]+'\n'+(ROOT/'public/styles.css').read_text(encoding='utf-8')+'\n'+(ROOT/'public/interface.css').read_text(encoding='utf-8')
html_text=re.sub(r'<style>.*?</style>','<link rel="stylesheet" href="/qa.css">',html_text)
html_text=html_text.replace('<script>'+js+'</script>','<script src="/qa.js"></script>')
html=html_text.encode('utf-8')
image=Image.new('RGB',(1280,720),'#25252a');draw=ImageDraw.Draw(image);draw.text((40,40),'VEXX REMOTE QA - SYNTHETIC SCREEN',(255,255,255));buffer=io.BytesIO();image.save(buffer,'JPEG',quality=72);jpeg=buffer.getvalue()
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  if self.path=='/remote.js':data=source.encode();ctype='application/javascript'
  elif self.path=='/qa.js':data=js.encode();ctype='application/javascript'
  elif self.path=='/qa.css':data=css.encode();ctype='text/css'
  elif self.path=='/frame':time.sleep(.04);data=jpeg;ctype='image/jpeg'
  elif self.path.startswith('/favicon'):self.send_response(204);self.end_headers();return
  else:data=html;ctype='text/html'
  self.send_response(200);self.send_header('Content-Security-Policy',csp);self.send_header('Content-Type',ctype+'; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.end_headers()
  try:self.wfile.write(data)
  except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
 def log_message(self,*a):pass
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
with tempfile.TemporaryDirectory(prefix='vexx-remote-browser-') as td:
 chrome=subprocess.Popen([r'C:/Program Files/Google/Chrome/Application/chrome.exe','--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--user-data-dir='+td,'about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 ws=None
 try:
  portfile=Path(td)/'DevToolsActivePort';deadline=time.monotonic()+15
  while not portfile.exists() and time.monotonic()<deadline:time.sleep(.1)
  debug=int(portfile.read_text().splitlines()[0])
  tabs=json.load(urllib.request.urlopen(f'http://127.0.0.1:{debug}/json'))
  ws=connect(next(t for t in tabs if t.get('type')=='page')['webSocketDebuggerUrl'],max_size=8_000_000,legacy=True)
  sequence=0;errors=[]
  def cmd(method,params=None):
   global sequence
   sequence+=1;idx=sequence;ws.send(json.dumps({'id':idx,'method':method,'params':params or {}}))
   while True:
    reply=json.loads(ws.recv(timeout=15))
    if reply.get('method')=='Runtime.exceptionThrown':errors.append(reply['params'])
    if reply.get('id')==idx:
     if 'error' in reply:raise AssertionError(reply['error'])
     return reply.get('result',{})
  def evaluate(expression):
   result=cmd('Runtime.evaluate',{'expression':expression,'returnByValue':True,'awaitPromise':True,'userGesture':True})
   assert 'exceptionDetails' not in result,result
   return result.get('result',{}).get('value')
  cmd('Runtime.enable');cmd('Page.enable')
  cmd('Emulation.setDeviceMetricsOverride',{'width':390,'height':844,'deviceScaleFactor':2,'mobile':True})
  cmd('Emulation.setTouchEmulationEnabled',{'enabled':True,'maxTouchPoints':5})
  cmd('Emulation.setUserAgentOverride',{'userAgent':'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/130 Mobile Safari/537.36'})
  cmd('Page.navigate',{'url':f'http://127.0.0.1:{server.server_port}/'})
  deadline=time.monotonic()+10
  while time.monotonic()<deadline:
   if evaluate('window.arrivals?.length||0')>=12:break
   time.sleep(.15)
  if evaluate('window.arrivals?.length||0')<12:print(evaluate('JSON.stringify({url:location.href,body:document.body?.innerHTML.slice(0,1000)})'),flush=True)
  assert evaluate('document.getElementById("screenImg").naturalWidth')==1280
  assert evaluate('document.getElementById("remotePointer").style.display')=='block'
  rect=evaluate('(()=>{let r=document.getElementById("remoteFrame").getBoundingClientRect();return {top:r.top,left:r.left,width:r.width,height:r.height}})()')
  def point(id,x,y):return {'id':id,'x':rect['left']+x,'y':rect['top']+y}
  cmd('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[point(1,100,70),point(2,180,70)]})
  for y in [74,80,86]:cmd('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[point(1,100,y),point(2,180,y)]})
  cmd('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]});time.sleep(.3)
  assert evaluate('commands.flatMap(c=>c.commands||[c]).some(c=>c.kind==="wheel")')
  evaluate('document.getElementById("touchMode").click()')
  cmd('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[point(1,100,70)]})
  cmd('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[point(1,140,90)]})
  time.sleep(.15)
  assert evaluate('commands.flatMap(c=>c.commands||[c]).some(c=>c.kind==="move")')
  cmd('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
  evaluate('document.getElementById("remoteQuality").value="sharp"')
  time.sleep(.3)
  assert evaluate('frameUrls.some(u=>u.includes("max_w=1920&q=85"))')
  evaluate('document.getElementById("remoteQuality").value="fast"')
  time.sleep(.3)
  assert evaluate('frameUrls.some(u=>u.includes("max_w=960&q=65"))')
  evaluate('document.getElementById("keyboardButton").click()')
  cmd('Input.insertText',{'text':'Olá 🚀\nsegunda linha'})
  time.sleep(.3)
  assert evaluate('commands.flatMap(c=>c.commands||[c]).filter(c=>c.kind==="text").map(c=>c.text).join("")')=='Olá 🚀\nsegunda linha'
  # Simulated viewport reduction, not a physical Android/iOS soft keyboard.
  cmd('Emulation.setDeviceMetricsOverride',{'width':390,'height':420,'deviceScaleFactor':2,'mobile':True})
  time.sleep(.2)
  geometry=evaluate('(()=>{const r=id=>{let b=document.getElementById(id).getBoundingClientRect();return {top:b.top,bottom:b.bottom,width:b.width,height:b.height}};return {viewer:r("remoteViewer"),frame:r("remoteFrame"),keys:r("remoteKeys"),viewport:visualViewport.height}})()')
  assert geometry['keys']['bottom']<=geometry['viewport'],geometry
  assert geometry['frame']['height']>80,geometry
  assert geometry['frame']['bottom']<=geometry['keys']['top'],geometry
  assert geometry['viewer']['width']<=390,geometry
  cmd('Emulation.setDeviceMetricsOverride',{'width':320,'height':320,'deviceScaleFactor':2,'mobile':True})
  time.sleep(.2)
  assert evaluate('document.getElementById("remoteKeys").getBoundingClientRect().bottom<=visualViewport.height')
  assert evaluate('document.getElementById("remoteFrame").getBoundingClientRect().height>40')
  assert evaluate('document.getElementById("remoteViewer").getBoundingClientRect().width<=320')
  evaluate('document.getElementById("keyboardButton").click()')
  assert evaluate('document.getElementById("remoteKeys").hidden && !document.getElementById("remoteViewer").classList.contains("keyboard-open")')
  evaluate('document.getElementById("keyboardButton").click()')
  cmd('Emulation.setDeviceMetricsOverride',{'width':390,'height':420,'deviceScaleFactor':2,'mobile':True})
  time.sleep(.2)
  arrivals=evaluate('arrivals');fps=(len(arrivals)-1)*1000/(arrivals[-1]-arrivals[0])
  shot=cmd('Page.captureScreenshot',{'format':'png'})['data'];(ART/'mobile-component.png').write_bytes(base64.b64decode(shot))
  evaluate('document.getElementById("remoteDisconnect").click()')
  assert evaluate('document.getElementById("screenImg").hasAttribute("src")') is False
  assert not errors,errors
  result={'scope':'REAL_CHROME_MOBILE_EMULATION_SYNTHETIC_FRAME_SIMULATED_INPUT_NOT_PHYSICAL_PHONE','frames':len(arrivals),'observed_fps':round(fps,2),'server_simulated_delay_ms':40,'checks':['binary JPEG decoded','cursor visible','native touch events produced wheel','browser text input preserved accents emoji newline','disconnect removed image','touchpad sends movement before finger release','sharp and fast profiles requested','420px viewport keeps screen and keyboard field visible'],'keyboard_layout':geometry,'page_errors':errors,'production_csp_enforced':csp}
  (ART/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
 finally:
  if ws:
   try:cmd('Browser.close')
   except Exception:pass
   ws.close()
  try:chrome.wait(timeout=5)
  except subprocess.TimeoutExpired:chrome.terminate();chrome.wait(timeout=5)
  server.shutdown()
