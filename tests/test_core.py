import json
import tempfile
import unittest
from pathlib import Path
from atr_zotero_workbench.app import build, build_program
from atr_zotero_workbench.core import load_legacy_run, project_graph
from atr_zotero_workbench.zotero import native_projection, sync_web_api, validate_native_projection
from atr_zotero_workbench.human_input import impact_report, materialize_review_packets, refresh_review_queue
from atr_zotero_workbench.runs import validate_registry

_REPO_TEST_TMP = Path(__file__).resolve().parents[1] / ".runtime" / "tests"
_REPO_TEST_TMP.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(_REPO_TEST_TMP)

class BuildTest(unittest.TestCase):
    def test_native_projection_rejects_duplicate_and_dangling_objects(self):
        graph = {
            'run': 'r',
            'nodes': [{'id': 'paper:P1', 'kind': 'paper', 'label': 'Paper', 'data': {'source_id': 'P1'}}],
            'edges': [],
        }
        projection = native_projection(graph)
        duplicate = dict(projection['objects'][0])
        duplicate['graph_node_id'] = 'paper:MISSING'
        duplicate['linked_source_ids'] = ['MISSING']
        projection['objects'].append(duplicate)
        errors = validate_native_projection(projection, graph)
        self.assertIn('duplicate object_id: topic:r', errors)
        self.assertIn('duplicate marker: ATR Topic Run: r', errors)
        self.assertTrue(any('missing graph node' in error for error in errors))
        self.assertTrue(any('missing source' in error for error in errors))

    def test_build_v1_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp); run=tmp_path/'run'; (run/'evidence').mkdir(parents=True); (run/'knowledge').mkdir()
            (run/'evidence'/'sources.jsonl').write_text(json.dumps({'source_id':'P1','title':'Paper','url':'https://e.org','kind':'PRIMARY_BENCHMARK_PAPER','supports':'x','does_not_support':'y'})+'\n')
            (run/'knowledge'/'frontier-map.json').write_text(json.dumps({'domain':'NLP','frontier_tensions':[{'tension_id':'Q1','question':'Why?','anchor_source_ids':['P1'],'dimensions':['tokens']}]}))
            (run/'run-state.json').write_text(json.dumps({'run_id':'r','active_stage':'LANDSCAPE'}))
            graph=build(run,tmp_path/'out')
            self.assertEqual(len(graph['nodes']), 6)
            self.assertTrue((tmp_path/'out'/'zotero'/'items.csl.json').exists())
            native = json.loads((tmp_path/'out'/'zotero'/'native-projection.json').read_text())
            self.assertEqual(native['projection'], 'atr-zotero-native-map')
            self.assertEqual(native['feedback_contract']['target_priority'], [
                'claim', 'research_problem', 'research_question', 'real_world_tension',
                'source', 'knowledge', 'topic',
            ])
            self.assertEqual(next(obj for obj in native['objects'] if obj['object_kind'] == 'source_item')['marker'], 'atr-source-id:P1')
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

    def test_build_registers_explicit_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp); run = tmp_path/'run'; (run/'evidence').mkdir(parents=True); (run/'knowledge').mkdir()
            (run/'evidence'/'sources.jsonl').write_text('')
            (run/'knowledge'/'frontier-map.json').write_text(json.dumps({'domain':'NLP'}))
            (run/'run-state.json').write_text(json.dumps({'run_id':'r'}))
            registry = tmp_path/'registry.json'; out = tmp_path/'out'
            build(run, out, registry, 'topic-a', 'Topic A')
            record = json.loads(registry.read_text())['runs'][0]
            self.assertEqual(record['key'], 'topic-a')
            self.assertEqual(record['label'], 'Topic A')
            self.assertEqual(Path(record['workspace']), out.resolve())
            self.assertEqual(record['controller_kind'], 'ATR_V1_RUN_STATE')
            self.assertEqual(record['authority_scope'], 'LEGACY_LIFECYCLE')
            self.assertEqual(json.loads(registry.read_text())['active_run'], 'topic-a')

    def test_registry_build_order_cannot_silently_change_active_topic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); registry = root / 'registry.json'
            for key in ('first', 'second'):
                run = root / key; (run / 'evidence').mkdir(parents=True); (run / 'knowledge').mkdir()
                (run / 'evidence' / 'sources.jsonl').write_text('')
                (run / 'knowledge' / 'frontier-map.json').write_text(json.dumps({'domain': key}))
                (run / 'run-state.json').write_text(json.dumps({'run_id': key}))
                build(run, root / (key + '-out'), registry, key, key.title())
            body = json.loads(registry.read_text())
            self.assertEqual(body['schema_version'], '0.2')
            self.assertEqual(body['active_run'], 'first')
            self.assertEqual(body['selection']['selected_key'], 'first')
            self.assertEqual(validate_registry(body), [])

    def test_v09_run_without_frontier_stays_honest_and_shows_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp); run = tmp_path/'run'; (run/'evidence').mkdir(parents=True)
            (run/'evidence'/'sources.jsonl').write_text('')
            (run/'intake.json').write_text(json.dumps({'initial_question':'How should agents be audited?'}))
            (run/'run-state.json').write_text(json.dumps({'schema_version':'1.0','run_id':'v09','active_stage':'R1_LANDSCAPE','status':'running','next_action':'Collect primary sources','stage_contract':{'mode':'EMERGING_DIRECTION','required_artifacts':['landscape brief']},'gates':{'G0-INTAKE':'PASS','G2-EVIDENCE':'PENDING'}}))
            (run/'observability').mkdir()
            (run/'observability'/'skill-events.jsonl').write_text(json.dumps({'event_id':'SK-1','timestamp':'2026-01-01T00:00:00Z','skill':'research-direction-gating','event':'END','status':'SUCCEEDED','invocation':'ROUTED','artifact_ids':[]})+'\n')
            graph = build(run, tmp_path/'out')
            domain = next(node for node in graph['nodes'] if node['id']=='concept:domain')
            self.assertEqual(domain['label'], 'How should agents be audited?')
            gate = next(node for node in graph['nodes'] if node['id']=='gate:G0-INTAKE')
            self.assertEqual(gate['data']['status'], 'PASS')
            self.assertEqual(next(node for node in graph['nodes'] if node['kind']=='run')['data']['stage_contract']['mode'], 'EMERGING_DIRECTION')
            self.assertEqual(next(node for node in graph['nodes'] if node['id']=='skill:SK-1')['data']['skill'], 'research-direction-gating')
            self.assertEqual(sum(node['kind']=='paper' for node in graph['nodes']), 0)
            self.assertTrue(any('不生成研究问题' in item for item in graph['diagnostics']))

    def test_v2_sqlite_run_projects_authority_not_derived_json(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); run = root / 'v2'; run.mkdir()
            conn = sqlite3.connect(run / 'atr.sqlite')
            conn.executescript('''
                CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE subjects (subject_id TEXT PRIMARY KEY, kind TEXT, state TEXT, version INTEGER, active INTEGER, created_at TEXT, updated_at TEXT);
                CREATE TABLE artifacts (artifact_id TEXT PRIMARY KEY, digest TEXT, kind TEXT, original_name TEXT, created_at TEXT, metadata_json TEXT);
                CREATE TABLE events (seq INTEGER PRIMARY KEY, event_id TEXT, subject_id TEXT, from_state TEXT, to_state TEXT, expected_version INTEGER, artifact_id TEXT, review_mode TEXT, note TEXT, created_at TEXT);
                CREATE TABLE attachments (seq INTEGER PRIMARY KEY, attachment_id TEXT, subject_id TEXT, subject_version INTEGER, artifact_id TEXT, role TEXT, note TEXT, created_at TEXT);
            ''')
            artifact = 'sha256:abc'; conn.execute('INSERT INTO meta VALUES (?,?)', ('run_id', 'v2-demo'))
            conn.execute('INSERT INTO subjects VALUES (?,?,?,?,?,?,?)', ('topic-1', 'direction', 'LANDSCAPE', 1, 1, '2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z'))
            conn.execute('INSERT INTO artifacts VALUES (?,?,?,?,?,?)', ('sha256:oldk', 'oldk', 'knowledge-map', 'old-map.json', '2025-12-31T00:00:00Z', '{}'))
            conn.execute('INSERT INTO artifacts VALUES (?,?,?,?,?,?)', (artifact, 'abc', 'knowledge-map', 'map.json', '2026-01-01T00:00:00Z', '{}'))
            conn.execute('INSERT INTO artifacts VALUES (?,?,?,?,?,?)', ('sha256:jkl', 'jkl', 'opportunity-map', 'opportunity.json', '2026-01-01T12:00:00Z', '{}'))
            conn.execute('INSERT INTO artifacts VALUES (?,?,?,?,?,?)', ('sha256:oldp', 'oldp', 'problem-case', 'old-problem.json', '2026-01-01T18:00:00Z', '{}'))
            conn.execute('INSERT INTO artifacts VALUES (?,?,?,?,?,?)', ('sha256:def', 'def', 'problem-case', 'problem.json', '2026-01-02T00:00:00Z', '{}'))
            conn.execute('INSERT INTO artifacts VALUES (?,?,?,?,?,?)', ('sha256:ghi', 'ghi', 'human-review-disposition', 'disposition.json', '2026-01-03T00:00:00Z', '{}'))
            conn.execute('INSERT INTO artifacts VALUES (?,?,?,?,?,?)', ('sha256:hra', 'hra', 'human-review-assessment', 'assessment.json', '2026-01-04T00:00:00Z', '{}'))
            conn.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?)', (1, 'E1', 'topic-1', 'INTAKE', 'LANDSCAPE', 0, artifact, 'human', 'landscape', '2026-01-01T00:00:00Z'))
            conn.execute('INSERT INTO attachments VALUES (?,?,?,?,?,?,?,?)', (1, 'A1', 'topic-1', 1, artifact, 'human-review-input', 'approved packet', '2026-01-02T00:00:00Z')); conn.commit(); conn.close()
            # A stale v2 derived cache must not be read as authority.
            old_knowledge_body = run / 'artifacts' / 'oldk'; old_knowledge_body.mkdir(parents=True)
            (old_knowledge_body / 'body.json').write_text(json.dumps({'artifact_type':'knowledge-map','map_id':'KM-1','topic':'Old auditable agents map','sources':[{'source_id':'P1','title':'Paper','url':'https://e.org','kind':'PAPER'}],'concepts':[{'concept_id':'auditability','label':'Old auditability definition','definition':'Earlier definition','source_ids':['P1']}]}))
            body = run / 'artifacts' / 'abc'; body.mkdir(parents=True)
            (body / 'body.json').write_text(json.dumps({'artifact_type':'knowledge-map','map_id':'KM-1','topic':'Auditable agents','sources':[{'source_id':'P1','title':'Paper','url':'https://e.org','pdf_url':'https://e.org/paper.pdf','kind':'PAPER','does_not_establish':'not a general guarantee'}],'concepts':[{'concept_id':'auditability','label':'Auditability','definition':'Traceable review','source_ids':['P1']},{'concept_id':'action','label':'Action attribution','parent_id':'auditability','source_ids':['P1']}]}))
            opportunity_body = run / 'artifacts' / 'jkl'; opportunity_body.mkdir(parents=True)
            (opportunity_body / 'body.json').write_text(json.dumps({
                'artifact_type':'opportunity-map','map_id':'OM-1','scope':'Human review of agent actions',
                'searched_through':'2026-01-01','created_at':'2026-01-01T12:00:00Z','valid_until':'2027-01-01',
                'does_not_establish':'This is inspiration, not a gap certificate.',
                'sources':[
                    {'source_id':'S-WORKFLOW','title':'Workflow issue','url':'https://w.org','kind':'ISSUE','source_function':'PRIMARY_WORKFLOW','observed_at':'2025-12-01','supports':'Reviewers lack traceability.','does_not_establish':'Prevalence.'},
                    {'source_id':'S-FRONTIER','title':'Frontier paper','url':'https://f.org','kind':'PAPER','source_function':'SCIENTIFIC_FRONTIER','observed_at':'2025-12-15','supports':'Trace evidence changes adjudication.','does_not_establish':'Deployment harm.'},
                ],
                'tension_clusters':[{'tension_id':'T-1','label':'Reviewers cannot locate the cause of an agent action','source_ids':['S-WORKFLOW','S-FRONTIER'],'actor':'reviewers','incumbent_practice':'trust an aggregate score','material_consequence':'incorrect remediation','candidate_construct':'action traceability','alternative_explanations':['model capability','interface contract'],'translation_status':'ROUTE_TO_R0','does_not_establish':'Novelty or population frequency.'}],
            }))
            old_problem_body = run / 'artifacts' / 'oldp'; old_problem_body.mkdir(parents=True)
            (old_problem_body / 'body.json').write_text(json.dumps({'artifact_type':'problem-case','problem_id':'PC-1','research_question':'Earlier action-cause question','worlds':['W1','W2'],'discriminator':'Earlier trace','falsifier':'No trace effect','source_spans':[{'source_id':'P2','title':'Deployment report','url':'https://r.org','kind':'REPORT','locator':'p. 2','observation':'earlier observation'}]}))
            problem_body = run / 'artifacts' / 'def'; problem_body.mkdir(parents=True)
            (problem_body / 'body.json').write_text(json.dumps({'artifact_type':'problem-case','problem_id':'PC-1','research_question':'Can a reviewer distinguish action causes?','worlds':['W1','W2'],'discriminator':'A contrastive trace','falsifier':'No trace changes judgment','source_spans':[{'source_id':'P2','title':'Deployment report','url':'https://r.org','kind':'REPORT','locator':'p. 3','observation':'reviewers lack provenance','problem_posture':'OBJECTIVELY_LEAVES','resolves':'Documents the observed workflow failure.','leaves_unresolved':'Does not distinguish model capability from interface contract.','does_not_establish':'Prevalence or causal attribution.'}],'derived_questions':[{'question_id':'DQ-1','question':'Does a contract-bearing trace distinguish the two causes?','smallest_discriminator':'One revision-pinned action with independent adjudication.','does_not_establish':'Population frequency.','source_ids':['P2']}]}))
            disposition_body = run / 'artifacts' / 'ghi'; disposition_body.mkdir(parents=True)
            (disposition_body / 'body.json').write_text(json.dumps({'artifact_type':'human-review-disposition','disposition_id':'HRD-1','packet_id':'HRP-1','disposition':'OPEN_CLAIM_REVIEW','owner':'researcher','rationale':'locator challenges scope','review':{'source_id':'P2'},'impact':{'all_affected_research_problems':[{'problem_id':'PC-1'}]}}))
            assessment_body = run / 'artifacts' / 'hra'; assessment_body.mkdir(parents=True)
            (assessment_body / 'body.json').write_text(json.dumps({'artifact_type':'human-review-assessment','assessment_id':'HRA-1','packet_id':'HRP-1','disposition_id':'HRD-1','reviewed_at':'2026-01-04T00:00:00Z','reviewer':{'id':'codex-reviewer','role':'evidence_reviewer','isolated_from_disposition_owner':True},'finding':'Keep the source but narrow the problem wording.','outcome':'REVISE_PROBLEM','evidence_basis':[{'kind':'HUMAN_REVIEW_PACKET','ref':'HRP-1','locator':'p. 3','observation':'The scope is narrower.','does_not_establish':'No new gate verdict.'}],'impact':{'preserve_object_ids':['paper:P2'],'reconsider_object_ids':['research_problem:PC-1']},'required_followup_artifact_kind':'problem-case','controller_boundary':'This assessment does not itself modify lifecycle state or history.'}))
            (run / 'state.json').write_text(json.dumps({'subjects':[{'state':'PAPER'}]}))
            graph = build(run, root / 'out')
            run_node = next(node for node in graph['nodes'] if node['kind'] == 'run')
            self.assertEqual(run_node['data']['stage'], 'LANDSCAPE')
            self.assertEqual(graph['projection'], 'derived-read-only-v2-sqlite')
            self.assertTrue(any(node['kind'] == 'atr_v2_attachment' for node in graph['nodes']))
            self.assertTrue(any(node['kind'] == 'knowledge_concept' and node['label'] == 'Action attribution' for node in graph['nodes']))
            self.assertTrue(any(edge['relation'] == 'defines_with_explicit_source' for edge in graph['edges']))
            tension = next(node for node in graph['nodes'] if node['id'] == 'real_world_tension:T-1')
            self.assertEqual(tension['data']['candidate_construct'], 'action traceability')
            tension_sources = {edge['target'] for edge in graph['edges'] if edge['source'] == tension['id'] and edge['relation'] == 'grounded_in_explicit_signal'}
            self.assertEqual(tension_sources, {'paper:S-WORKFLOW', 'paper:S-FRONTIER'})
            problem = next(node for node in graph['nodes'] if node['id'] == 'research_problem:PC-1')
            self.assertEqual(problem['data']['discriminator'], 'A contrastive trace')
            problem_source = next(edge for edge in graph['edges'] if edge['source'] == problem['id'] and edge['relation'] == 'grounds_in_explicit_source_span' and edge['target'] == 'paper:P2')
            self.assertEqual(problem_source['data']['problem_posture'], 'OBJECTIVELY_LEAVES')
            self.assertEqual(problem_source['data']['leaves_unresolved'], 'Does not distinguish model capability from interface contract.')
            derived = next(node for node in graph['nodes'] if node['id'] == 'derived_question:PC-1:DQ-1')
            self.assertEqual(derived['data']['smallest_discriminator'], 'One revision-pinned action with independent adjudication.')
            self.assertTrue(any(edge['source'] == problem['id'] and edge['target'] == derived['id'] and edge['relation'] == 'generates_finer_review_question' for edge in graph['edges']))
            disposition = next(node for node in graph['nodes'] if node['id'] == 'human_review:HRD-1')
            self.assertEqual(disposition['data']['disposition'], 'OPEN_CLAIM_REVIEW')
            self.assertTrue(any(edge['source'] == disposition['id'] and edge['target'] == 'research_problem:PC-1' for edge in graph['edges']))
            assessment = next(node for node in graph['nodes'] if node['id'] == 'human_review_assessment:HRA-1')
            self.assertEqual(assessment['data']['outcome'], 'REVISE_PROBLEM')
            self.assertTrue(any(edge['source'] == disposition['id'] and edge['target'] == assessment['id'] and edge['relation'] == 'reviewed_by_isolated_assessment' for edge in graph['edges']))
            self.assertTrue(any(edge['source'] == assessment['id'] and edge['target'] == 'paper:P2' and edge['relation'] == 'preserves_object_after_review' for edge in graph['edges']))
            self.assertTrue(any(edge['source'] == assessment['id'] and edge['target'] == 'research_problem:PC-1' and edge['relation'] == 'requests_new_version_after_review' for edge in graph['edges']))
            self.assertIn('ATR v2：知识与现实问题链路', (root / 'out' / 'index.html').read_text())
            native = json.loads((root / 'out' / 'zotero' / 'native-projection.json').read_text())
            p1 = next(node for node in graph['nodes'] if node['id'] == 'paper:P1')
            self.assertEqual(p1['data']['pdf_url'], 'https://e.org/paper.pdf')
            p1_object = next(obj for obj in native['objects'] if obj['object_id'] == 'source:P1')
            self.assertEqual(p1_object['pdf_url'], 'https://e.org/paper.pdf')
            problem_object = next(obj for obj in native['objects'] if obj['object_kind'] == 'problem_note' and obj['review_role'] == 'CURRENT_REVIEW_TARGET')
            self.assertEqual(problem_object['marker'], 'ATR Problem ID: PC-1 | ATR Graph Node: research_problem:PC-1')
            self.assertEqual(problem_object['linked_source_ids'], ['P2'])
            historical_problem = next(obj for obj in native['objects'] if obj['object_kind'] == 'problem_note' and obj['review_role'] == 'HISTORICAL_VERSION')
            self.assertIn('@oldp', historical_problem['graph_node_id'])
            tension_object = next(obj for obj in native['objects'] if obj['object_kind'] == 'tension_note')
            self.assertEqual(set(tension_object['linked_source_ids']), {'S-WORKFLOW', 'S-FRONTIER'})
            derived_object = next(obj for obj in native['objects'] if obj['object_kind'] == 'derived_question_note')
            self.assertEqual(derived_object['parent_graph_node_id'], 'research_problem:PC-1')
            self.assertEqual(derived_object['linked_source_ids'], ['P2'])
            knowledge_objects = [obj for obj in native['objects'] if obj['object_kind'] == 'knowledge_note']
            self.assertEqual(len(knowledge_objects), 3)
            self.assertEqual(sum(obj['review_role'] == 'HISTORICAL_VERSION' for obj in knowledge_objects), 1)
            child_object = next(obj for obj in knowledge_objects if obj['title'] == 'Action attribution' and obj['review_role'] != 'HISTORICAL_VERSION')
            self.assertEqual(child_object['parent_graph_node_id'], 'knowledge_concept:KM-1:auditability')
            self.assertEqual(child_object['linked_source_ids'], ['P1'])
            self.assertEqual(native['collections']['knowledge'], '02 · 知识体系')
            assessment_object = next(obj for obj in native['objects'] if obj['object_kind'] == 'review_assessment_note')
            self.assertEqual(assessment_object['marker'], 'ATR Review Assessment: HRA-1 | ATR Graph Node: human_review_assessment:HRA-1')
            self.assertEqual(assessment_object['linked_source_ids'], ['P2'])
            self.assertEqual(native['collections']['research_reviews'], '05 · 共创复核')
            attachment = next(item for item in graph['timeline'] if item['kind'] == 'atr_v2_attachment')
            self.assertIn('不改变 lifecycle', attachment['label'])

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

    def test_contextual_ledger_connects_to_question_without_becoming_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp); run = tmp_path/'run'; (run/'evidence').mkdir(parents=True); (run/'knowledge').mkdir()
            (run/'evidence'/'sources.jsonl').write_text(json.dumps({'source_id':'P1','title':'Paper','url':'https://e.org','kind':'PAPER','supports':'x','does_not_support':'y'})+'\n')
            (run/'evidence'/'contextual-sources.jsonl').write_text(json.dumps({'source_id':'C1','title':'Public report','url':'https://c.org','kind':'REPORT','supports':'observation','does_not_support':'causal proof','why_it_matters':'exposes deployment friction','related_tension_ids':['Q1']})+'\n')
            (run/'knowledge'/'frontier-map.json').write_text(json.dumps({'domain':'NLP','frontier_tensions':[{'tension_id':'Q1','question':'Why?','anchor_source_ids':['P1']}]}))
            (run/'run-state.json').write_text(json.dumps({'run_id':'r'}))
            graph = build(run, tmp_path/'out')
            source = next(node for node in graph['nodes'] if node['id'] == 'paper:C1')
            self.assertEqual(source['data']['source_layer'], 'contextual_inspiration')
            link = next(edge for edge in graph['edges'] if edge['relation'] == 'inspired_by_context')
            self.assertEqual((link['source'], link['target']), ('question:Q1', 'paper:C1'))

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
                sync_web_api({'run': 'r', 'nodes': []}, Path('unused-audit.json'))
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
            queue = refresh_review_queue(out)
            self.assertEqual(queue['new_items'], 1)
            self.assertEqual(queue['items'][0]['status'], 'pending_human_and_codex_review')
            self.assertEqual(queue['items'][0]['nearest_research_branches'][0]['question'], 'Why?')
            self.assertEqual(refresh_review_queue(out)['new_items'], 0)

    def test_claims_keep_status_conditions_and_explicit_lineage(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp); run = tmp_path / 'run'; (run / 'evidence').mkdir(parents=True); (run / 'knowledge').mkdir()
            (run / 'evidence' / 'sources.jsonl').write_text(json.dumps({'source_id':'P1','title':'Paper','url':'https://e.org','kind':'PAPER'}) + '\n')
            claims = [
                {'claim_id':'C1.v1','text':'A narrow claim','status':'SUPERSEDED','conditions':{'setting':'x'},'forbidden_claims':['broad claim']},
                {'claim_id':'C1.v2','claim':'A reframed claim','status':'PROBLEM_FORMULATION','supersedes':'C1.v1','source_ids':['P1']},
            ]
            (run / 'evidence' / 'claims.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in claims))
            (run / 'knowledge' / 'frontier-map.json').write_text(json.dumps({'domain':'NLP'}))
            (run / 'run-state.json').write_text(json.dumps({'run_id':'r'}))
            graph = build(run, tmp_path / 'out')
            first = next(node for node in graph['nodes'] if node['id'] == 'claim:C1.v1')
            self.assertEqual(first['data']['conditions'], {'setting':'x'})
            self.assertEqual(first['data']['forbidden_claims'], ['broad claim'])
            self.assertTrue(any(edge['relation'] == 'supersedes' and edge['source'] == 'claim:C1.v2' for edge in graph['edges']))
            self.assertTrue(any(edge['relation'] == 'cites_explicit_source' and edge['target'] == 'paper:P1' for edge in graph['edges']))

    def test_claim_review_is_not_reduced_to_a_source_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); (out / 'human-input').mkdir()
            graph = {
                'nodes': [
                    {'id':'claim:C1','kind':'claim','label':'Test claim','data':{'claim_id':'C1'}},
                    {'id':'paper:P1','kind':'paper','label':'Paper','data':{'source_id':'P1'}},
                    {'id':'question:Q1','kind':'research_question','label':'Why?','data':{'tension_id':'Q1'}},
                ],
                'edges': [
                    {'source':'claim:C1','target':'paper:P1','relation':'cites_explicit_source','data':{}},
                    {'source':'paper:P1','target':'question:Q1','relation':'anchored_by','data':{}},
                ],
            }
            (out / 'graph.json').write_text(json.dumps(graph))
            event = {'event':'human_note_modified','zotero_note_key':'N1','atr_claim_id':'C1','atr_source_id':'P1','review_stance':'CHALLENGES'}
            (out / 'human-input' / 'inbox.jsonl').write_text(json.dumps(event) + '\n')
            item = impact_report(out)['affected'][0]
            self.assertEqual(item['review_target_type'], 'claim')
            self.assertEqual(item['annotation_claim_id'], 'C1')
            self.assertEqual(item['nearest_research_branches'][0]['question'], 'Why?')
            self.assertEqual(item['nearest_decision_objects'][0]['id'], 'claim:C1')
            self.assertEqual(item['nearest_decision_objects'][0]['distance_from_review_target'], 0)

    def test_review_packet_is_immutable_and_requires_owner_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); (out / 'human-input').mkdir()
            graph = {
                'nodes': [
                    {'id':'claim:C1','kind':'claim','label':'Test claim','data':{'claim_id':'C1'}},
                    {'id':'question:Q1','kind':'research_question','label':'Why?','data':{'tension_id':'Q1'}},
                ],
                'edges': [{'source':'claim:C1','target':'question:Q1','relation':'raises_question','data':{}}],
            }
            (out / 'graph.json').write_text(json.dumps(graph))
            event = {'event':'human_note_modified','at':'2026-01-01T00:00:00Z','zotero_note_key':'N1','atr_claim_id':'C1','review_stance':'CHALLENGES','source_locator':'p. 7, para. 2','note_html':'<p>reason</p>'}
            (out / 'human-input' / 'inbox.jsonl').write_text(json.dumps(event) + '\n')
            result = materialize_review_packets(out)
            self.assertEqual(len(result['written']), 1)
            packet = json.loads(Path(result['written'][0]).read_text())
            self.assertEqual(packet['review']['stance'], 'CHALLENGES')
            self.assertEqual(packet['review']['source_locator'], 'p. 7, para. 2')
            self.assertEqual(packet['status'], 'PENDING_ATR_OWNER_REVIEW')
            self.assertEqual(packet['impact']['nearest_decision_objects'][0]['id'], 'claim:C1')
            self.assertIn('OPEN_CLAIM_REVIEW', packet['required_owner_decision']['allowed_dispositions'])
            self.assertEqual(materialize_review_packets(out)['existing'], 1)

    def test_owner_disposition_is_append_only_and_projects_back_to_the_claim(self):
        from atr_zotero_workbench.human_input import record_review_disposition
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); out = root / 'out'; run = root / 'run'; (out / 'human-input' / 'review-packets').mkdir(parents=True); (run / 'evidence').mkdir(parents=True); (run / 'decisions').mkdir()
            packet = {'packet_id':'HRP-a', 'review':{'target_type':'claim','claim_id':'C1','source_id':'P1','source_locator':'p. 3'}, 'impact':{'all_affected_research_questions':[{'tension_id':'Q1'}], 'related_claims':[], 'all_affected_research_problems':[]}, 'required_owner_decision':{'allowed_dispositions':['OPEN_CLAIM_REVIEW']}}
            (out / 'human-input' / 'review-packets' / 'HRP-a.json').write_text(json.dumps(packet))
            decision = record_review_disposition(out, run, 'HRP-a', 'OPEN_CLAIM_REVIEW', 'The locator challenges the scope.', 'researcher')
            self.assertEqual(decision['disposition'], 'OPEN_CLAIM_REVIEW')
            with self.assertRaises(ValueError): record_review_disposition(out, run, 'HRP-a', 'OPEN_CLAIM_REVIEW', 'Repeat.', 'researcher')
            (run / 'evidence' / 'sources.jsonl').write_text(json.dumps({'source_id':'P1','title':'Paper','kind':'PAPER'}) + '\n')
            (run / 'evidence' / 'claims.jsonl').write_text(json.dumps({'claim_id':'C1','text':'Claim'}) + '\n')
            (run / 'knowledge').mkdir(); (run / 'knowledge' / 'frontier-map.json').write_text(json.dumps({'domain':'NLP','frontier_tensions':[{'tension_id':'Q1','question':'Why?','anchor_source_ids':['P1'],'dimensions':[]}]}))
            (run / 'run-state.json').write_text(json.dumps({'run_id':'r'}))
            graph = build(run, root / 'built')
            node = next(node for node in graph['nodes'] if node['kind'] == 'human_review_disposition')
            self.assertEqual(node['data']['disposition'], 'OPEN_CLAIM_REVIEW')
            self.assertTrue(any(edge['source'] == node['id'] and edge['target'] == 'claim:C1' for edge in graph['edges']))

    def test_owner_approved_packet_attaches_to_v2_without_lifecycle_change(self):
        from unittest.mock import patch
        from atr_zotero_workbench.human_input import attach_review_packet_to_v2
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); out = root / 'out'; v2 = root / 'v2'; (out / 'human-input' / 'review-packets').mkdir(parents=True); v2.mkdir()
            packet = {'artifact_type':'human-review-packet','packet_id':'HRP-a','impact':{'nearest_decision_objects':[{'id':'claim:C1'}], 'nearest_research_problems':[{'problem_id':'RQ-1'}]}}
            packet_path = out / 'human-input' / 'review-packets' / 'HRP-a.json'; packet_path.write_text(json.dumps(packet))
            digest = __import__('hashlib').sha256(packet_path.read_bytes()).hexdigest()
            ledger = root / 'human-review-dispositions.jsonl'; ledger.write_text(json.dumps({'packet_id':'HRP-a','packet_sha256':digest,'decision_id':'HRD-1','disposition':'OPEN_CLAIM_REVIEW'}) + '\n')
            atrctl = root / 'atrctl.py'; atrctl.write_text('# placeholder')
            class Result:
                returncode = 0; stderr = ''
                def __init__(self, stdout): self.stdout = stdout
            with patch('atr_zotero_workbench.human_input.subprocess.run', side_effect=[Result('sha256:packet\n'), Result('')]) as invoke:
                result = attach_review_packet_to_v2(out, v2, 'HRP-a', 'subject-1', 3, atrctl, ledger)
            self.assertEqual(result['artifact_id'], 'sha256:packet')
            self.assertFalse(result['lifecycle_changed'])
            self.assertEqual(result['nearest_decision_objects'][0]['id'], 'claim:C1')
            self.assertIn('ingest', invoke.call_args_list[0].args[0])
            self.assertIn('attach', invoke.call_args_list[1].args[0])
            self.assertIn('--expected-version', invoke.call_args_list[1].args[0])

    def test_isolated_review_assessment_bridge_closes_queue_without_transition(self):
        from unittest.mock import patch
        from atr_zotero_workbench.human_input import attach_review_assessment_to_v2
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); out = root / 'out'; v2 = root / 'v2'
            packets = out / 'human-input' / 'review-packets'; packets.mkdir(parents=True); v2.mkdir()
            (packets / 'HRP-a.json').write_text(json.dumps({'artifact_type':'human-review-packet','packet_id':'HRP-a'}))
            (out / 'human-input' / 'review-queue.json').write_text(json.dumps({'schema_version':'0.1','projection':'codex-review-queue','items':[{'id':'a','status':'pending_human_and_codex_review'}]}))
            assessment_path = root / 'assessment.json'
            assessment_path.write_text(json.dumps({
                'artifact_type':'human-review-assessment','assessment_id':'HRA-a',
                'packet_id':'HRP-a','disposition_id':'HRD-a','outcome':'REQUEST_EVIDENCE',
                'required_followup_artifact_kind':'evidence-review',
            }))
            atrctl = root / 'atrctl.py'; atrctl.write_text('# placeholder')
            class Result:
                returncode = 0; stderr = ''; stdout = 'sha256:assessment\n'
            with patch('atr_zotero_workbench.human_input.subprocess.run', return_value=Result()) as invoke:
                result = attach_review_assessment_to_v2(out, v2, assessment_path, 'subject-1', 3, atrctl)
            self.assertFalse(result['lifecycle_changed'])
            self.assertEqual(result['outcome'], 'REQUEST_EVIDENCE')
            self.assertIn('record-human-assessment', invoke.call_args.args[0])
            self.assertIn('--expected-version', invoke.call_args.args[0])
            queue = json.loads((out / 'human-input' / 'review-queue.json').read_text())
            self.assertEqual(queue['items'][0]['status'], 'review_assessment_recorded')
            self.assertEqual(queue['items'][0]['assessment_history'][0]['artifact_id'], 'sha256:assessment')

    def test_projects_existing_harness_knowledge_and_problem_artifacts_without_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp); run = tmp_path / 'run'; (run / 'evidence').mkdir(parents=True); (run / 'knowledge' / 'research-problem-cards').mkdir(parents=True)
            (run / 'evidence' / 'sources.jsonl').write_text(json.dumps({'source_id':'P1','title':'Paper','url':'https://e.org','kind':'PAPER'}) + '\n')
            (run / 'evidence' / 'claims.jsonl').write_text(json.dumps({'claim_id':'C1.v1','text':'Claim'}) + '\n')
            (run / 'knowledge' / 'frontier-map.json').write_text(json.dumps({'domain':'NLP','frontier_tensions':[{'tension_id':'FT-1','question':'Why?','anchor_source_ids':['P1'],'dimensions':['a','b'],'competing_explanations':['x','y'],'freshness':'fresh'}]}))
            context = {'context_id':'KCTX-1','decision_node':'CLAIM_REVIEW','map_id':'FKM-1','unresolved':['collision'], 'valid_until':None, 'frontier_tension_ids':['FT-1'], 'contraction_path':[{'step_id':'CP-1','layer':'FRONTIER_TENSION','question':'Tension','invariant_preserved':'scope','excluded_explanations':['z'],'evidence_refs':['P1']}, {'step_id':'CP-2','layer':'CLAIM','question':'Claim question','invariant_preserved':'scope','excluded_explanations':['z'],'evidence_refs':['MISSING']} ]}
            (run / 'knowledge' / 'knowledge-context.test.json').write_text(json.dumps(context))
            opportunity = {'map_id':'OPP-1','scope':'Deployment friction','searched_through':'2026-01-01','valid_until':'2027-01-01','translation_policy':{'no_gap_certificate':True}, 'tension_clusters':[{'cluster_id':'OT-1','observed_tension':'People cannot audit a system outcome','actor':'reviewers','incumbent_practice':'trust score','material_consequence':'bad decisions','candidate_construct':'traceability','alternative_explanations':['a','b'],'translation_status':'WATCH','does_not_establish':'not a gap','signal_refs':['P1','MISSING']}]}
            (run / 'knowledge' / 'opportunity-map.json').write_text(json.dumps(opportunity))
            problem = {'problem_id':'RQ-1','claim_version':'C1.v1','research_question':'How do we distinguish two explanations for a reported pattern?','construct_of_interest':'Traceability quality across decisions','status_quo':'Current studies trust a single score','confounded_observation':'The score mixes two mechanisms','counterfactual_worlds':[{'label':'W1'},{'label':'W2'}],'decision_consequence':'Model selection would change','minimum_falsifier':'No discriminating result remains after audit','contribution_boundary':{},'evidence_layers':[{'kind':'LITERATURE','sources':['P1','MISSING']} ]}
            (run / 'knowledge' / 'research-problem-cards' / 'RQ-1.json').write_text(json.dumps(problem))
            (run / 'run-state.json').write_text(json.dumps({'run_id':'r'}))
            graph = build(run, tmp_path / 'out')
            self.assertTrue(any(node['kind'] == 'knowledge_step' for node in graph['nodes']))
            self.assertTrue(any(node['kind'] == 'real_world_tension' for node in graph['nodes']))
            problem_node = next(node for node in graph['nodes'] if node['kind'] == 'research_problem')
            self.assertEqual(problem_node['data']['minimum_falsifier'], 'No discriminating result remains after audit')
            explicit = [edge for edge in graph['edges'] if edge['relation'] in {'uses_explicit_evidence', 'grounded_in_explicit_signal', 'grounds_in_explicit_evidence_layer'}]
            self.assertTrue(explicit)
            self.assertFalse(any(edge['target'] == 'paper:MISSING' for edge in explicit))

    def test_research_problem_preserves_explicit_paper_roles(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp); run = tmp_path / 'run'; (run / 'evidence').mkdir(parents=True); (run / 'knowledge' / 'research-problem-cards').mkdir(parents=True)
            (run / 'evidence' / 'sources.jsonl').write_text(json.dumps({'source_id':'P1','title':'Paper','kind':'PAPER'}) + '\n')
            problem = {'problem_id':'RQ-1','status':'DRAFT_R0_NEEDS_OWNER_REVIEW','research_question':'A sufficiently long, method-free question that preserves multiple possible explanations for the observed mismatch.','paper_roles':[{'source_id':'P1','posture':'OBJECTIVE_DIAGNOSTIC','resolves':'localizes a mechanism','leaves_unresolved':'does not establish prevalence'},{'source_id':'MISSING','posture':'OBJECTIVE','resolves':'must not link','leaves_unresolved':'must not link'}]}
            (run / 'knowledge' / 'research-problem-cards' / 'RQ-1.json').write_text(json.dumps(problem))
            (run / 'run-state.json').write_text(json.dumps({'run_id':'r'}))
            graph = build(run, tmp_path / 'out')
            node = next(node for node in graph['nodes'] if node['kind'] == 'research_problem')
            self.assertEqual(node['data']['status'], 'DRAFT_R0_NEEDS_OWNER_REVIEW')
            role = next(edge for edge in graph['edges'] if edge['relation'] == 'has_explicit_problem_role')
            self.assertEqual((role['source'], role['target']), ('paper:P1', 'research_problem:RQ-1'))
            self.assertEqual(role['data']['leaves_unresolved'], 'does not establish prevalence')
            self.assertFalse(any(edge['source'] == 'paper:MISSING' for edge in graph['edges']))

    def test_research_problem_projects_explicit_finer_review_questions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); run = root / 'run'; (run / 'evidence').mkdir(parents=True); (run / 'knowledge' / 'research-problem-cards').mkdir(parents=True)
            (run / 'evidence' / 'sources.jsonl').write_text(json.dumps({'source_id':'P1','title':'Paper','kind':'PAPER'}) + '\n')
            problem = {'problem_id':'RQ-1','research_question':'How can a review distinguish two source-grounded mechanisms?','derived_questions':[{'question_id':'DQ-1','question':'Can a frozen item distinguish the two mechanisms?','status':'R2_REVIEW_TASK','smallest_discriminator':'a contract-bearing item','does_not_establish':'not a claim','source_ids':['P1','MISSING']}]} 
            (run / 'knowledge' / 'research-problem-cards' / 'RQ-1.json').write_text(json.dumps(problem))
            (run / 'run-state.json').write_text(json.dumps({'run_id':'r'}))
            graph = build(run, root / 'out')
            child = next(node for node in graph['nodes'] if node['kind'] == 'derived_research_question')
            self.assertEqual(child['data']['status'], 'R2_REVIEW_TASK')
            self.assertTrue(any(edge['relation'] == 'generates_finer_review_question' for edge in graph['edges']))
            self.assertTrue(any(edge['source'] == child['id'] and edge['target'] == 'paper:P1' for edge in graph['edges']))
            self.assertFalse(any(edge['source'] == child['id'] and edge['target'] == 'paper:MISSING' for edge in graph['edges']))

    def test_native_projection_materializes_research_problem_forest(self):
        tension = 'real_world_tension:T1'
        frontier = 'question:Q1'
        problem = 'research_problem:R1'
        derived = 'derived_question:R1:D1'
        graph = {
            'run': 'r',
            'nodes': [
                {'id': tension, 'kind': 'real_world_tension', 'label': 'Deployment tension', 'data': {'cluster_id': 'T1'}},
                {'id': frontier, 'kind': 'research_question', 'label': 'Which failure locus?', 'data': {'tension_id': 'Q1'}},
                {'id': problem, 'kind': 'research_problem', 'label': 'Which mechanism?', 'data': {'problem_id': 'R1'}},
                {'id': derived, 'kind': 'derived_research_question', 'label': 'Can one item discriminate?', 'data': {'question_id': 'D1'}},
                {'id': 'paper:P1', 'kind': 'paper', 'label': 'Paper', 'data': {'source_id': 'P1'}},
            ],
            'edges': [
                {'source': tension, 'target': 'paper:P1', 'relation': 'grounded_in_explicit_signal', 'data': {}},
                {'source': frontier, 'target': 'paper:P1', 'relation': 'anchored_by', 'data': {}},
                {'source': problem, 'target': 'paper:P1', 'relation': 'grounds_in_explicit_source_span', 'data': {}},
                {'source': problem, 'target': derived, 'relation': 'generates_finer_review_question', 'data': {}},
                {'source': derived, 'target': 'paper:P1', 'relation': 'cites_explicit_source', 'data': {}},
            ],
        }
        projection = native_projection(graph)
        by_kind = {obj['object_kind']: obj for obj in projection['objects'] if obj['object_kind'] != 'source_item'}
        self.assertEqual(by_kind['tension_note']['marker'], f'ATR Tension Node: {tension}')
        self.assertEqual(by_kind['frontier_question_note']['linked_source_ids'], ['P1'])
        self.assertEqual(by_kind['derived_question_note']['parent_graph_node_id'], problem)
        self.assertEqual(by_kind['derived_question_note']['linked_source_ids'], ['P1'])
        self.assertEqual(projection['collections']['research_tensions'], '01 · 现实世界张力')
        self.assertEqual(projection['collections']['research_current'], '03 · 当前问题卡')

    def test_derived_question_note_targets_exact_node_and_parent_problem(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); (out / 'human-input').mkdir()
            problem = 'research_problem:R1'
            derived = 'derived_question:R1:D1'
            graph = {
                'run': 'r',
                'nodes': [
                    {'id': problem, 'kind': 'research_problem', 'label': 'Which mechanism?', 'data': {'problem_id': 'R1'}},
                    {'id': derived, 'kind': 'derived_research_question', 'label': 'Can one item discriminate?', 'data': {'question_id': 'D1'}},
                ],
                'edges': [{'source': problem, 'target': derived, 'relation': 'generates_finer_review_question', 'data': {}}],
            }
            (out / 'graph.json').write_text(json.dumps(graph))
            (out / 'human-input' / 'inbox.jsonl').write_text(json.dumps({
                'event': 'human_note_modified', 'zotero_note_key': 'N-derived',
                'atr_derived_question_node_id': derived, 'atr_graph_node_id': derived,
            }) + '\n')
            item = impact_report(out)['affected'][0]
            self.assertEqual(item['review_target_type'], 'research_question')
            self.assertEqual(item['nearest_decision_objects'][0]['id'], derived)
            self.assertEqual(item['nearest_research_problems'][0]['problem_id'], 'R1')
            self.assertEqual(item['nearest_research_problems'][0]['distance_from_review_target'], 1)

    def test_research_problem_retains_draft_alongside_its_current_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp); run = tmp_path / 'run'; (run / 'evidence').mkdir(parents=True); (run / 'knowledge' / 'research-problem-cards').mkdir(parents=True)
            (run / 'evidence' / 'sources.jsonl').write_text('')
            base = {'problem_id': 'RQ-1', 'research_question': 'A sufficiently long question about attribution and executable contracts', 'counterfactual_worlds': []}
            (run / 'knowledge' / 'research-problem-cards' / 'RQ-1.draft.json').write_text(json.dumps({**base, 'status': 'DRAFT_R0_NEEDS_OWNER_REVIEW'}))
            (run / 'knowledge' / 'research-problem-cards' / 'RQ-1.v1.json').write_text(json.dumps({**base, 'status': 'R2_FOCUSED_REVIEW_NEEDS_OWNER_REVIEW', 'artifact_version': 'v1'}))
            graph = project_graph(load_legacy_run(run))
            problems = [node for node in graph['nodes'] if node['kind'] == 'research_problem']
            self.assertEqual(len(problems), 2)
            self.assertIn('research_problem:RQ-1', [node['id'] for node in problems])
            draft = next(node for node in problems if node['data']['status'].startswith('DRAFT_R0'))
            self.assertIn('RQ-1.draft.json', draft['id'])
            self.assertTrue(any(edge['relation'] == 'superseded_by_recorded_problem_version' for edge in graph['edges']))
            projection = native_projection(graph)
            problem_objects = [obj for obj in projection['objects'] if obj['object_kind'] == 'problem_note']
            self.assertEqual(len({obj['object_id'] for obj in problem_objects}), 2)
            self.assertEqual(len({obj['marker'] for obj in problem_objects}), 2)
            self.assertEqual(
                {obj['review_role'] for obj in problem_objects},
                {'HISTORICAL_VERSION', 'CURRENT_REVIEW_TARGET'},
            )

    def test_source_review_identifies_nearest_research_problem_for_codex(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); (out / 'human-input').mkdir()
            graph = {'nodes':[{'id':'paper:P1','kind':'paper','label':'Paper','data':{'source_id':'P1'}},{'id':'research_problem:R1','kind':'research_problem','label':'Which mechanism?','data':{'problem_id':'R1','status':'DRAFT_R0_NEEDS_OWNER_REVIEW'}}], 'edges':[{'source':'paper:P1','target':'research_problem:R1','relation':'has_explicit_problem_role','data':{}}]}
            (out / 'graph.json').write_text(json.dumps(graph))
            (out / 'human-input' / 'inbox.jsonl').write_text(json.dumps({'event':'human_note_modified','zotero_note_key':'N1','atr_source_id':'P1','review_stance':'CHALLENGES'}) + '\n')
            item = impact_report(out)['affected'][0]
            self.assertEqual(item['nearest_research_problems'][0]['problem_id'], 'R1')
            self.assertEqual(item['nearest_research_problems'][0]['distance_from_review_target'], 1)
            queue = refresh_review_queue(out)
            self.assertEqual(queue['items'][0]['nearest_research_problems'][0]['problem_id'], 'R1')

    def test_native_reader_annotation_enters_impact_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            graph = {
                'nodes': [
                    {'id':'paper:P1','kind':'paper','label':'Paper','data':{'source_id':'P1'}},
                    {'id':'research_problem:R1','kind':'research_problem','label':'Which mechanism?','data':{'problem_id':'R1'}},
                ],
                'edges': [{'source':'research_problem:R1','target':'paper:P1','relation':'grounds_in_explicit_source_span','data':{}}],
            }
            (out / 'graph.json').write_text(json.dumps(graph))
            (out / 'human-input').mkdir()
            event = {
                'event':'human_annotation_modified', 'at':'2026-01-01T00:00:00Z',
                'zotero_annotation_key':'A1', 'zotero_attachment_key':'PDF1',
                'atr_source_id':'P1', 'annotation_text':'original span',
                'annotation_comment':'this weakens the scope', 'annotation_page_label':'7',
                'zotero_open_uri':'zotero://open-pdf/library/items/PDF1?page=7&annotation=A1',
            }
            (out / 'human-input' / 'inbox.jsonl').write_text(json.dumps(event) + '\n')
            report = impact_report(out)
            self.assertEqual(report['latest_annotations'], 1)
            self.assertEqual(report['affected'][0]['review_target_type'], 'source')
            self.assertEqual(report['affected'][0]['nearest_research_problems'][0]['problem_id'], 'R1')
            self.assertEqual(report['affected'][0]['zotero_open_uri'], event['zotero_open_uri'])
            packet_path = Path(materialize_review_packets(out)['written'][0])
            packet = json.loads(packet_path.read_text())
            self.assertEqual(packet['created_from']['event_type'], 'human_annotation_modified')
            self.assertEqual(packet['review']['annotation']['comment'], 'this weakens the scope')
            self.assertEqual(packet['review']['zotero_open_uri'], event['zotero_open_uri'])
            self.assertIn(f"]({event['zotero_open_uri']})", (out / 'human-input' / 'review-links.md').read_text())
            queue = refresh_review_queue(out)
            self.assertEqual(queue['items'][0]['zotero_open_uri'], event['zotero_open_uri'])

    def test_reader_feedback_does_not_leak_through_run_or_domain_containment(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            graph = {
                'nodes': [
                    {'id':'paper:P1','kind':'paper','label':'Reviewed paper','data':{'source_id':'P1'}},
                    {'id':'concept:domain','kind':'concept','label':'Broad domain','data':{}},
                    {'id':'run:r','kind':'run','label':'Run','data':{}},
                    {'id':'claim:UNRELATED','kind':'claim','label':'Unrelated claim','data':{'claim_id':'UNRELATED'}},
                ],
                'edges': [
                    {'source':'concept:domain','target':'paper:P1','relation':'has_evidence','data':{}},
                    {'source':'run:r','target':'concept:domain','relation':'explores','data':{}},
                    {'source':'run:r','target':'claim:UNRELATED','relation':'records_claim','data':{}},
                ],
            }
            (out / 'graph.json').write_text(json.dumps(graph))
            (out / 'human-input').mkdir()
            (out / 'human-input' / 'inbox.jsonl').write_text(json.dumps({
                'event':'human_annotation_modified', 'zotero_annotation_key':'A1', 'atr_source_id':'P1',
            }) + '\n')
            item = impact_report(out)['affected'][0]
            self.assertEqual(item['review_path_policy'], 'EXPLICIT_SOURCE_DECISION_RELATIONS_ONLY')
            self.assertEqual(item['nearest_decision_objects'], [])
            self.assertEqual(item['related_claims'], [])

    def test_problem_note_is_a_precise_review_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            graph = {
                'nodes': [
                    {'id':'research_problem:R1','kind':'research_problem','label':'Which mechanism?','data':{'problem_id':'R1'}},
                    {'id':'paper:P1','kind':'paper','label':'Paper','data':{'source_id':'P1'}},
                ],
                'edges': [{'source':'research_problem:R1','target':'paper:P1','relation':'grounds_in_explicit_source_span','data':{}}],
            }
            (out / 'graph.json').write_text(json.dumps(graph))
            (out / 'human-input').mkdir()
            (out / 'human-input' / 'inbox.jsonl').write_text(json.dumps({
                'event':'human_note_modified', 'zotero_note_key':'N1', 'atr_problem_id':'R1',
            }) + '\n')
            item = impact_report(out)['affected'][0]
            self.assertEqual(item['review_target_type'], 'research_problem')
            self.assertEqual(item['nearest_decision_objects'][0]['id'], 'research_problem:R1')
            self.assertEqual(item['nearest_decision_objects'][0]['distance_from_review_target'], 0)

    def test_topic_note_maps_to_active_v2_subject_without_advancing_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            graph = {
                'run':'r',
                'nodes': [
                    {'id':'run:r','kind':'run','label':'Run','data':{}},
                    {'id':'subject:S1','kind':'atr_v2_subject','label':'Topic','data':{'active':True,'state':'INTAKE'}},
                ],
                'edges': [{'source':'run:r','target':'subject:S1','relation':'tracks_subject','data':{}}],
            }
            (out / 'graph.json').write_text(json.dumps(graph))
            (out / 'human-input').mkdir()
            (out / 'human-input' / 'inbox.jsonl').write_text(json.dumps({
                'event':'human_note_modified', 'zotero_note_key':'N-topic', 'atr_run':'r',
            }) + '\n')
            item = impact_report(out)['affected'][0]
            self.assertEqual(item['review_target_type'], 'topic')
            self.assertEqual(item['nearest_decision_objects'][0]['id'], 'subject:S1')
            packet = json.loads(Path(materialize_review_packets(out)['written'][0]).read_text())
            self.assertEqual(packet['review']['run_id'], 'r')
            self.assertEqual(packet['required_owner_decision']['invariant'], 'This packet cannot itself modify a claim, ATR lifecycle, gate, source record, or historical projection.')

    def test_knowledge_note_targets_exact_concept_and_traces_to_problem(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            concept = 'knowledge_concept:K1:child'
            graph = {
                'run':'r',
                'nodes': [
                    {'id':concept,'kind':'knowledge_concept','label':'Executable values','data':{'concept_id':'child'}},
                    {'id':'paper:P1','kind':'paper','label':'Paper','data':{'source_id':'P1'}},
                    {'id':'research_problem:R1','kind':'research_problem','label':'Which failure?','data':{'problem_id':'R1'}},
                ],
                'edges': [
                    {'source':concept,'target':'paper:P1','relation':'defines_with_explicit_source','data':{}},
                    {'source':'research_problem:R1','target':'paper:P1','relation':'grounds_in_explicit_source_span','data':{}},
                ],
            }
            (out / 'graph.json').write_text(json.dumps(graph))
            (out / 'human-input').mkdir()
            (out / 'human-input' / 'inbox.jsonl').write_text(json.dumps({
                'event':'human_note_modified', 'zotero_note_key':'N-knowledge',
                'atr_knowledge_node_id':concept, 'atr_graph_node_id':concept,
            }) + '\n')
            item = impact_report(out)['affected'][0]
            self.assertEqual(item['review_target_type'], 'knowledge')
            self.assertEqual(item['nearest_decision_objects'][0]['id'], concept)
            self.assertEqual(item['nearest_research_problems'][0]['problem_id'], 'R1')
            self.assertEqual(item['nearest_research_problems'][0]['distance_from_review_target'], 2)

    def test_versioned_problem_note_maps_to_exact_historical_graph_node(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            old = 'research_problem:R1:draft'
            current = 'research_problem:R1'
            graph = {
                'nodes': [
                    {'id':old,'kind':'research_problem','label':'Draft','data':{'problem_id':'R1'}},
                    {'id':current,'kind':'research_problem','label':'Current','data':{'problem_id':'R1'}},
                ],
                'edges': [{'source':old,'target':current,'relation':'superseded_by_recorded_problem_version','data':{}}],
            }
            (out / 'graph.json').write_text(json.dumps(graph))
            (out / 'human-input').mkdir()
            (out / 'human-input' / 'inbox.jsonl').write_text(json.dumps({
                'event':'human_note_modified', 'zotero_note_key':'N-old',
                'atr_problem_id':'R1', 'atr_graph_node_id':old,
            }) + '\n')
            item = impact_report(out)['affected'][0]
            self.assertEqual(item['annotation_graph_node_id'], old)
            self.assertEqual(item['nearest_decision_objects'][0]['id'], old)

    def test_projects_landscape_brief_with_explicit_source_locators(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp); run = tmp_path / 'run'; (run / 'evidence').mkdir(parents=True); (run / 'knowledge').mkdir()
            (run / 'evidence' / 'sources.jsonl').write_text(json.dumps({'source_id':'P1','title':'Paper','url':'https://e.org','kind':'PAPER'}) + '\n')
            brief = {'brief_id':'LB-1','immutable':True,'created_at':'2026-01-03T00:00:00Z','question':'Which failure locus?','disposition':'NEEDS_EVIDENCE','observed_tension':'A strict mismatch may have two causes','sources_do_not_establish':['a general defect'],'smallest_next_discriminator':'Audit frozen items','inspected_sources':[{'source_id':'P1','locator':'p. 2','observation':'Observed a localized mismatch'},{'source_id':'MISSING','locator':'p. 4','observation':'must not become an edge'}]}
            (run / 'knowledge' / 'landscape-brief-test.json').write_text(json.dumps(brief))
            (run / 'run-state.json').write_text(json.dumps({'run_id':'r'}))
            graph = build(run, tmp_path / 'out')
            node = next(node for node in graph['nodes'] if node['kind'] == 'landscape_brief')
            self.assertEqual(node['data']['disposition'], 'NEEDS_EVIDENCE')
            edge = next(edge for edge in graph['edges'] if edge['relation'] == 'inspects_explicit_source')
            self.assertEqual((edge['source'], edge['target']), ('landscape_brief:LB-1', 'paper:P1'))
            self.assertEqual(edge['data']['locator'], 'p. 2')
            self.assertFalse(any(edge['target'] == 'paper:MISSING' for edge in graph['edges']))
            self.assertEqual(graph['timeline'][-1]['kind'], 'landscape_brief')

    def test_projects_item_contract_audit_as_missing_evidence_not_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp); run = tmp_path / 'run'; (run / 'evidence').mkdir(parents=True)
            (run / 'evidence' / 'sources.jsonl').write_text(json.dumps({'source_id':'P1','title':'Paper','kind':'PAPER'}) + '\n')
            audit = {'audit_id':'ICA-1','recorded_at':'2026-01-03T00:00:00Z','source_id':'P1','access_status':'UNAVAILABLE','item_contract_visibility':'NONE','independent_action_oracle':'NONE','observed':'Release cannot be audited','does_not_establish':'no item claim','disposition':'PARK','next_required_action':'find a pinned release'}
            (run / 'evidence' / 'item-contract-audit.jsonl').write_text(json.dumps(audit) + '\n')
            (run / 'run-state.json').write_text(json.dumps({'run_id':'r'}))
            graph = build(run, tmp_path / 'out')
            node = next(node for node in graph['nodes'] if node['kind'] == 'evidence_audit')
            self.assertEqual(node['data']['access_status'], 'UNAVAILABLE')
            self.assertTrue(any(edge['relation'] == 'audits_explicit_source' and edge['target'] == 'paper:P1' for edge in graph['edges']))
            self.assertFalse(any(node['kind'] == 'claim' for node in graph['nodes']))

    def test_projects_source_grounded_concept_tree_without_inferred_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp); run = tmp_path / 'run'; (run / 'evidence').mkdir(parents=True); (run / 'knowledge').mkdir()
            (run / 'evidence' / 'sources.jsonl').write_text(json.dumps({'source_id':'P1','title':'Paper','kind':'PAPER'}) + '\n')
            concept_map = {'map_id':'KMAP-1','created_at':'2026-01-04T00:00:00Z','status':'PARTIAL_SOURCE_GROUNDED','scope':'A bounded map','does_not_establish':'not an ontology','concepts':[{'concept_id':'root','label':'Root','definition':'root definition','source_ids':['P1'],'does_not_establish':'not causal','depth':0},{'concept_id':'child','parent_id':'root','label':'Child','definition':'child definition','source_ids':['P1','MISSING'],'does_not_establish':'not complete','depth':1}]}
            (run / 'knowledge' / 'concept-map.json').write_text(json.dumps(concept_map))
            (run / 'run-state.json').write_text(json.dumps({'run_id':'r'}))
            graph = build(run, tmp_path / 'out')
            root = next(node for node in graph['nodes'] if node['id'] == 'knowledge_concept:KMAP-1:root')
            self.assertEqual(root['data']['definition'], 'root definition')
            self.assertTrue(any(edge['relation'] == 'roots_concept' and edge['target'] == root['id'] for edge in graph['edges']))
            self.assertTrue(any(edge['relation'] == 'specializes_concept' and edge['target'] == 'knowledge_concept:KMAP-1:child' for edge in graph['edges']))
            source_edges = [edge for edge in graph['edges'] if edge['relation'] == 'defines_with_explicit_source']
            self.assertEqual(len(source_edges), 2)
            self.assertFalse(any(edge['target'] == 'paper:MISSING' for edge in source_edges))
            self.assertTrue(any(item['kind'] == 'concept_map' for item in graph['timeline']))

    def test_timeline_uses_only_timestamped_artifacts_in_chronological_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp); run = tmp_path / 'run'; (run / 'evidence').mkdir(parents=True); (run / 'observability').mkdir()
            (run / 'evidence' / 'sources.jsonl').write_text('')
            (run / 'evidence' / 'claims.jsonl').write_text(json.dumps({'claim_id':'C1.v1','text':'Claim','recorded_at':'2026-01-02T00:00:00Z'}) + '\n')
            (run / 'observability' / 'skill-events.jsonl').write_text(json.dumps({'event_id':'SK1','skill':'discovery','event':'END','status':'SUCCEEDED','timestamp':'2026-01-01T00:00:00Z'}) + '\n')
            (run / 'run-state.json').write_text(json.dumps({'run_id':'r'}))
            graph = build(run, tmp_path / 'out')
            self.assertEqual([item['kind'] for item in graph['timeline']], ['skill_event', 'claim'])
            self.assertEqual(graph['timeline'][0]['id'], 'SK1')

    def test_timeline_labels_declared_skills_as_activity_not_execution_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); run = root / 'run'; (run / 'evidence').mkdir(parents=True); (run / 'observability').mkdir()
            (run / 'evidence' / 'sources.jsonl').write_text('')
            (run / 'observability' / 'skill-events.jsonl').write_text(json.dumps({'event_id':'SK-1','timestamp':'2026-01-01T00:00:00+00:00','skill':'codex-exec','event':'END','status':'SUCCEEDED','declared_skills':['posterior-review'],'activity_boundary':'declared only'}) + '\n')
            (run / 'run-state.json').write_text(json.dumps({'run_id':'r'}))
            graph = build(run, root / 'out')
            event = next(item for item in graph['timeline'] if item['id'] == 'SK-1')
            self.assertIn('声明技能：posterior-review', event['label'])
            self.assertEqual(event['activity_boundary'], 'declared only')

    def test_program_view_shares_sources_but_preserves_branch_claims(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp); catalog_dir = tmp_path / 'catalog'; catalog_dir.mkdir()
            for name, claim in [('a', 'C1.v1'), ('b', 'C2.v1')]:
                run = tmp_path / name; (run / 'evidence').mkdir(parents=True)
                (run / 'evidence' / 'sources.jsonl').write_text(json.dumps({'source_id':'P1','title':'Shared paper','kind':'PAPER'}) + '\n')
                (run / 'evidence' / 'claims.jsonl').write_text(json.dumps({'claim_id':claim,'text':name + ' claim'}) + '\n')
                (run / 'run-state.json').write_text(json.dumps({'run_id':name}))
            catalog = {'programs':[{'key':'p','label':'Program','root_question':'A root question','branches':[{'run':'../a','role':'first','disposition':'retain'},{'run':'../b','role':'second','disposition':'retain'}]}]}
            catalog_path = catalog_dir / 'programs.json'; catalog_path.write_text(json.dumps(catalog))
            graph = build_program(catalog_path, 'p', tmp_path / 'out')
            self.assertEqual(sum(node['kind'] == 'paper' for node in graph['nodes']), 1)
            self.assertEqual(sum(node['kind'] == 'claim' for node in graph['nodes']), 2)
            self.assertEqual(sum(edge['relation'] == 'contains_historical_branch' for edge in graph['edges']), 2)
            self.assertEqual(graph['program']['root_question'], 'A root question')
