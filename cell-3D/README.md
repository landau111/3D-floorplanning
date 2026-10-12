# cell-3D：从模块级最终布局继续做细粒度优化

**[最新正式结果](results/LATEST.md) · [所有历史运行](results/README.md) · [今晚算法与数学原理](docs/ALGORITHM_2026-10-13.md) · [云桌面运行说明](docs/PORTABLE_RUN.md)**

当前正式运行完成了非矩形区域、cell 合法化和 HotSpot 温度评估，但所有候选仍有布线溢出；没有可行 winner，正式帕累托集合为空。selected 是诊断方案。功耗、IPC、时序含估算，不能作为签核结果。

## 目录与文件用途

```text
cell-3D/
  run.py / run_layout.cmd / run_layout.sh   统一运行入口
  configs/                               两份输入原件
  src/                                   当前优化器与输出代码
  data/                                  gem5 IPC 基线
  tests/                                 数学、合法性、结果管理验证
  tools/                                 打包、索引、历史重放工具
  docs/                                  数学解析与移植运行说明
  results/YYYY-MM-DD/运行名/              全部历史及新运行
  archive/                               历史代码和发布源码快照
  releases/                              源码/离线包与 SHA256
```

|文件|作用|
|---|---|
|[run.py](run.py)|统一 Python 入口，自动定位 src，不依赖启动工作目录|
|[run_layout.cmd](run_layout.cmd)|Windows 启动，优先包内 runtime，其次 LAYOUT_PYTHON/系统 Python|
|[run_layout.sh](run_layout.sh)|Linux/macOS Python 启动入口|
|[requirements.txt](requirements.txt)|当前唯一第三方运行依赖 NumPy，不需要 GPU/PyYAML|
|[.gitignore](.gitignore)|忽略缓存、虚拟环境、runtime；结果不忽略|
|[.gitattributes](.gitattributes)|保留原始字节，避免换行转换破坏输入/历史 SHA256|
|[configs/config.yaml.json](configs/config.yaml.json)|最终模块布局摘要原件：die、BOT/TOP、x/y/w/h、硬模块、HBT 限制|
|[configs/folding_dse_annealing_cfg.yaml](configs/folding_dse_annealing_cfg.yaml)|辅助输入：功耗、模块连接、时钟、材料/热堆栈、距离偏好|
|[data/layout_baseline.json](data/layout_baseline.json)|封装的 2GHz gem5 工作负载基线；供 IPC 外推，不重新启动 gem5|
|[src/run_layout.py](src/run_layout.py)|Model 合成 cell/网；Regions 区域；Cells 梯度放置/合法化；Routing 路径；evaluate/Pareto；CLI|
|[src/layout_input.py](src/layout_input.py)|解析原格式、统一别名、检矩形与参数冲突；最终布局优先|
|[src/yaml_subset.py](src/yaml_subset.py)|无 PyYAML 的受限 YAML 读取；只支持本项目所需语法|
|[src/layout_hotspot.py](src/layout_hotspot.py)|构建真实 HotSpot 输入、原生/WSL 执行、读取原生温度网格|
|[src/layout_svg.py](src/layout_svg.py)|生成布局、区域、温度、帕累托 SVG 和单次 HTML|
|[src/results_index.py](src/results_index.py)|日期输出、防覆盖、每次文件说明、总索引、最新正式入口|
|[tests/test_layout.py](tests/test_layout.py)|输入、解析梯度与有限差分、cell/形状/bond 合法性、发布数据检查|
|[tests/test_results_index.py](tests/test_results_index.py)|目录重名防覆盖、快速/未完成运行不覆盖正式入口|
|[tools/build_layout_bundle.py](tools/build_layout_bundle.py)|生成源码及独立 Python/NumPy 的 Windows x64 离线 ZIP|
|[tools/rebuild_results_index.py](tools/rebuild_results_index.py)|重建全部结果 README、HTML、catalog/latest，不修改原始数据|
|[tools/validate_reorganization.py](tools/validate_reorganization.py)|核对发布源码哈希、算法 AST、输入字节、四种方案数组和指标完全一致|
|[tools/validate_portability.py](tools/validate_portability.py)|维护者从实际离线 ZIP 解压，验证中文/空格路径、启动器、换配置与正式入口保持|
|[tools/legacy_runner.py](tools/legacy_runner.py)|在新结果目录建立旧环境，测试/重放历史代码，不覆盖原归档|
|[docs/ALGORITHM_2026-10-13.md](docs/ALGORITHM_2026-10-13.md)|实际修改、输入来源、数学、梯度、合法化、性能估算、结果与限制|
|[docs/PORTABLE_RUN.md](docs/PORTABLE_RUN.md)|Windows 云桌面、Linux、HotSpot 编译、换配置、故障处理|
|[docs/PORTABILITY_VALIDATION.json](docs/PORTABILITY_VALIDATION.json)|移植验证证据及尚未验证的环境|
|[docs/REORGANIZATION_VALIDATION.json](docs/REORGANIZATION_VALIDATION.json)|目录调整前后完整复跑的逐项一致性证据|
|[archive/README.md](archive/README.md)|历史代码/快照逐文件说明和历史结果可比性限制|
|[releases/README.md](releases/README.md)|ZIP 范围、使用方式、校验值|

