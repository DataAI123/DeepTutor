"""Redacted forensics for a connected Tencent IMA knowledge base.

A KB that is bound, credentialed and reachable can still answer a query with
nothing. There are exactly three places the evidence can stop flowing, and they
are indistinguishable from the outside — the ``rag`` tool just reports an empty
result either way:

1. **binding** — the KB points at a different account, a different library, or
   half a credential pair;
2. **remote** — the library answered, but matched nothing (or that document is
   not indexed yet);
3. **parsing** — the library matched, but the response carried no text to
   reason from.

Assembling that picture through the normal retrieval path is the point: this
module runs the *real* :meth:`ImaPipeline.search` and reports what each stage
observed, so the diagnosis cannot drift from what retrieval actually does.

Redaction
---------
The report is meant to be a safe artefact — pasteable into an issue. It is built
from counts, a hashed id and method/status/code triples only. It never carries
the API key, a request or response body, a signed COS URL, or any textbook text.
The one free-text field (an upstream error message) is run through
:func:`_summarize`, which strips URLs and truncates.

Like :mod:`.probe`, this always returns an :class:`ImaDiagnosis` and never
raises: a failed diagnosis is still a diagnosis.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import re
from typing import Any, Callable, Optional

from deeptutor.services.rag.provider_binding import load_kb_config_entry

from .client import ImaClient
from .config import ImaConfig, ImaNotConfiguredError, get_account_credentials, resolve_kb_config
from .pipeline import ImaPipeline, SearchDiagnostics
from .transport import ImaWireEvent, WireObserver

# How much of the knowledge base id survives into the report: enough to tell two
# bindings apart, far too little to reconstruct the id.
FINGERPRINT_CHARS = 8

# Bounds on the report's only free-text field and its round-trip list.
MAX_MESSAGE_CHARS = 500
MAX_REMOTE_EVENTS = 20

_URL_RE = re.compile(r"https?://\S+")

# Where the credential pair a KB resolves to actually comes from. ``mixed`` is
# the interesting one: the KB entry supplied half a pair and the account-level
# settings supplied the other, which is a binding worth scrutinising.
CREDENTIAL_SOURCE_KB = "kb"
CREDENTIAL_SOURCE_ACCOUNT = "account"
CREDENTIAL_SOURCE_MIXED = "mixed"
CREDENTIAL_SOURCE_NONE = "none"


@dataclass
class ImaDiagnosis:
    """A redacted, stage-by-stage account of one IMA retrieval."""

    kb_name: str
    query: str
    # Whether a complete ImaConfig could be resolved at all.
    configured: bool = False
    # One of CREDENTIAL_SOURCE_*: which level the credential pair came from.
    credential_source: str = CREDENTIAL_SOURCE_NONE
    # Salt-free hash prefix of the knowledge base id (see FINGERPRINT_CHARS).
    knowledge_base_id_fingerprint: Optional[str] = None
    # Every IMA round-trip made, in order: {method, status_code, code}.
    remote: list[dict[str, Any]] = field(default_factory=list)
    # Retrieval stage counts (see SearchDiagnostics).
    documents: int = 0
    folders: int = 0
    sources: int = 0
    hydration_targets: int = 0
    hydrated: int = 0
    hydration_failed: int = 0
    evidence_chars: int = 0
    # The verdict retrieval reached, plus the reason when it errored.
    retrieval_status: str = "error"
    error_type: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


async def diagnose_knowledge_base(
    kb_base_dir: str,
    kb_name: str,
    query: str,
    *,
    client_builder: Optional[Callable[[ImaConfig, WireObserver], Any]] = None,
) -> ImaDiagnosis:
    """Run *query* through the KB's real retrieval path and report what it saw.

    *client_builder* — ``(config, observer) -> client`` — is an injection seam
    for tests; the observer is handed to it so a stub can still report its
    round-trips. In production it is a real :class:`ImaClient`.
    """
    query = str(query or "").strip()
    report = ImaDiagnosis(kb_name=kb_name, query=query)

    entry = load_kb_config_entry(kb_base_dir, kb_name)
    report.credential_source = _credential_source(entry)
    report.knowledge_base_id_fingerprint = _fingerprint(
        str(entry.get("knowledge_base_id") or "")
    )

    try:
        resolve_kb_config(entry)
    except ImaNotConfiguredError as exc:
        # No complete binding to query: this *is* the finding. Reported verbatim
        # — it is our own message, naming which field is missing.
        report.error_type = "not_configured"
        report.error = _summarize(exc)
        return report
    report.configured = True

    events: list[ImaWireEvent] = []
    builder = client_builder or _default_client_builder
    observer: WireObserver = events.append

    def build_client(config: ImaConfig) -> Any:
        return builder(config, observer)

    pipeline = ImaPipeline(kb_base_dir, client_factory=build_client)
    diagnostics = SearchDiagnostics()
    result = await pipeline.search(query, kb_name, diagnostics=diagnostics)

    report.remote = [asdict(event) for event in events[:MAX_REMOTE_EVENTS]]
    report.documents = diagnostics.documents
    report.folders = diagnostics.folders
    report.sources = diagnostics.sources
    report.hydration_targets = diagnostics.hydration_targets
    report.hydrated = diagnostics.hydrated
    report.hydration_failed = diagnostics.hydration_failed
    report.evidence_chars = _as_int(result.get("evidence_chars"))
    report.retrieval_status = str(result.get("retrieval_status") or "error")

    error_type = result.get("error_type")
    if error_type:
        report.error_type = str(error_type)
        report.error = _summarize(result.get("answer"))
    return report


def _default_client_builder(config: ImaConfig, observer: WireObserver) -> ImaClient:
    return ImaClient(config, observer=observer)


def _credential_source(entry: dict[str, Any]) -> str:
    """Which level the KB's credential pair comes from.

    Mirrors :func:`~.config.config_from_entry`: a complete per-KB pair wins, and
    anything it omits is filled from the account settings.
    """
    client_id = str(entry.get("client_id") or "").strip()
    api_key = str(entry.get("api_key") or "").strip()
    if client_id and api_key:
        return CREDENTIAL_SOURCE_KB
    if client_id or api_key:
        return CREDENTIAL_SOURCE_MIXED
    return CREDENTIAL_SOURCE_ACCOUNT if get_account_credentials().complete else CREDENTIAL_SOURCE_NONE


def _fingerprint(value: str) -> Optional[str]:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:FINGERPRINT_CHARS]


def _summarize(text: Any) -> Optional[str]:
    """A short, URL-free rendering of upstream text.

    Every free-text field in the report passes through here, so a message that
    happened to quote a signed download URL cannot carry it out of the process.
    """
    cleaned = str(text or "").strip()
    if not cleaned:
        return None
    cleaned = _URL_RE.sub("<redacted-url>", cleaned)
    if len(cleaned) > MAX_MESSAGE_CHARS:
        cleaned = cleaned[:MAX_MESSAGE_CHARS] + "…"
    return cleaned


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


__all__ = [
    "CREDENTIAL_SOURCE_ACCOUNT",
    "CREDENTIAL_SOURCE_KB",
    "CREDENTIAL_SOURCE_MIXED",
    "CREDENTIAL_SOURCE_NONE",
    "FINGERPRINT_CHARS",
    "ImaDiagnosis",
    "diagnose_knowledge_base",
]
