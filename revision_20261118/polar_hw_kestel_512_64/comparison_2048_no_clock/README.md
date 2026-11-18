# 两种 Polar 架构：2048-bit 输出的资源实测

日期：2026-10-14。Vivado 2022.2，器件 `xczu3eg-sbva484-1-i`。

## 统一的实现与统计范围

- 两版均综合 `polar_sc_2048` 完整模块，使用 out-of-context 模式。
- 一个 `N=512, K=64, R=1/8` 译码核心顺序复用 32 次，LLR 位宽均为 8 bit。
- 总计接收 16,384 个 LLR，输出并保存 2,048 个译码信息位。
- 资源包含译码核心、32 块调度控制和完整的 2048-bit 并行结果寄存器。
- 不包含 PUF 采集、helper-data 处理、哈希、外部输入缓存、AXI 或物理引脚接口。
- 未加载任何 XDC 时序约束；两份日志均确认 `clocks=0`。不要求 200 MHz，也不声明任何频率时序收敛。
- 以下是综合后的资源估计，尚未进行布局布线，不能据此报告实际占用 CLB 数或最高工作频率。

## 结果

| 架构 | LUT 总数 | 其中 LUTRAM | FF | RAMB18 | RAMB36 | DSP | 完成 2048-bit 输出的周期数 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 原版 scalar SC | 34,329 | 1,840 | 7,495 | 0 | 0 | 0 | 254,016 |
| Kestel-inspired 快速节点优化版（FAST=1） | 2,755 | 0 | 2,314 | 4 | 0 | 0 | 195,904 |

4 个 RAMB18 对应 2 个 36-Kb BRAM tile 的容量。LUTRAM 已包含在 LUT 总数中，不能重复相加。
周期数包括连续有效输入的加载、32 次译码和控制，不是一个 512-bit 码块的译码延迟。
输入停顿会增加总周期数。

这里是复用一个小码核心累积 2048-bit 输出，**不是**重新设计了 `(4096,2048)` 长码。
因此不能把已有 4096-bit 软件 Polar FER 曲线直接标为此硬件的性能。
2048 表示译码信息位数量，不包含最终哈希提取步骤。

原版的高资源消耗来自当前功能参考 RTL 的存储/动态寻址实现，不能代表优化 Polar 硬件的必然开销。
优化版借鉴 Kestel 的存储复用、并行运算和快速节点思想，不是原作者 ASIC 网表复现。
FAST=1 的有限位宽和快速节点处理可能与原版饱和 SC 在部分输入上产生不同判决；
资源表不是两者 FER 完全等价的证明。相关功能边界见 `../docs/architecture.md`。

## 证据与验证

- 原版资源报告：[utilization_synth.rpt](build/original/utilization_synth.rpt)
- 优化版资源报告：[utilization_synth.rpt](build/optimized/utilization_synth.rpt)
- 两版 `build/<variant>/` 中另有层级资源报告、无约束检查报告、综合 DCP。
- 两份日志分别为 `original.log` 与 `optimized.log`；均正常结束，综合 0 errors / 0 critical warnings。
- 本次重新运行原版 `tests/check_core.py`：8 个核心测试及 32 块 wrapper 测试均通过，wrapper 为 254,016 周期。
- 优化版沿用已通过的 32 块 wrapper 参考模型验证，195,904 周期，见 `../build/verification.json`。
- 本次没有修改两版 RTL。当前源文件 SHA256 与前次 `../comparison/provenance.json` 一致：

| 文件 | SHA256 |
|---|---|
| original/rtl/polar_sc_core.sv | `90cb0e86b0a2eed9ea729aea0c03a29750cfdc33d49b6762fd25011fe0644669` |
| original/rtl/polar_sc_2048.sv | `ebb41c7517846bbe842f7872577a492441810a55a4662b0d3cd0a7f81ed5b7b0` |
| optimized/rtl/polar_sc_kestel.sv | `999c5b8211992a6d34b742a06d696572ea35707bbb9b718c4953d7c3cb8fe061` |
| optimized/rtl/polar_sc_2048.sv | `5739da3fb6b24cde8ee472d67bab012ea602542d2f4718989d8020579fe66039` |

原有 5-ns 综合报告未覆盖；原版 README 中“wrapper 尚未综合”仅描述前次状态，本目录报告补齐了此次完整模块的无时钟约束综合。

## 重跑

```powershell
$env:PROCESSOR_ARCHITECTURE = 'AMD64'
Set-Location D:\program\polar_hw_kestel_512_64\comparison_2048_no_clock
& D:\vivado\Vivado\2022.2\bin\vivado.bat -mode batch -log original.log -journal original.jou -source synth.tcl -tclargs original
& D:\vivado\Vivado\2022.2\bin\vivado.bat -mode batch -log optimized.log -journal optimized.jou -source synth.tcl -tclargs optimized
```

该脚本会重新生成本目录的结果，不修改原版项目或 Proposed LDPC。
