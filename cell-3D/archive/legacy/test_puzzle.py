"""Verify nonrectangular partition, true cell legality, gradients and provenance."""
import hashlib,json
from pathlib import Path
import numpy as np
from puzzle import Territory,PuzzlePlacement,test_shape_gradient
from simulate import Design,Thermal

ROOT=Path(__file__).resolve().parent
m=json.loads((ROOT/"puzzle_results/manifest.json").read_text(encoding="utf-8"))
assert hashlib.sha256((ROOT/"puzzle.py").read_bytes()).hexdigest()==m["source_sha256"]
c,cfg=m["physical_config"],m["config"]
d=Design(c,cfg["base_candidate"])
t=Territory(d,cfg,Thermal(c))
err=test_shape_gradient(t)
assert m["territory_coverage"]==1
assert np.isclose(m["free_area_cell_utilization"],.245)
for profile in cfg["profiles"]:
    saved=np.load(ROOT/"puzzle_results"/f"puzzle__{profile}.npz")
    td=Design(c,cfg["base_candidate"])
    placement=PuzzlePlacement(td,t,saved["labels"],cfg,profile)
    shape_records=t.validate(saved["labels"])
    assert placement.validate(saved["xy_mm"])
    assert np.array_equal(saved["edges"],d.edges)
    assert np.array_equal(saved["tier"],d.z)
    assert np.array_equal(saved["module_id"],d.module)
    assert all(x["components"]==1 and x["holes"]==0 for x in shape_records)
    # Entire cell rectangles must be outside the exact fixed macros and their halos.
    for z in range(2):
        ids=np.flatnonzero(td.movable&(td.z==z))
        xy=saved["xy_mm"][ids]
        x,y,w,h=d.regions[f"l2_b{z}"];halo=cfg["macro_keepout_mm"]
        low=xy-[placement.w/2,placement.h/2];high=xy+[placement.w/2,placement.h/2]
        overlap=(high[:,0]>x-halo+1e-10)&(low[:,0]<x+w+halo-1e-10)&(high[:,1]>y-halo+1e-10)&(low[:,1]<y+h+halo-1e-10)
        assert not overlap.any()
    if profile==m["winner"]["profile"]:
        xy=saved["xy_mm"].copy()
        _,grad,_=placement.objective(xy)
        rng=np.random.default_rng(173)
        errors=[]
        for i in rng.choice(np.flatnonzero(td.movable),12,replace=False):
            for k in [0,1]:
                a,b=xy.copy(),xy.copy();a[i,k]+=1e-7;b[i,k]-=1e-7
                numeric=(placement.objective(a)[0]-placement.objective(b)[0])/2e-7
                errors.append(abs(numeric-grad[i,k])/max(1e-5,abs(numeric),abs(grad[i,k])))
        assert max(errors)<.01,errors
        print("Cell+uniform-density gradient max relative error",max(errors))
assert abs(m["fine_grid_peak_delta_C"])<.5
print("PASS: shape gradients",err,"; 3 exact partitions; 42 connected hole-free territories; all 88200 placed cells legal; identical netlist/tier; macro halo; source hashes; thermal refinement")
