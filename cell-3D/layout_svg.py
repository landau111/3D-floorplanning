"""Dependency-free SVG and HTML output for the portable optimizer."""
from html import escape
from pathlib import Path
import json
import math
import numpy as np

COLORS=["#64748b","#64748b","#4f46e5","#b45309","#a21caf","#be185d","#2563eb","#0e7490","#0891b2","#ea580c","#65a30d","#4d7c0f","#7c3aed","#c27719","#0d9488","#9333ea"]


def svg(width,height):
    return ['<svg xmlns="http://www.w3.org/2000/svg" width="{}" height="{}" viewBox="0 0 {} {}">'.format(width,height,width,height),
        '<rect width="100%" height="100%" fill="white"/><style>text{font-family:Arial,sans-serif;fill:#172033}.title{font-size:24px;font-weight:bold}.note{font-size:13px;fill:#475569}</style>']


def text(items,x,y,value,size=14,color=None):
    items.append('<text x="{}" y="{}" font-size="{}"{}>{}</text>'.format(x,y,size,' style="fill:{}"'.format(color) if color else '',escape(str(value))))


def save(path,items):
    Path(path).write_text("\n".join(items+['</svg>']),encoding="utf-8")


def panel(items,d,r,labels,xy,z,px,py,width,mode,title):
    scale=width/d.extent[0];height=d.extent[1]*scale
    text(items,px,py-14,title,17)
    items.append('<rect x="{}" y="{}" width="{}" height="{}" fill="#f1f5f9" stroke="#94a3b8"/>'.format(px,py,width,height))
    def rect(x,y,w,h,fill,stroke=None,opacity=1):
        items.append('<rect x="{:.3f}" y="{:.3f}" width="{:.3f}" height="{:.3f}" fill="{}"{} opacity="{}"/>'.format(px+x*scale,py+(d.extent[1]-y-h)*scale,w*scale,h*scale,fill,' stroke="{}"'.format(stroke) if stroke else '',opacity))
    if mode!="initial":
        # Paint only assigned regions; gray strips are intentionally reserved routing space.
        for y in range(r.ny):
            row=labels[z,y];start=0
            while start<r.nx:
                mi=row[start];end=start+1
                while end<r.nx and row[end]==mi:end+=1
                if mi>=0:rect(start*r.step[0],y*r.step[1],(end-start)*r.step[0],r.step[1],COLORS[mi%len(COLORS)],opacity=.15)
                start=end
        # Explicit horizontal CTS rows, including all reserved rows within regions.
        period=max(2,round(1/d.settings["cts_reserve_row_fraction"]))
        for sy in range(period-1,math.floor(d.extent[1]/d.h),period):
            y=(sy+.5)*d.h;gy=min(r.ny-1,int(y/r.step[1]));row=labels[z,gy];start=0
            while start<r.nx:
                end=start+1
                while end<r.nx and (row[end]>=0)==(row[start]>=0):end+=1
                if row[start]>=0:rect(start*r.step[0],sy*d.h,(end-start)*r.step[0],d.h,"#22c55e",opacity=.25)
                start=end
    for mi,m in enumerate(d.mods):
        if m["tier"]!=z:continue
        if m["hard"]:
            x,y,w,h=m["rect_mm"];rect(x,y,w,h,"#cbd5e1","#475569")
            text(items,px+(x+w/2)*scale,py+(d.extent[1]-y-h/2)*scale,m["name"]+" [hard]",12)
        elif mode=="initial":
            x,y,w,h=m["rect_mm"];rect(x,y,w,h,COLORS[mi%len(COLORS)],COLORS[mi%len(COLORS)],.15)
        if not m["hard"]:
            ids=d.ids[mi];paths=[]
            if mode!="regions":
                for cx,cy in xy[ids]:
                    x=px+(cx-d.w/2)*scale;y=py+(d.extent[1]-cy-d.h/2)*scale
                    paths.append('M{:.2f},{:.2f}h{:.2f}v{:.2f}h-{:.2f}z'.format(x,y,d.w*scale,d.h*scale,d.w*scale))
                items.append('<path d="{}" fill="{}" opacity=".82"/>'.format(''.join(paths),COLORS[mi%len(COLORS)]))
            if mode=="initial":
                x,y,w,h=m["rect_mm"];cx,cy=x+w/2,y+h/2
            else:
                yy,xx=np.nonzero(labels[z]==mi);cx=(xx.mean()+.5)*r.step[0];cy=(yy.mean()+.5)*r.step[1]
            tx=px+cx*scale;ty=py+(d.extent[1]-cy)*scale
            items.append('<text x="{:.2f}" y="{:.2f}" font-size="11" text-anchor="middle" stroke="white" stroke-width="3" paint-order="stroke">{}</text>'.format(tx,ty,escape(m["name"])))
    if mode!="initial":
        segments=[]
        for y,x in zip(*np.nonzero(labels[z]>=0)):
            mi=labels[z,y,x]
            for yy,xx,a,b in ((y-1,x,(x,y),(x+1,y)),(y+1,x,(x,y+1),(x+1,y+1)),(y,x-1,(x,y),(x,y+1)),(y,x+1,(x+1,y),(x+1,y+1))):
                if not(0<=yy<r.ny and 0<=xx<r.nx and labels[z,yy,xx]==mi):
                    ax,ay=px+a[0]*r.step[0]*scale,py+(d.extent[1]-a[1]*r.step[1])*scale
                    bx,by=px+b[0]*r.step[0]*scale,py+(d.extent[1]-b[1]*r.step[1])*scale
                    segments.append('M{:.2f},{:.2f}L{:.2f},{:.2f}'.format(ax,ay,bx,by))
        items.append('<path d="{}" fill="none" stroke="#475569" stroke-width=".7"/>'.format(''.join(segments)))


