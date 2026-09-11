/* View-only navigation. CSS transforms keep mask/crop coordinates normalized. */
(() => {
  const viewport=$('#viewport'),canvas=$('#canvas');
  const badge=document.createElement('div');
  badge.id='gpuLoading';badge.setAttribute('role','status');badge.hidden=true;
  badge.innerHTML='<span></span>Loading photo into GPU';viewport.append(badge);
  const style=document.createElement('style');style.textContent=`
    #canvas{transform-origin:center center;will-change:transform}
    #gpuLoading{position:absolute;right:14px;top:14px;display:flex;align-items:center;gap:10px;padding:11px 14px;border:1px solid #626970;border-radius:9px;background:#171a1deb;box-shadow:0 2px 12px #0006;color:#e8e4dc;font-size:12px;pointer-events:none;z-index:3}
    #gpuLoading[hidden]{display:none}
    #gpuLoading span{width:24px;height:24px;flex-shrink:0;border:3px solid #64686c;border-top-color:#efb47f;border-radius:50%;animation:gpuSpin .8s linear infinite}
    @keyframes gpuSpin{to{transform:rotate(360deg)}}
    @media(prefers-reduced-motion:reduce){#gpuLoading span{animation:none}}
  `;document.head.append(style);
  let zoom=1,x=0,y=0,gestureScale=1,gesturing=false;
  const navigationKeys=new Set();
  window.addEventListener('keydown',e=>{
    if(!['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(e.key)||e.metaKey||e.ctrlKey||e.altKey||e.shiftKey)return;
    if(e.target.closest('input,select,textarea,button,[contenteditable],dialog')||$('dialog[open]')||$('main').inert)return;
    navigationKeys.add(e.key);window.photoNavigationHeld=true;
  },true);
  window.addEventListener('keyup',e=>{navigationKeys.delete(e.key);window.photoNavigationHeld=!!navigationKeys.size;});
  window.addEventListener('blur',()=>{navigationKeys.clear();window.photoNavigationHeld=false;});
  function apply(){
    const bx=Math.max(0,(canvas.offsetWidth*zoom-viewport.clientWidth)/2);
    const by=Math.max(0,(canvas.offsetHeight*zoom-viewport.clientHeight)/2);
    x=Math.max(-bx,Math.min(bx,x));y=Math.max(-by,Math.min(by,y));
    canvas.style.transform=`translate(${x}px,${y}px) scale(${zoom})`;
    const vr=viewport.getBoundingClientRect(),cr=canvas.getBoundingClientRect();
    const hasPhoto=!!(state.liveFrame||state.after||state.before);
    badge.style.top=(hasPhoto?Math.max(0,cr.top-vr.top):0)+14+'px';
    badge.style.right=(hasPhoto?Math.max(0,vr.right-cr.right):0)+14+'px';
    $('#fit').textContent=zoom===1?'Fit':Math.round(zoom*100)+'% · Fit';
  }
  function reset(){zoom=1;x=y=0;apply()}
  function magnify(factor,cx,cy){
    const next=Math.max(1,Math.min(12,zoom*factor)),r=viewport.getBoundingClientRect();
    const px=cx-r.left-r.width/2,py=cy-r.top-r.height/2,ratio=next/zoom;
    x=px-(px-x)*ratio;y=py-(py-y)*ratio;zoom=next;apply();
  }
  viewport.addEventListener('wheel',e=>{
    if(!state.current||!canvas.width||$('dialog[open]'))return;
    e.preventDefault();
    if(state.drag||(typeof brush!=='undefined'&&brush.stroke))return;
    const unit=e.deltaMode===1?16:e.deltaMode===2?viewport.clientHeight:1;
    if(e.ctrlKey){if(!gesturing)magnify(Math.exp(-e.deltaY*unit*.01),e.clientX,e.clientY)}
    else{x-=e.deltaX*unit;y-=e.deltaY*unit;apply()}
  },{passive:false});
  // WKWebView/Safari delivers native trackpad pinch as gesture events.
  viewport.addEventListener('gesturestart',e=>{e.preventDefault();gesturing=true;gestureScale=e.scale||1},{passive:false});
  viewport.addEventListener('gesturechange',e=>{
    e.preventDefault();if(!state.current||state.drag)return;
    magnify(e.scale/gestureScale,e.clientX,e.clientY);gestureScale=e.scale;
  },{passive:false});
  viewport.addEventListener('gestureend',e=>{e.preventDefault();gesturing=false},{passive:false});
  $('#fit').onclick=()=>{reset();drawCanvas()};
  $('#fit').title='Reset zoom and pan. Pinch to zoom; two-finger scroll to pan. Percentage is relative to Fit.';
  const draw=drawCanvas;drawCanvas=function(){
    const tool=state.tool,compare=state.compare;
    try{if(state.loadingPhoto){state.tool='edit';state.compare=false;}draw();}
    finally{state.tool=tool;state.compare=compare;}apply();
  };
  const immediate=window.showImmediatePhoto;
  window.showImmediatePhoto=function(...args){reset();badge.hidden=false;viewport.setAttribute('aria-busy','true');return immediate(...args)};
  const load=loadLinearSource;
  loadLinearSource=async function(f,token){try{return await load(f,token)}finally{
    if(token===state.linearToken){badge.hidden=true;viewport.setAttribute('aria-busy','false')}
  }};
  window.addEventListener('keydown',e=>{
    if(!['ArrowUp','ArrowDown'].includes(e.key)||e.metaKey||e.ctrlKey||e.altKey||e.shiftKey||e.defaultPrevented)return;
    if(e.target.closest('input,select,textarea,button,[contenteditable="true"],[role="slider"],dialog')||$('dialog[open]')||$('main').inert)return;
    e.preventDefault();const step=e.key==='ArrowDown'?1:-1;
    let n=state.visible.indexOf(state.current)+step;
    while(state.visible[n]?.missing)n+=step;
    if(state.visible[n]){selectPhoto(state.visible[n]);$('.thumb.selected')?.scrollIntoView({block:'nearest'})}
  });
})();
