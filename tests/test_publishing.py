from __future__ import annotations

from datetime import date
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from ouroboros_v2_publication.publishing import (
    build_orcid_work_payload,
    build_release_bundle,
    load_project_metadata,
    load_zenodo_metadata,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


class PublicationMetadataTest(unittest.TestCase):
    def test_release_bundle_contains_expected_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            bundle_path = Path(tmp_dir) / "release-bundle.zip"
            build_release_bundle(REPO_ROOT, bundle_path)
            with zipfile.ZipFile(bundle_path) as archive:
                names = set(archive.namelist())
            self.assertIn("paper/final/ouroboros-v2-publication-manuscript.pdf", names)
            self.assertIn("results/benchmark_summary.json", names)
            self.assertIn(".zenodo.json", names)

    def test_metadata_versions_are_consistent(self) -> None:
        project = load_project_metadata(REPO_ROOT)
        zenodo = load_zenodo_metadata(REPO_ROOT)
        self.assertEqual(project.version, "1.0.0")
        self.assertEqual(zenodo["version"], project.version)
        self.assertEqual(zenodo["title"], project.title)

    def test_orcid_payload_uses_doi_as_self_identifier(self) -> None:
        payload = build_orcid_work_payload(
            title="Ouroboros V2",
            doi="10.5281/zenodo.1234567",
            doi_url="https://doi.org/10.5281/zenodo.1234567",
            published_on=date(2026, 5, 4),
            description="Synthetic benchmark release.",
        )
        external_ids = payload["external-ids"]["external-id"]
        self.assertEqual(len(external_ids), 1)
        self.assertEqual(external_ids[0]["external-id-type"], "doi")
        self.assertEqual(external_ids[0]["external-id-relationship"], "SELF")
        self.assertEqual(payload["type"], "SOFTWARE")


if __name__ == "__main__":
    unittest.main()
