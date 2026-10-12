"""Portable CPU cell placement for the user's original layout-summary format.

Python 3.9+, NumPy 1.24+. No historical results, GPU, fonts or machine paths.
Module power/connectivity come from annealing YAML; placement comes from config.
"""
import os
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
import argparse
import csv
import datetime
import hashlib
import json
import math
import platform
import shutil
import sys
import time
from collections import deque
from pathlib import Path
try:
    import numpy as np
except ImportError:
    raise SystemExit("NumPy missing. Use the Windows offline package, or: python -m pip install -r requirements.txt")
from layout_input import read_layout, read_auxiliary

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PROJECT_ANNEALING=ROOT.parent/"folding_dse/folding_dse_annealing_cfg.yaml"
DEFAULT_ANNEALING=PROJECT_ANNEALING if PROJECT_ANNEALING.is_file() else ROOT/"configs/folding_dse_annealing_cfg.yaml"
DEFAULTS = dict(cell_width_um=8.0,cell_height_um=4.0,initial_utilization=0.65,
    ambient_C=26.85,nominal_GHz=2.0,vdd_V=0.8,wire_C_pF_mm=0.20,activity=0.12,
    wire_delay_ns_mm=0.11,wire_delay_ns_mm2=0.04,bond_delay_ns=0.014,bond_C_pF=0.004,
    thermal_grid=16,lateral_G=0.008,vertical_G_at_16=0.012,sink_G_at_16=0.025,
    common_R_K_W=12.0,temperature_limit_C=95.0,tracks_per_mm=12000.0,
    shape_grid_pitch_um=20.0,minimum_region_neck_tiles=3,
    macro_keepout_mm=0.004,max_bbox_aspect=3.0,max_compactness=2.5,
    max_area_error=0.25,wire_temp_alpha=0.002,logic_temp_alpha=0.0012,
    reference_temperature_C=27.0,cell_padding_um=1.0,cts_reserve_row_fraction=0.10,
    density_upper_bound=0.70)
PROFILES={"balanced":(1.0,.45),"timing":(1.8,.12),"thermal":(.45,1.2)}


