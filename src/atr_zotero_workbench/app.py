import argparse
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .core import load_legacy_run, project_graph
from .human_input import impact_report, refresh_review_queue
from .history import archive_previous_projection
from .zotero import export_bundle, sync_web_api


# The graph is embedded at build time so the page works in Zotero's file:// tab
# without relying on fetch() permissions.
HTML = r'''<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8"><title>ATR Research Workbench</title>
<style>
:root{--ink:#172033;--muted:#64748b;--line:#d9e2ec;--paper:#276fbf;--question:#bc5b12;--concept:#7858a6;--bg:#f5f7fb}
*{box-sizing:border-box}body{margin:0;font:14px system-ui,-apple-system,sans-serif;color:var(--ink);background:var(--bg)}
header{padding:16px 24px;background:#122a43;color:#fff;display:flex;justify-content:space-between;gap:16px;align-items:center}header b{font-size:17px}header span{color:#c7d6e6}
main{display:grid;grid-template-columns:minmax(520px,1fr) 360px;height:calc(100vh - 61px)}section{padding:18px 22px;overflow:auto}aside{padding:20px;overflow:auto;border-left:1px solid var(--line);background:#fff}
.metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-bottom:16px}.metric,.card{background:#fff;border:1px solid var(--line);border-radius:10px;padding:14px}.metric b{display:block;font-size:24px}.metric span{color:var(--muted);font-size:12px}
.tabs{display:flex;gap:8px;margin-bottom:16px}.tabs button{border:1px solid var(--line);border-radius:18px;padding:7px 12px;background:#fff;color:var(--ink);cursor:pointer}.tabs button.active{background:#122a43;border-color:#122a43;color:#fff}
#map{width:100%;min-height:390px;background:#fff;border:1px solid var(--line);border-radius:10px}.edge{stroke:#b9c6d2;stroke-width:1.3}.node{cursor:pointer;stroke:#fff;stroke-width:2}.run{fill:#374151}.concept{fill:var(--concept)}.research_question{fill:var(--question)}
.legend{color:var(--muted);margin:10px 0}.legend i{display:inline-block;width:10px;height:10px;border-radius:50%;margin:0 4px 0 12px}.paper-dot{background:var(--paper)}.question-dot{background:var(--question)}.concept-dot{background:var(--concept)}
.paper{width:100%;text-align:left;margin:0 0 8px;padding:12px;border:1px solid var(--line);border-radius:8px;background:#fff;cursor:pointer;color:var(--ink)}.paper:hover{border-color:#7aa7d7}.paper strong{display:block}.paper small{color:var(--muted)}
.tag{display:inline-block;border-radius:12px;padding:3px 8px;margin:2px;background:#edf2f7;color:#425466;font-size:12px}h2{margin:0 0 10px;font-size:19px}h3{font-size:13px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;margin:18px 0 5px}p{line-height:1.5}.empty{color:var(--muted);padding:22px}.warning{background:#fff7e6;border:1px solid #f0c36d;border-radius:8px;padding:10px;margin-top:12px}
@media(max-width:800px){main{grid-template-columns:1fr;height:auto;min-height:calc(100vh - 61px)}aside{border-left:0;border-top:1px solid var(--line)}.metrics{grid-template-columns:1fr}.tabs{flex-wrap:wrap}}
</style></head><body>
<header><b>ATR × Zotero Research Workbench</b><span id="meta"></span></header>
<main><section><div class="metrics" id="metrics"></div><div class="tabs"><button class="active" data-view="questions">研究问题地图</button><button data-view="knowledge">知识体系</button><button data-view="papers">来源与证据边界</button></div><div id="view"></div></section><aside id="detail"><h2>从研究问题开始</h2><p>默认视图只显示研究问题、其所需概念与锚定文献，避免把全部证据节点挤成一团。</p></aside></main>
<script>
const data=__GRAPH_DATA__;
const by=Object.fromEntries(data.nodes.map(n=>[n.id,n]));
const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const short=(s,n=34)=>String(s??'').length>n?String(s).slice(0,n-1)+'…':String(s??'');
function edgesFor(id){return data.edges.filter(e=>e.source===id||e.target===id)}
function show(n){let d=n.data||{},related=edgesFor(n.id).map(e=>by[e.source===n.id?e.target:e.source]).filter(Boolean);let html='<h2>'+esc(n.label)+'</h2><span class="tag">'+esc(n.kind)+'</span>';
 for(const [k,v] of Object.entries(d)){html+='<h3>'+esc(k.replaceAll('_',' '))+'</h3><p>'+esc(Array.isArray(v)?v.join('\n'):v).replaceAll('\n','<br>')+'</p>'}
 if(related.length)html+='<h3>直接连接</h3>'+related.map(x=>'<span class="tag">'+esc(short(x.label,28))+'</span>').join('');$('#detail').innerHTML=html}
function button(n){let b=document.createElement('button');b.className='paper';b.innerHTML='<strong>'+esc(n.label)+'</strong><small>'+esc(n.data.source_layer||n.data.source_kind||n.kind)+' · '+esc(n.data.source_id||'')+'</small>';b.onclick=()=>show(n);return b}
function renderMetrics(){let counts=data.nodes.reduce((a,n)=>(a[n.kind]=(a[n.kind]||0)+1,a),{}), scholarly=data.nodes.filter(n=>n.kind==='paper'&&n.data.source_layer==='scholarly_evidence').length, contextual=data.nodes.filter(n=>n.kind==='paper'&&n.data.source_layer==='contextual_inspiration').length;$('#meta').textContent=data.run+' · 派生只读投影';$('#metrics').innerHTML=`<div class="metric"><b>${counts.research_question||0}</b><span>待验证的研究问题</span></div><div class="metric"><b>${scholarly}</b><span>学术证据来源</span></div><div class="metric"><b>${contextual}</b><span>现实世界灵感来源</span></div>`}
function renderQuestions(){let qs=data.nodes.filter(n=>n.kind==='research_question'), ids=new Set(['concept:domain',...qs.map(n=>n.id)]);for(const e of data.edges)if(qs.some(q=>q.id===e.source)&&by[e.target]?.kind==='concept')ids.add(e.target);let nodes=[...ids].map(id=>by[id]).filter(Boolean);let svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.id='map';svg.setAttribute('viewBox','0 0 900 470');let pos={};let domain=by['concept:domain'];if(domain)pos[domain.id]=[450,92];qs.forEach((q,i)=>pos[q.id]=[260+i*(380/Math.max(qs.length-1,1)),220]);let concepts=nodes.filter(n=>n.kind==='concept'&&n.id!=='concept:domain');concepts.forEach((n,i)=>pos[n.id]=[95+(i%5)*178,365+Math.floor(i/5)*72]);let run=data.nodes.find(n=>n.kind==='run');if(run){nodes.unshift(run);pos[run.id]=[450,28]}
 for(const e of data.edges){if(!pos[e.source]||!pos[e.target])continue;let l=document.createElementNS(svg.namespaceURI,'line');l.setAttribute('x1',pos[e.source][0]);l.setAttribute('y1',pos[e.source][1]);l.setAttribute('x2',pos[e.target][0]);l.setAttribute('y2',pos[e.target][1]);l.setAttribute('class','edge');svg.append(l)}
 for(const n of nodes){let [x,y]=pos[n.id],g=document.createElementNS(svg.namespaceURI,'g'),c=document.createElementNS(svg.namespaceURI,'circle'),t=document.createElementNS(svg.namespaceURI,'text');c.setAttribute('cx',x);c.setAttribute('cy',y);c.setAttribute('r',n.kind==='research_question'?20:14);c.setAttribute('class','node '+n.kind);t.setAttribute('x',x);t.setAttribute('y',y+(n.kind==='research_question'?37:31));t.setAttribute('text-anchor','middle');t.setAttribute('font-size','12');t.textContent=short(n.label,30);g.append(c,t);g.onclick=()=>show(n);svg.append(g)}
 let wrap=document.createElement('div');wrap.innerHTML='<div class="legend"><i class="question-dot"></i>研究问题 <i class="concept-dot"></i>所需概念</div>';wrap.append(svg);if(data.diagnostics?.length){let d=document.createElement('div');d.className='warning';d.textContent='数据完整性提示：'+data.diagnostics.join('；');wrap.append(d)}$('#view').replaceChildren(wrap)}
function renderPapers(){let wrap=document.createElement('div');wrap.innerHTML='<p class="legend">选择一篇文献，可在右侧查看其支持范围与不支持的结论。证据边界不会作为独立节点堆叠显示。</p>';for(const n of data.nodes.filter(n=>n.kind==='paper'))wrap.append(button(n));$('#view').replaceChildren(wrap)}
function renderKnowledge(){let wrap=document.createElement('div'),domain=by['concept:domain'];wrap.append(Object.assign(document.createElement('h2'),{textContent:domain?.label||'知识体系'}));for(const q of data.nodes.filter(n=>n.kind==='research_question')){let box=document.createElement('div');box.className='card';let concepts=data.edges.filter(e=>e.source===q.id&&e.relation==='requires_concept').map(e=>by[e.target]).filter(Boolean),papers=data.edges.filter(e=>e.source===q.id&&e.relation==='anchored_by').map(e=>by[e.target]).filter(Boolean);box.innerHTML='<strong>'+esc(q.label)+'</strong><p class="legend">从前沿问题展开到需要理解的概念与锚定来源。</p><h3>所需概念</h3>'+concepts.map(n=>'<span class="tag">'+esc(n.label)+'</span>').join('')+'<h3>锚定来源</h3>';for(const p of papers)box.append(button(p));box.onclick=e=>{if(e.target===box||e.target.tagName==='STRONG')show(q)};wrap.append(box)}if(!data.nodes.some(n=>n.kind==='research_question'))wrap.innerHTML+='<p class="empty">该 run 尚未产生 frontier tensions，不能自动编造知识层级。</p>';$('#view').replaceChildren(wrap)}
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>{document.querySelectorAll('[data-view]').forEach(x=>x.classList.toggle('active',x===b));({questions:renderQuestions,knowledge:renderKnowledge,papers:renderPapers}[b.dataset.view])()});renderMetrics();renderQuestions();
</script></body></html>'''