def layout_figures(out,d,r,labels,saved,selected):
    width=500;height=d.extent[1]/d.extent[0]*width
    items=svg(1150,2*height+220);text(items,35,35,"Input placement -> nonrectangular cell refinement",23)
    text(items,35,60,"Fixed partition and hard macros | die {:.3f} x {:.3f} mm | {} cells".format(*d.extent,int(d.movable.sum())),13)
    for row,z in enumerate((1,0)):
        y=110+row*(height+60)
        panel(items,d,r,labels,saved['initial'][0],z,35,y,width,"initial",("TOP" if z else "BOT")+" / input")
        panel(items,d,r,labels,saved[selected['run']][0],z,610,y,width,"cells",("TOP" if z else "BOT")+" / "+selected['run'])
    text(items,35,2*height+190,"Pale color: ownership; dark blocks: cells; green rows: CTS reserve; gray: macro/routing margin",12)
    save(out/"before_after.svg",items)
    items=svg(1150,height+160);text(items,35,35,"Optimized module regions with backend margin",23)
    for z in range(2):panel(items,d,r,labels,saved[selected['run']][0],z,35+575*z,90,width,"regions","BOT" if z==0 else "TOP")
    text(items,35,height+130,"Region coverage excludes hard macros/keepout and thin routing margins; physical cell fill is lower",12)
    save(out/"regions.svg",items)


def temperature_figure(out,d,saved,selected):
    temp=saved[selected["run"]][1];g=round(math.sqrt(len(temp)/2));temp=temp.reshape(2,g,g)
    lo=float(temp.min());hi=float(temp.max());width=500;height=d.extent[1]/d.extent[0]*width
    items=svg(1150,height+160);text(items,35,35,"Operating temperature at {:.3f} GHz / {}".format(selected["frequency_GHz"],selected["thermal_backend"]),23)
    for z in range(2):
        px=35+575*z;py=90;text(items,px,75,"{} / peak {:.2f} C".format("BOT" if z==0 else "TOP",temp[z].max()),16)
        for y in range(g):
            for x in range(g):
                f=(temp[z,y,x]-lo)/max(.001,hi-lo);rgb=(round(40+210*f),round(90+75*(1-f)),round(205-170*f))
                items.append('<rect x="{:.2f}" y="{:.2f}" width="{:.2f}" height="{:.2f}" fill="rgb({},{},{})"/>'.format(px+x*width/g,py+(g-1-y)*height/g,width/g+.1,height/g+.1,*rgb))
    text(items,35,height+130,"Shared scale {:.2f} to {:.2f} C | assumed materials, cell sizes and parasitics".format(lo,hi),12)
    save(out/"temperature.svg",items)


def pareto_figure(out,rows):
    items=svg(1150,600);text(items,35,35,"Power / Temperature / Throughput trade-offs",23)
    for panel_index,(key,label) in enumerate((("power_W","Power (W)"),("peak_C","Peak temperature (C)"))):
        left=80+560*panel_index;top=90;pw=430;ph=390
        xs=np.array([r[key] for r in rows]);ys=np.array([r["mean_bips"] for r in rows]);xmin,xmax=xs.min(),xs.max();ymin,ymax=ys.min(),ys.max()
        dx=max(.01,(xmax-xmin)*.2);dy=max(.005,(ymax-ymin)*.2);xmin-=dx;xmax+=dx;ymin-=dy;ymax+=dy
        for i in range(6):
            x=left+i*pw/5;y=top+i*ph/5
            items.append('<path d="M{} {}V{} M{} {}H{}" stroke="#e2e8f0" fill="none"/>'.format(x,top,top+ph,left,y,left+pw))
            text(items,x-15,top+ph+25,"{:.3f}".format(xmin+i*(xmax-xmin)/5),11)
            text(items,left-55,y+4,"{:.4f}".format(ymax-i*(ymax-ymin)/5),11)
        text(items,left+160,top+ph+55,label,14);text(items,left,top-20,"Mean throughput (BIPS)",14)
        for row_index,r in enumerate(rows):
            x=left+(r[key]-xmin)/(xmax-xmin)*pw;y=top+(ymax-r["mean_bips"])/(ymax-ymin)*ph
            color="#64748b" if r["run"]=="initial" else "#ea580c" if r["feasible"] else "#dc2626"
            items.append('<circle cx="{:.2f}" cy="{:.2f}" r="5" fill="{}"/>'.format(x,y,color))
            if r["run"]=="initial":text(items,x+8,y-8,r["run"],12)
            else:
                lx=left+pw-110;ly=top+30+row_index*25
                items.append('<path d="M{:.2f} {:.2f}L{:.2f} {:.2f}" fill="none" stroke="{}" opacity=".5"/>'.format(x,y,lx-5,ly-5,color))
                text(items,lx,ly,r["run"],12)
    text(items,35,570,"Gray: input; orange: feasible refinement; red: routing-infeasible diagnostic | IPC is estimated",12)
    save(out/"pareto.svg",items)


