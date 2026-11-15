"""Conformance & property tests for Lean S9 (pareto_model) and S10 (optimizer)."""
from __future__ import annotations

import math
import os
import random
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

from planner.optimizer import (
    CampaignProblem,
    InfeasibleCampaignError,
    build_campaign_problem_from_years,
    solve_cvar_campaign,
)
from planner.pareto_model import (
    AxisSpec,
    build_target_axes,
    evaluate_sites,
    pareto_layers,
    rank_earth_for_target,
    select_diverse_frontier_candidates,
)


def _dominates(u: tuple[float, ...], v: tuple[float, ...]) -> bool:
    return all(a <= b for a, b in zip(u, v)) and any(a < b for a, b in zip(u, v))


def _naive_pareto_layers(vectors: list[tuple[float, ...]]) -> list[int]:
    """Reference iterative frontier peeling (exact S9 `peelRem` / `peelLayer`)."""
    unique = list(dict.fromkeys(vectors))
    remaining = set(unique)
    layer_of: dict[tuple[float, ...], int] = {}
    k = 1
    while remaining:
        front = [x for x in remaining if not any(_dominates(y, x) for y in remaining)]
        for x in front:
            layer_of[x] = k
            remaining.remove(x)
        k += 1
    return [layer_of[v] for v in vectors]


def _dot(a: list[float] | tuple[float, ...], b: list[float] | tuple[float, ...]) -> float:
    return sum(x * y for x, y in zip(a, b))


class ParetoModelS9Tests(unittest.TestCase):
    def test_empty_and_constant(self) -> None:
        self.assertEqual(pareto_layers([]), [])
        self.assertEqual(pareto_layers([(1.0, 2.0, 3.0), (1.0, 2.0, 3.0)]), [1, 1])

    def test_rejects_nonfinite_unknowns_s9e(self) -> None:
        with self.assertRaises(ValueError):
            pareto_layers([(0.0, math.nan), (1.0, 2.0)])
        with self.assertRaises(ValueError):
            pareto_layers([(0.0, math.inf), (1.0, 2.0)])

    def test_matches_naive_peeling_across_dimensions_s9a_to_s9g(self) -> None:
        rng = random.Random(20261115)
        for dim in (1, 2, 3, 4, 6):
            for _trial in range(12):
                vecs = [
                    tuple(round(rng.uniform(0.0, 5.0), 1) for _ in range(dim))
                    for _ in range(rng.randint(1, 35))
                ]
                if vecs:
                    vecs.append(vecs[0])
                got = pareto_layers(vecs)
                ref = _naive_pareto_layers(vecs)
                self.assertEqual(got, ref, f"Mismatch at dim={dim}")

                for i, vi in enumerate(vecs):
                    for j, vj in enumerate(vecs):
                        if got[i] == got[j]:
                            self.assertFalse(_dominates(vi, vj))
                        if _dominates(vi, vj):
                            self.assertLess(got[i], got[j])
                        if vi == vj:
                            self.assertEqual(got[i], got[j])

                for i, vi in enumerate(vecs):
                    dom_layers = [got[j] for j, vj in enumerate(vecs) if _dominates(vj, vi)]
                    expected = 1 + max(dom_layers, default=0)
                    self.assertEqual(got[i], expected)

    def test_tradeoff_corners_share_layer1_and_unknown_excluded_s9e_s9f(self) -> None:
        axes = [
            AxisSpec("slope_gap_deg", "slope_mean_deg", "deg", mode="target_abs", target_value=2.0),
            AxisSpec("diurnal_gap_k", "lst_diurnal_range_mean_k", "K", mode="target_abs", target_value=80.0),
            AxisSpec("dust_gap", "dust_aod_mean", "unitless", mode="target_abs", target_value=0.2),
        ]
        target = {"target_id": "mars-test", "body": "mars"}
        rows = [
            {"h3": "840000000000001", "lat": 20.0, "lon": 10.0, "slope_mean_deg": 2.0, "lst_diurnal_range_mean_k": 50.0, "dust_aod_mean": 0.4},
            {"h3": "840000000000002", "lat": 21.0, "lon": 11.0, "slope_mean_deg": 8.0, "lst_diurnal_range_mean_k": 80.0, "dust_aod_mean": 0.3},
            {"h3": "840000000000003", "lat": 22.0, "lon": 12.0, "slope_mean_deg": 6.0, "lst_diurnal_range_mean_k": 60.0, "dust_aod_mean": 0.2},
            {"h3": "840000000000004", "lat": 23.0, "lon": 13.0, "slope_mean_deg": 3.0, "lst_diurnal_range_mean_k": 45.0, "dust_aod_mean": 0.5},
            {"h3": "840000000000005", "lat": 24.0, "lon": 14.0, "slope_mean_deg": 2.0, "lst_diurnal_range_mean_k": 80.0, "dust_aod_mean": None, "missing_reason": '{"dust_aod_mean":"outside-domain"}'},
            {"h3": "840000000000006", "lat": 25.0, "lon": 15.0, "slope_mean_deg": 15.0, "lst_diurnal_range_mean_k": 80.0, "dust_aod_mean": 0.2},
        ]
        res = evaluate_sites(rows, axes, limits={"slope": 10.0, "protected": 5.0}, target=target)
        self.assertEqual(res["counts"]["comparable"], 4)
        self.assertEqual(res["counts"]["excludedUnknown"], 1)
        self.assertEqual(res["counts"]["excludedLimits"], 1)
        self.assertEqual([d["h3"] for d in res["excludedUnknown"]], ["840000000000005"])
        self.assertIsNone(res["excludedUnknown"][0]["paretoLayer"])

        layer_map = {d["h3"]: d["paretoLayer"] for d in res["comparable"]}
        self.assertEqual(layer_map["840000000000001"], 1)
        self.assertEqual(layer_map["840000000000002"], 1)
        self.assertEqual(layer_map["840000000000003"], 1)
        self.assertEqual(layer_map["840000000000004"], 2)
        self.assertEqual({m["mismatch"] for m in res["notTestableOnEarth"]}, {"gravity", "pressureRegime", "radiation"})

        chosen = select_diverse_frontier_candidates(res, max_candidates=3)
        self.assertEqual({d["h3"] for d in chosen}, {"840000000000001", "840000000000002", "840000000000003"})

        res_l1 = evaluate_sites(rows, axes, limits={"slope": 10.0, "protected": 5.0}, target=target, max_layers=1)
        self.assertEqual(res_l1["counts"]["comparable"], 4)
        self.assertEqual(res_l1["counts"]["returned"], 3)
        self.assertEqual(len(res_l1["comparable"]), 3)

    def test_build_target_axes_only_uses_populated_planetary_fields(self) -> None:
        sparse_target = {"target_id": "sparse", "body": "moon", "target_slope_local_deg": 3.5}
        axes, mismatches = build_target_axes(sparse_target, include_stability=False, include_barren=False)
        self.assertEqual([a.name for a in axes], ["slope_gap_deg"])
        self.assertEqual(len(mismatches), 3)


