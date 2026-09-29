/* Source-space clone strokes. No source files or raster layers are modified. */
(()=>{
  const host=$('.controls'),vp=$('#viewport'),canvas=$('#canvas');
  const brush={size:5,feather:75,opacity:100,flow:100},tool={layer:null,source:null,offset:null,armed:false,erase:false,gesture:null,photo:null};
  $('.workspaceTabs').insertAdjacentHTML('beforeend','<button id="cloneWorkspace">Clone</button>');
  const panel=document.createElement('details');panel.id='clonePanel';panel.open=true;
  panel.innerHTML=`<summary>Clone stamp</summary><div class="maskHeading"><h2>Clone</h2><button id="doneClone">Done</button></div>
    <p class="maskIntro">Copy a clean area over a distraction. Your original stays untouched.</p>
    <button id="cloneSource" class="primary">Set source</button><p id="cloneStatus" role="status">Option-click the photo to choose a source.</p>
    <div class="brushModes"><button id="clonePaint" class="active">Clone</button><button id="cloneErase">Erase retouch</button></div><div id="cloneSliders"></div>
    <label class="cloneOption"><input id="cloneAligned" type="checkbox" checked> Aligned source</label>
    <label class="cloneOption">Sample<select id="cloneSample"><option value="original">Original photo</option><option value="stack">Retouch stack</option></select></label>
    <small>Aligned keeps the source offset between strokes. Retouch stack includes earlier strokes and layers below.</small>
    <div class="cloneLayerHeading"><h3>Retouch layers</h3><button id="cloneNew">＋ Layer</button></div><div id="cloneLayers"></div>
    <div id="cloneLayerSettings"><label class="maskNameLabel">Layer name<input id="cloneName" maxlength="80"></label><label class="slider"><span>Layer opacity</span><input id="cloneLayerOpacity" aria-label="Clone layer opacity" type="range" min="0" max="100" value="100"><output>100%</output></label><button id="cloneDelete">Delete layer</button></div>
    <p class="brushShortcuts">⌥ / Alt-click source · [ / ] size · ⌘Z undo</p>`;
  $('.workspaceTabs').after(panel);
  const style=document.createElement('style');style.textContent=`.controls:not(.cloneWorkspace)>#clonePanel{display:none}.controls.cloneWorkspace>details:not(#clonePanel){display:none}#clonePanel>summary{display:none}.cloneOption{display:flex;align-items:center;gap:8px;margin:12px 0}.cloneOption select{flex:1;min-width:0}.cloneLayerHeading{display:flex;align-items:center;justify-content:space-between;margin-top:18px}#cloneLayers{display:grid;gap:5px;margin-bottom:12px}.cloneLayer{display:flex;gap:8px;align-items:center;padding:8px;border:1px solid #414148;border-radius:7px}.cloneLayer.selected{border-color:#d3ad77;background:#ffffff08}.cloneLayer button{flex:1;text-align:left;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;border:0;background:none}#cloneStatus{font-size:12px;line-height:1.5;color:#d3ad77;min-height:36px}#cloneGuides{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:8}.cloneWorkspace small{line-height:1.5}`;document.head.append(style);
  const ns='http://www.w3.org/2000/svg',guide=document.createElementNS(ns,'svg');guide.id='cloneGuides';guide.innerHTML='<g stroke="black" stroke-width="3" fill="none"><circle id="cloneRingShadow"/></g><g stroke="white" stroke-width="1" fill="none"><circle id="cloneRing"/><circle id="cloneCore" stroke-dasharray="2 3"/><path id="cloneCross" stroke="#ffd38e" stroke-width="2"/></g>';vp.append(guide);guide.style.display='none';
  const layers=()=>state.current?(recipe().clone_layers||[]):[],selected=()=>layers().find(l=>l.id===tool.layer);
  function sync(){
    if(tool.photo!==state.current?.id){tool.photo=state.current?.id;tool.source=tool.offset=null;tool.layer=null;}
    if(!selected())tool.layer=layers().at(-1)?.id||null;
    const list=$('#cloneLayers');list.replaceChildren();
    for(const l of layers().slice().reverse()){const row=document.createElement('div');row.className='cloneLayer'+(l.id===tool.layer?' selected':'');const check=document.createElement('input');check.type='checkbox';check.checked=l.enabled!==false;check.setAttribute('aria-label',`Show ${l.name}`);check.onchange=()=>{snapshot();l.enabled=check.checked;changed(true)};const b=document.createElement('button');b.textContent=`${l.name} · ${l.strokes.length}`;b.onclick=()=>{finish();tool.layer=l.id;tool.offset=null;sync()};row.append(check,b);list.append(row);}
    if(!layers().length)list.textContent='Your first stroke creates a layer.';
    const l=selected();$('#cloneLayerSettings').hidden=!l;if(l){$('#cloneName').value=l.name;$('#cloneLayerOpacity').value=l.opacity??100;$('#cloneLayerOpacity').nextElementSibling.value=`${l.opacity??100}%`;}
    $('#cloneStatus').textContent=tool.armed?'Click a clean area to sample.':tool.erase?'Paint to erase from the selected retouch layer.':tool.source?'Source ready. Paint over the area to replace.':'Option-click the photo, or use Set source.';
    $('#cloneSource').classList.toggle('active',tool.armed);$('#clonePaint').classList.toggle('active',!tool.erase);$('#cloneErase').classList.toggle('active',tool.erase);
  }
  function newLayer(){const l={id:crypto.randomUUID(),name:`Clone ${layers().length+1}`,enabled:true,opacity:100,strokes:[]};(recipe().clone_layers??=[]).push(l);tool.layer=l.id;return l;}
  for(const [key,label,min,max,step] of [['size','Brush size',.1,40,.1],['feather','Feather',0,100,1],['opacity','Stroke opacity',1,100,1],['flow','Flow',1,100,1]]){const row=document.createElement('label');row.className='slider';row.innerHTML=`<span>${label}</span><input aria-label="Clone ${label.toLowerCase()}" type="range" min="${min}" max="${max}" step="${step}" value="${brush[key]}"><output>${brush[key]}%</output>`;row.querySelector('input').oninput=e=>{brush[key]=+e.target.value;row.querySelector('output').value=brush[key]+'%'};$('#cloneSliders').append(row);}
  $('#cloneWorkspace').onclick=()=>setTool('clone');$('#doneClone').onclick=()=>setTool('edit');$('#cloneSource').onclick=()=>{tool.armed=!tool.armed;sync()};
  $('#clonePaint').onclick=()=>{tool.erase=false;sync()};$('#cloneErase').onclick=()=>{tool.erase=true;tool.armed=false;sync()};
  $('#cloneAligned').onchange=()=>tool.offset=null;
  $('#cloneNew').onclick=()=>{if(!state.current)return;snapshot();newLayer();sync();changed(true)};
  $('#cloneDelete').onclick=()=>{if(!selected())return;snapshot();recipe().clone_layers=layers().filter(l=>l.id!==tool.layer);sync();changed(true)};
  $('#cloneName').onchange=e=>{if(!selected())return;snapshot();selected().name=e.target.value.trim()||'Clone';sync();saveProject()};
  let opacityEditing=false;$('#cloneLayerOpacity').oninput=e=>{if(!selected())return;if(!opacityEditing){snapshot();opacityEditing=true}selected().opacity=+e.target.value;e.target.nextElementSibling.value=e.target.value+'%';changed(true)};$('#cloneLayerOpacity').onchange=()=>opacityEditing=false;
  function geometry(){const {width:w,height:h}=state.sourceInfo;return {w,h,b:CropMath.bounds(w,h,recipe())};}
  function point(e){const p=canvasPos(e),{w,h,b}=geometry(),x=(p.x-.5)*b.w,y=(p.y-.5)*b.h;let sx=(b.c*x+b.s*y)/w+.5,sy=(-b.s*x+b.c*y)/h+.5;if(recipe().flip_h)sx=1-sx;if(recipe().flip_v)sy=1-sy;return [sx,sy];}
  function screen(p){const {w,h,b}=geometry();let [x,y]=p;if(recipe().flip_h)x=1-x;if(recipe().flip_v)y=1-y;x=(x-.5)*w;y=(y-.5)*h;const r=canvas.getBoundingClientRect(),v=vp.getBoundingClientRect();return [(b.c*x-b.s*y)/b.w*r.width+r.width/2+r.left-v.left,(b.s*x+b.c*y)/b.h*r.height+r.height/2+r.top-v.top];}
  function guides(e,p){const v=vp.getBoundingClientRect(),{w,h,b}=geometry(),radius=brush.size/100*Math.min(w,h)/2*canvas.getBoundingClientRect().width/b.w;guide.style.display='block';for(const id of ['cloneRing','cloneRingShadow','cloneCore']){const c=$('#'+id);c.setAttribute('cx',e.clientX-v.left);c.setAttribute('cy',e.clientY-v.top);c.setAttribute('r',id==='cloneCore'?radius*(1-brush.feather/100):radius);}const src=tool.offset&&!tool.armed?p.map((n,i)=>n+tool.offset[i]):tool.source;const c=$('#cloneCross');if(src){const [x,y]=screen(src);c.setAttribute('d',`M${x-8} ${y}h16 M${x} ${y-8}v16`)}else c.setAttribute('d','');}
  function finish(){const g=tool.gesture;if(!g)return;tool.gesture=null;state.drag=null;try{canvas.releasePointerCapture(g.id)}catch{}changed(true);sync();}
  const active=()=>state.tool==='clone'&&state.current&&state.linearReady&&state.sourceInfo&&!state.compare;
  const inside=p=>p.every(n=>Number.isFinite(n)&&n>=0&&n<=1);
  vp.addEventListener('pointerdown',e=>{if(state.tool!=='clone'||e.target!==canvas||e.button!==0)return;e.preventDefault();e.stopImmediatePropagation();if(!active()){toast('Wait for the photo to load; turn off Before to clone.');return;}const p=point(e);if(!inside(p))return;
    if(e.altKey||tool.armed){tool.source=p;tool.offset=null;tool.armed=false;sync();guides(e,p);return;}
    if(!tool.erase&&!tool.source){tool.armed=true;sync();return;}if(selected()?.enabled===false){toast('Show this retouch layer before painting.');return;}if(tool.erase&&!selected())return;
    snapshot();const l=selected()||newLayer();if(!tool.erase&&(!$('#cloneAligned').checked||!tool.offset))tool.offset=tool.source.map((n,i)=>n-p[i]);
    const s={...brush,size:brush.size/100,erase:tool.erase,sample:$('#cloneSample').value,offset:tool.erase?[0,0]:[...tool.offset],points:[p]};l.strokes.push(s);tool.gesture={id:e.pointerId,s,last:p,token:state.linearToken};state.drag={kind:'clone'};canvas.setPointerCapture(e.pointerId);window.gpuBrushChanged?.();guides(e,p);
  },true);
  vp.addEventListener('pointermove',e=>{if(!active())return;e.stopImmediatePropagation();const p=point(e);guides(e,p);const g=tool.gesture;if(!g)return;if(!(e.buttons&1)||g.token!==state.linearToken){finish();return;}if(g.id!==e.pointerId)return;if(!inside(p)){g.last=null;return;}if(!g.last){g.s.points.push(p);g.last=p;}else{const {w,h}=geometry(),dx=p[0]-g.last[0],dy=p[1]-g.last[1],d=Math.hypot(dx*w,dy*h),spacing=Math.max(.5,g.s.size*Math.min(w,h)*.12),start=g.last;for(let i=1;i<=Math.floor(d/spacing);i++){const q=[start[0]+dx*i*spacing/d,start[1]+dy*i*spacing/d];g.s.points.push(q);g.last=q;}}window.gpuBrushChanged?.();},true);
  for(const event of ['pointerup','pointercancel'])window.addEventListener(event,e=>{if(tool.gesture?.id===e.pointerId){finish();e.stopImmediatePropagation();}},true);
  canvas.addEventListener('lostpointercapture',finish);canvas.addEventListener('pointerleave',()=>guide.style.display='none');window.addEventListener('blur',finish);document.addEventListener('visibilitychange',()=>{if(document.hidden)finish()});
  window.addEventListener('keydown',e=>{if(state.tool!=='clone')return;if(e.key==='Escape'||e.metaKey||e.ctrlKey)finish();if(['INPUT','SELECT','TEXTAREA'].includes(document.activeElement.tagName))return;if(e.key==='['||e.key===']'){e.preventDefault();const input=$('#cloneSliders input');input.value=brush.size+(e.key===']'?1:-1);input.dispatchEvent(new Event('input'));}},true);
  const oldTool=setTool;setTool=function(t){finish();oldTool(t);host.classList.toggle('cloneWorkspace',t==='clone');$('#editWorkspace').classList.toggle('active',t!=='mask'&&t!=='clone');$('#cloneWorkspace').classList.toggle('active',t==='clone');panel.open=true;guide.style.display='none';sync();schedulePreview(0)};
  const refresh=refreshControls;refreshControls=function(){refresh();sync()};
  const select=selectPhoto;selectPhoto=async function(...args){finish();guide.style.display='none';return select(...args)};
  style.textContent+=`#clonePanel .maskHeading{display:flex;align-items:center;justify-content:space-between;margin:16px 16px 8px}#clonePanel h2{font-size:19px;margin:0}#clonePanel>.maskIntro,#clonePanel>#cloneStatus,#clonePanel>.brushShortcuts{margin:8px 16px 12px}#clonePanel>#cloneSource{margin-left:16px}#clonePanel .maskNameLabel{display:flex;flex-direction:column;gap:5px;margin-bottom:10px}#clonePanel .maskNameLabel input{padding:7px;width:100%}#clonePanel>.cloneOption,#clonePanel>small{margin-left:16px;margin-right:16px}#clonePanel>small{display:block;color:var(--muted)}#clonePanel #cloneSliders .slider>span{font-size:12px}`;
  sync();
})();
