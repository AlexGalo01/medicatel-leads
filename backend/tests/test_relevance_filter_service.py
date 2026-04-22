from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from mle.services.relevance_filter_service import (
    filter_exa_list_heuristic_only,
    filter_exa_raw_results_by_relevance,
)


class RelevanceFilterServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_heuristic_drops_eg_when_target_hn(self) -> None:
        raw = [
            {
                "title": "Dev local",
                "url": "https://linkedin.com/in/hn",
                "highlights": ["Tegucigalpa, Francisco Morazán, Honduras (HN)"],
            },
            {
                "title": "Muhammed Mahmoud",
                "url": "https://linkedin.com/in/eg",
                "highlights": ["Full Stack .NET Trainee at DEPI Mīt Ghamr, Ad Daqahliyah, Egypt (EG)"],
            },
        ]
        criteria = {"country_iso2": "HN", "city": "Tegucigalpa", "country_text": "Honduras"}
        gemini = SimpleNamespace(
            complete_json_prompt=AsyncMock(
                return_value={"verdicts": [{"index": 0, "match": True, "reason_es": "Ubicación Honduras."}]}
            )
        )
        kept, meta = await filter_exa_raw_results_by_relevance(
            raw_results=raw,
            user_query="desarrolladores .net en tegucigalpa honduras",
            relevance_criteria=criteria,
            gemini_client=gemini,
            chunk_size=8,
        )
        self.assertEqual(meta.get("relevance_filter_heuristic_drops"), 1)
        self.assertEqual(len(kept), 1)
        self.assertIn("tegucigalpa", str((kept[0].get("highlights") or [""])[0]).lower())

    async def test_gemini_marks_non_match(self) -> None:
        raw = [
            {
                "title": "Perfil ambiguo",
                "url": "https://example.com/a",
                "highlights": ["Consultor .NET remoto para clientes en LATAM"],
            },
        ]
        criteria = {"country_iso2": "HN", "country_text": "Honduras"}
        gemini = SimpleNamespace(
            complete_json_prompt=AsyncMock(
                return_value={"verdicts": [{"index": 0, "match": False, "reason_es": "Sin señal de Honduras."}]}
            )
        )
        kept, meta = await filter_exa_raw_results_by_relevance(
            raw_results=raw,
            user_query="solo perfiles en honduras",
            relevance_criteria=criteria,
            gemini_client=gemini,
        )
        self.assertEqual(meta.get("relevance_filter_kept"), 0)
        self.assertEqual(meta.get("relevance_filter_dropped"), 1)
        self.assertEqual(len(kept), 0)

    async def test_heuristic_drops_cairo_egypt_without_paren(self) -> None:
        raw = [
            {
                "title": "Mohamed Salah Full Stack DotNet Developer",
                "url": "https://linkedin.com/in/ms",
                "highlights": ["System Administrator at HealthMasr Cairo, Egypt · network administrator"],
            },
        ]
        criteria = {"country_iso2": "HN", "country_text": "Honduras"}
        gemini = SimpleNamespace(complete_json_prompt=AsyncMock(return_value={"verdicts": []}))
        kept, meta = await filter_exa_raw_results_by_relevance(
            raw_results=raw,
            user_query="ingenieros en sistemas hondureños",
            relevance_criteria=criteria,
            gemini_client=gemini,
        )
        self.assertEqual(len(kept), 0)
        self.assertGreaterEqual(int(meta.get("relevance_filter_heuristic_drops") or 0), 1)
        gemini.complete_json_prompt.assert_not_called()

    def test_heuristic_only_drops_us_from_snippet_for_hn_target(self) -> None:
        items = [
            {
                "title": "Roberto Ortega",
                "url": "https://linkedin.com/in/ro",
                "snippet": "# Roberto Ortega\n\nOperations Manager at Fullerton\n\nBridgewater, New Jersey, United States (US) 323 connections",
            },
        ]
        kept, meta = filter_exa_list_heuristic_only(items, "HN")
        self.assertEqual(len(kept), 0)
        self.assertEqual(meta.get("relevance_heuristic_only_drops"), 1)

    async def test_empty_verdicts_drop_when_country_strict(self) -> None:
        raw = [
            {
                "title": "Perfil sin ubicación clara",
                "url": "https://example.com/x",
                "highlights": ["Desarrollador .NET varios años de experiencia"],
            },
        ]
        criteria = {"country_iso2": "HN"}
        gemini = SimpleNamespace(complete_json_prompt=AsyncMock(return_value={"verdicts": []}))
        kept, _meta = await filter_exa_raw_results_by_relevance(
            raw_results=raw,
            user_query="honduras",
            relevance_criteria=criteria,
            gemini_client=gemini,
        )
        self.assertEqual(len(kept), 0)


if __name__ == "__main__":
    unittest.main()
