// Dedicated isolated catalog only. Start a test server on 8766.
const {chromium}=require(process.env.PLAYWRIGHT_PATH||'playwright');
const fs=require('fs'),os=require('os'),path=require('path');
(async()=>{
 const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--use-angle=metal']});
 try{
 const page=await browser.newPage({viewport:{width:1400,height:1000}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:8766/');await page.waitForFunction(()=>state.config!==null);
 const gpu=await page.evaluate(()=>{
  const r=new UnifiedPhotoRenderer(),w=100,h=100,src=new Float32Array(w*h*4);
  for(let y=0;y<h;y++)for(let x=0;x<w;x++){const i=(y*w+x)*4;src[i]=x<50?4:0;src[i+3]=1;}r.setSource(src.buffer,w,h);
  const s={size:.3,feather:0,flow:100,opacity:100,offset:[-.5,0],sample:'original',points:[[.75,.5]]},l={enabled:true,opacity:100,strokes:[s]};
  const read=layers=>{const t=r.cloneSource(layers,100),g=r.gl;g.bindFramebuffer(g.FRAMEBUFFER,t.fbo);const p=new Float32Array(w*h*4);g.readPixels(0,0,w,h,g.RGBA,g.FLOAT,p);return p;};
  let p=read([l]);if(p[(50*w+75)*4]!==4||p[(10*w+75)*4]!==0)throw Error('GPU clone placement or RAW range');
  p=read([{...l,opacity:50}]);if(p[(50*w+75)*4]!==2)throw Error('GPU layer opacity');
  p=read([{...l,strokes:[s,{...s,erase:true}]}]);if(p[(50*w+75)*4]!==0)throw Error('GPU erase');
  const recipe={...state.config.default_recipe,clone_layers:[l],exposure:-3};r.render(recipe,0,{full:true,crop:true});const out=r.pixels();if(out.width!==100||!out.bytes.some(v=>v>0))throw Error('Full export');
  // Replaying before geometry must match a baked linear source after geometry.
  const cloned=read([l]),baked=new UnifiedPhotoRenderer();baked.setSource(cloned.buffer,w,h);
  // Retouch render targets use bilinear sampling, so match the reference sampler.
  baked.gl.bindTexture(baked.gl.TEXTURE_2D,baked.source);baked.gl.texParameteri(baked.gl.TEXTURE_2D,baked.gl.TEXTURE_MIN_FILTER,baked.gl.LINEAR);
  for(const geometry of [{rotation:90},{straighten:12,flip_h:true,crop:[.1,.2,.6,.5]}]){
    r.render({...recipe,...geometry},0,{full:true,crop:true});baked.render({...recipe,...geometry,clone_layers:[]},0,{full:true,crop:true});
    const a=r.pixels(),b=baked.pixels();let max=0,total=0;for(let i=0;i<a.bytes.length;i++){const d=Math.abs(a.bytes[i]-b.bytes[i]);max=Math.max(max,d);total+=d;}if(a.width!==b.width||a.height!==b.height||max>1)throw Error('Retouch geometry/export mismatch '+JSON.stringify({geometry,max,mean:total/a.bytes.length}));
  }
  baked.dispose();if(r.gl.getError())throw Error('GL error');r.dispose();return 'float32, confinement, opacity, erase, geometry/export passed';
 });
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'clone-fixture-'));
 const png=await page.evaluate(()=>{const c=document.createElement('canvas');c.width=1200;c.height=800;const x=c.getContext('2d');x.fillStyle='#385d70';x.fillRect(0,0,1200,800);x.fillStyle='#eead7e';x.fillRect(0,0,600,800);return c.toDataURL().split(',')[1]});fs.writeFileSync(path.join(root,'Clone test.png'),Buffer.from(png,'base64'));
 await page.evaluate(async root=>{await useProject(await projectRequest('/api/projects',{name:'Clone QA'}));await startProgressiveImport(root)},root);
 await page.waitForFunction(()=>state.linearReady);await page.click('#cloneWorkspace');await page.waitForTimeout(250);
 const b=await page.locator('#canvas').boundingBox();const at=(x,y)=>({x:b.x+b.width*x,y:b.y+b.height*y});
 let p=at(.25,.5);await page.keyboard.down('Alt');await page.mouse.click(p.x,p.y);await page.keyboard.up('Alt');p=at(.75,.5);await page.mouse.move(p.x,p.y);await page.mouse.down();await page.mouse.move(p.x+25,p.y+10,{steps:4});await page.mouse.up();
 const strokes=await page.evaluate(()=>JSON.stringify(recipe().clone_layers));await page.mouse.move(p.x+60,p.y+40);if(strokes!==await page.evaluate(()=>JSON.stringify(recipe().clone_layers)))throw Error('Sticky clone stroke');
 if(!await page.evaluate(()=>recipe().clone_layers[0].strokes[0].points.length>1))throw Error('No painted stroke');
 await page.click('#undo');if(await page.evaluate(()=>recipe().clone_layers?.length))throw Error('Undo');await page.click('#redo');
 await page.waitForFunction(()=>document.querySelector('#saveStatus').textContent.includes('All edits saved'));
 await page.screenshot({path:'/tmp/darkroom-clone-qa.png'});
 await page.reload();await page.waitForFunction(()=>state.linearReady);if(strokes!==await page.evaluate(()=>JSON.stringify(recipe().clone_layers)))throw Error('Persistence');
 if(errors.length)throw Error(errors.join(';'));console.log({gpu,ui:'paint, release, undo, redo, save/reload passed',errors});
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
