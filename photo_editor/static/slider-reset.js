/* Individual resets reuse each slider's normal edit/undo/render path. */
(() => {
  const entries=new Map();
  const maskDefaults={exposure:0,saturation:0,temperature:0,feather:60,width:.25,height:.25,angle:0,amount:100,size:.35};
  function defaultValue(input){
    const key=input.dataset.key;
    if(key?.startsWith('mask.'))return maskDefaults[key.slice(5)]??0;
    if(key&&state.config)return valueAt(state.config.default_recipe,key)??0;
    return Number(input.defaultValue||0);
  }
  function sync(){
    for(const [input,button] of entries){
      const value=defaultValue(input),label=input.getAttribute('aria-label')||input.closest('.slider')?.querySelector('label,span')?.textContent||({split:'Comparison split',sweepEV:'Exposure offset',exportQuality:'JPEG quality'}[input.id])||'Slider';
      button.title=`Reset ${label} to ${value}`;button.setAttribute('aria-label',button.title);
      const disabled=input.disabled||Math.abs(Number(input.value)-value)<1e-8;
      if(button.disabled!==disabled)button.disabled=disabled;
    }
  }
  function install(){
    document.querySelectorAll('input[type="range"]').forEach(input=>{
      if(entries.has(input))return;
      const button=document.createElement('button');button.type='button';button.className='sliderReset';
      button.innerHTML='<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 6a5 5 0 1 1-.1 4M3 2v4h4"/></svg>';
      const output=input.nextElementSibling?.tagName==='OUTPUT'?input.nextElementSibling:null;
      const row=input.closest('.slider');
      if(row){row.classList.add('hasSliderReset');(output||input).after(button);}
      else{
        const group=document.createElement('span');group.className='rangeResetGroup';input.before(group);group.append(input);if(output)group.append(output);group.append(button);
      }
      entries.set(input,button);
      button.addEventListener('click',e=>{
        e.preventDefault();e.stopPropagation();if(input.disabled)return;
        if(input.dataset.key){if(!state.current)return;snapshot();state.live=null;}
        input.value=defaultValue(input);
        input.dispatchEvent(new Event('input',{bubbles:true}));
        input.dispatchEvent(new Event('change',{bubbles:true}));sync();
      });
      input.addEventListener('input',sync);input.addEventListener('change',sync);
    });sync();
  }
  const original=refreshControls;refreshControls=function(){original();install()};
  new MutationObserver(install).observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['disabled']});
  install();
})();
