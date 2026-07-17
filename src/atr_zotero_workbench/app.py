from __future__ import annotations
import argparse, json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from .core import load_legacy_run, project_graph
from .zotero import export_bundle, sync_web_api
from .human_input import impact_report

HTML = '''<!doctype html><meta charset="utf-8"><title>ATR Research Workbench</title><style>
body{margin:0;font:14px system-ui;color:#19212b;background:#f6f8fb}header{padding:16px 22px;background:#152b42;color:white}main{display:grid;grid-template-columns:1fr 340px;height:calc(100vh - 68px)}svg{width:100%;height:100%;background:white}.edge{stroke:#aab6c2;stroke-width:1.4}.node{cursor:pointer;stroke:white;stroke-width:2}.paper{fill:#3478b9}.concept{fill:#7b61a8}.research_question{fill:#ca6f1e}.evidence_boundary{fill:#4a9e85}.run{fill:#374151}aside{padding:18px;overflow:auto;border-left:1px solid #d5dde5}h2{margin-top:0}.tag{display:inline-block;padding:2px 7px;background:#e8eef5;border-radius:10px;margin:2px}a{color:#075da8}</style><header><b>ATR × Zotero Research Workbench</b><span id="meta"></span></header><main><svg id="g"></svg><aside id="detail"><h2>选择一个节点</h2><p>蓝色：文献；紫色：概念；橙色：研究问题；绿色：证据边界。</p></aside></main><script>
fetch('graph.json').then(x=>x.json()).then(data=>{document.querySelector('#meta').textContent=' · '+data.run+' · 派生只读投影';let svg=document.querySelector('#g'),w=svg.clientWidth,h=svg.clientHeight, by=Object.fromEntries(data.nodes.map(x=>[x.id,x]));let pos={};data.nodes.forEach((n,i)=>{let a=i/data.nodes.length*6.283,r=Math.min(w,h)*.34;pos[n.id]=[w/2+Math.cos(a)*r,h/2+Math.sin(a)*r]});data.edges.forEach(e=>{let a=pos[e.source],b=pos[e.target];if(a&&b){let l=document.createElementNS('http://www.w3.org/2000/svg','line');l.setAttribute('x1',a[0]);l.setAttribute('y1',a[1]);l.setAttribute('x2',b[0]);l.setAttribute('y2',b[1]);l.setAttribute('class','edge');svg.append(l)}});data.nodes.forEach(n=>{let [x,y]=pos[n.id],c=document.createElementNS('http://www.w3.org/2000/svg','circle');c.setAttribute('cx',x);c.setAttribute('cy',y);c.setAttribute('r',n.kind==='run'?17:12);c.setAttribute('class','node '+n.kind);c.onclick=()=>show(n,data.edges);svg.append(c);let t=document.createElementNS('http://www.w3.org/2000/svg','text');t.setAttribute('x',x+15);t.setAttribute('y',y+4);t.textContent=n.label.slice(0,32);t.style.fontSize='11px';svg.append(t)});function show(n,edges){let d=n.data, rel=edges.filter(e=>e.source===n.id||e.target===n.id).map(e=>by[e.source===n.id?e.target:e.source].label);document.querySelector('#detail').innerHTML='<h2>'+n.label+'</h2><p><span class="tag">'+n.kind+'</span></p>'+Object.entries(d).map(([k,v])=>'<h3>'+k+'</h3><div>'+ (Array.isArray(v)?v.join('<br>'):String(v).replaceAll('\n','<br>'))+'</div>').join('')+'<h3>连接</h3><div>'+rel.map(x=>'<span class="tag">'+x+'</span>').join(' ')+'</div>'}}
});</script>'''

def build(run_dir: Path, out: Path) -> dict:
    graph = project_graph(load_legacy_run(run_dir)); out.mkdir(parents=True, exist_ok=True)
    (out/'graph.json').write_text(json.dumps(graph,ensure_ascii=False,indent=2),encoding='utf-8'); (out/'index.html').write_text(HTML,encoding='utf-8'); export_bundle(graph,out); return graph
def main() -> None:
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='cmd', required=True)
    b=sub.add_parser('build'); b.add_argument('run_dir',type=Path); b.add_argument('--out',type=Path,required=True)
    s=sub.add_parser('serve'); s.add_argument('directory',type=Path); s.add_argument('--port',type=int,default=8765)
    y=sub.add_parser('sync'); y.add_argument('directory',type=Path)
    h=sub.add_parser('review-human-input'); h.add_argument('directory',type=Path); h.add_argument('--out',type=Path)
    a=p.parse_args()
    if a.cmd=='build': print(json.dumps({"built":str(a.out),"nodes":len(build(a.run_dir,a.out)['nodes'])},ensure_ascii=False))
    elif a.cmd=='serve':
        with ThreadingHTTPServer(('127.0.0.1',a.port),partial(SimpleHTTPRequestHandler,directory=str(a.directory))) as server: print(f'http://127.0.0.1:{a.port}'); server.serve_forever()
    elif a.cmd=='sync': print(json.dumps(sync_web_api(json.loads((a.directory/'graph.json').read_text()),a.directory/'zotero'/'sync-audit.json'),ensure_ascii=False))
    else:
        report=impact_report(a.directory)
        if a.out: a.out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__': main()
