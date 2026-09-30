/* Project folders contain portable catalogs; photo imports are references only. */
let catalogCapabilities=null;
const capabilitiesReady=projectRequest('/api/catalog-capabilities').then(c=>catalogCapabilities=c).catch(()=>null);
$('#newProject').textContent='Create project';$('#addFolder').textContent='Add photos';$('#reconnectProject').textContent='Find missing originals';
$('.projectActions').insertAdjacentHTML('beforeend','<button id="importCatalog">Import catalog…</button><button id="revealCatalog">Open catalog location</button>');
$('#saveStatus').insertAdjacentHTML('afterend','<div id="catalogLocation" title="Project catalog"></div>');
const folderLabel=$('#projectFolder').closest('label');folderLabel.firstChild.textContent='Folder ';
folderLabel.insertAdjacentHTML('beforeend','<button type="button" id="browseProjectFolder" aria-label="Choose file or folder">Choose…</button>');
$('#empty').insertAdjacentHTML('beforeend','<button id="emptyAddPhotos" class="primary">Add photos</button>');
$('#emptyAddPhotos').onclick=()=>showProjectDialog(state.files.length?'reconnect':state.projectId?'add':'create');
$('#projectHelp').insertAdjacentHTML('afterend','<small id="projectDestination"></small>');
const pendingPickers=new Map();
window.addEventListener('darkroomPathChosen',e=>{const resolve=pendingPickers.get(e.detail.id);if(resolve){pendingPickers.delete(e.detail.id);resolve(e.detail.path)}});
function chooseProjectPath(kind){return new Promise(resolve=>{const handler=window.webkit?.messageHandlers?.chooseProjectPath;if(!handler){toast('Paste the file or folder path into the field.');resolve(null);return}const id=crypto.randomUUID();pendingPickers.set(id,resolve);handler.postMessage({id,kind})})}
$('#browseProjectFolder').onclick=async()=>{const path=await chooseProjectPath(projectAction==='import'?'catalog':'folder');if(path){$('#projectFolder').value=path;updateProjectDestination()}};
function updateProjectDestination(){const name=$('#projectName').value.trim().replace(/[^\p{L}\p{N}_ .-]/gu,'_').replace(/^[ .]+|[ .]+$/g,'').slice(0,100)||'Project name';$('#projectDestination').textContent=projectAction==='create'?`Creates: ${$('#projectFolder').value.replace(/\/$/,'')}/${name}/catalog.darkroom.json`:''}
$('#projectName').addEventListener('input',updateProjectDestination);$('#projectFolder').addEventListener('input',updateProjectDestination);
showProjectDialog=async function(action){
  await capabilitiesReady;if(!catalogCapabilities){toast('Restart the photo engine to use project catalogs.');return}
  if(!['create','import'].includes(action)&&!state.projectId){toast('Create a project first');return}
  projectAction=action;$('#projectNameLabel').hidden=action!=='create';$('#projectName').required=action==='create';
  const titles={create:'Create project',add:'Add photos to this project',reconnect:'Find missing originals',import:'Import catalog'};
  $('#projectDialogTitle').textContent=titles[action];$('#confirmProject').textContent=action==='reconnect'?'Find originals':action==='add'?'Add photos':titles[action];
  folderLabel.firstChild.textContent=action==='create'?'Create project folder inside ':action==='import'?'Catalog file ':'Photo folder ';
  $('#projectName').value='';$('#projectFolder').value=action==='create'?catalogCapabilities.default_parent:action==='import'?'':(state.source||'');
  $('#projectFolder').placeholder=action==='import'?'/path/to/catalog.darkroom.json':'/path/to/folder';
  $('#projectHelp').textContent=action==='create'?'A new folder and an empty catalog will be created. Add photo references after creating the project.':action==='import'?'Imports a catalog into its own local project folder, including all edits and masks. Originals remain in their existing locations. Reconnect missing originals after import.':action==='add'?`Add photos to “${state.projectName||'this project'}”. The original files stay in this folder.`:'Choose the new location of your originals. Matching files keep their saved edits.';
  $('#projectError').textContent='';updateProjectDestination();$('#projectDialog').showModal();
};
$('#importCatalog').onclick=()=>showProjectDialog('import');
$('#revealCatalog').onclick=async()=>{if(!state.projectId)return;try{await saveChain;await projectRequest(`/api/projects/${state.projectId}/reveal`,{})}catch(e){toast(e.message)}};
$('#projectForm').onsubmit=async e=>{
  e.preventDefault();$('#confirmProject').disabled=true;$('#projectError').textContent='Working…';
  try{await saveChain;const folder=$('#projectFolder').value.trim();
    if(projectAction==='reconnect'){const report=await projectRequest(`/api/projects/${state.projectId}/reconnect`,{folder});await openCatalogProject(state.projectId);toast(`${report.reconnected} reconnected • ${report.missing} missing`)}
    else if(projectAction==='add'){await startProgressiveImport(folder);}
    else{const url=projectAction==='create'?'/api/projects':'/api/catalog-import';
      const body=projectAction==='create'?{name:$('#projectName').value.trim(),parent:folder}:projectAction==='import'?{path:folder}:{folder};
      await useProject(await projectRequest(url,body));}
    $('#projectDialog').close();
  }catch(error){$('#projectError').textContent=error.message}finally{$('#confirmProject').disabled=false}
};
const useFolderProject=useProject;
useProject=async function(data){
  await window.retargetTetherProject?.(data.project_id);
  state.linearToken++;state.history=[];state.future=[];state.live=null;state.drag=null;state.compare=false;
  $('#before').classList.remove('active');$('.compareSlider').style.display='none';$('#loading').style.display='none';
  state.projectName=data.name;state.catalogPath=data.catalog_path;
  await useFolderProject(data);
  $('#catalogLocation').textContent=data.catalog_path||'';$('#catalogLocation').title=data.catalog_path||'';
  $('#revealCatalog').disabled=!data.catalog_path;
  if(data.project_folder)$('#exportPath').value=`${data.project_folder}/Exports`;
  if(!state.current){$('#filename').textContent=data.name;$('#liveStatus').textContent='';$('#clippingStats').textContent='';$('#loading').style.display='none';
    $('#emptyAddPhotos').textContent=data.files.length?'Find missing originals':'Add photos';
    $('#empty b').textContent=data.files.length?'Originals are offline':'Your project is empty';
    $('#empty span').textContent=data.files.length?'Use Find missing originals to reconnect your photos. All edit settings are saved.':'Use Add photos to select a folder of originals.';
  }
  $('.controls').inert=!state.current;
  $$('.toolbar button:not(#toggleLibrary),.rating button,#export,#before,#undo,#redo').forEach(button=>button.disabled=!state.current);
};
// The header now adds references to the active project instead of silently creating another.
$('#openFolder').textContent='Add photos';$('#sourcePath').placeholder='Photo folder to add';
$('#openFolder').onclick=()=>showProjectDialog(state.projectId?'add':'create');
$('#sourcePath').addEventListener('keydown',e=>{if(e.key==='Enter'){e.stopImmediatePropagation();e.preventDefault();showProjectDialog(state.projectId?'add':'create')}},true);

