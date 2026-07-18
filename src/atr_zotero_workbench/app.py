import argparse
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

from .core import load_legacy_run, project_graph
from .human_input import impact_report, materialize_review_packets, refresh_review_queue
from .history import archive_previous_projection
from .programs import project_program
from .runs import register_run
from .zotero import export_bundle, sync_web_api


# The graph is embedded at build time so the page works in Zotero's file:// tab
# without relying on fetch() permissions.
HTML = r'''<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8"><title>ATR Research Workbench</title>
<style>
:root{--ink:#172033;--muted:#64748b;--line:#d9e2ec;--paper:#276fbf;--question:#bc5b12;--concept:#7858a6;--claim:#28796c;--bg:#f5f7fb}
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
<main><section><div class="metrics" id="metrics"></div><div class="tabs"><button class="active" data-view="questions">研究问题地图</button><button data-view="knowledge">知识体系</button><button data-view="evolution">知识与现实链路</button><button data-view="claims">待审查断言</button><button data-view="papers">来源与证据边界</button></div><div id="view"></div></section><aside id="detail"><h2>从研究问题开始</h2><p>默认视图只显示研究问题、其所需概念与锚定文献，避免把全部证据节点挤成一团。</p></aside></main>
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
function renderMetrics(){let counts=data.nodes.reduce((a,n)=>(a[n.kind]=(a[n.kind]||0)+1,a),{}), scholarly=data.nodes.filter(n=>n.kind==='paper'&&n.data.source_layer==='scholarly_evidence').length, contextual=data.nodes.filter(n=>n.kind==='paper'&&n.data.source_layer==='contextual_inspiration').length;$('#meta').textContent=data.run+' · 派生只读投影';$('#metrics').innerHTML=`<div class="metric"><b>${counts.research_question||0}</b><span>待验证的研究问题</span></div><div class="metric"><b>${counts.claim||0}</b><span>可审查断言</span></div><div class="metric"><b>${counts.knowledge_step||0}</b><span>知识收缩步骤</span></div><div class="metric"><b>${counts.real_world_tension||0}</b><span>现实世界张力</span></div><div class="metric"><b>${counts.research_problem||0}</b><span>问题卡</span></div><div class="metric"><b>${scholarly}</b><span>学术证据来源</span></div><div class="metric"><b>${contextual}</b><span>现实世界灵感来源</span></div>`}
function renderQuestions(){let qs=data.nodes.filter(n=>n.kind==='research_question'), ids=new Set(['concept:domain',...qs.map(n=>n.id)]);for(const e of data.edges)if(qs.some(q=>q.id===e.source)&&by[e.target]?.kind==='concept')ids.add(e.target);let nodes=[...ids].map(id=>by[id]).filter(Boolean);let svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.id='map';svg.setAttribute('viewBox','0 0 900 470');let pos={};let domain=by['concept:domain'];if(domain)pos[domain.id]=[450,92];qs.forEach((q,i)=>pos[q.id]=[260+i*(380/Math.max(qs.length-1,1)),220]);let concepts=nodes.filter(n=>n.kind==='concept'&&n.id!=='concept:domain');concepts.forEach((n,i)=>pos[n.id]=[95+(i%5)*178,365+Math.floor(i/5)*72]);let run=data.nodes.find(n=>n.kind==='run');if(run){nodes.unshift(run);pos[run.id]=[450,28]}
 for(const e of data.edges){if(!pos[e.source]||!pos[e.target])continue;let l=document.createElementNS(svg.namespaceURI,'line');l.setAttribute('x1',pos[e.source][0]);l.setAttribute('y1',pos[e.source][1]);l.setAttribute('x2',pos[e.target][0]);l.setAttribute('y2',pos[e.target][1]);l.setAttribute('class','edge');svg.append(l)}
 for(const n of nodes){let [x,y]=pos[n.id],g=document.createElementNS(svg.namespaceURI,'g'),c=document.createElementNS(svg.namespaceURI,'circle'),t=document.createElementNS(svg.namespaceURI,'text');c.setAttribute('cx',x);c.setAttribute('cy',y);c.setAttribute('r',n.kind==='research_question'?20:14);c.setAttribute('class','node '+n.kind);t.setAttribute('x',x);t.setAttribute('y',y+(n.kind==='research_question'?37:31));t.setAttribute('text-anchor','middle');t.setAttribute('font-size','12');t.textContent=short(n.label,30);g.append(c,t);g.onclick=()=>show(n);svg.append(g)}
 let wrap=document.createElement('div');wrap.innerHTML='<div class="legend"><i class="question-dot"></i>研究问题 <i class="concept-dot"></i>所需概念</div>';wrap.append(svg);if(data.diagnostics?.length){let d=document.createElement('div');d.className='warning';d.textContent='数据完整性提示：'+data.diagnostics.join('；');wrap.append(d)}$('#view').replaceChildren(wrap)}
function renderPapers(){let wrap=document.createElement('div');wrap.innerHTML='<p class="legend">选择一篇文献，可在右侧查看其支持范围与不支持的结论。证据边界不会作为独立节点堆叠显示。</p>';for(const n of data.nodes.filter(n=>n.kind==='paper'))wrap.append(button(n));$('#view').replaceChildren(wrap)}
function renderKnowledge(){let wrap=document.createElement('div'),domain=by['concept:domain'];wrap.append(Object.assign(document.createElement('h2'),{textContent:domain?.label||'知识体系'}));for(const q of data.nodes.filter(n=>n.kind==='research_question')){let box=document.createElement('div');box.className='card';let concepts=data.edges.filter(e=>e.source===q.id&&e.relation==='requires_concept').map(e=>by[e.target]).filter(Boolean),papers=data.edges.filter(e=>e.source===q.id&&e.relation==='anchored_by').map(e=>by[e.target]).filter(Boolean);box.innerHTML='<strong>'+esc(q.label)+'</strong><p class="legend">从前沿问题展开到需要理解的概念与锚定来源。</p><h3>所需概念</h3>'+concepts.map(n=>'<span class="tag">'+esc(n.label)+'</span>').join('')+'<h3>锚定来源</h3>';for(const p of papers)box.append(button(p));box.onclick=e=>{if(e.target===box||e.target.tagName==='STRONG')show(q)};wrap.append(box)}if(!data.nodes.some(n=>n.kind==='research_question'))wrap.innerHTML+='<p class="empty">该 run 尚未产生 frontier tensions，不能自动编造知识层级。</p>';$('#view').replaceChildren(wrap)}
function renderClaims(){let wrap=document.createElement('div'),claims=data.nodes.filter(n=>n.kind==='claim');wrap.innerHTML='<p class="legend">断言由 ATR artifact 提出，不是论文本身的原话。只有明确记录 source ID 的断言才显示来源连线；请在 Zotero 中阅读原始材料后再作出判断。</p>';for(const claim of claims){let box=document.createElement('div');box.className='card';let d=claim.data||{},sources=data.edges.filter(e=>e.source===claim.id&&e.relation==='cites_explicit_source').map(e=>by[e.target]).filter(Boolean),prior=data.edges.filter(e=>e.source===claim.id&&e.relation==='supersedes').map(e=>by[e.target]).filter(Boolean);box.innerHTML='<strong>'+esc(claim.label)+'</strong><p><span class="tag">'+esc(d.status||'UNSPECIFIED')+'</span><span class="tag">claim '+esc(d.claim_id||'')+'</span></p><h3>适用条件</h3><p>'+esc(JSON.stringify(d.conditions||{}))+'</p><h3>不能声称</h3><p>'+esc((d.forbidden_claims||[]).join('；')||'未记录')+'</p><h3>显式来源</h3><p>'+esc(sources.map(n=>n.label).join('；')||'该 artifact 未声明来源 ID')+'</p>';if(prior.length)box.innerHTML+='<h3>替代的旧断言</h3><p>'+esc(prior.map(n=>n.label).join('；'))+'</p>';box.onclick=()=>show(claim);wrap.append(box)}if(!claims.length)wrap.innerHTML+='<p class="empty">该 run 没有可用的 claim ledger；工作台不会从论文标题或摘要自动编造断言。</p>';$('#view').replaceChildren(wrap)}
function renderEvolution(){let wrap=document.createElement('div'),contexts=data.nodes.filter(n=>n.kind==='knowledge_context'),steps=data.nodes.filter(n=>n.kind==='knowledge_step'),briefs=data.nodes.filter(n=>n.kind==='landscape_brief'),tensions=data.nodes.filter(n=>n.kind==='real_world_tension'),problems=data.nodes.filter(n=>n.kind==='research_problem'),timeline=Array.isArray(data.timeline)?data.timeline:[];wrap.innerHTML='<h2>知识与现实问题如何进入研究</h2><p class="legend">这里仅展示 ATR 明确记录的 artifact。缺失并不由工作台替你补写。</p><h3>研究演化时间线</h3>';if(!timeline.length)wrap.innerHTML+='<p class="empty">当前 run 未提供可排序的时间戳 artifact。</p>';for(const item of timeline){let box=document.createElement('div');box.className='card';box.innerHTML='<strong>'+esc(item.at||'未记录时间')+' · '+esc(item.kind||'artifact')+'</strong><p>'+esc(item.label||item.id||'未命名 artifact')+'</p>';wrap.append(box)}wrap.innerHTML+='<h3>已读证据的景观简报</h3>';if(!briefs.length)wrap.innerHTML+='<p class="empty">尚无 landscape brief；不能把来源列表伪装成已完成的证据综合。</p>';for(const brief of briefs){let d=brief.data||{},sources=data.edges.filter(e=>e.source===brief.id&&e.relation==='inspects_explicit_source').map(e=>by[e.target]).filter(Boolean),box=document.createElement('div');box.className='card';box.innerHTML='<strong>'+esc(brief.label)+'</strong><p><span class="tag">'+esc(d.disposition||'UNSPECIFIED')+'</span><span class="tag">'+(d.immutable?'immutable':'draft')+'</span></p><p>'+esc(d.observed_tension||'未记录张力')+'</p><h3>还不能证明</h3><p>'+esc((d.sources_do_not_establish||[]).join('；')||'未记录')+'</p><h3>最小下一判别</h3><p>'+esc(d.smallest_next_discriminator||'未记录')+'</p><h3>已检查来源</h3><p>'+esc(sources.map(n=>n.label).join('；')||'未记录')+'</p>';box.onclick=()=>show(brief);wrap.append(box)}wrap.innerHTML+='<h3>从前沿张力到断言的知识收缩</h3>';if(!contexts.length)wrap.innerHTML+='<p class="empty">尚无 knowledge-context artifact。</p>';for(const context of contexts){let box=document.createElement('div');box.className='card';let queue=data.edges.filter(e=>e.source===context.id&&e.relation==='contracts_to').map(e=>by[e.target]).filter(Boolean),lines=[];while(queue.length){let step=queue.shift();lines.push((step.data.layer||'步骤')+'：'+step.label);queue.push(...data.edges.filter(e=>e.source===step.id&&e.relation==='contracts_to').map(e=>by[e.target]).filter(Boolean))}box.innerHTML='<strong>'+esc(context.label)+'</strong><p>'+esc(lines.join(' → ')||'没有收缩步骤')+'</p>';box.onclick=()=>show(context);wrap.append(box)}if(!contexts.length&&steps.length)wrap.innerHTML+='<p class="warning">发现未归属的知识步骤，需回到 ATR artifact 修复 lineage。</p>';wrap.innerHTML+='<h3>现实世界张力</h3>';if(!tensions.length)wrap.innerHTML+='<p class="empty">尚无 opportunity-map artifact。</p>';for(const tension of tensions){let d=tension.data||{},box=document.createElement('div');box.className='card';box.innerHTML='<strong>'+esc(tension.label)+'</strong><p>主体：'+esc(d.actor||'未记录')+'；后果：'+esc(d.material_consequence||'未记录')+'</p><p class="legend">不能说明：'+esc(d.does_not_establish||'未记录')+'</p>';box.onclick=()=>show(tension);wrap.append(box)}wrap.innerHTML+='<h3>可证伪的研究问题</h3>';if(!problems.length)wrap.innerHTML+='<p class="empty">尚无 research-problem-card artifact。</p>';for(const problem of problems){let d=problem.data||{},box=document.createElement('div');box.className='card';box.innerHTML='<strong>'+esc(problem.label)+'</strong><p>'+esc((d.counterfactual_worlds||[]).map(w=>(w.label||'世界')+'：'+(w.explanation||'未记录')).join('；'))+'</p><p class="legend">最小证伪条件：'+esc(d.minimum_falsifier||'未记录')+'</p>';box.onclick=()=>show(problem);wrap.append(box)}$('#view').replaceChildren(wrap)}
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>{document.querySelectorAll('[data-view]').forEach(x=>x.classList.toggle('active',x===b));({questions:renderQuestions,knowledge:renderKnowledge,evolution:renderEvolution,claims:renderClaims,papers:renderPapers}[b.dataset.view])()});renderMetrics();renderQuestions();
</script></body></html>'''


