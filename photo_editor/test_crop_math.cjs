const assert=require('assert'),M=require('./static/crop-math.js');
let cases=0;
for(const [w,h] of [[6246,4170],[4170,6246],[2000,2000]])for(const rotation of [0,90,180,-90])for(const straighten of [-15,-6,0,8,15])for(const ratio of [1,.8,2/3,16/9])for(const center of [.05,.5,.9]){
 const b=M.bounds(w,h,{rotation,straighten});let f={ratio,zoom:1,cx:center,cy:center};
 f=M.autoFill(f,b,w,h);const c=M.rectangle(f,b);
 assert(Math.abs(c[2]*b.w/(c[3]*b.h)-ratio)<1e-9,'pixel aspect incorrect');
 for(const x of [c[0],c[0]+c[2]])for(const y of [c[1],c[1]+c[3]]){
   const px=(x-.5)*b.w,py=(y-.5)*b.h;
   assert(Math.abs(b.c*px+b.s*py)<=w/2-.9,'empty horizontal edge');
   assert(Math.abs(-b.s*px+b.c*py)<=h/2-.9,'empty vertical edge');
 }
 const again=M.rectangle(M.frame(c,b),b);c.forEach((v,i)=>assert(Math.abs(v-again[i])<1e-9));cases++;
}
console.log('PASS',cases,'crop ratios, orientations, Auto-fill coverage and rectangle round trips');
