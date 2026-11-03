/* Lucide icons: ISC license; see LICENSE-lucide. Only icons used by AEGIS. */
(()=>{
  const icons={"hard-drive":[["path",{"d":"M10 16h.01"}],["path",{"d":"M2.212 11.577a2 2 0 0 0-.212.896V18a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-5.527a2 2 0 0 0-.212-.896L18.55 5.11A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"}],["path",{"d":"M21.946 12.013H2.054"}],["path",{"d":"M6 16h.01"}]],"library":[["path",{"d":"m16 6 4 14"}],["path",{"d":"M12 6v14"}],["path",{"d":"M8 8v12"}],["path",{"d":"M4 4v16"}]],"bookmark":[["path",{"d":"M17 3a2 2 0 0 1 2 2v15a1 1 0 0 1-1.496.868l-4.512-2.578a2 2 0 0 0-1.984 0l-4.512 2.578A1 1 0 0 1 5 20V5a2 2 0 0 1 2-2z"}]],"file-check-2":[["path",{"d":"M10.5 22H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.706.706l3.588 3.588A2.4 2.4 0 0 1 20 8v6"}],["path",{"d":"M14 2v5a1 1 0 0 0 1 1h5"}],["path",{"d":"m14 20 2 2 4-4"}]],"search":[["path",{"d":"m21 21-4.34-4.34"}],["circle",{"cx":"11","cy":"11","r":"8"}]],"sparkles":[["path",{"d":"M11.017 2.814a1 1 0 0 1 1.966 0l1.051 5.558a2 2 0 0 0 1.594 1.594l5.558 1.051a1 1 0 0 1 0 1.966l-5.558 1.051a2 2 0 0 0-1.594 1.594l-1.051 5.558a1 1 0 0 1-1.966 0l-1.051-5.558a2 2 0 0 0-1.594-1.594l-5.558-1.051a1 1 0 0 1 0-1.966l5.558-1.051a2 2 0 0 0 1.594-1.594z"}],["path",{"d":"M20 2v4"}],["path",{"d":"M22 4h-4"}],["circle",{"cx":"4","cy":"20","r":"2"}]],"arrow-up-right":[["path",{"d":"M7 7h10v10"}],["path",{"d":"M7 17 17 7"}]],"arrow-up":[["path",{"d":"m5 12 7-7 7 7"}],["path",{"d":"M12 19V5"}]]};
  const ns='http://www.w3.org/2000/svg';
  document.querySelectorAll('[data-lucide]').forEach(element=>{
    const nodes=icons[element.getAttribute('data-lucide')];
    if(!nodes)return;
    const svg=document.createElementNS(ns,'svg');
    for(const [key,value] of Object.entries({width:17,height:17,viewBox:'0 0 24 24',fill:'none',stroke:'currentColor','stroke-width':2,'stroke-linecap':'round','stroke-linejoin':'round','aria-hidden':'true'}))svg.setAttribute(key,value);
    for(const [tag,attrs] of nodes){const child=document.createElementNS(ns,tag);for(const [key,value] of Object.entries(attrs))child.setAttribute(key,value);svg.append(child);}
    element.replaceWith(svg);
  });
})();