def build(run_dir: Path, out: Path, registry: Optional[Path] = None, run_key: Optional[str] = None, label: Optional[str] = None) -> dict:
    graph = project_graph(load_legacy_run(run_dir))
    out.mkdir(parents=True, exist_ok=True)
    graph["history"] = archive_previous_projection(out, graph)
    encoded = json.dumps(graph, ensure_ascii=False).replace("</", "<\\/")
    (out / "graph.json").write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "index.html").write_text(HTML.replace("__GRAPH_DATA__", encoded), encoding="utf-8")
    export_bundle(graph, out)
    if registry:
        register_run(registry, key=run_key or out.name, label=label or graph["run"], run_dir=run_dir, output=out, graph=graph)
    return graph


def build_program(catalog: Path, program_key: str, out: Path, registry: Optional[Path] = None, label: Optional[str] = None) -> dict:
    graph = project_program(catalog, program_key)
    out.mkdir(parents=True, exist_ok=True)
    graph["history"] = archive_previous_projection(out, graph)
    encoded = json.dumps(graph, ensure_ascii=False).replace("</", "<\\/")
    (out / "graph.json").write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "index.html").write_text(HTML.replace("__GRAPH_DATA__", encoded), encoding="utf-8")
    export_bundle(graph, out)
    if registry:
        register_run(registry, key=program_key, label=label or graph["program"]["label"], run_dir=catalog, output=out, graph=graph)
    return graph


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("run_dir", type=Path); b.add_argument("--out", type=Path, required=True); b.add_argument("--registry", type=Path); b.add_argument("--run-key"); b.add_argument("--label")
    pbuild = sub.add_parser("build-program"); pbuild.add_argument("catalog", type=Path); pbuild.add_argument("--program", required=True); pbuild.add_argument("--out", type=Path, required=True); pbuild.add_argument("--registry", type=Path); pbuild.add_argument("--label")
    s = sub.add_parser("serve"); s.add_argument("directory", type=Path); s.add_argument("--port", type=int, default=8765)
    y = sub.add_parser("sync"); y.add_argument("directory", type=Path)
    h = sub.add_parser("review-human-input"); h.add_argument("directory", type=Path); h.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    if a.cmd == "build": print(json.dumps({"built": str(a.out), "nodes": len(build(a.run_dir, a.out, a.registry, a.run_key, a.label)["nodes"])}, ensure_ascii=False))
    elif a.cmd == "build-program": print(json.dumps({"built": str(a.out), "nodes": len(build_program(a.catalog, a.program, a.out, a.registry, a.label)["nodes"])}, ensure_ascii=False))
    elif a.cmd == "serve": ThreadingHTTPServer(("127.0.0.1", a.port), partial(SimpleHTTPRequestHandler, directory=a.directory)).serve_forever()
    elif a.cmd == "sync": print(json.dumps(sync_web_api(a.directory), ensure_ascii=False))
    else:
        report = impact_report(a.directory)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        queue = refresh_review_queue(a.directory)
        packets = materialize_review_packets(a.directory)
        print(json.dumps({"written": str(a.out), "affected": len(report["affected"]), "new_queue_items": queue["new_items"], "new_review_packets": len(packets["written"])}, ensure_ascii=False))


if __name__ == "__main__": main()
