// Run against an isolated backend with REFERENCE_DARKROOM_DATA/PROJECTS set.
const {chromium}=require(process.env.PLAYWRIGHT_PATH||'/tmp/darkroom-gpu-test/node_modules/playwright');
const fs=require('fs'),path=require('path'),os=require('os');
(async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'darkroom-library-fixtures-'));
 const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--use-angle=metal']});
 const page=await browser.newPage({viewport:{width:1400,height:950}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:8766/');await page.waitForFunction(()=>state.config!==null);
 const png=await page.evaluate(()=>{const c=document.createElement('canvas');c.width=2400;c.height=1600;const x=c.getContext('2d');x.fillStyle='#92684b';x.fillRect(0,0,c.width,c.height);x.fillStyle='#eee';x.fillRect(50,60,500,350);return c.toDataURL('image/png').split(',')[1];});
 for(let i=0;i<36;i++)fs.writeFileSync(path.join(root,String(i).padStart(3,'0')+'.png'),Buffer.from(png,'base64'));
 const data=await page.evaluate(async root=>{const p=await projectRequest('/api/projects',{name:'Library QA'});await useProject(p);await startProgressiveImport(root);return p;},root);
 await page.waitForFunction(()=>document.querySelector('#importWorkText').textContent.includes('Import complete'),{timeout:60000});
 await page.waitForFunction(()=>state.linearReady,{timeout:60000});
 await page.waitForFunction(()=>document.querySelector('#previewWorkText').textContent.includes('saved'),{timeout:30000});
 const first=await page.evaluate(()=>({count:state.files.length,width:state.sourceInfo.width,height:state.sourceInfo.height,recipe:recipe(),file:state.current,project:state.projectId}));
 if(first.count!==36||first.width!==2400||first.height!==1600)throw Error('Import or native dimensions incorrect');
 const cached=await page.evaluate(async f=>{const res=await fetch('/api/screen-preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:f.file.path,recipe:f.recipe})});return res.headers.get('X-Preview-Kind');},first);
 if(cached!=='edited')throw Error('Edited preview did not persist');
 await page.reload();await page.waitForFunction(()=>state.current!==null);
 await page.waitForFunction(()=>state.after!==null,{timeout:30000});
 const ratio=await page.evaluate(()=>{const im=state.after;return (im.naturalWidth||im.width)/(im.naturalHeight||im.height);});
 if(Math.abs(ratio-1.5)>.001)throw Error('Screen preview aspect ratio incorrect: '+ratio);
 await page.waitForFunction(()=>state.linearReady);
 // Holding navigation must keep a useful frame and defer foreground decoding.
 let rawRequests=0;const countRaw=req=>{if(req.url().includes('/api/gpu-source'))rawRequests++;};
 page.on('request',countRaw);
 await page.keyboard.down('ArrowDown');
 for(let i=0;i<5;i++){await page.waitForTimeout(70);await page.keyboard.down('ArrowDown');}
 await page.waitForTimeout(500);
 const during=await page.evaluate(()=>({held:window.photoNavigationHeld,frame:!!state.after,ready:state.linearReady}));
 if(!during.held||!during.frame||during.ready||rawRequests)throw Error('Rapid browsing started RAW work or blanked the frame: '+JSON.stringify({during,rawRequests}));
 await page.keyboard.up('ArrowDown');
 await page.waitForFunction(()=>state.linearReady,{timeout:30000});
 page.off('request',countRaw);
 if(rawRequests!==1)throw Error('Expected one RAW load after release, got '+rawRequests);
 await page.screenshot({path:'/tmp/darkroom-library-qa.png'});
 console.log(JSON.stringify({count:first.count,persistentCache:cached,ratio,rapidBrowsing:during,rawRequests,errors,fixtureRoot:root}));
 if(errors.length)throw Error(errors.join('; '));
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
