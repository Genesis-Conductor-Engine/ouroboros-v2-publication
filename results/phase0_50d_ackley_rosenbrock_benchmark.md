# Ouroboros Protocol v2 — Phase 0 Benchmark: Why 3D-PCA Spatial Heuristics Fail in 50D Ackley+Rosenbrock Saddle Traps

**Status:** Published 2026-11-17. Single-run Phase 0 diagnostic — 5 trials, seed 42.
Not a multi-seed validated result.

**Source:** `ouroboros_phase0_telemetry.json`, experiment id
`ouroboros_phase0_1772123429` (Gemini upload 2026-11-15). All numbers below are taken
from that file and checked against it.

**Scope note:** This is a separate Phase 0 diagnostic on a 50D Ackley+Rosenbrock
landscape. It is distinct from this repository's main committed benchmark (20D
Ackley+saddle landscape, seeds 42–51, in `results/benchmark_summary.json`), where
the HITL Spatial variant converges. Do not conflate the two experiments.

## The result

| Method | Mean final loss | Std |
|---|---|---|
| Baseline SGD+Noise | 12.26 | ±2.71 |
| 3D-PCA HITL | 24.34 | ±3.49 |

**Verdict in the telemetry file: `BASELINE_OUTPERFORMS`.** The 3D-PCA human-in-the-loop
variant ends at roughly twice the loss of the baseline. The 3D-PCA intervention makes
it worse, not better. This is a negative result, and that is the point — the value is
the diagnosis (why 3D-PCA fails), not a win claim.

## The diagnostics (why it fails)

| Diagnostic | Value (mean over 5 trials) | Per-trial values |
|---|---|---|
| 3D-PCA variance captured | **15.12%** | 15.30, 14.62, 15.75, 14.99, 14.95 |
| Gradient cosine alignment | **0.0895** | −0.011, 0.088, 0.129, 0.150, 0.091 |
| Negative-curvature Hessian energy | **0.38%** | 0.00, 0.21, 1.70, 0.00, 0.00 |

- 3D PCA captures only ~15.1% of the variance — **84.88%** of the optimization
  geometry is discarded (100 − 15.12; the telemetry file's `root_cause` text says
  84.65%, which does not match its own mean — 84.88% is the arithmetic from the
  file's own numbers).
- The escape vector is nearly orthogonal to the gradient (cosine 0.0895; ideal −1.0
  for descent).
- Only ~0.38% of escape energy enters negative-curvature Hessian directions.

Additional telemetry: escape-vector magnitude 3.08 (3D) vs 5.33 (full ND); mean time
0.43 s (baseline) vs 0.34 s (HITL); 200 iterations each, std 0.0.

## Phase 1 (the fix)

Replace 3D PCA with **bottom-k negative-eigenvalue Hessian eigenvector projection**
(λ_i < 0): project the escape direction onto the eigenvectors of the Hessian with
negative eigenvalues, so the step actually follows directions of negative curvature
instead of the ~15% of variance a 3D projection retains.

## Verification notes and caveats

1. **Numbers match the telemetry file exactly.** Baseline 12.2616 ± 2.7074 →
   "12.26 ± 2.71"; HITL 24.3391 ± 3.4938 → "24.34 ± 3.49"; PCA 15.1191% →
   "15.12%"; gradient 0.08952 → "0.0895"; neg-curvature 0.3807% → "0.38%".
2. **The negative-curvature mean is fragile.** Three of five trials are exactly
   0.00%; the 0.38% mean is driven almost entirely by one trial at 1.70%. Do not
   overstate the precision of "0.38%" — report the per-trial spread alongside it
   (as done above).
3. **Single source, no independent reproduction.** The telemetry file is the only
   source. There is no experiment code, no run log, and no `benchmarks` or
   `diagnostics` top-level entries in the file (both are empty). The numbers are
   internally consistent and the per-trial values are present, but the experiment
   has not been independently reproduced. Label it as a single-run Phase 0
   diagnostic (5 trials, seed 42), not as a multi-seed validated result.
