# Ouroboros V2 Publication Benchmark

Reproducible saddle-point escape benchmark for a synthetic 20D Ackley+saddle landscape. The repository packages the full benchmark, fixed-seed outputs, validation checks, and publication assets needed to reproduce or falsify the current claim surface.

## Research Question

Does a PCA-projected Barnes-Hut spatial heuristic outperform isotropic noise when escaping a verified saddle point, and do the two p-bit-inspired solvers outperform or match that baseline on the same deterministic landscape?

## Fixed-Seed Result Snapshot

The committed `results/` directory was generated from seeds `42..51` with the shipped code.

| Method | Converged | Mean steps to convergence | Mean final loss |
| --- | --- | ---: | ---: |
| Bare SGD | 0/10 | n/a | 2.0000 |
| Random Langevin | 10/10 | 3.60 ± 1.07 | 0.6660 |
| HITL Spatial | 10/10 | 0.00 ± 0.00 | -1.0090 |
| Chiral p-bit | 10/10 | 3.00 ± 0.00 | 0.4839 |
| ER=EPR Hypersphere | 10/10 | 0.00 ± 0.00 | -0.3044 |

Validation checks in the committed run all pass:

- Saddle confirmed with both positive and negative eigenvalues.
- PCA variance captured exceeds `0.5`.
- Barnes-Hut repulsion force magnitude is positive.
- `HITL Spatial` converges.
- `Chiral p-bit` converges.
- `ER=EPR Hypersphere` mean TtC is lower than `Chiral p-bit`.
- Locked v8.8 constants match the specified values.

## Repository Layout

- `src/ouroboros_v2_publication/benchmark.py`: benchmark implementation and CLI.
- `tests/test_benchmark.py`: numerical and pipeline assertions.
- `results/`: committed figures, machine-readable summaries, and per-seed measurements.
- `presentation/`: publication deck assets.
- `FALSIFIABILITY.md`: explicit acceptance and rejection criteria.

## Reproduce From Scratch

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
python -m ouroboros_v2_publication.benchmark --output-dir results
```

Or use the bundled helper:

```bash
./scripts/reproduce.sh
```

The benchmark writes:

- `results/benchmark_summary.json`
- `results/per_seed_results.csv`
- `results/mean_loss_curves.csv`
- `results/loss_curves.png`
- `results/mean_ttc.png`
- `results/hessian_eigenspectrum.png`
- `results/pca_repulsion_force.png`

## Falsifiability

This repository is intentionally narrow. The claims should be rejected if the fixed-seed rerun no longer reproduces the validation surface, if `HITL Spatial` or `Chiral p-bit` fails to converge, or if `ER=EPR Hypersphere` no longer beats `Chiral p-bit` on mean steps-to-convergence. The full contract is in [FALSIFIABILITY.md](FALSIFIABILITY.md).

## Publication Notes

- Python requirement: `3.10+`
- Locked device constants are encoded directly in the benchmark and rechecked in tests.
- CI reruns the benchmark and uploads fresh outputs on every push and pull request.