def save_json(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")


def write_csv(path,rows):
    if not rows:
        return
    with Path(path).open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def softmax(x):
    exp=np.exp(x-np.max(x,axis=-1,keepdims=True))
    return exp/exp.sum(axis=-1,keepdims=True)


def smoothmax(x,tau):
    return float(x.max()+tau*np.log(np.exp((x-x.max())/tau).sum()))


def splat(xy,z,extent,g):
    u0=xy*g/extent-.5;u=np.clip(u0,0,g-1-1e-9);ij=np.floor(u).astype(int)
    fx,fy=(u-ij).T;ix,iy=ij.T
    idx=np.stack([z*g*g+iy*g+ix,z*g*g+iy*g+ix+1,z*g*g+(iy+1)*g+ix,z*g*g+(iy+1)*g+ix+1],1)
    weights=np.stack([(1-fx)*(1-fy),fx*(1-fy),(1-fx)*fy,fx*fy],1)
    dx=np.stack([-(1-fy),1-fy,-fy,fy],1)*g/extent[0]
    dy=np.stack([-(1-fx),-fx,1-fx,fx],1)*g/extent[1]
    dx*=((u0[:,0]>0)&(u0[:,0]<g-1))[:,None]
    dy*=((u0[:,1]>0)&(u0[:,1]<g-1))[:,None]
    return idx,weights,dx,dy


def deposit(values,sp,size):
    return np.bincount(sp[0].ravel(),weights=(values[:,None]*sp[1]).ravel(),minlength=size)


def adjoint(values,sp,field):
    vals=field[sp[0]]*values[:,None]
    return np.column_stack([(vals*sp[2]).sum(1),(vals*sp[3]).sum(1)])


def sample(field,sp):
    return (field[sp[0]]*sp[1]).sum(1)


def groups(mask):
    ny,nx=mask.shape;seen=np.zeros_like(mask,bool);result=[]
    for y,x in zip(*np.nonzero(mask)):
        if seen[y,x]:continue
        q=deque([(int(y),int(x))]);seen[y,x]=True;group=[]
        while q:
            yy,xx=q.popleft();group.append((yy,xx))
            for v,u in ((yy-1,xx),(yy+1,xx),(yy,xx-1),(yy,xx+1)):
                if 0<=v<ny and 0<=u<nx and mask[v,u] and not seen[v,u]:
                    seen[v,u]=True;q.append((v,u))
        result.append(group)
    return sorted(result,key=len,reverse=True)


class Heat:
    """Symmetric rectangular two-tier resistance proxy, not HotSpot."""
    def __init__(self,d,g=None):
        self.g=g or d.settings["thermal_grid"];self.d=d;g=self.g;s=d.settings
        lap=np.diag(np.r_[1,np.full(g-2,2),1])-np.eye(g,k=1)-np.eye(g,k=-1)
        eig,self.U=np.linalg.eigh(lap)
        w,h=d.extent
        lat=s["lateral_G"]*(eig[:,None]*w/h+eig[None,:]*h/w)
        gv=s["vertical_G_at_16"]*(16/g)**2*w*h/2.56
        gs=s["sink_G_at_16"]*(16/g)**2*w*h/2.56
        a,b=lat+gv,lat+gv+gs;det=a*b-gv*gv
        self.aa,self.bb,self.ab=b/det,a/det,gv/det
    def apply(self,p):
        p=p.reshape(2,self.g,self.g);q=self.U.T@p@self.U
        t=np.stack([self.aa*q[0]+self.ab*q[1],self.ab*q[0]+self.bb*q[1]])
        return (self.U@t@self.U.T+self.d.settings["common_R_K_W"]*p.sum()).ravel()


class Model:
    def __init__(self,config,auxiliary,settings,seed):
        self.config,self.aux,self.settings=config,auxiliary,settings
        self.mods=config["modules"];self.names=[m["name"] for m in self.mods]
        self.mid={n:i for i,n in enumerate(self.names)};self.extent=np.array([config["width_mm"],config["height_mm"]])
        self.rng=np.random.default_rng(seed);self.w=settings["cell_width_um"]/1000;self.h=settings["cell_height_um"]/1000
        self.slot=self.w+2*settings["cell_padding_um"]/1000
        if min(self.w,self.h)<=0 or self.w>=self.extent[0] or self.h>=self.extent[1]:raise ValueError("Invalid cell size")
        xy=[];module=[];tier=[];movable=[];self.ids=[]
        for mi,m in enumerate(self.mods):
            x,y,w,h=m["rect_mm"]
            if m["hard"]:
                xx,yy=np.meshgrid(np.linspace(x+w/16,x+15*w/16,8),np.linspace(y+h/16,y+15*h/16,8))
                pos=np.column_stack([xx.ravel(),yy.ravel()])
            else:
                nx,ny=math.floor(self.extent[0]/self.slot+1e-9),math.floor(self.extent[1]/self.h+1e-9)
                sx=np.arange(nx)*self.slot+self.slot/2;sy=np.arange(ny)*self.h+self.h/2
                xs=np.flatnonzero((sx-self.w/2>=x-1e-10)&(sx+self.w/2<=x+w+1e-10))
                ys=np.flatnonzero((sy-self.h/2>=y-1e-10)&(sy+self.h/2<=y+h+1e-10))
                period=max(2,round(1/settings["cts_reserve_row_fraction"]))
                ys=ys[ys%period!=period-1]
                count=max(1,round(w*h*settings["initial_utilization"]/(self.w*self.h)))
                if len(xs)*len(ys)<count:raise ValueError("Initial module cannot fit cells: "+m["name"])
                picks=self.rng.choice(len(xs)*len(ys),count,replace=False)
                pos=np.column_stack([sx[xs[picks%len(xs)]],sy[ys[picks//len(xs)]]])
            self.ids.append(np.arange(len(xy),len(xy)+len(pos)))
            xy.extend(pos);module.extend([mi]*len(pos));tier.extend([m["tier"]]*len(pos));movable.extend([not m["hard"]]*len(pos))
        self.xy=np.array(xy);self.module=np.array(module);self.z=np.array(tier);self.movable=np.array(movable,bool)
        self.cell_area=np.where(self.movable,self.w*self.h,0.)
        self.edges=[];self.external=[];self.links=[]
        links=auxiliary["interconnect"]
        for mi,m in enumerate(self.mods):
            if m["hard"]:continue
            ids=self.ids[mi]
            for _ in range(2):
                self.edges.extend(np.column_stack([ids,self.rng.permutation(ids)]));self.external.extend([False]*len(ids))
        for a,b,n in links:
            if not n:continue
            aa,bb=self.mid[a],self.mid[b];self.links.append((aa,bb,n))
            self.edges.extend(np.column_stack([self.rng.choice(self.ids[aa],n),self.rng.choice(self.ids[bb],n)]));self.external.extend([True]*n)
        self.edges=np.array(self.edges,int);self.external=np.array(self.external,bool);self.a,self.b=self.edges.T
        self.cross=(self.z[self.a]!=self.z[self.b]).astype(int)
        self.logic=self.rng.uniform(.24,.35,len(self.a))+.035*self.external
        critical={self.mid[n] for n in auxiliary["critical_modules"] if n in self.mid}
        ca=np.isin(self.module[self.a],list(critical));cb=np.isin(self.module[self.b],list(critical))
        nw=auxiliary["net_weights"]
        self.critical=np.where(ca&cb,nw.get("crit_crit",1.0),np.where(ca|cb,nw.get("crit_other",1.0),nw.get("other_other",1.0)))
        self.heat=Heat(self)
        self.unit_power=np.zeros(len(self.xy))
        for m,ids in zip(self.mods,self.ids):self.unit_power[ids]=auxiliary["power_w"][m["name"]]/len(ids)
        self.power_provenance=dict(source="annealing_cfg.power_w",total_module_dynamic_W=float(self.unit_power.sum()),
            no_temperature_fitting=True,no_extra_leakage_added=True)

    def wire_power(self,xy,length=None,vias=None):
        length=np.abs(xy[self.a]-xy[self.b]).sum(1) if length is None else length
        vias=self.cross if vias is None else vias;s=self.settings
        p=(length*s["wire_C_pF_mm"]+vias*s["bond_C_pF"])*s["vdd_V"]**2*s["activity"]*s["nominal_GHz"]*.001
        p[~self.external]=0
        out=np.zeros(len(xy));np.add.at(out,self.a,p/2);np.add.at(out,self.b,p/2)
        return out

def opening(mask,radius):
    padded=np.pad(mask,radius,constant_values=False);ny,nx=mask.shape
    eroded=np.ones_like(mask)
    for y in range(2*radius+1):
        for x in range(2*radius+1):eroded &= padded[y:y+ny,x:x+nx]
    padded=np.pad(eroded,radius,constant_values=False);result=np.zeros_like(mask)
    for y in range(2*radius+1):
        for x in range(2*radius+1):result |= padded[y:y+ny,x:x+nx]
    return result&mask


class Regions:
    def __init__(self,d):
        self.d=d;s=d.settings;pitch=s["shape_grid_pitch_um"]/1000
        self.nx=max(8,round(d.extent[0]/pitch));self.ny=max(8,round(d.extent[1]/pitch))
        self.step=d.extent/[self.nx,self.ny];grid=np.indices((self.ny,self.nx)).transpose(1,2,0)[...,::-1]
        self.grid=grid;self.xy=(grid+.5)*self.step;self.free=np.ones((2,self.ny,self.nx),bool)
        lo,hi=grid*self.step,(grid+1)*self.step;halo=s["macro_keepout_mm"]
        for m in d.mods:
            if not m["hard"]:continue
            x,y,w,h=m["rect_mm"]
            blocked=(hi[...,0]>x-halo+1e-10)&(lo[...,0]<x+w+halo-1e-10)&(hi[...,1]>y-halo+1e-10)&(lo[...,1]<y+h+halo-1e-10)
            self.free[m["tier"],blocked]=False
        self.macro_free=self.free.copy()
        radius=max(0,(s["minimum_region_neck_tiles"]-1)//2)
        self.free=np.array([opening(mask,radius) for mask in self.free])
        self.indices=[np.flatnonzero(self.free[z]) for z in range(2)]
        self.ms=[[i for i,m in enumerate(d.mods) if not m["hard"] and m["tier"]==z] for z in range(2)]
        if any(not ms for ms in self.ms):raise ValueError("Each tier requires at least one soft module")
        self.centers=np.array([[m["rect_mm"][0]+m["rect_mm"][2]/2,m["rect_mm"][1]+m["rect_mm"][3]/2] for m in d.mods])
        self.target=[];self.powers=[];self.neighbors=[];self.sp=[]
        for z,ms in enumerate(self.ms):
            areas=np.array([np.prod(d.mods[i]["rect_mm"][2:]) for i in ms]);self.target.append(areas/areas.sum())
            self.powers.append(np.array([d.unit_power[d.ids[i]].sum() for i in ms]))
            remap=np.full(self.nx*self.ny,-1);remap[self.indices[z]]=np.arange(len(self.indices[z]));edges=[]
            for y,x in zip(*np.nonzero(self.free[z])):
                for yy,xx in ((y+1,x),(y,x+1)):
                    if yy<self.ny and xx<self.nx and self.free[z,yy,xx]:edges.append((remap[y*self.nx+x],remap[yy*self.nx+xx]))
            if not edges:raise ValueError("No free connected routing space on tier "+str(z))
            self.neighbors.append(np.array(edges,int))
            self.sp.append(splat(self.xy[self.free[z]],np.full(len(self.indices[z]),z),d.extent,d.heat.g))
        self.fixed=deposit(np.where(d.movable,0,d.unit_power),splat(d.xy,d.z,d.extent,d.heat.g),2*d.heat.g**2)
        self.anchor=self.centers.copy()

    def objective(self,c,w,tau):
        d=self.d;gc=np.zeros_like(c);gw=np.zeros(len(c));loss=0;q=[];gradq=[];diff=[];areas=[];centroids=c.copy()
        for z,ms in enumerate(self.ms):
            r=self.xy[self.free[z]];delta=r[:,None,:]-c[ms][None,:,:];distance=(delta**2).sum(2)
            prob=softmax((w[ms][None,:]-distance)/tau);area=prob.sum(0);rel=prob.mean(0)-self.target[z]
            loss+=35*np.sum((rel/self.target[z])**2)+np.sum(prob*distance)/len(r)
            gp=np.broadcast_to(70*rel/self.target[z]**2/len(r),prob.shape).copy()+distance/len(r)
            gc[ms]+=-2*(prob[:,:,None]*delta).sum(0)/len(r)
            a,b=self.neighbors[z].T;ed=prob[a]-prob[b];loss+=.35*np.mean((ed**2).sum(1));force=.70*ed/len(a)
            np.add.at(gp,a,force);np.add.at(gp,b,-force)
            anchor=c[ms]-self.anchor[ms];loss+=.025*np.mean(anchor**2);gc[ms]+=.05*anchor/anchor.size
            centroids[ms]=prob.T@r/area[:,None]
            q.append(prob);gradq.append(gp);diff.append(delta);areas.append(area)
        ctrgrad=np.zeros_like(c);total=sum(n for _,_,n in d.links)
        for a,b,n in d.links:
            delta=centroids[a]-centroids[b];length=np.sqrt(delta**2+.002**2)
            loss+=.08*n/total*length.sum();force=.08*n/total*delta/length
            if d.mods[a]["hard"] is False:ctrgrad[a]+=force
            if d.mods[b]["hard"] is False:ctrgrad[b]-=force
        constraints=d.aux["layout_constraints"]
        weight=d.aux["objective_weights"].get("constraints",2.0)/max(1,len(constraints))
        for item in constraints:
            a,b=[d.mid[n] for n in item["pair"]];limit=item["max_dist_mm"]
            delta=centroids[a]-centroids[b];sm=np.sqrt(delta**2+.0004**2);dist=sm.sum()
            excess=max(0,dist/limit-1);loss+=weight*excess**2
            force=2*weight*excess/limit*delta/sm
            if not d.mods[a]["hard"]:ctrgrad[a]+=force
            if not d.mods[b]["hard"]:ctrgrad[b]-=force
        # Chain all centroid costs into soft region assignments.
        power=self.fixed.copy()
        for z,ms in enumerate(self.ms):
            r=self.xy[self.free[z]];gradq[z]+=np.einsum("gmk,mk->gm",r[:,None,:]-centroids[ms][None,:,:],ctrgrad[ms])/areas[z]
            power+=deposit(q[z]@(self.powers[z]/areas[z]),self.sp[z],len(power))
        temp=d.settings["ambient_C"]+d.heat.apply(power);loss+=.3*(smoothmax(temp,2)-d.settings["ambient_C"])/40
        field=d.heat.apply(.3*softmax(temp/2)/40)
        for z,ms in enumerate(self.ms):
            f=sample(field,self.sp[z]);mean=(q[z]*f[:,None]).sum(0)/areas[z]
            gradq[z]+=(f[:,None]-mean)*self.powers[z]/areas[z]
            gs=q[z]*(gradq[z]-(gradq[z]*q[z]).sum(1,keepdims=True))/tau
            gw[ms]=gs.sum(0);gc[ms]+=(2*gs[:,:,None]*diff[z]).sum(0)
        return float(loss),gc,gw,q

    def optimize(self,steps):
        c=self.centers.copy();w=np.zeros(len(c));scale=max(self.d.extent)**2
        for it in range(60):
            for z,ms in enumerate(self.ms):
                r=self.xy[self.free[z]];dist=((r[:,None,:]-c[ms][None,:,:])**2).sum(2)
                for _ in range(35):
                    q=softmax((w[ms][None,:]-dist)/(.02*scale));w[ms]+=.12*scale*(self.target[z]-q.mean(0))
                c[ms]=.75*c[ms]+.25*(q.T@r/q.sum(0)[:,None])
        mc,vc=np.zeros_like(c),np.zeros_like(c);mw,vw=np.zeros(len(c)),np.zeros(len(c));history=[]
        checkpoints=[(c.copy(),w.copy(),-1)]
        for it in range(steps):
            fraction=it/max(1,steps-1);tau=.055*scale*(.004/.055)**fraction
            loss,gc,gw,_=self.objective(c,w,tau);mc=.9*mc+.1*gc;vc=.999*vc+.001*gc**2
            mw=.9*mw+.1*gw;vw=.999*vw+.001*gw**2;lr=.005*max(self.d.extent)*(1-.7*fraction)
            c-=lr*(mc/(1-.9**(it+1)))/(np.sqrt(vc/(1-.999**(it+1)))+1e-9)
            w-=lr*.2*(mw/(1-.9**(it+1)))/(np.sqrt(vw/(1-.999**(it+1)))+1e-9)
            c=np.clip(c,self.step/2,self.d.extent-self.step/2)
            for ms in self.ms:w[ms]-=w[ms].mean()
            if it%40==0 or it==steps-1:
                history.append(dict(step=it,loss=loss,tau=tau));checkpoints.append((c.copy(),w.copy(),it))
        # Soft objectives need not satisfy discrete geometry. Select the best legal
        # checkpoint at a COMMON final tau rather than relaxing hard shape limits.
        legal=[];failures=[]
        for cc,ww,it in checkpoints:
            try:
                labels,checks,adjusted=self.partition(cc,ww)
                score=self.objective(cc,adjusted,.001*scale)[0]
                legal.append((score,labels,checks,it))
            except ValueError as error:failures.append(dict(step=it,error=str(error)))
        if not legal:raise ValueError("No legal region checkpoint: "+str(failures))
        _,labels,checks,picked=min(legal,key=lambda item:item[0])
        history.append(dict(selected_legal_checkpoint=picked,rejected_checkpoint_count=len(failures)))
        return labels,checks,history

    def partition(self,c,w):
        # Equalize discrete area with a sharper dual phase while keeping optimized centers.
        w=w.copy();scale=max(self.d.extent)**2
        for z,ms in enumerate(self.ms):
            r=self.xy[self.free[z]];dist=((r[:,None,:]-c[ms][None,:,:])**2).sum(2)
            for _ in range(400):
                q=softmax((w[ms][None,:]-dist)/(.001*scale));w[ms]+=.012*scale*(self.target[z]-q.mean(0))
        q=self.objective(c,w,.001*scale)[3]
        labels=np.full(self.free.shape,-1,int);labels[self.macro_free&~self.free]=-3
        for z,ms in enumerate(self.ms):
            lab=np.full((self.ny,self.nx),-1,int);lab.ravel()[self.indices[z]]=np.argmax(q[z],1)
            for j in range(len(ms)):
                parts=groups(lab==j)
                if not parts:raise ValueError("Empty region: "+self.d.names[ms[j]])
                for part in parts[1:]:
                    for y,x in part:lab[y,x]=-2
            while (lab==-2).any():
                candidates=[]
                for y,x in zip(*np.nonzero(lab==-2)):
                    adj={lab[v,u] for v,u in ((y-1,x),(y+1,x),(y,x-1),(y,x+1)) if 0<=v<self.ny and 0<=u<self.nx and lab[v,u]>=0}
                    for j in adj:candidates.append((((self.xy[y,x]-c[ms[j]])**2).sum()-w[ms[j]],y,x,j))
                if not candidates:raise ValueError("Disconnected free area cannot be assigned")
                _,y,x,j=min(candidates);lab[y,x]=j
            for j,mi in enumerate(ms):labels[z,lab==j]=mi
        checks=self.validate(labels)
        return labels,checks,w

    def validate(self,labels):
        if not np.array_equal(labels>=0,self.free):raise ValueError("Region partition has gaps or overlap")
        rows=[]
        for z,ms in enumerate(self.ms):
            for j,mi in enumerate(ms):
                mask=labels[z]==mi;yy,xx=np.nonzero(mask);n=len(xx)
                if not n:raise ValueError("Empty region")
                perimeter=sum(sum(not(0<=v<self.ny and 0<=u<self.nx and mask[v,u]) for v,u in ((y-1,x),(y+1,x),(y,x-1),(y,x+1))) for y,x in zip(yy,xx))
                bw=(xx.max()-xx.min()+1)*self.step[0];bh=(yy.max()-yy.min()+1)*self.step[1]
                # Geometry uses rectangular tiles; count each vertical/horizontal edge in mm.
                p=0.
                for y,x in zip(yy,xx):
                    for v,u,length in ((y-1,x,self.step[0]),(y+1,x,self.step[0]),(y,x-1,self.step[1]),(y,x+1,self.step[1])):
                        if not(0<=v<self.ny and 0<=u<self.nx and mask[v,u]):p+=length
                holes=sum(not any(y==0 or x==0 or y==self.ny-1 or x==self.nx-1 for y,x in group) for group in groups(~mask))
                area=n*np.prod(self.step);target=self.free[z].sum()*np.prod(self.step)*self.target[z][j]
                row=dict(module=self.d.names[mi],tier=z,area_mm2=float(area),components=len(groups(mask)),holes=holes,
                    bbox_aspect=float(max(bw/bh,bh/bw)),compactness=float(p*p/(16*area)),area_error=float(abs(area/target-1)))
                row["valid"]=bool(row["components"]==1 and holes==0 and row["bbox_aspect"]<=self.d.settings["max_bbox_aspect"] and row["compactness"]<=self.d.settings["max_compactness"] and row["area_error"]<=self.d.settings["max_area_error"])
                rows.append(row)
        if not all(r["valid"] for r in rows):raise ValueError("Shape constraints violated: "+str([r for r in rows if not r["valid"]]))
        return rows


class Cells:
    def __init__(self,d,regions,labels):
        self.d,self.regions,self.labels=d,regions,labels
        self.nx=math.floor(d.extent[0]/d.slot+1e-9);self.ny=math.floor(d.extent[1]/d.h+1e-9)
        sx=(np.arange(self.nx)+.5)*d.slot;sy=(np.arange(self.ny)+.5)*d.h
        xx,yy=np.meshgrid(sx,sy);positions=np.column_stack([xx.ravel(),yy.ravel()])
        low=positions-[d.slot/2,d.h/2];high=positions+[d.slot/2,d.h/2]
        li=np.floor((low+1e-10)/regions.step).astype(int);hi=np.floor((high-1e-10)/regions.step).astype(int)
        owner=labels[:,li[:,1],li[:,0]].copy()
        for u,v in ((hi[:,0],li[:,1]),(li[:,0],hi[:,1]),(hi[:,0],hi[:,1])):
            owner[owner!=labels[:,v,u]]=-1
        period=max(2,round(1/d.settings["cts_reserve_row_fraction"]))
        reserved=(np.arange(self.ny)%period)==period-1
        owner[:,np.repeat(reserved,self.nx)]=-1
        self.reserved_rows=reserved
        self.owner=owner.reshape(2,self.ny,self.nx);self.positions=positions;self.sites={};self.nearest={}
        self.target=np.zeros(2*d.heat.g**2)
        for z,ms in enumerate(regions.ms):
            r=regions.xy[regions.free[z]];values=np.zeros(len(r));tilemods=labels[z].ravel()[regions.indices[z]]
            for mi in ms:
                sites=np.flatnonzero(owner[z]==mi)
                if len(sites)<len(d.ids[mi]):raise ValueError("Not enough legal sites for "+d.names[mi])
                self.sites[mi]=sites
                valid=np.argwhere(labels[z]==mi)[:,::-1];flat=regions.grid.reshape(-1,2)
                # Chunk distances to avoid quadratic peak memory on cloud desktops.
                nearest=[]
                for start in range(0,len(flat),128):
                    dist=(((flat[start:start+128,None,:]-valid[None,:,:])*regions.step)**2).sum(2)
                    nearest.extend(valid[dist.argmin(1)])
                self.nearest[mi]=np.array(nearest)
                sel=tilemods==mi;values[sel]=len(d.ids[mi])*d.w*d.h/sel.sum()
            self.target+=deposit(values,regions.sp[z],len(self.target))
        self.binarea=np.prod(d.extent)/d.heat.g**2;self.target/=self.binarea

    def project(self,xy):
        out=xy.copy();r=self.regions;d=self.d
        for z,ms in enumerate(r.ms):
            for mi in ms:
                ids=d.ids[mi];tiles=np.clip(np.floor(out[ids]/r.step).astype(int),[0,0],[r.nx-1,r.ny-1])
                outside=self.labels[z,tiles[:,1],tiles[:,0]]!=mi
                tiles[outside]=self.nearest[mi][tiles[outside,1]*r.nx+tiles[outside,0]]
                out[ids]=np.clip(out[ids],tiles*r.step+[d.slot/2,d.h/2],(tiles+1)*r.step-[d.slot/2,d.h/2])
        out[~d.movable]=d.xy[~d.movable]
        return out

    def legalize(self,xy):
        d=self.d;out=xy.copy();used=np.zeros_like(self.owner,bool)
        for mi,sites in self.sites.items():
            z=d.mods[mi]["tier"];ids=d.ids[mi]
            for i in ids[np.lexsort((xy[ids,0],xy[ids,1]))]:
                cx=int(np.clip(round(xy[i,0]/d.slot-.5),0,self.nx-1));cy=int(np.clip(round(xy[i,1]/d.h-.5),0,self.ny-1));radius=0
                while True:
                    x0,x1=max(0,cx-radius),min(self.nx,cx+radius+1);y0,y1=max(0,cy-radius),min(self.ny,cy+radius+1)
                    yy,xx=np.nonzero((self.owner[z,y0:y1,x0:x1]==mi)&~used[z,y0:y1,x0:x1])
                    if len(xx):
                        xx+=x0;yy+=y0;ds=((xx+.5)*d.slot-xy[i,0])**2+((yy+.5)*d.h-xy[i,1])**2;k=ds.argmin();cx,cy=xx[k],yy[k];break
                    radius+=1
                    if radius>max(self.nx,self.ny):raise ValueError("Legalization exhausted sites")
                used[z,cy,cx]=True;out[i]=[(cx+.5)*d.slot,(cy+.5)*d.h]
        self.validate(out);return out

    def validate(self,xy):
        d=self.d
        if not np.array_equal(xy[~d.movable],d.xy[~d.movable]):raise ValueError("Hard macro points moved")
        for z in range(2):
            ids=np.flatnonzero(d.movable&(d.z==z));coords=xy[ids]/[d.slot,d.h]-.5
            if np.max(abs(coords-np.rint(coords)))>1e-7:raise ValueError("Off-site cells")
            xx,yy=np.rint(coords).astype(int).T
            if len(np.unique(yy*self.nx+xx))!=len(ids) or not np.all(self.owner[z,yy,xx]==d.module[ids]):raise ValueError("Overlapping/out-of-region cell")
        return True

    def objective(self,xy,profile):
        d=self.d;s=d.settings;ww,wt=PROFILES[profile]
        delta=xy[d.a]-xy[d.b];smooth=np.sqrt(delta**2+.0004**2);length=smooth.sum(1)
        delay=d.logic+s["wire_delay_ns_mm"]*length+s["wire_delay_ns_mm2"]*length**2+d.cross*s["bond_delay_ns"]
        ow=d.aux["objective_weights"];wl=ow.get("wirelength",1.0);tw=ow.get("timing",1.0)
        loss=ww*(.45*wl*(length*d.critical).mean()/.25+1.5*tw*smoothmax(delay,.012)/.5)
        dl=ww*(.45*wl*d.critical/(len(length)*.25)+1.5*tw*softmax(delay/.012)*(s["wire_delay_ns_mm"]+2*s["wire_delay_ns_mm2"]*length)/.5)
        grad=np.zeros_like(xy);force=dl[:,None]*delta/smooth;np.add.at(grad,d.a,force);np.add.at(grad,d.b,-force)
        sp=splat(xy,d.z,d.extent,d.heat.g);size=2*d.heat.g**2;rho=deposit(d.cell_area,sp,size)/self.binarea
        diff=rho-self.target;spill=np.maximum(rho-s["density_upper_bound"],0)
        coeff=d.config["spill_coef"]*35;viol=d.config["viol_penalty_coef"]*.03
        loss+=coeff*np.mean(diff**2)+viol*np.mean(spill**2)
        grad+=adjoint(d.cell_area,sp,(2*coeff*diff+2*viol*spill)/(size*self.binarea))
        temp=s["ambient_C"]+d.heat.apply(deposit(d.unit_power,sp,size));loss+=wt*(smoothmax(temp,2)-s["ambient_C"])/40
        field=d.heat.apply(wt*softmax(temp/2)/40);grad+=adjoint(d.unit_power,sp,field)
        grad[~d.movable]=0
        return float(loss),grad

    def optimize(self,profile,steps,seed):
        d=self.d;rng=np.random.default_rng(seed);xy=d.xy.copy()
        for mi,sites in self.sites.items():
            ids=d.ids[mi];picks=rng.choice(sites,len(ids),replace=False);points=self.positions[picks]
            xy[ids[np.lexsort((d.xy[ids,0],d.xy[ids,1]))]]=points[np.lexsort((points[:,0],points[:,1]))]
        xy=self.project(xy);mom,vel=np.zeros_like(xy),np.zeros_like(xy);best=xy.copy();bestloss=float("inf");history=[]
        for i in range(steps+1):
            loss,grad=self.objective(xy,profile)
            if loss<bestloss:best,bestloss=xy.copy(),loss
            if i%40==0 or i==steps:history.append(dict(step=i,loss=loss))
            if i==steps:break
            mom=.9*mom+.1*grad;vel=.999*vel+.001*grad**2;lr=.004*max(d.extent)*(1-.8*i/steps)
            xy=self.project(xy-lr*(mom/(1-.9**(i+1)))/(np.sqrt(vel/(1-.999**(i+1)))+1e-9))
        return self.legalize(best),history


class Routing:
    def __init__(self,d,xy):
        self.d,self.xy=d,xy;self.g=16;g=self.g;self.ept=2*g*(g-1);self.size=2*self.ept
        self.grid=np.clip(np.floor(xy*g/d.extent).astype(int),0,g-1);self.guide=np.flatnonzero(d.external)
        capx=d.settings["tracks_per_mm"]*d.extent[1]/g;capy=d.settings["tracks_per_mm"]*d.extent[0]/g
        self.cap=np.tile(np.r_[np.full(g*(g-1),capx),np.full(g*(g-1),capy)],2)
        for m in d.mods:
            if not m["hard"]:continue
            rx,ry,rw,rh=m["rect_mm"];z=m["tier"]
            for direction in (0,1):
                for y in range(g if direction==0 else g-1):
                    for x in range(g-1 if direction==0 else g):
                        pos=(np.array([x+.5,y+.5])*d.extent/g)
                        if rx<=pos[0]<=rx+rw and ry<=pos[1]<=ry+rh:self.cap[self.edge(z,direction,x,y)]*=.45
        self.background=np.zeros(self.size)
        for i in np.flatnonzero(~d.external):np.add.at(self.background,self.path(i,0,int(d.z[d.a[i]])),1)
        cand,resource,vc,vb=[],[],[],[];self.vias=np.zeros((len(self.guide),4))
        for j,i in enumerate(self.guide):
            for k in range(4):
                tier,bend=k//2,k%2;route=self.path(i,bend,tier);cand.extend([j*4+k]*len(route));resource.extend(route)
                for node in (d.a[i],d.b[i]):
                    if d.z[node]!=tier:
                        x,y=self.grid[node];vc.append(j*4+k);vb.append(y*g+x);self.vias[j,k]+=1
        self.cand,self.resource=np.array(cand,int),np.array(resource,int);self.vc,self.vb=np.array(vc,int),np.array(vb,int)
        self.vcap=min(d.config["max_density_per_mm2"],(1000/d.config["pitch_um"])**2)*np.prod(d.extent)/g**2*(1-d.aux["bond_reserve_fraction"])
    def edge(self,z,direction,x,y):
        return z*self.ept+(y*(self.g-1)+x if direction==0 else self.g*(self.g-1)+y*self.g+x)
    def path(self,i,bend,tier):
        ax,ay=self.grid[self.d.a[i]];bx,by=self.grid[self.d.b[i]];hy,vx=(ay,bx) if bend==0 else (by,ax)
        return [self.edge(tier,0,x,hy) for x in range(min(ax,bx),max(ax,bx))]+[self.edge(tier,1,vx,y) for y in range(min(ay,by),max(ay,by))]
    def demand(self,p):
        flat=p.ravel();return self.background+np.bincount(self.resource,weights=flat[self.cand],minlength=self.size),np.bincount(self.vb,weights=flat[self.vc],minlength=self.g**2)
    def loss(self,logits):
        p=softmax(logits);demand,vias=self.demand(p);over=np.maximum(demand/self.cap-1,0);vo=np.maximum(vias/self.vcap-1,0)
        n=len(p);coeff=(.08+.04*self.d.critical[self.guide,None])/n
        loss=12*np.mean(over**2)+5*np.mean(vo**2)+np.sum(p*self.vias*coeff)
        gp=np.bincount(self.cand,weights=(24*over/(self.size*self.cap))[self.resource],minlength=n*4).reshape(n,4)
        gp+=np.bincount(self.vc,weights=(10*vo/(self.g**2*self.vcap))[self.vb],minlength=n*4).reshape(n,4);gp+=self.vias*coeff
        return float(loss),p*(gp-(gp*p).sum(1,keepdims=True))
    def optimize(self,steps):
        logits=np.zeros((len(self.guide),4));logits[np.arange(len(logits)),2*self.d.z[self.d.a[self.guide]]]=.1
        m,v=np.zeros_like(logits),np.zeros_like(logits);trace=[]
        for i in range(steps):
            loss,grad=self.loss(logits);m=.9*m+.1*grad;v=.999*v+.001*grad**2
            logits-=.15*(m/(1-.9**(i+1)))/(np.sqrt(v/(1-.999**(i+1)))+1e-9)
            if i%40==0 or i==steps-1:trace.append(dict(step=i,loss=loss))
        return softmax(logits).argmax(1),trace
    def assign(self,choice):
        d=self.d;step=d.config["pitch_um"]/1000;nx,ny=np.floor(d.extent/step+1e-9).astype(int)
        sx,sy=np.meshgrid((np.arange(nx)+.5)*step,(np.arange(ny)+.5)*step)
        sites=np.column_stack([sx.ravel(),sy.ravel()]);used=np.zeros(len(sites),bool)
        window=d.aux["bond_window_mm"];wx=math.ceil(d.extent[0]/window);wy=math.ceil(d.extent[1]/window)
        bins=np.floor(sites/window).astype(int);bin_id=bins[:,1]*wx+bins[:,0]
        caps=[]
        for y in range(wy):
            for x in range(wx):caps.append(math.floor(min(window,d.extent[0]-x*window)*min(window,d.extent[1]-y*window)*d.config["max_density_per_mm2"]*(1-d.aux["bond_reserve_fraction"])+1e-8))
        caps=np.array(caps);counts=np.zeros(len(caps),int);records=[];length=np.abs(self.xy[d.a]-self.xy[d.b]).sum(1)
        vias=d.cross.copy();vias[self.guide]=self.vias[np.arange(len(choice)),choice].astype(int)
        # Exact pitch sites, separate density windows including partial edge windows.
        for j,i in enumerate(self.guide):
            tier=choice[j]//2
            for node in (d.a[i],d.b[i]):
                if d.z[node]==tier:continue
                pos=self.xy[node];cx=int(np.clip(round(pos[0]/step-.5),0,nx-1));cy=int(np.clip(round(pos[1]/step-.5),0,ny-1));radius=0
                while True:
                    x0,x1=max(0,cx-radius),min(nx,cx+radius+1);y0,y1=max(0,cy-radius),min(ny,cy+radius+1)
                    yy,xx=np.meshgrid(np.arange(y0,y1),np.arange(x0,x1),indexing="ij");inds=(yy*nx+xx).ravel()
                    candidates=inds[(~used[inds])&(counts[bin_id[inds]]<caps[bin_id[inds]])]
                    if len(candidates):
                        k=candidates[((sites[candidates]-pos)**2).sum(1).argmin()];break
                    radius+=1
                    if radius>max(nx,ny):raise ValueError("No legal HBT sites: total/local density capacity exhausted")
                used[k]=True;counts[bin_id[k]]+=1
                detour=2*np.abs(sites[k]-pos).sum();length[i]+=detour
                records.append(dict(net_id=int(i),endpoint_cell_id=int(node),x_mm=float(sites[k,0]),y_mm=float(sites[k,1]),detour_mm=float(detour)))
        demand,_=self.demand(np.eye(4)[choice])
        # Detours consume routing tracks in BOTH endpoint and trunk tiers.
        for bond in records:
            i,node=bond["net_id"],bond["endpoint_cell_id"];ax,ay=self.grid[node]
            bx,by=np.clip(np.floor(np.array([bond["x_mm"],bond["y_mm"]])*self.g/d.extent).astype(int),0,self.g-1)
            for z in (0,1):
                for x in range(min(ax,bx),max(ax,bx)):demand[self.edge(z,0,x,ay)]+=1
                for y in range(min(ay,by),max(ay,by)):demand[self.edge(z,1,bx,y)]+=1
        density=np.array([counts[y*wx+x]/(min(window,d.extent[0]-x*window)*min(window,d.extent[1]-y*window)) for y in range(wy) for x in range(wx)])
        metrics=dict(route_overflow_tracks=float(np.maximum(demand-self.cap,0).sum()),max_route_utilization=float((demand/self.cap).max()),
            bond_count=len(records),max_bond_density_per_mm2=float(density.max()),legal_pitch_sites=True,legal_fixed_window_density=bool(np.all(counts<=caps)))
        return metrics,length,vias,records


def evaluate(d,xy,route,length,vias,hotspot_field=None):
    s=d.settings;sp=splat(xy,d.z,d.extent,d.heat.g);size=2*d.heat.g**2
    nominal_power=d.unit_power+d.wire_power(xy,length,vias)
    def state(f):
        power=nominal_power*f/s["nominal_GHz"]
        if hotspot_field is None:
            field=s["ambient_C"]+d.heat.apply(deposit(power,sp,size));node=sample(field,sp)
        else:
            native=s["ambient_C"]+(hotspot_field-s["ambient_C"])*f/s["nominal_GHz"]
            native_g=round(math.sqrt(len(native)/2))
            node=sample(native,splat(xy,d.z,d.extent,native_g))
            # Preserve native HotSpot peak when saving/displaying maps; resampling would hide it.
            field=native
        tn=np.maximum(node[d.a],node[d.b])
        delay=d.logic*(1+s["logic_temp_alpha"]*(tn-s["reference_temperature_C"]))
        delay+=(s["wire_delay_ns_mm"]*length+s["wire_delay_ns_mm2"]*length**2+vias*s["bond_delay_ns"])*(1+s["wire_temp_alpha"]*(tn-s["reference_temperature_C"]))
        return power,field,delay
    nominal=state(s["nominal_GHz"]);lo,hi=0.,s["nominal_GHz"]
    for _ in range(28):
        mid=(lo+hi)/2;power,temp,delay=state(mid)
        if temp.max()<=s["temperature_limit_C"] and delay.max()*mid<=1:lo=mid
        else:hi=mid
    power,temp,delay=state(lo)
    ipc={};bips={};baseline=json.loads((ROOT/"data/layout_baseline.json").read_text(encoding="utf-8"))
    l2ids=[d.mid[n] for n in ("l2_b0","l2_b1","l2_ctl") if n in d.mid]
    mask=np.isin(d.module[d.a],l2ids)|np.isin(d.module[d.b],l2ids)
    link_ns=float(np.quantile((delay-d.logic)[mask],.95)) if mask.any() else 0.
    cycles=max(1,math.ceil(link_ns*lo))
    for run in baseline["runs"]:
        name=run["workload"];mem=.35 if name=="stream" else .12
        cpi=run["cpi"]*((1-mem)+mem*lo/baseline["frequency_GHz"])+run["l2_accesses_per_instruction"]*.25*(cycles-1)
        ipc[name]=1/cpi;bips[name]=lo/cpi
    mean=float(np.mean(list(bips.values())));wns=(1/s["nominal_GHz"]-nominal[2])*1000
    result=dict(**route,power_W=float(power.sum()),peak_C=float(temp.max()),frequency_GHz=float(lo),
        nominal_power_W=float(nominal[0].sum()),nominal_peak_C=float(nominal[1].max()),nominal_WNS_ps=float(wns.min()),
        nominal_TNS_ns=float(np.minimum(wns,0).sum()/1000),total_wire_mm=float(length.sum()),mean_bips=mean,
        ipc_stream=ipc["stream"],ipc_matmul=ipc["matmul"],energy_nJ_per_instruction=float(power.sum()/max(mean,1e-9)),
        estimated=True,thermal_backend="HotSpot" if hotspot_field is not None else "resistance_proxy",feasible=bool(route["route_overflow_tracks"]<1e-8 and temp.max()<=s["temperature_limit_C"] and lo>.1))
    return result,temp


def pareto(rows,feasible_only=True):
    valid=[r for r in rows if r["feasible"] or not feasible_only]
    return [r["run"] for r in valid if not any(b["power_W"]<=r["power_W"] and b["peak_C"]<=r["peak_C"] and b["mean_bips"]>=r["mean_bips"] and
        (b["power_W"]<r["power_W"] or b["peak_C"]<r["peak_C"] or b["mean_bips"]>r["mean_bips"]) for b in valid)]


def source_settings(aux):
    s=DEFAULTS.copy();s["ambient_C"]=aux["ambient_c"]
    s["nominal_GHz"]=1000/float(aux["timing"].get("clock_period_ps",500))
    s["bond_delay_ns"]=float(aux["timing"].get("hbt_latency_ps",14))/1000
    s["wire_temp_alpha"]=aux["rc_temp_alpha"];s["reference_temperature_C"]=aux["rc_ref_temp"]
    s["macro_keepout_mm"]=aux["module_gap_mm"]/2
    if aux["hotspot"]:s["common_R_K_W"]=float(aux["hotspot"]["r_convec"])
    stack=aux["stack"]
    if stack:
        bottom=next(v for v in stack if v["power_layer"]=="bottom")
        top=next(v for v in stack if v["power_layer"]=="top")
        interface=next(v for v in stack if v["name"]=="hb_interface")
        tim=next(v for v in stack if v["name"]=="tim")
        def resistance(v):return float(v["thickness_um"])*1e-6/float(v["conductivity_W_m_K"])
        s["lateral_G"]=float(top["conductivity_W_m_K"])*float(top["thickness_um"])*1e-6
        s["vertical_G_at_16"]=1e-8/(resistance(interface)+.5*resistance(bottom)+.5*resistance(top))
        s["sink_G_at_16"]=1e-8/(resistance(tim)+.5*resistance(top))
    return s


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",type=Path,default=ROOT/"configs/config.yaml.json")
    parser.add_argument("--annealing-config",type=Path,default=DEFAULT_ANNEALING)
    parser.add_argument("--output",type=Path)
    parser.add_argument("--settings",type=Path,help="Optional JSON overrides for documented synthetic assumptions")
    parser.add_argument("--seed",type=int,default=20261012)
    parser.add_argument("--shape-steps",type=int,default=360)
    parser.add_argument("--cell-steps",type=int,default=180)
    parser.add_argument("--route-steps",type=int,default=160)
    parser.add_argument("--profiles",default="balanced,timing,thermal")
    parser.add_argument("--quick",action="store_true")
    parser.add_argument("--run-kind",choices=("formal","environment_validation"),default="formal",help="Controls results catalog; quick always remains quick")
    parser.add_argument("--check",action="store_true",help="Only validate config and dependency versions")
    parser.add_argument("--hotspot-exe",help="Optional native HotSpot executable for final thermal evaluation")
    parser.add_argument("--hotspot-wsl",help="Use bundled HotSpot in this WSL distro for final thermal evaluation")
    args=parser.parse_args();start=time.time()
    config=read_layout(args.config);aux=read_auxiliary(args.annealing_config,config);settings=source_settings(aux)
    if args.settings:
        extra=json.loads(args.settings.read_text(encoding="utf-8-sig"));unknown=set(extra)-set(settings)
        if unknown:raise ValueError("Unknown settings: "+str(sorted(unknown)))
        settings.update(extra)
    if any(not isinstance(v,(int,float)) or not math.isfinite(v) or v<=0 for v in settings.values()):raise ValueError("Settings must be finite positive numbers")
    if settings["initial_utilization"]>1:raise ValueError("initial_utilization must be <= 1")
    if not 0<settings["cts_reserve_row_fraction"]<=.5:raise ValueError("cts_reserve_row_fraction must be in (0, 0.5]")
    if settings["density_upper_bound"]>1:raise ValueError("density_upper_bound must be <= 1")
    for name in ("thermal_grid","minimum_region_neck_tiles"):
        if int(settings[name])!=settings[name]:raise ValueError(name+" must be an integer")
        settings[name]=int(settings[name])
    if settings["thermal_grid"]<4:raise ValueError("thermal_grid must be >= 4")
    profiles=args.profiles.split(",")
    if not profiles or any(p not in PROFILES for p in profiles):raise ValueError("Profiles: balanced,timing,thermal")
    if min(args.shape_steps,args.cell_steps,args.route_steps)<1:raise ValueError("Iteration counts must be positive")
    print("Input:",args.config.resolve(),flush=True)
    print("Die {} x {} mm; {} modules; hard macros: {}".format(config["width_mm"],config["height_mm"],len(config["modules"]),[m["name"] for m in config["modules"] if m["hard"]]),flush=True)
    print("Python {} / NumPy {} / {}".format(platform.python_version(),np.__version__,platform.platform()),flush=True)
    for warning in config["warnings"]+aux["warnings"]:print("Input warning:",warning,flush=True)
    print("Module dynamic power: {:.6f} W; supplied connections: {} pairs".format(sum(aux["power_w"].values()),len(aux["interconnect"])),flush=True)
    if args.check:
        print("PASS: input syntax, names, rectangle boundaries/overlap/area and pitch capacity. No simulation.");return 0
    if args.quick:args.shape_steps,args.cell_steps,args.route_steps=40,12,16
    from results_index import allocate_output,update_index
    started=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
    out=allocate_output(ROOT/"results",args.output)
    out.mkdir(parents=True,exist_ok=True);shutil.copyfile(args.config,out/"input_config.yaml.json")
    shutil.copyfile(args.annealing_config,out/"input_annealing_cfg.yaml")
    save_json(out/"run_info.json",dict(started_at=started,kind="quick" if args.quick else args.run_kind,status="running",algorithm="config-driven cell refinement",command_arguments=sys.argv[1:]))
    save_json(out/"effective_input.json",dict(layout=config,auxiliary=aux));save_json(out/"assumptions.json",settings)
    d=Model(config,aux,settings,args.seed)
    print("Cells:",int(d.movable.sum()),"; synthetic edges:",len(d.edges),"; cross-tier signal edges:",int(d.cross.sum()),flush=True)
    print("Input temperatures retained as references; no power fitting. Backend:","HotSpot" if args.hotspot_exe or args.hotspot_wsl else "resistance proxy",flush=True)
    r=Regions(d);print("Optimizing nonrectangular regions ...",flush=True)
    labels,checks,shape_trace=r.optimize(args.shape_steps);cells=Cells(d,r,labels)
    print("Region checks passed; reserved thin margin {:.6f} mm2".format(float((r.macro_free&~r.free).sum()*np.prod(r.step))),flush=True)
    write_csv(out/"module_shapes.csv",checks);save_json(out/"shape_trace.json",shape_trace)
    rows=[];saved={}
    for profile in ["initial"]+profiles:
        print("Running",profile,"...",flush=True)
        if profile=="initial":xy=d.xy.copy();trace=[]
        else:xy,trace=cells.optimize(profile,args.cell_steps,args.seed)
        router=Routing(d,xy);choice,rt=router.optimize(args.route_steps);route,length,vias,bonds=router.assign(choice)
        hotspot_field=None
        if args.hotspot_exe or args.hotspot_wsl:
            from layout_hotspot import run_hotspot_grid
            nominal_power=d.unit_power+d.wire_power(xy,length,vias)
            pmap=deposit(nominal_power,splat(xy,d.z,d.extent,d.heat.g),2*d.heat.g**2)
            hotspot_field=run_hotspot_grid(d,pmap,out/(profile+"_hotspot"),args.hotspot_exe,args.hotspot_wsl)
        result,temp=evaluate(d,xy,route,length,vias,hotspot_field);result["run"]=profile
        result["cells_outside_initial_rectangles"]=int(sum(np.sum((xy[d.ids[i],0]-d.w/2<m["rect_mm"][0]-1e-9)|(xy[d.ids[i],0]+d.w/2>m["rect_mm"][0]+m["rect_mm"][2]+1e-9)|(xy[d.ids[i],1]-d.h/2<m["rect_mm"][1]-1e-9)|(xy[d.ids[i],1]+d.h/2>m["rect_mm"][1]+m["rect_mm"][3]+1e-9)) for i,m in enumerate(d.mods) if not m["hard"]))
        rows.append(result);saved[profile]=(xy,temp,bonds,choice)
        tempg=round(math.sqrt(len(temp)/2))
        np.savez_compressed(out/(profile+".npz"),xy_mm=xy,tier=d.z,module_id=d.module,movable=d.movable,edges=d.edges,labels=labels,temperature_C=temp.reshape(2,tempg,tempg),route_choice=choice)
        save_json(out/(profile+"_trace.json"),dict(cells=trace,routing=rt))
        print("{}: {:.3f} GHz, {:.3f} W, {:.2f} C, BIPS {:.4f}, overflow {:.1f}".format(profile,result["frequency_GHz"],result["power_W"],result["peak_C"],result["mean_bips"],result["route_overflow_tracks"]),flush=True)
    valid=[v for v in rows if v["run"]!="initial" and v["feasible"]]
    winner=max(valid,key=lambda v:(v["mean_bips"],-v["energy_nJ_per_instruction"])) if valid else None
    selected=winner or min(rows[1:],key=lambda v:(v["route_overflow_tracks"],-v["mean_bips"]))
    xy,temp,bonds,choice=saved[selected["run"]]
    cells.validate(xy);write_csv(out/"metrics.csv",rows)
    centroids=np.array([xy[ids].mean(0) for ids in d.ids])
    constraint_rows=[]
    for item in aux["layout_constraints"]:
        a,b=[d.mid[n] for n in item["pair"]]
        distance=float(np.abs(centroids[a]-centroids[b]).sum())
        requested=item.get("layer", "")
        tier_ok=not requested or all(d.mods[i]["tier"]==({"BOT":0,"TOP":1}[requested]) for i in (a,b))
        constraint_rows.append(dict(module_a=d.names[a],module_b=d.names[b],distance_mm=distance,
            limit_mm=item["max_dist_mm"],distance_pass=distance<=item["max_dist_mm"],
            requested_tier=requested,tier_pass=tier_ok,kind="soft; final-layout tiers fixed"))
    write_csv(out/"selected_soft_constraints.csv",constraint_rows)
    write_csv(out/"selected_cells.csv",[dict(cell_id=i,module=d.names[d.module[i]],tier=int(d.z[i]),movable=bool(d.movable[i]),x_mm=float(xy[i,0]),y_mm=float(xy[i,1])) for i in range(len(xy))])
    write_csv(out/"selected_bonds.csv",bonds)
    write_csv(out/"selected_route_guides.csv",[dict(net_id=int(i),trunk_tier=int(k//2),path="XY" if k%2==0 else "YX") for i,k in zip(np.flatnonzero(d.external),choice)])
    for p in saved:
        tempg=round(math.sqrt(len(saved[p][1])/2))
        write_csv(out/(p+"_module_temperatures.csv"),[dict(module=m["name"],reference_C=m["reference_C"],computed_mean_C=float(sample(saved[p][1],splat(saved[p][0],d.z,d.extent,tempg))[d.ids[i]].mean())) for i,m in enumerate(d.mods)])
    fine=Heat(d,32);sp=splat(xy,d.z,d.extent,32);rp,rl,rv,_=Routing(d,xy).assign(choice)
    powers=(d.unit_power+d.wire_power(xy,rl,rv))*selected["frequency_GHz"]/settings["nominal_GHz"]
    finepeak=settings["ambient_C"]+fine.apply(deposit(powers,sp,2048)).max()
    manifest=dict(input=config,auxiliary=aux,settings=settings,seed=args.seed,iterations=dict(shape=args.shape_steps,cells=args.cell_steps,routing=args.route_steps),
        power_provenance=d.power_provenance,winner=winner,selected_candidate=selected,pareto=pareto(rows),
        diagnostic_pareto_including_infeasible=pareto(rows,False),
        no_feasible_candidate=not bool(valid),cells_legal=True,shapes_valid=True,standard_cell_count=int(d.movable.sum()),
        region_coverage=1.0,region_coverage_denominator="eligible plane excluding hard macro keepout and thin routing margins",
        thin_reserved_margin_mm2=float((r.macro_free&~r.free).sum()*np.prod(r.step)),
        proxy_fine_grid_peak_C=float(finepeak),elapsed_seconds=time.time()-start,
        environment=dict(python=platform.python_version(),numpy=np.__version__,os=platform.platform(),machine=platform.machine()),
        source_sha256={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),HERE/"layout_input.py",HERE/"layout_svg.py",ROOT/"data/layout_baseline.json",HERE/"yaml_subset.py",HERE/"layout_hotspot.py",HERE/"results_index.py")},
        limits=["Synthetic cell sizes and within-module nets; provided module interconnect counts retained exactly", "Module dynamic watts supplied by annealing YAML; additional intermodule wire power is estimated; leakage not supplied", "HotSpot final temperature only when explicitly enabled; differentiable optimization uses a resistance proxy", "IPC extrapolation of bundled gem5 baseline, not a new gem5 run", "Density bound and source distance/tier preferences are soft objectives, not final backend guarantees", "No PDK, true STA, detailed routing, sliding-window bond DRC or DRG-3D replication"])
    save_json(out/"manifest.json",manifest)
    from layout_svg import render
    render(out,d,r,labels,rows,saved,selected)
    save_json(out/"run_info.json",dict(started_at=started,kind="quick" if args.quick else args.run_kind,status="complete",algorithm="config-driven cell refinement",command_arguments=sys.argv[1:]))
    update_index(ROOT/"results",out)
    print("Saved:",out,flush=True)
    if not valid:print("No feasible optimized candidate; selected_candidate is diagnostic only.",flush=True)
    print("Elapsed {:.1f} seconds".format(time.time()-start),flush=True)
    return 0


if __name__=="__main__":
    try:raise SystemExit(main())
    except (ValueError,OSError,KeyError) as error:
        print("ERROR:",error,file=sys.stderr);raise SystemExit(2)
