from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from mle.services.profile_interpret_service import (
    PROFESSIONAL_SUMMARY_MAX_LEN,
    _extract_experiences_from_blob,
    _sanitize_summary_text,
    _strip_markdown_noise,
    _strip_profile_blob_noise,
    extract_profile_summary,
)


class StripMarkdownNoiseTests(unittest.TestCase):
    def test_strips_heading_prefixes_per_line(self) -> None:
        raw = "## About\n### Experience\nTexto sin encabezado."
        out = _strip_markdown_noise(raw)
        self.assertNotIn("##", out)
        self.assertNotIn("###", out)
        self.assertIn("Texto sin encabezado.", out)


class StripProfileBlobNoiseTests(unittest.TestCase):
    def test_strips_english_social_and_labels(self) -> None:
        raw = (
            "Médico (Current) 118 connections 120 followers Department: Medicina "
            "Level: Senior at Hospital Uno About Total E"
        )
        out = _strip_profile_blob_noise(raw)
        self.assertNotIn("connections", out.lower())
        self.assertNotIn("followers", out.lower())
        self.assertNotIn("Department", out)
        self.assertNotIn("Level", out)
        self.assertIn("Médico", out)
        self.assertIn("Hospital Uno", out)


class ExtractExperiencesHeuristicTests(unittest.TestCase):
    def test_at_split_keeps_longer_fields_with_word_boundary(self) -> None:
        role = "Ginecologo" + "x" * 80
        org = "Hospital del Valle San Pedro" + "y" * 100
        blob = f"X Experience {role} at {org}"
        items = _extract_experiences_from_blob(blob)
        self.assertTrue(len(items) >= 1)
        self.assertIn("Ginecologo", items[0]["role"] or "")
        self.assertGreater(len(items[0]["role"] or ""), 50)


class SanitizeSummaryTextTests(unittest.TestCase):
    def test_word_boundary_avoids_mid_word_cut(self) -> None:
        text = "a " * 50 + "palabra_larga_final"
        out = _sanitize_summary_text(text, max_len=30, at_word_boundary=True)
        self.assertIsNotNone(out)
        assert out is not None
        self.assertLessEqual(len(out), 30)
        self.assertNotIn("palabra", out)
        self.assertFalse(out.endswith(","))

    def test_long_summary_respects_max_with_space(self) -> None:
        words = " ".join([f"w{i}" for i in range(80)])
        out = _sanitize_summary_text(words, max_len=PROFESSIONAL_SUMMARY_MAX_LEN, at_word_boundary=True)
        self.assertIsNotNone(out)
        assert out is not None
        self.assertLessEqual(len(out), PROFESSIONAL_SUMMARY_MAX_LEN)


class ProfileSummaryServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_extract_profile_summary_uses_fallback_when_blob_detected(self) -> None:
        mocked_json = {
            "professional_summary": "## Experience Total Experience: 10 years and 2 months connections followers",
            "company": "Hospital Central",
            "location": "Tegucigalpa",
            "confidence": "high",
        }
        with patch("mle.services.profile_interpret_service.GeminiClient.complete_json_prompt", new=AsyncMock(return_value=mocked_json)):
            summary = await extract_profile_summary(
                title="Wendy Yolani Urbina",
                specialty="Cuidados Intensivos Pediátricos",
                city="Tegucigalpa",
                snippet="Perfil con experiencia hospitalaria y residencia.",
            )
        self.assertEqual(summary["professional_summary"], "Cuidados Intensivos Pediátricos")
        self.assertEqual(summary["confidence"], "low")
        self.assertEqual(summary["location"], "Tegucigalpa")

    async def test_extract_profile_summary_uses_model_when_clean(self) -> None:
        mocked_json = {
            "professional_summary": "Pediatra con experiencia reciente en cuidados intensivos pediátricos.",
            "company": "Instituto Nacional de Pediatría",
            "location": "México",
            "confidence": "high",
        }
        with patch("mle.services.profile_interpret_service.GeminiClient.complete_json_prompt", new=AsyncMock(return_value=mocked_json)):
            summary = await extract_profile_summary(
                title="Dra. Prueba",
                specialty="Pediatría",
                city="",
                snippet="",
            )
        self.assertEqual(summary["professional_summary"], mocked_json["professional_summary"])
        self.assertEqual(summary["company"], mocked_json["company"])
        self.assertEqual(summary["location"], mocked_json["location"])
        self.assertEqual(summary["confidence"], "high")

    async def test_blob_path_uses_second_llm_experiences_when_non_empty(self) -> None:
        main = {
            "professional_summary": "department: Medicina 118 connections 120 followers at Hospital",
            "company": None,
            "location": None,
            "confidence": "high",
        }
        ex_items = {
            "items": [
                {
                    "role": "Ginecólogo y obstetra",
                    "organization": "Hospital del Valle",
                    "period": "2007 - actual",
                }
            ]
        }
        with patch(
            "mle.services.profile_interpret_service.GeminiClient.complete_json_prompt",
            new=AsyncMock(side_effect=[main, ex_items]),
        ):
            summary = await extract_profile_summary(
                title="Dr. Prueba",
                specialty="",
                city="Tegucigalpa",
                snippet="Texto con department: y level: para marcar como blob de resumen.",
            )
        self.assertEqual(summary["notes"], "blob_llm_experiences")
        self.assertEqual(len(summary["experiences"]), 1)
        self.assertIn("Ginecólogo", summary["experiences"][0]["role"] or "")
        self.assertEqual(summary["experiences"][0].get("organization"), "Hospital del Valle")


if __name__ == "__main__":
    unittest.main()
