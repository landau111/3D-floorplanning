# 3D-floorplanning

模块级双 die 折叠布局探索：读取脱敏 YAML，搜索模块的上下层、位置和宽高比，通过真实 HotSpot 计算稳态温度，输出五目标帕累托候选。

## 开始使用

CentOS/Linux：Python 3.6+、GCC、GNU make。在仓库根目录运行：

```bash
make test-hotspot
make quick
make explore
```

Windows：运行 `.\run.cmd quick` / `.\run.cmd explore`，自动使用已有 WSL 工具链，或用 `--hotspot-exe` 指定本机 HotSpot。

- **[操作手册](操作手册.md)**：安装、运行、调参、参数比较、输出解读及排错。
- [默认配置](folding_dse/folding_dse_annealing_cfg.yaml)：保留原参数文件样式。
- [模型与算法说明](folding_dse/README.md)：硬/软约束、时序代价和热模型假设。
- [真实 HotSpot 示例](examples/hotspot_20261008/README.md)：4个代表布局、温度图及完整复算输入。

当前面积、功耗、材料和封装包含脱敏估计；RC平方律用于布局排序。模型未接入gem5/McPAT/CACTI，没有真实IPC/BIPS或后端时序签核。
当前Top软偏好存在面积冲突，结果会明确报告各项违例。
