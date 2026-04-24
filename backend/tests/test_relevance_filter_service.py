from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from mle.services.relevance_filter_service import (
    _exa_category_entity_rules,
    _heuristic_drop_reason,
    _parse_verdicts,
    _professional_intent_rules_block,
    _sector_intent_rules_block,
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

    def test_exa_category_entity_rules_non_empty(self) -> None:
        self.assertIn("PERSONAS", _exa_category_entity_rules("people"))
        self.assertIn("EMPRESAS", _exa_category_entity_rules("company"))
        self.assertEqual(_exa_category_entity_rules(None), "")
        self.assertEqual(_exa_category_entity_rules(""), "")

    def test_sector_intent_block_generic_and_consistent(self) -> None:
        """Sector rules are now generic (no hardcoded keyword detection)."""
        block_health = _sector_intent_rules_block("clínicas pediátricas en San Pedro Sula")
        block_other = _sector_intent_rules_block("suministros de oficina tegucigalpa")
        # Both queries should return the same generic block
        self.assertEqual(block_health, block_other)
        self.assertIn("beneficio de la duda", block_health.lower())

    def test_professional_intent_block_includes_search_term(self) -> None:
        block = _professional_intent_rules_block("Psicólogos en Tegucigalpa", "Psicólogos")
        self.assertIn("Psicólogos", block)
        self.assertIn("REGLA PRINCIPAL", block)

    def test_professional_intent_block_falls_back_to_query(self) -> None:
        block = _professional_intent_rules_block("Restaurantes en CDMX", None)
        self.assertIn("Restaurantes en CDMX", block)

    def test_professional_intent_block_empty_returns_empty(self) -> None:
        block = _professional_intent_rules_block("", None)
        self.assertEqual(block, "")

    def test_confidence_threshold_rejects_low_confidence(self) -> None:
        parsed = {"verdicts": [{"index": 0, "match": True, "confidence": 3, "reason_es": "dudoso"}]}
        result = _parse_verdicts(parsed, confidence_threshold=5)
        self.assertFalse(result[0])

    def test_confidence_threshold_keeps_high_confidence(self) -> None:
        parsed = {"verdicts": [{"index": 0, "match": True, "confidence": 8, "reason_es": "claro"}]}
        result = _parse_verdicts(parsed, confidence_threshold=5)
        self.assertTrue(result[0])

    def test_confidence_threshold_ignores_false_matches(self) -> None:
        parsed = {"verdicts": [{"index": 0, "match": False, "confidence": 9, "reason_es": "no coincide"}]}
        result = _parse_verdicts(parsed, confidence_threshold=5)
        self.assertFalse(result[0])

    def test_confidence_missing_defaults_to_keep(self) -> None:
        """When confidence is not provided, default to 10 (keep the match)."""
        parsed = {"verdicts": [{"index": 0, "match": True, "reason_es": "ok"}]}
        result = _parse_verdicts(parsed, confidence_threshold=5)
        self.assertTrue(result[0])

    def test_heuristic_drop_india_private_limited_without_hn_signal(self) -> None:
        # Sin la palabra "india" el pre-filtro por país (first_matching) no aplica; la heurística Mumbai+PL cubre el caso.
        item = {
            "title": "Kairos Supplies Private Limited",
            "snippet": "Operations in Mumbai. Private Limited company registered 2018.",
        }
        reason = _heuristic_drop_reason(item, "HN")
        self.assertIsNotNone(reason)
        self.assertIn("India", reason)

    async def test_prompt_includes_people_entity_block(self) -> None:
        raw = [
            {
                "title": "Dra. Ana López",
                "url": "https://linkedin.com/in/ana-lopez",
                "highlights": ["Médica en Tegucigalpa, Francisco Morazán, Honduras (HN)"],
            },
        ]
        criteria = {"country_iso2": "HN", "exa_category": "people"}
        mock = AsyncMock(
            return_value={"verdicts": [{"index": 0, "match": True, "reason_es": "Persona y Honduras."}]}
        )
        gemini = SimpleNamespace(complete_json_prompt=mock)
        await filter_exa_raw_results_by_relevance(
            raw_results=raw,
            user_query="médicos honduras",
            relevance_criteria=criteria,
            gemini_client=gemini,
        )
        prompt = str(mock.call_args[0][0])
        self.assertIn("PERSONAS", prompt)
        self.assertIn("linkedin.com/in/", prompt)
        self.assertIn('"exa_category": "people"', prompt)

    async def test_prompt_includes_company_entity_block(self) -> None:
        raw = [
            {
                "title": "Clínica Demo S.A.",
                "url": "https://linkedin.com/company/clinica-demo",
                "highlights": ["Institución de salud en San Pedro Sula, Honduras (HN)"],
            },
        ]
        criteria = {"country_iso2": "HN", "exa_category": "company"}
        mock = AsyncMock(
            return_value={"verdicts": [{"index": 0, "match": True, "reason_es": "Entidad y Honduras."}]}
        )
        gemini = SimpleNamespace(complete_json_prompt=mock)
        _kept, meta = await filter_exa_raw_results_by_relevance(
            raw_results=raw,
            user_query="clínicas honduras",
            relevance_criteria=criteria,
            gemini_client=gemini,
        )
        prompt = str(mock.call_args[0][0])
        self.assertIn("EMPRESAS", prompt)
        self.assertIn("linkedin.com/company/", prompt)
        self.assertEqual(meta.get("relevance_filter_exa_category"), "company")

    async def test_prompt_includes_professional_intent_and_sector_blocks(self) -> None:
        raw = [
            {
                "title": "Clínica La Esperanza",
                "url": "https://example.com/c",
                "highlights": ["Tegucigalpa, Francisco Morazán, Honduras (HN)"],
            },
        ]
        criteria = {"country_iso2": "HN", "role_or_stack_hint": "clínicas de pediatría"}
        mock = AsyncMock(
            return_value={"verdicts": [{"index": 0, "match": True, "confidence": 9, "reason_es": "ok"}]}
        )
        gemini = SimpleNamespace(complete_json_prompt=mock)
        await filter_exa_raw_results_by_relevance(
            raw_results=raw,
            user_query="clínicas de pediatría en honduras",
            relevance_criteria=criteria,
            gemini_client=gemini,
        )
        prompt = str(mock.call_args[0][0])
        self.assertIn("REGLA PRINCIPAL", prompt)
        self.assertIn("clínicas de pediatría", prompt)
        self.assertIn("alineación sectorial", prompt.lower())
        self.assertIn("confidence", prompt)

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
