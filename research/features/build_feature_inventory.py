#!/usr/bin/env python3
"""Builds research/features/feature_dataset_inventory.csv (issue #33).

One row per (feature, dataset, side). For every feature in
landing_site_features.csv it lists which registry rows (data/catalog/*.yaml)
supply the target-body side (Moon/Mars) and the Earth side, with the role each
dataset plays, and copies the registry's own independenceGroup, licence and
coverage so the gaps are visible in one table. Registry ids are asserted to
exist; every feature must appear in MAP (an empty list is an explicit "nothing
in the registry", never an omission).

Roles:
  primary        the dataset the feature is computed from
  secondary      an alternative / cross-check source for the same quantity
  derived-input  an input to a computed quantity (e.g. DEM for horizon/shadow)
  context        display or interpretation only; not a measurement of the feature
Columns copied from the registry are NOT re-probed here; their truth is the
registry row and its probe log (data/snapshots/registry-probes/).
Run: python3 research/features/build_feature_inventory.py
"""
import collections
import csv
import pathlib

import yaml

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CATALOG = ROOT / "data" / "catalog"

T, E = "target", "earth"
P, S, D, C = "primary", "secondary", "derived-input", "context"
DEMS_GLOBAL = [("nasadem-hgt", E, P, "60N-56S only; mixed lineage: SRTM radar void-filled with ASTER GDEM / AW3D30, ICESat control; NUM layer gives per-pixel source (#7)"),
               ("copernicus-dem-glo30", E, P, "")]
DEMS_POLAR = [("arcticdem", E, S, "polar only (>60N)"), ("rema", E, S, "Antarctica only")]

