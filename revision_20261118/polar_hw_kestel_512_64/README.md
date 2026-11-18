> For the exact manuscript configuration and portable commands, see
> [the reviewer guide](../REVIEWER_GUIDE.md). Historical notes below
> may describe other development configurations; only the guide selects the paper run.

# Kestel-inspired Polar FPGA architecture (512, 64)

新项目：`D:/program/polar_hw_kestel_512_64`。
原版保留在 `D:/program/polar_hw_baseline_512_64`，两者是独立文件夹。

本项目按 Kestel SOCC 2022 的共享存储、指令控制、四路 f/g 运算和
构成节点剪枝思路实现 FPGA RTL。原文依据和具体差异见
[docs/architecture.md](docs/architecture.md)。

## 已完成并验证

- `rtl/polar_sc_kestel.sv`：N=512、K=64，可选 8-bit / 4-bit LLR，
  min-sum f、饱和 g、同步单端口 alpha/beta RAM、指令 ROM。
- `scripts/compile_schedule.py`：从与原版相同的冻结位生成 exact/fast
  指令。fast 实际包含 52 个 REP、4 个 SPC 节点，共 449 条指令；
  ROM 按 512 条分配。exact 为 896 条，ROM 按 1024 条分配。
- `rtl/polar_sc_2048.sv`：同一核心顺序处理 32 个码块；16384 个输入
  LLR 对应 2048-bit 信息输出。该总线为内部接口。
- 功能测试：8/4-bit 下分别测试原版、exact、fast，每种 128 帧，
  覆盖饱和、零值、并列可靠度、随机含错输入、输入暂停和复位。
  exact 与原版逐位一致；fast 与独立递归 fast-SSC 模型一致。
  两种 2048-bit wrapper 各验证 32 块。
- Vivado 2022.2 已完成 exact8、fast8、fast4、wrapper8 四种配置综合。
- exact8、fast8 各完成 8 帧 Vivado 综合后功能仿真，实际 BRAM/ROM
  原语的输出与各自参考模型一致；未使用 SDF 时延回标。

## 当前综合结果

同一目标器件 `xczu3eg-sbva484-1-i`；内部时钟约束 5 ns。

| 配置 | LUT | FF | RAMB18 | RAMB36 | 译码周期 | WNS (ns) |
|---|---:|---:|---:|---:|---:|---:|
| 原版 baseline8 | 33709 | 5350 | 0 | 0 | 7424 | -1.211 |
| 优化 exact8 | 719 | 195 | 2 | 2 | 7810 | -0.825 |
| 优化 fast8 | 714 | 194 | 4 | 0 | 5608 | -0.825 |
| 优化 fast4 | 494 | 158 | 4 | 0 | 5608 | +1.000 |

周期从最后一个输入 LLR 接收完成计至 done；连续输入加载再加 512
周期。fast8 32 块 wrapper 的完整仿真为 195904 周期；其 OOC 综合
结果为 2758 LUT、2314 FF、4 RAMB18，包含 2048-bit 输出寄存器。

这些是综合结果，尚未布局布线。8-bit 核心未达到 5 ns setup 约束；
4-bit 核心综合 setup slack 为正，但存在综合阶段 hold violation，
仍需布局布线确认。输入/输出外部延时和物理引脚尚未约束；wrapper
的 OOC 时序没有顶层时钟源布局信息。不要将 WNS 直接换算成最终 Fmax。

## 两版如何比较

首先用 `baseline8` 对 `exact8`：冻结位、位宽、逐位 SC 数学语义和
接口相同。共享 RAM 大幅减少 LUT/FF，增加 BRAM；单端口读写调度
使 exact8 周期略增。原版资源较高来自直观的逐层动态存储实现。

再用 `fast8` 观察剪枝效果：REP/SPC 快速节点减少计算，但其有限
位宽语义与逐层饱和 SC 不总是相同。128 帧专用压力向量中，8-bit
有 47 帧、4-bit 有 60 帧输出不同；这不是 FER 测量，也不能据此
判断哪种方案纠错更强。fast4 还改变位宽，应独立标记。

详细数据、来源路径和 SHA256：

- [comparison/comparison.md](comparison/comparison.md)
- [comparison/synthesis_comparison.csv](comparison/synthesis_comparison.csv)
- [comparison/provenance.json](comparison/provenance.json)
- [build/verification.json](build/verification.json)
- [build/netlist_verification.json](build/netlist_verification.json)

本项目为按照公开架构描述独立编写的 FPGA 实现；不等同于作者的
22 nm ASIC/HLS 工程。没有据此复现其 FER、4211 μm²、500 MHz 或
3857 周期。软件 4096-bit Polar 曲线也不能直接归到本 512/64 核心。

## 重现命令

```powershell
Set-Location D:\program\polar_hw_kestel_512_64
python scripts\compile_schedule.py
python tests\verify_architecture.py --frames 128
.\scripts\run_synthesis.ps1
python scripts\collect_results.py
```

综合后功能仿真重现：

```powershell
$env:PROCESSOR_ARCHITECTURE='AMD64'
& 'D:\vivado\Vivado\2022.2\bin\vivado.bat' -mode batch -source scripts\export_netlists.tcl
python tests\verify_netlist.py
```

运行依赖：Python 3、Icarus Verilog（iverilog/vvp）、Vivado 2022.2。
冻结位由本地 BSC(0.15) Bhattacharyya 构造生成；具体 mask 存于
`generated/manifest.json`。更改冻结位时须重建指令表和重新验证。

Vivado 图形工程已创建：`build/gui/polar_kestel.xpr`。它配置为 fast8
核心，batch 综合 checkpoint/report 存在另外的 `build/fast8` 等目录。
GUI 工程本身尚未运行 GUI synthesis run；可查看源代码或重新发起综合。

## 接口

核心 `ready=1` 时脉冲 `start`，下一周期起用 `in_valid` 输入 512 个
有符号 LLR，允许暂停。译码结束后 `done` 脉冲一个周期；
`decoded_info[0]` 是最小索引的信息位。

wrapper 在 `ready=1` 时接受 `start`，之后只有 `input_ready=1` 时
接收 LLR。32 块按顺序处理，block 0 输出在 `[63:0]`。PUF 采样、
helper data XOR、LLR 标定和 hash 不在这个译码器项目内。

复制时的原版说明保存在 `provenance/baseline_README.md`，原版综合
报告和 checkpoint 在 `provenance/baseline_synthesis`。新项目的
`rtl/polar_sc_core.sv` 是未修改的原版核心副本，仅用于溯源。
