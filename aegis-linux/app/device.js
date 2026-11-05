(()=>{
 'use strict';
 const ui=globalThis.AegisDeviceUI,root=document.querySelector('#aegis-library'),main=root.querySelector('main'),nav=root.querySelector('nav');
 if(!ui||!globalThis.AEGIS_SESSION)return;
 const labels={calculator:'Calculadora',updates:'Atualizações',diagnostics:'Diagnóstico',collection:'Verificar acervo',backups:'Backups',accessibility:'Acessibilidade',recovery:'Recuperação'};
 const menu=document.createElement('div');menu.id='device-menu';menu.hidden=true;menu.setAttribute('role','navigation');menu.setAttribute('aria-label','Configurações do dispositivo');main.prepend(menu);
 const panels={};let state=null,timer=null,prefs=null;
 const status=document.createElement('p');status.id='device-status';status.className='device-status';status.setAttribute('role','status');status.setAttribute('aria-live','polite');status.hidden=true;main.append(status);
 function error(e){if(e.name!=='AbortError'){status.hidden=false;status.textContent='Erro: '+e.message;}}
 function panel(id,html){const el=document.createElement('section');el.id='device-'+id;el.hidden=true;el.innerHTML='<div class="eyebrow">CONFIGURAÇÕES</div><h1 tabindex="-1">'+labels[id]+'</h1>'+html;main.append(el);panels[id]=el;return el;}
 const diagnostic=panel('diagnostics','<p>Leituras reais; sensores ausentes são indicados. Atualização sob demanda, com intervalo mínimo de 15 segundos.</p><div class="device-actions"><button id="device-diagnose">Atualizar diagnóstico</button><button id="device-report" disabled>Exportar relatório</button></div><div id="device-readings" class="device-card"></div>');
 const collection=panel('collection','<p>Hashes verificam correspondência ao manifesto; a autenticidade é apresentada separadamente. Nenhuma referência será criada a partir dos arquivos instalados.</p><div class="device-actions"><button id="device-verify">Verificar acervo agora</button><button id="device-cancel" disabled>Cancelar verificação</button></div><progress id="device-progress" max="100" value="0" aria-label="Progresso do acervo" hidden></progress><div id="device-results" class="device-card" aria-live="polite">Ainda não verificado nesta sessão.</div>');
 const backups=panel('backups','<div class="device-card"><p>Inclui library.sqlite3 com snapshot consistente, preferências, favoritos, anotações, configurações, histórico e documentos em personal/. Exclui aplicativo, Linux, modelos de IA, pacotes do acervo, chaves e arquivos fora desse alcance.</p><p>O backup pode conter seus dados pessoais. Escolha um destino seguro. Limites: 128 MiB compactados e 256 MiB expandidos.</p><div class="device-actions"><button id="device-backup-create">Criar backup</button><button id="device-backup-save" disabled>Salvar backup</button><button id="device-backup-recovery">Abrir recuperação para restaurar</button></div><p>A restauração dos dados exige a interface principal fechada, conferência do backup e confirmação na recuperação. Restaurar aplicativo e reinstalar acervo são operações separadas.</p></div>');
 const access=panel('accessibility','<div class="device-card"><label>Tamanho do texto<select id="device-text"><option value="100">100% — padrão</option><option value="125">125%</option><option value="150">150%</option><option value="200">200%</option></select></label><label><input id="device-contrast" type="checkbox"> Alto contraste</label><label><input id="device-motion" type="checkbox"> Reduzir efeitos e animações</label><p>As alterações são visualizadas imediatamente em todas as telas. Salve para mantê-las ao abrir novamente.</p><div class="device-actions"><button id="device-access-save">Salvar acessibilidade</button><button id="device-access-default">Visualizar padrões</button></div></div>');
 const shortcuts=panel('shortcuts','<div class="device-card"><p>Adicione ferramentas disponíveis. Use os botões para reordenar, inclusive com Tab e Enter; não é necessário arrastar.</p><label>Ferramenta<select id="device-tool"></select></label><button id="device-shortcut-add">Adicionar atalho</button><ol id="device-shortcut-list"></ol><div class="device-actions"><button id="device-shortcut-save">Salvar atalhos</button><button id="device-shortcut-default">Restaurar atalhos padrão</button></div></div>');
 shortcuts.querySelector('h1').textContent='Atalhos da tela inicial';
 const recovery=panel('recovery','<div class="device-card"><p>A recuperação independente permite consultar diagnóstico e registros, restaurar o aplicativo ou um backup dos dados, e escolher quando abrir o aplicativo.</p><p>A janela principal será fechada antes de abrir a recuperação. Não há garantia de recuperação de cartão SD fisicamente danificado ou Linux que não inicia.</p><button id="device-open-recovery">Abrir modo de recuperação</button></div>');
 const $=id=>document.getElementById('device-'+id);
 function show(id){
  if(id==='updates'){document.getElementById('open-settings').click();return;}
  [...main.children].forEach(el=>el.hidden=true);menu.hidden=false;panels[id].hidden=false;status.hidden=false;
  menu.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.tool===id)));
  nav.querySelectorAll('[aria-pressed]').forEach(b=>b.setAttribute('aria-pressed',String(b.id==='open-settings')));
  panels[id].querySelector('h1').focus();
  if(id==='diagnostics')run('diagnostics');else refresh();
 }
 for(const id of ['updates','diagnostics','collection','backups','accessibility','shortcuts','recovery']){
  const b=document.createElement('button');b.type='button';b.dataset.tool=id;b.textContent=id==='shortcuts'?'Atalhos':labels[id];b.onclick=()=>show(id);menu.append(b);
 }
 nav.querySelectorAll('button').forEach(button=>button.addEventListener('click',()=>{
  Object.values(panels).forEach(p=>p.hidden=true);status.hidden=true;
  const settings=button.id==='open-settings';menu.hidden=!settings;
  if(settings){menu.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.tool==='updates')));refresh();}
 }));
 const home=document.createElement('section');home.id='device-shortcuts';home.setAttribute('aria-label','Atalhos da tela inicial');
 // The medication module wraps the original library; keep shortcuts inside that wrapper.
 const library=main.querySelector('#aegis-search').closest('div');
 library.prepend(home);
 function openTool(id){if(id==='calculator')document.getElementById('open-medication').click();else if(id==='updates')document.getElementById('open-settings').click();else if(panels[id])show(id);}
 function homeShortcuts(){home.replaceChildren();const h=document.createElement('h2');h.textContent='Seus atalhos';home.append(h);const actions=document.createElement('div');actions.className='device-actions';for(const id of prefs.shortcuts){if(!labels[id])continue;const b=document.createElement('button');b.type='button';b.textContent=labels[id];b.dataset.shortcut=id;b.onclick=()=>openTool(id);actions.append(b);}home.append(actions);}
 function editShortcuts(focusIndex=null){
  $('shortcut-list').replaceChildren();
  prefs.shortcuts.forEach((id,index)=>{const li=document.createElement('li');li.textContent=labels[id]+' ';const actions=document.createElement('div');actions.className='device-actions';
   for(const [label,move,disabled]of [['Subir',-1,index===0],['Descer',1,index===prefs.shortcuts.length-1],['Remover',0,false]]){const b=document.createElement('button');b.type='button';b.textContent=label;b.setAttribute('aria-label',label+' '+labels[id]);b.disabled=disabled;b.onclick=()=>{if(move){[prefs.shortcuts[index],prefs.shortcuts[index+move]]=[prefs.shortcuts[index+move],prefs.shortcuts[index]];}else prefs.shortcuts.splice(index,1);editShortcuts(Math.max(0,index+move));};actions.append(b);}li.append(actions);$('shortcut-list').append(li);
  });
  if(focusIndex!==null)$('shortcut-list').children[focusIndex]?.querySelector('button:not(:disabled)')?.focus();
  homeShortcuts();
 }
 function fillPrefs(){if(!prefs)return;$('text').value=prefs.text_size;$('contrast').checked=prefs.high_contrast;$('motion').checked=prefs.reduced_motion;ui.apply(prefs);editShortcuts();}
 for(const [id,label]of Object.entries(labels)){const opt=document.createElement('option');opt.value=id;opt.textContent=label;$('tool').append(opt);}
 function preview(){if(!prefs)return;ui.apply({...prefs,text_size:Number($('text').value),high_contrast:$('contrast').checked,reduced_motion:$('motion').checked});}
 for(const id of ['text','contrast','motion'])$(id).onchange=preview;
 async function savePrefs(value){try{await ui.api('preferences',value);prefs=value;ui.apply(prefs);homeShortcuts();status.hidden=false;status.textContent='Preferências salvas localmente.';}catch(e){error(e);}}
 $('access-save').onclick=()=>savePrefs({...prefs,text_size:Number($('text').value),high_contrast:$('contrast').checked,reduced_motion:$('motion').checked});
 $('access-default').onclick=()=>{$('text').value='100';$('contrast').checked=false;$('motion').checked=false;preview();status.textContent='Padrões visualizados. Selecione Salvar acessibilidade para persistir.';};
 $('shortcut-add').onclick=()=>{const id=$('tool').value;if(!prefs.shortcuts.includes(id)){prefs.shortcuts.push(id);editShortcuts();}else{status.hidden=false;status.textContent='Esse atalho já está na lista.';}};
 $('shortcut-save').onclick=()=>savePrefs(prefs);
 $('shortcut-default').onclick=()=>{prefs.shortcuts=['calculator','diagnostics','collection'];editShortcuts();savePrefs(prefs);};
 async function run(path,body={}){try{await ui.api(path,body);await refresh();}catch(e){error(e);}}
 function results(result){const out=$('results');out.replaceChildren();if(!result){out.textContent='Ainda não verificado nesta sessão.';return;}
  const p=document.createElement('p');p.textContent=(result.complete?'Verificação concluída':'Verificação interrompida ou incompleta')+' · '+result.at;out.append(p);
  const translated={intact:'Pacote íntegro',damaged:'Pacote com problemas — precisa de reinstalação',unverifiable:'Pacote sem manifesto verificável',incomplete:'Verificação incompleta'};
  const fileStates={intact:'íntegro',missing:'ausente',divergent:'conteúdo divergente',unreadable:'ilegível',changed_or_unsafe:'alterado durante a verificação ou caminho inseguro',incomplete:'leitura interrompida',unexpected:'arquivo não previsto'};
  for(const pkg of result.packages){const section=document.createElement('details'),summary=document.createElement('summary');summary.textContent=pkg.id+': '+translated[pkg.integrity];section.append(summary);const note=document.createElement('p');note.textContent='Autenticidade: '+pkg.authenticity+(pkg.reason?' · '+pkg.reason:'');section.append(note);const ul=document.createElement('ul');for(const file of pkg.files){const li=document.createElement('li');li.textContent=file.path+': '+fileStates[file.status];ul.append(li);}section.append(ul);out.append(section);}
  if(!result.packages.length){const p=document.createElement('p');p.textContent='Nenhum pacote instalado. Isso não valida um acervo inexistente.';out.append(p);}
  const guidance=document.createElement('p');guidance.textContent=result.guidance;out.append(guidance);
 }
 async function refresh(){try{
  state=await ui.api('status');if(!prefs){prefs=structuredClone(state.preferences);fillPrefs();}
  ui.diagnostic($('readings'),state.diagnostic);$('report').disabled=!state.diagnostic;results(state.verification);
  for(const id of ['diagnose','verify','backup-create','open-recovery','backup-recovery'])$(id).disabled=state.job.busy;
  $('cancel').disabled=!state.job.busy||state.job.operation!=='collection';$('backup-save').disabled=state.job.busy||!state.backup_ready;
  $('progress').hidden=!state.job.busy;$('progress').value=state.job.progress;
  if(!status.hidden)status.textContent=(state.job.error?'Erro: ':'')+(state.job.message||state.notice||'');
  if(state.job.busy&&!timer)timer=setTimeout(()=>{timer=null;refresh();},400);
 }catch(e){error(e);}}
 $('diagnose').onclick=()=>run('diagnostics');$('report').onclick=()=>ui.save('diagnostic-report','aegis-diagnostico.json','application/json').catch(error);
 $('verify').onclick=()=>run('collection-verify');$('cancel').onclick=()=>run('collection-cancel');
 $('backup-create').onclick=()=>run('backup-create');$('backup-save').onclick=()=>ui.save('backup-download','aegis-dados.aegis-backup','application/octet-stream').catch(error);
 const recover=()=>ui.confirm('Fechar o aplicativo e abrir a recuperação independente? Aguarde operações em andamento terminarem.',()=>run('recovery'));
 $('open-recovery').onclick=$('backup-recovery').onclick=recover;
 refresh();
})();
