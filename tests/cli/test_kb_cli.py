from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from deeptutor_cli import kb as kb_module
from deeptutor_cli.kb import _collect_documents
from deeptutor_cli.main import app

runner = CliRunner()


def test_collect_documents_from_directory_matches_uppercase_extensions(tmp_path: Path) -> None:
    docs_dir = tmp_path / "资料"
    docs_dir.mkdir()
    upper_pdf = docs_dir / "报告.PDF"
    upper_pdf.write_bytes(b"%PDF-1.4")
    nested = docs_dir / "nested"
    nested.mkdir()
    upper_md = nested / "README.MD"
    upper_md.write_text("hello", encoding="utf-8")

    collected = [Path(path).name for path in _collect_documents([], str(docs_dir))]

    assert collected == ["README.MD", "报告.PDF"]


class _FakeKbManager:
    def __init__(self, base_dir: Path, names: list[str]) -> None:
        self.base_dir = base_dir
        self._names = list(names)

    def list_knowledge_bases(self) -> list[str]:
        return list(self._names)


def _patch_diagnose(monkeypatch) -> list[tuple[str, str, str]]:
    import deeptutor.services.rag.pipelines.ima.diagnose as diagnose_module

    calls: list[tuple[str, str, str]] = []

    async def fake_diagnose(kb_base_dir, kb_name, query, *, client_builder=None):
        calls.append((kb_base_dir, kb_name, query))
        return diagnose_module.ImaDiagnosis(
            kb_name=kb_name,
            query=query,
            configured=True,
            credential_source=diagnose_module.CREDENTIAL_SOURCE_ACCOUNT,
            knowledge_base_id_fingerprint="deadbeef",
            remote=[{"method": "POST", "status_code": 200, "code": "success"}],
            documents=3,
            folders=0,
            sources=1,
            hydration_targets=1,
            hydrated=1,
            hydration_failed=0,
            evidence_chars=64,
            retrieval_status="ok",
        )

    monkeypatch.setattr(diagnose_module, "diagnose_knowledge_base", fake_diagnose)
    return calls


def test_diagnose_ima_prints_the_redacted_report(monkeypatch, tmp_path: Path) -> None:
    calls = _patch_diagnose(monkeypatch)
    manager = _FakeKbManager(tmp_path, ["ima-kb"])
    monkeypatch.setattr(kb_module, "_get_kb_manager", lambda: manager)

    result = runner.invoke(app, ["kb", "diagnose-ima", "ima-kb", "--query", "why empty?"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["kb_name"] == "ima-kb"
    assert payload["retrieval_status"] == "ok"
    assert payload["knowledge_base_id_fingerprint"] == "deadbeef"
    assert calls == [(str(tmp_path), "ima-kb", "why empty?")]


def test_diagnose_ima_exits_one_for_unknown_kb(monkeypatch, tmp_path: Path) -> None:
    calls = _patch_diagnose(monkeypatch)
    manager = _FakeKbManager(tmp_path, ["other-kb"])
    monkeypatch.setattr(kb_module, "_get_kb_manager", lambda: manager)

    result = runner.invoke(app, ["kb", "diagnose-ima", "missing-kb", "--query", "why"])

    assert result.exit_code == 1
    assert "not found" in result.stdout.lower()
    assert calls == []
