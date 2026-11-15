"""Multi-year CVaR campaign optimizer conforming to Lean S10 (Analog.CampaignOpt).

Pure Python stdlib implementation (+ lazy `pyarrow` for `.parquet` I/O), zero
SciPy or NumPy dependency.

Implements the Rockafellar–Uryasev multi-year CVaR linear program (`S10a`, `S10c`,
`S10e`), iterative tail-scenario screening (`S10b`), and an exact two-phase Revised
Simplex solver with Bland's anti-cycling rule that extracts dual multipliers for a
computable `Certificate.subopt_le` suboptimality bound (`S10d`).

Per `ADR-0005` D5: this plans field-day allocations across candidate `(site, month)`
blocks under physical weather/thermal risk and operational constraints. It never
computes a site "analogy similarity score".
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Iterable, Sequence


class InfeasibleCampaignError(ValueError):
    """Raised when the campaign LP constraints admit no feasible allocation."""


def _to_vec(seq: Sequence[float]) -> tuple[float, ...]:
    return tuple(float(x) for x in seq)


def _to_mat(mat: Sequence[Sequence[float]]) -> tuple[tuple[float, ...], ...]:
    return tuple(tuple(float(x) for x in row) for row in mat)


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return math.fsum(x * y for x, y in zip(a, b))


def _dot_q(a: Sequence[Fraction], b: Sequence[Fraction]) -> Fraction:
    return sum((x * y for x, y in zip(a, b)), Fraction(0))


def _fraction_to_float_upper(q: Fraction) -> float:
    """Convert exact `q` to a `float` guaranteed to satisfy `Fraction(f) >= q`."""
    f = float(q)
    if math.isfinite(f) and Fraction(f) < q:
        f = math.nextafter(f, math.inf)
    return f


def _fraction_to_float_lower(q: Fraction) -> float:
    """Convert exact `q` to a `float` guaranteed to satisfy `Fraction(f) <= q`."""
    f = float(q)
    if math.isfinite(f) and Fraction(f) > q:
        f = math.nextafter(f, -math.inf)
    return f


def _solve_linear(M: list[list[float]], rhs: Sequence[float], *, transpose: bool = False) -> list[float]:
    """Solve `M x = rhs` (or `M^T x = rhs`) using Gaussian elimination with partial pivoting."""
    n = len(rhs)
    if n == 0:
        return []
    aug: list[list[float]] = []
    if transpose:
        for i in range(n):
            row = [M[j][i] for j in range(n)]
            row.append(float(rhs[i]))
            aug.append(row)
    else:
        for i in range(n):
            row = list(M[i])
            row.append(float(rhs[i]))
            aug.append(row)

    for col in range(n):
        piv = col
        best = abs(aug[col][col])
        for r in range(col + 1, n):
            v = abs(aug[r][col])
            if v > best:
                best = v
                piv = r
        if best < 1e-13:
            raise ValueError("Singular Simplex basis matrix encountered")
        if piv != col:
            aug[col], aug[piv] = aug[piv], aug[col]

        piv_val = aug[col][col]
        piv_row = aug[col]
        for r in range(col + 1, n):
            factor = aug[r][col] / piv_val
            if factor == 0.0:
                continue
            row_r = aug[r]
            row_r[col] = 0.0
            for c in range(col + 1, n + 1):
                row_r[c] -= factor * piv_row[c]

    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        row_i = aug[i]
        s = row_i[n] - math.fsum(row_i[j] * x[j] for j in range(i + 1, n))
        x[i] = s / row_i[i]
    return x


@dataclass(frozen=True)
class CampaignProblem:
    """Parameters mirroring `Analog.CampaignOpt.CampaignProblem`."""

    candidate_ids: list[str]
    years: list[int]
    loss_matrix: Sequence[Sequence[float]]  # shape (T, m), L[i][j] = year i loss for block j
    alpha: float                            # tail fraction in (0, 1], giving c = 1 / (alpha * T)
    hi: Sequence[float]                     # length m, 0 <= w_j <= hi_j
    cov: Sequence[Sequence[float]]        # shape (k, m), cov @ w >= req
    req: Sequence[float]                    # length k
    cost: Sequence[float]                   # length m, cost @ w <= budget
    budget: float

    def __post_init__(self) -> None:
        loss = _to_mat(self.loss_matrix)
        t_cnt = len(loss)
        if t_cnt < 1:
            raise ValueError("CampaignProblem requires T >= 1 years")
        m_cnt = len(loss[0])
        if m_cnt < 1 or any(len(r) != m_cnt for r in loss):
            raise ValueError("loss_matrix must be rectangular with m >= 1 candidates")

        hi = _to_vec(self.hi)
        cov = _to_mat(self.cov)
        req = _to_vec(self.req)
        cost = _to_vec(self.cost)

        if len(self.candidate_ids) != m_cnt or len(self.years) != t_cnt:
            raise ValueError("candidate_ids/years length mismatch with loss_matrix shape")
        if not (0.0 < float(self.alpha) <= 1.0) or not math.isfinite(self.alpha):
            raise ValueError("alpha must be finite and in (0, 1]")
        if len(hi) != m_cnt or len(cost) != m_cnt or len(cov) != len(req) or any(len(r) != m_cnt for r in cov):
            raise ValueError("Incompatible constraint dimensions in CampaignProblem")

        for name, seq in (("hi", hi), ("req", req), ("cost", cost)):
            if not all(math.isfinite(x) for x in seq):
                raise ValueError(f"{name} contains non-finite values")
        for row in loss:
            if not all(math.isfinite(x) for x in row):
                raise ValueError("loss_matrix contains non-finite values")
        for row in cov:
            if not all(math.isfinite(x) for x in row):
                raise ValueError("cov contains non-finite values")
        if not math.isfinite(self.budget):
            raise ValueError("budget must be finite")
        if any(x < 0.0 for x in hi):
            raise ValueError("Per-candidate upper bounds hi must be non-negative")

        object.__setattr__(self, "loss_matrix", loss)
        object.__setattr__(self, "hi", hi)
        object.__setattr__(self, "cov", cov)
        object.__setattr__(self, "req", req)
        object.__setattr__(self, "cost", cost)
        object.__setattr__(self, "budget", float(self.budget))
        object.__setattr__(self, "alpha", float(self.alpha))

    @property
    def n_candidates(self) -> int:
        return len(self.loss_matrix[0])

    @property
    def n_years(self) -> int:
        return len(self.loss_matrix)

    @property
    def c(self) -> float:
        return 1.0 / (self.alpha * self.n_years)

    @property
    def c_exact(self) -> Fraction:
        return Fraction(1) / (Fraction(self.alpha) * self.n_years)


@dataclass(frozen=True)
class DualCertificate:
    """Audit artifact mirroring `Analog.CampaignOpt.S10d_dual_subopt_certificate`.

    `S10d` is instantiated over the nonnegativity-augmented inequality system
    `G_aug = [G_struct; -I]`, `h_aug = [h_struct; 0]` with multiplier vector
    `lam_full = lam_struct + lam_nn >= 0`, so `dual_residual_linf` bounds
    `||g + G_aug^T lam_full + E^T y||_inf` against the exact CVaR weight
    `c_exact = 1 / (alpha * T)`.

    `certified` is `True` ONLY when every `S10d` feasibility hypothesis holds with
    zero violation in exact rational arithmetic (`primal_max_ineq_violation == 0.0`,
    `primal_max_eq_violation == 0.0`, and `dual_min_multiplier >= 0.0`). When
    floating-point rounding leaves positive tolerance residuals (`> 0.0`), `certified`
    is `False`, `certified_subopt_le` is `None`, and `numerical_subopt_estimate`
    records the uncertified upper-bounded diagnostic
    `objective_rounding_error + comp_gap + M_dual * l1_bound`.
    """

    objective_value: float
    primal_max_ineq_violation: float
    primal_max_eq_violation: float
    dual_min_multiplier: float
    dual_residual_linf: float
    complementarity_gap: float
    l1_radius_bound: float
    certified_subopt_le: float | None
    certified: bool = False
    certification_status: str = "uncertified-numerical-tolerance"
    numerical_subopt_estimate: float = 0.0
    objective_rounding_error: float = 0.0

    def subopt_bound(self, z_minus_zs_l1: float) -> float:
        """Evaluate upper-bounded `S10d` RHS on `objective_value - opt` for `||z - z*||_1`."""
        l1_dev = float(z_minus_zs_l1)
        if not math.isfinite(l1_dev) or l1_dev < 0.0:
            raise ValueError("z_minus_zs_l1 must be finite and >= 0")
        rhs_q = (
            Fraction(self.objective_rounding_error)
            + Fraction(self.complementarity_gap)
            + Fraction(self.dual_residual_linf) * Fraction(l1_dev)
        )
        return _fraction_to_float_upper(rhs_q)


@dataclass(frozen=True)
class CampaignSolution:
    """Verified optimal CVaR campaign day allocation (`S10a`–`S10e`)."""

    weights: dict[str, float]
    var_t: float
    cvar: float
    scenario_losses: dict[int, float]
    tail_excess: dict[int, float]
    expected_cost: float
    achieved_coverage: list[float]
    screened_years: list[int]
    dropped_years: list[int]
    screening_iterations: int
    screening_exact: bool
    certificate: DualCertificate


def _basis_matrix(A: list[list[float]], basis: list[int]) -> list[list[float]]:
    return [[row[j] for j in basis] for row in A]


def _simplex_core(
    A: list[list[float]],
    b: list[float],
    c: list[float],
    basis: list[int],
    max_iter: int = 20000,
) -> tuple[list[int], list[float]]:
    """Revised Simplex solver with Bland's anti-cycling rule."""
    m_rows = len(A)
    n_cols = len(A[0])
    basis = list(basis)
    max_c = max((abs(v) for v in c), default=0.0)
    rc_tol = 1e-9 * max(1.0, max_c)
    piv_tol = 1e-10

    for _ in range(max_iter):
        B = _basis_matrix(A, basis)
        x_B = _solve_linear(B, b)
        c_B = [c[j] for j in basis]
        pi = _solve_linear(B, c_B, transpose=True)

        # Bland's rule: pick smallest column index with strictly negative reduced cost
        entering = -1
        for j in range(n_cols):
            col_dot_pi = math.fsum(A[r][j] * pi[r] for r in range(m_rows))
            if c[j] - col_dot_pi < -rc_tol:
                entering = j
                break
        if entering == -1:
            return basis, x_B

        col_enter = [A[r][entering] for r in range(m_rows)]
        d = _solve_linear(B, col_enter)
        pos_rows = [r for r in range(m_rows) if d[r] > piv_tol]
        if not pos_rows:
            raise RuntimeError("LP appears unbounded along entering direction")

        ratios = [max(0.0, x_B[r]) / d[r] for r in pos_rows]
        min_ratio = min(ratios)
        ratio_tol = 1e-11 * max(1.0, min_ratio)
        leaving_row = min(
            (r for r, rat in zip(pos_rows, ratios) if rat <= min_ratio + ratio_tol),
            key=lambda r: basis[r],
        )
        basis[leaving_row] = entering

    raise RuntimeError(f"Simplex exceeded max_iter={max_iter} without converging")


