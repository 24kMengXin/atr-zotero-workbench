import json
import tempfile
import unittest
from pathlib import Path
from atr_zotero_workbench.app import build, build_program
from atr_zotero_workbench.core import load_legacy_run, project_graph
from atr_zotero_workbench.zotero import sync_web_api
from atr_zotero_workbench.human_input import impact_report, materialize_review_packets, refresh_review_queue

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