def build(run_dir: Path, out: Path) -> dict:
    graph = project_graph(load_legacy_run(run_dir))
    out.mkdir(parents=True, exist_ok=True)
    graph["history"] = archive_previous_projection(out, graph)
    encoded = json.dumps(graph, ensure_ascii=False).replace("</", "<\\/")
    (out / "graph.json").write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "index.html").write_text(HTML.replace("__GRAPH_DATA__", encoded), encoding="utf-8")
    export_bundle(graph, out)
    return graph


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("run_dir", type=Path); b.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("serve"); s.add_argument("directory", type=Path); s.add_argument("--port", type=int, default=8765)
    y = sub.add_parser("sync"); y.add_argument("directory", type=Path)
    h = sub.add_parser("review-human-input"); h.add_argument("directory", type=Path); h.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    if a.cmd == "build": print(json.dumps({"built": str(a.out), "nodes": len(build(a.run_dir, a.out)["nodes"])}, ensure_ascii=False))
    elif a.cmd == "serve": ThreadingHTTPServer(("127.0.0.1", a.port), partial(SimpleHTTPRequestHandler, directory=a.directory)).serve_forever()
    elif a.cmd == "sync": print(json.dumps(sync_web_api(a.directory), ensure_ascii=False))
    else:
        report = impact_report(a.directory)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        queue = refresh_review_queue(a.directory)
        print(json.dumps({"written": str(a.out), "affected": len(report["affected"]), "new_queue_items": queue["new_items"]}, ensure_ascii=False))


if __name__ == "__main__": main()
