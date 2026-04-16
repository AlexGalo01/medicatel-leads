from __future__ import annotations

import logging
from dataclasses import asdict, is_dataclass
from typing import Any

from langsmith import traceable

from mle.core.config import get_settings
from mle.observability.langsmith_setup import compact_node_patch, trace_inputs_from_graph_state
from mle.db.base import async_session_factory
from mle.db.models import Lead
from mle.repositories.jobs_repository import JobsRepository
from mle.repositories.leads_repository import LeadsRepository
from mle.services.export_service import export_leads_to_csv
from mle.state.graph_state import LeadSearchGraphState

logger = logging.getLogger(__name__)


def _truncate_text(raw_value: Any, max_length: int) -> str:
    normalized_text = str(raw_value or "").strip()
    if len(normalized_text) <= max_length:
        return normalized_text
    return normalized_text[: max_length - 1].rstrip() + "…"


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

    lead_metadata = dict(metadata)
    lead_metadata["crm"] = {
        "stage": "new",
        "notes": "",
        "activity_timeline": [],
    }

    return Lead(
        job_id=job_id,
        full_name=_truncate_text(lead_data.get("full_name", "Lead sin nombre"), 160),
        specialty=_truncate_text(lead_data.get("specialty", "No definido"), 120),
        country=_truncate_text(lead_data.get("country", "Honduras"), 80),
        city=_truncate_text(lead_data.get("city", "No definido"), 120),
        score=float(lead_data.get("score")) if lead_data.get("score") is not None else None,
        score_reasoning=_truncate_text(lead_data.get("score_reasoning", ""), 1000) or None,
        email=_truncate_text(lead_data.get("email", ""), 255) or None,
        whatsapp=_truncate_text(lead_data.get("whatsapp", ""), 30) or None,
        linkedin_url=_truncate_text(lead_data.get("linkedin_url", ""), 500) or None,
        primary_source_url=_truncate_text(primary_source_url, 500) or None,
        source_citations=source_citations if isinstance(source_citations, list) else [],
        exa_result_json={},
        langsmith_metadata=lead_metadata,
    )


@traceable(
    name="storage_export_node",
    run_type="chain",
    process_inputs=trace_inputs_from_graph_state,
    process_outputs=compact_node_patch,
)
async def storage_export_node(state: LeadSearchGraphState) -> dict[str, object]:
    """Persist scored leads and generate CSV export artifact."""
    try:
        normalized_leads = [_normalize_lead_item(item) for item in state.leads]
        normalized_leads = [lead for lead in normalized_leads if lead]
        normalized_leads = [
            lead
            for lead in normalized_leads
            if str(lead.get("purification_status", "valid")).lower() in {"valid", "partial"}
        ]
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
                    "contact_coverage": round(state.contact_coverage, 4),
                    "missing_contact_count": state.missing_contact_count,
                    "retry_used": state.retry_used,
                    "discarded_leads_count": len(state.discarded_leads),
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
                "contact_coverage": round(state.contact_coverage, 4),
                "missing_contact_count": state.missing_contact_count,
                "retry_used": state.retry_used,
                "discarded_leads_count": len(state.discarded_leads),
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

