# 发布包

|文件|用途|
|---|---|
|cell3d_source.zip|当前源码、配置、测试、文档、最新/参考结果和 HotSpot C 源码；需安装 Python/NumPy|
|cell3d_windows_x64_offline.zip|同上，加独立 Python3.12、NumPy、DLL/许可证；Windows10/11 x64 离线运行|
|SHA256.json|两个包的字节数和 SHA256|

解压顶层 cell-3D，双击 run_layout.cmd；结果在 results/日期/运行名。完整历史代码/结果在 Git 仓库，便携包只携带当前与发布参考结果。HotSpot 可选，需要编译/WSL；普通代理运行无需它。

从 cell-3D 打包，stage 必须是仓库内新的目录，输入完整 Python3.12 运行时需已有 NumPy：

```powershell
python tools/build_layout_bundle.py --python-runtime "C:\路径\完整Python3.12" --stage "..\build\新的打包目录"
```
