/* Declarative educational operations over the existing Three scene, no extra renderer. */
import {Vector3, Box3} from './vendor/three-engine.js';
export function attachEducation({props, saved, content, group, camera, reduced, menu, panel, changed}) {
  const ids=props.objects.map(o=>o.id), meshes=new Map(), initial=new Map(), transitions=new Map();
  content.traverse(o=>{if(o.isMesh){meshes.set(o.userData.objectId,o);initial.set(o.userData.objectId,o.position.clone());}});
  const validate=v=>window.validateModel3DInteraction(v,ids,props.steps.length);
  let state=validate(props.interaction), elapsed=0, orbitTime=0;
  try {if(saved?.scene===props.id && saved.interaction) state=validate(saved.interaction);} catch (_) { /* stale remote state is not a command */ }
  if(reduced.matches) state.lessonPlaying=false;
  const buttons=[];
  function make(tag,text,parent=menu){const e=document.createElement(tag); if(text)e.textContent=text; parent.append(e); return e;}
  function button(text,fn,needsPart=false){const b=make('button',text);b.type='button';b.className='jdui-btn';b.onclick=fn;buttons.push({b,needsPart});return b;}
  const views={free:null,front:[0,0,0],back:[0,Math.PI,0],side:[0,Math.PI/2,0],top:[Math.PI/2,0,0]};
  const viewLabel=make('label','Vista '), view=make('select','',viewLabel);
  for(const [key,label] of Object.entries({free:'Livre',front:'Frontal',back:'Traseira',side:'Lateral',top:'Superior'})){const o=make('option',label,view);o.value=key;}
  view.onchange=()=>{state.view=view.value;state.focus='';commit();};
  button('Isolar',()=>{state.isolated=state.selected;state.hidden=state.hidden.filter(k=>k!==state.selected);commit();},true);
  button('Ocultar',()=>{state.hidden=[...new Set([...state.hidden,state.selected])];state.focus='';commit();},true);
  button('Revelar tudo',()=>{state.hidden=[];state.isolated='';state.transparent=[];commit();});
  button('Transparência',()=>{state.transparent=state.transparent.includes(state.selected)?state.transparent.filter(k=>k!==state.selected):[...state.transparent,state.selected];commit();},true);
  button('Focar',()=>{state.focus=state.selected;state.hidden=state.hidden.filter(k=>k!==state.selected);commit();},true);
  const explode=button('Separar peças',()=>{state.exploded=!state.exploded;commit();});
  explode.disabled=ids.length<2;
  const lesson=document.createElement('section');lesson.className='m3-lesson';panel.append(lesson);
  const label=make('label','Etapa ',lesson), stepSelect=make('select','',label);
  props.steps.forEach((s,i)=>{const o=make('option',s.title,stepSelect);o.value=String(i);});
  const note=make('p','',lesson);note.setAttribute('aria-live','polite');
  const row=make('div','',lesson);row.className='m3-lesson-controls';
  function lessonButton(text,fn){const b=make('button',text,row);b.type='button';b.className='jdui-btn';b.onclick=fn;return b;}
  const prev=lessonButton('Etapa anterior',()=>go(state.step-1)), play=lessonButton('Reproduzir etapas',()=>{state.lessonPlaying=!state.lessonPlaying;elapsed=0;commit();}), next=lessonButton('Próxima etapa',()=>go(state.step+1));
  const speedLabel=make('label','Velocidade ',lesson), speed=make('select','',speedLabel);
  for(const n of [.5,1,1.5,2]){const o=make('option',n+'×',speed);o.value=String(n);}
  speed.onchange=()=>{state.speed=Number(speed.value);commit();};
  stepSelect.onchange=()=>go(Number(stepSelect.value));
  lesson.hidden=!props.steps.length;
  function refresh(){
    buttons.forEach(({b,needsPart})=>{if(needsPart)b.disabled=!state.selected;});
    explode.textContent=state.exploded?'Remontar peças':'Separar peças';view.value=state.view;
    stepSelect.value=String(state.step);speed.value=String(state.speed);
    prev.disabled=state.step===0;next.disabled=state.step>=props.steps.length-1;
    play.textContent=state.lessonPlaying?'Pausar etapas':'Reproduzir etapas';
    note.textContent=props.steps[state.step]?.text || '';
  }
  function targetPosition(id){
    const target=initial.get(id).clone();
    if(props.education==='solar' && ['earth','mars'].includes(id)){
      const r=target.length(),angle=orbitTime*(id==='earth'?1:.53);
      target.set(Math.cos(angle)*r,target.y,Math.sin(angle)*r);
    }
    if(state.exploded){const direction=target.clone();if(direction.length()<.01)direction.set(0,-1,0);target.add(direction.normalize().multiplyScalar(.7));}
    return target;
  }
  function apply(smooth=true){
    for(const [id,m] of meshes){
      m.visible=!state.hidden.includes(id) && (!state.isolated || id===state.isolated);
      m.material.transparent=state.transparent.includes(id);m.material.opacity=m.material.transparent ? .25 : 1;
      m.material.depthWrite=!m.material.transparent;m.material.needsUpdate=true;
      m.material.emissive?.setHex(id===state.selected?0x393958:0);
      const target=targetPosition(id);
      if(smooth && !reduced.matches)transitions.set(id,{from:m.position.clone(),target,t:0});
      else {m.position.copy(target);transitions.delete(id);}
    }
    refresh();
  }
  function commit(){state=validate(state);apply();changed();}
  function go(index,keepPlaying=false){
    if(index<0 || index>=props.steps.length)return;
    state.step=index;state.lessonPlaying=keepPlaying;elapsed=0;
    const step=props.steps[index]; Object.assign(state,{selected:step.selected,view:step.view,exploded:step.exploded,hidden:[],isolated:'',focus:''});commit();
  }
  apply(false);
  return {
    get state(){return structuredClone(state);},
    get animating(){return transitions.size>0 || state.lessonPlaying;},
    get viewRotation(){return views[state.view];},
    select(id){if(!ids.includes(id))return;state.selected=id;state.hidden=state.hidden.filter(k=>k!==id);state.isolated='';commit();},
    setState(s){state=validate(s);if(reduced.matches)state.lessonPlaying=false;elapsed=0;apply();},
    reset(){state=validate({});elapsed=0;orbitTime=0;apply(false);changed();},
    stopMotion(){state.lessonPlaying=false;apply(false);changed();},
    freeView(){state.view='free';state.focus='';refresh();},
    tick(dt){
      for(const [id,tr] of transitions){tr.t=Math.min(1,tr.t+dt/.3);const ease=tr.t*tr.t*(3-2*tr.t);meshes.get(id).position.lerpVectors(tr.from,tr.target,ease);if(tr.t===1)transitions.delete(id);}
      if(state.lessonPlaying){
        elapsed+=dt*state.speed;
        if(props.education==='solar' && !reduced.matches){
          orbitTime+=dt*state.speed;
          for(const id of ['earth','mars']){const m=meshes.get(id);if(m){transitions.delete(id);m.position.copy(targetPosition(id));}}
        }
        if(elapsed>=4){if(state.step<props.steps.length-1)go(state.step+1,true);else {state.lessonPlaying=false;refresh();changed();}}
      }
    },
    focusCamera(distance){
      const mesh=meshes.get(state.focus);if(!mesh || !mesh.visible)return false;
      group.updateMatrixWorld(true);const center=new Box3().setFromObject(mesh).getCenter(new Vector3());
      camera.position.copy(center).add(new Vector3(0,0,Math.max(1.5,distance*.65)));camera.lookAt(center);return true;
    },
    dispose(){transitions.clear();for(const b of menu.querySelectorAll('button,select')){b.onclick=null;b.onchange=null;}for(const b of lesson.querySelectorAll('button,select')){b.onclick=null;b.onchange=null;}lesson.remove();}
  };
}
