'use strict';
const $ = (id) => document.getElementById(id);
const sample = '# Online Python compiler (interpreter)\n# Write and run Python online using this editor.\n\nprint("Hello, world!")\n';
const languages = [
  ['python','Python','/python-programming/online-compiler/'],['r','R','/r/online-compiler/'],
  ['sql','SQL','/sql/online-compiler/'],['html','HTML/CSS','/html/online-compiler/'],
  ['java','Java','/java-programming/online-compiler/'],['kotlin','Kotlin','/kotlin-programming/online-compiler/'],
  ['c','C','/c-programming/online-compiler/'],['cpp','C++','/cpp-programming/online-compiler/'],
  ['csharp','C#','/csharp-programming/online-compiler/'],['javascript','JavaScript','/javascript/online-compiler/'],
  ['typescript','TypeScript','/typescript/online-compiler/'],['golang','Go','/golang/online-compiler/'],
  ['rust','Rust','/rust/online-compiler/'],['scala','Scala','/scala/online-compiler/'],
  ['dart','Dart','/dart/online-compiler/'],['ruby','Ruby','/ruby/online-compiler/'],
  ['php','PHP','/php/online-compiler/'],['swift','Swift','/swift/online-compiler/']
];
const storage = {get(key,fallback){try{return localStorage.getItem('local-python:'+key)??fallback;}catch{return fallback;}},set(key,value){try{localStorage.setItem('local-python:'+key,value);}catch{}}};
let languageInfo={}, currentLanguage='python', changingLanguage=false, saveTimer=null, savePromise=Promise.resolve(), changeVersion=0, languageSwitchVersion=0, previewTimer=null, ready=false;
const codeCache={};
let workspaceDirectory='';
for(const [icon,name,path] of languages){
  const link = document.createElement('a');
  link.className = 'language-link'+(icon==='python'?' selected':'');
  link.title = `Online ${name} Compiler`;
  link.setAttribute('aria-label',link.title);
  link.href = '?lang='+icon;
  link.dataset.language=icon;
  if(icon==='python')link.setAttribute('aria-current','page');
  link.addEventListener('click',e=>{e.preventDefault();switchLanguage(icon);});
  const img=document.createElement('img');img.src='/assets/'+icon+'.svg';img.alt=name;link.append(img);
  document.querySelector('.language-rail').append(link);
}
let activeRun=null, cursor=0, generation=0, outputText='', traceSteps=[], traceIndex=0, traceTimer=null, highlighted=null;
let fontSize=Math.min(24,Math.max(11,Number(storage.get('font','14'))||14));
const defaultOutputFontSize=14;
let outputFontSize=defaultOutputFontSize;
let currentMode='run';
const editor=CodeMirror.fromTextArea($('source'),{
  mode:{name:'python',version:3},lineNumbers:true,indentUnit:4,tabSize:4,indentWithTabs:false,
  matchBrackets:true,autoCloseBrackets:true,styleActiveLine:true,lineWrapping:false,
  extraKeys:{'Ctrl-Enter':()=>execute(),'Cmd-Enter':()=>execute(),'Ctrl-S':()=>saveLocal(true),
    'Cmd-S':()=>saveLocal(true),'Ctrl-/':'toggleComment','Cmd-/':'toggleComment',
    Tab:cm=>cm.somethingSelected()?cm.indentSelection('add'):cm.replaceSelection(' '.repeat(4),'end'),
    'Shift-Tab':cm=>cm.indentSelection('subtract')}
});
$('run').disabled=true;$('visualize').disabled=true;
editor.getInputField().setAttribute('aria-label','Python code editor');
editor.setValue(storage.get('code',sample));editor.clearHistory();
editor.on('change',()=>{
  if(changingLanguage)return;
  storage.set('code:'+currentLanguage,editor.getValue());codeCache[currentLanguage]=editor.getValue();changeVersion++;
  $('save-status').textContent='Saving…';clearTimeout(saveTimer);saveTimer=setTimeout(()=>saveLocal(),500);
  $('share').disabled=!editor.getValue().trim();clearHighlight();
  if(currentLanguage==='html'){clearTimeout(previewTimer);previewTimer=setTimeout(updatePreview,350);}
});
function setFont(size){fontSize=Math.min(24,Math.max(11,size));editor.getWrapperElement().style.fontSize=fontSize+'px';$('font-size').textContent=fontSize;storage.set('font',fontSize);editor.refresh();}
function setOutputFont(size){
  outputFontSize=Math.min(48,Math.max(8,Number(size)||defaultOutputFontSize));
  document.querySelector('.output-pane').style.setProperty('--output-font-size',outputFontSize+'px');
  storage.set('output-font',outputFontSize);
}
setFont(fontSize);
setOutputFont(storage.get('output-font',String(defaultOutputFontSize)));
// Handle zoom before browser shortcuts, and only while focus is in Output.
document.addEventListener('keydown',event=>{
  if(!(event.ctrlKey||event.metaKey)||event.altKey)return;
  if(!document.querySelector('.output-pane').contains(document.activeElement))return;
  let size;
  if(event.key==='='||event.key==='+'||event.code==='NumpadAdd')size=outputFontSize+2;
  else if(event.key==='-'||event.code==='NumpadSubtract')size=outputFontSize-2;
  else if(event.key==='0'||event.code==='Numpad0')size=defaultOutputFontSize;
  else return;
  event.preventDefault();event.stopImmediatePropagation();setOutputFont(size);
},true);
function setTheme(theme){document.documentElement.dataset.theme=theme;storage.set('theme',theme);$('theme-label').textContent=theme==='dark'?'Light mode':'Dark mode';document.querySelector('[data-action="theme"] use').setAttribute('href',theme==='dark'?'#i-sun':'#i-moon');document.querySelector('meta[name="theme-color"]').content=theme==='dark'?'#1f2023':'#f5f5f5';}
setTheme(storage.get('theme','dark'));
function toast(text){$('toast').textContent=text;$('toast').hidden=false;clearTimeout(toast.timeout);toast.timeout=setTimeout(()=>$('toast').hidden=true,3500);}
async function api(path,data){const response=await fetch(path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Local-Compiler':'1'},body:JSON.stringify(data)});const result=await response.json();if(!response.ok)throw new Error(result.error||'Request failed.');return result;}
function showMobile(output){document.body.classList.toggle('output-visible',output);$('code-tab').setAttribute('aria-selected',String(!output));$('mobile-output-tab').setAttribute('aria-selected',String(output));if(!output)editor.refresh();}
function selectPanel(trace){$('html-preview').hidden=true;$('preview-tab').classList.remove('selected');$('trace-panel').hidden=!trace;$('terminal').hidden=trace;$('output-tab').classList.toggle('selected',!trace);$('trace-tab').classList.toggle('selected',trace);if(!trace)clearHighlight();else renderStep(traceIndex);}
function showPreview(){selectPanel(false);$('terminal').hidden=true;$('html-preview').hidden=false;$('output-tab').classList.remove('selected');$('preview-tab').classList.add('selected');}
function updatePreview(){if(currentLanguage!=='html')return;$('html-preview').srcdoc=editor.getValue();showPreview();}
$('preview-tab').onclick=showPreview;
async function saveLocal(notify=false){
  clearTimeout(saveTimer);const language=currentLanguage,code=editor.getValue(),version=changeVersion;
  codeCache[language]=code;
  const operation=savePromise.catch(()=>{}).then(()=>api('/api/files/'+language,{code}));
  savePromise=operation;
  try{const result=await operation;if(language===currentLanguage&&version===changeVersion){$('save-status').textContent='Saved locally';$('save-status').title=result.path;}if(notify)toast('Saved: '+result.path);return true;}
  catch(error){if(language===currentLanguage)$('save-status').textContent='Save failed';toast('Could not save file: '+error.message);return false;}
}
async function switchLanguage(language,{initial=false,code:providedCode}={}){
  if(!languageInfo[language])return;
  if(language===currentLanguage&&!initial){document.querySelector('.language-rail').classList.remove('open');showMobile(false);return;}
  const switchToken=++languageSwitchVersion;
  if(!initial){if(!await saveLocal())return;}
  if(switchToken!==languageSwitchVersion)return;
  if(activeRun){await stopRun();generation++;activeRun=null;setRunning(false);}
  pauseTrace();clearTimeout(previewTimer);
  let code=providedCode;
  if(code===undefined){try{const saved=await api('/api/files/'+language);code=saved.code;}catch(error){code=codeCache[language]??storage.get('code:'+language,languageInfo[language].code);toast('Local file unavailable: '+error.message);}}
  if(switchToken!==languageSwitchVersion)return;
  currentLanguage=language;storage.set('language',language);const config=languageInfo[language];
  changingLanguage=true;editor.setOption('mode',config.mode);editor.setValue(code);editor.clearHistory();changingLanguage=false;
  editor.getInputField().setAttribute('aria-label',config.name+' code editor');
  $('code-tab').textContent=config.filename;$('save-status').textContent='Saved locally';$('save-status').title=workspaceDirectory+'\\'+config.filename;
  $('visualize').hidden=language!=='python';$('trace-tab').hidden=true;$('preview-tab').hidden=language!=='html';
  $('file-input').title='Open '+config.name+' source file';
  $('run').title=language==='html'?'Refresh live preview (Ctrl+Enter)':'Run '+config.name+' (Ctrl+Enter)';
  document.title=config.name+' Online Compiler — Local';
  document.querySelectorAll('.language-link').forEach(link=>{const selected=link.dataset.language===language;link.classList.toggle('selected',selected);if(selected)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');});
  document.querySelector('.language-rail').classList.remove('open');resetOutput();selectPanel(false);showMobile(false);
  if(!location.pathname.startsWith('/s/'))history.replaceState(null,'','/?lang='+language);
  if(language==='html')updatePreview();
  else if(!config.available){appendOutput(config.note+'\n','completion');}
  if(providedCode!==undefined)await saveLocal();
  editor.refresh();
}
$('code-tab').onclick=()=>showMobile(false);
$('mobile-output-tab').onclick=()=>{showMobile(true);selectPanel(false);};
$('nav-button').onclick=()=>document.querySelector('.language-rail').classList.toggle('open');
$('output-tab').onclick=()=>selectPanel(false);
$('trace-tab').onclick=()=>selectPanel(true);
function appendOutput(text,kind='stdout'){
  outputText+=text;const nearBottom=$('terminal').scrollHeight-$('terminal').scrollTop-$('terminal').clientHeight<100;
  const node=document.createElement('span');node.className=kind;node.textContent=text;$('output').append(node);
  if(nearBottom)$('terminal').scrollTop=$('terminal').scrollHeight;
}
function setRunning(running){$('run').classList.toggle('running',running);$('run').querySelector('span').textContent=running?'Stop':'Run';$('run').querySelector('use').setAttribute('href',running?'#i-stop':'#i-play');$('run').title=running?'Stop execution (Ctrl+Enter)':'Run code (Ctrl+Enter)';$('visualize').disabled=running;}
function clearHighlight(){if(highlighted!==null){editor.removeLineClass(highlighted,'background','execution-line');editor.removeLineClass(highlighted,'gutter','execution-gutter');highlighted=null;}}
function resetOutput(){pauseTrace();outputText='';$('output').replaceChildren();$('input-form').hidden=true;$('input-hint').hidden=true;traceSteps=[];traceIndex=0;clearHighlight();$('trace-frames').replaceChildren();$('trace-output').textContent='';$('step-label').textContent='Recording execution…';$('trace-note').textContent='';$('step-range').value=0;$('step-range').max=0;}
async function execute(mode='run'){
  if(!ready){toast('Loading your local files…');return;}
  if(activeRun){await stopRun();return;}
  if(!editor.getValue().trim()){toast('Write some code first.');editor.focus();return;}
  if(!await saveLocal())return;
  if(currentLanguage==='html'){updatePreview();showMobile(true);return;}
  const token=++generation;currentMode=mode;resetOutput();$('trace-tab').hidden=mode!=='trace';selectPanel(mode==='trace');showMobile(true);setRunning(true);
  try{
    const run=await api('/api/runs',{code:editor.getValue(),mode,language:currentLanguage});
    if(token!==generation)return;
    activeRun=run.id;cursor=0;
    while(activeRun===run.id && token===generation){
      const update=await api(`/api/runs/${run.id}?after=${cursor}`);
      if(token!==generation)break;
      cursor=update.next;
      for(const event of update.events){
        if(['stdout','stderr','stdin'].includes(event.type))appendOutput(event.text,event.type);
        if(event.type==='input_request'){
          $('input-form').hidden=false;$('input-hint').hidden=false;$('stdin').value='';
          selectPanel(false);showMobile(true);if(!event.continuous)$('stdin').focus();$('terminal').scrollTop=$('terminal').scrollHeight;
        }
        if(event.type==='trace'){traceSteps.push({...event,output:outputText});$('step-range').max=traceSteps.length-1;if(traceSteps.length===1)renderStep(0);}
        if(event.type==='trace_limit')$('trace-note').textContent=event.text;
        if(event.type==='done'){
          $('input-form').hidden=true;$('input-hint').hidden=true;
          const message=event.reason || (event.exit_code===0?'Code Execution Successful':`Code Exited With Errors (exit code ${event.exit_code})`);
          appendOutput(`\n\n=== ${message} ===\n`,'completion');
          if(mode==='trace'&&traceSteps.length){traceSteps.push({line:traceSteps.at(-1).line,event:'finished',frames:traceSteps.at(-1).frames,output:outputText});$('step-range').max=traceSteps.length-1;selectPanel(true);renderStep(0);}
        }
      }
      if(update.status!=='running'){activeRun=null;break;}
      await new Promise(resolve=>setTimeout(resolve,100));
    }
  }catch(error){appendOutput('\n'+error.message+'\n','stderr');toast(error.message);activeRun=null;}
  finally{if(token===generation){setRunning(false);activeRun=null;}}
}
async function stopRun(){if(!activeRun)return;try{await api(`/api/runs/${activeRun}/stop`,{});}catch(error){toast(error.message);}}
$('run').onclick=()=>execute();$('visualize').onclick=()=>execute('trace');
$('input-form').onsubmit=async e=>{
  e.preventDefault();if(!activeRun)return;
  const value=$('stdin').value;$('input-form').hidden=true;$('input-hint').hidden=true;
  try{await api(`/api/runs/${activeRun}/input`,{value});}catch(error){toast(error.message);$('input-form').hidden=false;$('input-hint').hidden=false;}
};
$('stdin').onkeydown=async e=>{if(e.ctrlKey&&e.key.toLowerCase()==='d'){e.preventDefault();if(activeRun){await api(`/api/runs/${activeRun}/input`,{eof:true});$('input-form').hidden=true;$('input-hint').hidden=true;}}};
$('terminal').addEventListener('click',()=>{
  if(!$('input-form').hidden)$('stdin').focus();
  else $('terminal').focus({preventScroll:true});
});
$('clear-output').onclick=()=>{$('output').replaceChildren();outputText='';toast('Output cleared.');};
function pauseTrace(){clearInterval(traceTimer);traceTimer=null;$('play-trace').querySelector('use').setAttribute('href','#i-play');$('play-trace').setAttribute('aria-label','Play visualization');}
function makeValue(value){
  const wrap=document.createElement('div');const type=document.createElement('span');type.className='value-type';type.textContent=value.type;wrap.append(type);
  if(value.items){
    const seq=document.createElement('div');seq.className='sequence';
    value.items.forEach((item,index)=>{const cell=document.createElement('div');cell.className='sequence-cell';cell.append(makeValue(item));const label=document.createElement('span');label.className='sequence-index';label.textContent=index;cell.append(label);seq.append(cell);});wrap.append(seq);
    if(value.length>value.items.length){const more=document.createElement('span');more.textContent=` … ${value.length} items`;wrap.append(more);}
  }else if(value.entries){
    const table=document.createElement('table');table.className='variables';
    value.entries.forEach(entry=>{const row=table.insertRow();row.insertCell().append(makeValue(entry.key));row.insertCell().append(makeValue(entry.value));});wrap.append(table);
  }else{const text=document.createElement('span');text.className='value-text';text.textContent=value.value;wrap.append(text);}
  return wrap;
}
function renderStep(index){
  clearHighlight();if(!traceSteps.length){$('trace-frames').innerHTML='<div class="empty-state">Recording your Python execution…</div>';return;}
  traceIndex=Math.min(traceSteps.length-1,Math.max(0,index));const step=traceSteps[traceIndex];
  $('step-label').textContent=`Step ${traceIndex+1} of ${traceSteps.length}`;$('step-range').value=traceIndex;
  const descriptions={line:`Next: execute line ${step.line}`,return:`Return from line ${step.line}`,exception:`${step.exception} at line ${step.line}`,finished:'Program finished'};
  $('trace-line').textContent=descriptions[step.event]||`Line ${step.line}`;
  if(step.event!=='finished'){
    highlighted=Math.max(0,step.line-1);editor.addLineClass(highlighted,'background','execution-line');editor.addLineClass(highlighted,'gutter','execution-gutter');editor.scrollIntoView({line:highlighted,ch:0},70);
  }
  $('trace-frames').replaceChildren();
  for(const frame of step.frames){
    const box=document.createElement('div');box.className='stack-frame';const title=document.createElement('div');title.className='frame-name';title.textContent=frame.name==='<module>'?'Global frame':frame.name+'()';box.append(title);
    const entries=Object.entries(frame.variables);
    if(entries.length){const table=document.createElement('table');table.className='variables';for(const [name,value] of entries){const row=table.insertRow();const key=row.insertCell();key.className='variable-name';key.textContent=name;row.insertCell().append(makeValue(value));}box.append(table);}
    else{const empty=document.createElement('div');empty.className='empty-state';empty.textContent='No variables yet.';box.append(empty);}
    $('trace-frames').append(box);
  }
  $('trace-output').textContent=step.output||'No output yet.';
  $('first-step').disabled=$('prev-step').disabled=traceIndex===0;
  $('last-step').disabled=$('next-step').disabled=traceIndex===traceSteps.length-1;
}
$('first-step').onclick=()=>{pauseTrace();renderStep(0);};$('last-step').onclick=()=>{pauseTrace();renderStep(traceSteps.length-1);};
$('prev-step').onclick=()=>{pauseTrace();renderStep(traceIndex-1);};$('next-step').onclick=()=>{pauseTrace();renderStep(traceIndex+1);};
$('step-range').oninput=e=>{pauseTrace();renderStep(Number(e.target.value));};
$('play-trace').onclick=()=>{if(traceTimer){pauseTrace();return;}if(!traceSteps.length)return;if(traceIndex===traceSteps.length-1)renderStep(0);$('play-trace').querySelector('use').setAttribute('href','#i-stop');$('play-trace').setAttribute('aria-label','Pause visualization');traceTimer=setInterval(()=>{if(traceIndex>=traceSteps.length-1)pauseTrace();else renderStep(traceIndex+1);},650);};
async function download(){try{await saveLocal();const response=await fetch('/api/download',{method:'POST',headers:{'Content-Type':'application/json','X-Local-Compiler':'1'},body:JSON.stringify({code:editor.getValue(),language:currentLanguage})});if(!response.ok)throw new Error('Download failed.');const url=URL.createObjectURL(await response.blob());const a=document.createElement('a');a.href=url;a.download=currentLanguage+'-project.zip';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('Project downloaded.');}catch(error){toast(error.message);}}
$('share').onclick=async()=>{try{const result=await api('/api/shares',{code:editor.getValue(),language:currentLanguage});$('share-url').value=location.origin+result.path;$('share-dialog').showModal();}catch(error){toast(error.message);}};
$('copy-link').onclick=async()=>{try{await navigator.clipboard.writeText($('share-url').value);$('copy-link').textContent='Copied!';setTimeout(()=>$('copy-link').textContent='Copy Link',1800);}catch{$('share-url').select();toast('Select and copy the link.');}};
function closeMenu(){$('options-menu').hidden=true;document.querySelectorAll('[aria-label="More options"]').forEach(e=>e.setAttribute('aria-expanded','false'));}
document.querySelectorAll('[aria-label="More options"]').forEach(button=>{button.setAttribute('aria-haspopup','menu');button.setAttribute('aria-expanded','false');button.onclick=e=>{e.stopPropagation();const show=$('options-menu').hidden;closeMenu();$('options-menu').hidden=!show;button.setAttribute('aria-expanded',String(show));};});
document.addEventListener('click',e=>{if(!$('options-menu').contains(e.target))closeMenu();});
document.addEventListener('keydown',e=>{if(e.key==='Escape'){closeMenu();document.querySelector('.language-rail').classList.remove('open');}if((e.ctrlKey||e.metaKey)&&e.key==='Enter'&&!editor.hasFocus()){e.preventDefault();execute();}if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='s'&&!editor.hasFocus()){e.preventDefault();saveLocal(true);}});
$('options-menu').addEventListener('click',async e=>{
  const action=e.target.closest('[data-action]')?.dataset.action;if(!action)return;closeMenu();
  if(action==='theme')setTheme(document.documentElement.dataset.theme==='dark'?'light':'dark');
  if(action==='download')await download();
  if(action==='save')await saveLocal(true);
  if(action==='upload')$('file-input').click();
  if(action==='help')$('help-dialog').showModal();
  if(action==='reset'){editor.setValue(languageInfo[currentLanguage]?.code??sample);editor.focus();showMobile(false);toast('Starter code restored. Ctrl+Z to undo.');}
  if(action==='fullscreen'){try{if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen();}catch{toast('Use F11 for browser full screen.');}}
});
$('font-up').onclick=()=>setFont(fontSize+1);$('font-down').onclick=()=>setFont(fontSize-1);
$('file-input').onchange=async e=>{const file=e.target.files[0];if(!file)return;if(file.size>200000){toast('Choose a code file smaller than 200 KB.');return;}const ext=file.name.split('.').at(-1).toLowerCase();const language=Object.values(languageInfo).find(info=>info.filename.split('.').at(-1).toLowerCase()===ext)?.id;if(language&&language!==currentLanguage)await switchLanguage(language);editor.setValue(await file.text());await saveLocal();showMobile(false);editor.focus();toast('Opened '+file.name);e.target.value='';};
document.addEventListener('fullscreenchange',()=>document.querySelector('[data-action="fullscreen"] span').textContent=document.fullscreenElement?'Exit full screen':'Full screen');
const splitter=$('splitter');let dragging=false;
function setSplit(percent){percent=Math.min(75,Math.max(25,percent));$('panels').style.setProperty('--editor-width',percent+'%');splitter.setAttribute('aria-valuenow',Math.round(percent));storage.set('split',percent);editor.refresh();}
setSplit(Number(storage.get('split','50'))||50);
splitter.onpointerdown=e=>{dragging=true;splitter.setPointerCapture(e.pointerId);document.body.style.userSelect='none';};
splitter.onpointermove=e=>{if(!dragging)return;const rect=$('panels').getBoundingClientRect();setSplit((e.clientX-rect.left)/rect.width*100);};
splitter.onpointerup=()=>{dragging=false;document.body.style.userSelect='';};splitter.onpointercancel=splitter.onpointerup;
splitter.onkeydown=e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();setSplit(Number(splitter.getAttribute('aria-valuenow'))+(e.key==='ArrowLeft'?-2:2));}};
window.addEventListener('resize',()=>editor.refresh());
window.addEventListener('beforeunload',()=>{if(ready)fetch('/api/files/'+currentLanguage,{method:'POST',headers:{'Content-Type':'application/json','X-Local-Compiler':'1'},body:JSON.stringify({code:editor.getValue()}),keepalive:true});if(activeRun)fetch(`/api/runs/${activeRun}/stop`,{method:'POST',headers:{'Content-Type':'application/json','X-Local-Compiler':'1'},body:'{}',keepalive:true});});
async function init(){
  try{const health=await api('/api/health');$('runtime-info').textContent='Python '+health.python+' · Runs locally · No account required';}catch{toast('Cannot connect to the local Python server.');}
  try{const result=await api('/api/languages');workspaceDirectory=result.directory;languageInfo=Object.fromEntries(result.languages.map(info=>[info.id,info]));
    const workspaceLabel=$('help-dialog').querySelector('strong');if(workspaceLabel)workspaceLabel.textContent=workspaceDirectory;
    if(location.pathname.startsWith('/s/')){const saved=await api('/api/shares/'+location.pathname.split('/')[2]);await switchLanguage(saved.language,{initial:true,code:saved.code});toast('Shared code loaded.');}
    else{const language=new URLSearchParams(location.search).get('lang')||storage.get('language','python');await switchLanguage(languageInfo[language]?language:'python',{initial:true});}
  }catch(error){toast('Could not load language files: '+error.message);}
  ready=Object.keys(languageInfo).length>0;$('run').disabled=!ready;$('visualize').disabled=!ready;
  $('share').disabled=!editor.getValue().trim();editor.refresh();
}
init();
