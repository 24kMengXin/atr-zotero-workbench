#!/usr/bin/env python3
"""Build claim-scoped posterior reviews for the first three pilot problems."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "programs" / "v2-intakes" / "pilot-reductions"
CACHE = ROOT / ".runtime" / "collision-review"


def source(source_id: str, title: str, url: str, cache_name: str, locator: str,
           comparison_type: str, finding: str, does_not_establish: str) -> dict:
    path = CACHE / cache_name
    if not path.is_file():
        raise FileNotFoundError(path)
    return {
        "source_id": source_id,
        "title": title,
        "url": url,
        "local_cache_path": str(path.relative_to(ROOT)),
        "cache_role": "REPO_LOCAL_GITIGNORED_VERIFICATION_CACHE_NOT_ZOTERO_ATTACHMENT",
        "content_digest": f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}",
        "fulltext_state": "FULLTEXT_INSPECTED",
        "locator": locator,
        "comparison_type": comparison_type,
        "finding": finding,
        "does_not_establish": does_not_establish,
    }


def review(program: str, artifact_id: str, problem_id: str, disposition: str,
           inspected_sources: list[dict], comparisons: dict, coverage_limits: list[str],
           surviving_boundary: str, alternatives: list[str], next_evidence: list[str]) -> dict:
    payload = {
        "artifact_type": "collision-review",
        "schema_version": "1.0",
        "artifact_id": artifact_id,
        "program_key": program,
        "input_problem_case_id": problem_id,
        "status": "CLAIM_SCOPED_POSTERIOR_REVIEW_NOT_GATE",
        "review_mode": "POSTERIOR_REVIEW_WORKER",
        "reviewer_role": "posterior-review",
        "reviewer_isolation_claimed": False,
        "source_cutoff": "2026-07-19",
        "query_log": [
            "exact problem wording and quoted constructs",
            "adjacent benchmark, stateful tool-use, harness, and evaluation mechanisms",
            "primary paper full text inspected rather than title/abstract-only matching",
        ],
        "inspected_sources": inspected_sources,
        "comparisons": comparisons,
        "coverage_limits": coverage_limits,
        "surviving_boundary": surviving_boundary,
        "alternative_explanations": alternatives,
        "disposition": disposition,
        "next_evidence": next_evidence,
        "does_not_authorize": "This worker output does not establish novelty, pass a gate, choose a route, mutate lifecycle state, or certify an independent review.",
    }
    required = ("exact", "claim", "mechanism", "compositional", "adjacent")
    if disposition not in {"REFRAME", "NEEDS_EVIDENCE"}:
        raise ValueError(disposition)
    if any(key not in comparisons for key in required) or not inspected_sources:
        raise ValueError(f"incomplete collision review: {program}")
    return payload


def write(program: str, payload: dict) -> None:
    path = OUT / program / "collision-review.json"
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != rendered:
        raise ValueError(f"refusing to rewrite non-identical review: {path}")
    path.write_text(rendered, encoding="utf-8")


def main() -> None:
    harness = source(
        "SRC-HARNESS-BENCH-2026", "Harness-Bench: Evaluating Agent Harnesses for Large Language Models",
        "https://arxiv.org/abs/2605.27922", "harness-bench.pdf", "pp. 1-2, 7-8", "CLAIM_COLLISION",
        "Shows large configuration-level score variation and a failure taxonomy, while explicitly warning that the diagnostics are not causal decomposition of individual mechanisms.",
        "Which individual contract field caused a score change or whether a model-only comparison is valid.",
    )
    agent_eval = source(
        "SRC-AGENTEVAL-2026", "AgentEval: A Step-Level Evaluation Framework for LLM Agents",
        "https://arxiv.org/abs/2604.23581", "agent-eval.pdf", "pp. 1, 6-8", "MECHANISM_COLLISION",
        "Adds step-level detection and root-cause localization, but its root-cause analysis is a practical heuristic rather than formal causal inference and its workflows are English-only.",
        "Causal attribution across harness fields, multilingual transport, or evaluator independence.",
    )
    stateful = source(
        "SRC-STATEFUL-TOOL-USE-2025", "Rethinking Stateful Tool Use in Multi-Turn LLM Agents",
        "https://aclanthology.org/2025.findings-acl.1249/", "stateful-tool-use.pdf", "pp. 1-2, 9", "CLAIM_COLLISION",
        "Directly studies the full stateful tool-use lifecycle across multiple turns, but excludes agent-framework effects and does not isolate a language-control plane.",
        "Whether a language switch loses task memory or merely changes retrieval, locale assets, routing, or judging.",
    )
    unitool = source(
        "SRC-UNITOOLCALL-2026", "UniToolCall: Unified Tool Calling via Question-Answer-Observation-Answer",
        "https://arxiv.org/abs/2604.11557", "unitoolcall.pdf", "pp. 1-2, 9", "MECHANISM_COLLISION",
        "Directly identifies representation fragmentation and evaluation mismatch, then standardizes the tool-call representation and strict-plus-semantic evaluation boundary.",
        "Multilingual long-horizon causal attribution or transport beyond the standardized representation and evaluation boundary.",
    )
    safe_tool = source(
        "SRC-VERIFIABLY-SAFE-TOOL-USE-2026", "Towards Verifiably Safe Tool Use for LLM Agents",
        "https://arxiv.org/abs/2601.08012", "safe-tool-use.pdf", "pp. 1-5", "MECHANISM_COLLISION",
        "Frames tool safety as verifiable conformance to explicit specifications at consequential calls, directly covering commit-aware safety mechanisms without testing multilingual authorization effects.",
        "Whether language changes recognition of an authorization boundary after comprehension and translation controls.",
    )
    mt_eval = source(
        "SRC-AI-ASSISTED-MT-EVAL-2024", "AI-Assisted Human Evaluation of Machine Translation",
        "https://arxiv.org/abs/2406.12419", "ai-assisted-mt-eval.pdf", "pp. 1-2, 8-10", "CLAIM_COLLISION",
        "Shows that AI-proposed error spans can reduce human MT-evaluation effort while maintaining evaluation quality in a bounded setup, and explicitly discusses priming, bias, metric choice, and intended-use limits.",
        "A universal routing threshold, transport across use cases/language pairs, or improved end-user agency under natural errors.",
    )
    audit_trails = source(
        "SRC-LLM-AUDIT-TRAILS-2026", "Audit Trails for Accountability in Large Language Models",
        "https://arxiv.org/abs/2601.20727", "audit-trails.pdf", "pp. 1-2, 11-15", "CLAIM_COLLISION",
        "Directly proposes chronological, tamper-evident, context-rich lifecycle and decision records with append-only storage and auditor-facing reconstruction, while acknowledging scale, composition, access, privacy, and proportionality limits.",
        "That added records improve scientific decisions, human learning, calibrated beliefs, or held-out validity rather than documentation volume.",
    )

    action_program = "multilingual-agent-action-attribution"
    write(action_program, review(
        action_program, "ARH-MULTILINGUAL-ACTION-ATTRIBUTION-R0-COL-001.v1",
        "PC-multilingual-action-semantics-interface.draft-v1", "REFRAME", [unitool],
        {
            "exact": ["No inspected source asks the full long-horizon multilingual factorial question verbatim."],
            "claim": ["MLCL already separates semantic intent from executable parameter-language convention in controlled single-turn calls."],
            "mechanism": ["UniToolCall already treats representation fragmentation and evaluation mismatch as load-bearing tool-call mechanisms."],
            "compositional": ["MLCL plus UniToolCall covers much of the broad semantic-versus-interface contrast; breadth alone is not a surviving gap."],
            "adjacent": ["MASSIVE-Agents supplies multilingual coverage but not causal-layer isolation."],
        },
        ["Fresh full-text review added one direct mechanism source; the existing MLCL and MASSIVE source spans remain the comparison baseline.", "No deployment incidence or broad language-family coverage was established."],
        "A narrower, testable boundary remains: a revision-pinned long-horizon factorial crossing query, schema, parameter-value, and evaluator languages while holding intent and execution semantics fixed, with both executable and independent semantic adjudication.",
        ["Observed gaps may be translation/template artifacts.", "Strict parsing may disagree with semantic correctness.", "Long-horizon failures may arise from state or harness drift rather than action selection."],
        ["Build one paired factorial trace set before any route decision.", "Pre-register which trace fields distinguish semantic selection from representation and evaluator effects."],
    ))

    state_program = "multilingual-agent-state-continuity"
    write(state_program, review(
        state_program, "ARH-MULTILINGUAL-STATE-CONTINUITY-R0-COL-001.v1",
        "PC-multilingual-state-memory-control-plane.draft-v1", "NEEDS_EVIDENCE", [stateful],
        {
            "exact": ["No inspected paper isolates persistent-memory loss from language-control routing under the same pre-switch state snapshot."],
            "claim": ["Stateful Tool Use directly covers general multi-turn state lifecycle, so a broad claim that stateful tool use is unstudied is invalid."],
            "mechanism": ["Vendor documentation exposes language-control and locale-asset mechanisms, but does not measure failures."],
            "compositional": ["Stateful Tool Use plus HINDSIGHT, Mem2ActBench, PolyWorkBench, and vendor control-plane documentation makes the proposed boundary plausible but not yet empirically demonstrated."],
            "adjacent": ["Long-horizon execution and judge failures can be mislabeled as memory discontinuity."],
        },
        ["Only one new scholarly full text was added in this bounded review.", "The control-plane evidence remains product documentation rather than a paired incident or benchmark trace.", "No prevalence claim is supportable."],
        "The only defensible candidate boundary is a paired language-switch replay that snapshots task state and separately logs language selection, retrieval, locale assets, flow routing, and independent action adjudication.",
        ["Task memory was actually lost or overwritten.", "Memory remained intact but language-specific retrieval or locale assets changed.", "The judge conflated an execution failure with memory failure."],
        ["Acquire at least one paired real or benchmark trace containing both state snapshots and language-control variables.", "Do not route until the trace can discriminate memory loss from intact-state rerouting."],
    ))

    infra_program = "agent-infrastructure-and-evaluation-contracts"
    write(infra_program, review(
        infra_program, "ARH-AGENT-INFRA-EVAL-CONTRACTS-R0-COL-001.v1",
        "PC-agent-score-execution-contract-attribution.draft-v1", "REFRAME", [harness, agent_eval],
        {
            "exact": ["Harness-Bench already directly establishes that full agent configurations can materially change scores."],
            "claim": ["The broad question 'does the harness matter?' is answered and cannot support a new gap."],
            "mechanism": ["AgentEval localizes step failures; Causal Agent Replay intervenes on mocked trajectories; neither yields general live field-level causal attribution."],
            "compositional": ["Together these works cover configuration sensitivity, trace diagnosis, and synthetic intervention, leaving only a narrower execution-contract attribution boundary."],
            "adjacent": ["Reproducibility documentation records versions and commits but does not estimate causal effects."],
        },
        ["Harness-Bench explicitly limits its results to configuration-level diagnostics.", "AgentEval uses an LLM judge, English workflows, and heuristic root-cause analysis.", "Causal Agent Replay uses mocked tools and synthetic ground truth."],
        "A narrower boundary remains: identify the minimal revision-pinned execution-contract fields whose controlled change reverses a comparison, and require trace evidence that attributes the reversal without treating diagnostic symptoms as causes.",
        ["Provider or environment drift may explain the change.", "Evaluator interpretation may reverse a ranking without changing execution.", "Trace-local symptoms may be downstream of an earlier contract mismatch."],
        ["Construct one pinned pair differing in exactly one declared contract field.", "Test whether independent replay and adjudication agree on the first causal divergence."],
    ))

    authorization_program = "multilingual-agent-authorization-safety"
    write(authorization_program, review(
        authorization_program, "ARH-MULTILINGUAL-AUTHORIZATION-SAFETY-R0-COL-001.v1",
        "PC-multilingual-authorization-cross-layer-evidence.draft-v1", "NEEDS_EVIDENCE", [safe_tool],
        {
            "exact": ["No inspected work isolates a language-conditioned commit authorization effect after comprehension and translation controls."],
            "claim": ["AgentAbstain directly covers commit-level abstention, so commit-aware act-or-abstain behavior itself is not an unstudied construct."],
            "mechanism": ["Verifiably Safe Tool Use directly covers specification-based checks at consequential tool calls, but not language-conditioned authorization recognition."],
            "compositional": ["AgentAbstain, multilingual text-safety evidence, and specification-based tool safety jointly motivate the contrast but do not demonstrate the cross-layer effect."],
            "adjacent": ["General comprehension, translation error, and text-refusal variation can reproduce the observed pattern without an authorization-specific mechanism."],
        },
        ["Only one new mechanism paper was inspected in this bounded review.", "No paired multilingual commit trace controls comprehension and translation.", "Text-level safety benchmarks are not executable authorization evidence."],
        "A candidate boundary survives only as a controlled paired commit task where language alone varies and comprehension, translation, tool contract, and text-safety refusal are separately measured.",
        ["The instruction was misunderstood before authorization was evaluated.", "Translation changed the requested action.", "A general safety refusal proxy was mistaken for tool authorization."],
        ["Acquire or construct one deterministic paired commit trace with explicit authorization state.", "Do not route until an authorization-specific effect survives comprehension and translation controls."],
    ))

    representation_program = "multilingual-representation-and-data-decisions"
    write(representation_program, review(
        representation_program, "ARH-MULTILINGUAL-REPRESENTATION-DATA-R0-COL-001.v1",
        "PC-multilingual-mt-decision-routing.draft-v1", "REFRAME", [mt_eval],
        {
            "exact": ["No inspected study crosses routing threshold, feedback representation, natural errors, use case, and language pair in one preregistered decision design."],
            "claim": ["Quality Gate already studies threshold routing, and prior user-reliance work already studies implicit versus explicit feedback; neither broad component is new."],
            "mechanism": ["AI-assisted MT evaluation directly tests error-span assistance and exposes priming, bias, and evaluation-economy mechanisms."],
            "compositional": ["The three lines substantially cover routing, feedback form, and AI-assisted evaluation; a broad 'human review improves MT decisions' claim is overrun."],
            "adjacent": ["Rater disagreement and synthetic-error presentation can generate apparent gains that fail to transport to natural operational errors."],
        },
        ["The fresh paper evaluates annotator efficiency and evaluation quality, not end-user deployment decisions.", "Evidence remains narrow in language, metric, and error-generation conditions."],
        "The defensible remainder is a transport test of a fixed routing/feedback policy across natural errors, at least two use cases and language pairs, with rater disagreement and presentation explicitly modeled.",
        ["A single threshold overfits one language or use case.", "AI suggestions prime raters rather than improve decisions.", "Synthetic errors exaggerate the value of explicit feedback."],
        ["Define the decision loss and human-review reference before selecting a threshold.", "Run a small natural-error transport check before any proposal route."],
    ))

    governance_program = "atr-research-governance"
    write(governance_program, review(
        governance_program, "ARH-ATR-RESEARCH-GOVERNANCE-R0-COL-001.v1",
        "PC-auditable-research-process-human-learning.draft-v1", "REFRAME", [audit_trails],
        {
            "exact": ["No inspected source causally compares output-only and branch/evidence-preserving research under equal budget with blinded scientific and human-learning outcomes."],
            "claim": ["Audit Trails and the existing Hypothesis Evolution Protocol directly cover append-only, decision-linked auditability; auditability as a mechanism is not a gap."],
            "mechanism": ["Audit Trails supplies capture/store/use layers and human governance events; ARBOR supplies persistent hypothesis-tree optimization under fixed evaluators."],
            "compositional": ["These mechanisms cover much of the broad process-design proposal but leave causal value beyond documentation and fixed task metrics unresolved."],
            "adjacent": ["AutoResearchBench diagnoses literature-agent failures without establishing that more process artifacts improve human understanding or scientific validity."],
        },
        ["Audit Trails is a reference architecture and proof of concept, not a controlled scientific-decision study.", "Human learning and held-out scientific validity remain unmeasured.", "Privacy and proportionality may make complete trails harmful or infeasible."],
        "The surviving question must be causal and minimal: which preserved object—failed branch, source locator, belief update, or route reversal—changes an independent scientific decision or source-grounded human understanding under matched time and artifact budgets?",
        ["More records may only increase documentation burden.", "Fixed evaluators may reward process artifacts without improving science.", "Audit access and privacy constraints may reduce practical utility."],
        ["Test one preserved object at a time against output-only review under a matched budget.", "Measure decision reversal or source-grounded reconstruction, not preference for transparency."],
    ))


if __name__ == "__main__":
    main()