// Discard asynchronous frames belonging to a photo/project that is no longer open.
loadBefore=async function(){if(!state.current)return;const photo=state.current,token=state.linearToken;
  const res=await fetch('/api/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:photo.path,recipe:state.config.default_recipe,apply_crop:false,max_side:1800})});
  if(res.ok){const img=await blobImage(await res.blob());if(photo!==state.current||token!==state.linearToken)return;state.before=img;drawCanvas()}
};
renderPreview=async function(draft=false){
  if(!state.current)return;if(recipe().masks?.length&&!maskEngineCompatible()){warnOldEngine();return}
  state.previewController?.abort();const controller=new AbortController();state.previewController=controller;
  const photo=state.current,token=state.linearToken;
  $('#loading').textContent=draft?'Previewing…':'Rendering…';$('#loading').style.display='block';
  try{const res=await fetch('/api/preview',{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({path:photo.path,recipe:recipe(),apply_crop:false,max_side:draft?900:1800,draft})});
    if(!res.ok)throw new Error((await res.json()).detail);
    const img=await blobImage(await res.blob());if(controller.signal.aborted||photo!==state.current||token!==state.linearToken||(draft&&state.live))return;
    state.after=img;if(!draft){state.live=null;state.liveFrame=null;updateClippingStats()}drawCanvas();
  }catch(e){if(e.name!=='AbortError'&&photo===state.current)toast(e.message)}finally{if(state.previewController===controller)$('#loading').style.display='none'}
};

// Catalog lifecycle: explicit removal, recoverable trash, and live-file recovery.
let catalogProblem=false, catalogCheckBusy=false, projectClosing=false;
$('.projectActions').insertAdjacentHTML('beforeend','<button id="manageProject">Manage project…</button>');
$('.projectsPanel').insertAdjacentHTML('beforeend','<div id="catalogWarning" role="alert" hidden><b>Catalog unavailable</b><p id="catalogWarningText"></p><button id="recoverNow">Save recovery copy</button><button id="locateNow">Locate catalog…</button></div>');
document.body.insertAdjacentHTML('beforeend',`<dialog id="manageProjectDialog"><form method="dialog"><h2 id="manageTitle">Manage project</h2><p id="manageLocation"></p><div class="manageOption"><b>Remove from library</b><p>Close this project and remove it from the project list. Its catalog and folder stay where they are. Import the catalog to reopen it.</p><button type="button" id="removeProject">Remove from library</button></div><div class="manageOption"><b>Move project to Trash</b><p>Close this project and move its entire project folder, including its catalog and any exports, to Trash. You can restore it from Trash. Referenced originals outside the folder stay in place.</p><button type="button" id="trashProject">Move project to Trash</button></div><div class="manageOption"><b>Recover an unavailable catalog</b><p>Locate the same project's catalog, or save all currently loaded references and edits into a new project.</p><label>Catalog path<input id="locatePath" placeholder="/path/to/catalog.darkroom.json"></label><div class="manageButtons"><button type="button" id="browseCatalogRecovery">Choose…</button><button type="button" id="locateCatalog">Locate catalog</button><button type="button" id="saveRecovery">Save recovery copy</button></div></div><p id="manageError" role="alert"></p><menu><button id="closeManage">Close</button></menu></form></dialog>`);
function snapshotOpenProject(){return {name:state.projectName||'Project',source:state.source,assets:state.files.map(({missing,...file})=>file),photos:structuredClone(state.photos),selected:state.current?.id||null}}
function setCatalogProblem(message){catalogProblem=true;$('#catalogWarning').hidden=false;$('#catalogWarningText').textContent=message||'Edits remain in memory but cannot be saved here. Save a recovery copy before closing.';$('#saveStatus').textContent='Catalog unavailable — recovery needed';}
function clearCatalogProblem(){catalogProblem=false;$('#catalogWarning').hidden=true;}
async function checkCatalog(){
  if(!state.projectId||catalogCheckBusy||projectClosing||catalogCapabilities?.version<2)return;
  catalogCheckBusy=true;const id=state.projectId;
  try{const status=await projectRequest(`/api/projects/${id}/status`);if(id!==state.projectId)return;
    if(!status.available)setCatalogProblem();else if(catalogProblem){await saveProject();clearCatalogProblem()}
  }catch(e){if(id===state.projectId)setCatalogProblem('The catalog cannot be reached. Keep this window open, or save a recovery copy when the photo engine is available.')}
  finally{catalogCheckBusy=false}
}
setInterval(checkCatalog,5000);window.addEventListener('focus',checkCatalog);
window.addEventListener('beforeunload',e=>{if(catalogProblem){e.preventDefault();e.returnValue=''}});
saveProject=function(){
  if(!state.projectId||projectClosing)return Promise.resolve();
  const id=state.projectId,body=JSON.stringify({project_id:id,source:state.source,photos:state.photos,selected:state.current?.id});
  $('#saveStatus').textContent=catalogProblem?'Trying to save…':'Saving…';
  saveChain=saveChain.catch(()=>{}).then(async()=>{const res=await fetch('/api/project',{method:'POST',headers:{'Content-Type':'application/json'},body,keepalive:body.length<60000});if(!res.ok)throw new Error((await res.json()).detail||'Catalog save failed');if(state.projectId===id){clearCatalogProblem();$('#saveStatus').textContent='All edits saved'}});
  saveChain.catch(()=>{if(state.projectId===id)setCatalogProblem()});return saveChain;
};
function showManage(){if(!state.projectId)return;if(catalogCapabilities?.version<2){toast('Restart the photo engine to manage projects.');return}$('#manageTitle').textContent=`Manage “${state.projectName||'project'}”`;$('#manageLocation').textContent=state.catalogPath||'';$('#locatePath').value='';$('#manageError').textContent='';$('#manageProjectDialog').showModal();$('#closeManage').focus()}
$('#manageProject').onclick=showManage;$('#locateNow').onclick=showManage;
$('#browseCatalogRecovery').onclick=async()=>{const path=await chooseProjectPath('catalog');if(path)$('#locatePath').value=path};
async function managementAction(action){
  $$('#manageProjectDialog button,#recoverNow,#locateNow').forEach(b=>b.disabled=true);$('#manageError').textContent='';
  try{await action()}catch(e){$('#manageError').textContent=e.message;if(!$('#manageProjectDialog').open)toast(e.message)}finally{$$('#manageProjectDialog button,#recoverNow,#locateNow').forEach(b=>b.disabled=false)}
}
const useManagedProject=useProject;
useProject=async function(data){if(catalogProblem&&!projectClosing)throw new Error('Save a recovery copy or locate the current catalog before switching projects.');await useManagedProject(data);clearCatalogProblem();};
async function closeRemovedProject(){
  state.previewController?.abort();clearTimeout(state.previewTimer);state.linearToken++;state.projectId=null;state.source='';state.files=[];state.photos={};state.current=null;state.after=null;state.before=null;state.liveFrame=null;state.linearReady=false;state.history=[];state.future=[];state.live=null;state.drag=null;
  localStorage.removeItem('referenceDarkroomProject');clearCatalogProblem();saveChain=Promise.resolve();filterFiles();refreshControls();drawCanvas();
  $('#catalogLocation').textContent='';$('#sourcePath').value='';$('#sourceStatus').textContent='';$('#filename').textContent='No project open';$('#liveStatus').textContent='';$('#clippingStats').textContent='';$('#loading').style.display='none';$('#saveStatus').textContent='Project closed';$('#empty').style.display='flex';$('#empty b').textContent='Create or import a project';$('#empty span').textContent='Choose Create project to start fresh, or Import catalog to reopen one.';$('#emptyAddPhotos').textContent='Create project';$('.controls').inert=true;
  $$('.toolbar button:not(#toggleLibrary),.rating button,#export,#before,#undo,#redo').forEach(b=>b.disabled=true);
  await refreshProjects();$('#manageProjectDialog').close();
}
async function removeOrTrash(kind){
  const confirmedId=state.projectId;
  if(!await confirmProjectRemoval(kind))return;
  if(state.projectId!==confirmedId)throw new Error('The active project changed. Open its management dialog and try again.');
  await saveChain.catch(()=>{});if(!catalogProblem)await saveProject();
  if(catalogProblem)throw new Error('Save a recovery copy or locate the catalog before removing this open project.');
  const id=state.projectId;projectClosing=true;
  try{await projectRequest(`/api/projects/${id}/${kind}`,{});await closeRemovedProject();toast(kind==='trash'?'Project folder moved to Trash. Restore it there if needed.':'Removed from library. The catalog and project folder were kept.')}finally{projectClosing=false}
}
document.body.insertAdjacentHTML('beforeend',`<dialog id="confirmProjectRemoval"><form method="dialog"><h2 id="confirmRemovalTitle">Are you sure you want to delete this project?</h2><p id="confirmRemovalName"></p><p id="confirmRemovalExplanation"></p><menu><button value="cancel" id="cancelRemoval">Cancel</button><button value="confirm" id="acceptRemoval">Delete project</button></menu></form></dialog>`);
function confirmProjectRemoval(kind){
  const dialog=$('#confirmProjectRemoval');dialog.returnValue='cancel';
  $('#confirmRemovalTitle').textContent=kind==='trash'?'Are you sure you want to delete this project?':'Are you sure you want to remove this project from the library?';
  $('#confirmRemovalName').textContent=state.projectName||'This project';
  $('#confirmRemovalExplanation').textContent=kind==='trash'?'Its project folder, catalog and any exports inside that folder will move to Trash. Referenced originals outside that folder will not be deleted. You can restore the folder from Trash.':'The project will disappear from this library. Its catalog, folder, photos and edits will stay on disk; import the catalog to reopen it.';
  $('#acceptRemoval').textContent=kind==='trash'?'Delete project — Move to Trash':'Remove from library';
  return new Promise(resolve=>{dialog.addEventListener('close',()=>resolve(dialog.returnValue==='confirm'),{once:true});dialog.showModal();$('#cancelRemoval').focus()});
}
$('#removeProject').onclick=()=>managementAction(()=>removeOrTrash('remove'));
$('#trashProject').onclick=()=>managementAction(()=>removeOrTrash('trash'));
async function recoverOpenProject(){
  await saveChain.catch(()=>{});const snapshot=snapshotOpenProject();const data=await projectRequest('/api/catalog-recovery',snapshot);
  clearCatalogProblem();saveChain=Promise.resolve();await useProject(data);$('#manageProjectDialog').close();toast('Recovery project saved. Your original project was kept.');
}
$('#saveRecovery').onclick=$('#recoverNow').onclick=()=>managementAction(recoverOpenProject);
$('#locateCatalog').onclick=()=>managementAction(async()=>{
  await saveChain.catch(()=>{});await projectRequest(`/api/projects/${state.projectId}/locate`,{path:$('#locatePath').value.trim(),asset_ids:state.files.map(f=>f.id)});
  await saveProject();clearCatalogProblem();const data=await projectRequest(`/api/projects/${state.projectId}`);await useProject(data);$('#manageProjectDialog').close();toast('Catalog reconnected and current edits saved.');
});
