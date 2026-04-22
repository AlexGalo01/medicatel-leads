from __future__ import annotations

import logging
from typing import Any

from langsmith import traceable

from mle.db.base import async_session_factory
from mle.db.models import DirectoryEntry
from mle.observability.langsmith_setup import compact_node_patch, trace_inputs_from_graph_state
from mle.repositories.directory_entries_repository import DirectoryEntriesRepository
from mle.state.graph_state import LeadSearchGraphState

logger = logging.getLogger(__name__)


def _snippet_from_result(result: dict[str, Any]) -> str:
    highlights = result.get("highlights")
    if isinstance(highlights, list):
        joined = " | ".join(str(item) for item in highlights[:16])
        return joined[:7900]
    text_value = result.get("text")
    return str(text_value or "")[:7900]


@traceable(
    name="directory_persist_node",
    run_type="chain",
    process_inputs=trace_inputs_from_graph_state,
    process_outputs=compact_node_patch,
)
async def directory_persist_node(state: LeadSearchGraphState) -> dict[str, object]:
    """
    Persiste filas de directorio a partir de resultados Exa fusionados.
    Falla de forma no bloqueante: el pipeline de leads continua aunque falle el INSERT.
    """
    rows_stored = 0
    if not state.exa_raw_results:
        return {
            "status": "running",
            "current_stage": "scoring_cleaning",
            "progress": 55,
            "langsmith_metadata": {
                **state.langsmith_metadata,
                "directory_rows_stored": 0,
                "pipeline_phase": "directory",
            },
        }

    plan = state.search_plan if isinstance(state.search_plan, dict) else {}
    entity_type = str(plan.get("entity_type", ""))[:120]
    geo = plan.get("geo") if isinstance(plan.get("geo"), dict) else {}
    city = str(geo.get("city", ""))[:120] if geo else ""
    country = str(geo.get("country", ""))[:80] if geo else ""

    entries: list[DirectoryEntry] = []
    for raw in state.exa_raw_results:
        if not isinstance(raw, dict):
            continue
        url = str(raw.get("url", "")).strip()[:2000]
        title = str(raw.get("title", "")).strip()[:500]
        entries.append(
            DirectoryEntry(
                job_id=state.job_id,
                display_title=title or url or "Sin titulo",
                primary_url=url,
                snippet=_snippet_from_result(raw) or None,
                entity_type=entity_type,
                city=city,
                country=country,
                raw_exa_json=raw,
            )
        )

    try:
        async with async_session_factory() as session:
            repo = DirectoryEntriesRepository(session)
            await repo.bulk_create(entries)
        rows_stored = len(entries)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "No se pudieron guardar filas de directorio job_id=%s: %s",
            state.job_id,
            exc,
        )

    return {
        "status": "running",
        "current_stage": "scoring_cleaning",
        "progress": 55,
        "langsmith_metadata": {
            **state.langsmith_metadata,
            "directory_rows_stored": rows_stored,
            "pipeline_phase": "directory",
        },
    }
