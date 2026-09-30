/* Camera UI consumes the same catalog assets/recipes as ordinary imports. */
(()=>{
  const $=s=>document.querySelector(s);
  const button=document.createElement('button');button.id='openTether';button.textContent='Tether';button.title='Nikon live view and tethered shooting';document.querySelector('header .actions').prepend(button);
  document.body.insertAdjacentHTML('beforeend',`<section id="tetherWindow" hidden aria-label="Tethered shooting">
    <div class="tetherHeading"><div><b>Tether</b><small id="tetherCamera">Nikon Z8</small></div><button id="hideTether" aria-label="Hide tether window">×</button></div>
    <div class="tetherLive"><img id="tetherImage" alt="Camera live view" hidden><div id="tetherEmpty">Connect your camera to start live view.</div><span id="tetherLiveBadge" hidden>LIVE</span></div>
    <div class="tetherBody"><div id="tetherConnection"><div class="tetherRow"><select id="tetherDevices" aria-label="Camera"><option>Scan for cameras</option></select><button id="tetherScan">Scan</button></div>
    <label class="tetherLabel">Save captures inside<div class="tetherRow"><input id="tetherDestination" placeholder="Current project / Captures"><button id="tetherChoose">Choose…</button></div></label>
    <small>A dated session folder is created here. New photos are saved to disk and referenced by the project.</small>
    <label class="tetherCheck"><input type="checkbox" id="tetherLossless" checked> Lossless RAW for full-resolution editing</label><small>High Efficiency NEFs aren't supported by the editor yet. The camera's prior compression setting is restored on disconnect.</small>
    <label class="tetherCheck"><input type="checkbox" id="tetherUseLook"> Use the current photo's look for new captures</label>
    <button id="tetherConnect" class="primary">Connect to current project</button></div>
    <div id="tetherShooting" hidden><p id="tetherSession"></p><small>Receiving project follows your project selection. Originals stay in this session's capture folder.</small><div class="tetherRow"><button id="tetherLiveToggle">Start live view</button><button id="tetherDisconnect">Disconnect</button><button id="tetherRefreshSettings" title="Refresh camera settings">↻ Settings</button></div>
    <div id="tetherSettings"></div><div class="tetherCaptureRow"><label class="tetherCheck"><input id="tetherAutofocus" type="checkbox" checked> Autofocus</label><button id="tetherCapture" class="primary">● Capture</button></div>
    <label class="tetherCheck"><input id="tetherFollow" type="checkbox" checked> Select new captures in this project</label><button id="tetherUpdateLook">Use current look for next captures</button></div>
    <label class="tetherCheck"><input id="tetherAutoLook" type="checkbox" checked> Auto-apply latest capture's edits to incoming photos</label><small id="tetherAutoLookInfo">Global tone, color and detail only. Crops, masks and clone work stay separate.</small>
    <p id="tetherStatus" role="status">Create or open a project, then scan for your camera.</p><p id="tetherError" role="alert"></p>
    </div></section>`);
  const css=document.createElement('style');css.textContent=`#tetherWindow{position:fixed;right:340px;top:76px;width:520px;min-width:350px;max-width:calc(100vw - 32px);max-height:calc(100vh - 100px);overflow:auto;resize:both;background:var(--panel);border:1px solid #535b62;border-radius:10px;z-index:30;box-shadow:0 20px 70px #0009}#tetherWindow[hidden]{display:none}.tetherHeading{display:flex;align-items:center;justify-content:space-between;padding:10px 14px;border-bottom:1px solid var(--line);cursor:move;touch-action:none}.tetherHeading>div{display:flex;align-items:center;gap:12px}.tetherHeading small{color:var(--muted)}#hideTether{font-size:20px;border:0;background:none;padding:0 6px}.tetherLive{position:relative;aspect-ratio:3/2;background:#070809;display:grid;place-items:center;overflow:hidden}.tetherLive img{width:100%;height:100%;object-fit:contain}.tetherLive img[hidden]{display:none}#tetherEmpty{position:absolute;color:var(--muted);padding:20px;text-align:center}#tetherLiveBadge{position:absolute;top:12px;left:12px;font-size:10px;letter-spacing:.14em;color:#8be3b0;background:#11281fe6;padding:4px 7px;border-radius:4px}.tetherBody{padding:14px}.tetherRow,.tetherCaptureRow{display:flex;align-items:center;gap:8px;margin:8px 0}.tetherRow select,.tetherRow input{min-width:0;flex:1;padding:7px}.tetherLabel{display:block;margin-top:12px}.tetherCheck{display:flex;align-items:center;gap:7px;margin:12px 0}.tetherBody small{display:block;color:var(--muted);font-size:11px;line-height:1.5}.tetherCaptureRow{justify-content:space-between}#tetherCapture{padding:10px 22px;font-size:14px}#tetherSession{font-size:11px;color:var(--muted);overflow-wrap:anywhere}#tetherStatus{font-size:12px;color:#9cceb4;margin-bottom:0}#tetherError{font-size:12px;color:#f0a595;white-space:pre-wrap;margin:7px 0 0}#tetherSettings{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px}#tetherSettings label{display:grid;gap:4px;font-size:11px;color:var(--muted)}#tetherSettings select{padding:6px;min-width:0}.tetherBusy{opacity:.7}@media(max-width:1100px){#tetherWindow{right:24px}}`;document.head.append(css);
  const win=$('#tetherWindow');let status=null,cursor=0,busy=false,frameBusy=false,imageURL=null,polling=false,syncBusy=false,settingsKey='',lastScan=0;
  const recent=new Set();let autoLookPending=null;
  let targetChain=Promise.resolve();
  window.retargetTetherProject=async id=>{
    targetChain=targetChain.catch(()=>{}).then(async()=>{
      status=await request('target',{project_id:id});update();
      if(status.connected&&status.session?.project_id!==id)throw Error('Tether project did not switch.');
    });
    try{await targetChain}catch(e){$('#tetherError').textContent=e.message;toast('Tether target could not switch: '+e.message);throw e}
  };
  async function request(path,body){const r=await fetch('/api/tether/'+path,{...(body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});if(!r.ok){const v=await r.json();throw Error(v.detail||'Camera request failed')}return r.json()}
  async function action(fn){if(busy)return;busy=true;$('#tetherError').textContent='';win.classList.add('tetherBusy');update();try{await fn();await poll()}catch(e){$('#tetherError').textContent=e.message}finally{busy=false;win.classList.remove('tetherBusy');update()}}
  function update(){if(!status)return;const connected=status.connected;
    $('#tetherConnection').hidden=connected;$('#tetherShooting').hidden=!connected;
    $('#tetherConnect').disabled=busy||!state.projectId||!$('#tetherDevices').value||!status.installed;
    $('#tetherScan').disabled=busy;$('#tetherCapture').disabled=busy||!connected;
    $('#tetherLiveToggle').textContent=status.live?'Stop live view':'Start live view';$('#tetherDisconnect').disabled=busy;
    $('#tetherUpdateLook').disabled=busy||!state.current||state.projectId!==status.session?.project_id;
    $('#tetherAutoLook').checked=autoLookPending??(status.auto_look!==false);$('#tetherAutoLook').disabled=busy;
    $('#tetherUpdateLook').hidden=status.auto_look!==false;
    $('#tetherAutoLookInfo').textContent=status.auto_look!==false?`Automatically follows edits to the latest captured shot${status.auto_look_source?' · '+status.auto_look_source:''}. Global adjustments only; crops, masks and clone work stay separate.`:'Automatic look updates are off. Use the manual button to set the next capture look.';
    if(status.session){$('#tetherSession').textContent=`Receiving: ${status.session.project_name} · Files: ${status.session.destination}`;$('#tetherCamera').textContent=status.devices.find(d=>d.id===status.session.device_id)?.name||'Nikon camera';}
    if(!status.live){$('#tetherImage').hidden=true;$('#tetherLiveBadge').hidden=true;$('#tetherEmpty').hidden=false;$('#tetherEmpty').textContent=connected?'Live view is off.':'Connect your camera to start live view.';}
    else if(status.frame_age===null||status.frame_age>3){$('#tetherImage').hidden=true;$('#tetherLiveBadge').hidden=true;$('#tetherEmpty').hidden=false;$('#tetherEmpty').textContent='Waiting for live view… Check the camera if it stays paused.';}
    const key=JSON.stringify(status.settings);if(key!==settingsKey){settingsKey=key;$('#tetherSettings').replaceChildren();for(const [key,item] of Object.entries(status.settings||{})){if(!item.options?.length)continue;const label=document.createElement('label');label.textContent=({iso:'ISO',shutter:'Shutter speed',aperture:'Aperture',mode:'Exposure mode'})[key]||key;const select=document.createElement('select');for(const o of item.options){const opt=document.createElement('option');opt.value=o.index;opt.textContent=o.label;select.append(opt)}select.value=item.index;select.onchange=()=>action(async()=>{const v=await request('setting',{key,index:+select.value});status.settings=v.settings});label.append(select);$('#tetherSettings').append(label);}}
    $('#tetherLiveToggle').disabled=busy;$('#tetherShooting').querySelectorAll('select').forEach(s=>s.disabled=busy);
  }
  async function ingestEvents(events){
    if(syncBusy)return;syncBusy=true;
    try{
      const pending=events.filter(e=>e.kind==='imported'&&e.project_id===state.projectId&&!recent.has(e.asset.id));
      if(!pending.length)return;
      for(const e of pending){recent.add(e.asset.id);if(state.files.some(f=>f.id===e.asset.id))continue;state.files.push({...e.asset,missing:false});state.photos[e.asset.id]=structuredClone(e.photo);if(!state.source){state.source=status.session.destination;$('#sourcePath').value=state.source}}
      filterFiles();$('#sourceStatus').textContent=state.files.length+' photos';
      await refreshProjects();
      $('#tetherStatus').textContent=`Received ${pending.at(-1).asset.name} · saved to ${status.session?.project_name||'project'}`;
      if($('#tetherFollow').checked&&state.projectId===status.session?.project_id&&!state.drag&&!document.querySelector('#exportDialog').open){
        const stem=pending.at(-1).asset.name.replace(/\.[^.]+$/,'');
        const f=state.visible.find(f=>f.name.replace(/\.[^.]+$/,'')===stem)||state.visible.find(f=>pending.some(e=>e.asset.id===f.id));if(f){await selectPhoto(f);document.querySelectorAll('.toolbar button,#export,#before,#undo,#redo,.rating button').forEach(b=>b.disabled=false);}
      }
      $('#tetherStatus').textContent=`Received ${pending.at(-1).asset.name} · saved to ${status.session?.project_name||'project'}`;
    }finally{syncBusy=false}
  }
  async function poll(){if(polling)return;polling=true;try{
    const next=await request('status?after='+cursor);status=next;cursor=next.cursor;
    if(next.events.some(e=>e.kind==='devices_changed'))lastScan=0;
    for(const e of next.events){if(e.kind==='error')$('#tetherError').textContent=e.message;else if(e.kind==='imported')$('#tetherStatus').textContent=`Received ${e.asset.name} · saved to ${e.project_name||'receiving project'}`;else if(e.message)$('#tetherStatus').textContent=e.message;}
    await ingestEvents(next.events);update();
    if(!next.installed)$('#tetherError').textContent='Install your Nikon SDK, then restart the photo engine.';
  }catch(e){if(!win.hidden)$('#tetherError').textContent=e.message}finally{polling=false}}
  async function frame(){if(frameBusy||win.hidden||!status?.live)return;frameBusy=true;try{const r=await fetch('/api/tether/frame?t='+Date.now(),{cache:'no-store'});if(!r.ok)return;const url=URL.createObjectURL(await r.blob()),image=new Image();image.src=url;await image.decode();if(win.hidden||!status?.live){URL.revokeObjectURL(url);return}const old=imageURL;imageURL=url;$('#tetherImage').src=url;$('#tetherImage').hidden=false;$('#tetherEmpty').hidden=true;$('#tetherLiveBadge').hidden=false;if(old)URL.revokeObjectURL(old);}catch{}finally{frameBusy=false}}
  async function scan(){const data=await request('scan',{});status=data;const select=$('#tetherDevices'),old=select.value;select.replaceChildren();for(const d of data.devices){const option=document.createElement('option');option.value=d.id;option.textContent=d.name+(d.available?'':' · in use');option.disabled=!d.available;select.append(option)}if([...select.options].some(o=>o.value===old))select.value=old;if(!data.devices.length){const option=document.createElement('option');option.value='';option.textContent='No camera found';select.append(option);$('#tetherStatus').textContent='Camera not found yet. Check USB data connection, power, and other camera apps.'}else $('#tetherStatus').textContent=`${data.devices.length} camera found`;lastScan=Date.now();update()}
  button.onclick=async()=>{win.hidden=!win.hidden;if(!win.hidden){await poll();if(!status?.connected)action(scan)}};
  $('#hideTether').onclick=()=>{win.hidden=true};
  $('#tetherChoose').onclick=async()=>{const p=await chooseProjectPath('folder');if(p)$('#tetherDestination').value=p};
  $('#tetherScan').onclick=()=>action(scan);
  $('#tetherConnect').onclick=()=>action(async()=>{if(!state.projectId)throw Error('Create or open a project first.');await saveProject();await saveChain;status=await request('connect',{project_id:state.projectId,device_id:+$('#tetherDevices').value,destination:$('#tetherDestination').value.trim()||null,recipe:$('#tetherUseLook').checked&&state.current?structuredClone(recipe()):null,lossless:$('#tetherLossless').checked});await request('live',{enabled:true});});
  $('#tetherDisconnect').onclick=()=>action(async()=>{status=await request('disconnect',{});});
  $('#tetherLiveToggle').onclick=()=>action(()=>request('live',{enabled:!status.live}));
  $('#tetherCapture').onclick=()=>action(async()=>{await saveProject();await saveChain;await request('capture',{autofocus:$('#tetherAutofocus').checked});$('#tetherStatus').textContent='Capture requested · waiting for transfer…'});
  $('#tetherAutoLook').onchange=()=>{const enabled=$('#tetherAutoLook').checked;autoLookPending=enabled;action(async()=>{try{await saveProject();await saveChain;status=await request('auto-look',{enabled});}finally{autoLookPending=null}});};
  $('#tetherRefreshSettings').onclick=()=>action(async()=>{const v=await request('settings');status.settings=v.settings});
  $('#tetherUpdateLook').onclick=()=>action(async()=>{if(!state.current)return;await request('recipe',{recipe:structuredClone(recipe())});$('#tetherStatus').textContent='Current look will apply to subsequent captures.'});
  // A detached live window remains usable while editing the latest photograph.
  let drag=null;const heading=win.querySelector('.tetherHeading');heading.onpointerdown=e=>{if(e.target.closest('button'))return;const b=win.getBoundingClientRect();drag={x:e.clientX,y:e.clientY,left:b.left,top:b.top};heading.setPointerCapture(e.pointerId)};heading.onpointermove=e=>{if(!drag)return;win.style.right='auto';win.style.left=Math.max(0,Math.min(innerWidth-win.offsetWidth,drag.left+e.clientX-drag.x))+'px';win.style.top=Math.max(0,Math.min(innerHeight-50,drag.top+e.clientY-drag.y))+'px'};heading.onpointerup=heading.onpointercancel=heading.onlostpointercapture=()=>drag=null;
  setInterval(()=>{if(status?.connected||!win.hidden)poll();if(!win.hidden&&!busy&&!status?.connected&&Date.now()-lastScan>4000)action(scan)},1000);
  setInterval(frame,100);
  poll();
  window.addEventListener('keydown',e=>{if(win.contains(e.target))e.stopImmediatePropagation()},true);
})();
