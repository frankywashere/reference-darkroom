/* Resolution-independent local brush strokes, replayed by the float32 engine. */
const brush = {size: .12, feather: 65, flow: 100, opacity: 100, erase: false, overlay: true, stroke: null};
$('#maskPanel summary').textContent = 'Masks & brushes';
$('.maskButtons').insertAdjacentHTML('afterbegin','<button id="addBrush">+ Brush</button>');
$('#maskList').insertAdjacentHTML('afterend', `<div id="brushTools" hidden>
  <h3>1 · Paint the area</h3><div class="brushModes"><button id="paintBrush" class="active">Add to mask</button><button id="eraseBrush">Erase from mask</button></div>
  <small>Feather softens the brush edge. New strokes use these settings.</small>
  <div id="brushSliders"></div></div>`);
for (const [key,label,min,max,step] of [['size','Brush size',.01,.8,.01],['feather','Feather',0,100,1],['flow','Flow',1,100,1],['opacity','Opacity',1,100,1]]) {
  const row=document.createElement('label');row.className='slider';
  row.innerHTML=`<span>${label}</span><input aria-label="${label}" type="range" min="${min}" max="${max}" step="${step}" value="${brush[key]}"><output>${Math.round(key==='size'?brush[key]*100:brush[key])}%</output>`;
  row.querySelector('input').oninput=e=>{brush[key]=+e.target.value;row.querySelector('output').value=`${Math.round(key==='size'?brush[key]*100:brush[key])}%`};
  $('#brushSliders').append(row);
}
$('#paintBrush').onclick=()=>brushMode(false);
$('#eraseBrush').onclick=()=>brushMode(true);
function brushMode(erase){brush.erase=erase;$('#paintBrush').classList.toggle('active',!erase);$('#eraseBrush').classList.toggle('active',erase)}
$('#addBrush').onclick=()=>{
  if(!state.current)return;
  snapshot();brushMode(false);brush.overlay=true;recipe().masks.push({name:`Brush ${recipe().masks.length+1}`,type:'brush',strokes:[],exposure:0,saturation:0,temperature:0,enabled:true,amount:100});
  renderMaskList(recipe().masks.length-1);refreshControls();setTool('mask');changed(true);
};
const originalRefreshControls=refreshControls;
refreshControls=function(){originalRefreshControls();const m=selectedMask(),isBrush=m?.type==='brush';$('#brushTools').hidden=!isBrush;
  $$('#maskControls [data-key]').forEach(input=>{input.closest('.slider').hidden=isBrush&&['mask.feather','mask.width','mask.height','mask.angle'].includes(input.dataset.key)});syncMaskUI()};
