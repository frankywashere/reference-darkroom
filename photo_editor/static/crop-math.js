/* Crop rectangles are normalized against the expanded, rotated image. */
(function(root){
  const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
  function bounds(w,h,r){const a=((+r.rotation||0)+(+r.straighten||0))*Math.PI/180,c=Math.cos(a),s=Math.sin(a);return {w:Math.round(w*Math.abs(c)+h*Math.abs(s)),h:Math.round(h*Math.abs(c)+w*Math.abs(s)),c,s};}
  function fit(ratio,b){const a=ratio*b.h/b.w;return a<1?[a,1]:[1,1/a];}
  function frame(crop,b){const [x,y,w,h]=crop,ratio=w*b.w/(h*b.h),base=fit(ratio,b);return {ratio,zoom:base[0]/w,cx:x+w/2,cy:y+h/2};}
  function rectangle(f,b){const base=fit(f.ratio,b),w=base[0]/Math.max(1,f.zoom),h=base[1]/Math.max(1,f.zoom);return [clamp(f.cx-w/2,0,1-w),clamp(f.cy-h/2,0,1-h),w,h];}
  function autoFill(f,b,sourceW,sourceH){
    f={...f};let crop=rectangle(f,b);f.cx=crop[0]+crop[2]/2;f.cy=crop[1]+crop[3]/2;
    let px=(f.cx-.5)*b.w,py=(f.cy-.5)*b.h;
    let roomX=sourceW/2-1-Math.abs(b.c*px+b.s*py),roomY=sourceH/2-1-Math.abs(-b.s*px+b.c*py);
    if(roomX<=0||roomY<=0){f.cx=f.cy=.5;roomX=sourceW/2-1;roomY=sourceH/2-1;crop=rectangle(f,b);}
    const hw=crop[2]*b.w/2,hh=crop[3]*b.h/2;
    const scale=Math.min(1,roomX/(Math.abs(b.c)*hw+Math.abs(b.s)*hh),roomY/(Math.abs(b.s)*hw+Math.abs(b.c)*hh));
    f.zoom/=Math.max(scale,.001);return f;
  }
  const api={bounds,fit,frame,rectangle,autoFill};root.CropMath=api;if(typeof module!=='undefined')module.exports=api;
})(globalThis);
