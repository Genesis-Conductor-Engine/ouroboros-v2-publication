# Ouroboros V2 v1.0.0

This release packages the benchmark as a publication artifact rather than only a source repository.

Included assets:

- publication-ready manuscript PDF built from `paper/main.tex`
- fixed-seed benchmark outputs and plots under `results/`
- explicit falsifiability contract
- Zenodo metadata via `.zenodo.json`
- GitHub Actions workflow for Zenodo and ORCID publication when credentials are configured

Claim surface:

- HITL Spatial converges in `0.00 +- 0.00` post-escape steps across seeds `42..51`
- Chiral p-bit converges in `3.00 +- 0.00` steps
- ER=EPR Hypersphere converges in `0.00 +- 0.00` steps and beats Chiral p-bit on mean time-to-convergence
- Bare SGD does not converge under the repository threshold
