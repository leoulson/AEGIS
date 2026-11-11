(()=>{
 'use strict';
 const data=globalThis.AegisCatalog,root=document.getElementById('aegis-library');
 if(!data||!root)return;
 const sources=new Map(data.sources.map(s=>[s.id,s])),areas=new Map(data.areas.map(a=>[a.id,a.title]));
 const states={draft:'Rascunho',pending_professional_review:'Pendente de revisão profissional',reviewed:'Revisado'};
 const sectionNames={initial_assessment:'Avaliação inicial',red_flags:'Sinais de alerta',source_based_actions:'Condutas fundamentadas nas fontes',limits_and_referral:'Limites, exceções e encaminhamento',follow_up:'Acompanhamento',evidence_context:'Evidência complementar e aplicabilidade'};
 const kinds={synthesis:'Síntese AEGIS',editorial:'Observação editorial',quotation:'Texto original citado'};
 const saved=new Set();let category='all',view='all',editorial=false;
 const list=root.querySelector('#aegis-books'),search=root.querySelector('#aegis-search'),detail=root.querySelector('#aegis-detail'),nav=root.querySelector('nav');
 const mode=root.querySelector('#catalog-editorial'),stateFilter=root.querySelector('#catalog-state');
 const norm=s=>s.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
 function el(tag,text,cls){const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(cls)node.className=cls;return node;}
 function button(text,handler){const b=el('button',text);b.type='button';b.onclick=handler;return b;}
 function https(url){try{const u=new URL(url);return u.protocol==='https:'&&!u.username&&!u.password?u.href:null;}catch{return null;}}
 function sourceBlock(source){
  const block=el('article',undefined,'catalog-source');block.append(el('h3',source.title),el('p',source.citation),el('p','Edição/versão: '+source.edition),el('p','Consulta documental: '+source.consulted_on+' — não é revisão clínica.'));
  const url=https(source.url);if(url){const link=el('a','Referência externa (requer internet)');link.href=url;link.target='_blank';link.rel='noopener noreferrer';block.append(link);}
  block.append(el('p','Avaliação crítica: '+source.appraisal),el('p','Direitos: '+source.reproduction.terms),el('p',source.reproduction.evidence));
  const ul=el('ul');for(const pending of source.pending)ul.append(el('li',pending));block.append(ul);return block;
 }
 function counts(){
  const reviewed=data.cards.filter(c=>c.editorial.state==='reviewed').length;
  root.querySelector('#catalog-counts').textContent=reviewed+' fichas revisadas para consulta · '+(data.cards.length-reviewed)+' fichas na oficina editorial · '+data.sources.length+' referências documentais.';
 }
 function selectArea(id){category=id;view='all';detail.hidden=true;render();}
 const planned=el('ul');
 for(const area of data.areas){
  const total=data.cards.filter(c=>c.category===area.id).length;
  if(total){const b=button(area.title+' ('+total+' na oficina)',()=>selectArea(area.id));b.dataset.category=area.id;b.setAttribute('aria-pressed','false');nav.insertBefore(b,nav.querySelector('.aside-note'));}
  else planned.append(el('li',area.title+' — planejada, sem ficha disponível.'));
 }
 root.querySelector('#catalog-planned').append(planned);
 const filters=root.querySelector('.filters');filters.replaceChildren();
 const all=button('Todas as áreas',()=>selectArea('all'));all.dataset.category='all';filters.append(all);
 for(const area of data.areas){const total=data.cards.filter(c=>c.category===area.id).length;if(total){const b=button(area.title,()=>selectArea(area.id));b.dataset.category=area.id;filters.append(b);}}
 function render(){
  counts();
  root.querySelectorAll('[data-nav]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.nav===view)));
  root.querySelectorAll('[data-category]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.category===category)));
  root.querySelector('#catalog-mode').textContent=editorial?'Oficina editorial — fichas não liberadas para consulta assistencial.':'Consulta assistencial — apenas fichas com revisão profissional documentada.';
  root.querySelector('#catalog-mode').classList.toggle('catalog-warning',editorial);
  stateFilter.disabled=!editorial;
  root.querySelector('#aegis-list-title').textContent=view==='saved'?'Salvos nesta sessão':view==='sources'?'Fontes, versões e direitos':view==='policy'?'Política editorial':editorial?'Fichas para avaliação editorial':'Fichas revisadas';
  list.replaceChildren();root.querySelector('#catalog-results').textContent='';
  if(view==='sources'){for(const source of data.sources)list.append(sourceBlock(source));return;}
  if(view==='policy'){for(const section of data.policy.sections){const article=el('article',undefined,'catalog-source');article.append(el('h3',section.title),el('p',section.text));list.append(article);}return;}
  const rows=data.cards.filter(c=>(editorial||c.editorial.state==='reviewed')&&(stateFilter.value==='all'||c.editorial.state===stateFilter.value)&&(category==='all'||c.category===category)&&(view!=='saved'||saved.has(c.id))&&c.search_text.includes(norm(search.value)));
  root.querySelector('#catalog-results').textContent=rows.length+' resultado(s) nesta seleção.';
  for(const card of rows){
   const item=el('article',undefined,'book');item.append(el('div',card.title.slice(0,1),'cover'));
   const box=el('div');box.append(el('h3',card.title,'book-name'),el('p',areas.get(card.category),'meta'),el('p',states[card.editorial.state],'catalog-state'),el('p',card.summary));
   box.append(button(editorial?'Ler ficha pendente →':'Ler ficha →',()=>openCard(card)));item.append(box);list.append(item);
  }
  if(!rows.length){list.append(el('p',editorial?'Nenhuma ficha corresponde aos filtros. Ajuste a busca ou a área.':'Nenhuma ficha revisada está disponível neste conjunto. Os materiais iniciais estão separados na oficina editorial, pendentes de revisão profissional.','empty'));}
 }
 function openCard(card){
  const trigger=document.activeElement;detail.hidden=false;detail.replaceChildren();
  const heading=el('h2',card.title);heading.tabIndex=-1;
  detail.append(el('p',states[card.editorial.state],'catalog-state'),heading);
  if(card.editorial.state!=='reviewed')detail.append(el('p','Leitura editorial. Esta ficha não está liberada para consulta assistencial.','catalog-warning'));
  for(const [name,value]of [['Resumo',card.summary],['Área',areas.get(card.category)],['Público',card.audience],['População',card.population],['Contexto',card.context],['Objetivo',card.objective]])detail.append(el('p',name+': '+value));
  detail.append(el('p','Consulta documental: '+card.editorial.source_consulted_on),el('p','Revisão clínica: '+(card.editorial.state==='reviewed'?card.editorial.reviewer+' — '+card.editorial.reviewed_on:'não realizada/documentada.')),el('p',card.editorial.provenance));
  const used=new Set();
  for(const [key,title]of Object.entries(sectionNames)){
   if(!card.sections[key].length)continue;
   detail.append(el('h3',title));
   for(const point of card.sections[key]){detail.append(el('p',kinds[point.kind]+': '+point.text));for(const cite of point.citations){used.add(cite.source_id);detail.append(el('p','['+cite.source_id+'] '+sources.get(cite.source_id).title+' — '+cite.locator,'meta'));}}
  }
  detail.append(el('h3','Pendências editoriais'));const notes=el('ul');for(const note of card.editorial.notes)notes.append(el('li',note));detail.append(notes,el('h3','Referências completas e condições de reprodução'));
  for(const id of used)detail.append(sourceBlock(sources.get(id)));
  detail.append(el('p','Texto da ficha: '+card.rights.text_license+' — '+card.rights.terms));
  const save=button(saved.has(card.id)?'Remover dos salvos':'Salvar referência',()=>{if(saved.has(card.id))saved.delete(card.id);else saved.add(card.id);save.textContent=saved.has(card.id)?'Remover dos salvos':'Salvar referência';render();});
  const close=button('Fechar ficha',()=>{detail.hidden=true;if(trigger?.isConnected)trigger.focus();else root.querySelector('[data-nav="all"]').focus();});detail.append(save,close);heading.focus();
 }
 root.querySelectorAll('[data-nav]').forEach(b=>b.onclick=()=>{view=b.dataset.nav;category='all';search.value='';detail.hidden=true;render();});
 search.oninput=()=>{view='all';detail.hidden=true;render();};
 mode.onchange=()=>{editorial=mode.checked;stateFilter.value=editorial?'all':'reviewed';detail.hidden=true;render();};
 stateFilter.onchange=()=>{detail.hidden=true;render();};
 root.querySelector('#catalog-open-editorial').onclick=()=>{editorial=true;mode.checked=true;stateFilter.value='pending_professional_review';view='all';detail.hidden=true;render();root.querySelector('#aegis-list-title').focus();};
 root.querySelector('#catalog-presentation').textContent=data.presentation;
 root.querySelector('#catalog-tagline').textContent=data.tagline;
 root.querySelector('#catalog-notice').textContent=data.notice;
 // This is ordinary local full-text navigation, not a generative assistant.
 function ask(text){search.value=text;view='all';detail.hidden=true;render();root.querySelector('#aegis-answer').textContent=editorial?'Busca textual local na oficina editorial. Resultados pendentes não são recomendações assistenciais.':'Busca textual local somente nas fichas revisadas. Explore a oficina editorial separadamente para avaliar os materiais pendentes.';}
 root.querySelectorAll('[data-prompt]').forEach(b=>b.onclick=()=>ask(b.dataset.prompt));
 root.querySelector('form.composer').onsubmit=e=>{e.preventDefault();const input=e.currentTarget.querySelector('input');ask(input.value.trim());};
 render();
})();
