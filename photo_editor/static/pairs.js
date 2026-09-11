/* Pure library projection: catalog assets and per-file edits are never merged. */
(function(root){
  const raw=new Set(['RAF','NEF','NRW','CR2','CR3','CRW','ARW','SR2','SRF','DNG','ORF','RW2','PEF','SRW','RAW','3FR','IIQ','FFF','MOS','MRW','ERF','X3F']);
  function format(f){const ext=(f.type||f.path.split('.').pop()).toUpperCase();return raw.has(ext)?'raw':['JPG','JPEG'].includes(ext)?'jpg':'other'}
  function pairs(files){
    const buckets=new Map(),result=new Map();
    for(const f of files){if(format(f)==='other')continue;const key=f.path.replace(/\.[^/.]+$/,'');if(!buckets.has(key))buckets.set(key,[]);buckets.get(key).push(f)}
    for(const group of buckets.values()){
      const raws=group.filter(f=>format(f)==='raw'),jpgs=group.filter(f=>format(f)==='jpg');
      if(raws.length!==1||jpgs.length!==1)continue;
      const [r,j]=[raws[0],jpgs[0]];
      // Reject contradictory capture metadata when provided by an importer.
      if(r.capture_time&&j.capture_time&&r.capture_time!==j.capture_time)continue;
      result.set(r.id,[r,j]);result.set(j.id,[r,j]);
    }
    return result;
  }
  function project(files,{mode='all',group=true,preferred=new Map(),accept=()=>true}={}){
    const index=pairs(files),seen=new Set(),visible=[];
    for(const f of files){
      if(seen.has(f.id))continue;
      const members=group?(index.get(f.id)||[f]):[f];members.forEach(m=>seen.add(m.id));
      const eligible=members.filter(m=>(mode==='all'||format(m)===mode)&&accept(m));
      if(!eligible.length)continue;
      visible.push(eligible.find(m=>m.id===preferred.get(members[0].id)&&!m.missing)||eligible.find(m=>!m.missing)||eligible[0]);
    }
    return {visible,index};
  }
  function equal(a,b){if(a===b)return true;if(!a||!b||typeof a!=='object'||typeof b!=='object')return false;const ak=Object.keys(a),bk=Object.keys(b);return ak.length===bk.length&&ak.every(k=>Object.hasOwn(b,k)&&equal(a[k],b[k]))}
  function hasEdits(recipe,defaults){if(!recipe||!defaults)return false;return Object.keys(defaults).some(k=>k!=='preset'&&!equal(recipe[k]??defaults[k],defaults[k]))}
  const api={format,pairs,project,hasEdits};if(typeof module!=='undefined')module.exports=api;else root.PhotoPairs=api;
})(globalThis);
