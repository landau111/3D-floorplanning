"""Small behavioral checks for geometry, density, and reproducibility."""
import copy
import random
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
from contextlib import contextmanager
from pathlib import Path

import optimize as o
from make_enlarged import scale_config
from thermal import hotspot_inputs, parse_grid, run_hotspot, find_hotspot


CONFIG = Path(__file__).parent / "config.yaml"
COMPACT_CONFIG = Path(__file__).parent / "folding_dse_annealing_cfg.yaml"


@contextmanager
def temporary_directory():
    root = Path(__file__).resolve().parents[1] / "tmp"
    root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=str(root)) as directory:
        # Check containment before TemporaryDirectory's recursive cleanup.
        Path(directory).resolve().relative_to(root.resolve())
        yield directory


class ExplorerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = o.load_config(CONFIG)
        o.validate(cls.c)

    def test_construct_and_reproducibility(self):
        first = o.construct(self.c, random.Random(7))
        second = o.construct(self.c, random.Random(7))
        self.assertEqual(first, second)
        self.assertTrue(o.geometry_ok(self.c, first))
        for name in self.c["fixed_bottom"]:
            self.assertEqual(first[name][4], "bottom")

    def test_original_style_yaml_is_executable(self):
        compact = o.load_config(COMPACT_CONFIG)
        o.validate(compact)
        self.assertEqual(len(compact["modules"]), 16)
        self.assertEqual(compact["interconnect"][0], ["l2_b0", "l2_ctl", 5000])
        self.assertTrue(o.geometry_ok(compact, o.construct(compact, random.Random(1))))
        source = COMPACT_CONFIG.read_text(encoding="utf-8")
        changed = source.replace("if_pp: [0.18, 0.61, 0.0680]", "if_pp: [0.18, 0.61, 0.0700]")
        parsed = o._normalize_compact_config(o._parse_compact_yaml(changed))
        self.assertEqual(parsed["modules"]["if_pp"]["area_mm2"], .07)

    def test_overlap_rejected(self):
        rects = o.initial_fixed(self.c)
        rects["if_pp"] = (*self.c["modules"]["l2_b0"]["rect"], "bottom")
        self.assertFalse(o.geometry_ok(self.c, rects))

    def test_connectivity_changes_cross_tier_count(self):
        rects = o.construct(self.c, random.Random(1))
        changed = copy.deepcopy(rects)
        # Layer assignment alone changes bond demand even at identical XY positions.
        changed["l2_ctl"] = (*changed["l2_ctl"][:4], "top" if changed["l2_ctl"][4] == "bottom" else "bottom")
        self.assertNotEqual(o.metrics(self.c, rects)["cross_layer_signals"],
                            o.metrics(self.c, changed)["cross_layer_signals"])

    def test_area_limit_rejected(self):
        c = copy.deepcopy(self.c)
        c["die_area_limit_mm2"] = .10
        with self.assertRaises(ValueError):
            o.validate(c)

    def test_enlarged_hotspot_inputs(self):
        c = scale_config(self.c, 1.7)
        rects = o.construct(c, random.Random(1))
        with temporary_directory() as directory:
            folder = Path(directory)
            info = hotspot_inputs(c, rects, folder)
            self.assertAlmostEqual(info["total_power_W"], sum(m["power_w"] for m in c["modules"].values()))
            self.assertLess(info["power_conservation_error_W"], 1e-8)
            self.assertEqual(info["active_layer_indices"], {"bottom":0,"top":2})
            trace = (folder/"power.ptrace").read_text().splitlines()
            expected = []
            for layer in ("bottom","top"):
                lines = (folder/(layer+".flp")).read_text().splitlines()
                expected += [line.split()[0] for line in lines]
                area = sum(float(line.split()[1])*float(line.split()[2]) for line in lines)
                self.assertAlmostEqual(area,c["die_width_mm"]*c["die_height_mm"]*1e-6,places=14)
            self.assertEqual(trace[0].split(),expected)

    def test_new_config_is_used(self):
        c = o.load_config(COMPACT_CONFIG)
        self.assertEqual(len(c["layout_constrains"]),12)
        self.assertEqual(c["anneal"]["iters"],40)
        self.assertEqual((c["grid_rows"],c["grid_cols"]),(64,64))
        self.assertAlmostEqual(sum(m["power_w"] for m in c["modules"].values()),.845)
        self.assertEqual(c["timing"]["hbt_latency_ps"],100)

    def test_yaml_rejects_duplicates_and_bad_indent(self):
        for text in ("a: 1\na: 2", "rules:\n- pair: [a,b]\n   type: same_layer_max_dist"):
            with self.assertRaises(ValueError):
                o._parse_compact_yaml(text)

    def test_unknown_constraints_and_conflicting_hbt_fail(self):
        c = o.load_config(COMPACT_CONFIG)
        c["layout_constrains"][0]["pair"][0] = "if_ctrl"
        with self.assertRaises(ValueError):
            o.validate(c)
        raw = o._parse_compact_yaml(COMPACT_CONFIG.read_text(encoding="utf-8"))
        raw["hbt"]["max_density_per_mm2"] = 1000
        with self.assertRaises(ValueError):
            o._normalize_compact_config(raw)

    def test_center_manhattan_soft_constraints_and_top_preference(self):
        c = copy.deepcopy(self.c)
        c["layout_constrains"] = [{"pair":["rn","ix"],"type":"same_layer_max_dist","max_dist_mm":.20,"layer":"top"}]
        rects = o.construct(c,random.Random(1))
        # Centers at (.1,.1) and (.2,.2): Manhattan .2, Euclidean .1414.
        rects["rn"] = (0,0,.2,.2,"top")
        rects["ix"] = (.1,.1,.2,.2,"top")
        self.assertAlmostEqual(o.metrics(c,rects)["soft_constraint_penalty"],0)
        rects["ix"] = (.2,.1,.2,.2,"top")
        self.assertAlmostEqual(o.metrics(c,rects)["soft_constraint_penalty"],.25)
        rects["ix"] = (.1,.1,.2,.2,"bottom")
        self.assertAlmostEqual(o.metrics(c,rects)["soft_constraint_penalty"],2)
        # Soft requirements never participate in geometry legality.
        legal = o.construct(c,random.Random(1))
        c["layout_constrains"][0]["max_dist_mm"] = 1e-6
        self.assertTrue(o.geometry_ok(c,legal))
        self.assertGreater(o.metrics(c,legal)["soft_constraint_violations"],0)

    def test_arbitrary_links_timing_and_temperature_feedback(self):
        c = copy.deepcopy(self.c)
        c["interconnect"] = [["rn","is_int",10],["is_int","mmu",5]]
        o.validate(c)
        rects = o.construct(c,random.Random(1))
        cool = {n:27.0 for n in rects}; hot = {n:127.0 for n in rects}
        a,b = o.metrics(c,rects,cool),o.metrics(c,rects,hot)
        self.assertAlmostEqual(b["rc_quadratic_cost_mm2"]/a["rc_quadratic_cost_mm2"],1.39)
        rects["is_int"] = (*rects["is_int"][:4],"bottom")
        rects["rn"] = (*rects["rn"][:4],"top")
        m = o.metrics(c,rects,cool)
        self.assertAlmostEqual(m["interconnect_costs"][0]["hbt_latency_ps"],100)
        c["net_weights"]["crit_crit"] = 3
        weighted = o.metrics(c,rects,cool)
        self.assertEqual(weighted["interconnect_costs"][0]["weight"],3)
        self.assertEqual(weighted["interconnect_costs"][1]["weight"],1)

    def test_hotspot_grid_layer_mapping_and_vertical_direction(self):
        raw = "Layer 0:\n0 300\n1 301\n2 302\n3 303\nLayer 2:\n0 310\n1 311\n2 312\n3 313\n"
        maps = parse_grid(raw,2,2,{"bottom":0,"top":2})
        self.assertAlmostEqual(maps[0][0][0],302-273.15)
        self.assertAlmostEqual(maps[1][1][1],311-273.15)
        with self.assertRaises(ValueError):
            parse_grid(raw.replace("3 313","3 nan"),2,2,{"bottom":0,"top":2})
        with self.assertRaises(ValueError):
            parse_grid(raw.replace("3 313\n",""),2,2,{"bottom":0,"top":2})

    def test_no_missing_hotspot_fallback(self):
        with self.assertRaises(RuntimeError):
            find_hotspot("/not/a/hotspot/binary")

    def test_hotspot_failure_is_not_hidden(self):
        import subprocess
        with temporary_directory() as directory:
            folder = Path(directory)
            exe = folder/"dummy_hotspot"
            exe.write_text("dummy")
            rects = o.construct(self.c,random.Random(1))
            with patch("thermal.subprocess.run",return_value=subprocess.CompletedProcess([],1,"","solver failed")):
                with self.assertRaisesRegex(RuntimeError,"solver failed"):
                    run_hotspot(str(exe),self.c,rects,folder/"run")

    def test_pareto_includes_constraint_and_timing_costs(self):
        from explore import OBJECTIVE_KEYS,pareto_flags,select_candidates
        points = [(1,1,1,1,1),(2,2,2,2,2),(.5,1,1,3,.5),(1,1,.5,1,1)]
        candidates = [{"metrics":dict(zip(OBJECTIVE_KEYS,p)),"profile":"balanced"} for p in points]
        flags = pareto_flags(candidates)
        self.assertEqual(flags,[False,False,True,True])
        self.assertTrue(all(flags[i] for i in select_candidates(candidates,flags,4)))

    def test_impossible_top_area_and_center_distance_are_reported(self):
        from constraints import constraint_feasibility
        report = constraint_feasibility(o.load_config(COMPACT_CONFIG))
        self.assertFalse(report["all_soft_constraints_necessarily_possible"])
        self.assertAlmostEqual(report["layer_preferences"]["top"]["required_area_mm2"],.6902)
        tight = [v for v in report["pair_distance_lower_bounds"] if v["pair"] == ["is_int","ix"]][0]
        self.assertFalse(tight["distance_necessary_condition_met"])


class RealHotSpotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.exe = find_hotspot()
            if sys.platform == "win32":
                raise RuntimeError("Run real binary tests using WSL")
        except RuntimeError as error:
            if os.environ.get("REQUIRE_HOTSPOT_TEST"):
                raise
            raise unittest.SkipTest(str(error))

    def test_power_monotonicity_layer_order_and_hot_region_direction(self):
        c = o.load_config(CONFIG)
        c.update(die_width_mm=1,die_height_mm=1,die_area_limit_mm2=1,module_gap_mm=0,grid_rows=8,grid_cols=8)
        c["modules"] = {"heater":{"kind":"soft","anchor":[.1,.9],"area_mm2":.04,"power_w":.2},
                        "idle":{"kind":"soft","anchor":[.9,.1],"area_mm2":.04,"power_w":0}}
        rects = {"heater":(0,.8,.2,.2,"bottom"),"idle":(.8,0,.2,.2,"top")}
        with temporary_directory() as directory:
            folder = Path(directory)
            one = run_hotspot(self.exe,c,rects,folder/"one")
            self.assertGreater(one["temperature_C"][0][-1][0],one["temperature_C"][0][0][0])
            c["modules"]["heater"]["power_w"] = .4
            two = run_hotspot(self.exe,c,rects,folder/"two")
            self.assertAlmostEqual(two["peak_C"]-c["ambient_c"],2*(one["peak_C"]-c["ambient_c"]),delta=.03)
            rects["heater"] = (*rects["heater"][:4],"top")
            rects["idle"] = (*rects["idle"][:4],"bottom")
            upper = run_hotspot(self.exe,c,rects,folder/"upper")
            self.assertLess(upper["peak_C"],two["peak_C"])


if __name__ == "__main__":
    unittest.main()
