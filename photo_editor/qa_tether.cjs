// --hardware explicitly requests one real test exposure into a temporary project.
// --repeat requests a second exposure in the same connected session.
const {chromium}=require(process.env.PLAYWRIGHT_PATH||'playwright');
(async()=>{
 const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--use-angle=metal']});
 const page=await browser.newPage({viewport:{width:1600,height:1100}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 const mock=process.argv.includes('--switch')?{installed:true,connected:false,live:false,devices:[{id:1,name:'Z 8',available:true}],settings:{},session:null,frame_age:null,cursor:0,events:[]}:null;
 if(mock)await page.route('**/api/tether/**',async route=>{
  const req=route.request();if(req.url().includes('/target')&&mock.connected){const id=req.postDataJSON().project_id;mock.session={...mock.session,project_id:id,project_name:'Switched project'};}
  await route.fulfill({json:mock});
 });
 try{
  await page.goto('http://127.0.0.1:8766');await page.waitForFunction(()=>state.config!==null);
  const project=await page.evaluate(async()=>{const p=await projectRequest('/api/projects',{name:'Z8 tether QA'});await useProject(p);return p.project_id;});
  await page.click('#openTether');await page.waitForFunction(()=>document.querySelector('#tetherDevices').options[0]?.value==='1',{timeout:15000});
  if(mock){
   mock.connected=true;mock.live=true;mock.session={project_id:project,project_name:'Initial',destination:'/tmp/mock-session',device_id:1};
   const second=await page.evaluate(async()=>{const p=await projectRequest('/api/projects',{name:'Switched project'});await useProject(p);return p.project_id});
   if(mock.session.project_id!==second||!mock.live)throw Error('Project switch failed or stopped live view');
   await page.waitForFunction(()=>document.querySelector('#tetherSession').textContent.includes('Switched project'));
   console.log('Project switch follows selection without reconnecting: PASS');
  }
  if(process.argv.includes('--hardware')){
   await page.click('#tetherConnect');await page.waitForFunction(()=>!document.querySelector('#tetherImage').hidden,{timeout:30000});
   const dimensions=await page.locator('#tetherImage').evaluate(im=>({width:im.naturalWidth,height:im.naturalHeight}));
   if(dimensions.width<500)throw Error('Live view resolution too small');
   await page.screenshot({path:'/tmp/darkroom-tether-live-qa.png'});
   await page.locator('#tetherAutofocus').uncheck();await page.click('#tetherCapture');
   await page.waitForFunction(()=>state.files.length>0,{timeout:60000});await page.waitForFunction(()=>state.linearReady,{timeout:60000});
   await page.waitForFunction(()=>!document.querySelector('#tetherCapture').disabled);
   if(process.argv.includes('--repeat')){const count=await page.evaluate(()=>state.files.length);await page.click('#tetherCapture');await page.waitForFunction(n=>state.files.length>n,count,{timeout:60000});await page.waitForFunction(()=>state.linearReady);await page.waitForFunction(()=>!document.querySelector('#tetherCapture').disabled);}
   const result=await page.evaluate(()=>({files:state.files.map(f=>({name:f.name,bytes:f.bytes})),source:state.sourceInfo,photo:recipe(),project:state.projectId}));
   if(result.project!==project)throw Error('Wrong project');
   if(!result.files.some(f=>f.bytes>10000))throw Error('Incomplete transfer');
   await page.screenshot({path:'/tmp/darkroom-tether-capture-qa.png'});
   await page.click('#tetherDisconnect');await page.waitForFunction(()=>!document.querySelector('#tetherConnection').hidden);
   await page.click('#hideTether');await page.reload();await page.waitForFunction(()=>state.linearReady,{timeout:60000});
   if(!await page.evaluate(()=>state.files.length>0))throw Error('Capture did not survive reopening');
   console.log(JSON.stringify({dimensions,result,errors},null,2));
  }
  if(errors.length)throw Error(errors.join(';'));
 }catch(error){await page.screenshot({path:'/tmp/darkroom-tether-failure.png'}).catch(()=>{});console.error(await page.locator('#tetherError').textContent().catch(()=>''));throw error;}finally{
  await page.request.post('http://127.0.0.1:8766/api/tether/disconnect',{data:{}}).catch(()=>{});
  await browser.close();
 }
})().catch(e=>{console.error(e);process.exit(1)});
