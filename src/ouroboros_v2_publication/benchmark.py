#!/usr/bin/env python3
"""Ouroboros V2 saddle-point escape benchmark on a 20D Ackley+saddle landscape."""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import matplotlib
matplotlib.use("Agg")
import numpy as np
from matplotlib import pyplot as plt
from sklearn.decomposition import PCA

Array = np.ndarray
METHOD_ORDER = [
    "Bare SGD",
    "Random Langevin",
    "HITL Spatial",
    "Chiral p-bit",
    "ER=EPR Hypersphere",
]

N_DIM = 20
NEIGHBORHOOD_SAMPLES = 300
NEIGHBORHOOD_RADIUS = 0.5
GRADIENT_EPS = 1e-5
HESSIAN_EPS = 1e-4
TRAP_GRAD_EPS = 5e-3
POST_ESCAPE_LR = 0.01
POST_ESCAPE_STEPS = 3000
ESCAPE_SCALE = 0.8
CONVERGENCE_LOSS = 1.0
BARNES_HUT_THETA = 0.5
OCTREE_MAX_LEAF = 1
OCTREE_MAX_DEPTH = 20
OCTREE_SOFTENING = 1e-3
ANNEALING_STEPS = 1000


@dataclass(frozen=True)
class LockedConstants:
    """Locked v8.8 device constants used by the p-bit solvers."""

    j_ij_mean: float = 0.389
    entropy_seed: float = 0.05028
    flip_bias: float = 0.497
    delta_v_ev: float = 0.05028
    nu_hz: float = 1.0e12
    tau_device_s: float = 5.23e-12
    temperature_k: float = 300.0
    kb_ev_per_k: float = 8.617333262145e-5

    def validate(self) -> bool:
        return (
            math.isclose(self.j_ij_mean, 0.389, rel_tol=0.0, abs_tol=1e-12)
            and math.isclose(self.entropy_seed, 0.05028, rel_tol=0.0, abs_tol=1e-12)
            and math.isclose(self.flip_bias, 0.497, rel_tol=0.0, abs_tol=1e-12)
            and math.isclose(self.delta_v_ev, 0.05028, rel_tol=0.0, abs_tol=1e-12)
            and math.isclose(self.nu_hz, 1.0e12, rel_tol=0.0, abs_tol=1e-6)
            and math.isclose(self.tau_device_s, 5.23e-12, rel_tol=0.0, abs_tol=1e-15)
            and math.isclose(self.temperature_k, 300.0, rel_tol=0.0, abs_tol=1e-12)
        )


LOCKED_CONSTANTS = LockedConstants()


@dataclass(frozen=True)
class LandscapeConfig:
    """Synthetic landscape hyperparameters."""

    n_dim: int = N_DIM
    ackley_a: float = 20.0
    ackley_b: float = 0.2
    ackley_c: float = 2.0 * math.pi
    # The smoothed radius keeps the injected origin saddle differentiable enough for
    # a stable Hessian test; the rest of the Ackley structure remains unchanged.
    ackley_radius_smoothing: float = 0.05
    saddle_scale: float = 12.0
    saddle_window_beta: float = 1.0
    loss_shift: float = 2.0


LANDSCAPE_CONFIG = LandscapeConfig()


@dataclass
class SGDTrace:
    theta: Array
    steps: int
    loss_history: list[float]
    grad_norm: float
    trapped: bool


@dataclass
class EscapeResult:
    vector_nd: Array
    vector_3d: Array | None
    metadata: dict[str, float | str]


@dataclass
class MethodOutcome:
    method: str
    seed: int
    converged: bool
    steps: int
    final_loss: float
    wall_time_ms: float
    loss_history: list[float]
    perturbation_norm: float


@dataclass
class BenchmarkContext:
    seed: int
    trapped_theta: Array
    trapped_trace: SGDTrace
    eigvals: Array
    eigvecs: Array
    pca: PCA
    pca_projection: Array
    pca_query: Array
    pca_variance_ratio: Array
    sampled_points: Array
    sampled_losses: Array
    sampled_masses: Array
    barnes_hut_force: Array
    router_choice: str


@dataclass
class BenchmarkBundle:
    contexts: list[BenchmarkContext] = field(default_factory=list)
    outcomes: dict[str, list[MethodOutcome]] = field(default_factory=dict)
    validations: list[tuple[str, bool]] = field(default_factory=list)


def ackley(theta: Array, config: LandscapeConfig = LANDSCAPE_CONFIG) -> float:
    """Smoothed Ackley in N dimensions with the standard coefficients."""

    theta = np.asarray(theta, dtype=float)
    mean_sq = np.mean(theta * theta)
    radius = math.sqrt(mean_sq + config.ackley_radius_smoothing**2) - config.ackley_radius_smoothing
    cosine_mean = np.mean(np.cos(config.ackley_c * theta))
    return (
        -config.ackley_a * math.exp(-config.ackley_b * radius)
        - math.exp(cosine_mean)
        + config.ackley_a
        + math.e
    )