// Until local masks have a GPU implementation, never show a global-only frame
// that would temporarily erase the user's local edits during slider movement.
const originalHighBit=renderHighBit;
renderHighBit=function(){if(recipe().masks?.length){state.liveFrame=null;state.live=null;return false}return originalHighBit()};
const originalDrawMasks=drawMasks;
drawMasks=function(c,w,h){
  const masks=recipe().masks, geometric=masks.filter(m=>m.type!=='brush'&&m.enabled!==false);
  recipe().masks=geometric;try{originalDrawMasks(c,w,h)}finally{recipe().masks=masks}
  const m=selectedMask();if(m?.type!=='brush'||!brush.overlay||m.enabled===false)return;
  const layer=document.createElement('canvas');layer.width=Math.ceil(w);layer.height=Math.ceil(h);const ctx=layer.getContext('2d');
  for(const s of m.strokes){
    ctx.globalCompositeOperation=s.erase?'destination-out':'source-over';
    const strokeLayer=document.createElement('canvas');strokeLayer.width=layer.width;strokeLayer.height=layer.height;const sc=strokeLayer.getContext('2d');
    const radius=s.size*Math.min(w,h)/2, feather=Math.max(.001,s.feather/100),alpha=s.flow/100;
    for(const [x,y] of s.points){
      const g=sc.createRadialGradient(x*w,y*h,0,x*w,y*h,radius);
      g.addColorStop(0,`rgba(255,95,85,${alpha})`);g.addColorStop(1-feather,`rgba(255,95,85,${alpha})`);g.addColorStop(1,'rgba(255,95,85,0)');
      sc.fillStyle=g;sc.fillRect(x*w-radius,y*h-radius,radius*2,radius*2);
    }
    ctx.globalAlpha=s.opacity/100;ctx.drawImage(strokeLayer,0,0);
  }
  c.save();c.globalAlpha=.5*(m.amount??100)/100;c.drawImage(layer,0,0,w,h);c.restore();
};
const canvas=$('#canvas');
const cursor=document.createElement('div');cursor.id='brushCursor';cursor.hidden=true;$('#viewport').append(cursor);
canvas.addEventListener('pointerleave',()=>cursor.hidden=true);
function brushActive(){return state.current&&state.tool==='mask'&&selectedMask()?.type==='brush'&&selectedMask().enabled!==false&&!state.compare}
canvas.addEventListener('pointerdown',e=>{
  if(!brushActive())return;e.stopImmediatePropagation();e.preventDefault();
  snapshot();brush.overlay=true;$('#showMask').checked=true;state.liveFrame=null;state.previewController?.abort();clearTimeout(state.previewTimer);state.previewTimer=null;
  const p=canvasPos(e);brush.stroke={size:brush.size,feather:brush.feather,flow:brush.flow,opacity:brush.opacity,erase:brush.erase||e.altKey,points:[[p.x,p.y]]};
  selectedMask().strokes.push(brush.stroke);canvas.setPointerCapture(e.pointerId);drawCanvas();window.gpuBrushChanged?.();
},true);
canvas.addEventListener('pointermove',e=>{
  cursor.hidden=!brushActive();if(!brushActive())return;e.stopImmediatePropagation();
  const bounds=canvas.getBoundingClientRect(),vp=$('#viewport').getBoundingClientRect(),diameter=brush.size*Math.min(bounds.width,bounds.height);
  Object.assign(cursor.style,{width:`${diameter}px`,height:`${diameter}px`,left:`${e.clientX-vp.left}px`,top:`${e.clientY-vp.top}px`});
  cursor.classList.toggle('erasing',brush.erase||e.altKey);cursor.style.setProperty('--brush-core',`${(1-brush.feather/100)*100}%`);
  if(!brush.stroke)return;
  const p=canvasPos(e),r=canvas.getBoundingClientRect(),last=brush.stroke.points.at(-1);
  const dx=p.x-last[0],dy=p.y-last[1],distance=Math.hypot(dx*r.width,dy*r.height),spacing=Math.max(.5,brush.stroke.size*Math.min(r.width,r.height)*.12);
  const steps=Math.floor(distance/spacing);
  for(let i=1;i<=steps;i++){const t=i*spacing/distance;brush.stroke.points.push([last[0]+dx*t,last[1]+dy*t])}
  drawCanvas();window.gpuBrushChanged?.();
},true);
function endStroke(e){if(!brush.stroke)return;e.stopImmediatePropagation();brush.stroke=null;changed(true);syncMaskUI()}
canvas.addEventListener('pointerup',endStroke,true);canvas.addEventListener('pointercancel',endStroke,true);canvas.addEventListener('lostpointercapture',endStroke,true);
window.addEventListener('keydown',e=>{if(['INPUT','SELECT','TEXTAREA'].includes(document.activeElement.tagName)||!brushActive())return;if(e.key==='['||e.key===']'){brush.size=Math.max(.01,Math.min(.8,brush.size+(e.key===']'?.01:-.01)));const input=$('#brushSliders input');input.value=brush.size;input.dispatchEvent(new Event('input'))}});

