from __future__ import annotations

import math
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from ouroboros_v2_publication.benchmark import (
    ESCAPE_SCALE,
    LOCKED_CONSTANTS,
    N_DIM,
    build_context,
    chiral_pbit_annealing_escape,
    er_epr_hypersphere_escape,
    exact_gradient,
    exact_hessian,
    escape_router,
    gradient_fd,
    hessian_fd,
    kramers_flip_probability,
    local_neighborhood_sampling,
    method_perturbations,
    normalize_to_scale,
    run_post_escape_sgd,
    run_benchmark,
    synthetic_loss,
    verify_saddle_geometry,
    write_publication_artifacts,
)


class OuroborosNumericsTest(unittest.TestCase):
    def test_gradient_fd_matches_exact_gradient(self) -> None:
        theta = np.linspace(-0.35, 0.45, N_DIM)
        grad_exact = exact_gradient(theta)
        grad_numeric = gradient_fd(synthetic_loss, theta)
        np.testing.assert_allclose(grad_numeric, grad_exact, rtol=2e-4, atol=5e-5)

    def test_hessian_fd_matches_exact_hessian(self) -> None:
        theta = np.linspace(-0.2, 0.3, N_DIM)
        hessian_exact = exact_hessian(theta)
        hessian_numeric = hessian_fd(synthetic_loss, theta)
        np.testing.assert_allclose(hessian_numeric, hessian_exact, rtol=2e-3, atol=5e-3)

    def test_locked_constants_and_kramers_probability(self) -> None:
        self.assertTrue(LOCKED_CONSTANTS.validate())
        flip_probability = kramers_flip_probability()
        self.assertGreater(flip_probability, 0.0)
        self.assertLess(flip_probability, 1.0)


class OuroborosPipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.context = build_context(42)

    def test_origin_trap_is_a_verified_saddle(self) -> None:
        is_saddle, eigvals, _ = verify_saddle_geometry(exact_hessian(np.zeros(N_DIM, dtype=float)))
        self.assertTrue(is_saddle)
        self.assertTrue(np.any(eigvals > 0.0))
        self.assertTrue(np.any(eigvals < 0.0))

    def test_local_sampling_produces_meaningful_pca_and_force(self) -> None:
        variance_captured = float(np.sum(self.context.pca_variance_ratio))
        force_magnitude = float(np.linalg.norm(self.context.barnes_hut_force))
        self.assertGreater(variance_captured, 0.5)
        self.assertGreater(force_magnitude, 0.0)

    def test_escape_router_prefers_negative_curvature_solver(self) -> None:
        curvature = float(np.sum(self.context.pca_variance_ratio[:1]))
        route = escape_router(self.context.eigvals, curvature)
        self.assertIn(route, {"chiral_pbit", "er_epr"})

    def test_escape_vectors_are_scaled_and_post_escape_sgd_converges(self) -> None:
        rng = np.random.default_rng(42 + 10_000)
        perturbations = method_perturbations(self.context, rng)
        for method in ("HITL Spatial", "Chiral p-bit", "ER=EPR Hypersphere"):
            perturbation = perturbations[method].vector_nd
            self.assertAlmostEqual(float(np.linalg.norm(perturbation)), ESCAPE_SCALE, places=6)

        hitl_outcome = run_post_escape_sgd(
            seed=42,
            method="HITL Spatial",
            theta_start=self.context.trapped_theta + perturbations["HITL Spatial"].vector_nd,
        )
        self.assertTrue(hitl_outcome.converged)

    def test_er_escape_is_more_aligned_with_negative_subspace_than_chiral(self) -> None:
        rng = np.random.default_rng(1234)
        chiral = normalize_to_scale(
            chiral_pbit_annealing_escape(rng, self.context.eigvals, self.context.eigvecs),
            ESCAPE_SCALE,
            rng,
        )
        er = normalize_to_scale(
            er_epr_hypersphere_escape(rng, self.context.eigvals, self.context.eigvecs),
            ESCAPE_SCALE,
            rng,
        )
        negative_basis = self.context.eigvecs[:, self.context.eigvals < 0.0]
        chiral_alignment = float(np.linalg.norm(negative_basis.T @ chiral))
        er_alignment = float(np.linalg.norm(negative_basis.T @ er))
        self.assertGreaterEqual(er_alignment, chiral_alignment)

    def test_publication_artifacts_are_written_with_expected_claim_surface(self) -> None:
        bundle = run_benchmark([42, 43])
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            paths = write_publication_artifacts(bundle, output_dir)
            self.assertEqual({path.name for path in paths}, {"benchmark_summary.json", "per_seed_results.csv", "mean_loss_curves.csv"})

            summary = json.loads((output_dir / "benchmark_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["metadata"]["n_dim"], N_DIM)
            self.assertGreater(summary["reference_context"]["pca_variance_captured"], 0.5)
            self.assertEqual(len(summary["methods"]), 5)
            self.assertTrue(all(item["passed"] for item in summary["validations"]))


if __name__ == "__main__":
    unittest.main()
