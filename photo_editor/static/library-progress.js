/* Persistent screen previews and visible, cancellable library work. */
(() => {
  const host=document.createElement('section');host.className='libraryWork';
  host.innerHTML='<div id="importWork" hidden><span id="importWorkText" role="status"></span><progress id="importWorkProgress"></progress><button id="cancelImportWork">Cancel import</button></div><div id="previewWorkText" role="status">Screen previews build as you browse.</div><button id="preparePreviews">Prepare project previews</button><button id="cancelPreviews" hidden>Stop preparing</button>';
  $('.projectsPanel').append(host);
  const memory=new Map();let foreground=null,generation=0,background=null,idleTimer=0,saveTimer=0,allMode=false,importID=null;
  const remember=(key,image,kind)=>{memory.delete(key);memory.set(key,{image,kind});while(memory.size>12)memory.delete(memory.keys().next().value);};
  const localKey=(f,r)=>f.path+JSON.stringify(r);
  async function lookup(f,r,signal){
    const res=await fetch('/api/screen-preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:f.path,recipe:r}),signal});
    if(!res.ok)throw Error('Screen preview unavailable');
    const im=await blobImage(await res.blob()),kind=res.headers.get('X-Preview-Kind');remember(localKey(f,r),im,kind);return {image:im,kind};
  }
  const show=(p,token)=>{if(token!==state.linearToken||state.linearReady)return;if(p.kind==='camera'&&state.after&&$('#liveStatus').textContent.startsWith('Saved'))return;state.after=p.image;$('#liveStatus').textContent=(p.kind==='edited'?'Saved edited preview':'Camera preview (before edits)')+' · loading editable photo…';drawCanvas();};
  window.loadScreenPreview=(f,token)=>{
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
    remember(localKey(f,r),await blobImage(blob),'edited');
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
        // Fetch/cache the larger embedded preview before doing any RAW development.
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
