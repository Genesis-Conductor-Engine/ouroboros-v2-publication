"""Helpers for packaging the benchmark as a publication artifact."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
import tomllib
from typing import Any
import zipfile


DEFAULT_RELEASE_ASSETS = (
    "README.md",
    "FALSIFIABILITY.md",
    "LICENSE",
    "CITATION.cff",
    ".zenodo.json",
    "paper/final/ouroboros-v2-publication-manuscript.pdf",
    "results/benchmark_summary.json",
    "results/per_seed_results.csv",
    "results/mean_loss_curves.csv",
    "results/loss_curves.png",
    "results/mean_ttc.png",
    "results/hessian_eigenspectrum.png",
    "results/pca_repulsion_force.png",
)


@dataclass(frozen=True)
class PublicationBundle:
    version: str
    title: str
    description: str
    release_assets: tuple[Path, ...]


def load_project_metadata(repo_root: Path) -> PublicationBundle:
    pyproject = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    zenodo_metadata = json.loads((repo_root / ".zenodo.json").read_text(encoding="utf-8"))
    release_assets = tuple(repo_root / asset for asset in DEFAULT_RELEASE_ASSETS)
    missing_assets = [str(path) for path in release_assets if not path.exists()]
    if missing_assets:
        raise FileNotFoundError(f"Missing publication assets: {missing_assets}")
    return PublicationBundle(
        version=pyproject["project"]["version"],
        title=zenodo_metadata["title"],
        description=str(zenodo_metadata["description"]),
        release_assets=release_assets,
    )


def build_release_bundle(repo_root: Path, output_path: Path) -> Path:
    bundle = load_project_metadata(repo_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for asset in bundle.release_assets:
            archive.write(asset, asset.relative_to(repo_root))
    return output_path


def load_zenodo_metadata(repo_root: Path) -> dict[str, Any]:
    return json.loads((repo_root / ".zenodo.json").read_text(encoding="utf-8"))


def build_orcid_work_payload(
    *,
    title: str,
    doi: str,
    doi_url: str,
    published_on: date,
    description: str,
) -> dict[str, Any]:
    return {
        "title": {
            "title": {
                "value": title,
            }
        },
        "journal-title": {
            "value": "Zenodo",
        },
        "short-description": description,
        "type": "SOFTWARE",
        "url": {
            "value": doi_url,
        },
        "publication-date": {
            "year": {"value": f"{published_on.year:04d}"},
            "month": {"value": f"{published_on.month:02d}"},
            "day": {"value": f"{published_on.day:02d}"},
        },
        "external-ids": {
            "external-id": [
                {
                    "external-id-type": "doi",
                    "external-id-value": doi,
                    "external-id-url": {"value": doi_url},
                    "external-id-relationship": "SELF",
                }
            ]
        },
    }
