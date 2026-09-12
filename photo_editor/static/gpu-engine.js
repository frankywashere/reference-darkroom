/* Shared preview/export renderer. All editing passes use RGBA32F targets.
 * Coordinate convention: row zero is the top of the photograph in textures;
 * only presentation to the browser framebuffer flips Y. No readback while editing.
 */
class UnifiedPhotoRenderer {
  constructor() {
    this.canvas=document.createElement('canvas');
    const g=this.gl=this.canvas.getContext('webgl2',{alpha:false,antialias:false,preserveDrawingBuffer:true});
    if(!g || !g.getExtension('EXT_color_buffer_float') || !g.getExtension('OES_texture_float_linear'))
      throw new Error('This GPU does not support the float32 editing pipeline');
    this.limit=Math.min(g.getParameter(g.MAX_TEXTURE_SIZE),g.getParameter(g.MAX_RENDERBUFFER_SIZE));
    this.targets=[];this.maskCache=new Map();this.programs=[];
    const vertex=`#version 300 es
      in vec2 p;out vec2 uv;uniform int present;
      void main(){uv=p*.5+.5;if(present==1)uv.y=1.-uv.y;gl_Position=vec4(p,0,1);}`;
    this.program=this.compile(vertex,`#version 300 es
      precision highp float;precision highp int;
      in vec2 uv;out vec4 outColor;
      uniform sampler2D image,aux,maskTex;
      uniform int op,monochrome,grade,flipH,flipV,clipMode,invert;
      uniform vec2 sourceSize,outputSize,direction;
      uniform vec4 crop;
      uniform vec3 bwWeights;
      uniform float exposure,contrast,highlights,shadows,whites,blacks,temperature,tint,saturation,vibrance;
      uniform float cameraEV,cameraGamma;
      uniform float angle,curve[5],sigma,amount,localExposure,localSaturation,localTemperature,grain,vignette,referenceScale;
      float lum(vec3 c){return dot(c,vec3(.2126,.7152,.0722));}
      float srgb(float x){return x<=.0031308?12.92*x:1.055*pow(max(x,0.),1./2.4)-.055;}
      float lin(float x){return x<=.04045?x/12.92:pow((x+.055)/1.055,2.4);}
      vec3 temp(vec3 c,float t,float v){return clamp(c*vec3(1.+t*.0022+v*.0008,1.-abs(v)*.0004,1.-t*.0022+v*.0006),0.,32.);}
      vec3 develop(vec3 c){
        if(cameraEV!=0.||cameraGamma!=1.){float cy=max(lum(c),0.);c*= (.18*pow(cy/.18,cameraGamma)*exp2(cameraEV))/max(cy,1e-12);}
        c=max(c*exp2(exposure),0.);c=.18*pow(c/.18,vec3(max(.15,1.+contrast*.008)));
        float y=lum(c),s=clamp(shadows*.01,-1.,1.),h=clamp(highlights*.01,-1.,1.);
        float x=clamp(y/.28,0.,1.),k=exp2(abs(s)*5.)-1.;
        float low=s>=0.?x*(1.+k*(1.-x))/(1.+k*x*(1.-x)):x/(1.+k*(1.-x)*(1.-x));
        float mapped=y<.28?.28*low:y,e=max(mapped-.18,0.);
        float shoulder=h<0.?.18+log(1.+(-h)*8.*e)/((-h)*8.):.18+e*exp2(h*2.);
        if(mapped>.18)mapped=shoulder;c*=mapped/max(y,1e-12);
        c=clamp(c*exp2(clamp((.075-mapped)/.075,0.,1.)*blacks*.012+clamp((mapped-.55)/.45,0.,1.)*whites*.012),0.,32.);
        c=temp(c,temperature,tint);vec3 gray=vec3(lum(c));c=gray+(c-gray)*(1.+saturation*.01);
        float hi=max(max(c.r,c.g),c.b),lo=min(min(c.r,c.g),c.b);
        c=clamp(gray+(c-gray)*(1.+vibrance*.01*(1.-(hi-lo)/max(hi,.00001))),0.,32.);
        y=lum(c);
        if(grade==1){float s=clamp((.58-y)/.58,0.,1.),h=clamp((y-.38)/.62,0.,1.);c+=vec3(h*.075-s*.035,s*.018+h*.015,s*.065-h*.080);}
        if(grade==2){float s=clamp((.60-y)/.60,0.,1.),h=clamp((y-.35)/.65,0.,1.);c=(c+vec3(s*.035+h*.028,h*.012,-s*.020-h*.038))*.94+vec3(.035,.026,.014);}
        return clamp(c,0.,32.);
      }
      float curveAt(float x){float z=clamp(x,0.,1.)*4.;int i=min(3,int(z));return mix(curve[i],curve[i+1],z-float(i));}
      // CIE Lab, D65. Identical shader is used at every output resolution.
      float labf(float x){return x>.0088564517?pow(x,1./3.):7.787037*x+16./116.;}
      float labinv(float x){return x>.20689655?x*x*x:(x-16./116.)/7.787037;}
      vec3 toLab(vec3 c){c=vec3(lin(c.r),lin(c.g),lin(c.b));
        vec3 v=vec3(dot(c,vec3(.4124564,.3575761,.1804375))/.95047,dot(c,vec3(.2126729,.7151522,.072175)),dot(c,vec3(.0193339,.119192,.9503041))/1.08883);
        v=vec3(labf(v.x),labf(v.y),labf(v.z));return vec3(116.*v.y-16.,500.*(v.x-v.y),200.*(v.y-v.z));}
      vec3 fromLab(vec3 c){float y=(c.x+16.)/116.;vec3 v=vec3(.95047*labinv(y+c.y/500.),labinv(y),1.08883*labinv(y-c.z/200.));
        vec3 r=vec3(dot(v,vec3(3.2404542,-1.5371385,-.4985314)),dot(v,vec3(-.969266,1.8760108,.041556)),dot(v,vec3(.0556434,-.2040259,1.0572252)));
        return clamp(vec3(srgb(r.x),srgb(r.y),srgb(r.z)),0.,1.);}
      uint hash(uint x){x^=x>>16;x*=0x7feb352du;x^=x>>15;x*=0x846ca68bu;return x^(x>>16);}
      float noise(vec2 p){uvec2 q=uvec2(p);uint h=hash(q.x+hash(q.y+1u));float a=(float(h&65535u)+1.)/65537.;float b=(float(h>>16)+.5)/65536.;return sqrt(-2.*log(a))*cos(6.2831853*b);}
      void main(){vec3 c=texture(image,uv).rgb;
        if(op==0){vec2 p=(uv-.5)*outputSize;float a=radians(angle),cs=cos(a),sn=sin(a);
          vec2 q=vec2(cs*p.x+sn*p.y,-sn*p.x+cs*p.y)/sourceSize+.5;
          if(flipH==1)q.x=1.-q.x;if(flipV==1)q.y=1.-q.y;
          c=any(lessThan(q,vec2(0)))||any(greaterThan(q,vec2(1)))?vec3(.006):texture(image,q).rgb;c=develop(c);
        }else if(op==1){float w=texture(maskTex,uv).r;if(invert==1)w=1.-w;w*=amount;
          c*=exp2(localExposure*w);vec3 gray=vec3(lum(c));c=mix(c,gray+(c-gray)*(1.+localSaturation*.01),w);
          c=clamp(mix(c,temp(c,localTemperature,0.),w),0.,32.);
        }else if(op==2){if(monochrome==1)c=vec3(dot(c,bwWeights));c=vec3(curveAt(srgb(c.r)),curveAt(srgb(c.g)),curveAt(srgb(c.b)));
        }else if(op==3){c=toLab(c);
        }else if(op==4){c=texture(image,uv).rgb;float sum=1.;int radius=min(256,int(ceil(sigma*3.)));
          // Combine adjacent Gaussian taps using hardware linear interpolation.
          // This is the same weighted sum, with roughly half the texture reads.
          for(int i=1;i<=radius;i+=2){float a=exp(-.5*float(i*i)/(sigma*sigma)),b=i+1<=radius?exp(-.5*float((i+1)*(i+1))/(sigma*sigma)):0.;float w=a+b;vec2 d=direction*(float(i)+b/w);c+=(texture(image,uv+d).rgb+texture(image,uv-d).rgb)*w;sum+=2.*w;}c/=sum;
        }else if(op==5){c=fromLab(vec3(texture(aux,uv).r,c.gb));
        }else if(op==6){c=clamp(c+(c-texture(aux,uv).rgb)*amount,0.,1.);
        }else if(op==7){float edge=pow(clamp((length((uv-.5)*2.)-.25)/1.1,0.,1.),1.6);c*=1.-edge*vignette*.0065;
          float envelope=sqrt(clamp(1.-abs(lum(c)-.5),.25,1.));c+=noise(floor(uv*outputSize/referenceScale))*grain*.00045*envelope;c=clamp(c,0.,1.);
        }else if(op==8){c=texture(image,crop.xy+uv*crop.zw).rgb;
        }else if(op==9){float hi=max(max(c.r,c.g),c.b),lo=lum(c);c=vec3(hi>=1.?1.:0.,lo<=.0005?1.:0.,hi>=1.&&min(min(c.r,c.g),c.b)<1.?1.:0.);
        }else if(op==10){vec3 flags=texture(aux,uv).rgb;if((clipMode==1||clipMode==3)&&flags.r>.5)c=mix(c,vec3(1,0,0),.82);if((clipMode==2||clipMode==3)&&flags.g>.5)c=mix(c,vec3(0,.25,1),.88);}
        outColor=vec4(c,1);
      }`);
    this.maskProgram=this.compile(vertex,`#version 300 es
      precision highp float;in vec2 uv;out vec4 outColor;
      uniform int kind;uniform vec2 center,radii,size;uniform float feather,angle,width;
      void main(){float v;if(kind==1){float d=dot(uv-center,vec2(cos(angle),sin(angle)));float t=clamp((width*.5-d)/width,0.,1.);v=t*t*(3.-2.*t);}
      else{float d=length((uv-center)/radii);v=1.-smoothstep(max(0.,1.-feather),1.+feather,d);}outColor=vec4(v,0,0,1);}`);
    this.dabProgram=this.compile(`#version 300 es
      in vec2 p;in vec2 center;out vec2 delta;uniform vec2 radius;
      void main(){delta=p;gl_Position=vec4((center+p*radius)*2.-1.,0,1);}`,`#version 300 es
      precision highp float;in vec2 delta;out vec4 outColor;uniform float feather,flow;
      void main(){float a=(1.-clamp((length(delta)-(1.-feather))/feather,0.,1.))*flow;outColor=vec4(a,0,0,a);}`);
    this.composeProgram=this.compile(vertex,`#version 300 es
      precision highp float;in vec2 uv;out vec4 outColor;uniform sampler2D image,aux;uniform float opacity;uniform int erase;
      void main(){float a=texture(image,uv).r,b=texture(aux,uv).r*opacity;outColor=vec4(erase==1?a*(1.-b):a+(1.-a)*b,0,0,1);}`);
    this.quad=g.createBuffer();g.bindBuffer(g.ARRAY_BUFFER,this.quad);g.bufferData(g.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,-1,1,1,-1,1,1]),g.STATIC_DRAW);
    this.pointBuffer=g.createBuffer();
  }
  compile(v,f){const g=this.gl,p=g.createProgram();for(const [type,src] of [[g.VERTEX_SHADER,v],[g.FRAGMENT_SHADER,f]]){const s=g.createShader(type);g.shaderSource(s,src);g.compileShader(s);if(!g.getShaderParameter(s,g.COMPILE_STATUS))throw Error(g.getShaderInfoLog(s));g.attachShader(p,s);g.deleteShader(s);}g.linkProgram(p);if(!g.getProgramParameter(p,g.LINK_STATUS))throw Error(g.getProgramInfoLog(p));this.programs.push(p);return p;}
  use(p){const g=this.gl;g.useProgram(p);this.active=p;g.bindBuffer(g.ARRAY_BUFFER,this.quad);const a=g.getAttribLocation(p,'p');g.enableVertexAttribArray(a);g.vertexAttribPointer(a,2,g.FLOAT,false,0,0);g.vertexAttribDivisor(a,0);}
  uniform(k,v,integer=false){const g=this.gl,l=g.getUniformLocation(this.active,k);if(l===null)return;if(Array.isArray(v)){g[`uniform${v.length}fv`](l,v);}else if(integer)g.uniform1i(l,v);else g.uniform1f(l,v);}
  bind(name,t,unit){const g=this.gl;g.activeTexture(g.TEXTURE0+unit);g.bindTexture(g.TEXTURE_2D,t?.texture||t);this.uniform(name,unit,true);}
  target(w,h,half=false){const g=this.gl,t={w,h,texture:g.createTexture(),fbo:g.createFramebuffer()};g.bindTexture(g.TEXTURE_2D,t.texture);g.texParameteri(g.TEXTURE_2D,g.TEXTURE_MIN_FILTER,g.LINEAR);g.texParameteri(g.TEXTURE_2D,g.TEXTURE_MAG_FILTER,g.LINEAR);g.texParameteri(g.TEXTURE_2D,g.TEXTURE_WRAP_S,g.CLAMP_TO_EDGE);g.texParameteri(g.TEXTURE_2D,g.TEXTURE_WRAP_T,g.CLAMP_TO_EDGE);g.texImage2D(g.TEXTURE_2D,0,half?g.RGBA16F:g.RGBA32F,w,h,0,g.RGBA,g.FLOAT,null);g.bindFramebuffer(g.FRAMEBUFFER,t.fbo);g.framebufferTexture2D(g.FRAMEBUFFER,g.COLOR_ATTACHMENT0,g.TEXTURE_2D,t.texture,0);if(g.checkFramebufferStatus(g.FRAMEBUFFER)!==g.FRAMEBUFFER_COMPLETE)throw Error('Float framebuffer unavailable');return t;}
  remove(t){if(t){this.gl.deleteTexture(t.texture);this.gl.deleteFramebuffer(t.fbo);}}
  setSource(buffer,w,h){const g=this.gl;if(w>this.limit||h>this.limit)throw Error('Photo exceeds GPU texture size');if(this.source)g.deleteTexture(this.source);this.source=g.createTexture();g.bindTexture(g.TEXTURE_2D,this.source);g.texParameteri(g.TEXTURE_2D,g.TEXTURE_MIN_FILTER,g.LINEAR_MIPMAP_LINEAR);g.texParameteri(g.TEXTURE_2D,g.TEXTURE_MAG_FILTER,g.LINEAR);g.texParameteri(g.TEXTURE_2D,g.TEXTURE_WRAP_S,g.CLAMP_TO_EDGE);g.texParameteri(g.TEXTURE_2D,g.TEXTURE_WRAP_T,g.CLAMP_TO_EDGE);g.pixelStorei(g.UNPACK_FLIP_Y_WEBGL,false);g.texImage2D(g.TEXTURE_2D,0,g.RGBA32F,w,h,0,g.RGBA,g.FLOAT,new Float32Array(buffer));g.generateMipmap(g.TEXTURE_2D);this.width=w;this.height=h;this.clearMasks();if(g.getError()!==g.NO_ERROR)throw Error('GPU source allocation failed');}
  clearMasks(){for(const t of this.maskCache.values())this.remove(t);this.maskCache.clear();}
  output(t){const g=this.gl;g.bindFramebuffer(g.FRAMEBUFFER,t?.fbo||null);g.viewport(0,0,t?.w||this.canvas.width,t?.h||this.canvas.height);}
  pass(op,src,dst,settings={},aux=null,mask=null){this.use(this.program);this.output(dst);this.bind('image',src,0);this.bind('aux',aux||src,1);this.bind('maskTex',mask||src,2);this.uniform('op',op,true);this.uniform('present',dst?0:1,true);for(const [k,v] of Object.entries(settings))this.uniform(k,v,['monochrome','grade','flipH','flipV','clipMode','invert'].includes(k));this.gl.drawArrays(this.gl.TRIANGLES,0,6);}
  mask(m,w,h){const key=JSON.stringify([w,h,m.type,m.strokes,m.x,m.y,m.width,m.height,m.size,m.angle,m.feather]);if(this.maskCache.has(key))return this.maskCache.get(key);
    const g=this.gl;let a=this.target(w,h,true);
    if(m.type!=='brush'){this.use(this.maskProgram);this.output(a);this.uniform('present',0,true);this.uniform('kind',m.type==='linear'?1:0,true);this.uniform('center',[m.x??.5,m.y??.5]);this.uniform('radii',[Math.max(.01,m.width??.25),Math.max(.01,m.height??.25)]);this.uniform('feather',Math.max(.02,(m.feather??60)/100));this.uniform('angle',(m.angle||0)*Math.PI/180);this.uniform('width',Math.max(.02,m.size??.35));g.drawArrays(g.TRIANGLES,0,6);
    }else{let b=this.target(w,h,true),coverage=this.target(w,h,true);this.output(a);g.clearColor(0,0,0,0);g.clear(g.COLOR_BUFFER_BIT);
      for(const s of m.strokes||[]){this.use(this.dabProgram);this.output(coverage);g.clear(g.COLOR_BUFFER_BIT);const radius=Math.max(.001,Math.min(1,s.size??.1))*Math.min(w,h)/2;this.uniform('radius',[radius/w,radius/h]);this.uniform('feather',Math.max(.001,(s.feather??60)/100));this.uniform('flow',Math.max(0,Math.min(1,(s.flow??50)/100)));
        const loc=g.getAttribLocation(this.dabProgram,'center');g.bindBuffer(g.ARRAY_BUFFER,this.pointBuffer);g.bufferData(g.ARRAY_BUFFER,new Float32Array((s.points||[]).flat()),g.STREAM_DRAW);g.enableVertexAttribArray(loc);g.vertexAttribPointer(loc,2,g.FLOAT,false,0,0);g.vertexAttribDivisor(loc,1);g.enable(g.BLEND);g.blendFunc(g.ONE,g.ONE_MINUS_SRC_ALPHA);g.drawArraysInstanced(g.TRIANGLES,0,6,(s.points||[]).length);g.disable(g.BLEND);g.vertexAttribDivisor(loc,0);g.disableVertexAttribArray(loc);
        this.use(this.composeProgram);this.output(b);this.bind('image',a,0);this.bind('aux',coverage,1);this.uniform('present',0,true);this.uniform('opacity',Math.max(0,Math.min(1,(s.opacity??100)/100)));this.uniform('erase',s.erase?1:0,true);g.drawArrays(g.TRIANGLES,0,6);[a,b]=[b,a];
      }this.remove(b);this.remove(coverage);
    }
    // Bound historical stroke masks: current recipes get rebuilt only on paint changes.
    this.maskCache.set(key,a);
    while(this.maskCache.size>1&&(this.maskCache.size>12||[...this.maskCache.values()].reduce((n,t)=>n+t.w*t.h*8,0)>128*1024*1024)){const first=this.maskCache.keys().next().value;this.remove(this.maskCache.get(first));this.maskCache.delete(first);}return a;
  }
  render(r,clipMode=0,options={}){
    const g=this.gl;if(!this.source)throw Error('No source loaded');const angle=(+r.rotation||0)+(+r.straighten||0),a=angle*Math.PI/180;
    const nativeW=Math.max(1,Math.round(this.width*Math.abs(Math.cos(a))+this.height*Math.abs(Math.sin(a)))),nativeH=Math.max(1,Math.round(this.height*Math.abs(Math.cos(a))+this.width*Math.abs(Math.sin(a))));
    const side=options.full?Math.max(nativeW,nativeH):(options.side||Math.min(2560,Math.max(1200,Math.max($('#viewport')?.clientWidth||900,$('#viewport')?.clientHeight||900)*devicePixelRatio)));
    const scale=Math.min(1,side/Math.max(nativeW,nativeH)),w=Math.max(1,Math.round(nativeW*scale)),h=Math.max(1,Math.round(nativeH*scale));
    if(w>this.limit||h>this.limit)throw Error('Rotated photo exceeds GPU limit; reduce rotation or export size');
    if(this.targets[0]?.w!==w||this.targets[0]?.h!==h){this.targets.forEach(t=>this.remove(t));this.targets=Array.from({length:5},()=>this.target(w,h));this.clearMasks();}
    let [cur,next,temp,blur,flags]=this.targets;const swap=()=>{[cur,next]=[next,cur]};
    this.use(this.program);for(const k of ['exposure','contrast','highlights','shadows','whites','blacks','temperature','tint','saturation','vibrance'])this.uniform(k,+r[k]||0);
    const cp=r.camera_look_enabled?r.camera_look:null;this.uniform('cameraEV',cp?Math.max(-3,Math.min(3,+cp.ev||0)):0);this.uniform('cameraGamma',cp?Math.max(.5,Math.min(1.8,+cp.gamma||1)):1);
    this.pass(0,this.source,cur,{sourceSize:[this.width,this.height],outputSize:[nativeW,nativeH],angle,flipH:r.flip_h?1:0,flipV:r.flip_v?1:0,grade:r.grade==='cinema'?1:r.grade==='faded'?2:0});
    for(const m of r.masks||[]){if(m.enabled===false)continue;const mask=this.mask(m,w,h);this.pass(1,cur,next,{invert:m.invert?1:0,amount:Math.max(0,Math.min(1,(m.amount??100)/100)),localExposure:+m.exposure||0,localSaturation:+m.saturation||0,localTemperature:+m.temperature||0},null,mask);swap();}
    this.pass(9,cur,flags);
    const weights=[r.bw_red??45,r.bw_green??40,r.bw_blue??15],sum=Math.max(1,weights.reduce((a,b)=>a+b,0));let prev=0;const points=(r.curve||[0,25,50,75,100]).map(v=>prev=Math.max(prev,Math.min(1,v/100)));
    this.use(this.program);g.uniform1fv(g.getUniformLocation(this.program,'curve[0]'),new Float32Array(points));this.pass(2,cur,next,{monochrome:r.bw?1:0,bwWeights:weights.map(v=>v/sum)});swap();
    // Radii are in reference-image units, so fit previews and full exports use
    // the same spatial scale rather than applying different preview algorithms.
    const ref=Math.max(w,h)/1800;
    const gaussian=(src,sigma)=>{sigma=Math.max(.2,Math.min(85,sigma));this.pass(4,src,temp,{sigma,direction:[1/w,0]});this.pass(4,temp,blur,{sigma,direction:[0,1/h]});};
    if(r.denoise>0){this.pass(3,cur,next);swap();gaussian(cur,(.4+r.denoise*.022)*ref);this.pass(5,blur,next,{},cur);swap();}
    const detail=(r.clarity||0)*.007+(r.dehaze||0)*.011;if(detail){gaussian(cur,16*ref);this.pass(6,cur,next,{amount:detail},blur);swap();}
    if(r.sharpen>0){gaussian(cur,.8*ref);this.pass(6,cur,next,{amount:r.sharpen*.01},blur);swap();}
    this.pass(7,cur,next,{grain:Math.max(0,r.grain||0),vignette:Math.max(0,r.vignette||0),outputSize:[w,h],referenceScale:ref});swap();
    if(clipMode){this.pass(10,cur,next,{clipMode},flags);swap();}
    const crop=options.crop?(r.crop||[0,0,1,1]):[0,0,1,1];const cw=Math.max(1,Math.round(w*crop[2])),ch=Math.max(1,Math.round(h*crop[3]));
    if(this.canvas.width!==cw)this.canvas.width=cw;if(this.canvas.height!==ch)this.canvas.height=ch;
    this.pass(8,cur,null,{crop});this.last={cur,flags,w,h,crop,cw,ch};
    if(g.getError()!==g.NO_ERROR)throw Error('GPU render failed (memory or graphics context)');return this.canvas;
  }
  pixels(){const g=this.gl,{cur,crop,cw,ch}=this.last;const t=this.target(cw,ch);try{this.pass(8,cur,t,{crop});const values=new Float32Array(cw*ch*4);g.readPixels(0,0,cw,ch,g.RGBA,g.FLOAT,values);if(g.getError()!==g.NO_ERROR)throw Error('GPU readback failed');const bytes=new Uint8Array(values.length);for(let i=0;i<values.length;i++)bytes[i]=Math.round(Math.max(0,Math.min(1,values[i]))*255);return {bytes,width:cw,height:ch};}finally{this.remove(t);}}
  clippingStats(){const g=this.gl,t=this.target(192,128);try{this.pass(8,this.last.flags,t,{crop:[0,0,1,1]});const values=new Float32Array(192*128*4);g.readPixels(0,0,192,128,g.RGBA,g.FLOAT,values);const sums=[0,0,0];for(let i=0;i<values.length;i+=4)for(let c=0;c<3;c++)sums[c]+=values[i+c];return sums.map(v=>v/(192*128)*100);}finally{this.remove(t);}}
  dispose(){this.clearMasks();this.targets.forEach(t=>this.remove(t));const g=this.gl;g.deleteTexture(this.source);g.deleteBuffer(this.quad);g.deleteBuffer(this.pointBuffer);this.programs.forEach(p=>g.deleteProgram(p));g.getExtension('WEBGL_lose_context')?.loseContext();}
}
if(typeof module!=='undefined')module.exports={UnifiedPhotoRenderer};
