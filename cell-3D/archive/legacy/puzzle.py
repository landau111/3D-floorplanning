"""Differentiable nonrectangular territory allocation and cell refinement.

Extends the saved synthetic experiment without changing its physical/netlist inputs.
Only NumPy. Shape gradients are analytical and numerically checked.
"""
import csv
import hashlib
import json
import time
from collections import deque
from pathlib import Path
import numpy as np
from simulate import (Design, Placement, Thermal, Router, evaluate, splat, deposit,
                      adjoint, softmax, save_json, write_csv, PROFILES)

ROOT = Path(__file__).resolve().parent


def components(mask):
    """4-neighbor components on a binary 2D grid."""
    seen = np.zeros_like(mask, bool)
    result = []
    h, w = mask.shape
    for sy, sx in zip(*np.nonzero(mask)):
        if seen[sy, sx]:
            continue
        queue = deque([(int(sy), int(sx))]); seen[sy, sx] = True
        group = []
        while queue:
            y, x = queue.popleft(); group.append((y, x))
            for yy, xx in [(y-1,x),(y+1,x),(y,x-1),(y,x+1)]:
                if 0 <= yy < h and 0 <= xx < w and mask[yy,xx] and not seen[yy,xx]:
                    seen[yy,xx] = True; queue.append((yy,xx))
        result.append(group)
    return sorted(result, key=len, reverse=True)


