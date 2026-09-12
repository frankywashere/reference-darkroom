/* Per-photo, reversible starting tone. Stored in the ordinary recipe. */
(() => {
  const panel=document.createElement('details');panel.open=true;
  panel.innerHTML='<summary>RAW starting look</summary><label class="toggle"><input id="cameraLookToggle" type="checkbox"> Camera-inspired tone</label><small id="cameraLookStatus" style="display:block;color:var(--muted)"></small>';
  $('.controls').prepend(panel);
  const toggle=$('#cameraLookToggle'),status=$('#cameraLookStatus');let busy=false;
  function refresh(){
    const r=recipe(),raw=state.current&&/\.(raf|nef|nrw|arw|cr2|cr3|dng|orf|rw2|pef|srw|raw)$/i.test(state.current.path);
    toggle.checked=!!r.camera_look_enabled;toggle.disabled=!state.current||busy||(!raw&&!r.camera_look);
    status.textContent=busy?'Analyzing camera preview…':!raw&&!r.camera_look?'JPEGs already contain the camera rendering.':r.camera_look?'Saved brightness/contrast approximation. Toggle off for neutral; other edits stay unchanged.':'Estimate brightness and contrast from this RAW’s embedded camera JPEG. Not an exact film simulation or color match.';
  }
  const original=refreshControls;refreshControls=function(){original();if(state.config)refresh()};
  toggle.onchange=async()=>{
    const f=state.current,token=state.linearToken,enabled=toggle.checked;
    if(!f)return;
    if(!enabled||recipe().camera_look){snapshot();recipe().camera_look_enabled=enabled;changed(true);refresh();return;}
    busy=true;toggle.checked=false;refresh();
    try{
      const res=await fetch('/api/camera-look',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:f.path,recipe:{}})});
      const profile=await res.json();if(!res.ok)throw Error(profile.detail||'Could not analyze camera preview');
      if(state.linearToken!==token){toast('Photo changed; camera-inspired tone was not applied.');return;}
      snapshot();recipe().camera_look=profile;recipe().camera_look_enabled=true;changed(true);
    }catch(e){toast(e.message)}finally{busy=false;refresh()}
  };
  if(state.config)refresh();
})();
