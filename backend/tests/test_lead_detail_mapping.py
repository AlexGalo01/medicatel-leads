"""Tests for API mapping helpers (sin base de datos)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from mle.api.routes import _lead_read_to_detail, _serialize_source_citations
from mle.schemas.leads import LeadContacts, LeadRead, LeadSourceCitation


def test_serialize_source_citations_mixed() -> None:
    raw: list[object] = [
        {"url": "https://a.example", "title": "A"},
        LeadSourceCitation(url="https://b.example", title="B", confidence="high"),
    ]
    out = _serialize_source_citations(raw)
    assert len(out) == 2
    assert out[0]["url"] == "https://a.example"
    assert out[1]["url"] == "https://b.example"
    assert out[1]["confidence"] == "high"


def test_lead_read_to_detail_enrichment_from_metadata() -> None:
    job_id = uuid4()
    lead_id = uuid4()
    now = datetime.now(timezone.utc)
    lead = LeadRead(
        id=lead_id,
        job_id=job_id,
        full_name="Dra. Prueba",
        specialty="Medicina interna",
        country="HN",
        city="San Pedro Sula",
        contacts=LeadContacts(),
        validation_status="ok",
        created_at=now,
        updated_at=now,
        langsmith_metadata={
            "last_deep_enrich": {
                "status": "no_data",
                "message": "No se encontraron datos verificables en las fuentes consultadas.",
            }
        },
    )
    detail = _lead_read_to_detail(lead)
    assert detail.enrichment_status == "no_data"
    assert detail.enrichment_message is not None
    assert "verificables" in detail.enrichment_message
