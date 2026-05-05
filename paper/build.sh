#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PAPER_DIR="${ROOT_DIR}/paper"
OUTPUT_DIR="${PAPER_DIR}/final"
WORK_DIR="${ROOT_DIR}/tmp/paper-build"
TECTONIC_BIN="/Users/Igor/.codex/plugins/cache/openai-bundled/latex-tectonic/0.1.0/bin/tectonic"

mkdir -p "${OUTPUT_DIR}" "${WORK_DIR}"
rm -f "${OUTPUT_DIR}/ouroboros-v2-publication-manuscript.pdf"

(
  cd "${PAPER_DIR}"
  "${TECTONIC_BIN}" --outdir "${WORK_DIR}" main.tex
)

mv "${WORK_DIR}/main.pdf" "${OUTPUT_DIR}/ouroboros-v2-publication-manuscript.pdf"
rm -f "${WORK_DIR}/main.log" "${WORK_DIR}/main.aux"

printf 'Wrote %s\n' "${OUTPUT_DIR}/ouroboros-v2-publication-manuscript.pdf"
