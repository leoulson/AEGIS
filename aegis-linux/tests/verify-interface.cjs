const fs = require('fs');
const path = require('path');
const {pathToFileURL} = require('url');
const assert = require('assert/strict');
const {chromium} = require(process.env.AEGIS_PLAYWRIGHT || 'playwright');

(async () => {
  const root = path.resolve(__dirname, '..');
  const browser = await chromium.launch({executablePath:process.env.AEGIS_CHROME, headless:true});
  try {
    const context = await browser.newContext({offline:true, colorScheme:'dark', viewport:{width:1440,height:810}});
    const page = await context.newPage();
    const errors=[], external=[];
    page.on('pageerror',error=>errors.push(String(error)));
    page.on('request',request=>{if(/^https?:/.test(request.url()))external.push(request.url());});
    await page.goto(pathToFileURL(path.join(root,'app/index.html')).href);
    assert.equal(await page.locator('.book').count(),3);
    assert.ok(await page.locator('svg').count()>0);
    await page.getByRole('searchbox').fill('fisiologia');
    assert.equal(await page.locator('.book').count(),1);
    await page.locator('.book button').click();
    await page.getByRole('button',{name:'Salvar referência',exact:true}).click();
    await page.getByRole('button',{name:'Salvos',exact:true}).click();
    assert.equal(await page.locator('.book').count(),1);
    await page.getByRole('button',{name:'Fontes',exact:true}).click();
    assert.match(await page.locator('#aegis-books').innerText(),/ilustrativos/);
    await page.getByRole('button',{name:'Biblioteca',exact:true}).click();
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
    await page.getByRole('button',{name:'Quero estudar anatomia'}).click();
    assert.match(await page.locator('#aegis-answer').innerText(),/Exemplo de navegação/);
    await page.getByRole('button',{name:'Biblioteca',exact:true}).click();
    await page.locator('#open-medication').click();
    const shots = process.env.AEGIS_QA;
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
    console.log(JSON.stringify({browser:'Chrome/Windows',offline:true,search:true,filters:true,saved:true,sources:true,guide_demo:true,icons:true,medication_manual:true,medication_reference:true,medication_blocks:true,external_requests:external,js_errors:errors,responsive_widths:[1440,1024,390]}));
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