class Territory:
    def __init__(self, d, cfg, thermal):
        self.d, self.cfg, self.thermal = d, cfg, thermal
        self.g = cfg["shape_grid"]
        self.step = d.c["die_mm"]/self.g
        grid = np.indices((self.g,self.g)).transpose(1,2,0)
        self.gridxy = grid[..., ::-1]
        self.allxy = (self.gridxy+.5)*self.step
        self.free = np.ones((2,self.g,self.g), bool)
        for tier, name in enumerate(["l2_b0","l2_b1"]):
            x,y,w,h = d.regions[name]; halo = cfg["macro_keepout_mm"]
            # Reject any coarse tile with positive overlap with macro/keepout.
            lo, hi = self.allxy-self.step/2, self.allxy+self.step/2
            blocked = ((hi[...,0] > x-halo+1e-10)&(lo[...,0] < x+w+halo-1e-10)&
                       (hi[...,1] > y-halo+1e-10)&(lo[...,1] < y+h+halo-1e-10))
            self.free[tier,blocked] = False
        self.modules = [[i for i,m in enumerate(d.mods) if m["kind"]=="logic" and d.module_tier[m["name"]]==z] for z in range(2)]
        self.points = [self.allxy[self.free[z]] for z in range(2)]
        self.free_indices = [np.flatnonzero(self.free[z]) for z in range(2)]
        self.initial_centers = np.array([[[d.regions[d.mods[i]["name"]][0]+.17,
                                           d.regions[d.mods[i]["name"]][1]+.17] for i in ms] for ms in self.modules])
        self.targets = [np.full(len(ms), 1/len(ms)) for ms in self.modules]
        self.powers = [np.array([d.mods[i]["dynamic_W"]+d.mods[i]["leakage_W"] for i in ms]) for ms in self.modules]
        self.index = {mi:(z,j) for z,ms in enumerate(self.modules) for j,mi in enumerate(ms)}
        self.links = []
        total = sum(n for _,_,n in d.c["connections"])
        for a,b,n in d.c["connections"]:
            self.links.append((d.mid[a],d.mid[b],n/total))
        self.sp = [splat(self.points[z], np.full(len(self.points[z]),z),d.c["die_mm"],thermal.g) for z in range(2)]
        self.fixed_macro_power = deposit(np.where(d.movable,0,d.dynamic+d.leak),
                    splat(d.xy,d.z,d.c["die_mm"],thermal.g),2*thermal.g**2)
        self.neighbor_edges = []
        for z in range(2):
            remap = np.full(self.g*self.g,-1); remap[self.free_indices[z]] = np.arange(len(self.points[z]))
            edges = []
            for y,x in zip(*np.nonzero(self.free[z])):
                for yy,xx in [(y+1,x),(y,x+1)]:
                    if yy < self.g and xx < self.g and self.free[z,yy,xx]:
                        edges.append((remap[y*self.g+x],remap[yy*self.g+xx]))
            self.neighbor_edges.append(np.array(edges,int))

    def objective(self, centers, weights, tau):
        cfg = self.cfg
        q, diff, dist, areas, centroids = [], [], [], [], []
        gradq, gradc = [], np.zeros_like(centers)
        loss = 0.
        info = {}
        for z in range(2):
            r = self.points[z]
            delta = r[:,None,:]-centers[z][None,:,:]
            distance = (delta**2).sum(2)
            prob = softmax((weights[z][None,:]-distance)/tau)
            q.append(prob); diff.append(delta); dist.append(distance)
            area = prob.sum(0); areas.append(area)
            ctr = prob.T@r/area[:,None]; centroids.append(ctr)
            rel = area/len(r)-self.targets[z]
            Larea = cfg["area_weight"]*np.sum((rel/self.targets[z])**2)
            gp = np.broadcast_to(2*cfg["area_weight"]*rel/self.targets[z]**2/len(r),prob.shape).copy()
            Lcompact = cfg["compact_weight"]*np.sum(prob*distance)/len(r)
            gp += cfg["compact_weight"]*distance/len(r)
            gradc[z] += -2*cfg["compact_weight"]*(prob[:,:,None]*delta).sum(0)/len(r)
            a,b = self.neighbor_edges[z].T
            edge_diff = prob[a]-prob[b]
            Lboundary = cfg["boundary_weight"]*np.mean((edge_diff**2).sum(1))
            fg = 2*cfg["boundary_weight"]*edge_diff/len(a)
            np.add.at(gp,a,fg); np.add.at(gp,b,-fg)
            anchor = centers[z]-self.initial_centers[z]
            Lanchor = cfg["anchor_weight"]*np.mean(anchor**2)
            gradc[z] += 2*cfg["anchor_weight"]*anchor/anchor.size
            loss += Larea+Lcompact+Lboundary+Lanchor
            gradq.append(gp)
            info[f"area_relative_error_tier{z}"] = float(np.max(abs(rel/self.targets[z])))
        centroids = np.array(centroids)
        gc = np.zeros_like(centroids)
        Lwire = 0.
        def center(mi):
            if mi in self.index:
                z,j = self.index[mi]; return centroids[z,j]
            x,y,w,h = self.d.regions[self.d.mods[mi]["name"]]
            return np.array([x+w/2,y+h/2])
        for a,b,n in self.links:
            delta = center(a)-center(b)
            smooth = np.sqrt(delta**2+.02**2)
            Lwire += cfg["connectivity_weight"]*n*smooth.sum()
            force = cfg["connectivity_weight"]*n*delta/smooth
            if a in self.index:
                z,j = self.index[a]; gc[z,j] += force
            if b in self.index:
                z,j = self.index[b]; gc[z,j] -= force
        for z in range(2):
            gradq[z] += np.einsum("gmk,mk->gm",self.points[z][:,None,:]-centroids[z][None,:,:],gc[z])/areas[z]
        pmap = self.fixed_macro_power.copy()
        for z in range(2):
            pmap += deposit(q[z]@(self.powers[z]/areas[z]), self.sp[z], len(pmap))
        temp = self.d.c["ambient_C"]+self.thermal.apply(pmap)
        heat_loss = cfg["heat_weight"]*(2*np.log(np.exp((temp-temp.max())/2).sum())+temp.max()-self.d.c["ambient_C"])/40
        field = self.thermal.apply(cfg["heat_weight"]*softmax(temp/2)/40)
        for z in range(2):
            f = (field[self.sp[z][0]]*self.sp[z][1]).sum(1)
            meanf = (q[z]*f[:,None]).sum(0)/areas[z]
            gradq[z] += (f[:,None]-meanf)*self.powers[z]/areas[z]
        gw = np.zeros_like(weights)
        for z in range(2):
            gs = q[z]*(gradq[z]-(gradq[z]*q[z]).sum(1,keepdims=True))/tau
            gw[z] = gs.sum(0)
            gradc[z] += (gs[:,:,None]*2*diff[z]).sum(0)
        loss += Lwire+heat_loss
        info.update(loss=float(loss), wire=float(Lwire), heat=float(heat_loss))
        return loss,gradc,gw,q,info

    def optimize(self):
        c = self.initial_centers.copy(); w = np.zeros(c.shape[:2])
        # Area-balanced centroid initialization: dual ascent on area prices, then
        # a relaxed centroid step (preconditioned gradient of fixed-q compactness).
        warmup=[]
        for it in range(self.cfg["centroid_warmup_steps"]):
            for z in range(2):
                distance=((self.points[z][:,None,:]-c[z][None,:,:])**2).sum(2)
                for _ in range(self.cfg["area_balance_inner_steps"]):
                    prob=softmax((w[z][None,:]-distance)/.02)
                    w[z]+=self.cfg["area_dual_step_mm2"]*(self.targets[z]-prob.mean(0))
                centroid=prob.T@self.points[z]/prob.sum(0)[:,None]
                alpha=self.cfg["centroid_relaxation"]
                c[z]=(1-alpha)*c[z]+alpha*centroid
            if it%10==0:
                warmup.append(dict(iteration=it,centers=c.tolist()))
        mc,vc,mw,vw = np.zeros_like(c),np.zeros_like(c),np.zeros_like(w),np.zeros_like(w)
        hist = []
        for i in range(self.cfg["shape_steps"]):
            frac = i/max(1,self.cfg["shape_steps"]-1)
            tau = self.cfg["shape_tau_start_mm2"]*(self.cfg["shape_tau_end_mm2"]/self.cfg["shape_tau_start_mm2"])**frac
            loss,gc,gw,q,info = self.objective(c,w,tau)
            mc=.9*mc+.1*gc; vc=.999*vc+.001*gc**2
            mw=.9*mw+.1*gw; vw=.999*vw+.001*gw**2
            lr=self.cfg["shape_learning_rate"]*(1-.7*frac)
            c -= lr*(mc/(1-.9**(i+1)))/(np.sqrt(vc/(1-.999**(i+1)))+1e-9)
            w -= lr*.3*(mw/(1-.9**(i+1)))/(np.sqrt(vw/(1-.999**(i+1)))+1e-9)
            c = np.clip(c,self.step/2,self.d.c["die_mm"]-self.step/2)
            w -= w.mean(axis=1,keepdims=True)
            if i%20==0 or i==self.cfg["shape_steps"]-1:
                hist.append(dict(iteration=i,tau=tau,**info))
        _,_,_,q,info=self.objective(c,w,self.cfg["shape_tau_end_mm2"])
        labels=np.full(self.free.shape,-1,int)
        repairs=0
        for z in range(2):
            lab=np.full((self.g,self.g),-1,int)
            lab.ravel()[self.free_indices[z]]=np.argmax(q[z],1)
            # Keep largest component of each module, regrow detached pieces from connected neighbors.
            for j in range(len(self.modules[z])):
                groups=components(lab==j)
                if not groups:
                    raise ValueError("Empty hard module territory")
                for group in groups[1:]:
                    for y,x in group:
                        lab[y,x]=-2; repairs+=1
            while np.any(lab==-2):
                candidates=[]
                for y,x in zip(*np.nonzero(lab==-2)):
                    adj=set(lab[yy,xx] for yy,xx in [(y-1,x),(y+1,x),(y,x-1),(y,x+1)] if 0<=yy<self.g and 0<=xx<self.g and lab[yy,xx]>=0)
                    for j in adj:
                        score=np.sum((self.allxy[y,x]-c[z,j])**2)-w[z,j]
                        candidates.append((score,y,x,j))
                if not candidates: raise ValueError("Detached unassignable free region")
                _,y,x,j=min(candidates); lab[y,x]=j
            for j,mi in enumerate(self.modules[z]): labels[z,lab==j]=mi
        checks=self.validate(labels)
        return labels,hist,checks,dict(centers=c.tolist(),weights=w.tolist(),repaired_tiles=repairs,centroid_warmup=warmup)

    def validate(self, labels):
        assert np.array_equal(labels>=0,self.free), "Territories must partition all free tiles"
        records=[]
        for z in range(2):
            target=self.free[z].sum()/len(self.modules[z])
            for mi in self.modules[z]:
                mask=labels[z]==mi
                groups=components(mask)
                yy,xx=np.nonzero(mask)
                n=len(xx)
                perimeter=0
                for y,x in zip(yy,xx):
                    perimeter+=sum(not(0<=v<self.g and 0<=u<self.g and mask[v,u]) for v,u in [(y-1,x),(y+1,x),(y,x-1),(y,x+1)])
                complement=components(~mask)
                holes=sum(not any(y==0 or x==0 or y==self.g-1 or x==self.g-1 for y,x in group) for group in complement)
                bboxw,bboxh=xx.max()-xx.min()+1,yy.max()-yy.min()+1
                aspect=max(bboxw/bboxh,bboxh/bboxw)
                compactness=perimeter**2/(16*n)
                areaerr=abs(n/target-1)
                ok=(len(groups)==1 and holes==0 and aspect<=self.cfg["max_bbox_aspect"] and
                    compactness<=self.cfg["max_grid_compactness"] and areaerr<=self.cfg["max_area_relative_error"])
                records.append(dict(module=self.d.mods[mi]["name"],tier=z,tiles=n,area_mm2=n*self.step**2,
                                    components=len(groups),holes=holes,bbox_aspect=aspect,grid_compactness=compactness,
                                    area_relative_error=float(areaerr),shape_valid=bool(ok)))
        if not all(r["shape_valid"] for r in records):
            raise ValueError("Shape constraints violated: "+str([r for r in records if not r["shape_valid"]]))
        return records