// Persistent library width and a keyboard-accessible collapse control.
const sidebarButton=document.createElement('button');sidebarButton.id='toggleLibrary';sidebarButton.textContent='◧ Library';sidebarButton.title='Show or hide photo library';$('.toolbar').prepend(sidebarButton);
const divider=document.createElement('div');divider.id='libraryDivider';divider.tabIndex=0;divider.setAttribute('role','separator');divider.setAttribute('aria-label','Resize photo library');divider.setAttribute('aria-orientation','vertical');divider.setAttribute('aria-valuemin','190');divider.setAttribute('aria-valuemax','440');$('.library').after(divider);
let libraryWidth=Number(localStorage.getItem('darkroomLibraryWidth'))||250,libraryCollapsed=localStorage.getItem('darkroomLibraryCollapsed')==='true';
function updateLibrary(){libraryWidth=Math.max(190,Math.min(440,libraryWidth));document.documentElement.style.setProperty('--library-width',`${libraryCollapsed?0:libraryWidth}px`);$('main').classList.toggle('libraryCollapsed',libraryCollapsed);sidebarButton.setAttribute('aria-expanded',String(!libraryCollapsed));divider.setAttribute('aria-valuenow',String(libraryWidth));localStorage.setItem('darkroomLibraryWidth',libraryWidth);localStorage.setItem('darkroomLibraryCollapsed',libraryCollapsed);drawCanvas()}
sidebarButton.onclick=()=>{libraryCollapsed=!libraryCollapsed;updateLibrary()};
divider.onpointerdown=e=>{e.preventDefault();divider.setPointerCapture(e.pointerId);divider.dataset.drag='true'};
divider.onpointermove=e=>{if(divider.dataset.drag){libraryWidth=e.clientX-$('main').getBoundingClientRect().left;updateLibrary()}};
divider.onpointerup=divider.onpointercancel=()=>delete divider.dataset.drag;
divider.onkeydown=e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();libraryWidth+=e.key==='ArrowRight'?10:-10;updateLibrary()}else if(e.key==='Enter'){libraryCollapsed=true;updateLibrary()}};
new ResizeObserver(()=>drawCanvas()).observe($('#viewport'));
updateLibrary();
// Keep local editing in its own workspace instead of below all global controls.
const controls=$('.controls'), panel=$('#maskPanel');
controls.prepend(panel);
controls.insertAdjacentHTML('afterbegin','<div class="workspaceTabs"><button id="editWorkspace" class="active">Edit photo</button><button id="maskWorkspace">Masks</button></div>');
panel.querySelector('summary').textContent='Local adjustments';
panel.insertAdjacentHTML('afterbegin','<div class="maskHeading"><h2>Masks</h2><button id="doneMask">Done</button></div><p class="maskIntro">Choose an area. Change only that area.</p>');
$('.maskButtons').insertAdjacentHTML('afterend','<div id="maskCards" aria-label="Photo masks"></div><p id="maskEmpty">Start with New brush, then paint the area you want to adjust. Your photo stays unchanged until you move an adjustment slider.</p><div id="maskSelection"><label class="maskNameLabel">Mask name<input id="maskName" maxlength="80" placeholder="e.g. Face, Background"></label><div class="maskReview"><label><input id="showMask" type="checkbox" checked> Show colored mask <kbd>O</kbd></label></div><p id="maskHint" role="status"></p></div>');
$('#maskList').hidden=true;
$('#addBrush').textContent='＋ New brush';$('#addBrush').classList.add('primary');
$('#addEllipse').textContent='Ellipse';$('#addLinear').textContent='Gradient';
const deleteButton=$('#deleteMask');deleteButton.textContent='Delete mask';deleteButton.title='Delete selected mask (Undo restores it)';
panel.append(deleteButton);
$('#maskControls').insertAdjacentHTML('beforebegin','<h3 id="maskAdjustTitle">2 · Adjust this area</h3><p id="maskAdjustHelp">Adjustments affect only the selected mask. The overlay hides as you adjust.</p>');
$('#maskControls').append(slider(['mask.amount','Effect strength',0,100,1],'mask'));
$('#maskControls').append(slider(['mask.size','Gradient width',.03,1,.01],'mask'));
const advanced=document.createElement('details');advanced.id='brushAdvanced';advanced.innerHTML='<summary>Advanced brush settings</summary><small>Flow builds coverage as dabs overlap. Opacity limits coverage within one stroke.</small>';
const rows=[...$('#brushSliders').children];advanced.append(rows[2],rows[3]);$('#brushSliders').append(advanced);
$('#brushTools').insertAdjacentHTML('beforeend','<p class="brushShortcuts">Hold ⌥ to erase · [ / ] size · ⌘Z undo</p>');
$('#maskName').onchange=e=>{const m=selectedMask();if(!m)return;snapshot();m.name=e.target.value.trim()||'Untitled mask';refreshControls();saveProject()};
$('#showMask').onchange=e=>{brush.overlay=e.target.checked;drawCanvas()};
$('#maskControls').addEventListener('input',()=>{brush.overlay=false;$('#showMask').checked=false;drawCanvas();syncMaskUI()});
$('#editWorkspace').onclick=$('#doneMask').onclick=()=>setTool('edit');
$('#maskWorkspace').onclick=()=>setTool('mask');
$('[data-tool="mask"]').textContent='Masks';
const originalSetTool=setTool;
setTool=function(tool){originalSetTool(tool);cursor.hidden=true;controls.classList.toggle('maskWorkspace',tool==='mask');panel.open=tool==='mask';$('#editWorkspace').classList.toggle('active',tool!=='mask');$('#maskWorkspace').classList.toggle('active',tool==='mask');controls.scrollTop=0;syncMaskUI()};
// Edit mode is for viewing/global adjustments, not accidental crop drags.
canvas.addEventListener('pointerdown',e=>{if(state.tool==='edit'||state.compare||(state.tool==='mask'&&(!selectedMask()||selectedMask().enabled===false))){e.stopImmediatePropagation();e.preventDefault()}},true);
function syncMaskUI(){
  if(!state.config||!$('#maskCards'))return;
  const m=selectedMask(),masks=recipe().masks||[];
  $$('.maskButtons button').forEach(b=>b.disabled=!state.current);
  $('#maskEmpty').hidden=masks.length>0;$('#maskSelection').hidden=!m;
  $('#maskControls').hidden=!m;$('#maskAdjustTitle').hidden=!m;$('#maskAdjustHelp').hidden=!m;deleteButton.hidden=!m;
  if(m){if(document.activeElement!==$('#maskName'))$('#maskName').value=m.name;$('#showMask').checked=brush.overlay;
    const amount=$('[data-key="mask.amount"]');if(amount){amount.value=m.amount??100;amount.nextElementSibling.value=m.amount??100}
    $$('#maskControls [data-key]').forEach(input=>{const key=input.dataset.key;const geometry=['mask.feather','mask.width','mask.height','mask.angle','mask.size'];if(geometry.includes(key))input.closest('.slider').hidden=m.type==='brush'||(m.type==='linear'?!['mask.angle','mask.size'].includes(key):['mask.angle','mask.size'].includes(key))});
    $('#maskAdjustTitle').textContent=m.type==='brush'?'2 · Adjust this area':'Adjust this area';
    $('#maskHint').textContent=m.enabled===false?'This mask is hidden. Turn it on in the list to edit.':state.compare?'Before comparison is on. Turn it off to paint.':m.type==='brush'?(m.strokes?.length?'Paint to add more, erase to refine, or adjust below.':'Paint on the photo to define this mask.'):'Drag on the photo to position this mask.';
  }
  $$('#maskControls input, #brushTools input, #brushTools button').forEach(el=>el.disabled=!m||m.enabled===false);
  $('#showMask').disabled=m?.type!=='brush';
  $('#maskCards').replaceChildren();
  masks.forEach((mask,i)=>{const row=document.createElement('div');row.className=`maskCard ${mask===m?'selected':''} ${mask.enabled===false?'muted':''}`;
    const select=document.createElement('button');select.className='maskSelect';select.setAttribute('aria-pressed',String(mask===m));
    const title=document.createElement('b');title.textContent=mask.name;const info=document.createElement('small');
    info.textContent=`${mask.type==='brush'?'Brush':mask.type==='linear'?'Gradient':'Ellipse'} · ${mask.enabled===false?'Hidden':mask.type==='brush'&&!mask.strokes?.length?'Empty':`${Number(mask.exposure||0).toFixed(2)} EV`}`;
    select.append(title,info);select.onclick=()=>{$('#maskList').value=i;brushMode(false);refreshControls();setTool('mask');drawCanvas()};
    const visible=document.createElement('button');visible.className='maskVisibility';visible.textContent=mask.enabled===false?'Off':'On';visible.title=`${mask.enabled===false?'Show':'Hide'} ${mask.name}`;visible.setAttribute('aria-pressed',String(mask.enabled!==false));visible.onclick=()=>{snapshot();mask.enabled=mask.enabled===false;refreshControls();changed(true)};
    row.append(select,visible);$('#maskCards').append(row);
  });
}
addMask=function(type){if(!state.current)return;snapshot();recipe().masks.push({name:`${type==='linear'?'Gradient':'Ellipse'} ${recipe().masks.length+1}`,type,x:.5,y:.5,width:.25,height:.25,size:.35,angle:0,feather:60,exposure:0,saturation:0,temperature:0,invert:false,enabled:true,amount:100});renderMaskList(recipe().masks.length-1);refreshControls();setTool('mask');changed(true)};
const previousBefore=$('#before').onclick;$('#before').onclick=()=>{previousBefore();syncMaskUI()};
window.addEventListener('keydown',e=>{if(['INPUT','SELECT','TEXTAREA'].includes(document.activeElement.tagName)||$('dialog[open]'))return;if(e.key.toLowerCase()==='o'&&state.tool==='mask'&&selectedMask()?.type==='brush'){brush.overlay=!brush.overlay;$('#showMask').checked=brush.overlay;drawCanvas()}else if(e.key==='Escape'&&state.tool==='mask')setTool('edit')});
state.tool='edit';controls.classList.remove('maskWorkspace');$$('[data-tool]').forEach(b=>b.classList.remove('active'));

// Static UI updates can be served by an older, already-running Python process.
// Fail closed instead of sending brush recipes to an ellipse-only engine.
const previewWithMasks=renderPreview, exportWithMasks=startExport;
function maskEngineCompatible(){return Number(state.config?.mask_engine_version)>=2}
function warnOldEngine(){toast('Photo engine is out of date. Restart the photo engine before editing or exporting masks.');$('#liveStatus').textContent='Engine restart required';}
renderPreview=async function(draft=false){if(recipe().masks?.length&&!maskEngineCompatible()){warnOldEngine();return}return previewWithMasks(draft)};
startExport=async function(){if(!maskEngineCompatible()){warnOldEngine();return}return exportWithMasks()};
const refreshCompatible=refreshControls;
refreshControls=function(){refreshCompatible();if(state.config&&!maskEngineCompatible()){warnOldEngine();$$('.maskButtons button,#maskControls input,#brushTools input,#brushTools button').forEach(el=>el.disabled=true)}};
const brushActiveCompatible=brushActive;
brushActive=function(){return maskEngineCompatible()&&brushActiveCompatible()};
