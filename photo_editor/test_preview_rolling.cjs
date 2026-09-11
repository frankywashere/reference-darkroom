// Deterministic tests execute the real module with mock I/O and a virtual clock.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
let now=0,serial=0;const timers=new Map(),requests=[];
const elements=new Map();const element=()=>({style:{},append(){},setAttribute(){},textContent:'',open:false});
const files=Array.from({length:500},(_,i)=>({id:i,path:'/test/'+i,name:String(i)}));
const state={projectId:'test',files,visible:files,current:files[0],linearToken:1,linearReady:false};
const context={state,console,Map,Set,AbortController,DOMException,structuredClone,
 Date:{now:()=>now},setTimeout:(fn,delay)=>{const id=++serial;timers.set(id,{fn,time:now+delay});return id},clearTimeout:id=>timers.delete(id),
 document:{createElement:element},$:selector=>{if(!elements.has(selector))elements.set(selector,element());return elements.get(selector)},
 localStorage:{getItem:()=>null},recipe:()=>({}),photoState:()=>({recipe:{}}),renderHighBit:()=>false,drawCanvas(){},
 blobImage:async()=>({width:1800,height:1200}),fetch:async(url,options)=>{requests.push(JSON.parse(options.body).path);return {ok:true,headers:{get:()=> 'camera'},blob:async()=>({size:1024})}}};
context.window=context;
let source=fs.readFileSync(__dirname+'/static/library-progress.js','utf8');
source=source.replace(/\}\)\(\);\s*$/,`window.testCache={memory,compressed,prepared,failures,lookup,localKey,remember,rememberBlob,scheduleWarm,get decodedBytes(){return decodedBytes},decodedLimit};})();`);
vm.createContext(context);vm.runInContext(source,context);
async function flush(){for(let i=0;i<20;i++)await Promise.resolve()}
async function advance(ms){const until=now+ms;while(true){const next=[...timers].filter(([,v])=>v.time<=until).sort((a,b)=>a[1].time-b[1].time)[0];if(!next)break;now=next[1].time;timers.delete(next[0]);next[1].fn();await flush()}now=until;await flush()}
function select(i){state.current=files[i];state.linearToken++;context.loadScreenPreview(files[i],state.linearToken)}
(async()=>{
 select(0);await flush();
 // Navigation every 30 ms used to indefinitely postpone the 100 ms worker.
 for(let i=1;i<=60;i++){await advance(30);select(i);await flush()}
 const warmed=[...context.testCache.prepared];assert(warmed.length>=15,'worker starved during sustained cycling');
 // Evict a successfully prepared photo from BOTH actual caches via budget pressure.
 const c=context.testCache,key=c.localKey(files[61],{});await c.lookup(files[61],{});c.prepared.add(key);
 for(let i=0;i<260;i++){c.remember('pressure'+i,{width:1800,height:1200},'camera');c.rememberBlob('pressure'+i,{size:1024*1024},'camera')}
 assert(!c.memory.has(key)&&!c.compressed.has(key));assert(c.prepared.has(key));
 assert.equal(c.decodedLimit,2*1024**3);assert(c.decodedBytes<=c.decodedLimit);
 const before=requests.filter(p=>p==='/test/61').length;
 select(60);await advance(250);
 assert(requests.filter(p=>p==='/test/61').length>before,'evicted preview never re-fetched');assert(c.memory.has(key));
 // Reversal must move preloading behind the new position.
 select(59);await advance(400);assert(c.memory.has(c.localKey(files[58],{})),'direction reversal failed');
 console.log('PASS sustained rolling, double-cache eviction/reload, reversal, 2 GiB memory bound; warmed during cycling:',warmed.length);
})().catch(e=>{console.error(e);process.exitCode=1});
