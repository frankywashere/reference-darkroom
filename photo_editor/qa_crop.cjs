// Run against the isolated QA library, never a user's catalog.
const {chromium}=require('/tmp/darkroom-gpu-test/node_modules/playwright');
(async()=>{
 const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--use-angle=metal']});
 const page=await browser.newPage({viewport:{width:1400,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:8766');await page.waitForFunction(()=>state.linearReady);
 for(const ending of ['release','outside','capture-loss','blur']){
   await page.evaluate(()=>{recipe().crop=[.15,.15,.7,.7];delete recipe().crop_frame;recipe().crop_aspect='free';setTool('crop');renderHighBit();});
   const box=await page.locator('#canvas').boundingBox(),x=box.x+box.width*.15,y=box.y+box.height*.15;
   await page.mouse.move(x,y);await page.mouse.down();await page.mouse.move(x+30,y+25,{steps:3});
   if(await page.evaluate(()=>recipe().crop[0]===.15))throw Error('Crop corner did not drag');
   if(ending==='outside'){await page.mouse.move(10,10);await page.mouse.up();}
   else if(ending==='release')await page.mouse.up();
   else if(ending==='blur')await page.evaluate(()=>window.dispatchEvent(new Event('blur')));
   else await page.evaluate(()=>{const canvas=document.querySelector('#canvas');canvas.dispatchEvent(new PointerEvent('lostpointercapture',{pointerId:1,bubbles:true}));});
   const stopped=await page.evaluate(()=>JSON.stringify(recipe().crop));
   await page.mouse.move(x+70,y+60,{steps:3});await page.mouse.up();
   if(await page.evaluate(()=>JSON.stringify(recipe().crop))!==stopped)throw Error('Sticky crop after '+ending);
 }
 await page.click('[data-aspect="0.8"]');await page.waitForFunction(()=>state.tool==='crop');
 const ratio=await page.evaluate(()=>{const b=CropMath.bounds(state.sourceInfo.width,state.sourceInfo.height,recipe());return recipe().crop[2]*b.w/(recipe().crop[3]*b.h)});
 if(Math.abs(ratio-.8)>1e-6)throw Error('4:5 incorrect');
 await page.evaluate(()=>{const s=document.querySelector('[data-key="straighten"]');s.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true}));s.value=10;s.dispatchEvent(new Event('input',{bubbles:true}));});
 await page.waitForTimeout(120);
 if(!await page.evaluate(()=>!!state.geometryPreview))throw Error('No fast geometry preview');
 await page.evaluate(()=>document.dispatchEvent(new PointerEvent('pointerup',{bubbles:true})));
 await page.click('#autoFillCrop');await page.waitForTimeout(250);
 await page.evaluate(()=>{document.querySelector('#presets').parentElement.open=false;document.querySelector('#lightControls').parentElement.open=false;});
 await page.screenshot({path:'/tmp/darkroom-crop-controls-qa.png'});
 const zoom=await page.locator('#cropZoom').inputValue();if(+zoom<=100)throw Error('Auto-fill did not increase zoom');
 await page.click('#doneCrop');await page.waitForTimeout(900);
 const output=await page.evaluate(async()=>{
   const r=recipe(),renderer=state.liveRenderer,shown=renderer.canvas.width/renderer.canvas.height;
   const res=await fetch('/api/screen-preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:state.current.path,recipe:r})});
   const image=await blobImage(await res.blob());
   renderer.render(r,0,{full:true,crop:true});const pixels=renderer.pixels();
   const query=new URLSearchParams({source:state.current.path,destination:'/tmp/darkroom-crop-export-qa',prefix:'crop_',quality:96,width:pixels.width,height:pixels.height});
   const exported=await fetch('/api/gpu-jpg?'+query,{method:'POST',body:pixels.bytes});if(!exported.ok)throw Error('JPG export failed');
   return {shown,cached:image.width/image.height,exported:pixels.width/pixels.height,path:(await exported.json()).path,crop:r.crop};
 });
 for(const key of ['shown','cached','exported'])if(Math.abs(output[key]-.8)>.003)throw Error(key+' crop mismatch '+JSON.stringify(output));
 await page.reload();await page.waitForFunction(()=>state.linearReady);
 if(!await page.evaluate(()=>recipe().crop_frame.zoom>1&&recipe().crop_aspect==='0.8'))throw Error('Crop did not persist');
 if(errors.length)throw Error(errors.join(';'));console.log({ratio,zoom,output,errors});await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