MAP = {
    # ---------------------------------------------------------------- terrain
    "slope_2_5km": [("mola-megdr", T, P, ""), ("mola-hrsc-blended-dem", T, S, "")] + DEMS_GLOBAL + [("aster-gdem-v3", E, S, "")],
    "slope_200_500m": [("mola-megdr", T, P, "~463 m posting: at the limit of the baseline"), ("ctx-dtms-usgs-stac", T, P, "local DTMs only"),
                       ("mola-hrsc-blended-dem", T, S, "")] + DEMS_GLOBAL,
    "slope_20_40m": [("ctx-dtms-usgs-stac", T, P, ""), ("hirise-dtms-usgs-stac", T, S, "")] + DEMS_GLOBAL + DEMS_POLAR,
    "slope_5m": [("hirise-dtms-usgs-stac", T, P, "")] + [("arcticdem", E, P, "2 m strips, >60N only"), ("rema", E, P, "2 m strips, Antarctica only")],
    "slope_100m": [("lola-south-pole-ldem-2023", T, P, ""), ("kaguya-tc-dtm-southpolar", T, S, "independent optical-stereo cross-check"),
                   ("lola-gdr", T, S, "")] + DEMS_GLOBAL + DEMS_POLAR,
    "slope_2km_eva": [("lola-south-pole-ldem-2023", T, P, ""), ("lola-gdr", T, S, "")] + DEMS_GLOBAL,
    "slope_trav_mean": [("hirise-dtms-usgs-stac", T, P, "Mars"), ("lola-south-pole-ldem-2023", T, P, "Moon")] + DEMS_GLOBAL + DEMS_POLAR,
    "rough_rms_lola": [("lola-south-pole-ldem-2023", T, P, "ROUGH products"), ("lola-shots-usgs-stac", T, S, "per-shot roughness")]
                      + DEMS_GLOBAL + [("arcticdem", E, S, "2 m: allows matching LOLA baselines in the Arctic")],
    "relief_ellipse": [("mola-megdr", T, P, "Mars"), ("lola-gdr", T, P, "Moon")] + DEMS_GLOBAL,
    "elev_areoid": [("mola-megdr", T, P, "")],
    "lat_abs": [],
    # ------------------------------------------------------- rocks / surface
    "rock_cfa": [("tes-mgs", T, P, "TES rock abundance (Nowicki & Christensen)"), ("hirise-dtms-usgs-stac", T, C, "orthoimages for counts")],
    "rock_abund_div": [("diviner-l4", T, P, "")],
    "boulder_density_nac": [("lroc-nac-boulders-watkins", T, P, "Moon: NAC boulder database"), ("lroc-wac-global", T, C, "")],
    "ti": [("tes-mgs", T, P, ""), ("themis-ir-controlled-mosaics", T, S, "100 m; mosaics are brightness, TI needs the derived product")]
          + [("modis-mod11c3", E, D, "day/night LST (Terra) for ATI"), ("modis-myd11c3", E, D, "day/night LST (Aqua); same MOD11 algorithm family"),
             ("modis-mcd43c3-albedo", E, D, "albedo term of ATI")],
    "albedo": [("tes-mgs", T, P, "Mars"), ("lroc-wac-global", T, P, "Moon (normalized reflectance, not bolometric)")]
              + [("modis-mcd43c3-albedo", E, P, "0.05 deg climate-modelling grid"), ("modis-mcd43a3-albedo", E, S, "500 m")],
    "dust_cover_index": [("tes-mgs", T, P, "")] + [("emit-l2b-min-v002", E, P, "dust-source mineralogy; sunlit acquisitions ~52N-52S, not wall-to-wall (#7)"), ("modis-mod44b", E, S, "bare-ground fraction")],
    "radar_ka_backscatter": [("alos-palsar-rtc-high", E, P, "L-band, not Ka")],
    "cpr_minirf": [("minirf-pds", T, P, "")] + [("alos-palsar-rtc-high", E, P, "linear polarization only")],
    "regolith_thick": [("soilgrids", E, P, "modelled depth to bedrock")],
    # ------------------------------------------------------------ environment
    "wind_h_edl": [("merra2-m2t1nxslv", E, P, "hourly 10 m / 50 m wind"), ("merra2-m2tmnxslv", E, S, "monthly means")],
    "wind_v_edl": [],
    "cdod_ann": [("mars-dust-climatology-lmd", T, P, ""), ("mcs-mro", T, S, "MCS dust profiles feed the climatology: not independent of it")]
                + [("merra2-m2tmnxaer", E, P, "DUEXTTAU")],
    "cdod_storm_freq": [("mars-dust-climatology-lmd", T, P, "")] + [("merra2-m2tmnxaer", E, P, ""), ("eonet-v3-events", E, S, "dustHaze events; event catalogue, not a field")],
    "tsurf_max": [("diviner-l4", T, P, "Moon"), ("tes-mgs", T, P, "Mars"), ("themis-ir-controlled-mosaics", T, S, ""), ("insight-weather-archive", T, C, "single site, air not surface")]
                 + [("modis-mod11c1-daily", E, P, "observed daily clear-sky extremes (#7: monthly LST is an average)"),
                    ("modis-mod21c3", E, S, "TES-algorithm LST; same sensor as MOD11, different retrieval"),
                    ("merra2-m2t1nxslv", E, S, "reanalysis TS: independent of MODIS (all-sky)")],
    "tsurf_min": [("diviner-l4", T, P, "Moon"), ("tes-mgs", T, P, "Mars")]
                 + [("modis-mod11c1-daily", E, P, "observed daily clear-sky extremes"), ("merra2-m2t1nxslv", E, S, "reanalysis TS")],
    "tsurf_range": [("diviner-l4", T, P, "Moon"), ("tes-mgs", T, P, "Mars")]
                   + [("modis-mod11c1-daily", E, P, "day minus night from the same day"), ("modis-myd11c3", E, S, "Aqua 01:30/13:30 overpass, monthly"),
                      ("merra2-m2t1nxslv", E, S, "hourly TS gives the full diurnal cycle")],
    "tsurf_ann_max_psr": [("diviner-l4", T, P, "Polar Resource Product")],
    # ---------------------------------------------------- illumination / comms
    "illum_frac_avg": [("lola-polar-illumination", T, P, "")] + [(d, E, D, "horizon for computed solar geometry") for d in ("copernicus-dem-glo30", "arcticdem", "rema")],
    "sun_elev_min": [("lola-polar-illumination", T, P, "")] + [(d, E, D, "horizon for computed solar geometry") for d in ("copernicus-dem-glo30", "arcticdem", "rema")],
    "earth_vis_frac": [("lola-south-pole-ldem-2023", T, D, "horizon model input")] + [("copernicus-dem-glo30", E, D, "terrain masking only")],
    "psr_frac_2km": [("lola-south-pole-ldem-2023", T, P, "LPSR layer")] + [(d, E, D, "topographic shadow computed from DEM") for d in ("copernicus-dem-glo30", "arcticdem", "rema")],
    "psr_dist_km": [("lola-south-pole-ldem-2023", T, P, "LPSR layer")] + [(d, E, D, "") for d in ("copernicus-dem-glo30", "arcticdem", "rema")],
    # --------------------------------------------------------------- volatiles
    "ice_stab_depth": [("diviner-l4", T, P, "Moon PRP"), ("swim-mars-ice", T, P, "Mars")]
                      + [("esa-cci-permafrost-extent-nh", E, P, "permafrost probability, NOT ice-table depth (#7)"),
                         ("esa-cci-permafrost-extent-antarctica", E, P, "same caveat"), ("nsidc-ggd318-permafrost", E, S, "ground-ice content class, not depth")],
    "h_wt_neutron": [("lend", T, P, "Moon"), ("ody-grs-pds", T, P, "Mars (GRS suite incl. neutron spectrometer)"), ("lp-grs-pds", T, S, "Moon elemental context")]
                    + [("nsidc-ggd318-permafrost", E, P, "ground-ice content class"), ("smap-spl3smp-e", E, S, "top ~5 cm soil moisture only")],
    "lya_offon": [("lamp", T, P, "")],
    "ice_consistency_swim": [("swim-mars-ice", T, P, "")] + [("nsidc-ggd318-permafrost", E, P, ""), ("esa-cci-permafrost-extent-nh", E, S, "")],
    # ------------------------------------------------------------- composition
    "feo_wt": [("kaguya-mi-59mpp", T, P, "UV-VIS Lucey-method input"), ("lp-grs-pds", T, S, "GRS Fe, ~100s km")]
              + [("aster-ged-ag100", E, P, "TIR emissivity mafic proxy"), ("glim-0p5deg", E, S, "lithology class")],
    "tio2_wt": [("kaguya-mi-59mpp", T, P, ""), ("lroc-wac-global", T, C, "")],
    "mafic_bd_1um": [("m3-pds", T, P, "Moon"), ("crism-mro", T, P, "Mars: OLINDEX3 / LCPINDEX2 / HCPINDEX2")] + [("emit-l2b-min-v002", E, P, "~52N-52S sunlit acquisitions; selected-mineral band depths (#7)")],
    "oh_3um": [("m3-pds", T, P, "")],
    "cf_position": [("diviner-l4", T, P, "")] + [("aster-ged-ag100", E, P, "5-band emissivity: not a spectrum (#7)")],
    "tes_mineral_frac": [("tes-mgs", T, P, "")] + [("aster-ged-ag100", E, P, "5 bands cannot be unmixed like TES (#7)")],
    "crism_hydration": [("crism-mro", T, P, "BD1900_2")] + [("emit-l2b-min-v002", E, P, "selected-mineral feature depth, not a fixed index (#7); ~52N-52S")],
    "crism_fe_mg_smectite": [("crism-mro", T, P, "D2300")] + [("emit-l2b-min-v002", E, P, "selected-mineral feature depth, not a fixed index (#7); ~52N-52S")],
    "crism_al_oh": [("crism-mro", T, P, "BD2210_2")] + [("emit-l2b-min-v002", E, P, "selected-mineral feature depth, not a fixed index (#7); ~52N-52S")],
    "crism_sulfate": [("crism-mro", T, P, "SINDEX2")] + [("emit-l2b-min-v002", E, P, "selected-mineral feature depth, not a fixed index (#7); ~52N-52S")],
    "crism_carbonate": [("crism-mro", T, P, "MIN2295_2480; MIN2345_2537; BD2500_2")] + [("emit-l2b-min-v002", E, P, "selected-mineral feature depth, not a fixed index (#7); ~52N-52S")],
    "grs_th_k": [("lp-grs-pds", T, P, "Moon"), ("ody-grs-pds", T, P, "Mars")],
    "geo_unit": [("unified-geologic-map-moon", T, P, "Moon 1:5M"), ("mars-geologic-map-sim3292", T, P, "Mars 1:20M")] + [("glim-0p5deg", E, P, "")],
    "crater_density": [("robbins-moon-craters", T, P, ""), ("robbins-mars-craters", T, P, "")] + [("earth-impact-database", E, P, "point catalogue; source currently unreachable")],
    # -------------------------------------------------------------- subsurface
    "pit_cave_presence": [("lroc-pits-atlas", T, P, "Moon"), ("mgc3-mars-caves", T, P, "Mars")],
    # ---------------------------------------------------- permanent mismatches
    "gravity": [],
    "psurf": [("insight-weather-archive", T, C, "Mars pressure record; never scored")],
    "radiation_dose": [],
}

