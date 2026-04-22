"""Constantes y tipos para oportunidades comerciales (vista previa Exa → CRM)."""

from __future__ import annotations

from typing import Literal

# Claves canónicas (API / BD). Etiquetas en español solo en frontend.
OPPORTUNITY_STAGE_KEYS: tuple[str, ...] = (
    "first_contact",
    "presentation",
    "response",
    "documents_wait",
    "agreement_sign",
    "medicatel_profile",
)

OpportunityStageLiteral = Literal[
    "first_contact",
    "presentation",
    "response",
    "documents_wait",
    "agreement_sign",
    "medicatel_profile",
]

# Subestado cuando stage == "response"
RESPONSE_OUTCOME_KEYS: tuple[str, ...] = ("pending", "positive", "negative")

ResponseOutcomeLiteral = Literal["pending", "positive", "negative"]

CONTACT_KIND_KEYS: tuple[str, ...] = ("email", "phone", "whatsapp", "linkedin", "other")

ContactKindLiteral = Literal["email", "phone", "whatsapp", "linkedin", "other"]

DEFAULT_OPPORTUNITY_STAGE = "first_contact"
