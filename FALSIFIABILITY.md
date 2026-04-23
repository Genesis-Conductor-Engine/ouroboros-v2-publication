# Falsifiability Contract

This repository makes a narrow, testable claim on one synthetic benchmark and one fixed seed set.

## Claim Surface

The publication hypothesis is supported only if all of the following remain true for seeds `42..51` on the shipped 20D Ackley+saddle landscape:

1. The trapped point is a verified saddle with both positive and negative Hessian eigenvalues.
2. The PCA-projected local neighborhood captures more than `0.5` cumulative variance across the first three components.
3. The Barnes-Hut repulsion force at the trapped point has non-zero magnitude.
4. `HITL Spatial` converges under the repository convergence threshold (`loss < 1.0`).
5. `Chiral p-bit` converges under the same threshold.
6. `ER=EPR Hypersphere` achieves a lower mean steps-to-convergence than `Chiral p-bit`.

## What Falsifies the Claim

The repository should be considered falsified if any of the following occur on an unmodified rerun:

- `results/benchmark_summary.json` reports a failed validation check.
- `per_seed_results.csv` shows a non-converged `HITL Spatial` or `Chiral p-bit` run.
- The mean steps ordering reverses so `ER=EPR Hypersphere >= Chiral p-bit`.
- The deterministic fixed-seed rerun cannot be reproduced from a clean Python `3.10+` environment using the stated dependencies.

## How To Reproduce

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
python -m ouroboros_v2_publication.benchmark --output-dir results
```

Compare the regenerated `results/` directory against the committed summary, CSVs, and plots.
