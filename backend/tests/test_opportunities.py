from __future__ import annotations

import unittest
from uuid import uuid4

from mle.db.models import SearchJob
from mle.repositories.opportunities_repository import _find_preview_row, apply_profile_overrides_patch


class FindPreviewRowTests(unittest.TestCase):
    def test_returns_row_when_index_matches(self) -> None:
        job = SearchJob(
            id=uuid4(),
            specialty="busqueda",
            country="HN",
            city="Tegucigalpa",
            metadata_json={
                "exa_results_preview": [
                    {"index": 2, "title": "Clínica Norte", "url": "https://example.com/n", "snippet": "x"},
                ],
            },
        )
        row = _find_preview_row(job, 2)
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["title"], "Clínica Norte")

    def test_returns_none_when_index_missing(self) -> None:
        job = SearchJob(
            specialty="busqueda",
            country="HN",
            city="Tegucigalpa",
            metadata_json={"exa_results_preview": [{"index": 1, "title": "A", "url": ""}]},
        )
        self.assertIsNone(_find_preview_row(job, 5))

    def test_returns_none_when_preview_not_list(self) -> None:
        job = SearchJob(
            specialty="busqueda",
            country="HN",
            city="Tegucigalpa",
            metadata_json={},
        )
        self.assertIsNone(_find_preview_row(job, 1))


class ApplyProfileOverridesPatchTests(unittest.TestCase):
    def test_sets_about_and_location(self) -> None:
        out = apply_profile_overrides_patch({}, {"about": "  Bio ", "location": " Tegus "})
        self.assertEqual(out["about"], "Bio")
        self.assertEqual(out["location"], "Tegus")

    def test_null_removes_keys(self) -> None:
        out = apply_profile_overrides_patch(
            {"about": "x", "location": "y", "experiences": [{"role": "R", "organization": None, "period": None}]},
            {"about": None, "location": None, "experiences": None},
        )
        self.assertEqual(out, {})

    def test_experiences_list_normalized(self) -> None:
        out = apply_profile_overrides_patch(
            {},
            {
                "experiences": [
                    {"role": " Dev ", "organization": " ACME ", "period": " 2020 "},
                ]
            },
        )
        self.assertEqual(len(out["experiences"]), 1)
        self.assertEqual(out["experiences"][0]["role"], "Dev")
        self.assertEqual(out["experiences"][0]["organization"], "ACME")
        self.assertEqual(out["experiences"][0]["period"], "2020")
