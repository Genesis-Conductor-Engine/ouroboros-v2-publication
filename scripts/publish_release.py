#!/usr/bin/env python3
"""Publish the benchmark bundle to Zenodo and ORCID when credentials exist."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any
from urllib import error, request

from ouroboros_v2_publication.publishing import (
    build_orcid_work_payload,
    build_release_bundle,
    load_project_metadata,
    load_zenodo_metadata,
)


ZENODO_API = "https://zenodo.org/api"
ZENODO_SANDBOX_API = "https://sandbox.zenodo.org/api"
ORCID_API = "https://api.orcid.org/v3.0"
ORCID_SANDBOX_API = "https://api.sandbox.orcid.org/v3.0"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def http_json(
    method: str,
    url: str,
    *,
    token: str,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    encoded_payload = None if payload is None else json.dumps(payload).encode("utf-8")
    request_headers = {"Authorization": f"Bearer {token}"}
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
    if headers:
        request_headers.update(headers)
    req = request.Request(url, data=encoded_payload, headers=request_headers, method=method)
    with request.urlopen(req) as response:
        body = response.read()
    if not body:
        return {}
    return json.loads(body.decode("utf-8"))


def upload_file(bucket_url: str, file_path: Path, *, token: str) -> dict[str, Any]:
    with file_path.open("rb") as handle:
        data = handle.read()
    req = request.Request(
        f"{bucket_url}/{file_path.name}",
        data=data,
        headers={"Authorization": f"Bearer {token}"},
        method="PUT",
    )
    with request.urlopen(req) as response:
        return json.loads(response.read().decode("utf-8"))


def publish_to_zenodo(
    *,
    api_base: str,
    token: str,
    metadata: dict[str, Any],
    bundle_path: Path,
) -> dict[str, Any]:
    deposition = http_json("POST", f"{api_base}/deposit/depositions", token=token, payload={})
    deposition_id = deposition["id"]
    upload_file(deposition["links"]["bucket"], bundle_path, token=token)
    http_json(
        "PUT",
        f"{api_base}/deposit/depositions/{deposition_id}",
        token=token,
        payload={"metadata": metadata},
    )
    published = http_json(
        "POST",
        f"{api_base}/deposit/depositions/{deposition_id}/actions/publish",
        token=token,
        payload={},
    )
    return {
        "status": "published",
        "deposition_id": published["id"],
        "doi": published.get("doi"),
        "doi_url": published.get("doi_url"),
        "record_id": published.get("record_id"),
    }


def publish_to_orcid(
    *,
    api_base: str,
    token: str,
    orcid_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    req = request.Request(
        f"{api_base}/{orcid_id}/work",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/vnd.orcid+json",
            "Accept": "application/vnd.orcid+json",
        },
        method="POST",
    )
    with request.urlopen(req) as response:
        location = response.headers.get("Location", "")
        body = response.read().decode("utf-8").strip()
    return {
        "status": "published",
        "location": location,
        "response": body,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default="v1.0.0", help="Git tag associated with the release bundle.")
    parser.add_argument(
        "--bundle-output",
        default=None,
        help="Optional output path for the zipped release bundle. Defaults to tmp/release-bundle-<tag>.zip.",
    )
    parser.add_argument("--publish", action="store_true", help="Perform live Zenodo and ORCID writes.")
    parser.add_argument("--skip-zenodo", action="store_true", help="Skip Zenodo publication entirely.")
    parser.add_argument("--skip-orcid", action="store_true", help="Skip ORCID publication entirely.")
    parser.add_argument("--zenodo-sandbox", action="store_true", help="Use the Zenodo sandbox API.")
    parser.add_argument("--orcid-sandbox", action="store_true", help="Use the ORCID sandbox API.")
    args = parser.parse_args()

    root = repo_root()
    metadata = load_project_metadata(root)
    bundle_output = (
        Path(args.bundle_output)
        if args.bundle_output
        else root / "tmp" / f"release-bundle-{args.tag.replace('/', '-')}.zip"
    )
    bundle_path = build_release_bundle(root, bundle_output)

    result: dict[str, Any] = {
        "tag": args.tag,
        "version": metadata.version,
        "bundle_path": str(bundle_path),
        "bundle_bytes": bundle_path.stat().st_size,
        "publish": args.publish,
        "zenodo": {"status": "skipped"},
        "orcid": {"status": "skipped"},
    }

    zenodo_metadata = load_zenodo_metadata(root)
    zenodo_metadata["version"] = metadata.version
    zenodo_metadata["publication_date"] = datetime.now(timezone.utc).date().isoformat()

    zenodo_token = os.environ.get("ZENODO_TOKEN", "")
    orcid_token = os.environ.get("ORCID_ACCESS_TOKEN", "")
    orcid_id = os.environ.get("ORCID_ID", "")

    doi = os.environ.get("PUBLICATION_DOI", "")
    doi_url = f"https://doi.org/{doi}" if doi else ""

    if args.skip_zenodo:
        result["zenodo"] = {"status": "skipped", "reason": "Requested by flag"}
    elif not zenodo_token:
        result["zenodo"] = {"status": "skipped", "reason": "ZENODO_TOKEN is not set"}
    elif not args.publish:
        result["zenodo"] = {
            "status": "dry-run",
            "api_base": ZENODO_SANDBOX_API if args.zenodo_sandbox else ZENODO_API,
            "metadata": zenodo_metadata,
        }
    else:
        result["zenodo"] = publish_to_zenodo(
            api_base=ZENODO_SANDBOX_API if args.zenodo_sandbox else ZENODO_API,
            token=zenodo_token,
            metadata=zenodo_metadata,
            bundle_path=bundle_path,
        )
        doi = str(result["zenodo"].get("doi", "") or doi)
        doi_url = str(result["zenodo"].get("doi_url", "") or doi_url)

    if args.skip_orcid:
        result["orcid"] = {"status": "skipped", "reason": "Requested by flag"}
    elif not orcid_token or not orcid_id:
        result["orcid"] = {"status": "skipped", "reason": "ORCID_ACCESS_TOKEN or ORCID_ID is not set"}
    elif not doi:
        result["orcid"] = {"status": "skipped", "reason": "No DOI available to publish"}
    else:
        work_payload = build_orcid_work_payload(
            title=metadata.title,
            doi=doi,
            doi_url=doi_url or f"https://doi.org/{doi}",
            published_on=date.today(),
            description=metadata.description,
        )
        if not args.publish:
            result["orcid"] = {
                "status": "dry-run",
                "api_base": ORCID_SANDBOX_API if args.orcid_sandbox else ORCID_API,
                "orcid_id": orcid_id,
                "payload": work_payload,
            }
        else:
            result["orcid"] = publish_to_orcid(
                api_base=ORCID_SANDBOX_API if args.orcid_sandbox else ORCID_API,
                token=orcid_token,
                orcid_id=orcid_id,
                payload=work_payload,
            )

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(detail, file=sys.stderr)
        raise
