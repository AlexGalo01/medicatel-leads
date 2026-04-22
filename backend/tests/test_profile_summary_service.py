from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from mle.services.profile_interpret_service import (
    PROFESSIONAL_SUMMARY_MAX_LEN,
    _sanitize_summary_text,
    _strip_markdown_noise,
    extract_profile_summary,
)


class StripMarkdownNoiseTests(unittest.TestCase):
    def test_strips_heading_prefixes_per_line(self) -> None:
        raw = "## About\n### Experience\nTexto sin encabezado."
        out = _strip_markdown_noise(raw)
        self.assertNotIn("##", out)
        self.assertNotIn("###", out)
        self.assertIn("Texto sin encabezado.", out)


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


if __name__ == "__main__":
    unittest.main()
