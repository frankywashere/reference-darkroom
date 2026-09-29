/* Non-destructive linear-light retouch stack, shared by preview and export.
 * Each stroke samples a frozen pre-stroke image (no self-smearing feedback).
 * Three reusable RGB float targets preserve the layer base and ping-pong strokes.
 */
(() => {
  const proto=UnifiedPhotoRenderer.prototype;
  proto.clearClone=function(){for(const t of this.cloneTargets||[])this.remove(t);this.remove(this.cloneCoverage);this.cloneTargets=[];this.cloneCoverage=null;this.cloneKey=null;this.cloneResult=null;};
  const setSource=proto.setSource,dispose=proto.dispose;
  proto.setSource=function(...args){this.clearClone();return setSource.apply(this,args)};
  proto.dispose=function(){this.clearClone();return dispose.call(this)};
  proto.cloneMask=function(stroke,w,h){
    const g=this.gl,t=this.cloneCoverage;this.use(this.dabProgram);this.output(t);g.clearColor(0,0,0,0);g.clear(g.COLOR_BUFFER_BIT);
    const radius=Math.max(.001,Math.min(1,stroke.size??.05))*Math.min(w,h)/2;
    this.uniform('radius',[radius/w,radius/h]);this.uniform('feather',Math.max(.001,Math.min(1,(stroke.feather??75)/100)));this.uniform('flow',Math.max(0,Math.min(1,(stroke.flow??100)/100)));
    const loc=g.getAttribLocation(this.dabProgram,'center');g.bindBuffer(g.ARRAY_BUFFER,this.pointBuffer);g.bufferData(g.ARRAY_BUFFER,new Float32Array(stroke.points.flat()),g.STREAM_DRAW);g.enableVertexAttribArray(loc);g.vertexAttribPointer(loc,2,g.FLOAT,false,0,0);g.vertexAttribDivisor(loc,1);
    g.enable(g.BLEND);g.blendFunc(g.ONE,g.ONE_MINUS_SRC_ALPHA);g.drawArraysInstanced(g.TRIANGLES,0,6,stroke.points.length);g.disable(g.BLEND);g.vertexAttribDivisor(loc,0);g.disableVertexAttribArray(loc);return t;
  };
  proto.cloneSource=function(layers,side){
    const active=(layers||[]).filter(l=>l.enabled!==false&&(l.opacity??100)>0&&l.strokes?.length);
    if(!active.length)return this.source;
    const scale=Math.min(1,side/Math.max(this.width,this.height)),w=Math.max(1,Math.round(this.width*scale)),h=Math.max(1,Math.round(this.height*scale));
    const key=JSON.stringify([w,h,active]);if(this.cloneKey===key)return this.cloneResult;
    if(this.cloneTargets?.[0]?.w!==w||this.cloneTargets?.[0]?.h!==h){this.clearClone();this.cloneTargets=Array.from({length:3},()=>this.target(w,h));this.cloneCoverage=this.target(w,h,true);}
    let current=this.source;
    for(const layer of active){
      const base=current;
      for(const s of layer.strokes){
        if(!s.points?.length||(!s.erase&&(!Array.isArray(s.offset)||s.offset.length!==2||!s.offset.every(Number.isFinite))))continue;
        const dst=this.cloneTargets.find(t=>t!==base&&t!==current),mask=this.cloneMask(s,w,h);
        const source=s.erase?base:s.sample==='original'?this.source:current;
        this.pass(11,current,dst,{direction:s.erase?[0,0]:s.offset,amount:Math.max(0,Math.min(1,(s.opacity??100)/100))},source,mask);current=dst;
      }
      if(current!==base&&(layer.opacity??100)<100){const dst=this.cloneTargets.find(t=>t!==base&&t!==current);this.pass(12,base,dst,{amount:Math.max(0,Math.min(1,layer.opacity/100))},current);current=dst;}
    }
    this.cloneKey=key;this.cloneResult=current;return current;
  };
})();