def _solve_canonical_lp(
    g: list[float],
    G_struct: list[list[float]],
    h_struct: list[float],
    E: list[list[float]],
    e: list[float],
) -> tuple[list[float], list[float], list[float], float]:
    """Solve `min g^T z` s.t. `G_struct z <= h_struct, E z = e, z >= 0`.

    Returns `(z_opt, lam_full, y_eq, M_dual)` where `lam_full >= 0` covers both
    structural inequalities `G_struct` and variable nonnegativity `-z <= 0`.
    """
    n_z = len(g)
    r_s = len(G_struct)
    p_eq = len(E)
    m_rows = r_s + p_eq
    n_orig = n_z + r_s

    A_orig: list[list[float]] = []
    for r in range(r_s):
        row = list(G_struct[r]) + [0.0] * r_s
        row[n_z + r] = 1.0
        A_orig.append(row)
    for r in range(p_eq):
        A_orig.append(list(E[r]) + [0.0] * r_s)

    b_orig = [float(x) for x in h_struct] + [float(x) for x in e]
    c_orig = [float(x) for x in g] + [0.0] * r_s

    row_sign = [-1.0 if val < 0.0 else 1.0 for val in b_orig]
    A_tab = [[s * x for x in row] for s, row in zip(row_sign, A_orig)]
    b_tab = [abs(x) for x in b_orig]

    basis = [-1] * m_rows
    art_rows: list[int] = []
    for r in range(m_rows):
        if r < r_s and row_sign[r] > 0.0:
            basis[r] = n_z + r
        else:
            basis[r] = n_orig + len(art_rows)
            art_rows.append(r)

    n_art = len(art_rows)
    if n_art > 0:
        art_col_for_row = {r: n_orig + idx for idx, r in enumerate(art_rows)}
        A_p1: list[list[float]] = []
        for r in range(m_rows):
            ext = [0.0] * n_art
            if r in art_col_for_row:
                ext[art_col_for_row[r] - n_orig] = 1.0
            A_p1.append(A_tab[r] + ext)
        c_p1 = [0.0] * n_orig + [1.0] * n_art

        basis_p1, x_p1 = _simplex_core(A_p1, b_tab, c_p1, basis)
        art_row_of_col = {n_orig + idx: r for idx, r in enumerate(art_rows)}
        for j, val in zip(basis_p1, x_p1):
            if j >= n_orig:
                r_orig = art_row_of_col[j]
                row_norm = math.fsum(abs(v) for v in A_orig[r_orig][:n_z])
                row_tol = 1e-12 + 1e-13 * (abs(b_tab[r_orig]) + row_norm)
                if val > row_tol:
                    raise InfeasibleCampaignError(
                        f"Campaign constraints are infeasible (row {r_orig} Phase I residual={val:.3e} > tol={row_tol:.3e})"
                    )

        active_rows = list(range(m_rows))
        cur_A = [row[:] for row in A_tab]
        cur_b = list(b_tab)
        cur_basis = list(basis_p1)

        row_pos = 0
        while row_pos < len(cur_basis):
            if cur_basis[row_pos] >= n_orig:
                k_act = len(active_rows)
                B_mat = [[0.0] * k_act for _ in range(k_act)]
                for col_i, idx_b in enumerate(cur_basis):
                    if idx_b < n_orig:
                        for ri in range(k_act):
                            B_mat[ri][col_i] = cur_A[ri][idx_b]
                    else:
                        ri_art = active_rows.index(art_row_of_col[idx_b])
                        B_mat[ri_art][col_i] = 1.0
                e_r = [0.0] * k_act
                e_r[row_pos] = 1.0
                u_r = _solve_linear(B_mat, e_r, transpose=True)

                used = set(cur_basis)
                best_val = 0.0
                best_j = -1
                for j in range(n_orig):
                    if j in used:
                        continue
                    v = abs(math.fsum(u_r[ri] * cur_A[ri][j] for ri in range(k_act)))
                    if v > best_val:
                        best_val = v
                        best_j = j
                if best_val > 1e-8 and best_j >= 0:
                    cur_basis[row_pos] = best_j
                    row_pos += 1
                else:
                    active_rows.pop(row_pos)
                    cur_basis.pop(row_pos)
                    cur_A = [A_tab[r][:] for r in active_rows]
                    cur_b = [b_tab[r] for r in active_rows]
            else:
                row_pos += 1
    else:
        active_rows = list(range(m_rows))
        cur_A = A_tab
        cur_b = b_tab
        cur_basis = basis

    basis_p2, x_p2 = _simplex_core(cur_A, cur_b, c_orig, cur_basis)
    B_opt = _basis_matrix(cur_A, basis_p2)

    x_sol = [0.0] * n_orig
    for j, val in zip(basis_p2, x_p2):
        if val < -1e-12:
            raise InfeasibleCampaignError(
                f"Campaign constraints are infeasible (negative basic variable x[{j}]={val:.3e})"
            )
        x_sol[j] = max(0.0, val)
    z_opt = x_sol[:n_z]

    # Verify exact per-row primal feasibility on the unscaled canonical system before returning.
    for r in range(r_s):
        viol = _dot(G_struct[r], z_opt) - h_struct[r]
        row_norm = math.fsum(abs(v) for v in G_struct[r])
        row_tol = 1e-12 + 1e-13 * (abs(h_struct[r]) + row_norm)
        if viol > row_tol:
            raise InfeasibleCampaignError(
                f"Campaign inequality row {r} infeasible (violation={viol:.3e} > tol={row_tol:.3e})"
            )
    for l in range(p_eq):
        viol = abs(_dot(E[l], z_opt) - e[l])
        row_norm = math.fsum(abs(v) for v in E[l])
        row_tol = 1e-12 + 1e-13 * (abs(e[l]) + row_norm)
        if viol > row_tol:
            raise InfeasibleCampaignError(
                f"Campaign equality row {l} infeasible (violation={viol:.3e} > tol={row_tol:.3e})"
            )

    pi_p2 = _solve_linear(B_opt, [c_orig[j] for j in basis_p2], transpose=True)
    pi_tab = [0.0] * m_rows
    for k_pos, orig_r in enumerate(active_rows):
        pi_tab[orig_r] = pi_p2[k_pos]
    pi_orig = [s * p for s, p in zip(row_sign, pi_tab)]

    lam_struct = [max(0.0, -pi_orig[r]) for r in range(r_s)]
    y_eq = [-pi_orig[r_s + l] for l in range(p_eq)]

    lam_nn: list[float] = []
    M_dual = 0.0
    for i in range(n_z):
        col_pi = math.fsum(A_orig[r][i] * pi_orig[r] for r in range(m_rows))
        rc_i = c_orig[i] - col_pi
        l_nn_i = max(0.0, rc_i)
        lam_nn.append(l_nn_i)
        res_i = (
            g[i]
            + math.fsum(G_struct[r][i] * lam_struct[r] for r in range(r_s))
            - l_nn_i
            + math.fsum(E[l][i] * y_eq[l] for l in range(p_eq))
        )
        if abs(res_i) > M_dual:
            M_dual = abs(res_i)

    lam_full = lam_struct + lam_nn
    return z_opt, lam_full, y_eq, M_dual


