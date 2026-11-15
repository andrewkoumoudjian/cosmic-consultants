"""L4 publish: the files the app loads (DATA-PIPELINE.md section 5, L4).

    cells.bin + cells.json   L1 + L2 columns the UI uses, Float32 column arrays
                             (NaN = null), plus names, units, null reasons, h3 order
    monthly/<column>.bin     one L1m column, Float32 [cell * 12 + (month - 1)]
    objectives.json, trait-map.json, campaigns.json   L3 tables as JSON
    build-manifest.json      sha256 of every file written and of every input

Deterministic: hexagons in sorted h3 order, JSON with sorted keys, no clocks
in any file, so the same inputs give byte-identical outputs (and hashes).
Values are copied, never computed: no verdicts, gaps or scores live in L4.
"""
from __future__ import annotations

import glob
import hashlib
import json
import math
import sys
from array import array
from pathlib import Path

from .tables import Tables, reasons_of

# L1 + L2 columns published to L4 (DATA-PIPELINE section 5 + #168 columns.yaml active columns).
CELL_COLUMNS = {
    "lat": "deg", "lon": "deg", "land_pct_mean": "%",
    "lst_day_max_k": "K", "lst_night_min_k": "K", "lst_diurnal_range_mean_k": "K",
    "barren_pct": "%", "snow_ice_pct": "%", "water_pct": "%", "permafrost_pct": "%",
    "elev_mean_m": "m", "elev_min_m": "m", "elev_max_m": "m",
    "slope_mean_deg": "deg", "slope_frac_lt5": "0-1", "slope_frac_lt15": "0-1", "slope_frac_gt30": "0-1",
    "sun_noon_elev_max_deg": "deg", "sun_noon_elev_min_deg": "deg", "polar_night": "0/1", "polar_day": "0/1",
    "dust_aod_mean": "unitless", "dust_aod_max": "unitless",
    "albedo_ws_sw_mean": "0-1", "albedo_bs_sw_mean": "0-1",
    "regolith_thick_m": "m", "soil_thick_m": "m", "sediment_thick_m": "m",
    "avg_soil_sed_thick_m": "m", "hillslope_frac_mean": "0-1",
    "wind_speed_mean": "m/s",
    "emit_n_observed": "count",
    "emit_min_hydration_share": "0-1", "emit_min_hydration_bd_med": "0-1",
    "emit_min_fe_mg_smectite_share": "0-1", "emit_min_fe_mg_smectite_bd_med": "0-1",
    "emit_min_al_oh_share": "0-1", "emit_min_al_oh_bd_med": "0-1",
    "emit_min_sulfate_share": "0-1", "emit_min_sulfate_bd_med": "0-1",
    "emit_min_carbonate_share": "0-1", "emit_min_carbonate_bd_med": "0-1",
    "emit_min_mafic_bd_1um_share": "0-1", "emit_min_mafic_bd_1um_bd_med": "0-1",
    "emit_min_dust_proxy_share": "0-1", "emit_min_dust_proxy_bd_med": "0-1",
    "vcf_percent_tree_cover_pct_median": "%", "vcf_percent_nontree_vegetation_pct_median": "%",
    "vcf_percent_nonvegetated_pct_median": "%",
    "vcf_percent_tree_cover_pct_mean": "%", "vcf_percent_nontree_vegetation_pct_mean": "%",
    "vcf_percent_nonvegetated_pct_mean": "%",
}
CONTEXT_COLUMNS = {
    "access_min_median": "min", "access_min_p10": "min", "airport_km": "km", "protected_pct": "%",
}
MONTHLY_COLUMNS = {
    "lst_day_k": "K", "lst_night_k": "K", "lst_diurnal_k": "K",
    "aqua_lst_day_k": "K", "aqua_lst_night_k": "K", "aqua_lst_diurnal_k": "K",
    "sun_noon_elev_deg": "deg", "daylight_h": "h", "polar_day": "0/1", "polar_night": "0/1",
    "dust_aod": "unitless", "burned_pct": "%",
    "albedo_ws_sw": "0-1", "albedo_bs_sw": "0-1",
    "wind_speed": "m/s", "wind_speed_max": "m/s", "u10m_mean": "m/s", "v10m_mean": "m/s",
}
ENGINE = "planner 0.2.0"


def _f32(values: list) -> bytes:
    """Little-endian Float32, None -> NaN. Booleans become 0/1."""
    a = array("f", [math.nan if v is None else float(v) for v in values])
    if sys.byteorder != "little":
        a.byteswap()
    return a.tobytes()


