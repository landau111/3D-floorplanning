# puzzle

日期：2026-09-25；分类：`legacy`；状态：`complete`。

日期依据：original files modification date; historical manifest has no explicit run timestamp。

|方案|工作频率 GHz|功耗 W|工作温度 °C|溢出 tracks|可行|
|---|---:|---:|---:|---:|---|
|puzzle__balanced|1.3502|6.3209|70.541|0.00|True|
|puzzle__timing|1.3726|6.3870|70.965|0.00|True|
|puzzle__thermal|1.3420|6.3520|70.607|15.00|False|

温度/功耗对应降频后的工作点；标称频率比较见 metrics.csv 的 nominal 列及算法解析。

|文件/目录|作用|
|---|---|
|[best_bonds.csv](best_bonds.csv)|历史运行原始数据/图表；原算法说明见 archive/legacy 中的文档|
|[best_cells.csv](best_cells.csv)|历史运行原始数据/图表；原算法说明见 archive/legacy 中的文档|
|[figures](figures)|历史出版图：PNG/SVG/PDF，保留原始版本|
|[manifest.json](manifest.json)|运行参数、环境、源码 SHA256、可行性与候选选择记录|
|[metrics.csv](metrics.csv)|所有候选的功耗、温度、频率、IPC/BIPS、时序和布线指标|
|[module_shapes.csv](module_shapes.csv)|各模块连通、孔洞、面积误差、长宽比和紧凑度检查|
|[puzzle__balanced.npz](puzzle__balanced.npz)|压缩 NumPy 数据：坐标、层、模块、连接、区域标签、温度及路由选择|
|[puzzle__balanced_trace.json](puzzle__balanced_trace.json)|该权重方案 cell 优化与布线优化的迭代轨迹|
|[puzzle__thermal.npz](puzzle__thermal.npz)|压缩 NumPy 数据：坐标、层、模块、连接、区域标签、温度及路由选择|
|[puzzle__thermal_trace.json](puzzle__thermal_trace.json)|该权重方案 cell 优化与布线优化的迭代轨迹|
|[puzzle__timing.npz](puzzle__timing.npz)|压缩 NumPy 数据：坐标、层、模块、连接、区域标签、温度及路由选择|
|[puzzle__timing_trace.json](puzzle__timing_trace.json)|该权重方案 cell 优化与布线优化的迭代轨迹|
|[README.md](README.md)|本次运行分类、指标与逐文件说明（自动生成）|
|[shape_trace.json](shape_trace.json)|区域优化迭代和合法检查点选择记录|
