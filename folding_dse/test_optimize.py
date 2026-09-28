"""Small behavioral checks for geometry, density, and reproducibility."""
import copy
import random
import unittest
from pathlib import Path

import optimize as o
from make_enlarged import scale_config
from thermal import hotspot_inputs, proxy_temperature


CONFIG = Path(__file__).parent / "config.yaml"


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

    def test_enlarged_thermal_and_hotspot_inputs(self):
        c = scale_config(self.c, 1.7)
        rects = o.construct(c, random.Random(1))
        thermal = proxy_temperature(c, rects)
        self.assertLess(thermal["power_conservation_error_W"], 1e-8)
        self.assertGreater(thermal["peak_C"], c["thermal_proxy"]["ambient_C"])
        folder = Path(__file__).parent / "_test_hotspot_inputs"
        folder.mkdir(exist_ok=True)
        try:
            info = hotspot_inputs(c, rects, folder)
            self.assertAlmostEqual(info["total_power_W"], sum(m["power_w"] for m in c["modules"].values()))
            self.assertTrue((folder / "stack.lcf").exists())
        finally:
            for file in folder.glob("*"):
                file.unlink()
            folder.rmdir()


if __name__ == "__main__":
    unittest.main()
