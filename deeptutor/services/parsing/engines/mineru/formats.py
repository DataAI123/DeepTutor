"""Input formats supported by the current MinerU CLI and hosted API."""

from __future__ import annotations

import re

from .._versions import version_at_least

MIN_MINERU_VERSION = "3.4.5"
MAX_MINERU_VERSION_EXCLUSIVE = "4.0.0"

# Keep this list aligned with ``mineru/cli/common.py`` in the official MinerU
# project. DeepTutor uses dotted, lower-case suffixes throughout its parser
# protocol.
MINERU_PDF_FORMATS = frozenset({".pdf"})
MINERU_IMAGE_FORMATS = frozenset(
    {
        ".bmp",
        ".gif",
        ".jp2",
        ".jpeg",
        ".jpg",
        ".png",
        ".tiff",
        ".webp",
    }
)
MINERU_OFFICE_FORMATS = frozenset({".docx", ".pptx", ".xlsx"})
MINERU_SUPPORTED_FORMATS = frozenset(
    MINERU_PDF_FORMATS | MINERU_IMAGE_FORMATS | MINERU_OFFICE_FORMATS
)


def mineru_version_is_current(version_text: str) -> bool:
    """Whether a MinerU CLI version is in the supported 3.x range.

    MinerU 4.0 changed the CLI entrypoint, so the current adapter's legacy
    ``mineru -p ... -o ...`` invocation is only supported through 3.x.
    """
    match = re.search(r"\d+(?:\.\d+)+", str(version_text or ""))
    if not match:
        return False
    version = match.group(0)
    return version_at_least(version, MIN_MINERU_VERSION) and not version_at_least(
        version, MAX_MINERU_VERSION_EXCLUSIVE
    )


__all__ = [
    "MIN_MINERU_VERSION",
    "MAX_MINERU_VERSION_EXCLUSIVE",
    "MINERU_IMAGE_FORMATS",
    "MINERU_OFFICE_FORMATS",
    "MINERU_PDF_FORMATS",
    "MINERU_SUPPORTED_FORMATS",
    "mineru_version_is_current",
]
