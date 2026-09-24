"""Local and opt-in online diagnostics for the DeepTutor CLI."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, dataclass
import importlib.util
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

from deeptutor.services.llm.utils import is_local_llm_server, sanitize_url
from deeptutor.services.provider_registry import find_by_name

CheckStatus = Literal["pass", "fail", "skip"]


@dataclass(frozen=True)
class DoctorCheck:
    """One diagnostic result shown by ``deeptutor doctor``."""

    key: str
    label: str
    status: CheckStatus
    detail: str
    required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DoctorReport:
    """Complete diagnostic report."""

    online: bool
    checks: list[DoctorCheck]

    @property
    def ok(self) -> bool:
        return all(check.status != "fail" for check in self.checks if check.required)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "online": self.online,
            "checks": [check.to_dict() for check in self.checks],
        }


def _safe_endpoint(raw_url: str | None) -> tuple[bool, str]:
    if not raw_url:
        return False, "No provider endpoint is configured."

    normalized = sanitize_url(raw_url)
    try:
        parsed = urlsplit(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False, "The configured provider endpoint is not a valid HTTP(S) URL."
        host = parsed.hostname
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        port = f":{parsed.port}" if parsed.port is not None else ""
        display_url = urlunsplit((parsed.scheme, f"{host}{port}", "", "", ""))
    except (ValueError, TypeError):
        return False, "The configured provider endpoint is not a valid HTTP(S) URL."
    return True, display_url.rstrip("/")


def _has_authentication_header(headers: Any) -> bool:
    if not isinstance(headers, Mapping):
        return False

    exact_names = {
        "authorization",
        "proxy-authorization",
        "api-key",
        "x-api-key",
        "x-goog-api-key",
    }
    auth_suffixes = (
        "-authorization",
        "-auth",
        "-api-key",
        "-apikey",
        "-access-token",
        "-auth-token",
    )
    for name, value in headers.items():
        normalized_name = re.sub(r"[_\s]+", "-", str(name).strip().lower())
        if str(value or "").strip() and (
            normalized_name in exact_names or normalized_name.endswith(auth_suffixes)
        ):
            return True
    return False


def _credentials_check(config: Any) -> DoctorCheck:
    provider_name = str(getattr(config, "provider_name", "") or "")
    provider_mode = str(getattr(config, "provider_mode", "") or "")
    api_key = str(getattr(config, "api_key", "") or "")
    endpoint = str(
        getattr(config, "effective_url", None) or getattr(config, "base_url", None) or ""
    )
    extra_headers = getattr(config, "extra_headers", None) or {}
    provider = find_by_name(provider_name)
    placeholders = {"", "no-key", "sk-no-key-required"}

    if provider_mode == "oauth" or (provider and provider.is_oauth):
        return DoctorCheck(
            key="llm_credentials",
            label="LLM credentials",
            status="pass",
            detail=f"{provider_name or 'Selected provider'} uses provider-managed OAuth.",
        )
    if (
        provider_mode == "local"
        or (provider and provider.is_local)
        or is_local_llm_server(endpoint)
    ):
        return DoctorCheck(
            key="llm_credentials",
            label="LLM credentials",
            status="pass",
            detail="The selected local provider does not require an API key.",
        )
    if api_key not in placeholders or _has_authentication_header(extra_headers):
        return DoctorCheck(
            key="llm_credentials",
            label="LLM credentials",
            status="pass",
            detail=f"Credentials are configured for {provider_name or 'the selected provider'}.",
        )
    if provider and provider.is_direct and provider.name != "azure_openai":
        return DoctorCheck(
            key="llm_credentials",
            label="LLM credentials",
            status="skip",
            detail=(
                "No recognized credential is configured for this custom endpoint. "
                "Use --online to verify whether it accepts unauthenticated requests."
            ),
            required=False,
        )
    return DoctorCheck(
        key="llm_credentials",
        label="LLM credentials",
        status="fail",
        detail=f"No credentials are configured for {provider_name or 'the selected provider'}.",
    )


def _llm_checks(config: Any) -> list[DoctorCheck]:
    model = str(getattr(config, "model", "") or "")
    provider_name = str(getattr(config, "provider_name", "") or "")
    provider_mode = str(getattr(config, "provider_mode", "") or "")
    endpoint = getattr(config, "effective_url", None) or getattr(config, "base_url", None)

    checks = [
        DoctorCheck(
            key="llm_config",
            label="LLM configuration",
            status="pass" if model else "fail",
            detail=(
                f"Active model: {model} ({provider_name or 'unknown provider'})."
                if model
                else "No active LLM model is configured."
            ),
        ),
        _credentials_check(config),
    ]

    provider = find_by_name(provider_name)
    if provider_mode == "oauth" or (provider and provider.is_oauth):
        checks.append(
            DoctorCheck(
                key="llm_endpoint",
                label="LLM endpoint",
                status="pass",
                detail="The OAuth provider manages its endpoint.",
            )
        )
    else:
        endpoint_ok, detail = _safe_endpoint(endpoint)
        checks.append(
            DoctorCheck(
                key="llm_endpoint",
                label="LLM endpoint",
                status="pass" if endpoint_ok else "fail",
                detail=detail,
            )
        )
    return checks


def _storage_check(data_root: Path) -> DoctorCheck:
    try:
        data_root.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=".deeptutor-doctor-",
            dir=data_root,
            delete=True,
        ) as handle:
            handle.write("ok")
            handle.flush()
    except OSError as exc:
        return DoctorCheck(
            key="storage",
            label="Runtime storage",
            status="fail",
            detail=f"Cannot write to {data_root}: {exc}",
        )
    return DoctorCheck(
        key="storage",
        label="Runtime storage",
        status="pass",
        detail=f"Writable: {data_root}",
    )


def _rag_check(
    config: dict[str, Any],
    preflight: Callable[[str], dict[str, Any]],
) -> DoctorCheck:
    knowledge_bases = config.get("knowledge_bases", {})
    if not isinstance(knowledge_bases, dict) or not knowledge_bases:
        return DoctorCheck(
            key="rag",
            label="RAG prerequisites",
            status="skip",
            detail="No knowledge bases are configured.",
            required=False,
        )

    defaults = config.get("defaults", {})
    default_provider = (
        str(defaults.get("rag_provider", "llamaindex"))
        if isinstance(defaults, dict)
        else "llamaindex"
    )
    from deeptutor.services.rag.factory import (
        LIGHTRAG_SERVER_PROVIDER,
        WEKNORA_PROVIDER,
        normalize_provider_name,
    )

    providers: set[str] = set()
    failures: list[str] = []
    for kb_name, entry in knowledge_bases.items():
        if not isinstance(entry, dict):
            continue
        provider = normalize_provider_name(str(entry.get("rag_provider") or default_provider))
        providers.add(provider)
        if provider == WEKNORA_PROVIDER:
            from deeptutor.services.rag.pipelines.weknora.config import (
                config_from_entry as weknora_config_from_entry,
            )

            try:
                weknora_config = weknora_config_from_entry(entry)
                endpoint_ok, _ = _safe_endpoint(weknora_config.base_url)
                if not endpoint_ok:
                    failures.append(f"{kb_name}: invalid WeKnora server URL")
            except Exception as exc:
                failures.append(f"{kb_name}: {_redact_error(exc, None)}")
            continue

        if provider != LIGHTRAG_SERVER_PROVIDER:
            continue

        from deeptutor.services.rag.pipelines.lightrag_server.config import (
            config_from_entry as lightrag_server_config_from_entry,
        )

        try:
            server_config = lightrag_server_config_from_entry(entry)
            endpoint_ok, _ = _safe_endpoint(server_config.base_url)
            if not endpoint_ok:
                failures.append(f"{kb_name}: invalid LightRAG server URL")
        except Exception as exc:
            failures.append(f"{kb_name}: {_redact_error(exc, None)}")

    for provider in sorted(providers - {LIGHTRAG_SERVER_PROVIDER, WEKNORA_PROVIDER}):
        try:
            report = preflight(provider)
            for check in report.get("checks", []):
                if not check.get("ok") and not check.get("optional", False):
                    failures.append(f"{provider}: {check.get('label', 'requirement failed')}")
        except Exception as exc:
            failures.append(f"{provider}: preflight could not run ({_redact_error(exc, None)})")

    if failures:
        return DoctorCheck(
            key="rag",
            label="RAG prerequisites",
            status="fail",
            detail="; ".join(failures),
            required=False,
        )
    return DoctorCheck(
        key="rag",
        label="RAG prerequisites",
        status="pass",
        detail=f"Ready for configured provider(s): {', '.join(sorted(providers))}.",
        required=False,
    )


#: Copy-pasteable fixes keyed by a parser engine's machine-readable reason.
_PARSER_REMEDIES: dict[str, str] = {
    "models_missing": (
        "Download the models from Settings -> Document Parsing, or run "
        '`pip install -U "mineru[all]>=3.4.5,<4"`.'
    ),
    "cli_missing": (
        'Install the supported 3.x engine CLI (for example `pip install -U "mineru[all]>=3.4.5,<4"`), '
        "then re-run `deeptutor doctor startup`."
    ),
    "not_configured": (
        "Select an engine and fill in its endpoint/credentials in Settings -> Document Parsing."
    ),
    "update_required": "Update the engine package, then restart DeepTutor.",
    "parser_probe_failed": (
        "Reinstall the engine, then re-run `deeptutor doctor startup` to confirm."
    ),
}


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _http_probe(url: str) -> bool:
    from deeptutor.runtime.launcher import _http_ready

    return _http_ready(url, timeout=2.0)


def _port_in_use(port: int) -> bool:
    from deeptutor.runtime.launcher import _port_accepts_connection

    return _port_accepts_connection(port)


def _list_port_listeners(port: int) -> list[tuple[int, str]]:
    from deeptutor.runtime.launcher import _port_listeners

    return _port_listeners(port)


def _local_web_kind(home: Path) -> tuple[str, Path] | None:
    from deeptutor.runtime.launcher import _packaged_web_dir, _source_web_dir

    packaged = _packaged_web_dir()
    if packaged is not None:
        return "packaged", packaged
    source = _source_web_dir(home)
    if source is not None:
        return "source", source
    return None


def _document_parser_readiness() -> dict[str, Any]:
    """Probe the selected parser engine the same way the settings page does."""

    from deeptutor.services.config import get_runtime_settings_service
    from deeptutor.services.parsing.engines.factory import get_parser

    parsing = get_runtime_settings_service().load_document_parsing(include_process_overrides=True)
    engine = str(parsing.get("engine") or "")
    if not engine:
        return {"engine": "", "ready": False, "reason": "not_configured"}
    try:
        parser = get_parser(engine)
        report = parser.is_ready(parser.resolve_config())
    except Exception:
        return {"engine": engine, "ready": False, "reason": "parser_probe_failed"}
    return {"engine": engine, "ready": bool(report.ready), "reason": str(report.reason or "")}


def _probe(
    key: str,
    label: str,
    probe: Callable[[], DoctorCheck],
    *,
    required: bool = True,
) -> DoctorCheck:
    """Run one startup probe, turning an unexpected error into a failing check."""

    try:
        return probe()
    except Exception as exc:
        return DoctorCheck(
            key=key,
            label=label,
            status="fail",
            detail=_redact_error(exc, None),
            required=required,
        )


def _backend_check(
    *,
    port: int,
    http_ready: Callable[[str], bool],
    module_available: Callable[[str], bool],
) -> DoctorCheck:
    missing = [name for name in ("uvicorn", "deeptutor.api.main") if not module_available(name)]
    if missing:
        return DoctorCheck(
            key="backend",
            label="Backend service",
            status="fail",
            detail=(
                f"Missing backend dependencies: {', '.join(missing)}. "
                'Reinstall with `pip install -e ".[server]"`.'
            ),
        )
    url = f"http://127.0.0.1:{port}/"
    if http_ready(url):
        return DoctorCheck(
            key="backend",
            label="Backend service",
            status="pass",
            detail=f"The API is already responding at {url}.",
        )
    return DoctorCheck(
        key="backend",
        label="Backend service",
        status="pass",
        detail=f"Not running; dependencies are installed and `deeptutor start` will serve port {port}.",
    )


def _frontend_check(
    *,
    web: tuple[str, Path] | None,
    which: Callable[[str], str | None],
) -> DoctorCheck:
    if web is None:
        return DoctorCheck(
            key="frontend",
            label="Web frontend",
            status="fail",
            detail=(
                "Web assets are not installed. Reinstall the packaged app, or run "
                "`deeptutor start` from a checkout that contains the web/ directory."
            ),
        )
    kind, path = web
    if which("node") is None:
        return DoctorCheck(
            key="frontend",
            label="Web frontend",
            status="fail",
            detail=(
                "Node.js 20+ is required for the web app. Install it from "
                "https://nodejs.org/ and re-run `deeptutor doctor startup`."
            ),
        )
    if kind == "source" and which("npm") is None:
        return DoctorCheck(
            key="frontend",
            label="Web frontend",
            status="fail",
            detail=(
                f"Source frontend found at {path} but npm is missing. Install Node.js/npm, then run "
                "`cd web && npm install && npm run build`."
            ),
        )
    return DoctorCheck(
        key="frontend",
        label="Web frontend",
        status="pass",
        detail=f"Ready ({kind}) at {path}.",
    )


def _ports_check(
    *,
    backend_port: int,
    frontend_port: int,
    source: str,
    port_in_use: Callable[[int], bool],
    port_listeners: Callable[[int], list[tuple[int, str]]],
) -> DoctorCheck:
    if not backend_port or not frontend_port:
        return DoctorCheck(
            key="ports",
            label="Service ports",
            status="fail",
            detail=(
                "Backend and frontend ports are not configured. "
                "Set them in data/user/settings/system.json."
            ),
        )
    if backend_port == frontend_port:
        return DoctorCheck(
            key="ports",
            label="Service ports",
            status="fail",
            detail=(
                f"Backend and frontend both use port {backend_port}. "
                "Set distinct ports in data/user/settings/system.json."
            ),
        )

    conflicts: list[str] = []
    for role, port in (("Backend", backend_port), ("Frontend", frontend_port)):
        if not port_in_use(port):
            continue
        listeners = port_listeners(port)
        owner = (
            ", ".join(f"pid {pid} ({command})" for pid, command in listeners)
            or "an unknown process"
        )
        conflicts.append(f"{role} port {port} is held by {owner}")
    if conflicts:
        return DoctorCheck(
            key="ports",
            label="Service ports",
            status="fail",
            detail=(
                f"{'; '.join(conflicts)}. Stop the process or pick another port in "
                "data/user/settings/system.json; list the owner with "
                "`netstat -ano | findstr :<port>`."
            ),
        )
    return DoctorCheck(
        key="ports",
        label="Service ports",
        status="pass",
        detail=f"Backend :{backend_port} and frontend :{frontend_port} are free ({source}).",
    )


def _parser_check(readiness: Mapping[str, Any]) -> DoctorCheck:
    engine = str(readiness.get("engine") or "")
    if not engine:
        return DoctorCheck(
            key="parser",
            label="Document parser",
            status="skip",
            detail="No document-parsing engine is selected.",
            required=False,
        )
    if bool(readiness.get("ready")):
        return DoctorCheck(
            key="parser",
            label="Document parser",
            status="pass",
            detail=f"{engine} is ready.",
            required=False,
        )
    reason = str(readiness.get("reason") or "unknown")
    hint = _PARSER_REMEDIES.get(
        reason,
        "Open Settings -> Document Parsing and pick a working engine.",
    )
    return DoctorCheck(
        key="parser",
        label="Document parser",
        status="fail",
        detail=f"{engine} is not ready ({reason}). {hint}",
        required=False,
    )


def _redact_error(exc: Exception, config: Any) -> str:
    message = str(exc).strip() or type(exc).__name__
    extra_headers = getattr(config, "extra_headers", None) or {}
    header_values = (
        [str(value or "") for value in extra_headers.values()]
        if isinstance(extra_headers, Mapping)
        else []
    )
    secrets = [
        str(getattr(config, "api_key", "") or ""),
        str(getattr(config, "effective_url", "") or ""),
        str(getattr(config, "base_url", "") or ""),
        *header_values,
    ]
    for secret in secrets:
        if secret and secret not in {"no-key", "sk-no-key-required"}:
            message = message.replace(secret, "[redacted]")
    message = re.sub(r"\bsk-[A-Za-z0-9_-]{4,}\b", "[redacted]", message)
    message = re.sub(
        r"(?i)((?:api[_-]?key|authorization|token|password)\s*[:=]\s*)[^\s,;]+",
        r"\1[redacted]",
        message,
    )
    return message


async def _probe_provider(config: Any) -> None:
    from deeptutor.services.llm import complete

    response = await complete(
        model=str(config.model),
        prompt="Reply with OK.",
        system_prompt="Reply with only OK.",
        binding=str(config.binding),
        api_key=str(config.api_key or ""),
        base_url=str(config.effective_url or config.base_url or ""),
        api_version=config.api_version,
        temperature=0,
        extra_headers=config.extra_headers,
        reasoning_effort=config.reasoning_effort,
        max_retries=0,
        allow_image_fallback=False,
        max_tokens=64,
    )
    if not (response or "").strip():
        raise RuntimeError("The model returned an empty response.")


async def run_diagnostics(
    *,
    online: bool = False,
    resolve_llm: Callable[[], Any] | None = None,
    data_root: Path | None = None,
    load_rag_config: Callable[[], dict[str, Any]] | None = None,
    rag_preflight: Callable[[str], dict[str, Any]] | None = None,
    online_probe: Callable[[Any], Awaitable[None]] | None = None,
) -> DoctorReport:
    """Run setup diagnostics without network access unless ``online`` is set."""
    if resolve_llm is None:
        from deeptutor.services.config import resolve_llm_runtime_config

        resolve_llm = resolve_llm_runtime_config
    if data_root is None:
        from deeptutor.services.path_service import get_path_service

        data_root = get_path_service().get_user_root()
    if load_rag_config is None:
        from deeptutor.services.config import get_kb_config_service

        load_rag_config = get_kb_config_service().get_all_configs
    if rag_preflight is None:
        from deeptutor.services.rag.preflight import engine_preflight

        rag_preflight = engine_preflight
    if online_probe is None:
        online_probe = _probe_provider

    checks: list[DoctorCheck] = []
    config = None
    llm_ready = False
    try:
        config = resolve_llm()
        llm_checks = _llm_checks(config)
        checks.extend(llm_checks)
        llm_ready = all(check.status != "fail" for check in llm_checks if check.required)
    except Exception as exc:
        checks.append(
            DoctorCheck(
                key="llm_config",
                label="LLM configuration",
                status="fail",
                detail=f"Could not resolve active LLM settings: {_redact_error(exc, None)}",
            )
        )

    checks.append(_storage_check(data_root))
    try:
        checks.append(_rag_check(load_rag_config(), rag_preflight))
    except Exception as exc:
        checks.append(
            DoctorCheck(
                key="rag",
                label="RAG prerequisites",
                status="fail",
                detail=f"Could not inspect RAG settings: {_redact_error(exc, None)}",
                required=False,
            )
        )

    if not online:
        checks.append(
            DoctorCheck(
                key="online",
                label="Provider response",
                status="skip",
                detail="Not requested. Use --online to send a small model request.",
                required=False,
            )
        )
    elif config is None or not llm_ready:
        checks.append(
            DoctorCheck(
                key="online",
                label="Provider response",
                status="skip",
                detail="Skipped because local LLM checks failed.",
                required=False,
            )
        )
    else:
        try:
            await online_probe(config)
            checks.append(
                DoctorCheck(
                    key="online",
                    label="Provider response",
                    status="pass",
                    detail="The model returned a response.",
                )
            )
        except Exception as exc:
            checks.append(
                DoctorCheck(
                    key="online",
                    label="Provider response",
                    status="fail",
                    detail=_redact_error(exc, config),
                )
            )

    return DoctorReport(online=online, checks=checks)


async def run_startup_diagnostics(
    *,
    home: Path | None = None,
    launch_settings: Any | None = None,
    http_ready: Callable[[str], bool] | None = None,
    port_in_use: Callable[[int], bool] | None = None,
    port_listeners: Callable[[int], list[tuple[int, str]]] | None = None,
    module_available: Callable[[str], bool] | None = None,
    which: Callable[[str], str | None] | None = None,
    local_web: Callable[[Path], tuple[str, Path] | None] | None = None,
    parser_readiness: Callable[[], dict[str, Any]] | None = None,
) -> DoctorReport:
    """Summarise ``deeptutor start`` readiness before a first launch (#1501).

    Reports backend, frontend, port, and document-parser readiness without
    contacting the model provider, so a blank page or a missing-model
    traceback can be explained up front. Ports are reused from the launcher's
    own probes, so the numbers here are the numbers the launcher will use.
    """

    if home is None:
        from deeptutor.runtime.home import get_runtime_home

        home = get_runtime_home()
    if launch_settings is None:
        from deeptutor.services.config.launch_settings import load_launch_settings

        launch_settings = load_launch_settings()
    if http_ready is None:
        http_ready = _http_probe
    if port_in_use is None:
        port_in_use = _port_in_use
    if port_listeners is None:
        port_listeners = _list_port_listeners
    if module_available is None:
        module_available = _module_available
    if which is None:
        which = shutil.which
    if local_web is None:
        local_web = _local_web_kind
    if parser_readiness is None:
        parser_readiness = _document_parser_readiness

    backend_port = int(getattr(launch_settings, "backend_port", 0) or 0)
    frontend_port = int(getattr(launch_settings, "frontend_port", 0) or 0)
    source = str(getattr(launch_settings, "source", "") or "")

    checks = [
        _probe(
            "backend",
            "Backend service",
            lambda: _backend_check(
                port=backend_port,
                http_ready=http_ready,
                module_available=module_available,
            ),
        ),
        _probe(
            "frontend",
            "Web frontend",
            lambda: _frontend_check(web=local_web(home), which=which),
        ),
        _probe(
            "ports",
            "Service ports",
            lambda: _ports_check(
                backend_port=backend_port,
                frontend_port=frontend_port,
                source=source,
                port_in_use=port_in_use,
                port_listeners=port_listeners,
            ),
        ),
        _probe(
            "parser",
            "Document parser",
            lambda: _parser_check(parser_readiness()),
            required=False,
        ),
    ]
    return DoctorReport(online=False, checks=checks)


async def run_runtime_diagnostics() -> DoctorReport:
    """Preflight v2 storage, migrations, and coordination without an LLM call."""

    checks: list[DoctorCheck] = []
    try:
        from deeptutor.runtime.coordination import (
            CoordinationSettings,
            create_runtime_coordinator,
        )
        from deeptutor.services.config import (
            load_integrations_settings,
            load_system_settings,
        )

        coordination_settings = CoordinationSettings.from_runtime_settings(
            load_system_settings(), load_integrations_settings()
        )
        coordinator = await create_runtime_coordinator(coordination_settings)
        healthy = await coordinator.health()
        await coordinator.close()
        checks.append(
            DoctorCheck(
                key="turn_coordination",
                label="Turn coordination",
                status="pass" if healthy else "fail",
                detail=(
                    f"{coordination_settings.backend} coordination is ready for "
                    f"{coordination_settings.backend_workers} worker(s)."
                    if healthy
                    else "The configured coordination backend is unavailable."
                ),
            )
        )
    except Exception as exc:
        checks.append(
            DoctorCheck(
                key="turn_coordination",
                label="Turn coordination",
                status="fail",
                detail=_redact_error(exc, None),
            )
        )

    try:
        from deeptutor.services.session import get_session_store

        store = get_session_store()
        await store.list_nonterminal_turns()
        checks.append(
            DoctorCheck(
                key="turn_repository",
                label="Turn repository",
                status="pass",
                detail=f"{type(store).__name__} schema and active-turn query are ready.",
            )
        )
    except Exception as exc:
        checks.append(
            DoctorCheck(
                key="turn_repository",
                label="Turn repository",
                status="fail",
                detail=_redact_error(exc, None),
            )
        )

    try:
        from deeptutor.services.session.legacy_migration import (
            migrate_all_legacy_chat_scopes,
        )

        reports = await migrate_all_legacy_chat_scopes(dry_run=True)
        pending_sessions = sum(int(report.get("imported") or 0) for report in reports)
        checks.append(
            DoctorCheck(
                key="legacy_chat_migration",
                label="Legacy chat migration",
                status="pass",
                detail=f"Preflight succeeded; {pending_sessions} session(s) pending migration.",
            )
        )
    except Exception as exc:
        checks.append(
            DoctorCheck(
                key="legacy_chat_migration",
                label="Legacy chat migration",
                status="fail",
                detail=_redact_error(exc, None),
            )
        )

    return DoctorReport(online=False, checks=checks)


__all__ = [
    "DoctorCheck",
    "DoctorReport",
    "run_diagnostics",
    "run_runtime_diagnostics",
    "run_startup_diagnostics",
]
