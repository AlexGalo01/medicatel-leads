from __future__ import annotations

import unittest

from mle.services.country_iso_resolution import (
    blob_has_target_country_markers,
    extract_parenthesized_iso_codes,
    first_matching_non_target_country_iso,
    resolve_country_iso2_from_text,
)


class CountryIsoResolutionTests(unittest.TestCase):
    def test_honduras_from_name(self) -> None:
        self.assertEqual(resolve_country_iso2_from_text("Honduras", "", ""), "HN")

    def test_honduras_from_query(self) -> None:
        self.assertEqual(resolve_country_iso2_from_text("", "", "desarrolladores .net en tegucigalpa honduras"), "HN")

    def test_parentheses_priority(self) -> None:
        blob = "Muhammed Mahmoud | Developer Mīt Ghamr, Ad Daqahliyah, Egypt (EG)"
        self.assertEqual(extract_parenthesized_iso_codes(blob), ["EG"])
        self.assertEqual(resolve_country_iso2_from_text("Egypt", "", blob), "EG")

    def test_first_matching_finds_egypt_when_not_honduras(self) -> None:
        blob = "Full Stack at HealthMasr Cairo, Egypt · engineer"
        self.assertEqual(first_matching_non_target_country_iso(blob, "HN"), "EG")

    def test_first_matching_skips_when_honduras_present(self) -> None:
        blob = "Consultor remoto para Honduras desde Cairo"
        self.assertTrue(blob_has_target_country_markers(blob, "HN"))
        self.assertIsNone(first_matching_non_target_country_iso(blob, "HN"))


if __name__ == "__main__":
    unittest.main()
