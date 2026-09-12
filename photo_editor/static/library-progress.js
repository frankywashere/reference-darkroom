/* Persistent screen previews and visible, cancellable library work. */
(() => {
  const host=document.createElement('section');host.className='libraryWork';
  host.innerHTML='<div id="importWork" hidden><span id="importWorkText" role="status"></span><progress id="importWorkProgress"></progress><button id="cancelImportWork">Cancel import</button></div><div id="previewWorkText" role="status">Screen previews build as you browse.</div><button id="preparePreviews">Prepare project previews</button><button id="cancelPreviews" hidden>Stop preparing</button>';
  $('.projectsPanel').append(host);
  const cacheStatus=document.createElement('small');cacheStatus.style.cssText='display:block;color:var(--muted);margin-top:6px';cacheStatus.setAttribute('role','status');host.append(cacheStatus);
  const memory=new Map(),compressed=new Map();let foreground=null,generation=0,background=null,idleTimer=0,saveTimer=0,allMode=false,importID=null;
  let decodedBytes=0,compressedBytes=0,warming=false,warmTimer=0,lastIndex=-1,direction=1,cacheProject=null;
  const decodedTarget=1024**3,decodedLimit=2*1024**3,compressedLimit=192*1024**2;
  const remember=(key,image,kind)=>{
    decodedBytes-=memory.get(key)?.bytes||0;memory.delete(key);
    const bytes=image.width*image.height*4;memory.set(key,{image,kind,bytes});decodedBytes+=bytes;
    while(decodedBytes>decodedLimit&&memory.size>1){const first=memory.keys().next().value;decodedBytes-=memory.get(first).bytes;memory.delete(first);}
  };
  const rememberBlob=(key,blob,kind)=>{
    compressedBytes-=compressed.get(key)?.blob.size||0;compressed.delete(key);compressed.set(key,{blob,kind});compressedBytes+=blob.size;
    while(compressedBytes>compressedLimit&&compressed.size>1){const first=compressed.keys().next().value;compressedBytes-=compressed.get(first).blob.size;compressed.delete(first);}
  };
  const localKey=(f,r)=>state.projectId+f.path+JSON.stringify(r);
  async function lookup(f,r,signal,decode=true){
    const project=state.projectId,key=localKey(f,r),ready=memory.get(key);
    if(ready&&decode){memory.delete(key);memory.set(key,ready);return ready;}
    let packed=compressed.get(key);
    if(!packed){
    const res=await fetch('/api/screen-preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:f.path,recipe:r}),signal});
    if(!res.ok)throw Error('Screen preview unavailable');
    packed={blob:await res.blob(),kind:res.headers.get('X-Preview-Kind')};
    if(signal?.aborted||project!==state.projectId)throw new DOMException('Aborted','AbortError');rememberBlob(key,packed.blob,packed.kind);
    }
    if(!decode)return packed;
    const im=await blobImage(packed.blob);if(project!==state.projectId)throw new DOMException('Aborted','AbortError');remember(key,im,packed.kind);return {image:im,kind:packed.kind};
  }
  // One lightweight worker: direction-first window, at least 1 GiB decoded
  // (or every available photo for small projects), then project-wide
  // compressed previews. No full RAW/GPU development in this queue.
  // Prepared only limits the one-time whole-project pass. It must never block
  // reloading an evicted preview in the moving look-ahead window.
  const prepared=new Set(),failures=new Map();let warmDue=0;
  function scheduleWarm(delay=80){
    if(warming)return;
    if(warmTimer&&warmDue<=Date.now()+delay)return;
    clearTimeout(warmTimer);warmDue=Date.now()+delay;
    warmTimer=setTimeout(()=>{warmTimer=0;warm();},delay);
  }
  async function warm(){
    if(warming||!state.current||$('#exportDialog').open)return;
    warming=true;const project=state.projectId;let more=true;
    try{
      const index=state.visible.indexOf(state.current),near=[];
      for(let n=1;n<=12;n++)near.push(state.visible[index+n*direction]);
      for(let n=1;n<=3;n++)near.push(state.visible[index-n*direction]);
      const eligible=f=>f&&!f.missing&&(failures.get(localKey(f,photoState(f).recipe))||0)<=Date.now();
      const next=near.find(f=>eligible(f)&&!memory.has(localKey(f,photoState(f).recipe)));
      let fill=null;
      if(!next&&decodedBytes<decodedTarget){
        // Expand outward from the current photo, favoring travel direction.
        const needs=f=>eligible(f)&&!memory.has(localKey(f,photoState(f).recipe));
        if(needs(state.current))fill=state.current;
        for(let n=1;!fill&&n<state.visible.length;n++)fill=[state.visible[index+n*direction],state.visible[index-n*direction]].find(needs);
        fill ||= state.files.find(needs);
      }
      const f=next||fill||state.files.find(f=>eligible(f)&&!compressed.has(localKey(f,photoState(f).recipe))&&!prepared.has(localKey(f,photoState(f).recipe)));
      const usage=memory.size+' ready · '+Math.round(decodedBytes/1024**2)+' MB decoded';
      if(!f){more=false;cacheStatus.textContent='Browsing previews prepared · '+usage;return;}
      cacheStatus.textContent='Preparing browsing previews · '+usage+' (1 GB warm-up target)';
      const r=structuredClone(photoState(f).recipe),key=localKey(f,r);
      try{await lookup(f,r,undefined,!!(next||fill));if(project===state.projectId){prepared.add(key);failures.delete(key);}}
      catch(e){if(project===state.projectId)failures.set(key,Date.now()+30000);console.debug('Preview preparation skipped',f.name,e.message);}
    }finally{warming=false;if(project!==state.projectId||more)scheduleWarm();else if(failures.size)scheduleWarm(30000);}
  }
  const show=(p,token)=>{if(token!==state.linearToken||state.linearReady)return;if(p.kind==='camera'&&state.after&&$('#liveStatus').textContent.startsWith('Saved'))return;state.after=p.image;$('#liveStatus').textContent=(p.kind==='edited'?'Saved edited preview':'Camera preview (before edits)')+' · loading editable photo…';drawCanvas();};
  window.loadScreenPreview=(f,token)=>{
    if(cacheProject!==state.projectId){clearTimeout(warmTimer);warmTimer=0;memory.clear();compressed.clear();prepared.clear();failures.clear();decodedBytes=compressedBytes=0;cacheProject=state.projectId;lastIndex=-1;}
    const index=state.visible.indexOf(f);if(lastIndex>=0&&index!==lastIndex)direction=index>lastIndex?1:-1;lastIndex=index;
    scheduleWarm();
    generation++;background?.abort();foreground?.abort();clearTimeout(idleTimer);clearTimeout(saveTimer);
    if(allMode){allMode=false;$('#previewWorkText').textContent='Preview preparation paused for browsing.';$('#cancelPreviews').hidden=true;}
    const r=structuredClone(recipe()),key=localKey(f,r),cached=memory.get(key);
    if(cached)show(cached,token);
    foreground=new AbortController();lookup(f,r,foreground.signal).then(p=>show(p,token)).catch(e=>{if(e.name!=='AbortError'&&token===state.linearToken&&!state.linearReady)$('#liveStatus').textContent='Loading editable photo…';});
  };
  async function storeFrame(f,r,canvas,signal){
    const keyRes=await fetch('/api/screen-preview-key',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:f.path,recipe:r}),signal});
    if(!keyRes.ok)throw Error('Could not identify preview');const {key}=await keyRes.json();
    const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',.94));if(!blob)throw Error('Could not encode preview');
    const res=await fetch('/api/screen-preview/'+key,{method:'PUT',headers:{'Content-Type':'image/jpeg'},body:blob,signal});if(!res.ok)throw Error('Could not save preview');
    rememberBlob(localKey(f,r),blob,'edited');remember(localKey(f,r),await blobImage(blob),'edited');
  }
  const copyCanvas=im=>{const c=document.createElement('canvas'),s=Math.min(1,1800/Math.max(im.width,im.height));c.width=Math.max(1,Math.round(im.width*s));c.height=Math.max(1,Math.round(im.height*s));c.getContext('2d').drawImage(im,0,0,c.width,c.height);return c;};
  const render=renderHighBit;
  renderHighBit=function(){const ok=render();if(ok&&!state.clipMode){clearTimeout(saveTimer);clearTimeout(idleTimer);const token=state.linearToken;
    saveTimer=setTimeout(async()=>{if(token!==state.linearToken||!state.linearReady||state.clipMode)return;const f=state.current,r=structuredClone(recipe()),c=copyCanvas(state.liveFrame);
      try{await storeFrame(f,r,c);if(token===state.linearToken)$('#previewWorkText').textContent='Edited screen preview saved.';}catch(e){$('#previewWorkText').textContent='Preview cache unavailable; editing is unaffected.';}
    },700);
    if(!allMode)idleTimer=setTimeout(()=>prepare(false),1800);
  }return ok;};
  async function prepare(all){
    if(!state.current||!state.linearReady||background||$('#exportDialog').open)return;
    const token=generation,index=state.visible.indexOf(state.current),files=all?state.files.filter(f=>!f.missing):[state.visible[index+1],state.visible[index-1]].filter(f=>f&&!f.missing);
    const controller=background=new AbortController();allMode=all;$('#cancelPreviews').hidden=false;let renderer,done=0,errors=0;
    try{for(const f of files){
      if(token!==generation||controller.signal.aborted)break;
      const r=structuredClone(photoState(f).recipe);$('#previewWorkText').textContent='Preparing '+(all?'project':'nearby')+' previews — '+done+' of '+files.length;
      try{
        // Resolve tone first so an edited preview uses the complete recipe key.
        await window.ensureCameraLook?.(f,r);
        const p=await lookup(f,r,controller.signal);
        if(p.kind!=='edited'){
          renderer ||= new UnifiedPhotoRenderer();
          const res=await fetch('/api/gpu-source?limit='+renderer.limit+'&path='+encodeURIComponent(f.path),{signal:controller.signal});if(!res.ok)throw Error('RAW unavailable');
          const bytes=await res.arrayBuffer();if(token!==generation||controller.signal.aborted)break;
          renderer.setSource(bytes,+res.headers.get('X-Width'),+res.headers.get('X-Height'));
          const c=copyCanvas(renderer.render(r,0,{side:1800}));await storeFrame(f,r,c,controller.signal);
        }done++;
      }catch(e){if(e.name==='AbortError')break;errors++;done++;}
      await new Promise(resolve=>setTimeout(resolve,100));
    }
    if(token===generation)$('#previewWorkText').textContent=controller.signal.aborted?'Preview preparation stopped.':`Previews ready: ${done-errors} of ${files.length}${errors?' · '+errors+' unavailable':''}`;
    }finally{renderer?.dispose();if(background===controller)background=null;allMode=false;$('#cancelPreviews').hidden=true;if(token!==generation&&state.linearReady)idleTimer=setTimeout(()=>prepare(false),1800);}
  }
  $('#preparePreviews').onclick=()=>{background?.abort();clearTimeout(idleTimer);if(!background)prepare(true);else $('#previewWorkText').textContent='Stopping nearby work; click Prepare again when stopped.';};
  $('#cancelPreviews').onclick=()=>background?.abort();
  window.startProgressiveImport=async folder=>{
    if(importID)throw Error('Finish or cancel the current folder import first.');
    const project=state.projectId;const result=await projectRequest('/api/projects/'+project+'/import-job',{folder});importID=result.job_id;
    $('#importWork').hidden=false;$('#importWorkText').textContent='Scanning folder…';$('#importWorkProgress').removeAttribute('value');$('#cancelImportWork').disabled=false;
    localStorage.setItem('darkroomImportJob',importID);pollImport(importID,project);
  };
  async function pollImport(id,project){
    try{const j=await projectRequest('/api/import-jobs/'+id);
      $('#importWork').hidden=false;const progress=$('#importWorkProgress');
      $('#importWorkText').textContent=j.phase==='scanning'?`Scanning folder — ${j.found} new photos found…`:`Adding references — ${j.done} of ${j.total} · ${j.added} added`;
      if(j.total===null)progress.removeAttribute('value');else{progress.max=Math.max(1,j.total);progress.value=j.done;}
      if(state.projectId===project){const known=new Set(state.files.map(f=>f.id)),fresh=j.assets.filter(f=>!known.has(f.id));
        if(fresh.length){state.files.push(...fresh);fresh.forEach(photoState);if(!state.source)state.source=j.folder;$('#sourcePath').value=state.source;$('#sourceStatus').textContent=state.files.length+' photos';filterFiles();if(!state.current){selectPhoto(fresh[0]).then(()=>{if(state.projectId===project){$('.controls').inert=!state.linearReady;$$('.toolbar button,#export,#before,#undo,#redo').forEach(b=>b.disabled=false);}});}}
      }
      if(j.status==='running'){setTimeout(()=>pollImport(id,project),350);return;}
      $('#importWorkText').textContent=`${j.status==='complete'?'Import complete':j.status==='cancelled'?'Import cancelled':'Import failed'} — ${j.added} references added${j.errors.length?' · '+j.errors.length+' issue(s): '+j.errors.slice(0,2).join('; '):''}`;
      $('#cancelImportWork').disabled=true;importID=null;localStorage.removeItem('darkroomImportJob');refreshProjects();
    }catch(e){$('#importWorkText').textContent='Import status unavailable: '+e.message;importID=null;localStorage.removeItem('darkroomImportJob');}
  }
  $('#cancelImportWork').onclick=async()=>{if(importID){$('#cancelImportWork').disabled=true;$('#importWorkText').textContent='Cancelling — references already added will be kept…';await projectRequest('/api/import-jobs/'+importID+'/cancel',{});}};
  const pending=localStorage.getItem('darkroomImportJob');if(pending){importID=pending;projectRequest('/api/import-jobs/'+pending).then(j=>pollImport(pending,j.project_id)).catch(()=>{importID=null;localStorage.removeItem('darkroomImportJob');});}
})();