def _write(path: Path, data: bytes, written: dict, root: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    written[path.relative_to(root).as_posix()] = hashlib.sha256(data).hexdigest()


def _json(obj) -> bytes:
    return (json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def _null_reasons(rows: list[dict | None], columns: list[str]) -> dict[str, dict[str, int]]:
    """Per column, how many hexagons are null for each reason code (the UI shows
    the code; the per-row reason stays in L1/L2)."""
    out: dict[str, dict[str, int]] = {}
    for c in columns:
        counts: dict[str, int] = {}
        for row in rows:
            if row is None or row.get(c) is None:
                reasons = reasons_of(row)
                code = reasons.get(c) or next((v for k, v in reasons.items() if k.endswith("*") and c.startswith(k[:-1])), None) \
                    or ("no-row-for-hexagon" if row is None else "not-in-source")
                counts[code] = counts.get(code, 0) + 1
        if counts:
            out[c] = dict(sorted(counts.items()))
    return out


def load_l3(repo: Path) -> dict[str, object]:
    import yaml  # PyYAML, pinned in pyproject

    objectives = [yaml.safe_load(Path(p).read_text(encoding="utf-8")) for p in sorted(glob.glob(str(repo / "data/objectives/*.yaml")))]
    campaigns = [yaml.safe_load(Path(p).read_text(encoding="utf-8")) for p in sorted(glob.glob(str(repo / "data/campaigns/*.yaml")))]
    trait_map = yaml.safe_load((repo / "data/requirements/trait-map.yaml").read_text(encoding="utf-8"))
    return {"objectives": objectives, "trait-map": trait_map, "campaigns": campaigns}


def publish(tables: Tables, l3: dict, out: Path, l3_inputs: list[dict] | None = None, synthetic: bool = False) -> dict:
    """Write L4 under `out` (e.g. apps/atlas/public/data/v1) and return the manifest."""
    order = tables.order()
    written: dict[str, str] = {}

    cell_rows = [tables.cells.get(h) for h in order]
    ctx_rows = [tables.context.get(h) for h in order]
    columns, blobs, offset = [], [], 0
    for table, rows, spec in (("L1", cell_rows, CELL_COLUMNS), ("L2", ctx_rows, CONTEXT_COLUMNS)):
        for name, unit in spec.items():
            blob = _f32([None if r is None else r.get(name) for r in rows])
            columns.append({"name": name, "table": table, "unit": unit, "offset": offset, "length": len(order)})
            blobs.append(blob)
            offset += len(blob)
    _write(out / "cells.bin", b"".join(blobs), written, out)
    meta = {
        "dtype": "float32-le", "null": "NaN", "count": len(order), "h3": order, "columns": columns,
        "nullReasons": {**_null_reasons(cell_rows, list(CELL_COLUMNS)), **_null_reasons(ctx_rows, list(CONTEXT_COLUMNS))},
        "synthetic": synthetic,
    }
    _write(out / "cells.json", _json(meta), written, out)

    for name in MONTHLY_COLUMNS:
        values = [(tables.monthly.get((h, m)) or {}).get(name) for h in order for m in range(1, 13)]
        _write(out / "monthly" / f"{name}.bin", _f32(values), written, out)
    _write(out / "monthly" / "monthly.json", _json({"dtype": "float32-le", "null": "NaN", "layout": "cell * 12 + (month - 1)",
                                                      "count": len(order), "columns": MONTHLY_COLUMNS, "synthetic": synthetic}), written, out)

    for name, value in l3.items():
        _write(out / f"{name}.json", _json(value), written, out)

    manifest = {
        "engine": ENGINE,
        "synthetic": synthetic,
        "files": dict(sorted(written.items())),
        "inputs": sorted(tables.inputs + (l3_inputs or []), key=lambda i: i["path"]),
    }
    data = _json(manifest)
    (out / "build-manifest.json").write_bytes(data)
    manifest["sha256"] = hashlib.sha256(data).hexdigest()
    return manifest


def read_column(out: Path, name: str) -> list[float | None]:
    """Read one cells.bin column back (tests and spot checks)."""
    meta = json.loads((out / "cells.json").read_text(encoding="utf-8"))
    col = next(c for c in meta["columns"] if c["name"] == name)
    raw = (out / "cells.bin").read_bytes()[col["offset"]: col["offset"] + 4 * col["length"]]
    a = array("f")
    a.frombytes(raw)
    if sys.byteorder != "little":
        a.byteswap()
    return [None if math.isnan(v) else v for v in a]
