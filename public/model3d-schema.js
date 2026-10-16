/* Small synchronous contract only. No GPU, engine import or model fetch here. */
'use strict';
window.validateModel3D = function (p) {
  const fail = () => { throw new Error('model3d: propriedade ou limite inválido'); };
  const obj = (v, keys) => { if (!v || typeof v !== 'object' || Array.isArray(v) || Object.keys(v).some(k => !keys.split(' ').includes(k))) fail(); return v; };
  const str = (v, n) => { if (typeof v !== 'string' || Array.from(v).length > n) fail(); return v; };
  const num = (v, a, b) => { if (typeof v !== 'number' || !Number.isFinite(v) || v < a || v > b) fail(); return v; };
  const vec = (v, a, b) => { if (!Array.isArray(v) || v.length !== 3) fail(); return v.map(n => num(n, a, b)); };
  const id = v => { if (typeof v !== 'string' || !/^[a-zA-Z0-9_-]{1,40}$/.test(v)) fail(); return v; };
  const bool = v => { if (typeof v !== 'boolean') fail(); return v; };
  const get = (v, k, d) => v[k] === undefined ? d : v[k];
  obj(p, 'id version title description objects model color scale rotation camera lighting annotations autoRotate details source');
  if (p.version !== 1) fail();
  const color = get(p, 'color', '#8b9cf7');
  if (typeof color !== 'string' || !/^#[a-fA-F0-9]{6}$/.test(color)) fail();
  const model = get(p, 'model', '');
  if (!['', 'demo-cube'].includes(model)) fail();
  const raw = get(p, 'objects', []), ids = new Set();
  if (!Array.isArray(raw) || raw.length < (model ? 0 : 1) || raw.length > 8 || (model && raw.length)) fail();
  const objects = raw.map(o => {
    obj(o, 'id kind position rotation scale label description');
    const key = id(o.id);
    if (ids.has(key) || !['cube', 'sphere', 'cylinder', 'pyramid'].includes(o.kind)) fail();
    ids.add(key);
    return {id:key, kind:o.kind, position:vec(get(o, 'position', [0,0,0]), -3,3),
      rotation:vec(get(o, 'rotation', [0,0,0]), -360,360), scale:num(get(o, 'scale', 1), .25,2),
      label:str(get(o, 'label', o.kind),100), description:str(get(o, 'description', ''),500)};
  });
  if (model) ids.add('demo-cube');
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
  if (new TextEncoder().encode(JSON.stringify(result)).length > 20000) fail();
  return result;
};
