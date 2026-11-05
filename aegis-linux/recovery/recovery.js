(()=>{
 'use strict';
 const ui=AegisDeviceUI,$=id=>document.getElementById(id);let state=null,timer=null,selectedName='';
 function error(e){if(e.name!=='AbortError')$('status').textContent=e.message;}
 async function refresh(){try{
  state=await ui.api('status');ui.apply(state.preferences);
  $('reason').textContent=state.notice||state.recovery||'Recuperação aberta explicitamente pelo usuário.';
  $('versions').textContent='Instalada: '+(state.installed||'indisponível')+' · anterior: '+(state.previous||'nenhuma')+' · pendente: '+(state.pending||'nenhuma');
  ui.diagnostic($('diagnostic'),state.diagnostic);
  $('logs').textContent=state.logs.map(e=>e.at+' · '+e.code).join('\n')||'Nenhum evento registrado.';
  for(const id of ['diagnose','create','select','restart','rollback','restore-data','resume'])$(id).disabled=state.job.busy;
  $('rollback').disabled=state.job.busy||(!state.previous&&!state.pending);
  $('rollback').textContent=state.pending?'Cancelar preparação pendente':'Restaurar versão anterior';
  $('restore-data').disabled=state.job.busy||!state.backup_candidate||state.restore_incomplete;
  $('save').disabled=state.job.busy||!state.backup_ready;$('report').disabled=!state.diagnostic;
  $('resume').hidden=!state.restore_incomplete;
  $('backup-details').textContent=state.backup_candidate?['Arquivo local: '+selectedName,'Origem declarada: '+state.backup_candidate.origin,'Data: '+state.backup_candidate.created_at,'AEGIS: '+state.backup_candidate.app_version,'Alcance: '+state.backup_candidate.scope+' · '+state.backup_candidate.files+' arquivos · '+ui.bytes(state.backup_candidate.size),state.backup_candidate.authenticity].join('\n'):'Nenhum backup selecionado.';
  $('status').textContent=(state.job.error?'Erro: ':'')+state.job.message;$('progress').hidden=!state.job.busy;$('progress').value=state.job.progress;
  if(state.job.busy&&!timer)timer=setTimeout(()=>{timer=null;refresh();},400);
 }catch(e){error(e);}}
 async function run(path,body={}){try{await ui.api(path,body);await refresh();}catch(e){error(e);}}
 $('diagnose').onclick=()=>run('diagnostics');$('report').onclick=()=>ui.save('diagnostic-report','aegis-diagnostico.json','application/json').catch(error);
 $('rollback').onclick=()=>ui.confirm('Preparar a restauração/cancelamento do aplicativo? Dados pessoais não serão modificados.',()=>run('restore'));
 $('restart').onclick=()=>ui.confirm('Encerrar a recuperação e iniciar o aplicativo? Não haverá nova tentativa sem esta confirmação.',()=>run('restart'));
 $('exit').onclick=()=>{window.close();$('status').textContent='Se a janela continuar aberta, feche-a com Alt+F4. Nenhuma reinicialização será feita.';};
 $('create').onclick=()=>run('backup-create');$('save').onclick=()=>ui.save('backup-download','aegis-dados.aegis-backup','application/octet-stream').catch(error);
 $('select').onclick=()=>$('file').click();
 $('file').onchange=async()=>{const file=$('file').files[0];if(!file)return;selectedName=file.name;try{
  if(file.size>128*1048576)throw Error('Backup acima de 128 MiB.');
  $('status').textContent='Importando backup local…';$('progress').hidden=false;$('progress').removeAttribute('value');
  const response=await fetch('/api/backup-import',{method:'POST',headers:{'X-Aegis-Token':AEGIS_SESSION},body:file});
  if(!response.ok)throw Error((await response.json()).error);await refresh();
 }catch(e){error(e);}finally{$('file').value='';}};
 $('restore-data').onclick=()=>{const id=state.backup_candidate?.id;ui.confirm('Sobrescrever os dados incluídos neste backup? Uma cópia consistente do estado atual será criada antes. Sem espaço, nada será restaurado.',()=>run('backup-restore',{id}));};
 $('resume').onclick=()=>ui.confirm('Retomar a restauração registrada? A interface principal ficará fechada até concluir.',()=>run('resume-restore'));
 refresh();ui.api('ready',{}).catch(error);
})();
