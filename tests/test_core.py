import json
import tempfile
import unittest
from pathlib import Path
from atr_zotero_workbench.app import build
from atr_zotero_workbench.zotero import sync_web_api
from atr_zotero_workbench.human_input import impact_report

class BuildTest(unittest.TestCase):
    def test_build_v1_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp); run=tmp_path/'run'; (run/'evidence').mkdir(parents=True); (run/'knowledge').mkdir()
            (run/'evidence'/'sources.jsonl').write_text(json.dumps({'source_id':'P1','title':'Paper','url':'https://e.org','kind':'PRIMARY_BENCHMARK_PAPER','supports':'x','does_not_support':'y'})+'\n')
            (run/'knowledge'/'frontier-map.json').write_text(json.dumps({'domain':'NLP','frontier_tensions':[{'tension_id':'Q1','question':'Why?','anchor_source_ids':['P1'],'dimensions':['tokens']}]}))
            (run/'run-state.json').write_text(json.dumps({'run_id':'r','active_stage':'LANDSCAPE'}))
            graph=build(run,tmp_path/'out')
            self.assertEqual(len(graph['nodes']), 6)
            self.assertTrue((tmp_path/'out'/'zotero'/'items.csl.json').exists())
            self.assertIn('缺少可用的 evidence/claims.jsonl', graph['diagnostics'])
            dashboard = (tmp_path/'out'/'index.html').read_text()
            self.assertIn('研究问题地图', dashboard)
            self.assertIn('const data=', dashboard)
            self.assertIn('<html lang="zh-CN"><head>', dashboard)
            self.assertIn('</body></html>', dashboard)
            self.assertNotIn("fetch('graph.json')", dashboard)
            source = next(node for node in graph['nodes'] if node['id'] == 'paper:P1')
            self.assertEqual(source['data']['source_layer'], 'scholarly_evidence')
            association = next(edge for edge in graph['edges'] if edge['relation'] == 'illustrated_by_question_anchor')
            self.assertEqual((association['source'], association['target']), ('concept:tokens', 'paper:P1'))
            self.assertEqual(association['data']['attribution'], 'derived_question_context')

    def test_contextual_source_is_not_promoted_to_scholarly_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp); run = tmp_path/'run'; (run/'evidence').mkdir(parents=True); (run/'knowledge').mkdir()
            (run/'evidence'/'sources.jsonl').write_text(json.dumps({'source_id':'C1','title':'Policy report','url':'https://e.org','kind':'WHITEPAPER','supports':'context','does_not_support':'proof'})+'\n')
            (run/'knowledge'/'frontier-map.json').write_text(json.dumps({'domain':'NLP'}))
            (run/'run-state.json').write_text(json.dumps({'run_id':'r'}))
            graph = build(run, tmp_path/'out')
            source = next(node for node in graph['nodes'] if node['id'] == 'paper:C1')
            self.assertEqual(source['data']['source_layer'], 'contextual_inspiration')
            relation = next(edge['relation'] for edge in graph['edges'] if edge['target'] == 'paper:C1')
            self.assertEqual(relation, 'inspires_context')

    def test_changed_projection_archives_previous_graph_without_deleting_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp); run = tmp_path/'run'; (run/'evidence').mkdir(parents=True); (run/'knowledge').mkdir()
            source = {'source_id':'P1','title':'Version one','url':'https://e.org','kind':'PRIMARY_BENCHMARK_PAPER','supports':'x','does_not_support':'y'}
            (run/'evidence'/'sources.jsonl').write_text(json.dumps(source)+'\n')
            (run/'knowledge'/'frontier-map.json').write_text(json.dumps({'domain':'NLP'}))
            (run/'run-state.json').write_text(json.dumps({'run_id':'r'}))
            out = tmp_path/'out'; build(run, out)
            source['title'] = 'Version two'
            (run/'evidence'/'sources.jsonl').write_text(json.dumps(source)+'\n')
            graph = build(run, out)
            snapshot = graph['history']['previous_projection']
            self.assertTrue(snapshot)
            previous = json.loads((out/'history'/'projections'/f'{snapshot}.json').read_text())
            self.assertEqual(next(node for node in previous['nodes'] if node['id']=='paper:P1')['label'], 'Version one')

    def test_sync_refuses_without_explicit_credentials(self):
        import os
        old = {key: os.environ.pop(key, None) for key in ('ZOTERO_LIBRARY_TYPE','ZOTERO_LIBRARY_ID','ZOTERO_API_KEY')}
        try:
            with self.assertRaisesRegex(RuntimeError, 'Refusing Zotero write'):
                sync_web_api({'run': 'r', 'nodes': []}, Path('/tmp/unused-audit.json'))
        finally:
            for key, value in old.items():
                if value is not None: os.environ[key] = value

    def test_human_note_maps_back_to_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); (out/'human-input').mkdir()
            graph={'nodes':[{'id':'paper:P1','kind':'paper','label':'Paper','data':{'source_id':'P1'}},{'id':'concept:domain','kind':'concept','label':'NLP','data':{}},{'id':'question:Q1','kind':'research_question','label':'Why?','data':{'tension_id':'Q1'}}], 'edges':[{'source':'paper:P1','target':'question:Q1','relation':'anchored_by','data':{}},{'source':'question:Q1','target':'concept:domain','relation':'contains_question','data':{}}]}
            (out/'graph.json').write_text(json.dumps(graph))
            (out/'human-input'/'inbox.jsonl').write_text(json.dumps({'event':'human_note_modified','zotero_note_key':'N1','atr_source_id':'P1'})+'\n')
            item = impact_report(out)['affected'][0]
            self.assertEqual(item['nearest_research_branches'][0]['question'], 'Why?')
            self.assertEqual(item['nearest_research_branches'][0]['tension_id'], 'Q1')
            self.assertEqual(item['nearest_research_branches'][0]['distance_from_annotated_source'], 1)
            self.assertEqual([part['id'] for part in item['nearest_research_branches'][0]['path']], ['paper:P1', 'question:Q1'])