class CampaignOptimizerS10Tests(unittest.TestCase):
    def test_known_analytical_cvar_lp_and_dual_certificate_s10a_to_s10e(self) -> None:
        L = [
            [10.0, 4.0],
            [0.0, 4.0],
            [0.0, 4.0],
            [0.0, 4.0],
            [0.0, 4.0],
        ]
        prob = CampaignProblem(
            candidate_ids=["siteA", "siteB"],
            years=[2019, 2020, 2021, 2022, 2023],
            loss_matrix=L,
            alpha=0.2,
            hi=[1.0, 1.0],
            cov=[[1.0, 0.0]],
            req=[0.2],
            cost=[1.0, 3.0],
            budget=2.0,
        )
        sol_screen = solve_cvar_campaign(prob, use_screening=True, initial_scenarios=1)
        sol_full = solve_cvar_campaign(prob, use_screening=False)

        self.assertAlmostEqual(sol_screen.weights["siteA"], 0.5, places=8)
        self.assertAlmostEqual(sol_screen.weights["siteB"], 0.5, places=8)
        self.assertAlmostEqual(sol_screen.cvar, 7.0, places=8)
        self.assertAlmostEqual(sol_screen.cvar, sol_full.cvar, places=8)
        self.assertTrue(sol_screen.screening_exact)
        self.assertLessEqual(sol_screen.certificate.primal_max_ineq_violation, 1e-9)
        self.assertLessEqual(sol_screen.certificate.primal_max_eq_violation, 1e-9)
        self.assertGreaterEqual(sol_screen.certificate.dual_min_multiplier, 0.0)
        self.assertLessEqual(sol_screen.certificate.dual_residual_linf, 1e-9)
        self._assert_certificate_sound(sol_screen.certificate, max_bound=1e-8)

    def _assert_certificate_sound(self, cert, *, max_bound: float) -> None:
        self.assertLessEqual(cert.dual_residual_linf, 1e-8)
        if cert.certified:
            self.assertEqual(cert.certification_status, "exact")
            self.assertEqual(cert.primal_max_ineq_violation, 0.0)
            self.assertEqual(cert.primal_max_eq_violation, 0.0)
            self.assertGreaterEqual(cert.dual_min_multiplier, 0.0)
            self.assertIsNotNone(cert.certified_subopt_le)
            self.assertLessEqual(cert.certified_subopt_le, max_bound)
        else:
            self.assertEqual(cert.certification_status, "uncertified-numerical-tolerance")
            self.assertIsNone(cert.certified_subopt_le)
            self.assertLessEqual(max(cert.primal_max_ineq_violation, cert.primal_max_eq_violation), 1e-11)
            self.assertLessEqual(cert.numerical_subopt_estimate, max_bound)

    def test_random_screened_vs_full_equivalence_and_convexity(self) -> None:
        rng = random.Random(998877)
        for trial in range(15):
            T = rng.randint(8, 20)
            m = rng.randint(4, 10)
            k = 2
            alpha = rng.choice([0.1, 0.2, 0.25, 0.4])
            L = [[rng.uniform(5.0, 50.0) for _ in range(m)] for _ in range(T)]
            hi = [max(0.35, 2.0 / m)] * m
            cov = [[rng.choice([0.0, 1.0]) for _ in range(m)] for _ in range(k)]

            raw = [rng.uniform(0.1, 1.0) for _ in range(m)]
            s = sum(raw)
            w_seed = [v / s for v in raw]
            while any(w_seed[j] > hi[j] for j in range(m)):
                w_seed = [min(w_seed[j], hi[j] * 0.9) for j in range(m)]
                s = sum(w_seed)
                w_seed = [v / s for v in w_seed]

            req = [0.85 * _dot(row, w_seed) for row in cov]
            cost = [rng.uniform(10.0, 100.0) for _ in range(m)]
            budget = _dot(cost, w_seed) + 5.0

            prob = CampaignProblem(
                candidate_ids=[f"c{j}" for j in range(m)],
                years=list(range(2000, 2000 + T)),
                loss_matrix=L,
                alpha=alpha,
                hi=hi,
                cov=cov,
                req=req,
                cost=cost,
                budget=budget,
            )
            s_full = solve_cvar_campaign(prob, use_screening=False)
            s_scr = solve_cvar_campaign(prob, use_screening=True)

            self.assertAlmostEqual(s_scr.cvar, s_full.cvar, places=6, msg=f"trial={trial}")
            self.assertTrue(s_scr.screening_exact)

            w_arr = [s_scr.weights[cid] for cid in prob.candidate_ids]
            self.assertAlmostEqual(sum(w_arr), 1.0, places=8)
            for j in range(m):
                self.assertGreaterEqual(w_arr[j], -1e-10)
                self.assertLessEqual(w_arr[j], hi[j] + 1e-8)

            theta = 0.37
            w_mix = [(1.0 - theta) * w_arr[j] + theta * w_seed[j] for j in range(m)]
            self.assertAlmostEqual(sum(w_mix), 1.0, places=8)
            for r in range(k):
                self.assertGreaterEqual(_dot(cov[r], w_mix), req[r] - 1e-8)
            self.assertLessEqual(_dot(cost, w_mix), budget + 1e-8)

            self._assert_certificate_sound(s_scr.certificate, max_bound=1e-6)

            seed_losses = [_dot(row, w_seed) for row in L]
            cvar_seed = min(
                t_cand + prob.c * sum(max(0.0, lv - t_cand) for lv in seed_losses)
                for t_cand in seed_losses
            )
            self.assertLessEqual(s_scr.cvar, cvar_seed + 1e-7)

    def test_infeasible_problem_raises_cleanly(self) -> None:
        L = [[1.0, 1.0] for _ in range(4)]
        prob = CampaignProblem(
            candidate_ids=["a", "b"],
            years=[2020, 2021, 2022, 2023],
            loss_matrix=L,
            alpha=0.25,
            hi=[0.4, 0.4],
            cov=[],
            req=[],
            cost=[1.0, 2.0],
            budget=10.0,
        )
        with self.assertRaises(InfeasibleCampaignError):
            solve_cvar_campaign(prob)

    def test_constraint_scaling_and_near_boundary_infeasibility_raise(self) -> None:
        # Zero cap with unit sum and huge unrelated budget must raise InfeasibleCampaignError.
        prob_scaled = CampaignProblem(["a"], [2020], [[1.0]], 1.0, [0.0], [], [], [10.0], 1e9)
        with self.assertRaises(InfeasibleCampaignError):
            solve_cvar_campaign(prob_scaled)

        # Near-boundary cap infeasibilities (1e-9 and 1e-14 below 1.0) must raise cleanly.
        for eps in (1e-9, 1e-14):
            prob_cap = CampaignProblem(["a"], [2020], [[1.0]], 1.0, [1.0 - eps], [], [], [0.0], 0.0)
            with self.assertRaises(InfeasibleCampaignError):
                solve_cvar_campaign(prob_cap)

        # Near-boundary budget infeasibility must raise cleanly.
        for eps in (1e-5, 1e-9):
            prob_near = CampaignProblem(["a"], [2020], [[1.0]], 1.0, [1.0], [], [], [10.0], 10.0 - eps)
            with self.assertRaises(InfeasibleCampaignError):
                solve_cvar_campaign(prob_near)

        # Cross-constraint infeasibility at 1e-11 must raise; if any microscopic 1e-14 case slips
        # inside solver float tolerance, it must never be marked certified or report certified_subopt_le=0.
        prob_cross_reject = CampaignProblem(
            ["a", "b"], [2020], [[1.0, 2.0]], 1.0, [1.0, 1.0], [[1.0, 0.0]], [0.5], [1.0, 0.0], 0.5 - 1e-11
        )
        with self.assertRaises(InfeasibleCampaignError):
            solve_cvar_campaign(prob_cross_reject)

        prob_cross_micro = CampaignProblem(
            ["a", "b"], [2020], [[1.0, 2.0]], 1.0, [1.0, 1.0], [[1.0, 0.0]], [0.5], [1.0, 0.0], 0.5 - 1e-14
        )
        try:
            sol_micro = solve_cvar_campaign(prob_cross_micro)
        except InfeasibleCampaignError:
            pass
        else:
            self.assertFalse(sol_micro.certificate.certified)
            self.assertEqual(sol_micro.certificate.certification_status, "uncertified-numerical-tolerance")
            self.assertIsNone(sol_micro.certificate.certified_subopt_le)

        # Binary float rounding of 0.1 + 0.9 == 1.0 in float64 must NOT hide the exact
        # rational excess 1/36028797018963968 > 0 or falsely mark the solution certified.
        prob_float_sum = CampaignProblem(
            ["a", "b"], [2020], [[1.0, 1.0]], 1.0, [0.1, 0.9], [[1.0, 0.0], [0.0, 1.0]], [0.1, 0.9], [0.0, 0.0], 0.0
        )
        try:
            sol_float_sum = solve_cvar_campaign(prob_float_sum)
        except InfeasibleCampaignError:
            pass
        else:
            exact_excess = sum(Fraction(v) for v in sol_float_sum.weights.values()) - Fraction(1)
            self.assertGreater(exact_excess, Fraction(0))
            self.assertGreater(sol_float_sum.certificate.primal_max_eq_violation, 0.0)
            self.assertGreaterEqual(
                Fraction(sol_float_sum.certificate.primal_max_eq_violation),
                abs(exact_excess),
            )
            self.assertFalse(sol_float_sum.certificate.certified)
            self.assertEqual(sol_float_sum.certificate.certification_status, "uncertified-numerical-tolerance")
            self.assertIsNone(sol_float_sum.certificate.certified_subopt_le)

    def test_screening_tolerance_validation_and_approximate_certificate(self) -> None:
        prob = CampaignProblem(["a", "b"], [2020, 2021], [[2.0, 0.0], [0.0, 1.0]], 0.5, [1.0, 1.0], [], [], [0.0, 0.0], 0.0)
        sol_full = solve_cvar_campaign(prob, use_screening=False)
        sol_exact = solve_cvar_campaign(prob, use_screening=True)
        self.assertTrue(sol_exact.screening_exact)
        self.assertAlmostEqual(sol_exact.cvar, sol_full.cvar, places=9)

        # Positive screen_tol that stops early must NOT claim screening_exact=True or a 0.0 full-problem bound.
        sol_approx = solve_cvar_campaign(prob, use_screening=True, initial_scenarios=1, screen_tol=2.0)
        self.assertFalse(sol_approx.screening_exact)
        self.assertEqual(sol_approx.certificate.objective_value, sol_approx.cvar)
        self.assertTrue(sol_approx.certificate.certified)
        self.assertIsNotNone(sol_approx.certificate.certified_subopt_le)
        self.assertGreaterEqual(sol_approx.certificate.certified_subopt_le, sol_approx.cvar - sol_full.cvar)
        self.assertGreaterEqual(sol_approx.certificate.subopt_bound(1.0), sol_approx.cvar - sol_full.cvar)

        for bad_l1 in (-1e-4, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                sol_approx.certificate.subopt_bound(bad_l1)

        for bad_tol in (-1e-4, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                solve_cvar_campaign(prob, screen_tol=bad_tol)

    def test_synthetic_parquet_years_missingness_exclusion_and_strict_constraints(self) -> None:
        import pyarrow as pa
        import pyarrow.parquet as pq

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "years.parquet"
            rows = []
            for yr in (2020, 2021, 2022):
                rows.append({"h3": "840000000000001", "year": yr, "month": 7, "lst_day_k": 295.0, "lst_night_k": 265.0})
                rows.append({"h3": "840000000000002", "year": yr, "month": 7, "lst_day_k": 290.0 if yr != 2021 else None, "lst_night_k": 260.0})
                rows.append({"h3": "840000000000003", "year": yr, "month": 7, "lst_day_k": 296.0, "lst_night_k": 264.0})
            pq.write_table(pa.Table.from_pylist(rows), p)

            cands = [
                {"h3": "840000000000001", "observations": {"access_min_median": 30.0}},
                {"h3": "840000000000002", "observations": {"access_min_median": 20.0}},
                {"h3": "840000000000003", "observations": {"access_min_median": 40.0}},
            ]
            prob, excluded = build_campaign_problem_from_years(
                cands, p, month=7, thermal_band_k=(262.0, 298.0), alpha=0.34, max_weight_per_site=1.0
            )
            self.assertEqual(prob.candidate_ids, ["840000000000001:m7", "840000000000003:m7"])
            self.assertEqual(excluded, [{"h3": "840000000000002", "reason": "missing-year-2021-lst"}])
            sol = solve_cvar_campaign(prob)
            self.assertAlmostEqual(sum(sol.weights.values()), 1.0, places=9)

            # Infeasible explicit budget must be preserved and raise InfeasibleCampaignError
            low_budget_prob, _ = build_campaign_problem_from_years(
                cands, p, month=7, thermal_band_k=(262.0, 298.0), alpha=0.34, max_weight_per_site=1.0, budget=5.0
            )
            self.assertEqual(low_budget_prob.budget, 5.0)
            with self.assertRaises(InfeasibleCampaignError):
                solve_cvar_campaign(low_budget_prob)

            # Infeasible explicit max_weight_per_site must be preserved and raise InfeasibleCampaignError
            tight_cap_prob, _ = build_campaign_problem_from_years(
                cands, p, month=7, thermal_band_k=(262.0, 298.0), alpha=0.34, max_weight_per_site=0.2, budget=100.0
            )
            self.assertEqual(tight_cap_prob.hi, (0.2, 0.2))
            with self.assertRaises(InfeasibleCampaignError):
                solve_cvar_campaign(tight_cap_prob)

            # Missing expected year across all candidates must not shrink T silently
            with self.assertRaises(InfeasibleCampaignError):
                build_campaign_problem_from_years(
                    cands,
                    p,
                    month=7,
                    thermal_band_k=(262.0, 298.0),
                    expected_years=(2020, 2021, 2022, 2023),
                )

            # Missing thermal band and target thermal fields must raise ValueError
            with self.assertRaises(ValueError):
                build_campaign_problem_from_years(cands, p, month=7)


def _find_real_data_paths() -> tuple[Path, Path] | None:
    """Locate assembled #168 outputs and cells-r4-monthly-years.parquet cleanly.

    Reads optional `COSMIC_ASSEMBLED_DIR` and `COSMIC_MONTHLY_YEARS_PATH`
    environment variables first, falling back to `data/snapshots/_derived/`.
    """
    here = Path(__file__).resolve()
    env_asm = os.environ.get("COSMIC_ASSEMBLED_DIR")
    env_years = os.environ.get("COSMIC_MONTHLY_YEARS_PATH")

    years_path: Path | None = Path(env_years) if env_years else None
    if years_path is None:
        for parent in here.parents:
            cand = parent / "data" / "snapshots" / "_derived" / "cells-r4-monthly-years.parquet"
            if cand.exists():
                years_path = cand
                break
    if years_path is None or not years_path.exists():
        return None

    asm_candidates: list[Path] = []
    if env_asm:
        asm_candidates.append(Path(env_asm))
    for parent in here.parents:
        asm_candidates.append(parent / "data" / "snapshots" / "_derived" / "assembled")
    for asm in asm_candidates:
        if (asm / "earth-features-r4.parquet").exists() and (asm / "planetary-targets.parquet").exists():
            return asm, years_path
    return None


class RealDataIntegrationTests(unittest.TestCase):
    def test_real_planetary_pareto_and_multiyear_cvar(self) -> None:
        paths = _find_real_data_paths()
        if paths is None:
            self.skipTest("Local real assembled parquets / monthly-years not present")
        assembled_dir, years_path = paths

        mars_res = rank_earth_for_target(
            assembled_dir,
            "mars-landing-perseverance",
            limits={"slope": 15.0, "access": 600.0},
            passthrough_columns=("access_min_median", "barren_pct", "slope_mean_deg"),
        )
        self.assertGreater(mars_res["counts"]["comparable"], 50000)
        self.assertGreater(mars_res["counts"]["layers"], 10)
        mars_l1 = [c for c in mars_res["comparable"] if c["paretoLayer"] == 1]
        self.assertGreaterEqual(len(mars_l1), 3)
        for a in mars_l1:
            va = tuple(a["gaps"].values())
            for b in mars_l1:
                self.assertFalse(_dominates(va, tuple(b["gaps"].values())))

        cands = select_diverse_frontier_candidates(mars_res, max_candidates=20)
        prob, _ = build_campaign_problem_from_years(
            cands,
            years_path,
            month=7,
            thermal_band_k=(245.0, 305.0),
            expected_years=range(2014, 2024),
            alpha=0.2,
            max_weight_per_site=0.5,
            coverage_rules=[("barren_pct", 50.0, 0.3, ">=")],
        )
        sol_scr = solve_cvar_campaign(prob, use_screening=True, initial_scenarios=2)
        sol_full = solve_cvar_campaign(prob, use_screening=False)
        self.assertAlmostEqual(sol_scr.cvar, sol_full.cvar, places=6)
        self.assertTrue(sol_scr.screening_exact)
        self.assertLessEqual(
            sol_scr.certificate.certified_subopt_le
            if sol_scr.certificate.certified
            else sol_scr.certificate.numerical_subopt_estimate,
            1e-6,
        )
        self.assertAlmostEqual(sum(sol_scr.weights.values()), 1.0, places=8)

        moon_res = rank_earth_for_target(
            assembled_dir,
            "moon-feature-shackleton",
            limits={"slope": 20.0},
            passthrough_columns=("access_min_median", "permafrost_pct", "slope_mean_deg"),
        )
        self.assertGreater(moon_res["counts"]["excludedUnknown"], 50000)
        self.assertGreater(moon_res["counts"]["comparable"], 5000)
        moon_cands = select_diverse_frontier_candidates(moon_res, max_candidates=16)
        moon_prob, _ = build_campaign_problem_from_years(
            moon_cands,
            years_path,
            month=1,
            thermal_band_k=(230.0, 275.0),
            expected_years=range(2014, 2024),
            alpha=0.2,
            max_weight_per_site=0.5,
        )
        moon_sol = solve_cvar_campaign(moon_prob, use_screening=True)
        self.assertTrue(moon_sol.screening_exact)
        self.assertLessEqual(
            moon_sol.certificate.certified_subopt_le
            if moon_sol.certificate.certified
            else moon_sol.certificate.numerical_subopt_estimate,
            1e-6,
        )
        self.assertAlmostEqual(sum(moon_sol.weights.values()), 1.0, places=8)


if __name__ == "__main__":
    unittest.main()
