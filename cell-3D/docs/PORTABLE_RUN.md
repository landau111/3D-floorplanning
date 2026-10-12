# 换配置、云桌面与编译运行

## 输入与优先级

configs/config.yaml.json 虽然名称像 YAML/JSON，实际是模块布局摘要文本，原格式不改。决定 die、BOT/TOP、x/y/w/h、硬模块、pitch/高度/密度等。configs/folding_dse_annealing_cfg.yaml 提供 power_w、interconnect、时钟、温度系数、材料/封装、距离偏好等；旧坐标和分层不覆盖最终解。if_ctrl→if_ctl、l2_ctrl→l2_ctl、mmu→mm 自动统一。

完整仓库默认用上一级 folding_dse 配置，便携包用 configs 副本；建议显式 --annealing-config。功耗 0.845W、18 对/10920 根外部连接，跨层 1360 根，不为匹配摘要 8582 而缩放。输入温度只作参考，不拟合功耗。density 最终 40000/mm² 与辅助 20000/mm² 冲突时以最终解为准；20% 预留后信号 32000/mm²。若工艺确为 20000，修改最终配置再跑。

## Windows 云桌面

解压 releases/cell3d_windows_x64_offline.zip 到有写权限的目录，顶层 cell-3D；中文、空格可用。替换 configs 两份输入，保持节标题/字段/模块名，然后双击 run_layout.cmd。不需要管理员权限、网络、GPU 或 Codex；不要在 ZIP 中运行。

```powershell
.\run_layout.cmd --check
.\run_layout.cmd --config "D:\项目\config.yaml" --annealing-config "D:\项目\folding_dse_annealing_cfg.yaml"
.\run_layout.cmd --quick
.\runtime\python.exe -m unittest discover -s tests
```

结果自动放 results/YYYY-MM-DD/HHMMSS_layout；查看 results/index.html 或 LATEST.md。`--output "D:\结果\新的空目录"` 可指定输出，外部路径不进程序内部索引。快速运行不覆盖正式入口。可选 --settings overrides.json，允许覆盖 assumptions 已有键，例如 `{"tracks_per_mm":16000,"cts_reserve_row_fraction":0.15}`。

源码包需要 Python>=3.9、NumPy>=1.24：

```powershell
python -m pip install -r requirements.txt
python run.py --check
python -m unittest discover -s tests
python run.py
```

Python 无需编译。LAYOUT_PYTHON 可指定解释器路径；启动脚本清空 PYTHONHOME/PYTHONPATH 避免污染。程序不依赖历史结果计算；历史发布检查仅在测试中读取。

## Linux / macOS 代理运行

```sh
cd cell-3D
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests
sh run_layout.sh --check
sh run_layout.sh --config configs/config.yaml.json --annealing-config configs/folding_dse_annealing_cfg.yaml
```

Windows 离线 runtime 不能用于 Linux/ARM，需对应平台 Python/NumPy。当前未在 ARM/macOS 机器验证。

## 可选真实 HotSpot：唯一需要编译的部分

默认是可微热阻代理。启用 HotSpot 后仍用代理优化，每个候选结束用真实 HotSpot 64×64 评估标称温度；降频工作点通过线性功耗缩放。是稳态评估，不是 transient/签核。

完整仓库源码在上一级 third_party/HotSpot；便携包在 cell-3D/third_party/HotSpot。Linux/WSL 安装 make 和 C 编译器后，**从 cell-3D 目录**：

```sh
# 完整仓库
make -C ../third_party/HotSpot hotspot SUPERLU=0
python run.py --hotspot-exe ../third_party/HotSpot/hotspot
# 便携包使用下面路径
make -C third_party/HotSpot hotspot SUPERLU=0
python run.py --hotspot-exe third_party/HotSpot/hotspot
```

Windows 先在自己的 WSL 发行版中 cd 到仓库/解压目录并 make，再从 Windows 调用：

```powershell
python run.py --hotspot-wsl Ubuntu --config configs/config.yaml.json --annealing-config configs/folding_dse_annealing_cfg.yaml
```

Ubuntu 换成 `wsl --list --quiet` 中实际名称，本机验证 Codex-C910-gem5。工具定位 HotSpot 并将 Windows 盘符转换为 /mnt 路径，支持含空格参数。默认代理无需 WSL。

## 报错和复现

先 --check；缺 NumPy 用离线包或 pip；非空 output 换新目录；未知模块、重叠/边界/面积错误修输入。没有合法形状检查点直接停止，不自动放宽限制。布线不可行仍保存诊断数据，但 winner=null、no_feasible_candidate=true，不是后端最优解。

复现需相同配置、seed=20261012、360/180/160 次、相同后端；输入、参数、源码哈希、环境均在运行目录。换 Python/NumPy/CPU 可能因浮点差异改变离散选择。验证记录见 PORTABILITY_VALIDATION.json；公司的实际桌面未连接，不能声称已在该机器执行。