def _evaluate_exact_certificate(
    problem: CampaignProblem,
    scenario_indices: list[int],
    w: Sequence[float],
    var_t: float,
    u_vec: Sequence[float],
    lam_full: Sequence[float],
    y_eq: Sequence[float],
    *,
    reported_objective: float | None = None,
) -> DualCertificate:
    """Evaluate `S10d` feasibility and upper-rounded suboptimality bound in exact rationals."""
    m = problem.n_candidates
    s_indices = sorted(scenario_indices)
    s_len = len(s_indices)
    idx_t = m
    idx_u0 = m + 1
    n_z = m + 1 + s_len

    L_q = [[Fraction(x) for x in row] for row in problem.loss_matrix]
    L_min_q = min(x for row in L_q for x in row)
    L_max_q = max(x for row in L_q for x in row)
    spread_q = max(Fraction(0), L_max_q - L_min_q)
    c_q = problem.c_exact

    g_q = [Fraction(0)] * n_z
    g_q[idx_t] = Fraction(1)
    for k_pos in range(s_len):
        g_q[idx_u0 + k_pos] = c_q

    G_struct_q: list[list[Fraction]] = []
    h_struct_q: list[Fraction] = []
    for j in range(m):
        row = [Fraction(0)] * n_z
        row[j] = Fraction(1)
        G_struct_q.append(row)
        h_struct_q.append(Fraction(problem.hi[j]))
    for r, req_r in enumerate(problem.req):
        row = [-Fraction(v) for v in problem.cov[r]] + [Fraction(0)] * (1 + s_len)
        G_struct_q.append(row)
        h_struct_q.append(-Fraction(req_r))
    G_struct_q.append([Fraction(v) for v in problem.cost] + [Fraction(0)] * (1 + s_len))
    h_struct_q.append(Fraction(problem.budget))
    for k_pos, scen_idx in enumerate(s_indices):
        row = [L_q[scen_idx][j] - L_min_q for j in range(m)] + [Fraction(0)] * (1 + s_len)
        row[idx_t] = Fraction(-1)
        row[idx_u0 + k_pos] = Fraction(-1)
        G_struct_q.append(row)
        h_struct_q.append(Fraction(0))

    E_q = [[Fraction(1)] * m + [Fraction(0)] * (1 + s_len)]
    e_q = [Fraction(1)]

    w_q = [Fraction(v) for v in w]
    t_q = Fraction(var_t)
    t_tilde_q = t_q - L_min_q
    u_q = [Fraction(v) for v in u_vec]
    z_q = w_q + [t_tilde_q] + u_q

    r_s = len(G_struct_q)
    lam_full_q = [Fraction(v) for v in lam_full]
    lam_struct_q = lam_full_q[:r_s]
    lam_nn_q = lam_full_q[r_s:]
    y_eq_q = [Fraction(v) for v in y_eq]

    ineq_slacks_q = [h_struct_q[r] - _dot_q(G_struct_q[r], z_q) for r in range(r_s)] + z_q
    eq_res_q = [e_q[l] - _dot_q(E_q[l], z_q) for l in range(len(E_q))]
    unshifted_epi_viols = [
        max(Fraction(0), _dot_q(L_q[scen_idx], w_q) - t_q - u_q[k_pos])
        for k_pos, scen_idx in enumerate(s_indices)
    ]

    max_ineq_viol_q = max([max(Fraction(0), -s) for s in ineq_slacks_q] + unshifted_epi_viols, default=Fraction(0))
    max_eq_viol_q = max((abs(v) for v in eq_res_q), default=Fraction(0))
    dual_min_q = min(lam_full_q, default=Fraction(0))
    min_z_q = min(z_q, default=Fraction(0))

    M_dual_q = Fraction(0)
    for i in range(n_z):
        res_i_q = (
            g_q[i]
            + sum((G_struct_q[r][i] * lam_struct_q[r] for r in range(r_s)), Fraction(0))
            - lam_nn_q[i]
            + sum((E_q[l][i] * y_eq_q[l] for l in range(len(E_q))), Fraction(0))
        )
        abs_res = abs(res_i_q)
        if abs_res > M_dual_q:
            M_dual_q = abs_res

    comp_gap_q = sum((l * s for l, s in zip(lam_full_q, ineq_slacks_q)), Fraction(0)) + sum(
        (yv * ev for yv, ev in zip(y_eq_q, eq_res_q)), Fraction(0)
    )
    z_star_l1_max_q = Fraction(1) + (Fraction(1) + s_len) * spread_q
    l1_bound_q = sum((abs(v) for v in z_q), Fraction(0)) + z_star_l1_max_q

    lp_obj_q = _dot_q(g_q, z_q) + L_min_q
    obj_float = float(lp_obj_q) if reported_objective is None else float(reported_objective)
    obj_rounding_q = max(Fraction(0), Fraction(obj_float) - lp_obj_q)
    obj_rounding_upper = _fraction_to_float_upper(obj_rounding_q)
    num_est_q = comp_gap_q + M_dual_q * l1_bound_q + obj_rounding_q

    # Shifted LP domain t_tilde >= 0 is equivalent to unshifted t in R iff |S| * c_exact >= 1.
    shifted_domain_equivalent = s_len * c_q >= Fraction(1)
    is_certified = (
        shifted_domain_equivalent
        and max_ineq_viol_q == 0
        and max_eq_viol_q == 0
        and dual_min_q >= 0
        and min_z_q >= 0
    )
    bound_upper = _fraction_to_float_upper(num_est_q)
    return DualCertificate(
        objective_value=obj_float,
        primal_max_ineq_violation=_fraction_to_float_upper(max_ineq_viol_q),
        primal_max_eq_violation=_fraction_to_float_upper(max_eq_viol_q),
        dual_min_multiplier=_fraction_to_float_lower(dual_min_q),
        dual_residual_linf=_fraction_to_float_upper(M_dual_q),
        complementarity_gap=_fraction_to_float_upper(comp_gap_q),
        l1_radius_bound=_fraction_to_float_upper(l1_bound_q),
        certified_subopt_le=bound_upper if is_certified else None,
        certified=is_certified,
        certification_status="exact" if is_certified else "uncertified-numerical-tolerance",
        numerical_subopt_estimate=bound_upper,
        objective_rounding_error=obj_rounding_upper,
    )