def render(out,d,r,labels,rows,saved,selected):
    layout_figures(out,d,r,labels,saved,selected);temperature_figure(out,d,saved,selected);pareto_figure(out,rows)
    header=["run","frequency_GHz","power_W","peak_C","mean_bips","nominal_WNS_ps","nominal_TNS_ns","route_overflow_tracks","feasible"]
    table='<table><tr>'+''.join('<th>'+escape(v)+'</th>' for v in header)+'</tr>'
    for row in rows:table+='<tr>'+''.join('<td>'+escape(str(round(row[k],5) if isinstance(row[k],float) else row[k]))+'</td>' for k in header)+'</tr>'
    table+='</table>'
    areas=[r.free[z].sum()*np.prod(r.step) for z in range(2)]
    cellareas=[d.cell_area[d.z==z].sum() for z in range(2)]
    utilization=[float(a/b) for a,b in zip(cellareas,areas)]
    reserve=dict(eligible_region_area_mm2=[float(v) for v in areas],actual_cell_area_mm2=[float(v) for v in cellareas],
        physical_cell_utilization=utilization,cts_reserved_row_fraction=d.settings["cts_reserve_row_fraction"],
        cell_side_padding_um=d.settings["cell_padding_um"],macro_keepout_mm=d.settings["macro_keepout_mm"],
        nominal_module_dynamic_power_W=sum(d.aux["power_w"].values()))
    (out/"backend_margin.json").write_text(json.dumps(reserve,indent=2),encoding="utf-8")
    html='<!doctype html><meta charset="utf-8"><title>CLIP-3D cell refinement</title><style>body{font:15px Arial,sans-serif;max-width:1200px;margin:28px auto;color:#172033}table{border-collapse:collapse;font-size:12px}td,th{border:1px solid #cbd5e1;padding:8px}img{width:100%;height:auto}p{line-height:1.7}</style>'
    html+='<h1>细粒度布局优化结果</h1><p>最优解配置提供几何、分层和硬模块；退火配置提供功耗、互连及物理参数。参考温度不用于反推功耗。当前 cell 尺寸、内部网络和 RC 仍为估算。</p>'
    html+='<p>所选候选：<b>'+escape(selected["run"])+('</b>（可行）' if selected["feasible"] else '</b>（诊断候选，存在拥塞违例）')+'；温度后端：'+escape(selected["thermal_backend"])+ '。IPC 为解析估计。</p>'
    html+='<p>实际 cell 利用率：BOT {:.1%}、TOP {:.1%}；预留约 {:.0%} 行用于 CTS，cell 两侧各留 {:.1f} μm padding。领地填满不等于实体 cell 填满。</p>'.format(*utilization,d.settings["cts_reserve_row_fraction"],d.settings["cell_padding_um"])
    html+='<p>下面主表和温度图使用满足估算路径延时后降频的运行状态。为了单独比较布局，名义频率 {:.3f} GHz 下各方案的功耗与峰值温度另列如下；均为模型结果。</p>'.format(d.settings["nominal_GHz"])
    html+='<table><tr><th>方案</th><th>名义功耗 W</th><th>名义峰值 °C</th></tr>'
    for row in rows:html+='<tr><td>{}</td><td>{:.4f}</td><td>{:.2f}</td></tr>'.format(escape(row["run"]),row["nominal_power_W"],row["nominal_peak_C"])
    html+='</table><p>估算降频状态及性能：</p>'
    html+=table
    for name in ('before_after','regions','temperature','pareto'):html+='<h2>'+name+'</h2><img src="'+name+'.svg">'
    html+='<p><a href="manifest.json">参数与运行记录</a> · <a href="metrics.csv">指标表</a> · <a href="selected_cells.csv">逐 cell 坐标</a> · <a href="backend_margin.json">后端留白</a> · <a href="selected_soft_constraints.csv">源配置软约束</a></p>'
    (out/"index.html").write_text(html,encoding="utf-8")