class PuzzlePlacement:
    def __init__(self,d,territory,labels,cfg,profile):
        self.d,self.territory,self.labels,self.cfg=d,territory,labels,cfg
        self.g,self.step=territory.g,territory.step
        self.w=d.c["cell_width_um"]/1000; self.h=d.c["cell_height_um"]/1000
        self.nx=round(d.c["die_mm"]/self.w); self.ny=round(d.c["die_mm"]/self.h)
        sx=(np.arange(self.nx)+.5)*self.w; sy=(np.arange(self.ny)+.5)*self.h
        gx=np.minimum((sx/self.step).astype(int),self.g-1); gy=np.minimum((sy/self.step).astype(int),self.g-1)
        self.site_owner=labels[:,gy[:,None],gx[None,:]]
        self.nearest={}
        for z in range(2):
            for mi in territory.modules[z]:
                valid=np.argwhere(labels[z]==mi)[:,::-1]
                grid=territory.gridxy.reshape(-1,2)
                dist=((grid[:,None,:]-valid[None,:,:])**2).sum(2)
                self.nearest[mi]=valid[dist.argmin(1)]
        # Same netlist and hard macros; replace old rectangle clipping by die bounds.
        d.lower[d.movable]=[self.w/2,self.h/2]
        d.upper[d.movable]=[d.c["die_mm"]-self.w/2,d.c["die_mm"]-self.h/2]
        self.core=Placement(d,territory.thermal,profile)
        tg=territory.thermal.g
        target=np.zeros(2*tg*tg)
        for z in range(2):
            point_density=np.zeros(len(territory.points[z]))
            flatlab=labels[z].ravel()[territory.free_indices[z]]
            for mi in territory.modules[z]:
                sel=flatlab==mi
                point_density[sel]=len(d.ids[d.mods[mi]["name"]])*self.w*self.h/sel.sum()
            target+=deposit(point_density,territory.sp[z],len(target))
        self.target_density=target/self.core.bin_area

    def initial(self):
        xy=self.d.base_xy.copy(); rng=np.random.default_rng(self.cfg["seed"])
        for z in range(2):
            for mi in self.territory.modules[z]:
                ids=self.d.ids[self.d.mods[mi]["name"]]
                yy,xx=np.nonzero(self.site_owner[z]==mi)
                picks=rng.choice(len(xx),len(ids),replace=False)
                sites=np.column_stack([(xx[picks]+.5)*self.w,(yy[picks]+.5)*self.h])
                ids=ids[np.lexsort((xy[ids,0],xy[ids,1]))]
                xy[ids]=sites[np.lexsort((sites[:,0],sites[:,1]))]
        return xy

    def project(self,xy):
        out=xy.copy()
        for z in range(2):
            for mi in self.territory.modules[z]:
                ids=self.d.ids[self.d.mods[mi]["name"]]
                tile=np.clip((out[ids]/self.step).astype(int),0,self.g-1)
                outside=self.labels[z,tile[:,1],tile[:,0]]!=mi
                tile[outside]=self.nearest[mi][tile[outside,1]*self.g+tile[outside,0]]
                lo=tile*self.step+[self.w/2,self.h/2]
                hi=(tile+1)*self.step-[self.w/2,self.h/2]
                out[ids]=np.clip(out[ids],lo,hi)
        out[~self.d.movable]=self.d.base_xy[~self.d.movable]
        return out

    def objective(self,xy):
        value,grad,info=self.core.objective(xy)
        sp=splat(xy,self.d.z,self.d.c["die_mm"],self.core.g)
        rho=deposit(self.core.area,sp,self.core.size)/self.core.bin_area
        delta=rho-self.target_density
        uniform=self.cfg["uniform_density_weight"]*np.mean(delta**2)
        grad+=adjoint(self.core.area,sp,2*self.cfg["uniform_density_weight"]*delta/(self.core.size*self.core.bin_area))
        grad[~self.d.movable]=0
        return value+uniform,grad,dict(**info,uniform=float(uniform),total_loss=float(value+uniform))

    def optimize(self):
        xy=self.initial(); start=xy.copy()
        mom,vel=np.zeros_like(xy),np.zeros_like(xy)
        best,bestloss=xy.copy(),float("inf")
        history=[]
        for i in range(self.cfg["cell_steps"]+1):
            loss,grad,info=self.objective(xy)
            if loss<bestloss: best,bestloss=xy.copy(),loss
            if i%20==0 or i==self.cfg["cell_steps"]:
                history.append(dict(iteration=i,**info))
            if i==self.cfg["cell_steps"]: break
            mom=.9*mom+.1*grad; vel=.999*vel+.001*grad**2
            lr=self.cfg["cell_learning_rate_mm"]*(1-.8*i/self.cfg["cell_steps"])
            xy=self.project(xy-lr*(mom/(1-.9**(i+1)))/(np.sqrt(vel/(1-.999**(i+1)))+1e-9))
        legalized=self.legalize(best)
        return legalized,start,history,float(np.linalg.norm(legalized-best,axis=1)[self.d.movable].mean()*1000)

    def legalize(self,xy):
        out=xy.copy(); used=np.zeros_like(self.site_owner,bool)
        for z in range(2):
            for mi in self.territory.modules[z]:
                ids=self.d.ids[self.d.mods[mi]["name"]]
                for i in ids[np.lexsort((xy[ids,0],xy[ids,1]))]:
                    cx=int(np.clip(round(xy[i,0]/self.w-.5),0,self.nx-1))
                    cy=int(np.clip(round(xy[i,1]/self.h-.5),0,self.ny-1))
                    r=0
                    while True:
                        x0,x1=max(0,cx-r),min(self.nx,cx+r+1)
                        y0,y1=max(0,cy-r),min(self.ny,cy+r+1)
                        yy,xx=np.nonzero((self.site_owner[z,y0:y1,x0:x1]==mi)&~used[z,y0:y1,x0:x1])
                        if len(xx):
                            xx+=x0; yy+=y0
                            ds=((xx+.5)*self.w-xy[i,0])**2+((yy+.5)*self.h-xy[i,1])**2
                            k=ds.argmin(); cx,cy=xx[k],yy[k]; break
                        r+=1
                        if r>max(self.nx,self.ny):raise ValueError("No legal site in module territory")
                    used[z,cy,cx]=True; out[i]=[(cx+.5)*self.w,(cy+.5)*self.h]
        self.validate(out)
        return out

    def validate(self,xy):
        d=self.d
        assert np.allclose(xy[~d.movable],d.base_xy[~d.movable])
        for z in range(2):
            ids=np.flatnonzero(d.movable&(d.z==z))
            coords=xy[ids]/[self.w,self.h]-.5
            assert np.max(abs(coords-np.rint(coords)))<1e-7
            xx,yy=np.rint(coords).astype(int).T
            assert len(np.unique(yy*self.nx+xx))==len(ids)
            assert np.all(self.site_owner[z,yy,xx]==d.module[ids])
        return True


