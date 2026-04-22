from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class SearchPlanGeo(BaseModel):
    country: str = ""
    city: str = ""


class SearchPlan(BaseModel):
    """
    Plan estructurado para fase directorio (expansion Gemini).
    Agnostico al vertical; contactos se rellenan en fases posteriores.
    """

    entity_type: str = Field(default="", max_length=200)
    geo: SearchPlanGeo = Field(default_factory=SearchPlanGeo)
    main_query: str = Field(min_length=1, max_length=1200)
    additional_queries: list[str] = Field(default_factory=list, max_length=12)
    required_channels: list[str] = Field(default_factory=list)
    negative_constraints: str = Field(default="", max_length=800)
    clarifying_question: str | None = Field(default=None, max_length=500)
    exa_category: str | None = Field(default=None, max_length=32)

    @field_validator("additional_queries", mode="before")
    @classmethod
    def _cap_additional(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return []
        cleaned: list[str] = []
        for item in value[:8]:
            text = str(item).strip()
            if text and text not in cleaned:
                cleaned.append(text[:400])
        return cleaned

    @field_validator("exa_category", mode="before")
    @classmethod
    def _normalize_category(cls, value: Any) -> str | None:
        if value is None or value == "":
            return None
        text = str(value).strip().lower()
        if text in ("people", "company"):
            return text
        return None

    def model_dump_for_job(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def search_plan_from_fallback(user_query: str, contact_channels: list[str]) -> SearchPlan:
    return SearchPlan(
        entity_type="",
        geo=SearchPlanGeo(),
        main_query=user_query.strip() or ".",
        additional_queries=[],
        required_channels=list(contact_channels),
        negative_constraints="",
        clarifying_question=None,
        exa_category=None,
    )
