const fs=require('fs'),vm=require('vm'),assert=require('assert');
const files=[{id:'raw',path:'/test/a.RAF'},{id:'jpg',path:'/test/a.JPG'}];
let calls=0,saves=0;
const elements=new Map(),element=()=>({style:{},prepend(){},checked:false,disabled:false});
const state={files,photos:{},config:{default_recipe:{camera_look_enabled:false,camera_look:null}},projectId:'p',linearToken:1,linearReady:true,current:files[0]};
const ctx={state,console,structuredClone,Map,document:{createElement:element},$:s=>{if(!elements.has(s))elements.set(s,element());return elements.get(s)},
 refreshControls(){},loadLinearSource:async()=>{},saveProject(){saves++},schedulePreview(){},toast(){},snapshot(){},changed(){},
 fetch:async()=>{calls++;return {ok:true,json:async()=>({ev:.5,gamma:.9})}}};
ctx.window=ctx;ctx.recipe=()=>state.photos[state.current.id].recipe;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(__dirname+'/static/app.js','utf8').split('\n').find(l=>l.startsWith('function photoState')),ctx);
assert.equal(ctx.photoState(files[0]).recipe.camera_look_enabled,true);
assert.equal(ctx.photoState(files[1]).recipe.camera_look_enabled,false);
vm.runInContext(fs.readFileSync(__dirname+'/static/camera-look.js','utf8'),ctx);
(async()=>{
 await ctx.loadLinearSource(files[0],1);
 assert.equal(calls,1);assert.equal(ctx.recipe().camera_look.ev,.5);
 await ctx.loadLinearSource(files[0],1);assert.equal(calls,1,'saved fit should not be reanalyzed');
 ctx.recipe().camera_look_enabled=false;await ctx.loadLinearSource(files[0],1);
 assert.equal(ctx.photoState(files[0]).recipe.camera_look_enabled,false,'explicit off must survive');
 assert.equal(calls,1);assert(saves>0);
 console.log('PASS new RAW on, JPG off, automatic analysis, fit persistence and explicit off preserved');
})().catch(e=>{console.error(e);process.exitCode=1});
