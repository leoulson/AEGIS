(()=>{
 'use strict';
 const core=globalThis.AegisMedication,root=document.querySelector('#aegis-library');
 const main=root.querySelector('main'), library=document.createElement('div');
 while(main.firstChild) library.append(main.firstChild);
 main.append(library);
 const nav=root.querySelector('nav'),open=document.createElement('button');
 open.type='button';open.textContent='▦ Calculadora';open.setAttribute('aria-pressed','false');open.id='open-medication';
 nav.insertBefore(open,nav.querySelector('.nav-label'));
 const panel=document.createElement('section');panel.hidden=true;panel.id='medication';
 panel.innerHTML=`<div class="eyebrow">FERRAMENTAS OFFLINE · VERSÃO 0.2</div>
 <h1 tabindex="-1">Calculadora de medicamentos</h1>
 <p class="muted">Adultos e pediatria · dose por tomada, total em 24 horas e volume oral.</p>
 <p class="med-notice">Protótipo para conferência de cálculos. Exige revisão profissional antes de uso clínico. As referências não substituem a prescrição e a bula da apresentação utilizada.</p>
 <div class="med-layout"><form id="med-form" novalidate>
 <label>Modo de cálculo<select id="med-mode"><option value="manual">Informar dose prescrita</option><option value="reference">Consultar medicamento cadastrado</option></select></label>
 <div class="med-grid"><label>População<select id="med-pop"><option value="child">Pediatria — menos de 18 anos</option><option value="adult">Adulto — 18 anos ou mais</option></select></label><label>Peso (kg)<input id="med-weight" inputmode="decimal" autocomplete="off" placeholder="Ex.: 20"></label>
 <label>Idade<input id="med-age" inputmode="decimal" autocomplete="off" placeholder="Ex.: 5"></label><label>Unidade da idade<select id="med-age-unit"><option value="years">Anos</option><option value="months">Meses</option></select></label></div>
 <div id="med-reference-fields" hidden><label>Medicamento e indicação<select id="med-drug"><option value="">Selecione a referência</option><option value="paracetamol">Paracetamol — dor leve / febre — oral</option><option value="ibuprofen">Ibuprofeno — dor / febre — oral</option><option value="cetirizine">Cetirizina — sintomas alérgicos — oral</option></select></label>
 <div id="med-source" class="med-source"></div>
 <label id="med-choice-label" hidden>Dose a conferir (selecione conforme a prescrição)<select id="med-choice"></select></label>
 <label class="med-check"><input type="checkbox" id="med-special"> Há gestação, lactação, doença renal/hepática, desnutrição, desidratação, alergia, sangramento, dengue, fragilidade ou interação/condição que exija ajuste.</label>
 <label class="med-check"><input type="checkbox" id="med-reviewed"> Conferi a indicação, a via oral, as precauções e os demais medicamentos em uso. O caso está no escopo desta referência.</label>
 </div>
 <div id="med-manual-fields"><div class="med-grid"><label>Dose prescrita<input id="med-dose" inputmode="decimal" autocomplete="off" placeholder="Ex.: 15"></label><label>Unidade<select id="med-unit"><option value="mg-kg-dose">mg/kg/dose</option><option value="mg-kg-day">mg/kg/dia — total em 24 h</option><option value="mg-dose">mg/dose</option></select></label></div>
 <p class="meta">O modo prescrito verifica a aritmética; não verifica indicação, contraindicações ou limites clínicos do medicamento.</p></div>
 <label id="med-frequency-label">Tomadas em 24 horas<select id="med-frequency"><option value="">Selecione</option><option value="1">1 — a cada 24 h</option><option value="2">2 — a cada 12 h</option><option value="3">3 — a cada 8 h</option><option value="4">4 — a cada 6 h</option><option value="6">6 — a cada 4 h</option></select></label>
 <fieldset><legend>Concentração do rótulo — opcional para obter mL</legend><p class="meta">Preencha os dois campos conforme a apresentação em uso. Não presumimos concentração nem fator de gotas.</p><div class="med-grid"><label>Quantidade (mg)<input id="med-strength" inputmode="decimal" autocomplete="off" placeholder="Ex.: 120"></label><label>Em qual volume (mL)?<input id="med-volume" inputmode="decimal" autocomplete="off" placeholder="Ex.: 5"></label></div></fieldset>
 <div class="med-actions"><button type="submit">Calcular e conferir →</button><button type="reset">Limpar</button></div>
 </form><aside class="med-result" aria-live="polite" aria-atomic="true"><h2>Conferência do cálculo</h2><div id="med-result">Preencha os dados e selecione Calcular. Nenhum dado de paciente é gravado.</div></aside></div>
 <details class="med-sources"><summary>Fontes, datas e escopo do cadastro</summary><div id="med-all-sources"></div><p class="meta">Regras de implementação: menores de 1 mês ficam fora das referências; paracetamol em adultos abaixo de 50 kg requer prescrição individualizada. Em pediatria, o teto adulto funciona como limite adicional conservador. Se excedido, o cálculo é bloqueado, sem ajuste automático. Cetirizina segue o esquema NHS, que pode diferir de outras diretrizes. Não há atualização automática: o cadastro é uma fotografia da consulta indicada. Fontes internacionais não substituem a bula aprovada pela Anvisa.</p></details>`;
 main.append(panel);
 const $=id=>panel.querySelector('#med-'+id), fmt=n=>n.toLocaleString('pt-BR',{maximumFractionDigits:6});
 function sourceHtml(s){return `<h2>${s.indication}</h2><p>${s.summary}</p><p class="med-caution">${s.cautions}</p><p><a href="${s.url}" target="_blank" rel="noopener noreferrer">${s.name} ↗</a></p><p class="meta">${s.dateKind}: ${s.updated||'não informada na página consultada'}. Consulta: 03/11/2026.</p>`;}
 $('all-sources').innerHTML=Object.values(core.sources).map(s=>'<article>'+sourceHtml(s)+'</article>').join('');
 function update(){
  $('result').textContent='Dados alterados. Calcule novamente para conferir.';
  const ref=$('mode').value==='reference',id=$('drug').value;
  $('reference-fields').hidden=!ref;$('manual-fields').hidden=ref;
  $('source').innerHTML=ref&&core.sources[id]?sourceHtml(core.sources[id]):'';
  $('choice-label').hidden=!ref||id!=='ibuprofen';
  let age=Number($('age').value.replace(',','.'))*($('age-unit').value==='years'?12:1);
  const adultIbu=Number.isFinite(age)&&age>=144;
  const options=adultIbu?'<option value="">Selecione</option><option value="200">200 mg/dose</option><option value="400">400 mg/dose</option>':'<option value="">Selecione</option><option value="5">5 mg/kg/dose</option><option value="10">10 mg/kg/dose</option>';
  if($('choice').dataset.band!==String(adultIbu)){$('choice').innerHTML=options;$('choice').dataset.band=String(adultIbu);}
  $('frequency-label').hidden=ref&&id==='cetirizine';
 }
 open.onclick=()=>{library.hidden=true;panel.hidden=false;nav.querySelectorAll('[aria-pressed]').forEach(b=>b.setAttribute('aria-pressed',String(b===open)));panel.querySelector('h1').focus();};
 nav.querySelectorAll('[data-nav],[data-category]').forEach(b=>b.addEventListener('click',()=>{panel.hidden=true;library.hidden=false;open.setAttribute('aria-pressed','false');}));
 $('form').addEventListener('input',update);$('form').addEventListener('change',update);
 $('form').addEventListener('reset',()=>{setTimeout(()=>{update();$('result').textContent='Campos limpos. Nenhum dado de paciente é gravado.';},0);});
 $('form').onsubmit=e=>{
  e.preventDefault();$('result').replaceChildren();
  try{
   const age=core.number($('age').value,'idade',true)*($('age-unit').value==='years'?12:1);
   const weight=core.number($('weight').value,'peso em kg');
   if(age>1440) throw Error('Confira a idade: o limite de entrada é 120 anos.');
   if(($('pop').value==='adult')!==(age>=216)) throw Error('A idade não corresponde à população selecionada.');
   let p={dose:$('dose').value,unit:$('unit').value,weight,frequency:$('frequency').value,strength:$('strength').value,volume:$('volume').value},r=null;
   if($('mode').value==='reference'){
    if(!$('reviewed').checked) throw Error('Confira o escopo e as precauções da referência antes de calcular.');
    r=core.reference($('drug').value,age,weight,$('choice').value,$('frequency').value,$('special').checked);
    p={...p,dose:r.dose,unit:r.unit,frequency:r.frequency};
   }
   const out=core.calculate(p),box=$('result');
   function line(text,cls){const el=document.createElement('p');el.textContent=text;if(cls)el.className=cls;box.append(el);}
   line(fmt(out.mg)+' mg por tomada','med-big');line(fmt(out.daily)+' mg em 24 horas');line(out.frequency+' tomada(s) em 24 horas — intervalo regular de '+fmt(24/out.frequency)+' h.');
   if(out.ml!==null){line(fmt(out.ml)+' mL por tomada','med-big');line('Concentração: '+p.strength+' mg ÷ '+p.volume+' mL = '+fmt(out.concentration)+' mg/mL.');line('Volume: '+fmt(out.mg)+' mg ÷ '+fmt(out.concentration)+' mg/mL.');line('mL exibidos com até 6 casas; não arredondados à seringa. Confira a graduação e a viabilidade da medida.');}
   else line('Sem concentração: volume em mL não calculado.');
   line(p.unit==='mg-kg-day'?'Fórmula: dose em mg/kg/dia × peso em kg ÷ tomadas/dia.':p.unit==='mg-kg-dose'?'Fórmula: dose em mg/kg/dose × peso em kg.':'Fórmula: dose prescrita em mg por tomada.');
   if(r){line('Dentro dos limites aritméticos deste cadastro: '+fmt(r.maxDose)+' mg/dose e '+fmt(r.maxDay)+' mg/24 h. Isso não confirma adequação clínica.');const d=document.createElement('div');d.className='med-source';d.innerHTML=sourceHtml(r.source);box.append(d);}
   else line('Limites clínicos não verificados. Dose e frequência são os valores informados pelo usuário.','med-caution');
  }catch(err){const p=document.createElement('p');p.className='med-error';p.textContent=err.message;$('result').append(p);}
 };
 update();$('result').textContent='Preencha os dados e selecione Calcular. Nenhum dado de paciente é gravado.';
})();
