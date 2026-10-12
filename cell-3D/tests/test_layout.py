"""Input precedence, mathematical gradients and saved placement invariants."""
import copy
import os
import tempfile
import unittest
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
import numpy as np
from layout_input import read_layout,read_auxiliary
from run_layout import Model,Regions,Cells,Routing,source_settings,pareto


class LayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.layout=read_layout(ROOT/"configs/config.yaml.json")
        cls.aux=read_auxiliary(ROOT/"configs/folding_dse_annealing_cfg.yaml",cls.layout)
        cls.d=Model(cls.layout,cls.aux,source_settings(cls.aux),20261012)
        cls.r=Regions(cls.d)

    def test_authoritative_data(self):
        self.assertAlmostEqual(sum(self.aux["power_w"].values()),.845)
        self.assertEqual(len(self.aux["interconnect"]),18)
        self.assertEqual(self.aux["cross_tier_signal_count"],1360)
        self.assertEqual(self.d.cross.sum(),1360)
        self.assertEqual(self.d.extent.tolist(),[.9,.78])
        self.assertEqual(self.layout["max_density_per_mm2"],40000)
        self.assertEqual(self.layout["hbt_vertical_um"],6)
        self.assertEqual(self.aux["aliases"],{"mmu":"mm"})

    def test_temperature_does_not_fit_power(self):
        changed=copy.deepcopy(self.layout)
        for m in changed["modules"]:m["reference_C"]+=20
        d=Model(changed,self.aux,source_settings(self.aux),20261012)
        np.testing.assert_array_equal(d.unit_power,self.d.unit_power)
        np.testing.assert_array_equal(d.xy,self.d.xy)

    def test_input_names_and_missing_coordinates(self):
        text=(ROOT/"configs/config.yaml.json").read_text(encoding="utf-8-sig")
        fd,name=tempfile.mkstemp(prefix="test_input_",suffix=".yaml",dir=ROOT);os.close(fd)
        file=Path(name)
        try:
            file.write_text(text.replace("w=0.400   h= 0.100","w=0.400"),encoding="utf-8")
            with self.assertRaises(ValueError):read_layout(file)
            file.write_text(text.replace("x= 0.020    y= 0.020","x= 0.800    y= 0.020",1),encoding="utf-8")
            with self.assertRaises(ValueError):read_layout(file)
        finally:file.unlink()

    def test_heat_adjoint_and_linearity(self):
        rng=np.random.default_rng(8);a=rng.random(512);b=rng.random(512)
        h=self.d.heat
        self.assertAlmostEqual(float(a@h.apply(b)),float(b@h.apply(a)),places=9)
        np.testing.assert_allclose(h.apply(2*a),2*h.apply(a),rtol=1e-12)

    def test_region_gradient(self):
        r=self.r;c=r.centers.copy();w=np.zeros(len(c));tau=.03
        loss,gc,gw,_=r.objective(c,w,tau)
        for mi,axis in ((self.d.mid["mm"],0),(self.d.mid["is_int"],1),(self.d.mid["vec_vx"],1)):
            eps=1e-6;cp=c.copy();cm=c.copy();cp[mi,axis]+=eps;cm[mi,axis]-=eps
            num=(r.objective(cp,w,tau)[0]-r.objective(cm,w,tau)[0])/(2*eps)
            self.assertAlmostEqual(num,gc[mi,axis],delta=2e-4*max(1,abs(num)))
            wp=w.copy();wm=w.copy();wp[mi]+=eps;wm[mi]-=eps
            num=(r.objective(c,wp,tau)[0]-r.objective(c,wm,tau)[0])/(2*eps)
            self.assertAlmostEqual(num,gw[mi],delta=2e-4*max(1,abs(num)))

    def test_cell_gradient(self):
        # Objective depends on density targets, but not the discrete partition itself.
        cells=Cells.__new__(Cells);cells.d=self.d
        cells.binarea=np.prod(self.d.extent)/self.d.heat.g**2
        cells.target=np.full(512,.5)
        xy=self.d.xy.copy();xy[self.d.movable]+=[.00011,.00013]
        _,grad=cells.objective(xy,"balanced")
        for mi in ("mm","is_int","ls"):
            i=self.d.ids[self.d.mid[mi]][10];eps=1e-7
            for axis in (0,1):
                xp=xy.copy();xm=xy.copy();xp[i,axis]+=eps;xm[i,axis]-=eps
                num=(cells.objective(xp,"balanced")[0]-cells.objective(xm,"balanced")[0])/(2*eps)
                self.assertAlmostEqual(num,grad[i,axis],delta=2e-5*max(1,abs(num)))

    def test_routing_gradient(self):
        router=Routing(self.d,self.d.xy);logits=np.random.default_rng(9).normal(0,.3,(len(router.guide),4))
        _,grad=router.loss(logits)
        for i,k in ((1,0),(5200,2),(7000,3)):
            eps=1e-5;lp=logits.copy();lm=logits.copy();lp[i,k]+=eps;lm[i,k]-=eps
            num=(router.loss(lp)[0]-router.loss(lm)[0])/(2*eps)
            self.assertAlmostEqual(num,grad[i,k],delta=1e-9)

    def test_pareto_rejects_infeasible_points(self):
        rows=[dict(run="a",feasible=False,power_W=1,peak_C=40,mean_bips=2)]
        self.assertEqual(pareto(rows),[])
        self.assertEqual(pareto(rows,False),["a"])

    def test_saved_full_run_invariants(self):
        folder=ROOT/"results/2026-10-13/20261013_release"
        if not folder.is_dir():folder=None
        if folder is None:self.skipTest("Run archive optional in portable package")
        data=np.load(folder/"timing.npz");xy=data["xy_mm"];labels=data["labels"]
        self.r.validate(labels);cells=Cells(self.d,self.r,labels);cells.validate(xy)
        self.assertEqual(self.d.movable.sum(),13132)
        np.testing.assert_array_equal(data["edges"],self.d.edges)
        ids=np.flatnonzero(self.d.movable)
        row=np.rint(xy[ids,1]/self.d.h-.5).astype(int)
        self.assertFalse(cells.reserved_rows[row].any())


if __name__=="__main__":unittest.main(verbosity=2)
