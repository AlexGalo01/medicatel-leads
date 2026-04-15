from __future__ import annotations

import logging
from dataclasses import asdict, is_dataclass
from typing import Any

from mle.core.config import get_settings
from mle.db.base import async_session_factory
from mle.db.models import Lead
from mle.repositories.jobs_repository import JobsRepository
from mle.repositories.leads_repository import LeadsRepository
from mle.services.export_service import export_leads_to_csv
from mle.state.graph_state import LeadSearchGraphState

logger = logging.getLogger(__name__)


def _normalize_lead_item(lead_item: Any) -> dict[str, Any]:
    if isinstance(lead_item, dict):
        return lead_item
    if is_dataclass(lead_item):
        return asdict(lead_item)
    return {}


def _build_lead_model(job_id: Any, lead_data: dict[str, Any], metadata: dict[str, Any]) -> Lead:
    primary_source_url = ""
    source_citations = lead_data.get("source_citations", [])
    if source_citations and isinstance(source_citations, list):
        first_citation = source_citations[0]
        if isinstance(first_citation, dict):
            primary_source_url = str(first_citation.get("url", "")).strip()

    return Lead(
        job_id=job_id,
        full_name=str(lead_data.get("full_name", "Lead sin nombre")),
        specialty=str(lead_data.get("specialty", "No definido")),
        country=str(lead_data.get("country", "Honduras")),
        city=str(lead_data.get("city", "No definido")),
        score=float(lead_data.get("score")) if lead_data.get("score") is not None else None,
        score_reasoning=str(lead_data.get("score_reasoning", "")) or None,
        email=str(lead_data.get("email", "")) or None,
        whatsapp=str(lead_data.get("whatsapp", "")) or None,
        linkedin_url=str(lead_data.get("linkedin_url", "")) or None,
        primary_source_url=primary_source_url or None,
        source_citations=source_citations if isinstance(source_citations, list) else [],
        exa_result_json={},
        langsmith_metadata=metadata,
    )


async def storage_export_node(state: LeadSearchGraphState) -> dict[str, object]:
    """Persist scored leads and generate CSV export artifact."""
    try:
        normalized_leads = [_normalize_lead_item(item) for item in state.leads]
        normalized_leads = [lead for lead in normalized_leads if lead]
        if not normalized_leads:
            raise ValueError("No hay leads procesados para almacenar.")

        settings = get_settings()

        async with async_session_factory() as session:
            leads_repository = LeadsRepository(session)
            jobs_repository = JobsRepository(session)

            for lead_data in normalized_leads:
                lead_model = _build_lead_model(state.job_id, lead_data, state.langsmith_metadata)
                await leads_repository.create(lead_model)

            export_path = export_leads_to_csv(
                job_id=state.job_id,
                leads=normalized_leads,
                export_dir_path=settings.export_dir,
            )
            await jobs_repository.update_status(
                job_id=state.job_id,
                status="completed",
                progress=100,
                metadata_json={
                    **state.langsmith_metadata,
                    "pipeline_stage": "done",
                    "export_path": export_path,
                    "stored_leads": len(normalized_leads),
                },
            )

        logger.info(
            "Storage export node completado para job_id=%s con %s leads",
            state.job_id,
            len(normalized_leads),
        )
        return {
            "status": "completed",
            "current_stage": "done",
            "progress": 100,
            "langsmith_metadata": {
                **state.langsmith_metadata,
                "pipeline_stage": "done",
                "export_path": export_path,
                "stored_leads": len(normalized_leads),
            },
        }
    except Exception as exc:  # noqa: BLE001 - graceful pipeline behavior
        error_message = f"Storage export node fallo: {exc!s}"
        logger.exception(error_message)
        return {
            "status": "error",
            "current_stage": "storage_export",
            "progress": state.progress,
            "errors": [*state.errors, error_message],
            "langsmith_metadata": {
                **state.langsmith_metadata,
                "pipeline_stage": "storage_export",
                "storage_error": error_message,
            },
        }

