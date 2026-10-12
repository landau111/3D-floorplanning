# 优化前后布局、帕累托图与参数

图件由已保存的实际估算输出生成，没有伪造新布局。前后对应 `A_split__baseline` → `A_split__thermal__seed17`，相同模块分层、fence、cell ID和网表。每幅完整布局都画出全部29,400个标准单元；SRAM硬宏保持固定。

[六页矢量PDF图册](output/pdf/cell3d_layouts_and_pareto.pdf) · [输入参数全集](PARAMETERS.md) · [机器可读参数](inputs_complete.json)

## 优化前的模块分层

![初始模块布局](figures/01_initial_modules.png)

## 优化前后 cell 级对比

左侧优化前，右侧优化后；上排为上层，下排为下层。模块区域不变，cell在区域内独立移动。

![优化前后](figures/04_before_after.png)

[优化前完整双层图](figures/02_before_cells.png) · [优化后完整双层图](figures/03_after_cells.png) · [逐cell坐标及位移](figures/cell_before_after.csv)

## 局部放大

![逐cell局部放大](figures/05_cell_zoom.png)

矩形尺寸为8×4µm，每个模块2100个单元。连续优化之后完成了row/site合法化，已核验无重叠。密集色块表示许多相邻cell，并不是又改回了模块矩形。

图中可见部分cell沿模块边缘聚集。此形状是当前粗网格目标与合法化流程下的输出，不能据此认为“沿边缘成带摆放”是实际芯片的普适最优规则；应在真实网表、库、细化密度网格与详细布线中进一步验证。

## 帕累托图

![帕累托前沿](figures/06_pareto.png)

17个方案中10个离散可行；仅这10个参与非支配关系计算。功耗—BIPS二维前沿10个，峰温—BIPS二维前沿9个，功耗↓/峰温↓/BIPS↑联合三目标前沿10个。编号16是以最大吞吐率选出的优胜方案，不代表所有偏好下唯一最优。

两个二维前沿分别计算，不能把三维前沿直接连成同一二维最优边界。虚线只连接已观察到的前沿点，不能视为可实现的插值方案。图中接近重合的点保留各自编号与数据。

功耗和温度对应各方案自己的可运行频率；降低频率同时降低功耗与吞吐率，所以本组离散可行解在功耗维度均形成取舍，不能据此宣称任意单一布局全面占优。所有方案的2GHz签核时序均未通过本模型的代理检查；当前“可行”指模型内降频后的运行点。

[所有散点与前沿成员CSV](figures/pareto_points.csv) · [图件来源与核验记录](figures/figure_manifest.json)

完整输入包含42个config顶层字段（含说明元数据）、51项固定代码设置、16模块功耗/几何、18组连接数量、3套布局、2个gem5基线。详见 [PARAMETERS.md](PARAMETERS.md)；不会把28nm标签当作加载了真实工艺库。
