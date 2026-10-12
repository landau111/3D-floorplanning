"""Reproducible synthetic cell placement + differentiable routing experiment.

Only NumPy is required. Units: mm, ns, GHz, W, C. All derivatives are analytic.
This is NOT synthesis, signoff STA, detailed routing, HotSpot or a gem5 rerun.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
import platform
import time
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent


def save_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def softmax(x, axis=-1):
    e = np.exp(x - x.max(axis=axis, keepdims=True))
    return e / e.sum(axis=axis, keepdims=True)


def write_csv(path, records):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(records[0]))
        w.writeheader()
        w.writerows(records)


class Design:
    def __init__(self, c, candidate):
        self.c, self.name = c, candidate
        self.rng = np.random.default_rng(c["seed"])
        self.mods = c["modules"]
        self.mid = {m["name"]: i for i, m in enumerate(self.mods)}
        # 4x4 slots, hard macro occupies upper-left 2x2 slots on each tier.
        slots = [(x, y) for y in range(4) for x in range(4) if not (x < 2 and y >= 2)]
        bottom = ["if_pp", "if_ctl", "id", "rn", "is_int", "ix", "ls"]
        top = ["l2_ctl", "tpe", "mm", "vec_vx", "is_int_fwd", "is_int_rf", "vec_is_vec"]
        if candidate == "B_critical_local":
            bottom = ["id", "rn", "is_int", "ix", "is_int_fwd", "is_int_rf", "ls"]
            top = ["if_pp", "if_ctl", "l2_ctl", "tpe", "mm", "vec_is_vec", "vec_vx"]
        if candidate == "C_hot_top":
            bottom, top = top, bottom
            top = ["ix", "ls", "is_int", "rn", "id", "if_ctl", "if_pp"]
        orders = {"A_split": [0, 1, 4, 5, 2, 3, 6],
                  "B_critical_local": [0, 1, 2, 3, 7, 6, 5],
                  "C_hot_top": [3, 2, 1, 0, 5, 4, 6]}
        self.regions, self.module_tier = {}, {}
        for tier, names in enumerate([bottom, top]):
            for j, name in enumerate(names):
                sx, sy = slots[orders[candidate][j]]
                self.regions[name] = [sx * .4 + .03, sy * .4 + .03, c["module_region_mm"], c["module_region_mm"]]
                self.module_tier[name] = tier
        for tier, name in enumerate(["l2_b0", "l2_b1"]):
            self.regions[name] = [.02, .82, c["macro_side_mm"], c["macro_side_mm"]]
            self.module_tier[name] = tier
        self.xy, self.z, self.module, self.dynamic, self.leak, self.lower, self.upper = [], [], [], [], [], [], []
        self.ids = {}
        w, h = c["cell_width_um"] / 1000, c["cell_height_um"] / 1000
        for mi, mod in enumerate(self.mods):
            name = mod["name"]
            x, y, rw, rh = self.regions[name]
            if mod["kind"] == "sram_macro":
                # Fixed distributed macro ports; NOT movable SRAM bit cells.
                xx, yy = np.meshgrid(np.linspace(x+.01, x+rw-.01, 8), np.linspace(y+.01, y+rh-.01, 8))
                p = np.column_stack([xx.ravel(), yy.ravel()])
            else:
                nx, ny = int(rw / w), int(rh / h)
                n = c["cell_count_per_logic_module"]
                assert n <= nx * ny
                sites = self.rng.choice(nx * ny, n, replace=False)
                p = np.column_stack([x + (sites % nx + .5) * w, y + (sites // nx + .5) * h])
            start, n = len(self.xy), len(p)
            self.ids[name] = np.arange(start, start+n)
            self.xy.extend(p)
            self.z.extend([self.module_tier[name]] * n)
            self.module.extend([mi] * n)
            activity = self.rng.uniform(.65, 1.35, n)
            activity /= activity.sum()
            self.dynamic.extend(activity * mod["dynamic_W"])
            self.leak.extend(np.full(n, mod["leakage_W"] / n))
            if mod["kind"] == "sram_macro":
                self.lower.extend(p); self.upper.extend(p)
            else:
                self.lower.extend([[x+w/2, y+h/2]] * n)
                self.upper.extend([[x+int(rw/w)*w-w/2, y+int(rh/h)*h-h/2]] * n)
        for k in ["xy", "dynamic", "leak", "lower", "upper"]:
            setattr(self, k, np.array(getattr(self, k), dtype=float))
        self.z, self.module = np.array(self.z), np.array(self.module)
        self.movable = np.any(self.lower != self.upper, axis=1)
        # Identical synthesized random connectivity and logic delays for all candidates.
        edges, external = [], []
        for name, ids in self.ids.items():
            if len(ids) == 64:
                continue
            for offset in [1, 7]:
                edges.extend(zip(ids, np.roll(ids, offset)))
                external.extend([False] * len(ids))
        for a, b, n in c["connections"]:
            edges.extend(zip(self.rng.choice(self.ids[a], n), self.rng.choice(self.ids[b], n)))
            external.extend([True] * n)
        self.edges = np.array(edges, dtype=int)
        self.external = np.array(external)
        self.a, self.b = self.edges.T
        self.cross = (self.z[self.a] != self.z[self.b]).astype(float)
        self.logic_ns = self.rng.uniform(.24, .35, len(edges))
        self.logic_ns[self.external] += .035
        self.critical = 1 + 2 * (self.logic_ns > .34)
        self.base_xy = self.xy.copy()

    def module_records(self):
        return [dict(name=m["name"], kind=m["kind"], tier=self.module_tier[m["name"]],
                     x_mm=self.regions[m["name"]][0], y_mm=self.regions[m["name"]][1],
                     width_mm=self.regions[m["name"]][2], height_mm=self.regions[m["name"]][3],
                     dynamic_W=m["dynamic_W"], leakage_at_60C_W=m["leakage_W"])
                for m in self.mods]


def splat(xy, z, width, g):
    """Bilinear cell-centered deposition; derivative uses clamped boundary rule."""
    u0 = xy * g / width - .5
    u = np.clip(u0, 0, g - 1 - 1e-9)
    ij = np.floor(u).astype(int)
    frac = u - ij
    ix, iy = ij.T
    fx, fy = frac.T
    indices = np.stack([z*g*g+iy*g+ix, z*g*g+iy*g+ix+1,
                        z*g*g+(iy+1)*g+ix, z*g*g+(iy+1)*g+ix+1], axis=1)
    weights = np.stack([(1-fx)*(1-fy), fx*(1-fy), (1-fx)*fy, fx*fy], axis=1)
    dx = np.stack([-(1-fy), 1-fy, -fy, fy], axis=1) * g/width
    dy = np.stack([-(1-fx), -fx, 1-fx, fx], axis=1) * g/width
    dx *= ((u0[:, 0] > 0) & (u0[:, 0] < g-1))[:, None]
    dy *= ((u0[:, 1] > 0) & (u0[:, 1] < g-1))[:, None]
    return indices, weights, dx, dy


def deposit(values, sp, size):
    return np.bincount(sp[0].ravel(), weights=(values[:, None]*sp[1]).ravel(), minlength=size)


def adjoint(values, sp, field):
    f = field[sp[0]] * values[:, None]
    return np.column_stack([(f * sp[2]).sum(1), (f * sp[3]).sum(1)])


class Thermal:
    def __init__(self, c, g=None):
        self.c, self.g = c, g or c["thermal_grid"]
        g = self.g
        lap = np.diag(np.r_[1, np.full(g-2, 2), 1]) - np.eye(g, k=1) - np.eye(g, k=-1)
        lam, self.U = np.linalg.eigh(lap)
        lateral = c["lateral_G_W_K"] * (lam[:, None] + lam[None, :])
        gv = c["intertier_G_W_K_at_16"] * (16/g)**2
        gs = c["top_sink_G_W_K_at_16"] * (16/g)**2
        a, b = lateral + gv, lateral + gv + gs
        det = a*b-gv*gv
        self.aa, self.bb, self.ab = b/det, a/det, gv/det

    def apply(self, p, package_R=None):
        p = p.reshape(2, self.g, self.g)
        q = self.U.T @ p @ self.U
        t = np.stack([self.aa*q[0]+self.ab*q[1], self.ab*q[0]+self.bb*q[1]])
        result = self.U @ t @ self.U.T
        return (result + (package_R if package_R is not None else self.c["package_R_K_W"]) * p.sum()).ravel()


PROFILES = {"balanced": (1.0, .45, .40), "timing": (1.8, .12, .15), "thermal": (.45, 1.2, .50)}


class Placement:
    def __init__(self, d, thermal, profile):
        self.d, self.c, self.thermal = d, d.c, thermal
        self.weights = PROFILES[profile]
        self.g, self.size = thermal.g, 2*thermal.g**2
        self.area = np.where(d.movable, d.c["cell_width_um"]*d.c["cell_height_um"]*1e-6, 0.)
        self.bin_area = (self.c["die_mm"]/self.g)**2

    def objective(self, xy):
        d, c = self.d, self.c
        delta = xy[d.a]-xy[d.b]
        smooth = np.sqrt(delta*delta+0.0004**2)
        length = smooth.sum(1)
        wl = (length*d.critical).mean() / .25
        delay_proxy = d.logic_ns+c["wire_delay_ns_per_mm"]*length+c["wire_delay_ns_per_mm2"]*length**2+d.cross*c["bond_delay_ns"]
        timing_prob = softmax(delay_proxy/.012)
        timing_loss = (.012*np.log(np.exp((delay_proxy-delay_proxy.max())/.012).sum())+delay_proxy.max())/.5
        timing_derivative = timing_prob*(c["wire_delay_ns_per_mm"]+2*c["wire_delay_ns_per_mm2"]*length)/.5
        dl = self.weights[0] * (.45*d.critical/(len(length)*.25)+1.5*timing_derivative)
        grad = np.zeros_like(xy)
        force = dl[:, None]*delta/smooth
        np.add.at(grad, d.a, force); np.add.at(grad, d.b, -force)
        sp = splat(xy, d.z, c["die_mm"], self.g)
        density = deposit(self.area, sp, self.size)/self.bin_area
        overflow = np.maximum(density-c["density_target"], 0)
        density_loss = 30 * np.mean(overflow**2)
        grad += adjoint(self.area, sp, 60*overflow/(self.size*self.bin_area))
        powers = d.dynamic+d.leak
        pmap = deposit(powers, sp, self.size)
        temp = c["ambient_C"]+self.thermal.apply(pmap)
        prob = softmax(temp/2)
        # Dimensionless smooth maximum and squared local power density objectives.
        tmax_smooth = 2*(np.log(np.exp((temp-temp.max())/2).sum())+temp.max()/2)
        heat = (tmax_smooth-c["ambient_C"])/40
        field = self.thermal.apply(prob/40)
        grad += self.weights[1]*adjoint(powers, sp, field)
        power_concentration = self.size * np.sum(pmap*pmap)/powers.sum()**2
        grad += self.weights[2]*adjoint(powers, sp, 2*self.size*pmap/powers.sum()**2)
        value = self.weights[0]*(.45*wl+1.5*timing_loss)+density_loss+self.weights[1]*heat+self.weights[2]*power_concentration
        grad[~d.movable] = 0
        return value, grad, dict(loss=float(value), wire=float(wl), timing=float(timing_loss), density=float(density_loss),
                                 thermal=float(heat), concentration=float(power_concentration))

    def optimize(self, steps, seed=0):
        d = self.d
        xy = d.base_xy.copy()
        if seed:
            xy = np.clip(xy+np.random.default_rng(seed).normal(0, .003, xy.shape), d.lower, d.upper)
        m, v = np.zeros_like(xy), np.zeros_like(xy)
        best, bestloss, history = xy.copy(), float("inf"), []
        for i in range(steps+1):
            loss, grad, info = self.objective(xy)
            if loss < bestloss:
                best, bestloss = xy.copy(), loss
            if i % 10 == 0 or i == steps:
                history.append(dict(iteration=i, **info))
            if i == steps:
                break
            m = .9*m+.1*grad
            v = .999*v+.001*grad*grad
            lr = .006 * (.20+.80*(1-i/max(steps, 1)))
            xy = np.clip(xy-lr*(m/(1-.9**(i+1)))/(np.sqrt(v/(1-.999**(i+1)))+1e-9), d.lower, d.upper)
        return best, history


def legalize(d, xy):
    """Assign each uniform cell to a unique row/site inside its fixed module fence."""
    result = xy.copy()
    w, h = d.c["cell_width_um"]/1000, d.c["cell_height_um"]/1000
    for name, ids in d.ids.items():
        if not d.movable[ids[0]]:
            continue
        x, y, rw, rh = d.regions[name]
        nx, ny = int(rw/w), int(rh/h)
        used = np.zeros((ny, nx), dtype=bool)
        for cell in ids[np.lexsort((xy[ids, 0], xy[ids, 1]))]:
            cx = int(np.clip(np.rint((xy[cell, 0]-x)/w-.5), 0, nx-1))
            cy = int(np.clip(np.rint((xy[cell, 1]-y)/h-.5), 0, ny-1))
            radius = 0
            while True:
                x0, x1 = max(0, cx-radius), min(nx, cx+radius+1)
                y0, y1 = max(0, cy-radius), min(ny, cy+radius+1)
                ry, rx = np.nonzero(~used[y0:y1, x0:x1])
                if len(rx):
                    rx, ry = rx+x0, ry+y0
                    dd = (x+(rx+.5)*w-xy[cell, 0])**2+(y+(ry+.5)*h-xy[cell, 1])**2
                    j = dd.argmin()
                    cx, cy = rx[j], ry[j]
                    break
                radius += 1
            used[cy, cx] = True
            result[cell] = [x+(cx+.5)*w, y+(cy+.5)*h]
    check_legal(d, result)
    return result


def check_legal(d, xy):
    assert np.all(xy >= d.lower-1e-10) and np.all(xy <= d.upper+1e-10)
    assert np.allclose(xy[~d.movable], d.base_xy[~d.movable])
    for name, ids in d.ids.items():
        if d.movable[ids[0]]:
            x, y, _, _ = d.regions[name]
            sites = (xy[ids]-[x, y])/[d.c["cell_width_um"]/1000, d.c["cell_height_um"]/1000]-.5
            assert np.max(np.abs(sites-np.rint(sites))) < 1e-7
            assert len(np.unique(np.rint(sites).astype(int), axis=0)) == len(ids)


class Router:
    """Two L paths x two trunk tiers, fixed two-pin topology. Not full DRG-3D."""
    def __init__(self, d, xy):
        self.d, self.c, self.xy = d, d.c, xy
        self.g = d.c["routing_grid"]
        self.ept = 2*self.g*(self.g-1)
        self.edge_count = 2*self.ept
        self.guide = np.flatnonzero(d.external)
        self.cap = np.full(self.edge_count, d.c["routing_tracks_per_edge"], dtype=float)
        for z in range(2):
            for direction in range(2):
                for y in range(self.g if direction == 0 else self.g-1):
                    for x in range(self.g-1 if direction == 0 else self.g):
                        mx, my = (x+.5)*d.c["die_mm"]/self.g, (y+.5)*d.c["die_mm"]/self.g
                        if .02 <= mx <= .78 and .82 <= my <= 1.58:
                            self.cap[self.edge(z, direction, x, y)] *= d.c["macro_routing_capacity_factor"]
        self.gridxy = np.minimum((xy*self.g/d.c["die_mm"]).astype(int), self.g-1)
        self.background = np.zeros(self.edge_count)
        for i in np.flatnonzero(~d.external):
            path = self.path(i, 0, int(d.z[d.a[i]]))
            np.add.at(self.background, path, 1)
        # Sparse incidence represented by flattened (candidate, resource) pairs.
        cand, resource, via_cand, via_bin = [], [], [], []
        self.vias = np.zeros((len(self.guide), 4))
        for j, i in enumerate(self.guide):
            for choice in range(4):
                tier, bend = choice//2, choice % 2
                route = self.path(i, bend, tier)
                cand.extend([j*4+choice]*len(route)); resource.extend(route)
                for node in [d.a[i], d.b[i]]:
                    if d.z[node] != tier:
                        vx, vy = self.gridxy[node]
                        via_cand.append(j*4+choice); via_bin.append(vy*self.g+vx)
                        self.vias[j, choice] += 1
        self.cand, self.resource = np.array(cand, int), np.array(resource, int)
        self.via_cand, self.via_bin = np.array(via_cand, int), np.array(via_bin, int)
        self.via_cap = min(d.c["max_density_per_mm2"], 1e6/d.c["pitch_um"]**2) * (d.c["die_mm"]/self.g)**2

    def edge(self, z, direction, x, y):
        return z*self.ept + (y*(self.g-1)+x if direction == 0 else self.g*(self.g-1)+y*self.g+x)

    def path(self, i, bend, tier):
        a, b = self.d.a[i], self.d.b[i]
        ax, ay = self.gridxy[a]; bx, by = self.gridxy[b]
        hy, vx = (ay, bx) if bend == 0 else (by, ax)
        return [self.edge(tier, 0, x, hy) for x in range(min(ax, bx), max(ax, bx))] + [
            self.edge(tier, 1, vx, y) for y in range(min(ay, by), max(ay, by))]

    def demand(self, prob):
        p = prob.ravel()
        routing = self.background + np.bincount(self.resource, weights=p[self.cand], minlength=self.edge_count)
        vias = np.bincount(self.via_bin, weights=p[self.via_cand], minlength=self.g**2)
        return routing, vias

    def loss_grad(self, logits):
        prob = softmax(logits)
        demand, vias = self.demand(prob)
        overflow = np.maximum(demand/self.cap-1, 0)
        vo = np.maximum(vias/self.via_cap-1, 0)
        n = len(self.guide)
        # Added timing proxy via count: same L-path length in either tier.
        coeff = (0.08 + .04*self.d.critical[self.guide, None]) / n
        loss = 12*np.mean(overflow**2)+5*np.mean(vo**2)+np.sum(prob*self.vias*coeff)
        adj = 24*overflow/(self.edge_count*self.cap)
        dv = 10*vo/(self.g**2*self.via_cap)
        gp = np.bincount(self.cand, weights=adj[self.resource], minlength=n*4).reshape(n, 4)
        gp += np.bincount(self.via_cand, weights=dv[self.via_bin], minlength=n*4).reshape(n, 4)
        gp += self.vias*coeff
        return loss, prob*(gp-(gp*prob).sum(1, keepdims=True))

    def baseline(self):
        return 2*self.d.z[self.d.a[self.guide]]

    def optimize(self, steps):
        logits = np.zeros((len(self.guide), 4))
        logits[np.arange(len(logits)), self.baseline()] = .1
        m, v, history = np.zeros_like(logits), np.zeros_like(logits), []
        for i in range(steps):
            loss, grad = self.loss_grad(logits)
            m = .9*m+.1*grad; v = .999*v+.001*grad**2
            logits -= .15*(m/(1-.9**(i+1)))/(np.sqrt(v/(1-.999**(i+1)))+1e-9)
            if i % 20 == 0 or i == steps-1:
                history.append(dict(iteration=i, loss=float(loss)))
        prob = softmax(logits)
        choice = prob.argmax(1)
        return choice, history, float(self.loss_grad(logits)[0])

    def metrics(self, choice):
        hard = np.eye(4)[choice]
        demand, bins = self.demand(hard)
        vias = self.d.cross.copy()
        vias[self.guide] = self.vias[np.arange(len(choice)), choice]
        length = np.abs(self.xy[self.d.a]-self.xy[self.d.b]).sum(1)
        return dict(route_overflow_tracks=float(np.maximum(demand-self.cap, 0).sum()),
                    route_overflow_fraction=float(np.maximum(demand-self.cap, 0).sum()/self.cap.sum()),
                    max_route_utilization=float((demand/self.cap).max()),
                    bond_count=int(vias.sum()), max_bond_bin_density_mm2=float(bins.max()/(self.c["die_mm"]/self.g)**2),
                    max_bond_bin_count=int(bins.max()), bond_bin_capacity=float(self.via_cap)), length, vias

    def assign_bonds(self, choice):
        """Distinct pitch-aligned sites within each aligned routing bin; validate density."""
        g, c, d = self.g, self.c, self.d
        used, records = {}, []
        step = c["pitch_um"]/1000
        count = round(c["die_mm"]/g/step)
        assert abs(count*step-c["die_mm"]/g) < 1e-9
        for j, i in enumerate(self.guide):
            tier = choice[j]//2
            for endpoint, node in enumerate([d.a[i], d.b[i]]):
                if d.z[node] == tier:
                    continue
                bx, by = self.gridxy[node]
                key = (int(bx), int(by))
                occupied = used.setdefault(key, set())
                if len(occupied) >= math.floor(self.via_cap):
                    raise ValueError("Bond density infeasible after hard routing selection")
                sx, sy = np.meshgrid(np.arange(count), np.arange(count))
                sites = np.column_stack([sx.ravel(), sy.ravel()])
                coords = (sites+.5)*step+np.array([bx, by])*c["die_mm"]/g
                order = np.argsort(((coords-self.xy[node])**2).sum(1), kind="stable")
                k = next(int(k) for k in order if int(k) not in occupied)
                occupied.add(k)
                records.append(dict(net_id=int(i), endpoint=endpoint, x_mm=float(coords[k, 0]), y_mm=float(coords[k, 1]),
                                    pin_x_mm=float(self.xy[node, 0]), pin_y_mm=float(self.xy[node, 1])))
        return records


def evaluate(d, xy, thermal, router, choice, baselines, scenario=None):
    """Electrothermal fixed point, timing/thermal frequency bisection, analytic CPI."""
    c = d.c
    s = dict(power_scale=1., rc_scale=1., package_R=c["package_R_K_W"])
    s.update(scenario or {})
    route, length, vias = router.metrics(choice)
    bonds = router.assign_bonds(choice)
    # Rerouting to legal bond sites adds a conservative out-and-back Manhattan detour.
    for bond in bonds:
        length[bond["net_id"]] += 2*(abs(bond["x_mm"]-bond["pin_x_mm"])+abs(bond["y_mm"]-bond["pin_y_mm"]))
    cap = c["wire_C_pF_per_mm"]*length+vias*c["bond_C_pF"]
    net_power = cap*c["vdd_V"]**2*c["wire_activity"]*c["frequency_GHz"]*.001
    dyn = d.dynamic.copy()
    np.add.at(dyn, d.a, net_power/2); np.add.at(dyn, d.b, net_power/2)
    sp = splat(xy, d.z, c["die_mm"], thermal.g)
    size = 2*thermal.g**2
    def state(freq):
        temp_node = np.full(len(xy), c["leakage_reference_C"])
        residual = float("inf")
        for iteration in range(150):
            leak = d.leak*s["power_scale"]*np.exp(c["leakage_alpha_per_K"]*(temp_node-c["leakage_reference_C"]))
            power = dyn*s["power_scale"]*freq/c["frequency_GHz"]+leak
            pmap = deposit(power, sp, size)
            temp = c["ambient_C"]+thermal.apply(pmap, s["package_R"])
            new = (temp[sp[0]]*sp[1]).sum(1)
            residual = float(np.max(np.abs(new-temp_node)))
            if residual < 1e-6:
                break
            temp_node = .5*temp_node+.5*new
            if temp_node.max() > 250:
                raise ValueError("Electrothermal runaway in assumed model")
        if residual >= 1e-6:
            raise ValueError("Electrothermal fixed point did not converge")
        tnet = np.maximum(new[d.a], new[d.b])
        delay = d.logic_ns*(1+c["logic_delay_alpha_per_K"]*(tnet-60))
        delay += s["rc_scale"]*(c["wire_delay_ns_per_mm"]*length+c["wire_delay_ns_per_mm2"]*length**2+vias*c["bond_delay_ns"])*(1+c["wire_delay_alpha_per_K"]*(tnet-60))
        return power, temp, delay, residual, pmap
    nominal = state(c["frequency_GHz"])
    low, high = 0., c["frequency_GHz"]
    for _ in range(26):
        f = (low+high)/2
        p, t, delay, _, _ = state(f)
        if t.max() <= c["temperature_limit_C"] and delay.max()*f <= 1:
            low = f
        else:
            high = f
    f = low
    power, temp, delay, residual, pmap = state(f)
    if f < .1:
        raise ValueError("No usable operating point at or above 0.1 GHz")
    ipc, bips, linkcycles = {}, {}, {}
    l2mask = np.isin(d.module[d.a], [0, 1, d.mid["l2_ctl"]]) | np.isin(d.module[d.b], [0, 1, d.mid["l2_ctl"]])
    link_ns = float(np.quantile((delay-d.logic_ns)[l2mask], .95))
    cycles = max(1, math.ceil(link_ns*f))
    for run in baselines["runs"]:
        name = run["workload"]
        base_cpi = run["simulation"]["cpi"]
        memfraction = .35 if name == "stream" else .12
        accesses_per_inst = run["cache"]["l2"]["accesses"]/run["simulation"]["instructions"]
        cpi = base_cpi*(1-memfraction)+base_cpi*memfraction*f/c["frequency_GHz"]+accesses_per_inst*.25*(cycles-1)
        ipc[name], bips[name], linkcycles[name] = 1/cpi, f/cpi, cycles
    result = dict(**route, power_W=float(power.sum()), dynamic_W=float(dyn.sum()*s["power_scale"]*f/c["frequency_GHz"]),
                  peak_C=float(temp.max()), nominal_peak_C=float(nominal[1].max()),
                  nominal_power_W=float(nominal[0].sum()), frequency_GHz=float(f),
                  critical_delay_ns=float(delay.max()), nominal_WNS_ps=float((1/c["frequency_GHz"]-nominal[2].max())*1000),
                  nominal_TNS_ns=float(np.minimum(1/c["frequency_GHz"]-nominal[2], 0).sum()),
                  operating_WNS_ps=float((1/f-delay.max())*1000),
                  timing_path_proxy_count=len(length), total_wire_mm=float(length.sum()),
                  electrothermal_residual_C=residual, power_conservation_error_W=float(abs(pmap.sum()-power.sum())),
                  ipc_stream=ipc["stream"], ipc_matmul=ipc["matmul"], bips_stream=bips["stream"], bips_matmul=bips["matmul"],
                  mean_bips=float(np.mean(list(bips.values()))), l2_link_cycles=cycles,
                  energy_nJ_per_instruction=float(power.sum()/np.mean(list(bips.values()))),
                  feasible=bool(route["route_overflow_tracks"] == 0 and route["max_bond_bin_count"] <= route["bond_bin_capacity"] and temp.max() <= c["temperature_limit_C"] and 1/f >= delay.max()))
    return result, temp, bonds


def verify_gradients(d, thermal):
    placement = Placement(d, thermal, "balanced")
    xy = d.base_xy.copy()+np.where(d.movable[:, None], .00013, 0)
    xy = np.clip(xy, d.lower+.000001*d.movable[:, None], d.upper-.000001*d.movable[:, None])
    value, grad, _ = placement.objective(xy)
    rng = np.random.default_rng(81)
    errors = []
    for i in rng.choice(np.flatnonzero(d.movable), 20, replace=False):
        for dim in range(2):
            eps = 1e-7
            xp, xm = xy.copy(), xy.copy()
            xp[i, dim] += eps; xm[i, dim] -= eps
            numeric = (placement.objective(xp)[0]-placement.objective(xm)[0])/(2*eps)
            errors.append(abs(numeric-grad[i, dim])/max(1e-5, abs(numeric), abs(grad[i, dim])))
    router = Router(d, d.base_xy)
    logits = rng.normal(0, .3, (len(router.guide), 4))
    _, grad = router.loss_grad(logits)
    routing_errors = []
    for i in rng.choice(len(logits), 10, replace=False):
        xp, xm = logits.copy(), logits.copy()
        xp[i, 0] += 1e-5; xm[i, 0] -= 1e-5
        numeric = (router.loss_grad(xp)[0]-router.loss_grad(xm)[0])/(2e-5)
        routing_errors.append(abs(numeric-grad[i, 0])/max(1e-7, abs(numeric), abs(grad[i, 0])))
    assert max(errors) < .01, max(errors)
    assert max(routing_errors) < .01, max(routing_errors)
    test_power = rng.random(2*thermal.g**2)
    heat = thermal.apply(test_power)
    assert heat.min() > 0
    assert np.allclose(thermal.apply(2*test_power), 2*heat)
    check_legal(d, d.base_xy)
    return dict(placement_gradient_max_relative_error=max(errors), routing_gradient_max_relative_error=max(routing_errors),
                thermal_linearity=True, initial_legal=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT/"config.json")
    parser.add_argument("--output", type=Path, default=ROOT/"results")
    parser.add_argument("--steps", type=int)
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    c = json.loads(args.config.read_text(encoding="utf-8"))
    if args.steps is not None:
        c["placement_steps"] = c["routing_steps"] = args.steps
    if args.quick:
        c["cell_count_per_logic_module"] = 120
        c["placement_steps"] = c["routing_steps"] = 8
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    baseline_path = ROOT.parent/"gem5-c910-baseline/results/stats.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    thermal = Thermal(c)
    start = time.time()
    validation = verify_gradients(Design(c, "A_split"), thermal)
    print("Gradient and thermal tests:", validation, flush=True)
    rows, states = [], {}
    candidates = ["A_split", "B_critical_local", "C_hot_top"]
    for name in candidates:
        d = Design(c, name)
        write_csv(out/f"{name}_modules.csv", d.module_records())
        for profile in ["baseline", "routing_only", *PROFILES]:
            key = f"{name}__{profile}"
            if profile in ["baseline", "routing_only"]:
                xy = d.base_xy.copy()
                history, routehist = [], []
            else:
                xy, history = Placement(d, thermal, profile).optimize(c["placement_steps"])
                relaxed = xy.copy()
                xy = legalize(d, xy)
            router = Router(d, xy)
            if profile == "baseline":
                choice = router.baseline()
                softloss = None
            else:
                choice, routehist, softloss = router.optimize(c["routing_steps"])
            result, temp, bonds = evaluate(d, xy, thermal, router, choice, baseline)
            result.update(run=key, candidate=name, profile=profile, seed=0)
            rows.append(result)
            states[key] = (d, xy, choice, result)
            np.savez_compressed(out/f"{key}.npz", xy_mm=xy, tier=d.z, module_id=d.module,
                                movable=d.movable, edges=d.edges, guide_net_ids=router.guide, route_choice=choice,
                                temperature_C=temp.reshape(2, thermal.g, thermal.g))
            save_json(out/f"{key}_trace.json", dict(placement=history, routing=routehist, soft_routing_loss=softloss,
                         legalization_mean_move_um=float(np.linalg.norm(xy-relaxed, axis=1)[d.movable].mean()*1000) if profile in PROFILES else 0))
            print(f"{key}: {result['frequency_GHz']:.3f} GHz, {result['power_W']:.3f} W, {result['peak_C']:.2f} C, "
                  f"overflow={result['route_overflow_tracks']:.0f}, BIPS={result['mean_bips']:.3f}", flush=True)
    feasible = [r for r in rows if r["feasible"]]
    if not feasible:
        write_csv(out/"metrics.csv", rows)
        raise RuntimeError("No feasible discrete layout; see metrics.csv")
    # Decision rule declared in README: highest throughput, then energy, within feasible set.
    winner = max(feasible, key=lambda r: (r["mean_bips"], -r["energy_nJ_per_instruction"]))
    # Treat restarts as actual candidates, so a better restart cannot be discarded.
    restarts = []
    if winner["profile"] in PROFILES:
        d = states[winner["run"]][0]
        for seed in [17, 41]:
            sx, history = Placement(d, thermal, winner["profile"]).optimize(c["placement_steps"], seed)
            relaxed = sx.copy()
            sx = legalize(d, sx)
            sr = Router(d, sx)
            sc, routehist, softloss = sr.optimize(c["routing_steps"])
            result, temp, _ = evaluate(d, sx, thermal, sr, sc, baseline)
            key = f"{d.name}__{winner['profile']}__seed{seed}"
            result.update(run=key, candidate=d.name, profile=winner["profile"], seed=seed)
            rows.append(result); restarts.append(result)
            states[key] = (d, sx, sc, result)
            np.savez_compressed(out/f"{key}.npz", xy_mm=sx, tier=d.z, module_id=d.module,
                                movable=d.movable, edges=d.edges, guide_net_ids=sr.guide, route_choice=sc,
                                temperature_C=temp.reshape(2, thermal.g, thermal.g))
            save_json(out/f"{key}_trace.json", dict(placement=history, routing=routehist, soft_routing_loss=softloss,
                      legalization_mean_move_um=float(np.linalg.norm(sx-relaxed, axis=1)[d.movable].mean()*1000)))
            print(f"Restart {seed}: {result['mean_bips']:.3f} BIPS", flush=True)
        feasible = [r for r in rows if r["feasible"]]
        winner = max(feasible, key=lambda r: (r["mean_bips"], -r["energy_nJ_per_instruction"]))
    d, xy, choice, _ = states[winner["run"]]
    router = Router(d, xy)
    _, _, bonds = evaluate(d, xy, thermal, router, choice, baseline)
    if bonds:
        write_csv(out/"best_bonds.csv", bonds)
    cell_records = [dict(cell_id=i, module=d.mods[d.module[i]]["name"], tier=int(d.z[i]),
                         kind="standard_cell" if d.movable[i] else "fixed_macro_port_power_sample",
                         x_mm=float(xy[i, 0]), y_mm=float(xy[i, 1])) for i in range(len(xy))]
    write_csv(out/"best_cells.csv", cell_records)
    write_csv(out/"best_route_guides.csv", [dict(net_id=int(i), trunk_tier=int(k//2), bend="XY" if k%2 == 0 else "YX",
                endpoint_a=int(d.a[i]), endpoint_b=int(d.b[i])) for i, k in zip(router.guide, choice)])
    # Re-evaluate each candidate's best throughput layout under shared physical perturbations.
    sensitivity = []
    scenarios = {"nominal": {}, "power_minus20": {"power_scale": .8}, "power_plus20": {"power_scale": 1.2},
                 "rc_minus25": {"rc_scale": .75}, "rc_plus25": {"rc_scale": 1.25},
                 "cooling_good": {"package_R": 2.5}, "cooling_poor": {"package_R": 5.0},
                 "combined_stress": {"power_scale": 1.2, "rc_scale": 1.25, "package_R": 5.0}}
    for name in candidates:
        eligible = [r for r in feasible if r["candidate"] == name]
        if not eligible:
            continue
        r = max(eligible, key=lambda r: r["mean_bips"])
        sd, sx, sc, _ = states[r["run"]]
        sr = Router(sd, sx)
        for sn, parameters in scenarios.items():
            result, _, _ = evaluate(sd, sx, thermal, sr, sc, baseline, parameters)
            sensitivity.append(dict(scenario=sn, run=r["run"], **result))
    # Thermal grid refinement is a validation, not an optimization rerun.
    fine, _, _ = evaluate(d, xy, Thermal(c, 32), router, choice, baseline)
    validation.update(thermal_grid_16_to_32_peak_delta_C=fine["peak_C"]-winner["peak_C"],
                      thermal_grid_16_to_32_frequency_delta_GHz=fine["frequency_GHz"]-winner["frequency_GHz"],
                      fine_grid_metrics=fine, all_saved_placements_legal=True,
                      max_power_conservation_error_W=max(r["power_conservation_error_W"] for r in rows))
    write_csv(out/"metrics.csv", rows)
    write_csv(out/"sensitivity.csv", sensitivity)
    if restarts:
        write_csv(out/"restarts.csv", restarts)
    pareto = [r["run"] for r in feasible if not any(
        other["mean_bips"] >= r["mean_bips"] and other["power_W"] <= r["power_W"] and other["peak_C"] <= r["peak_C"]
        and (other["mean_bips"] > r["mean_bips"] or other["power_W"] < r["power_W"] or other["peak_C"] < r["peak_C"])
        for other in feasible)]
    manifest = dict(track=c["track"], status="synthetic_proxy_only", config=c, numpy=np.__version__, python=platform.python_version(),
                    baseline_sha256=hashlib.sha256(baseline_path.read_bytes()).hexdigest(),
                    source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    elapsed_seconds=time.time()-start, standard_cells=int(d.movable.sum()),
                    fixed_macro_samples=int((~d.movable).sum()), two_pin_nets=len(d.edges), winner=winner,
                    pareto=pareto, validation=validation, sensitivity_scenarios=scenarios,
                    decision_rule="Among discrete feasible layouts maximize equally weighted STREAM/MATMUL BIPS; then minimize energy/instruction.")
    save_json(out/"manifest.json", manifest)
    print("Saved", out, "winner", winner["run"], "elapsed", round(time.time()-start, 1), flush=True)


if __name__ == "__main__":
    main()
