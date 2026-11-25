"""Resolution agent: generates a draft only when retrieved evidence exists."""
from __future__ import annotations
from typing import Any


def run_resolution(
    pipeline: Any, subject: str, body: str, language: str,
    predictions: dict[str, Any], sources: list[dict[str, Any]],
) -> dict[str, Any]:
    if not sources:
        return {
            "draft": None,
            "generated": False,
            "generation_error": "Generation skipped because no approved knowledge source was retrieved.",
            "source_count": 0,
        }
    try:
        draft = pipeline.generator.draft(
            subject=subject, body=body, language=language,
            predicted=predictions, sources=sources,
        )
        return {
            "draft": draft,
            "generated": bool(draft),
            "generation_error": None if draft else "The generator returned an empty draft.",
            "source_count": len(sources),
        }
    except Exception as exc:
        return {
            "draft": None,
            "generated": False,
            "generation_error": f"{type(exc).__name__}: {str(exc)[:350]}",
            "source_count": len(sources),
        }
