/* One GPU pipeline for interactive editing and JPG exports. */
(() => {
  let frame=0,loadTimer=0,controller=null,exporting=false,fullDetail=false,loadResolve=null,statsTimer=0,cancelExport=false;
  const previews=new Map(),status=$('#liveStatus');
  const quality=document.createElement('button');quality.id='previewQuality';quality.textContent='Preview: Fit';
  quality.title='Full detail processes every sensor pixel. Fit uses the same GPU operations at display size.';status.before(quality);
  const editable=ready=>{$('.controls').inert=!ready;$('#canvas').style.pointerEvents=ready?'':'none';};
  window.rememberPhotoFrame=()=>{
    if(!state.current||!state.linearReady||!state.liveFrame)return;
    const im=state.liveFrame,c=window.copyEditedPreview?window.copyEditedPreview(im,recipe(),state.liveRenderer.last):document.createElement('canvas');
    if(!window.copyEditedPreview){const s=Math.min(1,1800/Math.max(im.width,im.height));c.width=Math.round(im.width*s);c.height=Math.round(im.height*s);c.getContext('2d').drawImage(im,0,0,c.width,c.height);}
    previews.delete(state.current.path);previews.set(state.current.path,{image:c,key:JSON.stringify(recipe())});
    while(previews.size>16)previews.delete(previews.keys().next().value);
  };
  window.showImmediatePhoto=(f,token)=>{
    controller?.abort();clearTimeout(loadTimer);loadResolve?.();loadResolve=null;cancelAnimationFrame(frame);frame=0;
    state.previewController?.abort();clearTimeout(state.previewTimer);state.previewTimer=null;
    state.loadingPhoto=true;state.before=null;state.liveFrame=null;editable(false);
    const cached=previews.get(f.path);
    if(cached&&cached.key===JSON.stringify(recipe())){state.after=cached.image;status.textContent='Saved preview · loading editable photo…';}
    else{status.textContent=state.after?'Previous photo · loading next preview…':'Loading screen preview…';}
    window.loadScreenPreview?.(f,token);
    $('#loading').style.display='none';$('#clippingStats').textContent='Clipping analysis available when the editable photo is ready.';drawCanvas();
  };
  loadBefore=async()=>{};
  loadLinearSource=function(f,token){
    return new Promise(resolve=>{loadResolve=resolve;loadTimer=setTimeout(async()=>{
      const mine=controller=new AbortController();
      try{
        while(window.photoNavigationHeld&&token===state.linearToken&&!mine.signal.aborted)await new Promise(r=>setTimeout(r,60));
        if(token!==state.linearToken)return;
        if(!(state.liveRenderer instanceof UnifiedPhotoRenderer))throw Error('GPU editor unavailable; reload the app.');
        const res=await fetch('/api/gpu-source?limit='+state.liveRenderer.limit+'&path='+encodeURIComponent(f.path),{signal:mine.signal});
        if(!res.ok)throw Error((await res.json()).detail||'Unable to decode photo');
        const bytes=await res.arrayBuffer();if(token!==state.linearToken||mine.signal.aborted)return;
        const width=+res.headers.get('X-Width'),height=+res.headers.get('X-Height');
        state.liveRenderer.setSource(bytes,width,height);state.sourceInfo={width,height,bits:+res.headers.get('X-Source-Bits'),kind:res.headers.get('X-Source-Kind')};
        state.linearReady=true;state.loadingPhoto=false;editable(true);renderHighBit();
      }catch(e){if(token!==state.linearToken||e.name==='AbortError')return;state.linearReady=false;status.textContent='Photo unavailable for editing';toast(e.message);}
      finally{resolve();}
    },350);});
  };
  renderHighBit=function(){
    if(!state.current||!state.linearReady||exporting)return false;
    try{
      const start=performance.now(),r=recipe(),renderer=state.liveRenderer;
      const work=state.geometryPreview,options={full:fullDetail&&!work,crop:state.tool==='edit',...(work?{side:work.side,workSize:work}:{})};
      if(state.compare){
        const before=renderer.render({...state.config.default_recipe,rotation:r.rotation,straighten:r.straighten,flip_h:r.flip_h,flip_v:r.flip_v,crop:r.crop},0,options);
        const c=state.beforeCanvas||(state.beforeCanvas=document.createElement('canvas'));c.width=before.width;c.height=before.height;c.getContext('2d').drawImage(before,0,0);state.before=c;
      }
      state.liveFrame=renderer.render(r,state.clipMode,options);state.after=state.liveFrame;drawCanvas();
      state.lastFrameMs=performance.now()-start;
      status.textContent=state.sourceInfo.width+' × '+state.sourceInfo.height+' · float32 GPU';
      status.title='Shared preview/export engine. Last displayed frame: '+state.lastFrameMs.toFixed(1)+' ms. '+renderer.canvas.width+' × '+renderer.canvas.height+' preview.';
      $('#loading').style.display='none';return true;
    }catch(e){state.linearReady=false;editable(false);status.textContent='GPU rendering stopped';toast(e.message);console.error(e);return false;}
  };
  function queue(){if(frame||!state.linearReady||exporting)return;frame=requestAnimationFrame(()=>{frame=0;renderHighBit();});}
  schedulePreview=function(){clearTimeout(state.previewTimer);state.previewTimer=null;queue();clearTimeout(statsTimer);statsTimer=setTimeout(updateClippingStats,600);};
  renderPreview=async()=>queue();
  renderLiveSlider=function(){if(!state.linearReady||exporting)return false;schedulePreview();return true;};
  quality.onclick=()=>{fullDetail=!fullDetail;quality.textContent=fullDetail?'Preview: Full detail':'Preview: Fit';queue();};
  const beforeClick=$('#before').onclick;$('#before').onclick=()=>{beforeClick();queue();};
  toggleClipping=function(bit){state.clipMode^=bit;$('#clipHighlights').classList.toggle('active',!!(state.clipMode&1));$('#clipShadows').classList.toggle('active',!!(state.clipMode&2));queue();};
  window.addEventListener('resize',queue);
  window.gpuBrushChanged=queue;
  $('#exportDialog').addEventListener('close',()=>{if(exporting)cancelExport=true;});
  window.addEventListener('keydown',e=>{if(exporting&&!$('#exportDialog').contains(e.target)){e.preventDefault();e.stopImmediatePropagation();}},true);
  updateClippingStats=async()=>{if(!state.linearReady||exporting||frame)return;try{const [hi,lo,partial]=state.liveRenderer.clippingStats();$('#clippingStats').textContent='Sampled display highlights: '+hi.toFixed(2)+'% · Near-black: '+lo.toFixed(2)+'% · Partial RGB clipping: '+partial.toFixed(2)+'%';$('#clippingStats').title='Sampled from the current GPU linear rendering, before the display curve. These display thresholds do not measure sensor saturation or prove recoverable RAW detail.';}catch(e){console.warn(e);}};
  startExport=async function(){
    if(exporting)return;
    const scope=$('#exportScope').value,files=(scope==='current'?[state.current]:scope==='picked'?state.files.filter(f=>photoState(f).rating>0):state.visible).filter(Boolean);
    if(!files.length){toast('No photos selected');return;}
    const items=files.map(f=>({path:f.path,recipe:structuredClone(photoState(f).recipe)}));
    const destination=$('#exportPath').value,prefix=$('#exportPrefix').value,quality=+$('#exportQuality').value;
    exporting=true;cancelExport=false;cancelAnimationFrame(frame);frame=0;editable(false);$('#startExport').disabled=true;$('main').inert=true;$('header .actions').inert=true;$('.sourcebar').inert=true;
    const completed=[],errors=[];let renderer;
    try{
      renderer=new UnifiedPhotoRenderer();
      for(const [i,item] of items.entries()){
        if(cancelExport)break;
        $('#exportProgress').textContent='Loading '+(i+1)+' of '+items.length+'…';
        try{
          await window.ensureCameraLook?.(item,item.recipe);
          const res=await fetch('/api/gpu-source?limit='+renderer.limit+'&path='+encodeURIComponent(item.path));if(!res.ok)throw Error((await res.json()).detail);
          renderer.setSource(await res.arrayBuffer(),+res.headers.get('X-Width'),+res.headers.get('X-Height'));
          if(cancelExport)break;
          $('#exportProgress').textContent='Rendering '+(i+1)+' of '+items.length+' on GPU…';
          await new Promise(requestAnimationFrame);
          renderer.render(item.recipe,0,{full:true,crop:true});const {bytes,width,height}=renderer.pixels();
          const query=new URLSearchParams({source:item.path,destination,prefix,quality,width,height});
          const saved=await fetch('/api/gpu-jpg?'+query,{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:bytes});
          if(!saved.ok)throw Error((await saved.json()).detail);completed.push((await saved.json()).path);
        }catch(e){errors.push(item.path+': '+e.message);}
      }
      $('#exportProgress').textContent='Saved '+completed.length+' of '+items.length+' JPGs. '+errors.join(' · ');
      toast(cancelExport?'Export stopped; '+completed.length+' JPGs saved':errors.length?'Export finished with errors — see export window':'Saved '+completed.length+' JPGs with the GPU renderer');
    }catch(e){$('#exportProgress').textContent=e.message;}
    finally{renderer?.dispose();exporting=false;$('main').inert=false;$('header .actions').inert=false;$('.sourcebar').inert=false;$('#startExport').disabled=false;editable(state.linearReady);queue();}
  };
})();
