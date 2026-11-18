> For the exact manuscript configuration and portable commands, see
> [the reviewer guide](../REVIEWER_GUIDE.md). Historical notes below
> may describe other development configurations; only the guide selects the paper run.

# 正式 5-bit QC-LDPC 实现的码长扩展实验

本目录独立于 `D:/FPGA/UPELDPC/UPELDPC.xpr` 和原正式实现。
只参数化译码与流式输出，不修改原工程、原矩阵、软件 FER 结果或论文源文件。

## 实验口径

采用论文现有的三个配置，不重新搜索矩阵：

| N | 名义输出 K | Z | 基矩阵尺寸 | H 边数 |
|---:|---:|---:|---:|---:|
| 1024 | 512 | 64 | 8 × 16 | 3456 |
| 2048 | 1024 | 64 | 16 × 32 | 7488 |
| 4096 | 2048 | 128 | 16 × 32 | 15744 |

1024、2048 来自当前软件实验目录 `D:/program/one_bit_mask_llr_experiment`；
4096 来自正式实现冻结的软件源文件，并核对当前 Vivado 使用的三个 HEX 文件。
所有输入文件的副本与 SHA-256 记录在 `provenance/manifest.json`。

**这是论文实际配置的资源扩展比较，不是固定基矩阵、仅改变 Z 的实验。**
基矩阵尺寸、行列度和单位码长边数随配置变化，不能把资源变化全部归因于 Z。
冻结的 4096 校验矩阵秩为 2046，名义输出仍为已有编码器定义的 2048 位；本实验不改变其秩或信息位约定。

所有配置保留：

- 5-bit 饱和算术、归一化最小和及原 flooding 更新顺序。
- 输入端 8-bit 容器，内部饱和到 [-15,15]。
- 输入/变量存储使用 LUTRAM，边消息使用带预取的同步 BRAM。
- 每轮 syndrome 提前检查及整帧提前终止。
- 64-bit 握手输出，无内部完整信息位输出缓存。
- 同一器件 `xczu3eg-sfvc784-1-i`、Vivado 2022.2、OOC 综合，无时钟约束，与现有资源对比的统计范围一致。

本实现不含 PUF 采集、helper XOR、mask/映射/量化生成或哈希模块。
资源统计是综合结果，不代表布局布线资源、Fmax、板上吞吐或实测功耗。

## 文件与运行

在本目录执行以下命令（需要 Python、GCC、Icarus Verilog 和 Vivado 2022.2）：

一键复现：`python -u scripts/run_all.py`。也可以分步骤运行：

```powershell
python scripts/prepare.py
python -u scripts/verify.py
python -u scripts/run_synthesis.py
python -u scripts/verify_netlist.py
python scripts/collect.py
```

`prepare.py` 校验 H/G 正交性、GF(2) 秩、QC 结构、信息位输出坐标和连续消息地址；
保持 4096 配置的矩阵 HEX 内容与现有正式工程一致。

`verify.py` 对三个码长分别用独立 C 和 Python 五比特模型建立参考，
检查 RTL 完整硬判决、输出信息位、迭代次数、失败标志和周期分解。
覆盖非零码字、软擦除、饱和极值、零 LLR、迭代上限、200 轮失败、
加载中途复位、输入间隙和输出反压。
4096 配置额外与冻结的生产 RTL 逐周期比较接口、控制状态、存储访问和写入。
功能测试通过不等于在老化信道下恢复成功；这些向量不是 FER 或平均延迟实验。

`run_synthesis.py` 只在所有配置验证通过且 RTL 哈希匹配时启动综合。
每个码长使用独立 Vivado 批处理进程。
启动器在进程环境中补充 Xilinx loader 所需的 Windows 架构变量，不修改系统环境。
同时规范化进程环境中的 Windows 路径分隔符，避免 Vivado 内部 Tcl 读取临时文件失败。

`verify_netlist.py` 对每个码长进行综合网表功能仿真，使用全正、非零合法码字、
饱和极值三组参考向量，验证输出、迭代次数、失败标志及 RTL 周期一致性。
使用 UNISIM 功能模型，无 SDF，不构成布局布线时序验证。
DONE 在同一时钟边沿后 1 ns 观察，以覆盖 UNISIM FDRE 固有的 100 ps 输出延迟；
延迟统计仍是时钟边沿间隔，没有增加一个译码周期。

仅重跑单个验证配置可用 `python scripts/verify.py --lengths 4096`；
已有其他配置记录只有在 RTL 哈希一致时才能复用。

## 结果

- `reports/matrix_audit.json`：各矩阵审计。
- `reports/verification.json`：功能验证及 4096 生产版本逐周期比较。
- `reports/synthesis.json`：工具、器件、综合条件与原始报告哈希。
- `reports/netlist_verification.json`：三个码长的综合网表功能检查。
- `reports/scaling_resources.csv`：可直接导入表格软件的资源数据。
- `reports/scaling_resources.md`：便于阅读的资源表。
- `reports/scaling_resources.json`：完整资源、单位比特指标及与原 4096 结果的差异。
- `build/n*/synthesis/`：每个码长的原始 Vivado 日志、综合报告、DCP 和功能网表。

LUT as Memory 单独列示为 LUTRAM；BRAM 另列，不能把 LUT 降低全部解释为存储总量降低。
所有 `/N` 指标按输入码长归一化，输出位归一化应使用 `/K`，两者不可混用。
实际资源趋势应以新报告为准，不预设 Logic/N 必然单调下降。

`provenance/early_qcpeg_run` 仅保存源目录校正前的历史结果，不用于最终论文表格。
最终结果统一位于 `reports/`，1024/2048 的权威输入来源为上述当前软件实验目录。

## 参数范围

当前导出与地址优化支持本实验的 6/7 或 7/8 行度、二次幂 QC 提升因子、
名义半码率和完整 64-bit 输出字。没有宣称支持任意 LDPC 矩阵。
若以后增加 256/512 配置，必须提供并验证对应矩阵，不能仅修改 N 后复用现有 HEX。
