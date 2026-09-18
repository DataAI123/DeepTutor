"""Tests for the ``deeptutor doctor`` command."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from deeptutor.services.doctor import (
    DoctorCheck,
    DoctorReport,
    _rag_check,
    run_diagnostics,
    run_startup_diagnostics,
)
from deeptutor_cli.main import app

runner = CliRunner()


def test_weknora_rag_check_skips_local_provider_preflight() -> None:
    def preflight(provider: str):
        raise AssertionError(f"WeKnora must not run local preflight: {provider}")

    check = _rag_check(
        {
            "knowledge_bases": {
                "remote": {
                    "rag_provider": "weknora",
                    "server_url": "http://localhost:8080",
                    "api_key": "secret",
                    "knowledge_base_id": "kb-1",
                }
            }
        },
        preflight,
    )

    assert check.status == "pass"
    assert check.detail == "Ready for configured provider(s): weknora."
    assert "secret" not in check.detail


def _llm_config(**overrides):
    values = {
        "model": "gpt-4o-mini",
        "provider_name": "openai",
        "provider_mode": "standard",
        "binding": "openai",
        "api_key": "sk-test-secret",
        "base_url": "https://api.openai.com/v1",
        "effective_url": "https://api.openai.com/v1",
        "api_version": None,
        "extra_headers": {},
        "reasoning_effort": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_local_diagnostics_pass_without_contacting_provider(tmp_path) -> None:
    online_calls = []

    async def online_probe(config) -> None:
        online_calls.append(config)

    report = await run_diagnostics(
        online=False,
        resolve_llm=lambda: _llm_config(),
        data_root=tmp_path,
        load_rag_config=lambda: {"defaults": {}, "knowledge_bases": {}},
        online_probe=online_probe,
    )

    assert report.ok is True
    assert online_calls == []
    assert {check.key: check.status for check in report.checks} == {
        "llm_config": "pass",
        "llm_credentials": "pass",
        "llm_endpoint": "pass",
        "storage": "pass",
        "rag": "skip",
        "online": "skip",
    }


@pytest.mark.asyncio
async def test_missing_required_llm_settings_fail_diagnostics(tmp_path) -> None:
    report = await run_diagnostics(
        resolve_llm=lambda: _llm_config(model="", api_key=""),
        data_root=tmp_path,
        load_rag_config=lambda: {"defaults": {}, "knowledge_bases": {}},
    )

    checks = {check.key: check for check in report.checks}
    assert report.ok is False
    assert checks["llm_config"].status == "fail"
    assert checks["llm_credentials"].status == "fail"


@pytest.mark.asyncio
async def test_storage_probe_failure_is_reported(tmp_path) -> None:
    file_instead_of_directory = tmp_path / "blocked"
    file_instead_of_directory.write_text("occupied", encoding="utf-8")

    report = await run_diagnostics(
        resolve_llm=lambda: _llm_config(),
        data_root=file_instead_of_directory,
        load_rag_config=lambda: {"defaults": {}, "knowledge_bases": {}},
    )

    storage = next(check for check in report.checks if check.key == "storage")
    assert storage.status == "fail"
    assert report.ok is False


@pytest.mark.asyncio
async def test_diagnostics_never_render_credentials_or_endpoint_secrets(tmp_path) -> None:
    api_key = "sk-top-secret-value"
    endpoint = "https://user:password@example.com/v1/path-secret?api_key=query-secret"

    report = await run_diagnostics(
        resolve_llm=lambda: _llm_config(
            api_key=api_key,
            base_url=endpoint,
            effective_url=endpoint,
        ),
        data_root=tmp_path,
        load_rag_config=lambda: {"defaults": {}, "knowledge_bases": {}},
    )

    rendered = json.dumps(report.to_dict())
    assert "https://example.com" in rendered
    for secret in (api_key, "user", "password", "path-secret", "query-secret"):
        assert secret not in rendered


@pytest.mark.asyncio
async def test_online_probe_failure_is_required_and_redacted(tmp_path) -> None:
    api_key = "sk-online-secret"

    async def failing_probe(config) -> None:
        raise RuntimeError(f"Provider rejected {config.api_key}")

    report = await run_diagnostics(
        online=True,
        resolve_llm=lambda: _llm_config(api_key=api_key),
        data_root=tmp_path,
        load_rag_config=lambda: {"defaults": {}, "knowledge_bases": {}},
        online_probe=failing_probe,
    )

    online = next(check for check in report.checks if check.key == "online")
    assert online.status == "fail"
    assert online.required is True
    assert api_key not in online.detail
    assert report.ok is False


@pytest.mark.asyncio
async def test_online_failure_redacts_configured_header_values(tmp_path) -> None:
    header_secret = "header-secret-value"

    async def failing_probe(config) -> None:
        raise RuntimeError(f"Provider rejected {config.extra_headers['X-Custom-Auth']}")

    report = await run_diagnostics(
        online=True,
        resolve_llm=lambda: _llm_config(
            extra_headers={"X-Custom-Auth": header_secret},
        ),
        data_root=tmp_path,
        load_rag_config=lambda: {"defaults": {}, "knowledge_bases": {}},
        online_probe=failing_probe,
    )

    online = next(check for check in report.checks if check.key == "online")
    assert online.status == "fail"
    assert header_secret not in online.detail


@pytest.mark.asyncio
async def test_online_probe_success_is_reported(tmp_path) -> None:
    probed_models = []

    async def successful_probe(config) -> None:
        probed_models.append(config.model)

    report = await run_diagnostics(
        online=True,
        resolve_llm=lambda: _llm_config(),
        data_root=tmp_path,
        load_rag_config=lambda: {"defaults": {}, "knowledge_bases": {}},
        online_probe=successful_probe,
    )

    online = next(check for check in report.checks if check.key == "online")
    assert online.status == "pass"
    assert probed_models == ["gpt-4o-mini"]
    assert report.ok is True


@pytest.mark.asyncio
async def test_online_probe_passes_one_bounded_token_parameter(monkeypatch, tmp_path) -> None:
    import deeptutor.services.llm as llm

    captured = {}

    async def fake_complete(**kwargs):
        captured.update(kwargs)
        return "OK"

    monkeypatch.setattr(llm, "complete", fake_complete)

    report = await run_diagnostics(
        online=True,
        resolve_llm=lambda: _llm_config(
            model="gpt-5-mini",
            provider_name="openrouter",
            provider_mode="gateway",
            binding="openrouter",
        ),
        data_root=tmp_path,
        load_rag_config=lambda: {"defaults": {}, "knowledge_bases": {}},
    )

    assert report.ok is True
    assert captured["max_tokens"] == 64
    assert "max_completion_tokens" not in captured


@pytest.mark.asyncio
async def test_online_probe_preserves_empty_custom_endpoint_api_key(monkeypatch, tmp_path) -> None:
    import deeptutor.services.llm as llm

    captured = {}

    async def fake_complete(**kwargs):
        captured.update(kwargs)
        return "OK"

    monkeypatch.setattr(llm, "complete", fake_complete)

    report = await run_diagnostics(
        online=True,
        resolve_llm=lambda: _llm_config(
            provider_name="custom",
            provider_mode="direct",
            binding="custom",
            api_key="",
            base_url="https://models.example.com/v1",
            effective_url="https://models.example.com/v1",
        ),
        data_root=tmp_path,
        load_rag_config=lambda: {"defaults": {}, "knowledge_bases": {}},
    )

    assert report.ok is True
    assert captured["api_key"] == ""


@pytest.mark.asyncio
async def test_online_probe_is_skipped_when_local_llm_checks_fail(tmp_path) -> None:
    online_calls = []

    async def online_probe(config) -> None:
        online_calls.append(config)

    report = await run_diagnostics(
        online=True,
        resolve_llm=lambda: _llm_config(model="", api_key=""),
        data_root=tmp_path,
        load_rag_config=lambda: {"defaults": {}, "knowledge_bases": {}},
        online_probe=online_probe,
    )

    online = next(check for check in report.checks if check.key == "online")
    assert online_calls == []
    assert online.status == "skip"
    assert report.ok is False


@pytest.mark.asyncio
async def test_local_provider_does_not_require_placeholder_api_key(tmp_path) -> None:
    report = await run_diagnostics(
        resolve_llm=lambda: _llm_config(
            provider_name="ollama",
            provider_mode="local",
            binding="ollama",
            api_key="sk-no-key-required",
            base_url="http://localhost:11434/v1",
            effective_url="http://localhost:11434/v1",
        ),
        data_root=tmp_path,
        load_rag_config=lambda: {"defaults": {}, "knowledge_bases": {}},
    )

    credentials = next(check for check in report.checks if check.key == "llm_credentials")
    assert credentials.status == "pass"
    assert report.ok is True


@pytest.mark.asyncio
async def test_unrecognized_headers_do_not_count_as_cloud_credentials(tmp_path) -> None:
    report = await run_diagnostics(
        resolve_llm=lambda: _llm_config(
            api_key="",
            extra_headers={"X-Trace-ID": "diagnostic-trace"},
        ),
        data_root=tmp_path,
        load_rag_config=lambda: {"defaults": {}, "knowledge_bases": {}},
    )

    credentials = next(check for check in report.checks if check.key == "llm_credentials")
    assert credentials.status == "fail"
    assert report.ok is False


@pytest.mark.asyncio
async def test_remote_custom_endpoint_without_credentials_is_advisory(tmp_path) -> None:
    report = await run_diagnostics(
        resolve_llm=lambda: _llm_config(
            provider_name="custom",
            provider_mode="direct",
            binding="custom",
            api_key="",
            base_url="https://models.example.com/v1",
            effective_url="https://models.example.com/v1",
        ),
        data_root=tmp_path,
        load_rag_config=lambda: {"defaults": {}, "knowledge_bases": {}},
    )

    credentials = next(check for check in report.checks if check.key == "llm_credentials")
    assert credentials.status == "skip"
    assert credentials.required is False
    assert report.ok is True


@pytest.mark.asyncio
async def test_custom_auth_header_counts_as_custom_endpoint_credentials(tmp_path) -> None:
    report = await run_diagnostics(
        resolve_llm=lambda: _llm_config(
            provider_name="custom",
            provider_mode="direct",
            binding="custom",
            api_key="",
            extra_headers={"X-Custom-Auth": "custom-secret"},
            base_url="https://models.example.com/v1",
            effective_url="https://models.example.com/v1",
        ),
        data_root=tmp_path,
        load_rag_config=lambda: {"defaults": {}, "knowledge_bases": {}},
    )

    credentials = next(check for check in report.checks if check.key == "llm_credentials")
    assert credentials.status == "pass"
    assert report.ok is True


@pytest.mark.asyncio
async def test_configured_rag_backend_reports_advisory_preflight_failure(tmp_path) -> None:
    report = await run_diagnostics(
        resolve_llm=lambda: _llm_config(),
        data_root=tmp_path,
        load_rag_config=lambda: {
            "defaults": {"rag_provider": "llamaindex"},
            "knowledge_bases": {"notes": {"rag_provider": "llamaindex"}},
        },
        rag_preflight=lambda provider: {
            "ok": False,
            "checks": [
                {
                    "label": "Active embedding model",
                    "ok": False,
                    "optional": False,
                }
            ],
        },
    )

    rag = next(check for check in report.checks if check.key == "rag")
    assert rag.status == "fail"
    assert rag.required is False
    assert "Active embedding model" in rag.detail
    assert report.ok is True


@pytest.mark.asyncio
async def test_lightrag_server_checks_per_kb_connection_without_engine_preflight(tmp_path) -> None:
    preflight_calls = []

    def preflight(provider):
        preflight_calls.append(provider)
        raise AssertionError("server-backed RAG should not use engine_preflight")

    report = await run_diagnostics(
        resolve_llm=lambda: _llm_config(),
        data_root=tmp_path,
        load_rag_config=lambda: {
            "defaults": {"rag_provider": "llamaindex"},
            "knowledge_bases": {
                "remote-notes": {
                    "rag_provider": "lightrag-server",
                    "server_url": "https://rag.example.com",
                }
            },
        },
        rag_preflight=preflight,
    )

    rag = next(check for check in report.checks if check.key == "rag")
    assert preflight_calls == []
    assert rag.status == "pass"
    assert "lightrag-server" in rag.detail


@pytest.mark.asyncio
async def test_lightrag_server_reports_missing_connection_as_advisory(tmp_path) -> None:
    report = await run_diagnostics(
        resolve_llm=lambda: _llm_config(),
        data_root=tmp_path,
        load_rag_config=lambda: {
            "defaults": {},
            "knowledge_bases": {
                "remote-notes": {"rag_provider": "lightrag-server"},
            },
        },
        rag_preflight=lambda provider: pytest.fail(f"unexpected engine preflight for {provider}"),
    )

    rag = next(check for check in report.checks if check.key == "rag")
    assert rag.status == "fail"
    assert rag.required is False
    assert "remote-notes" in rag.detail
    assert "no server URL configured" in rag.detail
    assert report.ok is True


def test_doctor_json_exits_nonzero_for_required_failure(monkeypatch) -> None:
    async def fake_run_diagnostics(*, online: bool):
        assert online is False
        return DoctorReport(
            online=False,
            checks=[
                DoctorCheck(
                    key="llm_config",
                    label="LLM configuration",
                    status="fail",
                    detail="No active LLM model is configured.",
                )
            ],
        )

    monkeypatch.setattr("deeptutor_cli.doctor.run_diagnostics", fake_run_diagnostics)

    result = runner.invoke(app, ["doctor", "--format", "json"])

    assert result.exit_code == 1, result.output
    assert json.loads(result.output) == {
        "ok": False,
        "online": False,
        "checks": [
            {
                "key": "llm_config",
                "label": "LLM configuration",
                "status": "fail",
                "detail": "No active LLM model is configured.",
                "required": True,
            }
        ],
    }


def test_doctor_online_rich_output_succeeds(monkeypatch) -> None:
    async def fake_run_diagnostics(*, online: bool):
        assert online is True
        return DoctorReport(
            online=True,
            checks=[
                DoctorCheck(
                    key="online",
                    label="Provider response",
                    status="pass",
                    detail="The model returned a response.",
                )
            ],
        )

    monkeypatch.setattr("deeptutor_cli.doctor.run_diagnostics", fake_run_diagnostics)

    result = runner.invoke(app, ["doctor", "--online"])

    assert result.exit_code == 0, result.output
    assert "PASS" in result.output
    assert "Provider response" in result.output


def _ready_launch_settings(**overrides):
    values = {"backend_port": 8001, "frontend_port": 3782, "source": "defaults"}
    values.update(overrides)
    return SimpleNamespace(**values)


async def _run_startup(**overrides) -> DoctorReport:
    kwargs = {
        "home": Path("/tmp/deeptutor"),
        "launch_settings": _ready_launch_settings(),
        "http_ready": lambda url: False,
        "port_in_use": lambda port: False,
        "port_listeners": lambda port: [],
        "module_available": lambda name: True,
        "which": lambda name: "/usr/bin/" + name,
        "local_web": lambda home: ("packaged", Path("/opt/deeptutor_web")),
        "parser_readiness": lambda: {"engine": "mineru", "ready": True, "reason": ""},
    }
    kwargs.update(overrides)
    return await run_startup_diagnostics(**kwargs)


@pytest.mark.asyncio
async def test_startup_diagnostics_reports_ready_when_everything_is_present() -> None:
    report = await _run_startup()

    assert report.ok is True
    assert report.online is False
    assert {check.key: check.status for check in report.checks} == {
        "backend": "pass",
        "frontend": "pass",
        "ports": "pass",
        "parser": "pass",
    }


@pytest.mark.asyncio
async def test_startup_diagnostics_notes_already_running_backend() -> None:
    report = await _run_startup(http_ready=lambda url: True)

    backend = next(check for check in report.checks if check.key == "backend")
    assert backend.status == "pass"
    assert "http://127.0.0.1:8001/" in backend.detail


@pytest.mark.asyncio
async def test_startup_diagnostics_flags_missing_backend_dependency() -> None:
    report = await _run_startup(module_available=lambda name: name != "uvicorn")

    assert report.ok is False
    backend = next(check for check in report.checks if check.key == "backend")
    assert backend.status == "fail"
    assert "uvicorn" in backend.detail


@pytest.mark.asyncio
async def test_startup_diagnostics_flags_occupied_port_with_listener() -> None:
    report = await _run_startup(
        port_in_use=lambda port: port == 8001,
        port_listeners=lambda port: [(4321, "python.exe")],
    )

    assert report.ok is False
    ports = next(check for check in report.checks if check.key == "ports")
    assert ports.status == "fail"
    assert ports.required is True
    assert "pid 4321 (python.exe)" in ports.detail
    assert "netstat" in ports.detail


@pytest.mark.asyncio
async def test_startup_diagnostics_flags_duplicate_ports() -> None:
    report = await _run_startup(
        launch_settings=_ready_launch_settings(frontend_port=8001),
    )

    ports = next(check for check in report.checks if check.key == "ports")
    assert ports.status == "fail"
    assert "both use port 8001" in ports.detail


@pytest.mark.asyncio
async def test_startup_diagnostics_flags_missing_web_assets() -> None:
    report = await _run_startup(local_web=lambda home: None)

    assert report.ok is False
    frontend = next(check for check in report.checks if check.key == "frontend")
    assert frontend.status == "fail"
    assert frontend.required is True


@pytest.mark.asyncio
async def test_startup_diagnostics_flags_missing_node() -> None:
    report = await _run_startup(which=lambda name: None)

    frontend = next(check for check in report.checks if check.key == "frontend")
    assert frontend.status == "fail"
    assert "nodejs.org" in frontend.detail


@pytest.mark.asyncio
async def test_startup_diagnostics_flags_missing_npm_for_source_frontend() -> None:
    report = await _run_startup(
        local_web=lambda home: ("source", Path("/repo/web")),
        which=lambda name: None if name == "npm" else "/usr/bin/node",
    )

    frontend = next(check for check in report.checks if check.key == "frontend")
    assert frontend.status == "fail"
    assert "npm install" in frontend.detail


@pytest.mark.asyncio
async def test_startup_diagnostics_parser_missing_models_is_advisory() -> None:
    report = await _run_startup(
        parser_readiness=lambda: {"engine": "mineru", "ready": False, "reason": "models_missing"},
    )

    parser = next(check for check in report.checks if check.key == "parser")
    assert parser.status == "fail"
    assert parser.required is False
    assert "mineru[all]" in parser.detail
    assert report.ok is True


@pytest.mark.asyncio
async def test_startup_diagnostics_parser_skips_without_engine() -> None:
    report = await _run_startup(
        parser_readiness=lambda: {"engine": "", "ready": False, "reason": "not_configured"},
    )

    parser = next(check for check in report.checks if check.key == "parser")
    assert parser.status == "skip"
    assert parser.required is False
    assert report.ok is True


@pytest.mark.asyncio
async def test_startup_diagnostics_parser_unknown_reason_uses_fallback_hint() -> None:
    report = await _run_startup(
        parser_readiness=lambda: {"engine": "docling", "ready": False, "reason": "mystery"},
    )

    parser = next(check for check in report.checks if check.key == "parser")
    assert parser.status == "fail"
    assert "Open Settings -> Document Parsing" in parser.detail


@pytest.mark.asyncio
async def test_startup_diagnostics_contains_probe_exception() -> None:
    def boom() -> dict:
        raise RuntimeError("parser probe exploded")

    report = await _run_startup(parser_readiness=boom)

    parser = next(check for check in report.checks if check.key == "parser")
    assert parser.status == "fail"
    assert parser.required is False
    assert "parser probe exploded" in parser.detail
    assert report.ok is True


def test_doctor_startup_rich_output_lists_readiness(monkeypatch) -> None:
    async def fake_run_startup_diagnostics():
        return DoctorReport(
            online=False,
            checks=[
                DoctorCheck(
                    key="backend",
                    label="Backend service",
                    status="pass",
                    detail="Ready.",
                ),
                DoctorCheck(
                    key="parser",
                    label="Document parser",
                    status="fail",
                    detail="mineru is not ready (models_missing).",
                    required=False,
                ),
            ],
        )

    monkeypatch.setattr(
        "deeptutor_cli.doctor.run_startup_diagnostics", fake_run_startup_diagnostics
    )

    result = runner.invoke(app, ["doctor", "startup"])

    assert result.exit_code == 0, result.output
    assert "PASS" in result.output
    assert "WARN" in result.output
    assert "Document parser" in result.output


def test_doctor_startup_json_exits_nonzero_for_required_failure(monkeypatch) -> None:
    async def fake_run_startup_diagnostics():
        return DoctorReport(
            online=False,
            checks=[
                DoctorCheck(
                    key="ports",
                    label="Service ports",
                    status="fail",
                    detail="Backend port 8001 is held by pid 4321 (python.exe).",
                )
            ],
        )

    monkeypatch.setattr(
        "deeptutor_cli.doctor.run_startup_diagnostics", fake_run_startup_diagnostics
    )

    result = runner.invoke(app, ["doctor", "startup", "--format", "json"])

    assert result.exit_code == 1, result.output
    assert json.loads(result.output) == {
        "ok": False,
        "online": False,
        "checks": [
            {
                "key": "ports",
                "label": "Service ports",
                "status": "fail",
                "detail": "Backend port 8001 is held by pid 4321 (python.exe).",
                "required": True,
            }
        ],
    }


def test_doctor_rejects_unknown_target() -> None:
    result = runner.invoke(app, ["doctor", "bogus"])

    assert result.exit_code == 2, result.output
    assert "startup" in result.output
