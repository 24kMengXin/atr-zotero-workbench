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
            (run/'evidence'/'sources.jsonl').write_text(json.dumps({'source_id':'P1','title':'Paper','url':'https://e.org','kind':'PRIMARY','supports':'x','does_not_support':'y'})+'\n')
            (run/'knowledge'/'frontier-map.json').write_text(json.dumps({'domain':'NLP','frontier_tensions':[{'tension_id':'Q1','question':'Why?','anchor_source_ids':['P1'],'dimensions':['tokens']}]}))
            (run/'run-state.json').write_text(json.dumps({'run_id':'r','active_stage':'LANDSCAPE'}))
            graph=build(run,tmp_path/'out')
            self.assertEqual(len(graph['nodes']), 6)
            self.assertTrue((tmp_path/'out'/'zotero'/'items.csl.json').exists())
            self.assertIn('缺少可用的 evidence/claims.jsonl', graph['diagnostics'])
            dashboard = (tmp_path/'out'/'index.html').read_text()
            self.assertIn('研究问题地图', dashboard)
            self.assertIn('const data=', dashboard)
            self.assertNotIn("fetch('graph.json')", dashboard)

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
            graph={'nodes':[{'id':'paper:P1','kind':'paper','label':'Paper','data':{'source_id':'P1'}},{'id':'question:Q1','kind':'research_question','label':'Why?','data':{}}], 'edges':[{'source':'paper:P1','target':'question:Q1','relation':'anchored_by','data':{}}]}
            (out/'graph.json').write_text(json.dumps(graph))
            (out/'human-input'/'inbox.jsonl').write_text(json.dumps({'event':'human_note_modified','zotero_note_key':'N1','atr_source_id':'P1'})+'\n')
            self.assertEqual(impact_report(out)['affected'][0]['affected_research_questions'], ['Why?'])
