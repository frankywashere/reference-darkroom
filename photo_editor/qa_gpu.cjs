// Standalone test browser: never loads the project/catalog UI or changes recipes.
const {chromium}=require(process.env.PLAYWRIGHT_PATH||'/tmp/darkroom-gpu-test/node_modules/playwright');
const fs=require('fs');
(async()=>{
 const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--use-angle=metal']});
 const page=await browser.newPage({viewport:{width:1000,height:700}});
 page.on('console',m=>{if(m.type()==='error')console.error(m.text())});
 page.on('pageerror',e=>console.error(e));
 await page.goto('http://127.0.0.1:8765/static/qa-gpu.html');
 const result=await page.evaluate(async()=>{
   const r=new UnifiedPhotoRenderer(),w=128,h=96,src=new Float32Array(w*h*4);
   for(let y=0;y<h;y++)for(let x=0;x<w;x++){let i=(y*w+x)*4;src[i]=.01+x/w*.5;src[i+1]=.02+y/h*.4;src[i+2]=.1;src[i+3]=1;}
   r.setSource(src.buffer,w,h);
   const base={...(await(await fetch('/api/config')).json()).default_recipe,denoise:0,sharpen:0};
   const render=recipe=>{r.render(recipe,0,{full:true});return r.pixels();};
   const a=render(base),b=render({...base,masks:[{type:'brush',strokes:[{size:.25,feather:60,flow:100,opacity:100,points:[[.25,.25]]}],exposure:1}]});
   const cameraProfile={ev:.7,gamma:.8};
   const camera=render({...base,camera_look_enabled:true,camera_look:cameraProfile});
   if(!camera.bytes.some((v,i)=>Math.abs(v-a.bytes[i])>10))throw Error('Camera tone did not affect GPU output');
   const disabledCamera=render({...base,camera_look_enabled:false,camera_look:cameraProfile});
   if(disabledCamera.bytes.some((v,i)=>v!==a.bytes[i]))throw Error('Disabled camera tone changed pixels');
   let inside=0,outside=0;
   for(let y=0;y<h;y++)for(let x=0;x<w;x++){const i=(y*w+x)*4,d=Math.max(...[0,1,2].map(c=>Math.abs(a.bytes[i+c]-b.bytes[i+c])));if(x<16||x>48||y<12||y>36)outside=Math.max(outside,d);else inside=Math.max(inside,d);}
   if(inside<10||outside>1)throw Error('Mask confinement failed '+inside+' / '+outside);
   const brush={type:'brush',exposure:1,strokes:[{size:.25,feather:0,flow:100,opacity:100,points:[[.25,.25]]}]};
   for(const m of [{...brush,enabled:false},{...brush,amount:0},{...brush,strokes:[]}]){
     const p=render({...base,masks:[m]});if(p.bytes.some((v,i)=>v!==a.bytes[i]))throw Error('Inactive mask changed pixels');
   }
   const erased=render({...base,masks:[{...brush,strokes:[...brush.strokes,{...brush.strokes[0],erase:true}]}]});
   const center=(24*w+32)*4;if(Math.abs(erased.bytes[center]-a.bytes[center])>1)throw Error('Erase did not remove mask');
   const tests=[];
   for(const edit of [{rotation:90},{straighten:8},{curve:[10,18,48,82,96]},{denoise:80,clarity:70,sharpen:65,grain:30,vignette:45},{masks:[{type:'ellipse',x:.5,y:.5,width:.2,height:.3,exposure:1,temperature:20},{type:'linear',x:.5,y:.5,angle:45,size:.3,exposure:-1}]}]){
     const first=render({...base,...edit}),second=render({...base,...edit});
     if(first.bytes.some((v,i)=>v!==second.bytes[i]))throw Error('Preview/export path not deterministic');
     const display=document.createElement('canvas');display.width=r.canvas.width;display.height=r.canvas.height;
     const ctx=display.getContext('2d');ctx.drawImage(r.canvas,0,0);const shown=ctx.getImageData(0,0,display.width,display.height).data;
     if(first.bytes.some((v,i)=>Math.abs(v-shown[i])>1))throw Error('Displayed pixels differ from export pixels');
     tests.push({edit,width:first.width,height:first.height});
   }
   r.render(base,0,{full:true});const pix=r.pixels();
   const first=[...pix.bytes.slice(0,3)],last=[...pix.bytes.slice(-4,-1)];
   if(first[0]>=last[0]||first[1]>=last[1])throw Error('Image orientation incorrect');
   window.testRenderer=r;return {inside,outside,first,last,tests,renderer:r.gl.getParameter(r.gl.RENDERER)};
 });
 console.log(JSON.stringify(result,null,2));
 if(process.argv.includes('--raw')){
   const raw=await page.evaluate(async()=>{
     const r=window.testRenderer,res=await fetch('/api/gpu-source?path='+encodeURIComponent('/Volumes/SU800/Ari/DSCF2876.RAF'));
     r.setSource(await res.arrayBuffer(),+res.headers.get('X-Width'),+res.headers.get('X-Height'));
     const base=(await(await fetch('/api/config')).json()).default_recipe;
     const edit={...base,shadows:45,clarity:15,masks:[{type:'brush',strokes:[{size:.25,feather:70,flow:100,opacity:100,points:[[.5,.5],[.52,.5]]}],exposure:.5}]};
     let start=performance.now();r.render(edit,0,{side:1800});r.gl.finish();let ms=performance.now()-start;
     const frames=[];for(let i=0;i<12;i++){const t=performance.now();r.render({...edit,exposure:i*.01},0,{side:1800});r.gl.readPixels(0,0,1,1,r.gl.RGBA,r.gl.UNSIGNED_BYTE,new Uint8Array(4));frames.push(performance.now()-t);}
     r.render(edit,0,{side:1800});
     document.body.append(r.canvas);r.canvas.style.width='900px';
     window.rawRecipe=edit;return {ms,width:r.width,height:r.height,frames};
   });console.log('RAW',JSON.stringify(raw));await page.screenshot({path:'/tmp/darkroom-gpu-unified-qa.png'});
   if(process.argv.includes('--export'))console.log('EXPORT',await page.evaluate(async()=>{
     const r=window.testRenderer,start=performance.now();r.render(window.rawRecipe,0,{full:true,crop:true});const p=r.pixels();
     const q=new URLSearchParams({source:'/Volumes/SU800/Ari/DSCF2876.RAF',destination:'/tmp/darkroom-unified-qa',prefix:'GPU_',quality:96,width:p.width,height:p.height});
     const res=await fetch('/api/gpu-jpg?'+q,{method:'POST',body:p.bytes});return {status:res.status,result:await res.json(),ms:performance.now()-start};
   }));
 }
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
