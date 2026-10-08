# 仿真结果

默认按北京时间保存到 `YYYY-MM-DD/HHMMSS_运行类型/`。同一天多次运行各有独立目录；重名自动加编号。
每次运行的 `README.md` 链接帕累托图、入选方案布局图、温度图和模块坐标CSV。

## 已有完整搜索

- [2026-10-08：40轮 HotSpot 搜索](2026-10-08/hotspot_40rounds/README.md)：239个候选，57个非支配候选，4个代表方案。
- [帕累托图](2026-10-08/hotspot_40rounds/pareto.svg)
- [4个方案的模块坐标汇总](2026-10-08/hotspot_40rounds/all_module_coordinates.csv)

旧示例已从 `examples/hotspot_20261008/` 移至这里，图、温度和布局数值保持不变。
历史搜索保留4个方案的完整HotSpot输入输出；所有239个候选的指标和搜索过程也保留。
候选全集的原始缓存仍在本机 `folding_dse/hotspot_results/hotspot_pool/`，未重复复制。
新运行的原始缓存位于自己的 `hotspot_pool/`，默认不纳入Git，其余结果可按需上传。

## 模块坐标定义

`module_coordinates.csv` 每个模块一行，`all_module_coordinates.csv` 另有方案编号、候选编号、搜索权重组。

| 字段 | 含义 |
| --- | --- |
| module | 模块名 |
| layer | bottom下层 / top上层 |
| x_mm, y_mm | 模块左下角坐标，各层die左下角为原点 |
| w_mm, h_mm | 模块宽、高 |
| center_x_mm, center_y_mm | 模块中心坐标 |

所有坐标和尺寸单位均为mm，中心曼哈顿距离可直接用中心坐标计算。
