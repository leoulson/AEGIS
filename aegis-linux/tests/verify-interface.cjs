const fs = require('fs');
const path = require('path');
const {pathToFileURL} = require('url');
const assert = require('assert/strict');
const browserName=process.env.AEGIS_BROWSER||'chromium';
const engine=require(process.env.AEGIS_PLAYWRIGHT || 'playwright')[browserName];

(async () => {
  const fixture=process.env.AEGIS_TEST_FIXTURE?JSON.parse(process.env.AEGIS_TEST_FIXTURE):null;
  const root = path.resolve(__dirname, '..');
  const shots = process.env.AEGIS_QA;
  if(shots)fs.mkdirSync(shots,{recursive:true});
  const browser = await engine.launch({executablePath:browserName==='chromium'?process.env.AEGIS_CHROME:undefined, headless:true});
  try {
    const context = await browser.newContext({offline:!fixture, colorScheme:'dark', viewport:{width:1440,height:810}});
    const page = await context.newPage();
    const errors=[], external=[];
    page.on('pageerror',error=>errors.push(String(error)));
    page.on('request',request=>{if(/^https?:/.test(request.url())&&(!fixture||!request.url().startsWith(fixture.url)))external.push(request.url());});
    if(fixture) await context.route('**/*',route=>{const url=route.request().url();return url.startsWith(fixture.url)?route.continue():route.abort();});
    await page.goto(fixture?fixture.url:pathToFileURL(path.join(root,'app/index.html')).href);
    assert.equal(await page.locator('.book').count(),0);
    if(shots)await page.screenshot({path:path.join(shots,'catalog-default-1440.png'),fullPage:true});
    await page.locator('#catalog-open-editorial').click();
    assert.equal(await page.locator('.book').count(),7);
    if(shots)await page.screenshot({path:path.join(shots,'catalog-editorial-1440.png'),fullPage:true});
    assert.ok(await page.locator('svg').count()>0);
    await page.getByRole('searchbox').fill('osmolaridade');
    assert.equal(await page.locator('.book').count(),1);
    await page.locator('.book button').click();
    assert.match(await page.locator('#aegis-detail').innerText(),/Hahn S, Kim Y, Garner P/);
    assert.match(await page.locator('#aegis-detail').innerText(),/Revisão clínica: não realizada/);
    if(shots)await page.screenshot({path:path.join(shots,'card-desidratacao-1440.png'),fullPage:true});
    await page.getByRole('button',{name:'Salvar referência',exact:true}).click();
    await page.getByRole('button',{name:'Salvos',exact:true}).click();
    assert.equal(await page.locator('.book').count(),1);
    await page.getByRole('button',{name:'Fontes',exact:true}).click();
    assert.match(await page.locator('#aegis-books').innerText(),/Direitos:/);
    await page.getByRole('button',{name:'Biblioteca',exact:true}).click();
    const original=await page.evaluate(()=>{const original=AegisCatalog.cards[0].title;AegisCatalog.cards[0].title='<img src=x onerror=alert(1)>';return original;});
    await page.getByRole('button',{name:'Biblioteca',exact:true}).click();
    assert.equal(await page.locator('#aegis-books img').count(),0);
    assert.ok((await page.locator('#aegis-books').innerText()).includes('<img src=x onerror=alert(1)>'));
    await page.evaluate(original=>{AegisCatalog.cards[0].title=original;},original);
    await page.getByRole('button',{name:'Política editorial',exact:true}).click();
    assert.match(await page.locator('#aegis-books').innerText(),/DOI, indexação/);
    await page.getByRole('button',{name:'Biblioteca',exact:true}).click();
    await page.locator('#catalog-state').selectOption('draft');
    assert.equal(await page.locator('.book').count(),0);
    assert.match(await page.locator('#aegis-books').innerText(),/Nenhuma ficha corresponde/);
    await page.locator('#catalog-state').selectOption('pending_professional_review');
    await page.getByRole('button',{name:'Urgência e emergência',exact:true}).click();
    assert.equal(await page.locator('.book').count(),4);
    assert.match(await page.locator('#catalog-planned').innerText(),/Estrutura planejada/);
    await page.locator('#catalog-editorial').uncheck();
    assert.equal(await page.locator('.book').count(),0);
    await page.locator('#catalog-open-editorial').click();
    await page.getByRole('button',{name:'Todas as áreas',exact:true}).click();
    await page.locator('#open-medication').click();
    assert.equal(await page.locator('#medication').isVisible(),true);
    await page.locator('#med-age').fill('5');
    await page.locator('#med-weight').fill('20');
    await page.locator('#med-dose').fill('15');
    await page.locator('#med-frequency').selectOption('4');
    await page.locator('#med-strength').fill('120');
    await page.locator('#med-volume').fill('5');
    await page.getByRole('button',{name:'Calcular e conferir →',exact:true}).click();
    assert.match(await page.locator('#med-result').innerText(),/300 mg por tomada/);
    assert.match(await page.locator('#med-result').innerText(),/12,5 mL por tomada/);
    await page.locator('#med-mode').selectOption('reference');
    await page.locator('#med-drug').selectOption('cetirizine');
    await page.locator('#med-reviewed').check();
    await page.getByRole('button',{name:'Calcular e conferir →',exact:true}).click();
    assert.match(await page.locator('#med-result').innerText(),/2,5 mg por tomada/);
    assert.match(await page.locator('#med-result').innerText(),/NHS/);
    await page.locator('#med-special').check();
    await page.getByRole('button',{name:'Calcular e conferir →',exact:true}).click();
    assert.match(await page.locator('#med-result').innerText(),/Condições especiais/);
    assert.equal(await page.locator('#med-result .med-big').count(),0);
    await page.getByRole('button',{name:'Limpar',exact:true}).click();
    await page.locator('#med-age').fill('5');
    await page.locator('#med-weight').fill('20');
    await page.locator('#med-dose').fill('15');
    await page.locator('#med-frequency').selectOption('4');
    await page.locator('#med-strength').fill('120');
    await page.getByRole('button',{name:'Calcular e conferir →',exact:true}).click();
    assert.equal(await page.locator('#med-result .med-error').count(),1);
    assert.equal(await page.locator('#med-result .med-big').count(),0);
    await page.getByRole('button',{name:'Biblioteca',exact:true}).click();
    await page.getByRole('button',{name:'Buscar evidência de reidratação'}).click();
    assert.match(await page.locator('#aegis-answer').innerText(),/Busca textual local na oficina editorial/);
    await page.getByRole('button',{name:'Biblioteca',exact:true}).click();
    await page.locator('#open-medication').click();
    if(shots){fs.mkdirSync(shots,{recursive:true});await page.screenshot({path:path.join(shots,'desktop.png'),fullPage:true});}
    for (const width of [1440,1024,390]) {
      await page.setViewportSize({width,height:810});
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,`Horizontal overflow at ${width}`);
    }
    if(shots) await page.screenshot({path:path.join(shots,'mobile.png'),fullPage:true});
    assert.deepEqual(errors,[]);
    assert.deepEqual(external,[]);
    await page.getByRole('button',{name:'Biblioteca',exact:true}).click();
    assert.equal(await page.locator('#medication').isVisible(),false);
    if(shots)await page.screenshot({path:path.join(shots,'catalog-editorial-390.png'),fullPage:true});
    if(fixture){
      const status=()=>page.locator('#update-status');
      async function waitMessage(pattern){await page.waitForFunction(pattern=>new RegExp(pattern).test(document.querySelector('#update-status').textContent),pattern);}
      const settings=()=>page.getByRole('button',{name:'⚙ Configurações',exact:true}).click();
      await settings();
      await page.waitForFunction(()=>document.querySelector('#update-installed').textContent==='0.2.0');
      assert.match(await page.locator('#update-trust').innerText(),/Instalação bloqueada/);
      assert.equal(await page.locator('#update-restore').isDisabled(),true);
      // Offline import still rejects a package signed by an unconfigured key.
      await page.locator('#update-file').setInputFiles(fixture.package);
      await waitMessage('Chave desconhecida');
      assert.equal(await page.locator('#update-details').isVisible(),false);
      // Provision only the temporary fixture's public trust anchor.
      fs.copyFileSync(fixture.public,fixture.trust_target);
      fs.writeFileSync(fixture.mode,'offline');
      await page.locator('#update-check').click();await waitMessage('Sem internet');
      fs.writeFileSync(fixture.mode,'none');
      await page.locator('#update-check').click();await waitMessage('Nenhuma Release');
      fs.writeFileSync(fixture.mode,'download-fail');
      await page.locator('#update-check').click();await waitMessage('Download interrompido');
      // A local package succeeds without calling the network fixture.
      fs.writeFileSync(fixture.mode,'offline');
      await page.locator('#update-file').setInputFiles(fixture.package);
      await waitMessage('Pacote autêntico');
      assert.equal(await page.locator('#update-details img').count(),0);
      assert.match(await page.locator('#update-metadata').innerText(),/0.3.0/);
      await page.locator('#update-install').click();
      await page.locator('#update-no').click();
      assert.equal(JSON.parse(fs.readFileSync(path.join(fixture.home,'state.json'))).pending,null);
      await page.locator('#update-install').click();await page.locator('#update-yes').click();
      await waitMessage('Preparação concluída');
      assert.match(await page.locator('#update-pending').innerText(),/0.3.0 preparada/);
      assert.equal(await page.locator('#update-installed').innerText(),'0.2.0');
      await page.locator('#update-restore').click();await page.locator('#update-yes').click();
      await waitMessage('pendente cancelada');
      fs.writeFileSync(fixture.mode,'available');
      await page.locator('#update-check').click();await waitMessage('Pacote autêntico');
      // The same details and explicit confirmation are required for online updates.
      assert.equal(await page.locator('#update-install').isEnabled(),true);
      if(shots)await page.screenshot({path:path.join(shots,'updates.png'),fullPage:true});
      const forbidden=await page.request.post(fixture.url+'api/restore',{data:{}});
      assert.equal(forbidden.status(),403);
      for(const width of [1440,1024,390]){await page.setViewportSize({width,height:810});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);}
      await page.getByRole('button',{name:'Biblioteca',exact:true}).click();
      assert.equal(await page.locator('.book').count(),7);
      await page.locator('#open-medication').click();
      assert.equal(await page.locator('#medication').isVisible(),true);
      assert.equal(await page.locator('#updates').isVisible(),false);
      console.log('Update center: missing trust, offline/local import, no releases, interrupted download, online preview, confirmation/cancel, deferred install, pending cancellation, CSRF, navigation and responsive layouts passed.');
    }
    if(fixture){await context.unroute('**/*');await context.route('**/*',route=>{const url=route.request().url();return url.startsWith(fixture.url)||url.startsWith(fixture.recovery_url)?route.continue():route.abort();});await require('./verify-device.cjs')(page,context,fixture,shots);}
    assert.deepEqual(errors,[]);
    assert.deepEqual(external,[]);
    console.log(JSON.stringify({browser:process.platform+' '+browserName,offline:!fixture,network_scope:fixture?'loopback-only':'none',search:true,filters:true,saved:true,sources:true,guide_demo:true,icons:true,medication_manual:true,medication_reference:true,medication_blocks:true,external_requests:external,js_errors:errors,responsive_widths:[1440,1024,390]}));
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