def test_shape_gradient(t):
    ctr=t.initial_centers.copy(); weights=np.zeros(ctr.shape[:2]); tau=.04
    loss,gc,gw,_,_=t.objective(ctr,weights,tau)
    errors=[]
    for z,j,k in [(0,1,0),(0,5,1),(1,2,0),(1,6,1)]:
        a,b=ctr.copy(),ctr.copy(); a[z,j,k]+=1e-6;b[z,j,k]-=1e-6
        num=(t.objective(a,weights,tau)[0]-t.objective(b,weights,tau)[0])/2e-6
        errors.append(abs(num-gc[z,j,k])/max(1e-6,abs(num),abs(gc[z,j,k])))
    for z,j in [(0,0),(0,6),(1,3),(1,5)]:
        a,b=weights.copy(),weights.copy();a[z,j]+=1e-6;b[z,j]-=1e-6
        num=(t.objective(ctr,a,tau)[0]-t.objective(ctr,b,tau)[0])/2e-6
        errors.append(abs(num-gw[z,j])/max(1e-6,abs(num),abs(gw[z,j])))
    assert max(errors)<.005,errors
    return float(max(errors))


def main():
    start=time.time()
    old=json.loads((ROOT/"results/manifest.json").read_text(encoding="utf-8"))
    c=old["config"]
    cfg=json.loads((ROOT/"puzzle_config.json").read_text(encoding="utf-8"))
    out=ROOT/"puzzle_results";out.mkdir(exist_ok=True)
    thermal=Thermal(c)
    base=Design(c,cfg["base_candidate"])
    territory=Territory(base,cfg,thermal)
    err=test_shape_gradient(territory)
    print("Shape gradient max relative error",err,flush=True)
    labels,hist,shapes,shapevars=territory.optimize()
    write_csv(out/"module_shapes.csv",shapes)
    save_json(out/"shape_trace.json",hist)
    print("Territories: all connected, no holes; max compactness",max(r["grid_compactness"] for r in shapes),flush=True)
    baselines=json.loads((ROOT.parent/"gem5-c910-baseline/results/stats.json").read_text(encoding="utf-8"))
    rows=[];saved={}
    for profile in cfg["profiles"]:
        d=Design(c,cfg["base_candidate"])
        placement=PuzzlePlacement(d,territory,labels,cfg,profile)
        xy,initial,history,legal_move=placement.optimize()
        router=Router(d,xy)
        choice,rhist,_=router.optimize(c["routing_steps"])
        result,temp,bonds=evaluate(d,xy,thermal,router,choice,baselines)
        result.update(run="puzzle__"+profile,profile=profile,legalization_mean_move_um=legal_move)
        old_regions=Design(c,cfg["base_candidate"]).regions
        outside=0
        for mod in d.mods:
            if mod["kind"]!="logic": continue
            ids=d.ids[mod["name"]];x,y,w,h=old_regions[mod["name"]]
            outside+=np.sum((xy[ids,0]<x)|(xy[ids,0]>x+w)|(xy[ids,1]<y)|(xy[ids,1]>y+h))
        result["cells_outside_old_rectangle"]=int(outside)
        rows.append(result); saved[result["run"]]=(d,placement,xy,choice,bonds)
        np.savez_compressed(out/(result["run"]+".npz"),xy_mm=xy,initial_xy_mm=initial,tier=d.z,module_id=d.module,movable=d.movable,
                            edges=d.edges,labels=labels,guide_net_ids=router.guide,route_choice=choice,temperature_C=temp.reshape(2,thermal.g,thermal.g))
        save_json(out/(result["run"]+"_trace.json"),dict(placement=history,routing=rhist))
        print(result["run"],"BIPS",round(result["mean_bips"],3),"GHz",round(result["frequency_GHz"],3),
              "Tmax",round(result["peak_C"],2),"overflow",result["route_overflow_tracks"],"outside old fences",outside,flush=True)
    write_csv(out/"metrics.csv",rows)
    valid=[r for r in rows if r["feasible"]]
    if not valid:raise ValueError("No physically feasible puzzle candidate")
    winner=max(valid,key=lambda r:(r["mean_bips"],-r["energy_nJ_per_instruction"]))
    d,placement,xy,choice,bonds=saved[winner["run"]]
    if bonds:write_csv(out/"best_bonds.csv",bonds)
    write_csv(out/"best_cells.csv",[dict(cell_id=i,module=d.mods[d.module[i]]["name"],tier=int(d.z[i]),movable=bool(d.movable[i]),x_mm=float(xy[i,0]),y_mm=float(xy[i,1])) for i in range(len(xy))])
    fine,_,_=evaluate(d,xy,Thermal(c,32),Router(d,xy),choice,baselines)
    save_json(out/"manifest.json",dict(config=cfg,physical_config=c,winner=winner,shape_variables=shapevars,
                shape_gradient_max_relative_error=err,territory_coverage=1.0,free_area_mm2=float(territory.free.sum()*territory.step**2),
                actual_standard_cell_area_mm2=float(d.movable.sum()*placement.w*placement.h),
                free_area_cell_utilization=float(d.movable.sum()*placement.w*placement.h/(territory.free.sum()*territory.step**2)),
                fine_grid_peak_delta_C=fine["peak_C"]-winner["peak_C"],fine_grid_frequency_delta_GHz=fine["frequency_GHz"]-winner["frequency_GHz"],
                shape_checks=shapes,all_cells_legal=True,elapsed_seconds=time.time()-start,
                source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                original_simulator_sha256=hashlib.sha256((ROOT/"simulate.py").read_bytes()).hexdigest()))
    print("Saved puzzle results",winner["run"],"elapsed",time.time()-start,flush=True)


if __name__=="__main__":main()
