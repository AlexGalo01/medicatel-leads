from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from mle.services.query_expansion_service import expand_user_search_query


class QueryExpansionServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_expand_success(self) -> None:
        expanded = ("Perfiles de medicos en Honduras con email corporativo " * 2).strip()

        with patch("mle.services.query_expansion_service.GeminiClient") as mock_cls:
            mock_cls.return_value.expand_search_query = AsyncMock(
                return_value={
                    "expanded_query": expanded + " ",
                    "channel_instructions": "Priorizar email institucional.",
                    "negative_constraints": "Excluir listados masivos sin contacto.",
                }
            )
            text, meta = await expand_user_search_query(
                user_query="medicos honduras",
                contact_channels=["email", "whatsapp"],
                search_focus="general",
                notes="sin excel",
            )

        self.assertEqual(text, expanded)
        self.assertIs(meta.get("fallback"), False)
        self.assertEqual(meta.get("focus"), "general")

    async def test_expand_fallback_on_error(self) -> None:
        with patch("mle.services.query_expansion_service.GeminiClient") as mock_cls:
            mock_cls.return_value.expand_search_query = AsyncMock(side_effect=RuntimeError("API error"))
            text, meta = await expand_user_search_query(
                user_query="  cardiologos  ",
                contact_channels=["linkedin"],
                search_focus="linkedin",
                notes=None,
            )

        self.assertEqual(text, "cardiologos")
        self.assertIs(meta.get("fallback"), True)
        self.assertIn("error", meta)
