/* Per-photo, reversible starting tone. Stored in the ordinary recipe. */
(() => {
  const panel=document.createElement('details');panel.open=true;
  panel.innerHTML='<summary>RAW starting look</summary><label class="toggle"><input id="cameraLookToggle" type="checkbox"> Camera-inspired tone</label><small id="cameraLookStatus" style="display:block;color:var(--muted)"></small>';
  $('.controls').prepend(panel);
  const toggle=$('#cameraLookToggle'),status=$('#cameraLookStatus');let busy=false;
  const pending=new Map();
  window.ensureCameraLook=async(f,r)=>{
    if(!r.camera_look_enabled||r.camera_look)return;
    if(!/\.(raf|nef|arw|cr2|cr3|dng)$/i.test(f.path)){r.camera_look_enabled=false;return;}
    const project=state.projectId;
    if(!pending.has(f.path))pending.set(f.path,(async()=>{
      const res=await fetch('/api/camera-look',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:f.path,recipe:{}})});
      const profile=await res.json();if(!res.ok)throw Error(profile.detail||'Could not analyze camera preview');return profile;
    })().finally(()=>pending.delete(f.path)));
    const profile=await pending.get(f.path);r.camera_look=profile;
    if(project===state.projectId){
      const file=state.files.find(x=>x.path===f.path),saved=file&&photoState(file).recipe;
      if(saved?.camera_look_enabled&&!saved.camera_look){saved.camera_look=profile;saveProject();}
    }
  };
  function refresh(){
    const r=recipe(),raw=state.current&&/\.(raf|nef|nrw|arw|cr2|cr3|dng|orf|rw2|pef|srw|raw)$/i.test(state.current.path);
    toggle.checked=!!r.camera_look_enabled;toggle.disabled=!state.current||busy||(!raw&&!r.camera_look);
    status.textContent=busy?'Analyzing camera preview…':!raw&&!r.camera_look?'JPEGs already contain the camera rendering.':r.camera_look?'Saved brightness/contrast approximation. Toggle off for neutral; other edits stay unchanged.':'Estimate brightness and contrast from this RAW’s embedded camera JPEG. Not an exact film simulation or color match.';
  }
  const original=refreshControls;refreshControls=function(){original();if(state.config)refresh()};
  const load=loadLinearSource;
  loadLinearSource=async function(f,token){
    await load(f,token);
    if(token!==state.linearToken||!state.linearReady||!recipe().camera_look_enabled||recipe().camera_look)return;
    const r=recipe();busy=true;refresh();
    try{await window.ensureCameraLook(f,r);if(token===state.linearToken&&recipe()===r){saveProject();schedulePreview();}}
    catch(e){if(token===state.linearToken){toast('Camera-inspired tone unavailable: '+e.message);}}
    finally{busy=false;if(state.config)refresh();}
  };
  toggle.onchange=async()=>{
    const f=state.current,token=state.linearToken,enabled=toggle.checked;
    if(!f)return;
    if(!enabled||recipe().camera_look){snapshot();recipe().camera_look_enabled=enabled;changed(true);refresh();return;}
    busy=true;toggle.checked=false;refresh();
    try{
      const candidate={camera_look_enabled:true};await window.ensureCameraLook(f,candidate);const profile=candidate.camera_look;
      if(state.linearToken!==token){toast('Photo changed; camera-inspired tone was not applied.');return;}
      snapshot();recipe().camera_look=profile;recipe().camera_look_enabled=true;changed(true);
    }catch(e){toast(e.message)}finally{busy=false;refresh()}
  };
  if(state.config)refresh();
})();