COLS = ["feature_id", "family", "dimension", "earth_match", "side", "dataset_id", "role", "dataset_bodies",
        "independence_group", "licence_id", "licence_verified", "registry_status", "coverage_spatial",
        "resolution", "note"]


def main() -> int:
    feats = list(csv.DictReader((HERE / "landing_site_features.csv").open()))
    fids = [f["feature_id"] for f in feats]
    missing = sorted(set(fids) - set(MAP)); extra = sorted(set(MAP) - set(fids))
    assert not missing and not extra, f"MAP out of sync: missing={missing} extra={extra}"
    reg = {}
    for p in sorted(CATALOG.glob("*.yaml")):
        if p.name == "dataset.template.yaml":
            continue
        reg[p.stem] = yaml.safe_load(p.read_text())
    rows = []
    for f in feats:
        ents = MAP[f["feature_id"]]
        if not ents:
            rows.append({**{k: f[k] for k in ("feature_id", "family", "dimension", "earth_match")},
                         "side": "-", "dataset_id": "", "role": "", "note": "no registry dataset (see feature notes)"})
        for did, side, role, note in ents:
            assert did in reg, f"{f['feature_id']}: unknown registry id {did}"
            r = reg[did]; lic = r.get("license") or {}; cov = r.get("coverage") or {}
            want = "earth" if side == E else None
            assert (want == "earth") == ("earth" in r["bodies"]), f"{f['feature_id']}: {did} side {side} vs bodies {r['bodies']}"
            rows.append({"feature_id": f["feature_id"], "family": f["family"], "dimension": f["dimension"],
                         "earth_match": f["earth_match"], "side": side, "dataset_id": did, "role": role,
                         "dataset_bodies": ";".join(r["bodies"]), "independence_group": r.get("independenceGroup"),
                         "licence_id": lic.get("id"), "licence_verified": lic.get("verified"),
                         "registry_status": r.get("status"), "coverage_spatial": cov.get("spatial"),
                         "resolution": cov.get("resolution"), "note": note})
    out = HERE / "feature_dataset_inventory.csv"
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, restval=""); w.writeheader(); w.writerows(rows)
    # per-feature summary -> feature_inventory_summary.csv (doc 08 §6 quotes the counts).
    # Independence groups count measured roles only (primary/secondary): derived inputs
    # and context layers are not independent evidence of the feature.
    srows = []
    for f in feats:
        ents = MAP[f["feature_id"]]
        def ids(side, roles): return sorted({d for d, s_, ro, _ in ents if s_ == side and ro in roles})
        tm, em, ed = ids(T, (P, S)), ids(E, (P, S)), ids(E, (D,))
        srows.append({"feature_id": f["feature_id"], "earth_match": f["earth_match"],
                      "target_datasets": ";".join(tm + [f"{d}(derived)" for d in ids(T, (D,))]),
                      "target_groups": len({reg[d]["independenceGroup"] for d in tm}),
                      "earth_datasets": ";".join(em), "earth_groups": len({reg[d]["independenceGroup"] for d in em}),
                      "earth_derived_inputs": ";".join(ed),
                      "unverified_licences": ";".join(sorted({d for d, *_ in ents if not (reg[d].get("license") or {}).get("verified")}))})
    sout = HERE / "feature_inventory_summary.csv"
    with sout.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(srows[0])); w.writeheader(); w.writerows(srows)
    scored = [r for r in srows if r["earth_match"] != "mismatch"]
    def bucket(r):
        if r["earth_groups"] >= 2: return ">=2 groups"
        if r["earth_groups"] == 1: return "1 group"
        return "computed from derived inputs only" if r["earth_derived_inputs"] else "no Earth dataset"
    cnt = collections.Counter(bucket(r) for r in scored)
    used = sorted({d for ents in MAP.values() for d, *_ in ents})
    print(f"{len(feats)} features, {len(rows)} inventory rows -> {out.name}, {sout.name}; {len(used)}/{len(reg)} registry rows used")
    print(f"Earth side of {len(scored)} non-mismatch features: " + ", ".join(f"{k} {v}" for k, v in sorted(cnt.items())))
    for k in ("no Earth dataset", "computed from derived inputs only"):
        print(f"  {k}:", ", ".join(r["feature_id"] for r in scored if bucket(r) == k))
    print("  no target dataset:", ", ".join(r["feature_id"] for r in srows if not r["target_datasets"]))
    print("unused registry rows:", ", ".join(sorted(set(reg) - set(used))))
    print("datasets with unverified licence in use:", ", ".join(sorted({d for r in srows for d in r["unverified_licences"].split(";") if d})))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