def _saddle_quadratic(theta: Array, config: LandscapeConfig = LANDSCAPE_CONFIG) -> tuple[float, Array]:
    theta = np.asarray(theta, dtype=float)
    sign = np.ones(config.n_dim, dtype=float)
    sign[config.n_dim // 2 :] = -1.0
    q = float(np.dot(sign * theta, theta))
    return q, sign


def synthetic_loss(theta: Array, config: LandscapeConfig = LANDSCAPE_CONFIG) -> float:
    """Ackley plus a Gaussian-windowed indefinite quadratic centered at the origin."""

    theta = np.asarray(theta, dtype=float)
    q, _ = _saddle_quadratic(theta, config)
    window = math.exp(-config.saddle_window_beta * float(np.dot(theta, theta)))
    return config.loss_shift + ackley(theta, config) + config.saddle_scale * window * q


def gradient_fd(
    loss_fn: Callable[[Array], float],
    theta: Array,
    eps: float = GRADIENT_EPS,
) -> Array:
    theta = np.asarray(theta, dtype=float)
    grad = np.zeros_like(theta)
    for idx in range(theta.size):
        direction = np.zeros_like(theta)
        direction[idx] = 1.0
        grad[idx] = (loss_fn(theta + eps * direction) - loss_fn(theta - eps * direction)) / (2.0 * eps)
    return grad


def hessian_fd(
    loss_fn: Callable[[Array], float],
    theta: Array,
    eps: float = HESSIAN_EPS,
) -> Array:
    theta = np.asarray(theta, dtype=float)
    n_dim = theta.size
    hessian = np.zeros((n_dim, n_dim), dtype=float)
    base = loss_fn(theta)
    for i in range(n_dim):
        ei = np.zeros(n_dim, dtype=float)
        ei[i] = 1.0
        hessian[i, i] = (loss_fn(theta + eps * ei) - 2.0 * base + loss_fn(theta - eps * ei)) / (eps**2)
        for j in range(i + 1, n_dim):
            ej = np.zeros(n_dim, dtype=float)
            ej[j] = 1.0
            h_ij = (
                loss_fn(theta + eps * ei + eps * ej)
                - loss_fn(theta + eps * ei - eps * ej)
                - loss_fn(theta - eps * ei + eps * ej)
                + loss_fn(theta - eps * ei - eps * ej)
            ) / (4.0 * eps**2)
            hessian[i, j] = hessian[j, i] = h_ij
    return hessian


def exact_gradient(theta: Array, config: LandscapeConfig = LANDSCAPE_CONFIG) -> Array:
    theta = np.asarray(theta, dtype=float)
    n_dim = theta.size
    mean_sq = np.mean(theta * theta)
    q_smooth = math.sqrt(mean_sq + config.ackley_radius_smoothing**2)
    radius = q_smooth - config.ackley_radius_smoothing
    exp_radius = math.exp(-config.ackley_b * radius)
    ackley_scale = config.ackley_a * config.ackley_b * exp_radius / (n_dim * q_smooth)
    grad_radius = ackley_scale * theta

    cosine = np.cos(config.ackley_c * theta)
    sine = np.sin(config.ackley_c * theta)
    exp_cosine = math.exp(float(np.mean(cosine)))
    grad_cosine = exp_cosine * (config.ackley_c / n_dim) * sine

    q, sign = _saddle_quadratic(theta, config)
    window = math.exp(-config.saddle_window_beta * float(np.dot(theta, theta)))
    grad_saddle = 2.0 * config.saddle_scale * window * (sign * theta - config.saddle_window_beta * q * theta)
    return grad_radius + grad_cosine + grad_saddle


def exact_hessian(theta: Array, config: LandscapeConfig = LANDSCAPE_CONFIG) -> Array:
    theta = np.asarray(theta, dtype=float)
    n_dim = theta.size
    identity = np.eye(n_dim, dtype=float)
    mean_sq = np.mean(theta * theta)
    q_smooth = math.sqrt(mean_sq + config.ackley_radius_smoothing**2)
    radius = q_smooth - config.ackley_radius_smoothing
    exp_radius = math.exp(-config.ackley_b * radius)
    scale = config.ackley_a * config.ackley_b * exp_radius / (n_dim * q_smooth)
    hessian_radius = scale * identity - (
        scale * (config.ackley_b + 1.0 / q_smooth) / (n_dim * q_smooth)
    ) * np.outer(theta, theta)

    cosine = np.cos(config.ackley_c * theta)
    sine = np.sin(config.ackley_c * theta)
    exp_cosine = math.exp(float(np.mean(cosine)))
    trig_gradient = (config.ackley_c / n_dim) * sine
    trig_diag = (config.ackley_c**2 / n_dim) * cosine
    hessian_cosine = exp_cosine * (np.diag(trig_diag) - np.outer(trig_gradient, trig_gradient))

    q, sign = _saddle_quadratic(theta, config)
    sign_matrix = np.diag(sign)
    window = math.exp(-config.saddle_window_beta * float(np.dot(theta, theta)))
    beta = config.saddle_window_beta
    hessian_saddle = config.saddle_scale * window * (
        2.0 * sign_matrix
        + q * (4.0 * beta**2 * np.outer(theta, theta) - 2.0 * beta * identity)
        - 4.0 * beta * np.outer(theta, sign * theta)
        - 4.0 * beta * np.outer(sign * theta, theta)
    )
    return hessian_radius + hessian_cosine + hessian_saddle


def sgd_with_trap_detection(
    loss_fn: Callable[[Array], float],
    grad_fn: Callable[[Array], Array],
    theta0: Array,
    lr: float = POST_ESCAPE_LR,
    grad_eps: float = TRAP_GRAD_EPS,
    max_steps: int = 500,
) -> SGDTrace:
    theta = np.asarray(theta0, dtype=float).copy()
    loss_history = [float(loss_fn(theta))]
    grad = grad_fn(theta)
    grad_norm = float(np.linalg.norm(grad))
    if grad_norm < grad_eps:
        return SGDTrace(theta=theta, steps=0, loss_history=loss_history, grad_norm=grad_norm, trapped=True)

    for step in range(1, max_steps + 1):
        theta = theta - lr * grad
        loss_history.append(float(loss_fn(theta)))
        grad = grad_fn(theta)
        grad_norm = float(np.linalg.norm(grad))
        if grad_norm < grad_eps:
            return SGDTrace(theta=theta, steps=step, loss_history=loss_history, grad_norm=grad_norm, trapped=True)
    return SGDTrace(theta=theta, steps=max_steps, loss_history=loss_history, grad_norm=grad_norm, trapped=False)


def verify_saddle_geometry(hessian: Array, tol: float = 1e-8) -> tuple[bool, Array, Array]:
    eigvals, eigvecs = np.linalg.eigh(hessian)
    has_positive = bool(np.any(eigvals > tol))
    has_negative = bool(np.any(eigvals < -tol))
    return has_positive and has_negative, eigvals, eigvecs


def sample_points_in_ball(
    rng: np.random.Generator,
    center: Array,
    n_samples: int = NEIGHBORHOOD_SAMPLES,
    radius: float = NEIGHBORHOOD_RADIUS,
) -> Array:
    center = np.asarray(center, dtype=float)
    directions = rng.normal(size=(n_samples, center.size))
    norms = np.linalg.norm(directions, axis=1, keepdims=True)
    directions = directions / np.clip(norms, 1e-12, None)
    radii = radius * np.power(rng.random(n_samples), 1.0 / center.size)
    return center + directions * radii[:, None]


def sample_hessian_aligned_points_in_ball(
    rng: np.random.Generator,
    center: Array,
    eigvecs: Array,
    n_samples: int = NEIGHBORHOOD_SAMPLES,
    radius: float = NEIGHBORHOOD_RADIUS,
) -> Array:
    center = np.asarray(center, dtype=float)
    dominant = eigvecs[:, :3]
    residual = eigvecs[:, 3:]
    dominant_coeffs = rng.normal(scale=np.array([1.0, 0.8, 0.65]), size=(n_samples, 3))
    if residual.shape[1]:
        residual_coeffs = rng.normal(scale=0.12, size=(n_samples, residual.shape[1]))
        raw_offsets = dominant_coeffs @ dominant.T + residual_coeffs @ residual.T
    else:
        raw_offsets = dominant_coeffs @ dominant.T

    norms = np.linalg.norm(raw_offsets, axis=1, keepdims=True)
    raw_offsets = raw_offsets / np.clip(norms, 1e-12, None)
    radii = radius * np.power(rng.random(n_samples), 1.0 / center.size)
    return center + raw_offsets * radii[:, None]


def local_neighborhood_sampling(
    theta_star: Array,
    rng: np.random.Generator,
    loss_fn: Callable[[Array], float] = synthetic_loss,
    hessian_fn: Callable[[Array], Array] = exact_hessian,
    n_samples: int = NEIGHBORHOOD_SAMPLES,
    radius: float = NEIGHBORHOOD_RADIUS,
) -> tuple[Array, Array, Array]:
    local_eigvals, local_eigvecs = np.linalg.eigh(hessian_fn(theta_star))
    negative_indices = np.flatnonzero(local_eigvals < 0.0)
    if negative_indices.size >= 3:
        negative_order = negative_indices[np.argsort(np.abs(local_eigvals[negative_indices]))[::-1]]
        remaining = [idx for idx in range(local_eigvals.size) if idx not in set(negative_order.tolist())]
        order = np.array(list(negative_order[:3]) + remaining, dtype=int)
    else:
        order = np.argsort(np.abs(local_eigvals))[::-1]
    aligned_eigvecs = local_eigvecs[:, order]
    sampled_points = sample_hessian_aligned_points_in_ball(
        rng,
        theta_star,
        aligned_eigvecs,
        n_samples=n_samples,
        radius=radius,
    )
    losses = np.array([loss_fn(point) for point in sampled_points], dtype=float)
    masses = np.zeros(n_samples, dtype=float)
    for idx, point in enumerate(sampled_points):
        eigvals = np.linalg.eigvalsh(hessian_fn(point))
        negative = eigvals[eigvals < 0.0]
        lambda_neg = float(abs(np.min(negative))) if negative.size else 0.0
        masses[idx] = max(losses[idx], 0.0) * lambda_neg
    return sampled_points, losses, masses


@dataclass
class OctreeNode:
    center: Array
    half_size: float
    depth: int
    max_leaf: int
    max_depth: int
    point: Array | None = None
    point_mass: float = 0.0
    total_mass: float = 0.0
    center_of_mass: Array = field(default_factory=lambda: np.zeros(3, dtype=float))
    children: list["OctreeNode | None"] = field(default_factory=lambda: [None] * 8)

    @property
    def is_leaf(self) -> bool:
        return all(child is None for child in self.children)

    def _child_index(self, point: Array) -> int:
        index = 0
        if point[0] >= self.center[0]:
            index |= 1
        if point[1] >= self.center[1]:
            index |= 2
        if point[2] >= self.center[2]:
            index |= 4
        return index

    def _make_child(self, index: int) -> "OctreeNode":
        offset = np.array(
            [
                0.5 if index & 1 else -0.5,
                0.5 if index & 2 else -0.5,
                0.5 if index & 4 else -0.5,
            ],
            dtype=float,
        )
        child_center = self.center + offset * self.half_size
        child = OctreeNode(
            center=child_center,
            half_size=self.half_size / 2.0,
            depth=self.depth + 1,
            max_leaf=self.max_leaf,
            max_depth=self.max_depth,
        )
        self.children[index] = child
        return child

    def _update_mass(self, point: Array, mass: float) -> None:
        previous_mass = self.total_mass
        self.total_mass += mass
        if self.total_mass <= 0.0:
            self.center_of_mass = np.zeros(3, dtype=float)
            return
        if previous_mass <= 0.0:
            self.center_of_mass = point.copy()
            return
        self.center_of_mass = (self.center_of_mass * previous_mass + point * mass) / self.total_mass

    def insert(self, point: Array, mass: float) -> None:
        self._update_mass(point, mass)
        if self.point is None and self.is_leaf:
            self.point = point.copy()
            self.point_mass = mass
            return

        if self.depth >= self.max_depth:
            return

        if self.is_leaf and self.point is not None:
            existing_point = self.point.copy()
            existing_mass = self.point_mass
            self.point = None
            self.point_mass = 0.0
            existing_index = self._child_index(existing_point)
            existing_child = self.children[existing_index] or self._make_child(existing_index)
            existing_child.insert(existing_point, existing_mass)

        child_index = self._child_index(point)
        child = self.children[child_index] or self._make_child(child_index)
        child.insert(point, mass)


def build_octree(
    points: Array,
    masses: Array,
    query_point: Array,
    max_leaf: int = OCTREE_MAX_LEAF,
    max_depth: int = OCTREE_MAX_DEPTH,
) -> OctreeNode:
    all_points = np.vstack([points, np.asarray(query_point, dtype=float)[None, :]])
    lower = np.min(all_points, axis=0)
    upper = np.max(all_points, axis=0)
    center = 0.5 * (lower + upper)
    half_size = float(max(np.max(upper - lower) / 2.0, 1e-3))
    root = OctreeNode(center=center, half_size=half_size, depth=0, max_leaf=max_leaf, max_depth=max_depth)
    for point, mass in zip(points, masses, strict=True):
        if mass > 0.0:
            root.insert(np.asarray(point, dtype=float), float(mass))
    return root


def barnes_hut_force(
    node: OctreeNode | None,
    query_point: Array,
    theta: float = BARNES_HUT_THETA,
    softening: float = OCTREE_SOFTENING,
) -> Array:
    if node is None or node.total_mass <= 0.0:
        return np.zeros(3, dtype=float)

    query_point = np.asarray(query_point, dtype=float)
    delta = node.center_of_mass - query_point
    distance_sq = float(np.dot(delta, delta) + softening**2)
    distance = math.sqrt(distance_sq)
    node_size = 2.0 * node.half_size

    if node.is_leaf:
        if node.point is not None and np.linalg.norm(node.point - query_point) < 1e-12:
            return np.zeros(3, dtype=float)
        return node.total_mass * delta / (distance_sq * distance)

    if node_size / max(distance, 1e-12) < theta:
        return node.total_mass * delta / (distance_sq * distance)

    force = np.zeros(3, dtype=float)
    for child in node.children:
        force += barnes_hut_force(child, query_point, theta=theta, softening=softening)
    return force


def fit_pca_projection(points: Array, theta_star: Array) -> tuple[PCA, Array, Array, Array]:
    pca = PCA(n_components=3, svd_solver="full")
    projected = pca.fit_transform(points)
    theta_star_proj = pca.transform(np.asarray(theta_star, dtype=float)[None, :])[0]
    return pca, projected, theta_star_proj, pca.explained_variance_ratio_


def simulated_human_spatial_agent(
    force_3d: Array,
    rng: np.random.Generator,
    step_scale: float = 1.0,
) -> Array:
    magnitude = float(np.linalg.norm(force_3d))
    if magnitude < 1e-12:
        fallback = rng.normal(size=3)
        return step_scale * fallback / np.linalg.norm(fallback)
    return -step_scale * np.asarray(force_3d, dtype=float) / magnitude


def reverse_project_escape_vector(pca: PCA, vector_3d: Array) -> Array:
    vector_3d = np.asarray(vector_3d, dtype=float)
    return pca.components_[:3].T @ vector_3d


def normalize_to_scale(vector: Array, scale: float, rng: np.random.Generator) -> Array:
    vector = np.asarray(vector, dtype=float)
    norm = float(np.linalg.norm(vector))
    if norm < 1e-12:
        fallback = rng.normal(size=vector.size)
        return scale * fallback / np.linalg.norm(fallback)
    return scale * vector / norm


def kramers_flip_probability(constants: LockedConstants = LOCKED_CONSTANTS) -> float:
    exponent = -constants.delta_v_ev / (constants.kb_ev_per_k * constants.temperature_k)
    rate = constants.nu_hz * math.exp(exponent)
    return 1.0 - math.exp(-rate * constants.tau_device_s)


def compute_ising_setup(
    eigvals: Array,
    constants: LockedConstants = LOCKED_CONSTANTS,
    er_bridges: bool = False,
) -> tuple[Array, Array]:
    eigvals = np.asarray(eigvals, dtype=float)
    max_abs = float(np.max(np.abs(eigvals)))
    if max_abs < 1e-12:
        return np.zeros((eigvals.size, eigvals.size), dtype=float), np.zeros(eigvals.size, dtype=float)

    diffs = np.abs(eigvals[:, None] - eigvals[None, :]) / max_abs
    couplings = constants.j_ij_mean * diffs
    np.fill_diagonal(couplings, 0.0)

    negative_mask = eigvals < 0.0
    field = np.where(
        negative_mask,
        constants.flip_bias * np.abs(eigvals) / max_abs,
        -0.25 * constants.flip_bias * np.abs(eigvals) / max_abs,
    )

    if er_bridges:
        negative_indices = np.flatnonzero(negative_mask)
        for i in negative_indices:
            for j in negative_indices:
                if i >= j:
                    continue
                bridge = constants.j_ij_mean * (abs(eigvals[i]) + abs(eigvals[j])) / (2.0 * max_abs)
                couplings[i, j] += bridge
                couplings[j, i] += bridge
    return couplings, field


def run_ising_annealing(
    rng: np.random.Generator,
    couplings: Array,
    field: Array,
    steps: int = ANNEALING_STEPS,
    temp_start: float = 1.0,
    temp_end: float = 0.2,
    base_flip_probability: float | None = None,
) -> Array:
    n_dim = field.size
    spins = rng.choice(np.array([-1, 1], dtype=int), size=n_dim).astype(float)
    flip_prob = kramers_flip_probability() if base_flip_probability is None else base_flip_probability
    for step in range(steps):
        temperature = temp_start + (temp_end - temp_start) * (step / max(steps - 1, 1))
        index = int(rng.integers(0, n_dim))
        local_field = float(np.dot(couplings[index], spins) + field[index])
        delta_energy = 2.0 * spins[index] * local_field
        acceptance = flip_prob if delta_energy <= 0.0 else flip_prob * math.exp(-delta_energy / max(temperature, 1e-6))
        if rng.random() < min(1.0, acceptance):
            spins[index] *= -1.0
    return spins


def spins_to_escape_vector(
    spins: Array,
    eigvals: Array,
    eigvecs: Array,
    negative_amplification: float,
    positive_scale: float,
    hypersphere: bool = False,
) -> Array:
    eigvals = np.asarray(eigvals, dtype=float)
    spins = np.asarray(spins, dtype=float)
    max_abs = float(np.max(np.abs(eigvals)))
    if max_abs < 1e-12:
        return eigvecs[:, np.argmin(eigvals)].copy()

    weights = np.where(
        eigvals < 0.0,
        negative_amplification * np.abs(eigvals) / max_abs,
        positive_scale * np.abs(eigvals) / max_abs,
    )
    direction = eigvecs @ (spins * weights)
    if np.linalg.norm(direction) < 1e-12:
        direction = eigvecs[:, np.argmin(eigvals)].copy()
    if hypersphere:
        direction = direction / np.linalg.norm(direction)
    return direction


def chiral_pbit_annealing_escape(
    rng: np.random.Generator,
    eigvals: Array,
    eigvecs: Array,
    constants: LockedConstants = LOCKED_CONSTANTS,
) -> Array:
    couplings, field = compute_ising_setup(eigvals, constants=constants, er_bridges=False)
    spins = run_ising_annealing(rng, couplings, field, steps=ANNEALING_STEPS)
    return spins_to_escape_vector(
        spins,
        eigvals,
        eigvecs,
        negative_amplification=1.4,
        positive_scale=0.5,
        hypersphere=False,
    )


def er_epr_hypersphere_escape(
    rng: np.random.Generator,
    eigvals: Array,
    eigvecs: Array,
    constants: LockedConstants = LOCKED_CONSTANTS,
) -> Array:
    couplings, field = compute_ising_setup(eigvals, constants=constants, er_bridges=True)
    spins = run_ising_annealing(rng, couplings, field, steps=ANNEALING_STEPS)
    return spins_to_escape_vector(
        spins,
        eigvals,
        eigvecs,
        negative_amplification=2.8,
        positive_scale=0.15,
        hypersphere=True,
    )


def escape_router(eigvals: Array, manifold_curvature: float) -> str:
    negative = eigvals[eigvals < 0.0]
    if negative.size == 0:
        return "resume_sgd"
    spectral_gap = abs(float(np.min(negative)))
    # The curvature proxy is ambiguous in the spec; PCA-axis concentration is the
    # lowest-risk deterministic proxy because it measures how sharply the local basin
    # bends into a dominant escape corridor.
    if spectral_gap > 0.1:
        return "er_epr" if manifold_curvature > 0.55 else "chiral_pbit"
    return "hitl_spatial"


def run_post_escape_sgd(
    seed: int,
    method: str,
    theta_start: Array,
    loss_fn: Callable[[Array], float] = synthetic_loss,
    grad_fn: Callable[[Array], Array] = exact_gradient,
    lr: float = POST_ESCAPE_LR,
    max_steps: int = POST_ESCAPE_STEPS,
    convergence_loss: float = CONVERGENCE_LOSS,
) -> MethodOutcome:
    theta = np.asarray(theta_start, dtype=float).copy()
    loss_history = [float(loss_fn(theta))]
    start_time = time.perf_counter()
    if loss_history[-1] < convergence_loss:
        wall_time_ms = (time.perf_counter() - start_time) * 1000.0
        return MethodOutcome(
            method=method,
            seed=seed,
            converged=True,
            steps=0,
            final_loss=loss_history[-1],
            wall_time_ms=wall_time_ms,
            loss_history=loss_history,
            perturbation_norm=float(np.linalg.norm(theta_start)),
        )

    for step in range(1, max_steps + 1):
        theta = theta - lr * grad_fn(theta)
        loss_history.append(float(loss_fn(theta)))
        if loss_history[-1] < convergence_loss:
            wall_time_ms = (time.perf_counter() - start_time) * 1000.0
            return MethodOutcome(
                method=method,
                seed=seed,
                converged=True,
                steps=step,
                final_loss=loss_history[-1],
                wall_time_ms=wall_time_ms,
                loss_history=loss_history,
                perturbation_norm=float(np.linalg.norm(theta_start)),
            )

    wall_time_ms = (time.perf_counter() - start_time) * 1000.0
    return MethodOutcome(
        method=method,
        seed=seed,
        converged=False,
        steps=max_steps,
        final_loss=loss_history[-1],
        wall_time_ms=wall_time_ms,
        loss_history=loss_history,
        perturbation_norm=float(np.linalg.norm(theta_start)),
    )


def method_perturbations(context: BenchmarkContext, rng: np.random.Generator) -> dict[str, EscapeResult]:
    start = time.perf_counter()
    hitl_3d = simulated_human_spatial_agent(context.barnes_hut_force, rng, step_scale=1.0)
    hitl_nd = normalize_to_scale(reverse_project_escape_vector(context.pca, hitl_3d), ESCAPE_SCALE, rng)
    hitl_ms = (time.perf_counter() - start) * 1000.0

    start = time.perf_counter()
    random_langevin = normalize_to_scale(rng.normal(size=context.trapped_theta.size), np.linalg.norm(hitl_nd), rng)
    random_ms = (time.perf_counter() - start) * 1000.0

    start = time.perf_counter()
    chiral_nd = normalize_to_scale(
        chiral_pbit_annealing_escape(rng, context.eigvals, context.eigvecs),
        ESCAPE_SCALE,
        rng,
    )
    chiral_ms = (time.perf_counter() - start) * 1000.0

    start = time.perf_counter()
    er_epr_nd = normalize_to_scale(
        er_epr_hypersphere_escape(rng, context.eigvals, context.eigvecs),
        ESCAPE_SCALE,
        rng,
    )
    er_ms = (time.perf_counter() - start) * 1000.0

    return {
        "Bare SGD": EscapeResult(
            vector_nd=np.zeros_like(context.trapped_theta),
            vector_3d=None,
            metadata={"strategy": "no_escape", "generation_ms": 0.0},
        ),
        "Random Langevin": EscapeResult(
            vector_nd=random_langevin,
            vector_3d=None,
            metadata={"strategy": "isotropic_noise", "generation_ms": random_ms},
        ),
        "HITL Spatial": EscapeResult(
            vector_nd=hitl_nd,
            vector_3d=hitl_3d,
            metadata={"strategy": "barnes_hut", "generation_ms": hitl_ms},
        ),
        "Chiral p-bit": EscapeResult(
            vector_nd=chiral_nd,
            vector_3d=None,
            metadata={"strategy": "chiral", "generation_ms": chiral_ms},
        ),
        "ER=EPR Hypersphere": EscapeResult(
            vector_nd=er_epr_nd,
            vector_3d=None,
            metadata={"strategy": "er_epr", "generation_ms": er_ms},
        ),
    }


def build_context(seed: int) -> BenchmarkContext:
    rng = np.random.default_rng(seed)
    trapped_trace = sgd_with_trap_detection(
        synthetic_loss,
        exact_gradient,
        np.zeros(N_DIM, dtype=float),
        lr=POST_ESCAPE_LR,
        grad_eps=TRAP_GRAD_EPS,
        max_steps=500,
    )
    trapped_theta = trapped_trace.theta
    hessian = exact_hessian(trapped_theta)
    saddle_confirmed, eigvals, eigvecs = verify_saddle_geometry(hessian)
    if not saddle_confirmed:
        raise RuntimeError("Synthetic landscape failed to produce a saddle at the trapped point.")

    sampled_points, sampled_losses, sampled_masses = local_neighborhood_sampling(trapped_theta, rng)
    pca, projected, pca_query, variance_ratio = fit_pca_projection(sampled_points, trapped_theta)
    octree = build_octree(projected, sampled_masses, pca_query)
    force = barnes_hut_force(octree, pca_query, theta=BARNES_HUT_THETA, softening=OCTREE_SOFTENING)
    router_choice = escape_router(eigvals, float(np.sum(variance_ratio[:1])))

    return BenchmarkContext(
        seed=seed,
        trapped_theta=trapped_theta,
        trapped_trace=trapped_trace,
        eigvals=eigvals,
        eigvecs=eigvecs,
        pca=pca,
        pca_projection=projected,
        pca_query=pca_query,
        pca_variance_ratio=variance_ratio,
        sampled_points=sampled_points,
        sampled_losses=sampled_losses,
        sampled_masses=sampled_masses,
        barnes_hut_force=force,
        router_choice=router_choice,
    )


def run_benchmark(seeds: list[int]) -> BenchmarkBundle:
    bundle = BenchmarkBundle(outcomes={})
    for seed in seeds:
        context = build_context(seed)
        bundle.contexts.append(context)
        rng = np.random.default_rng(seed + 10_000)
        perturbations = method_perturbations(context, rng)
        for method, escape in perturbations.items():
            theta_post = context.trapped_theta + escape.vector_nd
            outcome = run_post_escape_sgd(seed=seed, method=method, theta_start=theta_post)
            outcome.wall_time_ms += float(escape.metadata.get("generation_ms", 0.0))
            bundle.outcomes.setdefault(method, []).append(outcome)

    reference = bundle.contexts[0]
    bundle.validations = [
        ("Saddle confirmed (both +/- eigenvalues)", np.any(reference.eigvals > 0.0) and np.any(reference.eigvals < 0.0)),
        ("PCA variance captured > 0.5", float(np.sum(reference.pca_variance_ratio)) > 0.5),
        ("Barnes-Hut force magnitude > 0", float(np.linalg.norm(reference.barnes_hut_force)) > 0.0),
        ("HITL converges", success_rate(bundle.outcomes["HITL Spatial"]) > 0.0),
        ("Chiral converges", success_rate(bundle.outcomes["Chiral p-bit"]) > 0.0),
        (
            "ER=EPR TtC < Chiral TtC",
            mean_steps(bundle.outcomes["ER=EPR Hypersphere"]) < mean_steps(bundle.outcomes["Chiral p-bit"]),
        ),
        ("All v8.8 constants match locked values", LOCKED_CONSTANTS.validate()),
    ]
    return bundle


def pad_histories(outcomes: list[MethodOutcome], target_length: int = POST_ESCAPE_STEPS + 1) -> Array:
    padded = np.zeros((len(outcomes), target_length), dtype=float)
    for row, outcome in enumerate(outcomes):
        history = np.asarray(outcome.loss_history, dtype=float)
        if history.size >= target_length:
            padded[row] = history[:target_length]
        else:
            padded[row, : history.size] = history
            padded[row, history.size :] = history[-1]
    return padded


def success_rate(outcomes: list[MethodOutcome]) -> float:
    return float(np.mean([outcome.converged for outcome in outcomes]))


def mean_steps(outcomes: list[MethodOutcome]) -> float:
    effective_steps = [outcome.steps for outcome in outcomes if outcome.converged]
    if not effective_steps:
        return float("inf")
    return float(np.mean(effective_steps))


def std_steps(outcomes: list[MethodOutcome]) -> float:
    effective_steps = [outcome.steps for outcome in outcomes if outcome.converged]
    if len(effective_steps) < 2:
        return 0.0
    return float(np.std(effective_steps, ddof=1))


def mean_final_loss(outcomes: list[MethodOutcome]) -> float:
    return float(np.mean([outcome.final_loss for outcome in outcomes]))


def mean_wall_time(outcomes: list[MethodOutcome]) -> float:
    return float(np.mean([outcome.wall_time_ms for outcome in outcomes]))


def ordered_methods(bundle: BenchmarkBundle) -> list[str]:
    preferred = [method for method in METHOD_ORDER if method in bundle.outcomes]
    remainder = [method for method in bundle.outcomes if method not in METHOD_ORDER]
    return preferred + remainder


def speedup_value(numerator: float, denominator: float) -> float | None:
    if not math.isfinite(numerator) or not math.isfinite(denominator):
        return None
    if denominator == 0.0:
        return None
    return numerator / denominator


def json_number(value: float) -> float | None:
    return float(value) if math.isfinite(value) else None


def format_speedup(numerator: float, denominator: float) -> str:
    if not math.isfinite(numerator):
        return "n/a"
    if denominator == 0.0:
        return "inf"
    if not math.isfinite(denominator):
        return "n/a"
    return f"{numerator / denominator:.2f}"


def print_benchmark_table(bundle: BenchmarkBundle) -> None:
    print("Benchmark Summary")
    print("=" * 88)
    header = f"{'Method':<22} {'Converged':<12} {'Steps':<16} {'Final Loss':<14} {'Wall Time (ms)':<14}"
    print(header)
    print("-" * len(header))
    for method in ordered_methods(bundle):
        outcomes = bundle.outcomes[method]
        converged_count = sum(outcome.converged for outcome in outcomes)
        steps_repr = f"{mean_steps(outcomes):7.2f} ± {std_steps(outcomes):5.2f}" if converged_count else "    n/a"
        print(
            f"{method:<22} "
            f"{converged_count:>2}/{len(outcomes):<9} "
            f"{steps_repr:<16} "
            f"{mean_final_loss(outcomes):<14.4f} "
            f"{mean_wall_time(outcomes):<14.2f}"
        )

    random_mean = mean_steps(bundle.outcomes["Random Langevin"])
    hitl_mean = mean_steps(bundle.outcomes["HITL Spatial"])
    chiral_mean = mean_steps(bundle.outcomes["Chiral p-bit"])
    er_mean = mean_steps(bundle.outcomes["ER=EPR Hypersphere"])

    print("\nAnalysis")
    print("-" * 88)
    print(f"HITL Spatial vs Random Langevin TtC speedup: {format_speedup(random_mean, hitl_mean)}x")
    print(f"Chiral p-bit vs Random Langevin TtC speedup: {format_speedup(random_mean, chiral_mean)}x")
    print(f"ER=EPR vs Chiral p-bit TtC speedup: {format_speedup(chiral_mean, er_mean)}x")

    print("\nValidation Checks")
    print("-" * 88)
    for label, passed in bundle.validations:
        print(f"[{'PASS' if passed else 'FAIL'}] {label}")


def plot_loss_curves(bundle: BenchmarkBundle, output_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(10, 6))
    steps = np.arange(POST_ESCAPE_STEPS + 1)
    for method, outcomes in bundle.outcomes.items():
        padded = pad_histories(outcomes)
        mean_curve = padded.mean(axis=0)
        std_curve = padded.std(axis=0)
        ax.plot(steps, mean_curve, linewidth=2.0, label=method)
        ax.fill_between(steps, mean_curve - std_curve, mean_curve + std_curve, alpha=0.18)
    ax.set_title("Post-Escape SGD Loss Curves")
    ax.set_xlabel("Post-escape step")
    ax.set_ylabel("Loss")
    ax.grid(alpha=0.25)
    ax.legend(frameon=False)
    fig.tight_layout()
    path = output_dir / "loss_curves.png"
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


def plot_mean_ttc(bundle: BenchmarkBundle, output_dir: Path) -> Path:
    methods = list(bundle.outcomes.keys())
    means = [mean_steps(bundle.outcomes[method]) for method in methods]
    stds = [std_steps(bundle.outcomes[method]) for method in methods]
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar(methods, means, yerr=stds, capsize=6, color=["#888", "#7fb3d5", "#f5b041", "#58d68d", "#af7ac5"])
    ax.set_title("Mean Steps-to-Convergence by Method")
    ax.set_ylabel("Steps to convergence")
    ax.tick_params(axis="x", rotation=15)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    path = output_dir / "mean_ttc.png"
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


def plot_eigenspectrum(context: BenchmarkContext, output_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.axhline(0.0, color="black", linewidth=1.0, alpha=0.7)
    ax.plot(np.arange(context.eigvals.size), context.eigvals, marker="o", linewidth=1.75, color="#2e86de")
    ax.set_title("Hessian Eigenvalue Spectrum at the Trapped Point")
    ax.set_xlabel("Eigenvalue index")
    ax.set_ylabel("Eigenvalue")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    path = output_dir / "hessian_eigenspectrum.png"
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


def plot_pca_force(context: BenchmarkContext, output_dir: Path) -> Path:
    fig = plt.figure(figsize=(9, 7))
    ax = fig.add_subplot(111, projection="3d")
    scatter = ax.scatter(
        context.pca_projection[:, 0],
        context.pca_projection[:, 1],
        context.pca_projection[:, 2],
        c=context.sampled_losses,
        cmap="viridis",
        s=22,
        alpha=0.8,
    )
    force = context.barnes_hut_force
    ax.quiver(
        context.pca_query[0],
        context.pca_query[1],
        context.pca_query[2],
        force[0],
        force[1],
        force[2],
        color="crimson",
        linewidth=2.5,
        arrow_length_ratio=0.15,
    )
    ax.set_title("PCA-Projected Neighborhood with Barnes-Hut Force")
    ax.set_xlabel("PC1")
    ax.set_ylabel("PC2")
    ax.set_zlabel("PC3")
    fig.colorbar(scatter, ax=ax, shrink=0.7, pad=0.1, label="Loss")
    fig.tight_layout()
    path = output_dir / "pca_repulsion_force.png"
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


def generate_plots(bundle: BenchmarkBundle, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    reference = bundle.contexts[0]
    return [
        plot_loss_curves(bundle, output_dir),
        plot_mean_ttc(bundle, output_dir),
        plot_eigenspectrum(reference, output_dir),
        plot_pca_force(reference, output_dir),
    ]


def summary_payload(bundle: BenchmarkBundle) -> dict[str, object]:
    reference = bundle.contexts[0]
    random_mean = mean_steps(bundle.outcomes["Random Langevin"])
    hitl_mean = mean_steps(bundle.outcomes["HITL Spatial"])
    chiral_mean = mean_steps(bundle.outcomes["Chiral p-bit"])
    er_mean = mean_steps(bundle.outcomes["ER=EPR Hypersphere"])
    negative = reference.eigvals[reference.eigvals < 0.0]
    spectral_gap = abs(float(np.min(negative))) if negative.size else 0.0
    methods = []
    for method in ordered_methods(bundle):
        outcomes = bundle.outcomes[method]
        methods.append(
            {
                "method": method,
                "runs": int(len(outcomes)),
                "converged_runs": int(sum(outcome.converged for outcome in outcomes)),
                "mean_steps": json_number(mean_steps(outcomes)),
                "std_steps": json_number(std_steps(outcomes)),
                "mean_final_loss": json_number(mean_final_loss(outcomes)),
                "mean_wall_time_ms": json_number(mean_wall_time(outcomes)),
            }
        )
    return {
        "metadata": {
            "n_dim": N_DIM,
            "neighborhood_samples": NEIGHBORHOOD_SAMPLES,
            "neighborhood_radius": NEIGHBORHOOD_RADIUS,
            "gradient_eps": GRADIENT_EPS,
            "hessian_eps": HESSIAN_EPS,
            "escape_scale": ESCAPE_SCALE,
            "post_escape_lr": POST_ESCAPE_LR,
            "post_escape_steps": POST_ESCAPE_STEPS,
            "convergence_loss": CONVERGENCE_LOSS,
        },
        "methods": methods,
        "speedups": {
            "hitl_vs_random_langevin": {
                "display": f"{format_speedup(random_mean, hitl_mean)}x",
                "value": speedup_value(random_mean, hitl_mean),
            },
            "chiral_vs_random_langevin": {
                "display": f"{format_speedup(random_mean, chiral_mean)}x",
                "value": speedup_value(random_mean, chiral_mean),
            },
            "er_epr_vs_chiral": {
                "display": f"{format_speedup(chiral_mean, er_mean)}x",
                "value": speedup_value(chiral_mean, er_mean),
            },
        },
        "validations": [{"label": str(label), "passed": bool(passed)} for label, passed in bundle.validations],
        "reference_context": {
            "seed": reference.seed,
            "router_choice": reference.router_choice,
            "pca_variance_ratio": reference.pca_variance_ratio.tolist(),
            "pca_variance_captured": float(np.sum(reference.pca_variance_ratio)),
            "barnes_hut_force_norm": float(np.linalg.norm(reference.barnes_hut_force)),
            "spectral_gap": spectral_gap,
            "eigvals": reference.eigvals.tolist(),
        },
        "locked_constants": {
            "j_ij_mean": LOCKED_CONSTANTS.j_ij_mean,
            "entropy_seed": LOCKED_CONSTANTS.entropy_seed,
            "flip_bias": LOCKED_CONSTANTS.flip_bias,
            "delta_v_ev": LOCKED_CONSTANTS.delta_v_ev,
            "nu_hz": LOCKED_CONSTANTS.nu_hz,
            "tau_device_s": LOCKED_CONSTANTS.tau_device_s,
            "temperature_k": LOCKED_CONSTANTS.temperature_k,
        },
    }


def write_results_csv(bundle: BenchmarkBundle, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "method",
                "seed",
                "converged",
                "steps",
                "final_loss",
                "wall_time_ms",
                "perturbation_norm",
            ],
        )
        writer.writeheader()
        for method in ordered_methods(bundle):
            for outcome in bundle.outcomes[method]:
                writer.writerow(
                    {
                        "method": outcome.method,
                        "seed": outcome.seed,
                        "converged": int(outcome.converged),
                        "steps": outcome.steps,
                        "final_loss": f"{outcome.final_loss:.10f}",
                        "wall_time_ms": f"{outcome.wall_time_ms:.10f}",
                        "perturbation_norm": f"{outcome.perturbation_norm:.10f}",
                    }
                )
    return output_path


def write_mean_curves_csv(bundle: BenchmarkBundle, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["method", "step", "mean_loss", "std_loss"])
        writer.writeheader()
        for method in ordered_methods(bundle):
            padded = pad_histories(bundle.outcomes[method])
            mean_curve = padded.mean(axis=0)
            std_curve = padded.std(axis=0)
            for step, (mean_loss, std_loss) in enumerate(zip(mean_curve, std_curve, strict=True)):
                writer.writerow(
                    {
                        "method": method,
                        "step": step,
                        "mean_loss": f"{float(mean_loss):.10f}",
                        "std_loss": f"{float(std_loss):.10f}",
                    }
                )
    return output_path


def write_summary_json(bundle: BenchmarkBundle, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = summary_payload(bundle)
    output_path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return output_path


def write_publication_artifacts(bundle: BenchmarkBundle, output_dir: Path) -> list[Path]:
    return [
        write_summary_json(bundle, output_dir / "benchmark_summary.json"),
        write_results_csv(bundle, output_dir / "per_seed_results.csv"),
        write_mean_curves_csv(bundle, output_dir / "mean_loss_curves.csv"),
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Ouroboros V2 escape benchmark.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results"),
        help="Directory where plots will be written.",
    )
    parser.add_argument(
        "--seed-start",
        type=int,
        default=42,
        help="Inclusive first seed for the benchmark.",
    )
    parser.add_argument(
        "--seed-count",
        type=int,
        default=10,
        help="Number of consecutive seeds to benchmark.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    seeds = list(range(args.seed_start, args.seed_start + args.seed_count))
    bundle = run_benchmark(seeds)
    print_benchmark_table(bundle)
    plot_paths = generate_plots(bundle, args.output_dir)
    report_paths = write_publication_artifacts(bundle, args.output_dir)
    print("\nPlots")
    print("-" * 88)
    for path in plot_paths:
        print(path)
    print("\nReports")
    print("-" * 88)
    for path in report_paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
