"""Multi-objective Pareto site-selection model conforming to Lean S9 (Analog.ParetoLayers).

Pure Python stdlib implementation (+ lazy `pyarrow` for `.parquet` table I/O).

Guarantees enforced from `proofs/Analog/ParetoLayers.lean` and `docs/decisions/ADR-0005`:
- No single combined scalar "analogy score" for any site (S9f, ADR-0005 D3).
- Unknown / missing observations never receive a fabricated zero gap: any site
  missing an active scored dimension is excluded from `comparable` and receives
  `paretoLayer = None` with its missing reason codes (S9e).
- Each Pareto layer is a pairwise incomparable antichain (S9a); strict dominance
  puts the dominator in a strictly earlier layer (S9b); identical gap vectors
  receive identical layers (S9c); DP recurrence matches iterative peeling (S9g).
- Permanent non-Earth-testable physics (`gravity`, `pressureRegime`, `radiation`)
  are reported separately in `notTestableOnEarth` and never mixed into gap vectors.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .logistics import LIMIT_COLUMNS
from .tables import reason_for


PERMANENT_MISMATCHES: dict[str, list[dict[str, str]]] = {
    "moon": [
        {
            "mismatch": "gravity",
            "why": "Surface operations and mechanics depend on lunar gravity (~0.17 g), which Earth sites cannot replicate.",
        },
        {
            "mismatch": "pressureRegime",
            "why": "Lunar hard vacuum alters thermal transport, dust adhesion, and plume-regolith interaction.",
        },
        {
            "mismatch": "radiation",
            "why": "Unshielded solar and cosmic radiation on the Moon is blocked by Earth's atmosphere and magnetosphere.",
        },
    ],
    "mars": [
        {
            "mismatch": "gravity",
            "why": "Rover mobility and EVA kinematics depend on Mars gravity (~0.38 g).",
        },
        {
            "mismatch": "pressureRegime",
            "why": "Thin CO2 surface pressure (~6 mbar) changes convective cooling, dust lifting, and suit pressure.",
        },
        {
            "mismatch": "radiation",
            "why": "Mars receives higher ionizing radiation flux than Earth sea-level/mid-elevation field sites.",
        },
    ],
}


@dataclass(frozen=True)
class AxisSpec:
    """One non-negative physical mismatch axis mapped from an Earth feature column.

    Modes:
    - `target_abs`: `|x - target_value|`
    - `target_min`: `max(0, target_value - x)`
    - `target_max`: `max(0, x - target_value)`
    - `band`: `0` inside `[lo, hi]` (or `< hi` if `hi_strict`), else positive boundary gap
    - `direct`: `max(0, x)` (non-negative instability / hazard magnitude)
    """

    name: str
    column: str
    unit: str
    table: str = "L1"
    mode: str = "target_abs"
    target_value: float | None = None
    lo: float | None = None
    hi: float | None = None
    hi_strict: bool = False

    def gap(self, row: dict | None) -> float | None:
        if row is None:
            return None
        raw = row.get(self.column)
        if raw is None or isinstance(raw, bool):
            return None
        val = float(raw)
        if not math.isfinite(val):
            return None

        if self.mode == "target_abs":
            if self.target_value is None or not math.isfinite(self.target_value):
                raise ValueError(f"Axis {self.name!r} mode 'target_abs' requires finite target_value")
            return abs(val - float(self.target_value))
        if self.mode == "target_min":
            if self.target_value is None or not math.isfinite(self.target_value):
                raise ValueError(f"Axis {self.name!r} mode 'target_min' requires finite target_value")
            return max(0.0, float(self.target_value) - val)
        if self.mode == "target_max":
            if self.target_value is None or not math.isfinite(self.target_value):
                raise ValueError(f"Axis {self.name!r} mode 'target_max' requires finite target_value")
            return max(0.0, val - float(self.target_value))
        if self.mode == "band":
            if self.lo is None or self.hi is None or self.lo > self.hi:
                raise ValueError(f"Axis {self.name!r} mode 'band' requires ordered finite lo/hi")
            if val < self.lo:
                return float(self.lo) - val
            if val > self.hi or (self.hi_strict and val == self.hi):
                return val - float(self.hi)
            return 0.0
        if self.mode == "direct":
            return max(0.0, val)
        raise ValueError(f"Unsupported axis mode: {self.mode!r}")

    def to_metadata(self) -> dict:
        return {
            "name": self.name,
            "column": self.column,
            "unit": self.unit,
            "table": self.table,
            "mode": self.mode,
            "targetValue": self.target_value,
            "lo": self.lo,
            "hi": self.hi,
            "hiStrict": self.hi_strict,
        }


def _finite_opt(val) -> float | None:
    if val is None or isinstance(val, bool):
        return None
    f = float(val)
    return f if math.isfinite(f) else None


def build_target_axes(
    target_row: dict,
    *,
    include_stability: bool = True,
    include_barren: bool = True,
    include_permafrost_when_psr: bool = True,
    extra_axes: Iterable[AxisSpec] = (),
) -> tuple[list[AxisSpec], list[dict[str, str]]]:
    """Build non-negative physical mismatch axes from a `planetary-targets` row.

    Only dimensions actually populated on `target_row` are added—missing planetary
    measurements are never fabricated. Returns `(axes, notTestableOnEarth)`.
    """
    axes: list[AxisSpec] = []

    slope_val = _finite_opt(target_row.get("target_slope_local_deg"))
    if slope_val is not None:
        axes.append(
            AxisSpec(
                name="slope_gap_deg",
                column="slope_mean_deg",
                unit="deg",
                table="L1",
                mode="target_abs",
                target_value=slope_val,
            )
        )

    diurnal_val = _finite_opt(target_row.get("target_tsurf_range_k"))
    if diurnal_val is not None:
        axes.append(
            AxisSpec(
                name="diurnal_range_gap_k",
                column="lst_diurnal_range_mean_k",
                unit="K",
                table="L1",
                mode="target_abs",
                target_value=diurnal_val,
            )
        )

    tmin_val = _finite_opt(target_row.get("target_tsurf_min_k"))
    if tmin_val is not None:
        axes.append(
            AxisSpec(
                name="thermal_cold_gap_k",
                column="lst_night_min_k",
                unit="K",
                table="L1",
                mode="target_abs",
                target_value=tmin_val,
            )
        )

    cdod_val = _finite_opt(target_row.get("mars_cdod_ann"))
    if cdod_val is not None:
        axes.append(
            AxisSpec(
                name="dust_aod_gap",
                column="dust_aod_mean",
                unit="unitless",
                table="L1",
                mode="target_abs",
                target_value=cdod_val,
            )
        )

    wind_val = _finite_opt(target_row.get("mars_wind_edl_10m_mean_ms"))
    if wind_val is not None:
        axes.append(
            AxisSpec(
                name="wind_speed_gap_ms",
                column="wind_speed_mean",
                unit="m/s",
                table="L1",
                mode="target_abs",
                target_value=wind_val,
            )
        )

    psr_frac = _finite_opt(target_row.get("moon_psr_frac_2km"))
    if include_permafrost_when_psr and psr_frac is not None and psr_frac > 0.0:
        axes.append(
            AxisSpec(
                name="permafrost_deficit_pct",
                column="permafrost_pct",
                unit="%",
                table="L1",
                mode="target_min",
                target_value=min(100.0, 100.0 * psr_frac),
            )
        )

    if include_barren:
        axes.append(
            AxisSpec(
                name="barren_deficit_pct",
                column="barren_pct",
                unit="%",
                table="L1",
                mode="target_min",
                target_value=100.0,
            )
        )

    if include_stability:
        axes.append(
            AxisSpec(
                name="night_interannual_iqr_k",
                column="lst_night_interannual_iqr_mean_k",
                unit="K",
                table="L1",
                mode="direct",
            )
        )

    axes.extend(extra_axes)
    body = str(target_row.get("body", "")).lower()
    not_testable = list(PERMANENT_MISMATCHES.get(body, []))
    return axes, not_testable


def pareto_layers(vectors: Iterable[Iterable[float]]) -> list[int]:
    """Compute exact 1-indexed Pareto layer index for each vector (`S9a`–`S9g`).

    Every coordinate must be finite (`S9e`: unknown dimensions must be excluded
    prior to layering). Identical vectors always receive the exact same layer (`S9c`).
    Uses an exact `O(U log U)` Fenwick tree for 2D and a lexicographic DP with
    monotonic layer binary search and coordinate bounding-box pruning for `d >= 3`.
    """
    raw = [tuple(float(x) for x in v) for v in vectors]
    if not raw:
        return []
    dim = len(raw[0])
    for v in raw:
        if len(v) != dim:
            raise ValueError("All loss vectors must share the same dimension")
        if not all(math.isfinite(x) for x in v):
            raise ValueError("Loss vectors passed to pareto_layers must contain only finite values (S9e)")

    unique = sorted(set(raw))
    if dim == 0:
        levels = {v: 1 for v in unique}
        return [levels[v] for v in raw]

    active_dims = [d for d in range(dim) if any(v[d] != unique[0][d] for v in unique)]
    n_act = len(active_dims)
    if n_act == 0:
        levels = {v: 1 for v in unique}
    elif n_act == 1:
        levels = {v: i + 1 for i, v in enumerate(unique)}
    elif n_act == 2:
        d = active_dims[1]
        ys = sorted({v[d] for v in unique})
        ranks = {y: i + 1 for i, y in enumerate(ys)}
        tree = [0] * (len(ys) + 1)
        levels = {}
        for v in unique:
            y = ranks[v[d]]
            j = y
            best = 0
            while j > 0:
                best = max(best, tree[j])
                j -= j & -j
            lvl = best + 1
            levels[v] = lvl
            j = y
            while j < len(tree):
                tree[j] = max(tree[j], lvl)
                j += j & -j
    else:
        # Exact S9g DP in lexicographic order accelerated by an exact branch-and-bound
        # k-d tree over the projected active axes. Each node tracks `min_box` (exact
        # coordinatewise minimum over its subtree) and `max_layer` (max assigned layer
        # among already-processed points in its subtree).
        proj = [tuple(v[d] for d in active_dims) for v in unique]
        n_pts = len(proj)
        rng_act = range(n_act)
        leaf_cap = 32

        # Flat node arrays for fast pure-Python traversal:
        # node_min[nid], node_max_layer[nid], node_left[nid], node_right[nid],
        # node_parent[nid], node_items[nid] (for leaves: list of (pt, layer))
        node_min: list[tuple[float, ...]] = []
        node_max_layer: list[int] = []
        node_left: list[int] = []
        node_right: list[int] = []
        node_parent: list[int] = []
        node_items: list[list[tuple[tuple[float, ...], int]] | None] = []
        leaf_of_idx = [0] * n_pts

        def _build(indices: list[int], depth: int, parent: int) -> int:
            nid = len(node_min)
            mins = tuple(min(proj[i][d] for i in indices) for d in rng_act)
            node_min.append(mins)
            node_max_layer.append(0)
            node_left.append(-1)
            node_right.append(-1)
            node_parent.append(parent)
            if len(indices) <= leaf_cap:
                node_items.append([])
                for idx in indices:
                    leaf_of_idx[idx] = nid
                return nid
            node_items.append(None)
            axis = depth % n_act
            indices.sort(key=lambda idx: proj[idx][axis])
            mid = len(indices) // 2
            l_id = _build(indices[:mid], depth + 1, nid)
            r_id = _build(indices[mid:], depth + 1, nid)
            node_left[nid] = l_id
            node_right[nid] = r_id
            return nid

        _build(list(range(n_pts)), 0, -1)

        def _query(pt: tuple[float, ...]) -> int:
            best = 0
            stack = [0]
            while stack:
                nid = stack.pop()
                if node_max_layer[nid] <= best:
                    continue
                nmin = node_min[nid]
                can_dom = True
                for d_idx in rng_act:
                    if nmin[d_idx] > pt[d_idx]:
                        can_dom = False
                        break
                if not can_dom:
                    continue
                items = node_items[nid]
                if items is not None:
                    for w, w_layer in items:
                        if w_layer <= best:
                            continue
                        ok = True
                        for d_idx in rng_act:
                            if w[d_idx] > pt[d_idx]:
                                ok = False
                                break
                        if ok:
                            best = w_layer
                else:
                    l_id = node_left[nid]
                    r_id = node_right[nid]
                    lm = node_max_layer[l_id]
                    rm = node_max_layer[r_id]
                    # Push lower max_layer first so higher max_layer pops first!
                    if lm <= rm:
                        if lm > best:
                            stack.append(l_id)
                        if rm > best:
                            stack.append(r_id)
                    else:
                        if rm > best:
                            stack.append(r_id)
                        if lm > best:
                            stack.append(l_id)
            return best

        levels = {}
        for idx, (orig_v, pt) in enumerate(zip(unique, proj)):
            lvl = _query(pt) + 1
            levels[orig_v] = lvl
            lid = leaf_of_idx[idx]
            node_items[lid].append((pt, lvl))
            cur = lid
            while cur != -1 and node_max_layer[cur] < lvl:
                node_max_layer[cur] = lvl
                cur = node_parent[cur]

    return [levels[v] for v in raw]


def _check_limits(row: dict, limits: dict[str, float] | None) -> tuple[bool, list[dict]]:
    """Evaluate hard limits following S7i (unknown limit value never excludes a site)."""
    if not limits:
        return True, []
    details: list[dict] = []
    passed = True
    for key in ("access", "protected", "airport", "slope"):
        if key not in limits:
            continue
        _, col, unit = LIMIT_COLUMNS[key]
        cap = float(limits[key])
        raw = row.get(col)
        if raw is None:
            details.append({"limit": key, "max": cap, "value": None, "unit": unit, "outcome": "unknown"})
        else:
            val = float(raw)
            ok = val <= cap
            if not ok:
                passed = False
            details.append(
                {"limit": key, "max": cap, "value": val, "unit": unit, "outcome": "pass" if ok else "fail"}
            )
    return passed, details


def evaluate_sites(
    rows: Iterable[dict],
    axes: list[AxisSpec],
    *,
    limits: dict[str, float] | None = None,
    target: dict | None = None,
    spread_by_key: dict[tuple[str, int], dict] | None = None,
    month: int | None = None,
    max_layers: int | None = None,
    passthrough_columns: Iterable[str] = ("access_min_median",),
) -> dict:
    """Rank sites by exact Pareto layers without any combined scalar similarity score.

    Any candidate missing one or more axis observations is isolated in
    `excludedUnknown` with `paretoLayer = None` (S9e). Hard limits reject only
    known values exceeding the cap (`S7i`). `counts['comparable']` records all
    eligible sites layered, while `counts['returned']` records the count
    remaining in `comparable` after optional `max_layers` filtering.
    """
    if not axes:
        raise ValueError("At least one comparable physical axis is required")

    passthrough = tuple(passthrough_columns)
    rows_list = sorted(rows, key=lambda r: str(r["h3"]))
    not_testable: list[dict[str, str]] = []
    if target is not None:
        not_testable = list(PERMANENT_MISMATCHES.get(str(target.get("body", "")).lower(), []))

    excluded_limits: list[dict] = []
    excluded_unknown: list[dict] = []
    comparable_items: list[dict] = []
    vectors: list[tuple[float, ...]] = []
    within_limits_count = 0

    for row in rows_list:
        h3 = str(row["h3"])
        ok, lim_details = _check_limits(row, limits)
        if not ok:
            excluded_limits.append({"h3": h3, "limits": lim_details})
            continue
        within_limits_count += 1

        spread_row = spread_by_key.get((h3, month)) if (spread_by_key is not None and month is not None) else None
        gaps: dict[str, float] = {}
        observations: dict[str, float] = {}
        missing_axes: list[str] = []
        missing_reasons: dict[str, str] = {}

        for ax in axes:
            src_row = spread_row if ax.table == "L1m_spread" else row
            g = ax.gap(src_row)
            if g is None:
                missing_axes.append(ax.name)
                missing_reasons[ax.name] = reason_for(src_row, ax.column, ax.name)
            else:
                gaps[ax.name] = g
                observations[ax.column] = float(src_row[ax.column])

        if missing_axes:
            excluded_unknown.append(
                {
                    "h3": h3,
                    "paretoLayer": None,
                    "missingAxes": missing_axes,
                    "reasons": missing_reasons,
                }
            )
            continue

        for pcol in passthrough:
            if pcol in row and pcol not in observations and row[pcol] is not None:
                fval = _finite_opt(row[pcol])
                if fval is not None:
                    observations[pcol] = fval

        vec = tuple(gaps[ax.name] for ax in axes)
        vectors.append(vec)
        comparable_items.append(
            {
                "h3": h3,
                "lat": row.get("lat"),
                "lon": row.get("lon"),
                "gaps": gaps,
                "observations": observations,
                "limits": lim_details,
                "_vec": vec,
            }
        )

    layers = pareto_layers(vectors)
    ranked: list[dict] = []
    for item, layer in zip(comparable_items, layers):
        if max_layers is not None and layer > max_layers:
            continue
        vec = item.pop("_vec")
        item["paretoLayer"] = layer
        item["_sort_key"] = (layer, vec, item["h3"])
        ranked.append(item)

    ranked.sort(key=lambda d: d.pop("_sort_key"))
    num_layers = max(layers, default=0)

    return {
        "targetId": None if target is None else target.get("target_id"),
        "body": None if target is None else target.get("body"),
        "axes": [ax.to_metadata() for ax in axes],
        "notTestableOnEarth": not_testable,
        "counts": {
            "total": len(rows_list),
            "withinLimits": within_limits_count,
            "excludedLimits": len(excluded_limits),
            "excludedUnknown": len(excluded_unknown),
            "comparable": len(comparable_items),
            "returned": len(ranked),
            "layers": num_layers,
        },
        "comparable": ranked,
        "excludedUnknown": excluded_unknown,
        "excludedLimits": excluded_limits,
    }


def select_diverse_frontier_candidates(
    evaluated: dict,
    *,
    max_candidates: int = 24,
    max_layer: int | None = None,
) -> list[dict]:
    """Select Pareto-layer candidates for campaign optimization without scoring site similarity.

    Maintains strict layer priority (Layer 1 before Layer 2, ...). Within a layer,
    includes per-axis extremal achievers first so trade-off corners (`S9f`) are never
    dropped in favor of a single arbitrary weighting, then fills remaining slots
    deterministically along lexicographic order.
    """
    if max_candidates < 1:
        raise ValueError("max_candidates must be >= 1")
    comparable = evaluated["comparable"]
    axes = [ax["name"] for ax in evaluated["axes"]]
    selected: list[dict] = []
    seen_h3: set[str] = set()

    by_layer: dict[int, list[dict]] = {}
    for item in comparable:
        layer = int(item["paretoLayer"])
        if max_layer is not None and layer > max_layer:
            continue
        by_layer.setdefault(layer, []).append(item)

    for layer in sorted(by_layer):
        bucket = by_layer[layer]
        # Preserve every axis's best trade-off representative in this layer first (S9f).
        for ax_name in axes:
            if len(selected) >= max_candidates:
                return selected
            best_in_ax = min(bucket, key=lambda d: (d["gaps"][ax_name], d["h3"]))
            if best_in_ax["h3"] not in seen_h3:
                seen_h3.add(best_in_ax["h3"])
                selected.append(best_in_ax)
        for item in bucket:
            if len(selected) >= max_candidates:
                return selected
            if item["h3"] not in seen_h3:
                seen_h3.add(item["h3"])
                selected.append(item)
    return selected


def load_assembled_targets(assembled_dir: Path) -> list[dict]:
    """Load `planetary-targets.parquet` rows from an `assembled/` directory."""
    import pyarrow.parquet as pq

    path = Path(assembled_dir) / "planetary-targets.parquet"
    return pq.read_table(path).to_pylist()


def load_earth_features(
    assembled_dir: Path,
    columns: Iterable[str] | None = None,
) -> list[dict]:
    """Load `earth-features-r4.parquet` rows (only needed columns if specified)."""
    import pyarrow.parquet as pq

    path = Path(assembled_dir) / "earth-features-r4.parquet"
    cols = list(dict.fromkeys(columns)) if columns is not None else None
    return pq.read_table(path, columns=cols).to_pylist()


def rank_earth_for_target(
    assembled_dir: Path,
    target_id: str,
    *,
    limits: dict[str, float] | None = None,
    include_stability: bool = True,
    include_barren: bool = True,
    include_permafrost_when_psr: bool = True,
    extra_axes: Iterable[AxisSpec] = (),
    max_layers: int | None = None,
    passthrough_columns: Iterable[str] = ("access_min_median",),
) -> dict:
    """Run exact S9 Pareto layer ranking over real assembled Earth + planetary tables."""
    targets = load_assembled_targets(assembled_dir)
    target = next((t for t in targets if t.get("target_id") == target_id), None)
    if target is None:
        raise ValueError(f"Unknown planetary target_id: {target_id!r}")

    axes, _ = build_target_axes(
        target,
        include_stability=include_stability,
        include_barren=include_barren,
        include_permafrost_when_psr=include_permafrost_when_psr,
        extra_axes=extra_axes,
    )
    passthrough = tuple(passthrough_columns)
    needed_cols = ["h3", "lat", "lon", "missing_reason", *(ax.column for ax in axes), *passthrough]
    if limits:
        for key in limits:
            if key in LIMIT_COLUMNS:
                needed_cols.append(LIMIT_COLUMNS[key][1])
    rows = load_earth_features(assembled_dir, columns=needed_cols)
    return evaluate_sites(
        rows,
        axes,
        limits=limits,
        target=target,
        max_layers=max_layers,
        passthrough_columns=passthrough,
    )
