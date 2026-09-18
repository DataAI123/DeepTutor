"""Retrieval-only pipeline backed by a Tencent IMA knowledge base.

Implements the same contract as the other pipelines (see ``..base.RAGPipeline``)
but owns no index: an ``ima`` KB is a connection pointer (``type: ima`` in
``kb_config.json``) to a library the user keeps in IMA and curates there. Only
:meth:`search` does real work — it resolves the KB's credentials, asks IMA for
matching passages, tops the thin ones up with real source text, and shapes them
for the ``rag`` tool. Documents are added in IMA (or through the IMA capability's
own tools), so :meth:`initialize` / :meth:`add_documents` are not part of this
engine's job and fail with a clear message; :meth:`delete` is a no-op because
deleting the KB only drops DeepTutor's pointer (handled by the manager) and must
never touch the user's IMA library.

The retrieval *policy* — which matches deserve a full-text fetch — lives in
:mod:`.sources`; this module only orchestrates.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from typing import Any, Dict, List, Optional

from deeptutor.runtime.home import get_runtime_data_root
from deeptutor.services.rag.provider_binding import load_kb_config_entry

from . import media as media_ops
from . import sources as source_policy
from .config import ImaNotConfiguredError, resolve_kb_config

logger = logging.getLogger(__name__)

PROVIDER = "ima"
DEFAULT_KB_BASE_DIR = str(get_runtime_data_root() / "knowledge_bases")

# How many matched passages one retrieval feeds into the prompt. IMA returns a
# highlight snippet per item rather than whole documents, so this is a passage
# budget, not a document budget.
_DEFAULT_TOP_K = 10
_MAX_TOP_K = 50


@dataclass
class SearchDiagnostics:
    """What one retrieval observed, stage by stage.

    Purely observational: ``search`` fills this in when a caller passes one and
    behaves identically when it does not. It exists so a mounted-but-empty IMA
    KB can be told apart by *where* the evidence stopped flowing — nothing
    matched, matches carried no text, or the full-text top-up failed — without
    re-running the retrieval under a different code path. Counts only; no
    query, snippet or document text is ever recorded here.
    """

    # Matched by the remote: IMA returns documents and folders separately, and
    # only documents ever become sources.
    documents: int = 0
    folders: int = 0
    # Documents that survived shaping into the ``sources`` shape.
    sources: int = 0
    # Documents selected for a full-text top-up, and how those fetches ended.
    hydration_targets: int = 0
    hydrated: int = 0
    hydration_failed: int = 0


class ImaPipeline:
    """Query a Tencent IMA knowledge base on behalf of a connected KB."""

    def __init__(self, kb_base_dir: Optional[str] = None, *, client_factory=None, **_: Any) -> None:
        self.logger = logging.getLogger(__name__)
        self.kb_base_dir = kb_base_dir or DEFAULT_KB_BASE_DIR
        # Injection seam for tests: (config) -> client. None uses the real client.
        self._client_factory = client_factory

    # ----- helpers --------------------------------------------------------

    def _client(self, config):
        if self._client_factory is not None:
            return self._client_factory(config)
        from .client import ImaClient

        return ImaClient(config)

    @staticmethod
    def _top_k(kwargs: dict[str, Any]) -> int:
        try:
            requested = int(kwargs.get("top_k") or _DEFAULT_TOP_K)
        except (TypeError, ValueError):
            return _DEFAULT_TOP_K
        return max(1, min(requested, _MAX_TOP_K))

    # ----- retrieval ------------------------------------------------------

    async def search(
        self,
        query: str,
        kb_name: str,
        *,
        diagnostics: Optional[SearchDiagnostics] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        try:
            config = resolve_kb_config(load_kb_config_entry(self.kb_base_dir, kb_name))
        except ImaNotConfiguredError as exc:
            return self._error_result(query, exc, error_type="not_configured")

        try:
            client = self._client(config)
            page = await client.search_knowledge(query, limit=self._top_k(kwargs))
        except Exception as exc:
            self.logger.error("IMA search failed for '%s': %s", kb_name, exc)
            return self._error_result(query, exc, error_type="retrieval_error")

        if diagnostics is not None:
            diagnostics.documents = len(page.documents)
            diagnostics.folders = len(page.folders)

        sources = source_policy.documents_to_sources(page.documents)
        await self._hydrate(client, sources, diagnostics=diagnostics)
        if diagnostics is not None:
            diagnostics.sources = len(sources)
        content = source_policy.render_context(sources)
        evidence_chars = sum(len(str(source.get("content") or "").strip()) for source in sources)
        status = "ok" if evidence_chars else ("insufficient_content" if sources else "no_hits")
        answer = content
        if status == "no_hits":
            answer = (
                "No matching documents were returned by the IMA knowledge base. "
                "Do not claim this query is supported by the textbook; try a more specific query."
            )
        elif status == "insufficient_content":
            answer = (
                "IMA returned references but no usable document text. "
                "Do not treat titles alone as evidence for an answer.\n\n" + content
            )
        return {
            "query": query,
            "answer": answer,
            "content": content,
            "sources": sources,
            "provider": PROVIDER,
            "retrieval_status": status,
            "source_count": len(sources),
            "evidence_chars": evidence_chars,
        }

    async def _hydrate(
        self,
        client,
        sources: list[dict[str, Any]],
        *,
        diagnostics: Optional[SearchDiagnostics] = None,
    ) -> None:
        """Replace thin or missing snippets with real source text, concurrently.

        Each fetch is independent, so they run together — a search that needs
        four documents costs one round-trip's latency, not four. A document that
        cannot be loaded keeps its snippet (or stays a title-only reference):
        one unavailable file must never discard the other matches.
        """
        targets = source_policy.hydration_targets(sources)
        if diagnostics is not None:
            diagnostics.hydration_targets = len(targets)
        if not targets:
            return
        results = await asyncio.gather(
            *(self._fetch_text(client, sources[index]) for index in targets),
            return_exceptions=True,
        )
        for index, result in zip(targets, results):
            if isinstance(result, BaseException):
                # HTTP errors may embed a signed COS URL; log only the error
                # class so short-lived download credentials never reach logs.
                self.logger.warning(
                    "Could not load IMA media '%s' (%s)",
                    sources[index]["chunk_id"],
                    type(result).__name__,
                )
                if diagnostics is not None:
                    diagnostics.hydration_failed += 1
            elif result:
                sources[index]["content"] = result
                if diagnostics is not None:
                    diagnostics.hydrated += 1
            elif diagnostics is not None:
                # Fetched without error but no text came back: the top-up ran
                # and the source still has nothing to reason from.
                diagnostics.hydration_failed += 1

    @staticmethod
    async def _fetch_text(client, source: dict[str, Any]) -> str:
        media = await client.get_media_content(source["chunk_id"])
        return await media_ops.extract_text(
            media,
            source["title"],
            max_chars=source_policy.MAX_FULLTEXT_CHARS,
        )

    def _error_result(self, query: str, exc: Exception, *, error_type: str) -> Dict[str, Any]:
        return {
            "query": query,
            "answer": str(exc),
            "content": "",
            "sources": [],
            "provider": PROVIDER,
            "error_type": error_type,
            "retrieval_status": "error",
            "source_count": 0,
            "evidence_chars": 0,
        }

    # ----- indexing (not applicable — owned by IMA) ------------------------

    async def initialize(self, kb_name: str, file_paths: List[str], **kwargs) -> bool:
        raise RuntimeError(
            "Tencent IMA knowledge bases are indexed by IMA; DeepTutor does not "
            "build or store their index. Add documents in IMA directly."
        )

    async def add_documents(self, kb_name: str, file_paths: List[str], **kwargs) -> bool:
        return await self.initialize(kb_name, file_paths, **kwargs)

    # ----- lifecycle ------------------------------------------------------

    async def delete(self, kb_name: str, **kwargs) -> bool:
        # The KB is only a pointer; the manager removes its config entry. Never
        # touch the user's IMA library. Nothing local to clean up here.
        return True


__all__ = ["ImaPipeline", "PROVIDER", "SearchDiagnostics"]
