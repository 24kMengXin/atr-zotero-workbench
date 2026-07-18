#!/usr/bin/env python3
"""Prepare a reproducible, repository-local Zotero smoke environment."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime" / "zotero-smoke"
sys.path.insert(0, str(ROOT / "src"))

from atr_zotero_workbench.zotero import export_native_projection  # noqa: E402


def write_smoke_pdf(path: Path) -> None:
    """Write one valid page for a local UI code-path test, not research evidence."""
    stream = b"BT /F1 18 Tf 72 720 Td (ATR repository-local Reader smoke fixture) Tj ET\n"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    body = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(body))
        body.extend(f"{index} 0 obj\n".encode())
        body.extend(obj + b"\nendobj\n")
    xref = len(body)
    body.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    body.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        body.extend(f"{offset:010d} 00000 n \n".encode())
    body.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    path.write_bytes(body)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="replace only .runtime/zotero-smoke")
    parser.add_argument("--run-key", help="explicit registered run to copy; defaults to active_run")
    parser.add_argument("--remote-pdf", action="store_true", help="exercise a mapped source pdf_url instead of the local fixture")
    parser.add_argument("--native-resolver", action="store_true", help="exercise Zotero's native available-file lookup for a DOI-only source")
    args = parser.parse_args()
    if args.remote_pdf and args.native_resolver:
        raise SystemExit("--remote-pdf and --native-resolver are mutually exclusive")
    if RUNTIME.exists():
        if not args.reset:
            raise SystemExit(f"smoke runtime already exists: {RUNTIME}; pass --reset to replace it")
        shutil.rmtree(RUNTIME)

    source_registry = json.loads((ROOT / "output" / "runs.json").read_text(encoding="utf-8"))
    selected_key = args.run_key or source_registry["active_run"]
    selected = next((row for row in source_registry["runs"] if row["key"] == selected_key), None)
    if not selected:
        available = ", ".join(row["key"] for row in source_registry["runs"])
        raise SystemExit(f"unknown --run-key {selected_key!r}; available: {available}")
    source_workspace = Path(selected["workspace"])
    workspace = RUNTIME / "workspace"
    profile = RUNTIME / "profile"
    data = RUNTIME / "data"
    (workspace / "zotero").mkdir(parents=True)
    profile.mkdir(parents=True)
    graph_path = workspace / "graph.json"
    shutil.copy2(source_workspace / "graph.json", graph_path)
    # Always derive the native map from the copied graph with the current
    # bridge contract.  Historical workspaces may carry an older projection,
    # and copying that cache would test stale output instead of today's code.
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    resolver_sources = []
    if args.native_resolver:
        for node in graph.get("nodes", []):
            node_data = node.get("data", {})
            url = str(node_data.get("url", ""))
            if node.get("kind") != "paper" or not node_data.get("pdf_url") or "doi.org/" not in url:
                continue
            node_data["doi"] = url.split("doi.org/", 1)[1]
            node_data["pdf_url"] = ""
            node_data["access_status"] = "RESOLVER_CANDIDATE"
            node_data["access_route"] = "ZOTERO_NATIVE_AVAILABLE_FILE"
            resolver_sources.append(node_data.get("source_id"))
        if not resolver_sources:
            raise SystemExit("selected run has no DOI source suitable for native-resolver smoke")
        graph_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    export_native_projection(graph, workspace)
    pdf_path = workspace / "reader-smoke-fixture.pdf"
    if not args.remote_pdf and not args.native_resolver:
        write_smoke_pdf(pdf_path)

    registry = {
        "schema_version": "0.2",
        "projection": "atr-workbench-run-registry",
        "selection_policy": "EXPLICIT_ACTIVATION_ONLY",
        "runs": [{
            "key": "smoke-current",
            "label": "Repository-local Zotero smoke fixture",
            "run_id": selected["run_id"],
            "run_dir": str(workspace),
            "workspace": str(workspace),
            "controller_kind": selected["controller_kind"],
            "authority_path": str(RUNTIME / "fixture-only-no-controller.sqlite"),
            "authority_scope": "TEST_FIXTURE_ONLY",
            "view_role": "CURRENT_RUN",
        }],
        "active_run": "smoke-current",
        "selection": {
            "mode": "EXPLICIT",
            "selected_key": "smoke-current",
            "reason": "Repository-local disposable Zotero runtime smoke fixture.",
        },
    }
    registry_path = RUNTIME / "registry.json"
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    subprocess.run([str(ROOT / "scripts" / "link_zotero_dev.sh"), str(profile), str(data)], check=True)
    with (profile / "user.js").open("a", encoding="utf-8") as handle:
        handle.write(f'user_pref("extensions.atr-zotero-workbench.registry", {json.dumps(str(registry_path))});\n')
        handle.write('user_pref("extensions.atr-zotero-workbench.devSmokeTestOnStartup", true);\n')
        handle.write('user_pref("extensions.atr-zotero-workbench.devSmokeFeedbackOnStartup", true);\n')
        handle.write('user_pref("extensions.atr-zotero-workbench.devSmokeReaderAnnotationOnStartup", true);\n')
        if not args.remote_pdf and not args.native_resolver:
            handle.write(f'user_pref("extensions.atr-zotero-workbench.devSmokePDFPath", {json.dumps(str(pdf_path))});\n')
        if args.native_resolver:
            handle.write('user_pref("extensions.atr-zotero-workbench.devSmokeNativeResolver", true);\n')
    metadata = {
        "source_active_run": source_registry["active_run"],
        "selected_run_key": selected_key,
        "source_workspace": str(source_workspace),
        "runtime": str(RUNTIME),
        "reader_fixture_mode": "ZOTERO_NATIVE_AVAILABLE_FILE" if args.native_resolver else ("MAPPED_REMOTE_PDF_ON_DEMAND" if args.remote_pdf else "REPOSITORY_LOCAL_SYNTHETIC_PDF"),
        "native_resolver_source_ids": resolver_sources,
        "safety_boundary": "REPOSITORY_LOCAL_GITIGNORED_DISPOSABLE_PROFILE_AND_DATA",
    }
    (RUNTIME / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(RUNTIME)


if __name__ == "__main__":
    main()
