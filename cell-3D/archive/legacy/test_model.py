"""Numerical/physical invariants meaningful for this scientific proxy."""
import json
from pathlib import Path
import numpy as np
from simulate import Design, Thermal, Router, Placement, legalize, splat, deposit, verify_gradients, check_legal

root = Path(__file__).resolve().parent
c = json.loads((root/"config.json").read_text(encoding="utf-8"))
c["cell_count_per_logic_module"] = 120
d = Design(c, "A_split")
t = Thermal(c)
print(verify_gradients(d, t))
rng = np.random.default_rng(55)
p, q = rng.random(512), rng.random(512)
assert np.isclose(p @ t.apply(q), q @ t.apply(p), rtol=1e-12), "Thermal reciprocity"
sp = splat(d.base_xy, d.z, c["die_mm"], t.g)
assert np.isclose(deposit(d.dynamic, sp, 512).sum(), d.dynamic.sum(), rtol=1e-13)
uniform = np.broadcast_to(d.lower+.00001, d.xy.shape).copy()
uniform[~d.movable] = d.base_xy[~d.movable]
xy = legalize(d, uniform)  # difficult case: nearly all cells collide at one corner
crowded_router = Router(d, xy)
crowded_choice, _, _ = crowded_router.optimize(8)
assert crowded_router.metrics(crowded_choice)[0]["max_bond_bin_count"] > crowded_router.via_cap
try:
    crowded_router.assign_bonds(crowded_choice)
    raise AssertionError("Overfull bond window must fail")
except ValueError:
    pass
router = Router(d, d.base_xy)
choice, _, _ = router.optimize(8)
bonds = router.assign_bonds(choice)
bondxy = np.array([[b["x_mm"], b["y_mm"]] for b in bonds])
pitch = c["pitch_um"]/1000
grid = bondxy/pitch-.5
assert np.max(abs(grid-np.rint(grid))) < 1e-8
assert len(np.unique(np.rint(grid).astype(int), axis=0)) == len(grid)
assert router.metrics(choice)[0]["bond_count"] == len(bonds)
oldcap = router.via_cap
router.via_cap = 0
try:
    router.assign_bonds(choice)
    raise AssertionError("Zero bond capacity must fail")
except ValueError:
    pass
router.via_cap = oldcap
manifest_path = root/"results/manifest.json"
if manifest_path.exists():
    import hashlib
    import csv
    m = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert m["source_sha256"] == hashlib.sha256((root/"simulate.py").read_bytes()).hexdigest()
    assert m["winner"]["feasible"]
    assert m["validation"]["max_power_conservation_error_W"] < 1e-10
    assert abs(m["validation"]["thermal_grid_16_to_32_peak_delta_C"]) < .5
    saved_count = 0
    for candidate in ["A_split", "B_critical_local", "C_hot_top"]:
        full = Design(m["config"], candidate)
        names = list(full.regions)
        for i, name in enumerate(names):
            x, y, w, h = full.regions[name]
            assert x >= 0 and y >= 0 and x+w <= m["config"]["die_mm"] and y+h <= m["config"]["die_mm"]
            for other in names[i+1:]:
                if full.module_tier[name] != full.module_tier[other]:
                    continue
                xx, yy, ww, hh = full.regions[other]
                assert x+w <= xx or xx+ww <= x or y+h <= yy or yy+hh <= y, "Overlapping module fences"
        for saved in (root/"results").glob(candidate+"__*.npz"):
            data = np.load(saved)
            check_legal(full, data["xy_mm"])
            assert np.array_equal(data["tier"], full.z)
            assert np.array_equal(data["edges"], full.edges)
            assert np.all(np.isfinite(data["temperature_C"]))
            saved_count += 1
    assert saved_count == 17
    with open(root/"results/best_bonds.csv", encoding="utf-8-sig") as f:
        saved_bonds = list(csv.DictReader(f))
    saved_grid = np.array([[float(b["x_mm"]), float(b["y_mm"])] for b in saved_bonds])/pitch-.5
    assert np.max(np.abs(saved_grid-np.rint(saved_grid))) < 1e-8
    assert len(np.unique(np.rint(saved_grid).astype(int), axis=0)) == m["winner"]["bond_count"]
    print(f"Verified all {saved_count} saved layouts and final bond geometry")
print("PASS: gradients, reciprocity, power conservation, collision legalization, bond pitch/uniqueness/capacity and saved-result provenance")
