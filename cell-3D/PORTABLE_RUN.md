# 从模块级最优解继续细粒度优化

输入文件保留现有格式，不需要补写另一套 YAML。

- `config.yaml.json`：虽然扩展名是 YAML/JSON，内容实际是布局摘要文本。它决定 die、模块 BOT/TOP 分层、x/y/w/h、硬模块、HBT pitch/高度/密度上限、面积限制。可以换成同格式的 `config.yaml`。
- `folding_dse_annealing_cfg.yaml`：提供模块 `power_w`、`interconnect`、时钟周期/HBT 延时、温度 RC 系数、热堆栈、HotSpot 封装、临界模块、距离约束、bond 预留比例和窗口。旧分层和旧坐标不覆盖最终解。
- 自动规范 `if_ctrl→if_ctl`、`l2_ctrl→l2_ctl`，在布局使用 `mm` 时映射 `mmu→mm`。
- 完整项目中默认读取上一级 `folding_dse/folding_dse_annealing_cfg.yaml`；便携包中没有该目录时使用包内同名配置。`--annealing-config` 始终可以覆盖默认路径。
- 每次运行保存输入原件、SHA256、有效配置、估算参数和环境信息。输出目录必须为空，原始配置不会被改写。

本组输入模块动态功耗合计 **0.845 W**，18 对模块连接。`interconnect` 是模块对的信号数量，并不是门级网表；跨层信号为 **1360**，保留数量，不为匹配摘要的 8582 而缩放。输入温度只作参考，不拟合功耗。

输入摘要 HBT 上限 40000/mm²、辅助配置 20000/mm² 存在冲突，按最终解使用 40000/mm²，并保留 20% 给时钟/电源等，当前信号上限 32000/mm²。若 20000 才是工艺上限，应在最终解的配置摘要中改成 20000 再跑。程序会报告冲突。坐标累计面积与摘要面积不同，也按坐标计算。

## Windows 云桌面

优先用 `cell3d_windows_x64_offline.zip`，解压到可写目录；不要直接在 ZIP 中运行。包内有独立 Python 3.12 和 NumPy，不需要管理员权限、联网安装、GPU 或 Codex。

1. 替换两个输入配置文件，保持布局摘要的节标题、字段和模块名一致。
2. 双击 `run_layout.cmd` 即运行三种权重方案。输出在程序旁边 `runs/日期/时间_layout/`。
3. 打开输出的 `index.html` 查看优化前后图、拼图区域、温度图和帕累托诊断图。

也可以在 PowerShell 中明确指定任意配置路径：

```powershell
.\run_layout.cmd --check
.\run_layout.cmd --config "D:\项目\config.yaml" --annealing-config "D:\项目\folding_dse_annealing_cfg.yaml" --output "D:\结果\新的一次运行"
.\run_layout.cmd --quick --output ".\runs\quick_check"
.\runtime\python.exe .\test_layout.py
```

`--quick` 只用于检查环境和配置，不应作为正式优化结果。正式默认为区域 360 步、cell 180 步、布线选择 160 步，固定随机种子可复现。新配置没有合法形状或放不下 cell 时会报错，不会放宽形状约束偷偷输出“最优解”。

## 已安装 Python 的 Windows / Linux

源码包要求 Python ≥3.9、NumPy ≥1.24。离线 Windows 包要求 Windows 10/11 x64；它不适用于 Linux 或 ARM。Linux 使用源码包和本机 Python。

```sh
python3 -m pip install -r requirements_portable.txt
sh run_layout.sh --check
sh run_layout.sh --config ./config.yaml --annealing-config ./folding_dse_annealing_cfg.yaml --output ./runs/run1
python3 test_layout.py
```

默认优化及报告用热阻代理模型，运行不依赖 WSL。要生成 **HotSpot** 最终温度，需显式提供本机可执行文件：

```sh
cd third_party/HotSpot
make hotspot
cd ../..
python3 run_layout.py --hotspot-exe ./third_party/HotSpot/hotspot --output ./runs/hotspot_run
```

Windows 可以用已有 WSL 环境编译 HotSpot，并指定 `--hotspot-wsl 发行版名称`。梯度阶段仍使用可微热阻模型；最终评估调用真正的 HotSpot。HotSpot 失败会报错，不会默默改用代理温度。包内保留上游许可证和来源。

## 后端留白和形状

“拼满平面”是模块所属区域覆盖可用平面，**不是实际 cell 占满平面**。当前约束：

- cell 暂估 8×4 μm，按原软模块面积的 65% 生成 cell 数量，固定数目和分层。
- cell 左右各留 1 μm padding；每 10 行留一行（约 10%）不摆功能 cell，供 CTS/缓冲/ECO 使用。
- 硬模块固定矩形，周围 keepout 为辅助配置 `module_gap_mm/2`，当前 4 μm。过窄的剩余带作为 routing/filler margin，不强行分配 cell。
- 拼图区域必须连通、无孔；包围盒长宽比 ≤3，紧凑度 `P²/(16A)≤2.5`，与目标分配面积偏差 ≤25%。
- 每个 cell 加 padding 后都必须完全位于所属区域、行/site 对齐且不与其他 cell 重叠。region/cell 检查为硬检查，70% 密度目标和源文件的距离/层偏好为软约束；后者另存 CSV。

预留不是后端签核保证。真实 CTS、hold 修复、PDN/时钟金属占用、宏引脚逃逸和拥塞可能要求更多留白；应该基于 PDK 和后端结果调整，不能把区域都接壤等同于标准单元满铺。

可用 `--settings settings.json` 覆盖估算参数，不必改代码：

```json
{"cell_width_um":8,"cell_height_um":4,"initial_utilization":0.65,"cell_padding_um":1,"cts_reserve_row_fraction":0.10,"density_upper_bound":0.70}
```

完整实际参数写入每次输出的 `assumptions.json`。未知参数名会报错。时钟延迟、cell 尺寸、RC、金属容量、活动率、电压、IPC 内存占比没有实际工艺/网表支撑，是估算参数；辅助文件的 annealing 迭代设置、旧几何搜索设置不适用于本梯度算法。

## 结果如何理解

报告同时保存名义频率指标和满足估算温度/延时上限后降频的指标。辅助配置 `clock_period_ps=333` 对应 3.003 GHz；模块动态功耗按该参考频率处理。不同频率下的温度/功耗不能直接归因于布局优化，应比较 `nominal_peak_C` / `nominal_power_W`。

全部布局存在布线溢出时，`winner=null`、`pareto=[]`，图上红点只是不可行方案的权衡。另列 `diagnostic_pareto_including_infeasible` 供探索。`selected_candidate` 是诊断候选，不是可签核最优解。两种同层绕线方向及借用另一层金属的候选由可微 softmax 优化，再离散化并分配 HBT site。

逐 cell 连接和门延时仍由模块数量生成；IPC 由随包 gem5 基线解析外推，没有重新跑 gem5。WNS/TNS 是合成路径模型的估计，并非 STA。没有执行 CTS、DRC 或详细布线，也不是 NVIDIA 论文的完整复现。真实门级网表和库可接入下一阶段，不能据此宣称实际芯片的性能。

参考：[OpenROAD 全局布局](https://openroad.readthedocs.io/en/latest/main/src/gpl/README.html)、[详细布局 padding](https://openroad.readthedocs.io/en/latest/main/src/dpl/README.html)。
