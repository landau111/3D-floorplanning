"""Date-based output allocation and inspectable historical result indexes."""
import csv
import datetime
import html
import json
import re
from pathlib import Path

ZONE = datetime.timezone(datetime.timedelta(hours=8))


def read_json(path, default=None):
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else default


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def allocate_output(root, requested=None, now=None):
    if requested is not None:
        output = Path(requested).resolve()
        if output.exists() and (not output.is_dir() or any(output.iterdir())):
            raise ValueError("Output must be a new or empty directory: " + str(output))
        return output
    now = now or datetime.datetime.now(ZONE)
    base = Path(root) / now.strftime("%Y-%m-%d") / now.strftime("%H%M%S_layout")
    output = base
    suffix = 2
    while output.exists():
        output = base.with_name(base.name + "_%02d" % suffix)
        suffix += 1
    return output.resolve()


def purpose(name):
    exact = {
        "manifest.json": "运行参数、环境、源码 SHA256、可行性与候选选择记录",
        "run_info.json": "运行时间、命令参数、正式/快速/环境验证分类和完成状态",
        "input_config.yaml.json": "本次最终模块布局输入原件",
        "input_annealing_cfg.yaml": "本次功耗、连接、热堆栈等辅助输入原件",
        "effective_input.json": "解析、名称规范化后的实际输入及冲突提示",
        "assumptions.json": "本次实际使用的估算/派生参数",
        "metrics.csv": "所有候选的功耗、温度、频率、IPC/BIPS、时序和布线指标",
        "module_shapes.csv": "各模块连通、孔洞、面积误差、长宽比和紧凑度检查",
        "shape_trace.json": "区域优化迭代和合法检查点选择记录",
        "selected_cells.csv": "诊断候选逐 cell 的模块、层、坐标和可移动属性",
        "selected_bonds.csv": "诊断候选实际分配的跨层 bond 坐标",
        "selected_route_guides.csv": "外部连接的 XY/YX 路径及主干层",
        "selected_soft_constraints.csv": "源配置距离与层偏好约束的达成情况",
        "backend_margin.json": "后端留白、利用率、padding、时钟预留统计",
        "index.html": "本次运行交互/图表浏览入口",
        "RUN_ANALYSIS.md": "原发布运行的分析说明（历史原文）",
        "README.md": "本次运行分类、指标与逐文件说明（自动生成）",
    }
    if name in exact:
        return exact[name]
    if name.endswith(".npz"):
        return "压缩 NumPy 数据：坐标、层、模块、连接、区域标签、温度及路由选择"
    if name.endswith("_module_temperatures.csv"):
        return "各模块输入参考温度和本次计算平均温度"
    if name.endswith("_trace.json"):
        return "该权重方案 cell 优化与布线优化的迭代轨迹"
    if name.endswith("_hotspot"):
        return "HotSpot 原始输入/输出：配置、层/材料、功耗迹线、稳态温度及执行日志"
    if name.startswith("before_after"):
        return "优化前后逐 cell 布局图"
    if name.startswith("regions"):
        return "非矩形模块归属区域图（区域覆盖率不等于标准单元利用率）"
    if name.startswith("temperature"):
        return "两层温度分布图"
    if name.startswith("pareto"):
        return "帕累托诊断图；不可行候选不会进入正式前沿"
    if name == "figures":
        return "历史出版图：PNG/SVG/PDF，保留原始版本"
    return "历史运行原始数据/图表；原算法说明见 archive/legacy 中的文档"


