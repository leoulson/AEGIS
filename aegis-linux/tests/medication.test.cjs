const {test}=require('node:test');
const a=require('node:assert/strict');
const c=require('../app/medication-core');
test('mg/kg/dose e concentração mg/5mL',()=>{
 const r=c.calculate({dose:'15',unit:'mg-kg-dose',weight:'20',frequency:'4',strength:'120',volume:'5'});
 a.equal(r.mg,300);a.equal(r.daily,1200);a.equal(r.ml,12.5);
});
test('mg/kg/dia é dividido entre tomadas, vírgula decimal aceita',()=>{
 const r=c.calculate({dose:'30',unit:'mg-kg-day',weight:'12,5',frequency:'3',strength:'100',volume:'5'});
 a.equal(r.mg,125);a.equal(r.daily,375);a.equal(r.ml,6.25);
});
test('mg/dose não multiplica pelo peso',()=>a.equal(c.calculate({dose:500,unit:'mg-dose',weight:70,frequency:3}).daily,1500));
test('dados vazios, zero, notação ambígua e fração de tomada bloqueados',()=>{
 for(const v of ['',0,-1,'1.000,5','1e3','NaN','Infinity'])a.throws(()=>c.number(v,'dose'));
 for(const f of ['1,5',0,25])a.throws(()=>c.calculate({dose:5,unit:'mg-dose',frequency:f}));
 a.throws(()=>c.calculate({dose:5,unit:'mcg-dose',frequency:1}));
 a.throws(()=>c.calculate({dose:5,unit:'mg-dose',frequency:1,strength:100,volume:0}));
 a.throws(()=>c.calculate({dose:5,unit:'mg-dose',frequency:1,strength:100}));
});
test('paracetamol: máximo diário pediátrico, adulto e limites de escopo',()=>{
 a.equal(c.reference('paracetamol',60,20,null,4,false).maxDay,1200);
 a.equal(c.reference('paracetamol',216,70,null,4,false).dose,1000);
 a.throws(()=>c.reference('paracetamol',0.9,3,null,3,false));
 a.throws(()=>c.reference('paracetamol',216,49,null,3,false));
 a.throws(()=>c.reference('paracetamol',60,20,null,6,false));
 a.throws(()=>c.reference('paracetamol',180,70,null,3,false));
});
test('ibuprofeno: não permitir 10 mg/kg 4x/dia; 5mg/kg 4x/dia permitido',()=>{
 a.throws(()=>c.reference('ibuprofen',60,20,10,4,false));
 a.equal(c.reference('ibuprofen',60,20,5,4,false).maxDay,600);
 a.throws(()=>c.reference('ibuprofen',3,5,5,3,false));
 a.equal(c.reference('ibuprofen',3.1,5,5,3,false).dose,5);
 a.throws(()=>c.reference('ibuprofen',144,40,400,4,false));
 a.equal(c.reference('ibuprofen',144,40,400,3,false).maxDay,1200);
});
test('cetirizina: fronteiras etárias NHS e bloqueio de condições especiais',()=>{
 a.throws(()=>c.reference('cetirizine',23.9,12,null,1,false));
 for(const [age,dose,freq] of [[24,2.5,2],[71.9,2.5,2],[72,5,2],[143.9,5,2],[144,10,1],[216,10,1]]){
  const r=c.reference('cetirizine',age,30,null,4,false);a.equal(r.dose,dose);a.equal(r.frequency,freq);
 }
 for(const id of Object.keys(c.sources))a.throws(()=>c.reference(id,240,70,200,3,true));
});
test('todas as referências têm fonte e data de consulta; atualização desconhecida não inventada',()=>{
 for(const s of Object.values(c.sources)){a.match(s.url,/^https:/);a.equal(s.consulted,'2026-11-03');a.ok(s.indication);}
 a.equal(c.sources.ibuprofen.updated,null);
});
