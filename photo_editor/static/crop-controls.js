/* Crop UI uses the same saved rectangle as full-resolution export. */
(() => {
  let zoomInput,zoomOutput,drag=null,sliderGesture=false;
  const ready=()=>state.current&&state.linearReady&&state.sourceInfo;
  const bounds=()=>CropMath.bounds(state.sourceInfo.width,state.sourceInfo.height,recipe());
  const getFrame=()=>recipe().crop_frame||CropMath.frame(recipe().crop,bounds());
  function writeFrame(f){recipe().crop_frame=f;recipe().crop=CropMath.rectangle(f,bounds());}
  function sync(){
    if(!zoomInput||!ready())return;
    const f=getFrame(),value=Math.round(f.zoom*100);zoomInput.max=Math.max(400,value);zoomInput.value=value;zoomOutput.value=value+'%';
    state.aspect=recipe().crop_aspect||'free';
    $$('[data-aspect]').forEach(b=>{const active=b.dataset.aspect===state.aspect;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});
  }
  function install(){
    const straighten=$('[data-key="straighten"]');if(!straighten||zoomInput)return;
    const row=document.createElement('div');row.className='slider';
    row.innerHTML='<label>Crop zoom</label><input id="cropZoom" aria-label="Crop zoom" type="range" min="100" max="400" step="1" value="100"><output>100%</output>';
    straighten.closest('.slider').after(row);zoomInput=row.querySelector('input');zoomOutput=row.querySelector('output');
    const actions=document.createElement('div');actions.className='cropActions';actions.innerHTML='<button id="autoFillCrop" type="button">Auto-fill</button><button id="doneCrop" type="button">Done cropping</button><small>Drag the frame to recompose. Zoom and crop are included in exports.</small>';row.after(actions);
    zoomInput.addEventListener('pointerdown',()=>{if(!ready())return;snapshot();sliderGesture=true;setTool('crop');});
    zoomInput.addEventListener('input',()=>{if(!ready())return;if(!sliderGesture)snapshot();writeFrame({...getFrame(),zoom:+zoomInput.value/100});sync();changed(true);});
    zoomInput.addEventListener('change',()=>{sliderGesture=false;});
    zoomInput.addEventListener('pointercancel',()=>{sliderGesture=false;});
    $('#autoFillCrop').onclick=()=>{if(!ready())return;snapshot();setTool('crop');const f=CropMath.autoFill(getFrame(),bounds(),state.sourceInfo.width,state.sourceInfo.height);writeFrame(f);sync();changed(true);};
    $('#doneCrop').onclick=()=>setTool('edit');
  }
  $$('[data-aspect]').forEach(button=>button.onclick=()=>{
    if(!ready())return;snapshot();const aspect=button.dataset.aspect,f=getFrame();recipe().crop_aspect=aspect;
    if(aspect!=='free')writeFrame({...f,ratio:aspect==='0.6667'?2/3:+aspect,zoom:1});
    setTool('crop');sync();changed(true);
  });
  $('#resetCrop').onclick=()=>{if(!ready())return;snapshot();recipe().crop=[0,0,1,1];delete recipe().crop_frame;recipe().crop_aspect='free';sync();changed(true);};
  const refresh=refreshControls;refreshControls=function(){refresh();install();sync();};
  const tool=setTool;setTool=function(t){if(t!=='crop')finish();tool(t);if(ready())schedulePreview();};
  const live=renderLiveSlider;renderLiveSlider=function(key,old,next){
    if(ready()&&['straighten','rotation'].includes(key)){
      if(!recipe().crop_frame){const prior={...recipe(),[key]:old};recipe().crop_frame=CropMath.frame(recipe().crop,CropMath.bounds(state.sourceInfo.width,state.sourceInfo.height,prior));}
      writeFrame(recipe().crop_frame);sync();
    }return live(key,old,next);
  };
  // Fix geometry after Undo, selecting another photo, or resetting a slider.
  const rendered=renderHighBit;renderHighBit=function(){const ok=rendered();if(ok)sync();return ok;};
  function beginGeometry(e){if(!ready()||!e.target.matches('[data-key="straighten"],[data-key="rotation"]'))return;
    const b=bounds(),side=Math.min(1600,Math.max($('#viewport').clientWidth,$('#viewport').clientHeight)*devicePixelRatio),s=side/Math.max(b.w,b.h);
    state.geometryPreview={width:Math.round(b.w*s),height:Math.round(b.h*s),side};setTool('crop');
  }
  function endGeometry(){if(!state.geometryPreview)return;state.geometryPreview=null;schedulePreview();}
  document.addEventListener('pointerdown',beginGeometry,true);
  document.addEventListener('pointerup',endGeometry);document.addEventListener('pointercancel',endGeometry);window.addEventListener('blur',endGeometry);
  document.addEventListener('change',e=>{if(e.target.matches('[data-key="straighten"],[data-key="rotation"]'))endGeometry();});
  const show=window.showImmediatePhoto;window.showImmediatePhoto=function(...args){drag=null;state.geometryPreview=null;sliderGesture=false;return show(...args);};
  const canvas=$('#canvas');
  canvas.addEventListener('pointerdown',e=>{
    if(state.tool==='edit'){e.stopImmediatePropagation();return;}
    if(!ready()||state.tool!=='crop'||e.button!==0)return;e.preventDefault();e.stopImmediatePropagation();
    const p=canvasPos(e),c=recipe().crop,r=canvas.getBoundingClientRect(),near=(a,b,span)=>Math.abs(a-b)*span<12;
    let corner=null;for(const [id,x,y] of [['tl',c[0],c[1]],['tr',c[0]+c[2],c[1]],['bl',c[0],c[1]+c[3]],['br',c[0]+c[2],c[1]+c[3]]])if(near(p.x,x,r.width)&&near(p.y,y,r.height))corner=id;
    state.drag=null;snapshot();drag={start:p,crop:[...c],corner,pointerId:e.pointerId,token:state.linearToken};canvas.setPointerCapture(e.pointerId);
  },true);
  canvas.addEventListener('pointermove',e=>{
    if(!drag)return;
    if(e.pointerId!==drag.pointerId)return;
    if(!(e.buttons&1)||state.tool!=='crop'||drag.token!==state.linearToken){finish(e);return;}
    e.stopImmediatePropagation();const p=canvasPos(e),[x,y,w,h]=drag.crop;let c;
    if(!drag.corner)c=[Math.max(0,Math.min(1-w,x+p.x-drag.start.x)),Math.max(0,Math.min(1-h,y+p.y-drag.start.y)),w,h];
    else{
      const left=drag.corner.includes('l'),top=drag.corner.includes('t'),ax=left?x+w:x,ay=top?y+h:y;
      let nw=Math.max(.02,Math.min(left?ax:1-ax,Math.abs(p.x-ax))),nh=Math.max(.02,Math.min(top?ay:1-ay,Math.abs(p.y-ay)));
      if(recipe().crop_aspect&&recipe().crop_aspect!=='free'){const b=bounds(),ratio=getFrame().ratio*b.h/b.w;nh=nw/ratio;const scale=Math.min(1,(top?ay:1-ay)/nh);nw*=scale;nh*=scale;}
      c=[left?ax-nw:ax,top?ay-nh:ay,nw,nh];
    }
    recipe().crop=c;recipe().crop_frame=CropMath.frame(c,bounds());sync();drawCanvas();
  },true);
  function finish(e){
    if(!drag||(e?.pointerId!==undefined&&e.pointerId!==drag.pointerId))return;
    const ended=drag;drag=null;state.drag=null;
    // Clear state before releasing capture: release can emit lostpointercapture.
    if(canvas.hasPointerCapture(ended.pointerId))canvas.releasePointerCapture(ended.pointerId);
    if(ended.token===state.linearToken)changed(true);
  }
  // Release can arrive outside the canvas or be replaced by capture loss when
  // the window loses focus. A later hover must never continue the crop gesture.
  window.addEventListener('pointerup',finish,true);window.addEventListener('pointercancel',finish,true);
  canvas.addEventListener('lostpointercapture',finish,true);
  window.addEventListener('blur',()=>finish());
  document.addEventListener('visibilitychange',()=>{if(document.hidden)finish();});
  window.addEventListener('keydown',e=>{if(e.key==='Escape')finish();});
  window.copyEditedPreview=(im,r,last)=>{
    const crop=last?.crop?.some((v,i)=>v!==[0,0,1,1][i])?[0,0,1,1]:(r.crop||[0,0,1,1]);
    const [x,y,w,h]=crop,s=Math.min(1,1800/Math.max(im.width*w,im.height*h)),c=document.createElement('canvas');c.width=Math.max(1,Math.round(im.width*w*s));c.height=Math.max(1,Math.round(im.height*h*s));c.getContext('2d').drawImage(im,x*im.width,y*im.height,w*im.width,h*im.height,0,0,c.width,c.height);return c;
  };
  install();
})();
