(function (root) {
 'use strict';
 const sources = {
  paracetamol: {name:'MSF — Essential drugs',url:'https://medicalguidelines.msf.org/en/viewport/EssDr/english/paracetamol-acetaminophen-oral-16684400.html',updated:'Outubro de 2024',dateKind:'Última atualização declarada',consulted:'2026-11-03',indication:'Dor leve ou febre; via oral',summary:'A partir de 1 mês: 15 mg/kg por dose, 3–4 tomadas/dia; máximo 60 mg/kg/dia. Adultos: 1.000 mg por dose, 3–4 tomadas/dia; máximo 4.000 mg/dia.',cautions:'Hepatopatia, desnutrição aguda grave e dengue com sinais de alarme exigem avaliação e esquemas específicos. Somar paracetamol de todos os produtos. Superdose pode causar lesão hepática grave.'},
  ibuprofen: {name:'MSF — Essential drugs',url:'https://medicalguidelines.msf.org/en/viewport/EssDr/english/ibuprofen-oral-16683877.html',updated:null,dateKind:'Atualização da monografia',consulted:'2026-11-03',indication:'Dor leve a moderada ou febre; via oral (exclui doenças reumáticas)',summary:'Crianças acima de 3 meses e menores de 12 anos: 5–10 mg/kg por dose, 3–4 tomadas/dia; máximo 30 mg/kg/dia. A partir de 12 anos: 200–400 mg por dose, 3–4 tomadas/dia; máximo 1.200 mg/dia.',cautions:'Não usar em alergia a AINE, úlcera, sangramento, distúrbio de coagulação, insuficiência renal/hepática grave, insuficiência cardíaca grave, desnutrição, desidratação/hipovolemia ou infecção grave. Evitar na gestação; contraindicado a partir do 6º mês. Interações relevantes: anticoagulantes, metotrexato, outros AINE, diuréticos e IECA. Cautela em idosos e asmáticos.'},
  cetirizine: {name:'NHS — Medicines',url:'https://www.nhs.uk/medicines/cetirizine/how-and-when-to-take-cetirizine/',updated:'18/02/2025',dateKind:'Última revisão declarada',consulted:'2026-11-03',indication:'Sintomas alérgicos, como rinite e urticária; via oral',summary:'De 2 a menos de 6 anos: 2,5 mg duas vezes/dia. De 6 a menos de 12 anos: 5 mg duas vezes/dia. A partir de 12 anos: 10 mg uma vez/dia.',cautions:'Doença renal pode exigir redução da dose. Menores de 2 anos ficam fora deste módulo. Alergia ao medicamento e condições especiais exigem avaliação. A frequência pediátrica segue especificamente o NHS; não combinar esquemas de fontes diferentes.'}
 };
 function number(value, label, zero=false) {
  const s=String(value ?? '').trim();
  if(!/^(?:\d+(?:[.,]\d+)?|[.,]\d+)$/.test(s)) throw Error('Informe '+label+' com número válido, sem separador de milhar.');
  const n=Number(s.replace(',','.'));
  if(!Number.isFinite(n)||(zero?n<0:n<=0)) throw Error(label+' deve ser '+(zero?'zero ou maior.':'maior que zero.'));
  return n;
 }
 function calculate(p) {
  const frequency=number(p.frequency,'tomadas em 24 horas');
  if(!Number.isInteger(frequency)||frequency>24) throw Error('Informe de 1 a 24 tomadas inteiras em 24 horas.');
  const dose=number(p.dose,'dose prescrita');
  const units=['mg-dose','mg-kg-dose','mg-kg-day'];
  if(!units.includes(p.unit)) throw Error('Unidade de dose inválida.');
  const weight=p.unit==='mg-dose'?null:number(p.weight,'peso em kg');
  let mg=p.unit==='mg-dose'?dose:dose*weight/(p.unit==='mg-kg-day'?frequency:1);
  const daily=mg*frequency;
  if(!Number.isFinite(daily)||daily<=0) throw Error('Resultado fora do intervalo numérico.');
  let concentration=null,ml=null;
  if(String(p.strength??'').trim()||String(p.volume??'').trim()) {
   concentration=number(p.strength,'quantidade do rótulo em mg')/number(p.volume,'volume do rótulo em mL');
   ml=mg/concentration;
   if(!Number.isFinite(concentration)||concentration<=0||!Number.isFinite(ml)||ml<=0) throw Error('Concentração ou volume fora do intervalo numérico.');
  }
  return {mg,daily,ml,concentration,frequency,weight};
 }
 function reference(id, ageMonths, weight, choice, frequency, special) {
  if(!sources[id]) throw Error('Escolha um medicamento cadastrado.');
  if(special) throw Error('Condições especiais: esta referência não fornece ajuste individualizado. Solicite revisão clínica da prescrição.');
  const age=number(ageMonths,'idade em meses',true), w=number(weight,'peso em kg');
  if(age>1440) throw Error('Confira a idade informada.');
  let dose,unit,freq=Number(frequency),maxDose,maxDay;
  if(id==='paracetamol') {
   if(age<1) throw Error('Neonatos estão fora do escopo desta versão.');
   if(age>=216&&w<50) throw Error('Adultos abaixo de 50 kg exigem prescrição individualizada fora desta referência.');
   dose=age>=216?1000:15; unit=age>=216?'mg-dose':'mg-kg-dose';
   maxDose=1000; maxDay=age>=216?4000:Math.min(60*w,4000);
   if(![3,4].includes(freq)) throw Error('A referência permite 3 ou 4 tomadas em 24 horas.');
  } else if(id==='ibuprofen') {
   if(age<=3) throw Error('Esta referência abrange somente crianças acima de 3 meses.');
   const older=age>=144;
   dose=number(choice,'dose selecionada'); unit=older?'mg-dose':'mg-kg-dose';
   if(!(older?[200,400]:[5,10]).includes(dose)) throw Error('Selecione uma das doses cadastradas para a idade.');
   maxDose=older?400:400; maxDay=older?1200:Math.min(30*w,1200);
   if(![3,4].includes(freq)) throw Error('A referência permite 3 ou 4 tomadas em 24 horas.');
  } else {
   if(age<24) throw Error('Cetirizina: menores de 2 anos estão fora deste módulo.');
   dose=age<72?2.5:age<144?5:10;unit='mg-dose';freq=age<144?2:1;
   maxDose=dose;maxDay=dose*freq;
  }
  const result=calculate({dose,unit,weight:w,frequency:freq});
  if(result.mg>maxDose+1e-9||result.daily>maxDay+1e-9) throw Error('Esquema excede o limite desta referência ('+maxDose+' mg/dose; '+maxDay+' mg/24 h). Revise dose/frequência. Nenhuma dose foi reduzida automaticamente.');
  return {dose,unit,frequency:freq,maxDose,maxDay,source:sources[id]};
 }
 const api={sources,number,calculate,reference};
 if(typeof module==='object'&&module.exports) module.exports=api;
 else root.AegisMedication=api;
})(globalThis);