def update_index(root, just_completed=None):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    history = {v["path"]: v for v in read_json(root / "history_catalog.json", [])}
    records = []
    for day in sorted(root.iterdir()):
        if not day.is_dir() or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day.name):
            continue
        for folder in sorted(day.iterdir()):
            if not folder.is_dir():
                continue
            relative = folder.relative_to(root).as_posix()
            historical = history.get("results/" + relative, {})
            info = read_json(folder / "run_info.json", {})
            manifest = read_json(folder / "manifest.json", {})
            record = dict(date=day.name, run=folder.name, path=relative,
                          kind=info.get("kind", historical.get("kind", "unclassified")),
                          status=info.get("status", historical.get("status", "unknown")),
                          started_at=info.get("started_at", day.name),
                          date_basis=historical.get("date_basis", "run_info UTC+08 timestamp"),
                          note=historical.get("note", ""))
            record["no_feasible_candidate"] = manifest.get("no_feasible_candidate")
            records.append(record)
            lines = ["# " + folder.name, "", "日期：%s；分类：`%s`；状态：`%s`。" % (day.name, record["kind"], record["status"]), "",
                     "日期依据：" + record["date_basis"] + "。", ""]
            if record["note"]:
                lines += [record["note"], ""]
            if record["no_feasible_candidate"]:
                lines += ["**本次没有布线可行的优化候选。selected 文件是诊断候选，不代表后端可用最优解；正式帕累托集合为空。**", ""]
            if (folder / "index.html").exists():
                lines += ["[打开布局与温度图](index.html) · [完整数学分析](../../../docs/ALGORITHM_2026-10-13.md)", ""]
            if (folder / "metrics.csv").exists():
                with (folder / "metrics.csv").open(encoding="utf-8-sig", newline="") as f:
                    rows = list(csv.DictReader(f))
                if rows and "frequency_GHz" in rows[0]:
                    lines += ["|方案|工作频率 GHz|功耗 W|工作温度 °C|溢出 tracks|可行|", "|---|---:|---:|---:|---:|---|"]
                    for row in rows:
                        lines.append("|%s|%.4f|%.4f|%.3f|%.2f|%s|" % (row["run"], float(row["frequency_GHz"]), float(row["power_W"]), float(row["peak_C"]), float(row["route_overflow_tracks"]), row["feasible"]))
                    lines += ["", "温度/功耗对应降频后的工作点；标称频率比较见 metrics.csv 的 nominal 列及算法解析。", ""]
            lines += ["|文件/目录|作用|", "|---|---|"]
            for file in sorted(folder.iterdir()):
                lines.append("|[%s](%s)|%s|" % (file.name, file.name, purpose(file.name)))
            (folder / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    formal = [r for r in records if r["kind"] == "formal" and r["status"] == "complete" and (root / r["path"] / "manifest.json").is_file()]
    latest = max(formal, key=lambda r: (r["date"], r["started_at"], r["run"])) if formal else None
    write_json(root / "catalog.json", records)
    write_json(root / "latest.json", latest)
    latest_md = "# 最新正式结果\n\n"
    if latest:
        latest_md += "[%s](%s/README.md) · [图表入口](%s/index.html) · [指标](%s/metrics.csv)\n\n" % (latest["run"], latest["path"], latest["path"], latest["path"])
        if latest["no_feasible_candidate"]:
            latest_md += "**本次无布线可行候选；所选方案仅供诊断。**\n\n"
    latest_md += "仅完成的 formal 运行更新此入口；quick、环境验证、历史实验和失败运行不会覆盖。\n"
    (root / "LATEST.md").write_text(latest_md, encoding="utf-8")
    lines = ["# 全部运行结果", "", "[最新正式结果](LATEST.md) · [浏览器总入口](index.html) · [机器可读清单](catalog.json)", "", "按运行日期归档；历史时间不明确时使用原目录日期或文件修改日期，具体依据在每次 README 中。完成状态只表示程序完成，并不表示满足布线约束。", "", "|日期|运行|分类|状态|", "|---|---|---|---|"]
    cards = []
    for r in reversed(records):
        lines.append("|%s|[%s](%s/README.md)|%s|%s|" % (r["date"], r["run"], r["path"], r["kind"], r["status"]))
        cards.append('<li><a href="%s/README.md">%s / %s</a> — %s / %s%s</li>' % (r["path"], html.escape(r["date"]), html.escape(r["run"]), r["kind"], r["status"], ' · <a href="%s/index.html">图表</a>' % r["path"] if (root / r["path"] / "index.html").is_file() else ""))
    (root / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    link = '<p><a href="%s/index.html">最新正式结果：%s</a>（结果可行性请查看运行说明）</p>' % (latest["path"], html.escape(latest["run"])) if latest else ""
    (root / "index.html").write_text('<!doctype html><meta charset="utf-8"><title>cell-3D 运行目录</title><style>body{font:16px system-ui;max-width:1100px;margin:40px auto;line-height:1.8}a{color:#1460a0}</style><h1>cell-3D 全部运行</h1>' + link + '<ul>' + ''.join(cards) + '</ul>', encoding="utf-8")
    return latest
