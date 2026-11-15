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


@dataclass(frozen=True)
class DualCertificate:
    """Audit artifact mirroring `Analog.CampaignOpt.S10d_dual_subopt_certificate`.

    `S10d` is instantiated over the nonnegativity-augmented inequality system
    `G_aug = [G_struct; -I]`, `h_aug = [h_struct; 0]` with multiplier vector
    `lam_full = lam_struct + lam_nn >= 0`, so `dual_residual_linf` bounds
    `||g + G_aug^T lam_full + E^T y||_inf`.

    `l1_radius_bound` bounds `||z - z*||_1` for any optimal `(w*, t*, u*)`
    (since an optimal VaR `t*` lies in `[L_min, L_max]` and `0 <= u_k* <= spread`);
    for an arbitrary feasible `z*`, call `subopt_bound(||z - z*||_1)` directly.
    """

    objective_value: float
    primal_max_ineq_violation: float
    primal_max_eq_violation: float
    dual_min_multiplier: float
    dual_residual_linf: float
    complementarity_gap: float
    l1_radius_bound: float
    certified_subopt_le: float

    def subopt_bound(self, z_minus_zs_l1: float) -> float:
        """Evaluate exact `S10d` RHS for a given L1 deviation `||z - z*||_1`."""
        return self.complementarity_gap + self.dual_residual_linf * float(z_minus_zs_l1)


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
        p1_obj = math.fsum(c_p1[j] * v for j, v in zip(basis_p1, x_p1))
        feas_tol = 1e-7 * max(1.0, max((abs(v) for v in b_tab), default=0.0))
        if p1_obj > feas_tol:
            raise InfeasibleCampaignError(
                f"Campaign constraints are infeasible (Phase I residual={p1_obj:.3e})"
            )

        active_rows = list(range(m_rows))
        cur_A = [row[:] for row in A_tab]
        cur_b = list(b_tab)
        cur_basis = list(basis_p1)
        art_row_of_col = {n_orig + idx: r for idx, r in enumerate(art_rows)}

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
        x_sol[j] = max(0.0, val)
    z_opt = x_sol[:n_z]

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


def _solve_screened_lp(
    problem: CampaignProblem,
    scenario_indices: list[int],
) -> tuple[list[float], float, list[float], DualCertificate]:
    """Solve the linearized Rockafellar–Uryasev LP on scenario subset `S`."""
    m = problem.n_candidates
    s_indices = sorted(scenario_indices)
    s_len = len(s_indices)
    c_val = problem.c
    L = problem.loss_matrix
    L_min = min(x for row in L for x in row)
    L_max = max(x for row in L for x in row)
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

    z_opt, lam_full, y_eq, M_dual = _solve_canonical_lp(g, G_struct, h_struct, E, e)

    w = z_opt[:m]
    t_tilde = z_opt[idx_t]
    u_sub = z_opt[idx_u0:]
    t_abs = t_tilde + L_min

    # Compute exact S10d certificate components over G_full z <= h_full, E z = e
    r_s = len(G_struct)
    ineq_slacks = [h_struct[r] - _dot(G_struct[r], z_opt) for r in range(r_s)] + list(z_opt)
    eq_res = [e[l] - _dot(E[l], z_opt) for l in range(len(E))]

    max_ineq_viol = max((max(0.0, -s) for s in ineq_slacks), default=0.0)
    max_eq_viol = max((abs(v) for v in eq_res), default=0.0)
    comp_gap = math.fsum(l * s for l, s in zip(lam_full, ineq_slacks)) + math.fsum(
        yv * ev for yv, ev in zip(y_eq, eq_res)
    )

    spread = max(0.0, L_max - L_min)
    z_star_l1_max = 1.0 + (1.0 + s_len) * spread
    l1_bound = math.fsum(abs(v) for v in z_opt) + z_star_l1_max

    cert = DualCertificate(
        objective_value=_dot(g, z_opt) + L_min,
        primal_max_ineq_violation=max_ineq_viol,
        primal_max_eq_violation=max_eq_viol,
        dual_min_multiplier=min(lam_full, default=0.0),
        dual_residual_linf=M_dual,
        complementarity_gap=comp_gap,
        l1_radius_bound=l1_bound,
        certified_subopt_le=comp_gap + M_dual * l1_bound,
    )
    return w, t_abs, u_sub, cert


def solve_cvar_campaign(
    problem: CampaignProblem,
    *,
    use_screening: bool = True,
    initial_scenarios: int | None = None,
    screen_tol: float = 1e-8,
) -> CampaignSolution:
    """Solve the multi-year Rockafellar–Uryasev CVaR campaign optimization LP.

    When `use_screening=True` (`S10b_cvar_screening_exact`), begins with a tail
    subset `S` containing at least `ceil(alpha * T)` high-loss years (ensuring
    `c * |S| >= 1`), solves the screened LP, checks all dropped years `i not in S`
    for `loss_i <= t* + screen_tol`, and expands `S` until every omitted year
    is certified inactive.
    """
    t_cnt = problem.n_years
    min_active = max(1, math.ceil(problem.alpha * t_cnt))
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
        w, var_t, _, cert = _solve_screened_lp(problem, active)
        losses = [_dot(problem.loss_matrix[i], w) for i in range(t_cnt)]
        active_set = set(active)
        violators = [i for i in range(t_cnt) if i not in active_set and losses[i] > var_t + screen_tol]
        if not violators:
            break
        active = sorted(active_set | set(violators))

    active_set = set(active)
    dropped = [i for i in range(t_cnt) if i not in active_set]
    all_excess = [max(0.0, losses[i] - var_t) for i in range(t_cnt)]
    full_cvar = var_t + problem.c * math.fsum(all_excess)
    screening_exact = all(losses[i] <= var_t + screen_tol for i in dropped)

    return CampaignSolution(
        weights={cid: float(w[j]) for j, cid in enumerate(problem.candidate_ids)},
        var_t=var_t,
        cvar=full_cvar,
        scenario_losses={problem.years[i]: float(losses[i]) for i in range(t_cnt)},
        tail_excess={problem.years[i]: float(all_excess[i]) for i in range(t_cnt)},
        expected_cost=_dot(problem.cost, w),
        achieved_coverage=[_dot(row, w) for row in problem.cov],
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
