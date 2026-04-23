# Ouroboros V2 Publication Deck Narrative Plan

## Audience

- Research reviewers evaluating reproducibility and falsifiability.
- Technical stakeholders deciding whether the benchmark is publication-ready.

## Objective

Show that the repository ships a narrow but testable saddle-escape benchmark, explain the fixed-seed result ordering, and make the rejection criteria explicit.

## Narrative Arc

1. Open with the benchmark thesis and the strongest fixed-seed result.
2. Explain the deterministic evaluation setup and why the saddle is legitimate.
3. Show the quantitative separation between methods.
4. Make the falsifiability surface concrete.
5. Close on the repository as the publication artifact.

## Slide List

1. Cover: title, scope, and fixed-seed result snapshot.
2. Protocol: landscape design, methods, and convergence rule.
3. Saddle verification: eigenvalue spectrum, PCA compression, Barnes-Hut force.
4. Primary result: mean steps-to-convergence by method.
5. Loss trajectories: why bare SGD is not a meaningful control.
6. Falsifiability: explicit refutation criteria and locked constants.
7. Publication package: repo layout, reviewer workflow, and citation metadata.

## Source Plan

- `results/benchmark_summary.json`
- `results/mean_ttc.png`
- `results/loss_curves.png`
- `results/hessian_eigenspectrum.png`
- `results/pca_repulsion_force.png`
- `FALSIFIABILITY.md`

## Visual System

- Warm paper base with muted green publication accents.
- Serif headlines and clean sans body copy.
- Figure panels sit inside rounded white cards with thin graphite strokes.
- Accent colors encode emphasis only: green for benchmark win states, gold for protocol, coral for risk and rejection criteria.

## Editability Plan

- All titles, subtitles, cards, metric values, and captions are editable PowerPoint text objects.
- Repo figures are inserted as images because they are generated outputs from the benchmark itself.
- Speaker notes carry the narrative framing and source references for each slide.