## 编译与仿真

优化器是 Python/NumPy，**无需编译**。在仓库的 cell-3D 目录运行：

```powershell
python -m pip install -r requirements.txt
python run.py --check
python -m unittest discover -s tests
python run.py --config configs/config.yaml.json --annealing-config configs/folding_dse_annealing_cfg.yaml
```

默认区域 360 次、每种 cell 方案 180 次、每种路由 160 次，seed=20261012。快速运行 `python run.py --quick` 使用 40/12/16 次，属于 quick，不更新最新正式结果。普通运行使用可微热阻代理。要复现正式 HotSpot 评估：

```powershell
python run.py --config configs/config.yaml.json --annealing-config configs/folding_dse_annealing_cfg.yaml --hotspot-wsl Codex-C910-gem5
```

这是本机 WSL 发行版名，其他机器换成自己的发行版；唯一需编译的 HotSpot 见 [运行文档](docs/PORTABLE_RUN.md)。没有 WSL 也能使用默认代理后端。

Windows 云桌面解压 [离线 ZIP](releases/cell3d_windows_x64_offline.zip)，替换 configs 输入，双击 run_layout.cmd。无需安装 Python：

```powershell
.\run_layout.cmd --check
.\run_layout.cmd --config "D:\项目\config.yaml" --annealing-config "D:\项目\folding_dse_annealing_cfg.yaml"
```

完整仓库默认先读上一级 folding_dse/folding_dse_annealing_cfg.yaml；便携包回退到 configs 副本。建议明确指定 `--annealing-config`。可选 `--settings overrides.json` 覆盖 assumptions 中已有的数值键，不改原输入格式。`--profiles`、`--seed`、三类 `--*-steps` 可调整搜索；实际参数保存到运行目录。

## 结果怎么找、文件怎么读

自动创建 results/YYYY-MM-DD/HHMMSS_layout（上海时区）；同秒重名追加序号，不覆盖旧数据。`--output` 可指定空目录；位于标准日期目录外的结果不进总索引。`--run-kind environment_validation` 标记移植测试，不更新正式入口。每个运行的 **README.md 逐一列出实际文件和作用**。

|结果文件|作用|
|---|---|
|results/LATEST.md、latest.json|最新完成的正式结果路径；程序完成不等于布线可行|
|results/README.md、index.html、catalog.json|所有日期/运行/分类/状态总目录|
|results/history_catalog.json|整理前历史日期依据、分类、失败原因|
|运行目录/README.md、run_info.json|逐文件说明；时间、命令、分类、完成状态|
|input_config.yaml.json、input_annealing_cfg.yaml|本次配置原件，不被程序改写|
|effective_input.json、assumptions.json|解析后输入与估算/派生参数|
|manifest.json|参数、环境、seed、源码哈希、合法性、winner、正式/诊断 Pareto、模型限制|
|metrics.csv|名义/工作点功耗温度时序、频率、IPC/BIPS、能效、布线指标|
|initial/balanced/timing/thermal.npz|cell 坐标、层、模块、连接、区域标签、温度、路由选择数组|
|shape_trace.json、各方案_trace.json|区域检查点、cell 和路由迭代轨迹|
|module_shapes.csv、selected_soft_constraints.csv|几何硬检查、距离/层偏好软约束达成情况|
|selected_cells.csv、selected_bonds.csv、selected_route_guides.csv|诊断候选逐 cell 坐标、bond 位置、路径/主干层|
|各方案_module_temperatures.csv|输入参考温度与计算平均温度，不用于拟合功耗|
|backend_margin.json|区域面积、真实 cell 面积、padding、CTS 行预留统计|
|before_after/regions/temperature/pareto.svg（及 .png）|前后布局、拼图区域、温度、帕累托诊断；SVG 自动生成，PNG 发布时导出|
|各方案_hotspot/|HotSpot 原始输入、稳态输出和日志；只有启用才生成|
|RUN_ANALYSIS.md|原发布结果说明，保留历史原文；现行完整解释在 docs|
|历史日期目录中的 figures/|历史出版 PNG/SVG/PDF；输入模型不同，不能直接比较今晚指标|

NPZ 示例：`python -c "import numpy as np; d=np.load('results/日期/运行名/timing.npz'); print(d.files,d['xy_mm'].shape)"`。重建总目录：`python tools/rebuild_results_index.py`。

HotSpot 子目录逐文件：bottom.flp/top.flp 为两层功耗网格几何，hb_interface.flp/tim.flp 为无源材料层；stack.lcf 为层序/材料/厚度；power.ptrace 为网格功耗；hotspot.config 为求解器/封装设置；hotspot.steady 为 block 稳态输出，hotspot.grid.steady 为原生网格稳态温度；stdout.txt/stderr.txt 为执行输出；manifest.json 为命令、功耗守恒、峰值及工具哈希。移植测试中 validation_stdout.txt 是启动器执行日志。

旧代码在 archive 保留，不参与默认计算。9 月 25 日日期依据原文件修改日期，不是精确运行时刻；失败的 20261013_full 保留输入和原因。部分早期开发版本没有完整源码快照，不能保证用当前代码逐数复现。
