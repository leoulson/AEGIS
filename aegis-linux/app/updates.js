(()=>{
 'use strict';
 const root=document.querySelector('#aegis-library'),main=root.querySelector('main'),nav=root.querySelector('nav');
 const other=[...main.children],open=document.createElement('button');
 open.id='open-settings';open.type='button';open.textContent='⚙ Configurações';open.setAttribute('aria-pressed','false');nav.insertBefore(open,nav.querySelector('.nav-label'));
 const panel=document.createElement('section');panel.id='updates';panel.hidden=true;
 panel.innerHTML=`<div class="eyebrow">CONFIGURAÇÕES</div><h1 tabindex="-1">Atualizações</h1>
 <p class="muted">Atualize somente o aplicativo AEGIS. Linux, acervo e modelos de IA permanecem separados.</p>
 <div class="update-card"><dl><dt>Versão instalada</dt><dd id="update-installed">Consultando…</dd><dt>Versão disponível</dt><dd id="update-available">Ainda não consultada</dd><dt>Versão anterior</dt><dd id="update-previous">—</dd></dl>
 <p id="update-trust" class="update-notice"></p><p id="update-pending"></p><p id="update-recovery" role="alert"></p></div>
 <div class="update-actions"><button id="update-check" type="button">Verificar atualizações</button><button id="update-import" type="button">Importar pacote de atualização</button><input id="update-file" type="file" accept=".aegis-update" hidden><button id="update-restore" type="button" disabled>Restaurar versão anterior</button></div>
 <p class="meta">O pacote pode estar no armazenamento local ou em um pendrive montado. A importação funciona sem internet. Limite: 48 MiB.</p>
 <div id="update-details" class="update-card" hidden><h2>Conferir atualização</h2><dl id="update-metadata"></dl><h2>O que mudou</h2><p id="update-notes"></p><p>Assinatura verificada com uma chave previamente confiável. A versão atual fica disponível para recuperação.</p><button id="update-install" type="button">Instalar esta atualização</button></div>
 <dialog id="update-confirm" aria-label="Confirmar operação"><p id="update-question"></p><div class="update-actions"><button id="update-yes" type="button">Confirmar</button><button id="update-no" type="button">Cancelar</button></div></dialog>
 <progress id="update-progress" max="100" value="0" aria-label="Progresso da atualização" hidden></progress><p id="update-status" role="status" aria-live="polite"></p>
 <p class="meta">Nenhuma instalação é silenciosa. A versão preparada só entra em uso ao fechar e abrir o AEGIS. Não feche durante a preparação. Dados persistentes não são migrados por este mecanismo.</p>`;
 main.append(panel);
 const $=id=>panel.querySelector('#update-'+id),session=globalThis.AEGIS_SESSION;
 let state=null,confirmAction=null,timer=null,localBusy=false;
 function error(e){$('status').textContent=e.message;$('status').classList.add('update-error');}
 async function api(path,body){
  const response=await fetch('/api/'+path,{method:body===undefined?'GET':'POST',headers:{'X-Aegis-Token':session,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
  const data=await response.json();if(!response.ok)throw Error(data.error||'Falha na comunicação local.');return data;
 }
 function controls(busy){
  for(const id of ['check','import'])$(id).disabled=busy||!session;
  $('restore').disabled=busy||!state||(!state.previous&&!state.pending);
  $('install').disabled=busy||!state?.candidate||!!state.pending||!state.trust_ready;
 }
 function metadata(candidate){
  $('metadata').replaceChildren();
  for(const [label,value] of [['Versão',candidate.version],['Data',candidate.released_at],['Tamanho',(candidate.size/1048576).toLocaleString('pt-BR',{maximumFractionDigits:2})+' MiB'],['Compatibilidade',candidate.systems.join(', ')+' · '+candidate.architectures.join(', ')],['Atualizador mínimo',candidate.min_updater]]){
   const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=value;$('metadata').append(dt,dd);
  }
  $('notes').textContent=candidate.notes;
 }
 async function refresh(){
  if(!session)return;
  try{
   state=await api('status');const busy=state.job.busy||localBusy;
   $('installed').textContent=state.installed;$('previous').textContent=state.previous||'Nenhuma';
   $('available').textContent=state.candidate?state.candidate.version:'Nenhum pacote conferido';
   $('trust').textContent=state.trust_ready?'Verificação de assinatura configurada.':'Instalação bloqueada: configure uma chave pública confiável e OpenSSL. Consulte o guia de atualizações.';
   $('pending').textContent=state.pending?'Versão '+state.pending+' preparada. Feche e abra o AEGIS quando desejar aplicar.':'';
   $('recovery').textContent=state.recovery;
   $('details').hidden=!state.candidate;if(state.candidate)metadata(state.candidate);
   $('restore').textContent=state.pending?'Cancelar atualização pendente':'Restaurar versão anterior';
   $('progress').hidden=!busy;$('progress').value=state.job.progress;
   $('status').textContent=state.job.message;$('status').classList.toggle('update-error',state.job.error);
   controls(busy);
   if(state.job.busy&&!timer)timer=setTimeout(()=>{timer=null;refresh();},400);
  }catch(e){error(e);controls(true);}
 }
 async function run(path,body={}){
  localBusy=true;controls(true);$('confirm').close();
  try{await api(path,body);}catch(e){error(e);localBusy=false;return;}
  localBusy=false;await refresh();
 }
 globalThis.AegisDeviceUI?.trap($('confirm'));
 let dialogTrigger=null;
 function confirm(text,action){dialogTrigger=document.activeElement;$('question').textContent=text;confirmAction=action;$('confirm').showModal();$('no').focus();}
 $('confirm').addEventListener('close',()=>{if(dialogTrigger?.isConnected)dialogTrigger.focus();});
 $('confirm').addEventListener('cancel',()=>{confirmAction=null;});
 $('yes').onclick=()=>{const action=confirmAction;confirmAction=null;$('confirm').close();if(action)action();};
 $('no').onclick=()=>{$('confirm').close();confirmAction=null;};
 $('check').onclick=()=>run('check');
 $('import').onclick=()=>$('file').click();
 $('file').onchange=async()=>{
  const file=$('file').files[0];if(!file)return;
  if(file.size===0||file.size>48*1048576){error(Error('Pacote vazio ou acima de 48 MiB.'));$('file').value='';return;}
  localBusy=true;controls(true);$('progress').hidden=false;$('progress').removeAttribute('value');$('status').textContent='Importando pacote local…';
  try{
   await new Promise((resolve,reject)=>{const xhr=new XMLHttpRequest();xhr.open('POST','/api/import');xhr.setRequestHeader('X-Aegis-Token',session);xhr.timeout=120000;
    xhr.upload.onprogress=e=>{if(e.lengthComputable)$('progress').value=e.loaded/e.total*70;};
    xhr.onload=()=>{if(xhr.status===202)resolve();else{let msg='Falha na importação.';try{msg=JSON.parse(xhr.responseText).error||msg;}catch{}reject(Error(msg));}};
    xhr.onerror=xhr.ontimeout=()=>reject(Error('Importação interrompida. Tente novamente.'));xhr.send(file);
   });
   localBusy=false;await refresh();
  }catch(e){localBusy=false;controls(false);error(e);}finally{$('file').value='';}
 };
 $('install').onclick=()=>{const candidate=state?.candidate;if(!candidate)return;confirm('Preparar a versão '+candidate.version+'? Ela só será aplicada quando você fechar e abrir o AEGIS.',()=>run('install',{id:candidate.id}));};
 $('restore').onclick=()=>confirm(state?.pending?'Cancelar a atualização pendente e preservar a versão atual?':'Preparar a restauração da versão anterior? Feche e abra o AEGIS depois da preparação.',()=>run('restore'));
 open.onclick=()=>{other.forEach(el=>el.hidden=true);panel.hidden=false;nav.querySelectorAll('[aria-pressed]').forEach(b=>b.setAttribute('aria-pressed',String(b===open)));panel.querySelector('h1').focus();refresh();};
 nav.querySelectorAll('button').forEach(button=>{if(button!==open)button.addEventListener('click',()=>{panel.hidden=true;open.setAttribute('aria-pressed','false');});});
 if(!session){$('installed').textContent='Prévia local';$('trust').textContent='Abra pelo lançador Python do AEGIS para usar as atualizações. Esta prévia de arquivo não instala pacotes.';controls(false);}
 // Confirm startup only after existing library/calculator scripts and the DOM loaded.
 addEventListener('load',()=>{if(session&&globalThis.AegisMedication&&(globalThis.AegisCatalog&&document.querySelector('#aegis-books'))&&!globalThis.AEGIS_START_ERRORS?.length)api('ready',{}).catch(error);});
})();
