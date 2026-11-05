const assert=require('assert/strict'),fs=require('fs'),path=require('path');
module.exports=async function verify(page,context,fixture,shots){
 const menu=()=>page.locator('#device-menu');
 const settings=()=>page.getByRole('button',{name:'⚙ Configurações',exact:true}).click();
 async function tab(name){await menu().getByRole('button',{name,exact:true}).click();}
 async function message(pattern){await page.waitForFunction(pattern=>new RegExp(pattern).test(document.querySelector('#device-status').textContent),pattern);}
 await settings();await tab('Diagnóstico');await message('Diagnóstico atualizado');
 assert.match(await page.locator('#device-readings').innerText(),/RAM total/);
 assert.match(await page.locator('#device-readings').innerText(),/Leituras atualizadas/);
 await page.evaluate(()=>{window.QA_SAVED=[];window.showSaveFilePicker=async options=>{window.QA_SAVE_NAME=options.suggestedName;return{createWritable:async()=>new WritableStream({write(chunk){QA_SAVED.push(...chunk);}})};};});
 await page.locator('#device-report').click();await page.waitForFunction(()=>QA_SAVED.length>0);
 assert.equal(await page.evaluate(()=>QA_SAVE_NAME),'aegis-diagnostico.json');
 assert.equal(await page.evaluate(()=>JSON.parse(new TextDecoder().decode(new Uint8Array(QA_SAVED))).aegis_version),'0.2.0');
 const report=await page.evaluate(async()=>{const r=await fetch('/api/diagnostic-report',{headers:{'X-Aegis-Token':AEGIS_SESSION}});return r.json();});
 assert.equal(report.aegis_version,'0.2.0');assert.equal(report.documents,2);assert.ok(report.storage.total>0);
 assert.equal(JSON.stringify(report).includes('personal QA fixture'),false);
 if(shots)await page.screenshot({path:path.join(shots,'diagnostic-390.png'),fullPage:true});
 await tab('Verificar acervo');await page.locator('#device-verify').click();await message('Verificação concluída');
 assert.match(await page.locator('#device-results').innerText(),/Pacote íntegro/);
 assert.match(await page.locator('#device-results').innerText(),/sem manifesto verificável/);
 await tab('Acessibilidade');await page.locator('#device-text').selectOption('200');await page.locator('#device-contrast').check();await page.locator('#device-motion').check();await page.locator('#device-access-save').click();await message('Preferências salvas');
 assert.equal(await page.evaluate(()=>getComputedStyle(document.querySelector('#aegis-library')).backgroundColor),'rgb(0, 0, 0)');
 for(const width of [1280,800,390]){await page.setViewportSize({width,height:800});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'200% overflow at '+width);}
 if(shots)await page.screenshot({path:path.join(shots,'accessibility-200-390.png'),fullPage:true});
 await page.locator('#device-access-default').click();assert.equal(await page.evaluate(()=>document.documentElement.dataset.textSize),'100');
 await page.reload();await settings();await tab('Acessibilidade');
 assert.equal(await page.locator('#device-text').inputValue(),'200');assert.equal(await page.locator('#device-contrast').isChecked(),true);
 await page.locator('#open-medication').click();
 assert.equal(await page.locator('#medication label').first().evaluate(e=>getComputedStyle(e).fontSize),'26px');
 await page.locator('#med-age').fill('5');await page.locator('#med-weight').fill('20');await page.locator('#med-dose').fill('15');await page.locator('#med-frequency').selectOption('4');
 await page.getByRole('button',{name:'Calcular e conferir →',exact:true}).click();assert.match(await page.locator('#med-result').innerText(),/300 mg por tomada/);
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 if(shots)await page.screenshot({path:path.join(shots,'calculator-200-390.png'),fullPage:true});
 await settings();
 await tab('Atalhos');await page.locator('#device-tool').selectOption('recovery');await page.locator('#device-shortcut-add').click();await page.locator('#device-shortcut-add').click();
 assert.equal(await page.locator('#device-shortcut-list li').count(),4);
 await page.getByRole('button',{name:'Subir Recuperação',exact:true}).focus();await page.keyboard.press('Enter');
 await page.locator('#device-shortcut-save').click();await message('Preferências salvas');
 const prefs=JSON.parse(fs.readFileSync(path.join(fixture.data,'preferences.json')));assert.deepEqual(prefs.shortcuts,['calculator','diagnostics','recovery','collection']);
 await page.getByRole('button',{name:'Biblioteca',exact:true}).click();
 assert.equal(await page.locator('[data-shortcut]').count(),4);
 await page.locator('[data-shortcut="diagnostics"]').click();assert.equal(await page.locator('#device-diagnostics').isVisible(),true);
 await settings();await tab('Recuperação');await page.locator('#device-open-recovery').focus();await page.keyboard.press('Space');
 const dialog=page.getByRole('dialog',{name:'Confirmar operação',exact:true});await dialog.waitFor();
 for(let i=0;i<4;i++){await page.keyboard.press('Tab');assert.equal(await page.evaluate(()=>!!document.activeElement.closest('dialog')),true);}
 for(let i=0;i<3;i++){await page.keyboard.press('Shift+Tab');assert.equal(await page.evaluate(()=>!!document.activeElement.closest('dialog')),true);}
 await page.keyboard.press('Escape');assert.equal(await page.locator('#device-open-recovery').evaluate(e=>e===document.activeElement),true);
 await tab('Backups');await page.locator('#device-backup-create').click();await message('Backup consistente criado');assert.equal(await page.locator('#device-backup-save').isEnabled(),true);
 const backup=await page.evaluate(async()=>{const r=await fetch('/api/backup-download',{headers:{'X-Aegis-Token':AEGIS_SESSION}});return Array.from(new Uint8Array(await r.arrayBuffer()));});
 const backupPath=path.join(fixture.home,'qa-export.aegis-backup');fs.writeFileSync(backupPath,Buffer.from(backup));
 // Main application restoration is blocked even with a selected backup.
 const blocked=await page.evaluate(async()=>{await fetch('/api/backup-restore',{method:'POST',headers:{'X-Aegis-Token':AEGIS_SESSION,'Content-Type':'application/json'},body:JSON.stringify({id:'fake'})});await new Promise(r=>setTimeout(r,100));return(await(await fetch('/api/status',{headers:{'X-Aegis-Token':AEGIS_SESSION}})).json()).job.message;});
 assert.match(blocked,/modo de recuperação/);
 await page.close();
 // Serve recovery assets while the selected application's index is damaged.
 const appState=JSON.parse(fs.readFileSync(path.join(fixture.home,'state.json'))),index=path.join(fixture.home,'versions',appState.current,'app/index.html');fs.writeFileSync(index,'broken application');
 fs.writeFileSync(path.join(fixture.data,'personal','qa.txt'),'newer personal state');
 const recovery=await context.newPage();await recovery.setViewportSize({width:390,height:800});await recovery.goto(fixture.recovery_url);
 await recovery.locator('#diagnose').click();await recovery.waitForFunction(()=>document.querySelector('#status').textContent.includes('Diagnóstico atualizado'));
 assert.equal(await recovery.locator('h1').innerText(),'Recuperação do AEGIS');
 assert.equal(await recovery.evaluate(()=>document.documentElement.dataset.textSize),'200');
 await recovery.locator('#file').setInputFiles(backupPath);
 await recovery.waitForFunction(()=>document.querySelector('#status').textContent.includes('Backup conferido'));
 assert.match(await recovery.locator('#backup-details').innerText(),/user-data-v1/);
 await recovery.locator('#restore-data').click();await recovery.getByRole('dialog').getByRole('button',{name:'Cancelar',exact:true}).click();
 assert.equal(fs.readFileSync(path.join(fixture.data,'personal','qa.txt'),'utf8'),'newer personal state');
 await recovery.locator('#restore-data').click();await recovery.getByRole('dialog').getByRole('button',{name:'Confirmar',exact:true}).click();
 await recovery.waitForFunction(()=>document.querySelector('#status').textContent.includes('Dados restaurados'));
 assert.equal(fs.readFileSync(path.join(fixture.data,'personal','qa.txt'),'utf8'),'personal QA fixture');
 assert.equal(fs.readdirSync(path.join(fixture.home,'safety-backups')).length,1);
 const overflowing=await recovery.evaluate(()=>[...document.querySelectorAll('main *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1).map(e=>({tag:e.tagName,id:e.id,width:e.getBoundingClientRect().width})).slice(0,8));
 assert.equal(await recovery.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'Recovery 200% overflow: '+JSON.stringify(overflowing));
 await recovery.evaluate(()=>scrollTo(0,0));
 if(shots)await recovery.screenshot({path:path.join(shots,'recovery-200-390.png')});
 await recovery.locator('#restart').click();await recovery.keyboard.press('Escape');
 assert.equal(await recovery.locator('#restart').evaluate(e=>e===document.activeElement),true);
 await recovery.close();
 console.log('Device tools passed: real diagnostics export, collection states, 200% high contrast, persisted preferences/shortcuts, keyboard reorder/modal focus, consistent backup, independent recovery with damaged main HTML, confirmation and data restoration.');
};
