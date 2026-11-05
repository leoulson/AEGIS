(()=>{
 'use strict';
 const token=globalThis.AEGIS_SESSION;
 async function api(path,body){
  const response=await fetch('/api/'+path,{method:body===undefined?'GET':'POST',headers:{'X-Aegis-Token':token,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
  const data=await response.json();if(!response.ok)throw Error(data.error||'Falha na comunicação local.');return data;
 }
 function apply(p){
  const root=document.querySelector('#aegis-library');
  if(!root)return;
  root.style.setProperty('--text-scale',p.text_size/100);
  document.documentElement.dataset.textSize=String(p.text_size);
  document.documentElement.dataset.contrast=String(p.high_contrast);
  document.documentElement.dataset.motion=String(p.reduced_motion);
 }
 function trap(dialog){
  if(dialog.dataset.focusTrap)return;dialog.dataset.focusTrap='true';
  dialog.addEventListener('keydown',event=>{
   if(event.key!=='Tab')return;
   const items=[...dialog.querySelectorAll('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href],[tabindex="0"]')].filter(e=>!e.hidden);
   const first=items[0],last=items[items.length-1];
   if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
   else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
  });
 }
 function confirm(message,action,trigger=document.activeElement){
  const dialog=document.createElement('dialog');dialog.className='device-dialog';dialog.setAttribute('aria-label','Confirmar operação');
  const p=document.createElement('p');p.textContent=message;
  const yes=document.createElement('button'),no=document.createElement('button');yes.textContent='Confirmar';no.textContent='Cancelar';
  dialog.append(p,yes,no);document.querySelector('#aegis-library').append(dialog);
  let accepted=false;yes.onclick=()=>{accepted=true;dialog.close();};no.onclick=()=>dialog.close();
  dialog.addEventListener('close',()=>{dialog.remove();if(trigger?.isConnected)trigger.focus();if(accepted)action();},{once:true});
  trap(dialog);dialog.showModal();no.focus();
 }
 async function save(path,name,type){
  // Request the native destination picker while still inside the user's click gesture.
  let handle=null;
  if(globalThis.showSaveFilePicker)handle=await showSaveFilePicker({suggestedName:name});
  const response=await fetch('/api/'+path,{headers:{'X-Aegis-Token':token}});
  if(!response.ok)throw Error((await response.json()).error||'Falha ao exportar.');
  if(handle){const output=await handle.createWritable();try{await response.body.pipeTo(output);}catch(e){await output.abort().catch(()=>{});throw e;}}
  else{const blob=await response.blob(),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
 }
 const unavailable='Não disponível neste ambiente';
 function bytes(n){return n===null||n===undefined?unavailable:(n/1048576).toLocaleString('pt-BR',{maximumFractionDigits:1})+' MiB';}
 function diagnostic(container,d){
  container.replaceChildren();if(!d){container.textContent='Selecione Atualizar diagnóstico para consultar fontes reais do sistema.';return;}
  const dl=document.createElement('dl');
  const summaryNames={intact:'íntegros',damaged:'com problemas',unverifiable:'sem manifesto verificável',incomplete:'incompletos',interrupted:'interrompido'};
  const summary=d.last_verification?Object.entries(d.last_verification.summary).map(([k,v])=>(summaryNames[k]||k)+': '+v).join('; '):'';
  const values=[['Modelo',d.model||unavailable],['Arquitetura',d.architecture||unavailable],['AEGIS',d.aegis_version||unavailable],['Sistema',d.os||unavailable],['Armazenamento total',bytes(d.storage?.total)],['Armazenamento usado',bytes(d.storage?.used)],['Armazenamento disponível',bytes(d.storage?.available)],['RAM total',bytes(d.memory.total)],['RAM disponível',bytes(d.memory.available)],['Temperatura CPU',d.cpu_temperature_c===null?unavailable:d.cpu_temperature_c+' °C'],['Pacotes do acervo',d.packages??unavailable],['Documentos/arquivos do acervo',d.documents??unavailable],['Última integridade',d.last_verification?d.last_verification.at+' · '+(d.last_verification.complete?'concluída':'incompleta')+' · '+summary:'Ainda não verificada'],['Leituras atualizadas em',d.updated_at]];
  for(const [k,v]of values){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=k;dd.textContent=v;dl.append(dt,dd);}container.append(dl);
  const title=document.createElement('h2');title.textContent='Componentes essenciais (observações básicas)';container.append(title);
  const names={python:'Python (lançador)',sqlite:'SQLite (banco)',openssl:'Verificação de assinaturas (OpenSSL)',browser:'Motor da interface (Chromium/Chrome)',interface_file_present:'Arquivo inicial da interface presente',restore_pending:'Restauração de dados pendente'};
  const list=document.createElement('ul');for(const[k,v]of Object.entries(d.components)){const li=document.createElement('li');li.textContent=(names[k]||k)+': '+(typeof v==='boolean'?(v?'sim':'não'):v);list.append(li);}container.append(list);
 }
 globalThis.AegisDeviceUI={api,apply,confirm,save,diagnostic,bytes,trap};
})();