def _solve_screened_lp_raw(
    problem: CampaignProblem,
    scenario_indices: list[int],
) -> tuple[list[float], float, list[float], list[float], list[float], DualCertificate]:
    """Solve the linearized Rockafellar–Uryasev LP on scenario subset `S`."""
    m = problem.n_candidates
    s_indices = sorted(scenario_indices)
    s_len = len(s_indices)
    c_val = problem.c
    L = problem.loss_matrix
    L_min = min(x for row in L for x in row)
    L_sub = [[L[i][j] - L_min for j in range(m)] for i in s_indices]

    # Variables z = [w (m), t_tilde (1), u_S (s_len)] >= 0, with t = L_min + t_tilde
    idx_t = m
    idx_u0 = m + 1
    n_z = m + 1 + s_len

    g = [0.0] * n_z
    g[idx_t] = 1.0
    for k_pos in range(s_len):
        g[idx_u0 + k_pos] = c_val

    G_struct: list[list[float]] = []
    h_struct: list[float] = []

    # 1. w_j <= hi_j
    for j in range(m):
        row = [0.0] * n_z
        row[j] = 1.0
        G_struct.append(row)
        h_struct.append(problem.hi[j])

    # 2. -cov[r] @ w <= -req[r]
    for r, req_r in enumerate(problem.req):
        row = [-v for v in problem.cov[r]] + [0.0] * (1 + s_len)
        G_struct.append(row)
        h_struct.append(-req_r)

    # 3. cost @ w <= budget
    G_struct.append(list(problem.cost) + [0.0] * (1 + s_len))
    h_struct.append(problem.budget)

    # 4. L_sub[k] @ w - t_tilde - u_k <= 0
    for k_pos in range(s_len):
        row = list(L_sub[k_pos]) + [0.0] * (1 + s_len)
        row[idx_t] = -1.0
        row[idx_u0 + k_pos] = -1.0
        G_struct.append(row)
        h_struct.append(0.0)

    E = [[1.0] * m + [0.0] * (1 + s_len)]
    e = [1.0]

    z_opt, lam_full, y_eq, _ = _solve_canonical_lp(g, G_struct, h_struct, E, e)

    w = z_opt[:m]
    t_tilde = z_opt[idx_t]
    u_sub = z_opt[idx_u0:]
    t_abs = t_tilde + L_min

    cert = _evaluate_exact_certificate(problem, s_indices, w, t_abs, u_sub, lam_full, y_eq)
    return w, t_abs, u_sub, lam_full, y_eq, cert


