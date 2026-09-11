/* RAW+JPG grouping is a view, never a catalog mutation. */
const libraryPrefs={mode:localStorage.getItem('darkroomFormat')||'all',group:localStorage.getItem('darkroomPairs')!=='false',preferred:new Map(),index:new Map()};
if(!['all','raw','jpg'].includes(libraryPrefs.mode))libraryPrefs.mode='all';
$('.libhead').insertAdjacentHTML('afterend',`<div class="formatTools"><div class="formatTabs" role="group" aria-label="Photo format"><button data-format="all">All</button><button data-format="raw">RAW</button><button data-format="jpg">JPG</button></div><label><input id="groupPairs" type="checkbox"> Group RAW + JPG</label><small id="formatCount" aria-live="polite"></small></div>`);
$('#filename').insertAdjacentHTML('beforebegin','<span id="pairSwitch" class="formatTabs" role="group" aria-label="Original file version" hidden><button data-version="raw">RAW</button><button data-version="jpg">JPG</button></span>');
$('#groupPairs').checked=libraryPrefs.group;
function syncPairSwitch(){const pair=state.current&&libraryPrefs.index.get(state.current.id);$('#pairSwitch').hidden=!pair;for(const b of $$('[data-version]')){const f=pair?.find(f=>PhotoPairs.format(f)===b.dataset.version);b.disabled=!f||f.missing;b.classList.toggle('active',f===state.current);b.setAttribute('aria-pressed',String(f===state.current));b.title=f?`${f.name}${f.missing?' — original offline':''}`:''}}
filterFiles=function(){
  const rating=$('#filter').value;
  const result=PhotoPairs.project(state.files,{...libraryPrefs,accept:f=>{const r=photoState(f).rating;return rating==='all'||rating==='picked'&&r>0||rating==='unrated'&&r===0||rating==='rejected'&&r<0}});
  state.visible=result.visible;libraryPrefs.index=result.index;
  $('#photoCount').textContent=state.visible.length;
  $('#formatCount').textContent=`${state.visible.length} shown · ${state.files.length} original files`;
  for(const b of $$('[data-format]')){b.classList.toggle('active',b.dataset.format===libraryPrefs.mode);b.setAttribute('aria-pressed',String(b.dataset.format===libraryPrefs.mode))}
  renderFilmstrip();syncPairSwitch();
};
// The original handler was assigned before this extension loaded.
$('#filter').onchange=()=>filterFiles();
const fileThumb=thumbElement;
thumbElement=function(f,i){const el=fileThumb(f,i);if(libraryPrefs.group&&libraryPrefs.index.has(f.id)){const badge=document.createElement('span');badge.className='pairBadge';badge.textContent='RAW + JPG';el.append(badge)}return el};
const selectFile=selectPhoto;
const usePairedProject=useProject;
useProject=async function(data){libraryPrefs.preferred.clear();if(!data.saved.selected){const view=PhotoPairs.project(data.files,libraryPrefs);data={...data,saved:{...data.saved,selected:view.visible.find(f=>!f.missing)?.id}}}await usePairedProject(data)};
selectPhoto=async function(f){
  if(!f||f.missing)return f?selectFile(f):undefined;
  // On initial project selection, honor the active format filter.
  if(libraryPrefs.mode!=='all'&&PhotoPairs.format(f)!==libraryPrefs.mode){f=state.visible.find(v=>libraryPrefs.index.get(f.id)?.includes(v))||state.visible[0]||f}
  const pair=libraryPrefs.index.get(f.id);if(pair)libraryPrefs.preferred.set(pair[0].id,f.id);
  const pending=selectFile(f);filterFiles();syncPairSwitch();await pending;
};
async function setFormat(mode){libraryPrefs.mode=mode;localStorage.setItem('darkroomFormat',mode);filterFiles();if(state.current&&!state.visible.includes(state.current)){const peer=state.visible.find(f=>libraryPrefs.index.get(state.current.id)?.includes(f));if(peer||state.visible.length)await selectPhoto(peer||state.visible[0])}}
for(const b of $$('[data-format]'))b.onclick=()=>setFormat(b.dataset.format);
$('#groupPairs').onchange=()=>{libraryPrefs.group=$('#groupPairs').checked;localStorage.setItem('darkroomPairs',String(libraryPrefs.group));filterFiles()};
for(const b of $$('[data-version]'))b.onclick=async()=>{const f=libraryPrefs.index.get(state.current?.id)?.find(f=>PhotoPairs.format(f)===b.dataset.version);if(!f||f.missing)return;if(libraryPrefs.mode!=='all'&&libraryPrefs.mode!==b.dataset.version){libraryPrefs.mode=b.dataset.version;localStorage.setItem('darkroomFormat',libraryPrefs.mode)}await selectPhoto(f)};
// A local clipboard also works when the native webview denies system clipboard access.
let copiedRecipe=null;
$('#copyRecipe').onclick=async()=>{if(!state.current)return;copiedRecipe=structuredClone(recipe());try{await navigator.clipboard.writeText(JSON.stringify(copiedRecipe))}catch{}toast('Recipe copied — paste onto RAW or JPG')};
$('#pasteRecipe').onclick=async()=>{if(!state.current)return;try{let data=copiedRecipe;try{const text=await navigator.clipboard.readText();if(text)data=JSON.parse(text)}catch{}if(!data||typeof data!=='object'||Array.isArray(data))throw new Error();snapshot();state.photos[state.current.id].recipe={...structuredClone(state.config.default_recipe),...structuredClone(data)};refreshControls();changed(true);toast('Recipe pasted. RAW and JPG may render differently.')}catch{toast('Copy a recipe first')}};
$('#lightControls').insertAdjacentHTML('afterend','<small class="recoveryHelp">Shadows targets dark tones, with up to 5 stops of lift near black and less near midtones. Highlights compresses bright tones. Exposure shifts the whole image. Strong shadow lift can reveal noise.</small>');
// A grouped thumbnail reports edits on either member, with the exact filenames
// in its tooltip. Ratings alone do not count as editing.
function markEditedThumb(el,f){
  const members=libraryPrefs.group?(libraryPrefs.index.get(f.id)||[f]):[f];
  const edited=members.filter(m=>PhotoPairs.hasEdits(state.photos[m.id]?.recipe,state.config?.default_recipe));
  let dot=el.querySelector('.editedDot');
  if(!edited.length){dot?.remove();return}
  if(!dot){dot=document.createElement('span');dot.className='editedDot';dot.setAttribute('role','img');el.append(dot)}
  dot.title=`Edited: ${edited.map(m=>m.name).join(', ')}`;dot.setAttribute('aria-label',dot.title);
}
const pairedThumb=thumbElement;
thumbElement=function(f,i){const el=pairedThumb(f,i);markEditedThumb(el,f);return el};
const saveWithEdits=saveProject;
saveProject=function(){
  if(state.current){const ids=new Set((libraryPrefs.index.get(state.current.id)||[state.current]).map(f=>f.id));for(const el of $$('#filmstrip .thumb')){if(ids.has(el.dataset.id)){const f=state.files.find(f=>f.id===el.dataset.id);if(f)markEditedThumb(el,f)}}}
  return saveWithEdits();
};
// These are display-range warnings, NOT a measurement of sensor headroom.
let statsRequest=0;
updateClippingStats=async function(){
  if(!state.current)return;const photo=state.current,token=++statsRequest,body=JSON.stringify(recipe());
  try{const res=await fetch('/api/clipping-stats',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:photo.path,recipe:JSON.parse(body)})});if(!res.ok)return;const s=await res.json();
    if(token!==statsRequest||photo!==state.current||body!==JSON.stringify(recipe()))return;
    $('#clippingStats').textContent=`Display highlights ≥ white: ${s.highlight_percent.toFixed(2)}% · Near-black: ${s.shadow_percent.toFixed(2)}% · Partial RGB clipping: ${s.recoverable_highlight_percent.toFixed(2)}%`;
    $('#clippingStats').title='Measured on the developed preview before the final display curve, not directly on RAW sensor samples. Partial RGB clipping means at least one channel is at/above white and another below it; this does not prove recoverable detail. Near-black uses a small nonzero threshold. RAW recovery headroom is not measured.';
  }catch{}
};
$('#clipShadows').title='Overlay near-black pixels in the current rendering (not sensor saturation analysis)';
filterFiles();
