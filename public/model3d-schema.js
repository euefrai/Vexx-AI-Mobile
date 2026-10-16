/* Small synchronous contract only. No GPU, engine import or model fetch here. */
'use strict';
window.validateModel3DInteraction = function (value, ids, count) {
  const defaults = {selected:'',hidden:[],isolated:'',exploded:false,transparent:[],view:'free',focus:'',step:0,speed:1,lessonPlaying:false};
  const fail = () => {throw Error('Estado ou parte 3D inválida');};
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).some(k => !Object.prototype.hasOwnProperty.call(defaults,k))) fail();
  const s = {...defaults,...value};
  for (const key of ['selected','isolated','focus']) if (typeof s[key] !== 'string' || (s[key] && !ids.includes(s[key]))) fail();
  for (const key of ['hidden','transparent']) if (!Array.isArray(s[key]) || s[key].length>32 || s[key].some(v => typeof v !== 'string' || !ids.includes(v)) || new Set(s[key]).size!==s[key].length) fail();
  if (!['free','front','back','side','top'].includes(s.view) || typeof s.exploded!=='boolean' || typeof s.lessonPlaying!=='boolean') fail();
  if (!Number.isInteger(s.step) || s.step<0 || s.step>=Math.max(count,1) || typeof s.speed!=='number' || !Number.isFinite(s.speed) || s.speed<.5 || s.speed>2 || (s.lessonPlaying && !count)) fail();
  return structuredClone(s);
};
window.validateModel3D = function (p) {
  const fail = () => { throw new Error('model3d: propriedade ou limite inválido'); };
  const obj = (v, keys) => { if (!v || typeof v !== 'object' || Array.isArray(v) || Object.keys(v).some(k => !keys.split(' ').includes(k))) fail(); return v; };
  const str = (v, n) => { if (typeof v !== 'string' || Array.from(v).length > n) fail(); return v; };
  const num = (v, a, b) => { if (typeof v !== 'number' || !Number.isFinite(v) || v < a || v > b) fail(); return v; };
  const vec = (v, a, b) => { if (!Array.isArray(v) || v.length !== 3) fail(); return v.map(n => num(n, a, b)); };
  const id = v => { if (typeof v !== 'string' || !/^[a-zA-Z0-9_-]{1,40}$/.test(v)) fail(); return v; };
  const bool = v => { if (typeof v !== 'boolean') fail(); return v; };
  const get = (v, k, d) => v[k] === undefined ? d : v[k];
  obj(p, 'id version title description objects model color scale rotation camera lighting annotations autoRotate details source education steps interaction');
  const education = get(p,'education','');
  if (!['','computer','geometry','solar'].includes(education) || (!education && ('steps' in p || 'interaction' in p))) fail();
  if (p.version !== 1) fail();
  const color = get(p, 'color', '#8b9cf7');
  if (typeof color !== 'string' || !/^#[a-fA-F0-9]{6}$/.test(color)) fail();
  const model = get(p, 'model', '');
  if (!['', 'demo-cube'].includes(model)) fail();
  const raw = get(p, 'objects', []), ids = new Set();
  if (!Array.isArray(raw) || raw.length < (model ? 0 : 1) || raw.length > (education ? 32 : 8) || (model && (raw.length || education))) fail();
  const objects = raw.map(o => {
    obj(o, 'id kind position rotation scale label description' + (education ? ' dimensions color category related metadata' : ''));
    const key = id(o.id);
    if (ids.has(key) || !['cube', 'sphere', 'cylinder', 'pyramid'].includes(o.kind)) fail();
    ids.add(key);
    const item = {id:key, kind:o.kind, position:vec(get(o, 'position', [0,0,0]), -3,3),
      rotation:vec(get(o, 'rotation', [0,0,0]), -360,360), scale:num(get(o, 'scale', 1), .25,2),
      label:str(get(o, 'label', o.kind),100), description:str(get(o, 'description', ''),500)};
    if (education) {
      const meta=obj(get(o,'metadata',{}),'conceptual note'), partColor=get(o,'color',color), category=get(o,'category','component');
      if (typeof partColor!=='string' || !/^#[a-fA-F0-9]{6}$/.test(partColor) || !['component','face','edge','vertex','body'].includes(category)) fail();
      Object.assign(item,{dimensions:vec(get(o,'dimensions',[1,1,1]),.015,3),color:partColor.toLowerCase(),category,
        related:get(o,'related',[]),metadata:{conceptual:bool(get(meta,'conceptual',true)),note:str(get(meta,'note',''),200)}});
    }
    return item;
  });
  if (model) ids.add('demo-cube');
  if (education) objects.forEach(o => {if (!Array.isArray(o.related) || o.related.length>8 || o.related.some(id=>typeof id!=='string' || !ids.has(id) || id===o.id) || new Set(o.related).size!==o.related.length) fail();});
  const rawNotes = get(p, 'annotations', []);
  if (!Array.isArray(rawNotes) || rawNotes.length > 8) fail();
  const annotations = rawNotes.map(a => {
    obj(a, 'objectId text'); if (!ids.has(a.objectId)) fail();
    return {objectId:a.objectId, text:str(a.text,300)};
  });
  const camera = obj(get(p, 'camera', {}), 'distance'), lighting = get(p, 'lighting', 'soft');
  if (!['soft', 'studio'].includes(lighting)) fail();
  const source = model ? 'Vexx AI — cubo GLB local original (CC0)' : 'Geometria procedural local';
  if (p.source !== undefined && p.source !== source) fail();
  const result = {id:id(p.id), version:1, title:str(get(p, 'title', 'Objeto 3D'),120),
    description:str(get(p, 'description', 'Objeto tridimensional interativo.'),500), objects, model,
    color:color.toLowerCase(), scale:num(get(p, 'scale',1),.25,2), rotation:vec(get(p, 'rotation',[15,25,0]),-360,360),
    camera:{distance:num(get(camera, 'distance',6),3,12)}, lighting, annotations,
    autoRotate:bool(get(p, 'autoRotate',false)), details:bool(get(p, 'details',false)), source};
  if (education) {
    const steps=get(p,'steps',[]);
    if (!Array.isArray(steps) || steps.length>8) fail();
    result.education=education;
    result.steps=steps.map(step => {
      obj(step,'title text selected view exploded');
      const s=window.validateModel3DInteraction(Object.fromEntries(['selected','view','exploded'].filter(k=>k in step).map(k=>[k,step[k]])),[...ids],0);
      return {title:str(get(step,'title','Etapa'),80),text:str(get(step,'text',''),400),selected:s.selected,view:s.view,exploded:s.exploded};
    });
    result.interaction=window.validateModel3DInteraction(get(p,'interaction',{}),[...ids],steps.length);
  }
  if (new TextEncoder().encode(JSON.stringify(result)).length > 20000) fail();
  return result;
};