def _solve_screened_lp(
    problem: CampaignProblem,
    scenario_indices: list[int],
) -> tuple[list[float], float, list[float], DualCertificate]:
    """Solve the linearized Rockafellar–Uryasev LP on scenario subset `S`."""
    w, t_abs, u_sub, _lam, _y, cert = _solve_screened_lp_raw(problem, scenario_indices)
    return w, t_abs, u_sub, cert


def solve_cvar_campaign(
    problem: CampaignProblem,
    *,
    use_screening: bool = True,
    initial_scenarios: int | None = None,
    screen_tol: float = 0.0,
) -> CampaignSolution:
    """Solve the multi-year Rockafellar–Uryasev CVaR campaign optimization LP.

    When `use_screening=True` (`S10b_cvar_screening_exact`), begins with a tail
    subset `S` containing at least `ceil(alpha * T)` high-loss years (ensuring
    `c_exact * |S| >= 1`), solves the screened LP, checks omitted years `i not in S`,
    and expands `S` until every omitted year satisfies `loss_i <= t* + screen_tol`
    (verified in exact rational arithmetic).

    `screen_tol` defaults to `0.0` (exact `S10b` condition `loss_i <= t*`). When
    a caller passes `screen_tol > 0`, `screening_exact` is `True` ONLY when every
    omitted scenario strictly satisfies `loss_i <= t*`; otherwise `screening_exact`
    is `False` and the returned `DualCertificate` is extended to the full `T`-year
    LP (`lam_omitted = 0`, `lam_nn_u = c`) and verified in exact rational arithmetic
    against `c_exact = 1 / (alpha * T)` so `certified_subopt_le` remains a sound
    `S10d` bound whenever exact primal and dual feasibility hold (`certified=True`).
    """
    screen_tol_f = float(screen_tol)
    if not math.isfinite(screen_tol_f) or screen_tol_f < 0.0:
        raise ValueError("screen_tol must be finite and >= 0")

    if sum(Fraction(h) for h in problem.hi) < Fraction(1):
        raise InfeasibleCampaignError(
            "Campaign constraints are infeasible (exact sum(hi) < 1; simplex cannot sum to 1)"
        )
    if all(c >= 0.0 for c in problem.cost) and min(Fraction(c) for c in problem.cost) > Fraction(problem.budget):
        raise InfeasibleCampaignError(
            "Campaign constraints are infeasible (minimum nonnegative candidate cost exceeds budget)"
        )

    m = problem.n_candidates
    t_cnt = problem.n_years
    L_q = [[Fraction(x) for x in row] for row in problem.loss_matrix]
    c_q = problem.c_exact
    screen_tol_q = Fraction(screen_tol_f)

    alpha_t_q = Fraction(problem.alpha) * t_cnt
    min_active = max(1, (alpha_t_q.numerator + alpha_t_q.denominator - 1) // alpha_t_q.denominator)
    if not use_screening or t_cnt <= min_active:
        active = list(range(t_cnt))
    else:
        n0 = min_active if initial_scenarios is None else max(min_active, min(t_cnt, initial_scenarios))
        row_scores = [
            (sum(row) / len(row) + max(row), idx) for idx, row in enumerate(problem.loss_matrix)
        ]
        ranked = sorted(row_scores, key=lambda pair: (-pair[0], pair[1]))
        active = sorted(idx for _, idx in ranked[:n0])

    iterations = 0
    while True:
        iterations += 1
        w, var_t, u_sub, lam_full, y_eq, cert = _solve_screened_lp_raw(problem, active)
        w_q = [Fraction(v) for v in w]
        t_q = Fraction(var_t)
        losses_q = [_dot_q(L_q[i], w_q) for i in range(t_cnt)]
        active_set = set(active)
        violators = [i for i in range(t_cnt) if i not in active_set and losses_q[i] > t_q + screen_tol_q]
        if not violators:
            break
        active = sorted(active_set | set(violators))

    active_set = set(active)
    dropped = [i for i in range(t_cnt) if i not in active_set]
    true_excess_q = [max(Fraction(0), losses_q[i] - t_q) for i in range(t_cnt)]
    full_cvar_q = t_q + c_q * sum(true_excess_q, Fraction(0))
    full_cvar = float(full_cvar_q)
    losses = [float(lv) for lv in losses_q]
    all_excess = [float(ev) for ev in true_excess_q]
    screening_exact = all(losses_q[i] <= t_q for i in dropped)

    if screening_exact:
        cert = _evaluate_exact_certificate(
            problem,
            active,
            w,
            var_t,
            u_sub,
            lam_full,
            y_eq,
            reported_objective=full_cvar,
        )
    else:
        # Extend (u, lam_full) to the full T-year LP in exact order 0..T-1:
        # for dropped scenarios i, u_i = upper_float(max(0, loss_i - t)), lam_struct_i = 0, lam_nn_u_i = c.
        s_len = len(active)
        base_r = m + len(problem.req) + 1
        active_pos = {scen_idx: pos for pos, scen_idx in enumerate(active)}
        u_full: list[float] = []
        lam_epi_full: list[float] = []
        lam_nn_u_full: list[float] = []
        for i in range(t_cnt):
            pos = active_pos.get(i)
            if pos is not None:
                u_full.append(u_sub[pos])
                lam_epi_full.append(lam_full[base_r + pos])
                lam_nn_u_full.append(lam_full[base_r + s_len + m + 1 + pos])
            else:
                u_full.append(_fraction_to_float_upper(true_excess_q[i]))
                lam_epi_full.append(0.0)
                lam_nn_u_full.append(problem.c)

        lam_full_ext = (
            list(lam_full[:base_r])
            + lam_epi_full
            + list(lam_full[base_r + s_len : base_r + s_len + m + 1])
            + lam_nn_u_full
        )
        cert = _evaluate_exact_certificate(
            problem,
            list(range(t_cnt)),
            w,
            var_t,
            u_full,
            lam_full_ext,
            y_eq,
            reported_objective=full_cvar,
        )

    cost_q = [Fraction(v) for v in problem.cost]
    cov_q = [[Fraction(v) for v in row] for row in problem.cov]
    return CampaignSolution(
        weights={cid: float(w[j]) for j, cid in enumerate(problem.candidate_ids)},
        var_t=var_t,
        cvar=full_cvar,
        scenario_losses={problem.years[i]: losses[i] for i in range(t_cnt)},
        tail_excess={problem.years[i]: all_excess[i] for i in range(t_cnt)},
        expected_cost=float(_dot_q(cost_q, w_q)),
        achieved_coverage=[float(_dot_q(row_q, w_q)) for row_q in cov_q],
        screened_years=[problem.years[i] for i in active],
        dropped_years=[problem.years[i] for i in dropped],
        screening_iterations=iterations,
        screening_exact=screening_exact,
        certificate=cert,
    )


def build_campaign_problem_from_years(
    candidates: Iterable[dict],
    years_parquet_path: Path,
    *,
    month: int,
    target_row: dict | None = None,
    thermal_band_k: tuple[float, float] | None = None,
    expected_years: Iterable[int] | None = None,
    alpha: float = 0.2,
    max_weight_per_site: float = 0.5,
    budget: float | None = None,
    coverage_rules: list[tuple[str, float, float, str]] | None = None,
) -> tuple[CampaignProblem, list[dict]]:
    """Construct a multi-year `CampaignProblem` from `cells-r4-monthly-years.parquet`.

    Each candidate dict comes from `pareto_model` / `earth-features-r4` and must
    contain `h3` (and `observations`/`access_min_median`).

    Completeness (`Rule 2`: never invent data):
    - When `expected_years` is provided (e.g. `range(2014, 2024)`), every candidate
      missing ANY year in `expected_years` for `month` is excluded cleanly.
    - When `expected_years` is `None`, completeness is checked over every year
      observed in `years_parquet_path` for `month` across the supplied candidates.

    Constraints (`S10e`):
    - `max_weight_per_site` and explicit `budget` are preserved verbatim without
      silent relaxation; infeasible values raise `InfeasibleCampaignError` when solved.
    - When `budget` is `None`, defaults to the median `access_min_median` among kept
      candidates.
    - Requires `thermal_band_k` or finite `target_tsurf_min_k` / `target_tsurf_range_k`
      on `target_row`.
    """
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    cand_list = list(candidates)
    if not cand_list:
        raise ValueError("No candidates provided to build_campaign_problem_from_years")
    if not (1 <= month <= 12):
        raise ValueError("month must be in 1..12")
    cap = float(max_weight_per_site)
    if not math.isfinite(cap) or cap < 0.0:
        raise ValueError("max_weight_per_site must be finite and >= 0")

    t_min_target = None if target_row is None else target_row.get("target_tsurf_min_k")
    t_range_target = None if target_row is None else target_row.get("target_tsurf_range_k")
    has_min_target = t_min_target is not None and math.isfinite(float(t_min_target))
    has_range_target = t_range_target is not None and math.isfinite(float(t_range_target))
    if thermal_band_k is None and not (has_min_target or has_range_target):
        raise ValueError(
            "build_campaign_problem_from_years requires thermal_band_k or finite "
            "target_tsurf_min_k / target_tsurf_range_k on target_row"
        )

    h3_ids = [str(c["h3"]) for c in cand_list]
    tbl = pq.read_table(
        Path(years_parquet_path),
        columns=["h3", "year", "month", "lst_day_k", "lst_night_k"],
        filters=[("month", "=", month)],
    )
    tbl = tbl.filter(pc.is_in(tbl["h3"], value_set=pa.array(h3_ids)))
    rows_by_h3_year: dict[tuple[str, int], dict] = {}
    all_years: set[int] = set()
    for r in tbl.to_pylist():
        y = int(r["year"])
        all_years.add(y)
        rows_by_h3_year[(str(r["h3"]), y)] = r

    if expected_years is not None:
        years = sorted({int(y) for y in expected_years})
        if not years:
            raise ValueError("expected_years must not be empty when provided")
    else:
        years = sorted(all_years)
        if not years:
            raise ValueError(f"No historical year rows found for month={month} and provided candidates")

    def _annual_loss(row: dict) -> float | None:
        day_k = row.get("lst_day_k")
        night_k = row.get("lst_night_k")
        if day_k is None or night_k is None:
            return None
        d = float(day_k)
        n = float(night_k)
        if not (math.isfinite(d) and math.isfinite(n)):
            return None
        if thermal_band_k is not None:
            lo_k, hi_k = float(thermal_band_k[0]), float(thermal_band_k[1])
            return max(0.0, lo_k - n) + max(0.0, d - hi_k)
        loss_k = 0.0
        if has_range_target:
            loss_k += abs((d - n) - float(t_range_target))
        if has_min_target:
            loss_k += abs(n - float(t_min_target))
        return loss_k

    kept: list[dict] = []
    excluded: list[dict] = []
    loss_cols: list[list[float]] = []

    for c in cand_list:
        h3 = str(c["h3"])
        obs = c.get("observations", {})
        access = c.get("access_min_median", obs.get("access_min_median"))
        if access is None:
            excluded.append({"h3": h3, "reason": "missing-access-cost"})
            continue
        col_losses: list[float] = []
        missing_year: int | None = None
        for y in years:
            yr_row = rows_by_h3_year.get((h3, y))
            lv = None if yr_row is None else _annual_loss(yr_row)
            if lv is None:
                missing_year = y
                break
            col_losses.append(lv)
        if missing_year is not None:
            excluded.append({"h3": h3, "reason": f"missing-year-{missing_year}-lst"})
            continue
        kept.append(c)
        loss_cols.append(col_losses)

    if not kept:
        raise InfeasibleCampaignError(
            f"Every candidate lacks complete yearly data ({years[0]}..{years[-1]}) or access cost"
        )

    m = len(kept)
    hi = [cap] * m
    # Transpose loss_cols (m x T) -> loss_matrix (T x m)
    t_cnt = len(years)
    loss_matrix = [[loss_cols[j][i] for j in range(m)] for i in range(t_cnt)]

    costs = [
        float(c.get("access_min_median", c.get("observations", {}).get("access_min_median")))
        for c in kept
    ]
    if budget is None:
        s_costs = sorted(costs)
        eff_budget = s_costs[len(s_costs) // 2]
    else:
        eff_budget = float(budget)

    cov_rows: list[list[float]] = []
    req_vals: list[float] = []
    for col_name, thresh, min_share, op in (coverage_rules or []):
        indicators: list[float] = []
        for c in kept:
            v = c.get(col_name, c.get("observations", {}).get(col_name))
            if v is None:
                indicators.append(0.0)
            elif op == ">=":
                indicators.append(1.0 if float(v) >= float(thresh) else 0.0)
            elif op == "<=":
                indicators.append(1.0 if float(v) <= float(thresh) else 0.0)
            else:
                raise ValueError(f"Unsupported coverage operator: {op!r}")
        cov_rows.append(indicators)
        req_vals.append(float(min_share))

    problem = CampaignProblem(
        candidate_ids=[f"{c['h3']}:m{month}" for c in kept],
        years=years,
        loss_matrix=loss_matrix,
        alpha=alpha,
        hi=hi,
        cov=cov_rows,
        req=req_vals,
        cost=costs,
        budget=eff_budget,
    )
    return problem, excluded
