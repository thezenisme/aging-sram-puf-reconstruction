> For the exact manuscript configuration and portable commands, see
> [the reviewer guide](../REVIEWER_GUIDE.md). Historical notes below
> may describe other development configurations; only the guide selects the paper run.

# Proposed 5-bit：仅边消息 BRAM、预取、流式输出

本项目派生自 `proposed_hw_formal_5bit_stream_4bit`。该中间工程已按用户确认的清理范围移出工作区。
验证用的两份参考RTL和必要报告保存在本项目 `provenance/baseline_distributed`，不再依赖中间工程目录。
仅将 15744×5-bit 边消息存储迁到同步读 BRAM；4096×5-bit 输入和变量存储仍使用异步 LUTRAM。
正式 H/G、信息位坐标、5-bit NMS 算术、逐次饱和顺序、flooding 调度和早停条件保持不变。

## 无等待状态的预取

- 在清零消息存储的最后一个周期读取地址 0，供首轮 CN1 使用。
- CN1 消费当前边时读取下一边；每行 CN2 最后一次写回时读取下一行首边。
- VRESET 最后一个周期读取地址 0；VADD 逐边消费并读取下一条消息，包括跨行访问。
- 校验失败且将开始下一轮时，同时预取地址 0。
- 同一拍 BRAM 读写地址不同；不依赖同地址读写冲突模式。
- 没有新增状态或改变变量写回顺序，不减少迭代上限。

## 验证

`tests/verify.py` 生成与原版哈希相同的 12 组向量，由独立 Python 和 C 五位参考计算期望值。
同拍运行原版 RTL 和新版 RTL，核对所有变量/消息写回、消费的消息、状态和接口信号。
测试涵盖非零码字、软擦除、9轮收敛、200轮失败、极值/饱和、复位中止、连续帧和输入空拍。
额外检查每次 BRAM 消费的预取地址、数据和读写无冲突，另跑3组接收端暂停。
`tests/verify_netlist.py` 运行3组 Vivado 综合后功能仿真，覆盖非零码字和两轮失败。

资源及通过状态以 `reports/resources.json`、`reports/rtl_verification.json` 和
`reports/netlist_verification.json` 为准。没有 FER 扫描、布局布线、达成频率或功耗结论。
周期相同不意味着物理时钟频率已验证。

## 2026-10-14 综合结果

Vivado 2022.2，器件 xczu3eg-sbva484-1-i，OOC综合，不加载时钟约束。

| 实现 | LUT总数 | 其中LUTRAM | FF | RAMB36 | RAMB18 | DSP |
|---|---:|---:|---:|---:|---:|---:|
| 原分布式RAM流式版 | 4028 | 2800 | 160 | 1 | 0 | 0 |
| 本版：仅边消息BRAM、预取 | 1440 | 832 | 160 | 3 | 1 | 0 |
| 本地Kestel-inspired Polar优化版 | 2755 | 0 | 2314 | 0 | 4 | 0 |

本版比原版减少2588 LUT（64.25%），比当前Polar实现少1315 LUT（47.73%）。
代价是比原版增加2个RAMB36及1个RAMB18。相对Polar，块RAM容量由等效2个RAMB36增至3.5个。
LUTRAM已包含在LUT总数内，不能重复相加。

层级报告：input_store为349 LUT（320 LUTRAM），var_store为816 LUT（512 LUTRAM），
message_store为97逻辑LUT、2个RAMB36及1个RAMB18；核心其余178 LUT、160 FF及1个输出坐标ROM RAMB36。
输入与变量存储的RTL没有改变；综合优化导致其外围逻辑统计可能略有变化。

原版和本版均无2048-bit完整输出缓存；Polar含该缓存且采用8-bit LLR，不能把FF差异直接作为译码器优势。
Polar为一个(512,64)核心顺序复用32次，16384个输入，2048个信息位；本版为4096个输入、2048个信息位。
本表不证明两者相同FER，不对应4096-bit软件Polar曲线，也不等于原作者ASIC面积复现。

12组无输出暂停RTL回归的每组处理周期与原版完全一致，例如：

| 用例 | 迭代次数 | 原版周期 | 本版周期 |
|---|---:|---:|---:|
| 无噪声非零码字 | 1 | 89221 | 89221 |
| 软擦除及噪声 | 9 | 527821 | 527821 |
| 迭代上限失败 | 200 | 10290973 | 10290973 |

每轮不计校验扫描为51328周期，完整校验扫描15744周期，均未改变。
上述总周期包含相同输入空拍、无输出暂停。RTL测试完成7746080次预取地址/数据检查。
另3组输出暂停测试通过，逐周期对照也包含暂停和加载/译码中复位。
3组Vivado综合网表功能仿真也全部通过（非零码字、全正输入、两轮极值失败），包含输出暂停。
其89283/89283/124955周期包含62个接收暂停周期，不能与无暂停的RTL周期混用。
综合为0错误、0严重警告；普通警告为未满足并行综合条件及未设置时钟/时钟源约束。

## 接口和范围

与原版接口相同：8-bit输入接口内部饱和到[-15,15]，64-bit输出流，共32个字。
输出暂停时保持valid/data/index/last，末字接收后才done。没有内部2048-bit完整输出缓存。
本项目只含已形成LLR到纠错输出，不含PUF采集、helper XOR、mask/映射/量化生成和哈希。
与Polar比较须说明5/8-bit位宽、输出缓存和码率差异，不将信息位数称为已验证安全密钥长度。

## 重现

在本目录执行：

```powershell
python tests/verify.py
$env:PROCESSOR_ARCHITECTURE='AMD64'
& D:/vivado/Vivado/2022.2/bin/vivado.bat -mode batch -log build/message_synth.log -journal build/message_synth.jou -source scripts/synth.tcl
python tests/verify_netlist.py
python scripts/collect_results.py
```

GUI工程由 `scripts/create_project.tcl` 创建；批量综合结果在 `build/message_bram`。
`reports/provenance.json` 记录本版哈希，核对原始软件、最早接口副本及项目内验证快照。

## 2026-10-14 中间工程清理

按用户确认的范围保留 `D:/program/proposed_hw_2048_io` 和本项目。
以下四个完整中间工程移入Windows回收站，可从回收站恢复：

- `D:/program/proposed_hw_formal_2048_io`
- `D:/program/proposed_hw_formal_5bit_2048_io`
- `D:/program/proposed_hw_formal_5bit_bram_stream`
- `D:/program/proposed_hw_formal_5bit_stream_4bit`

LDPC05、Polar工程、论文和软件实验数据不在清理范围内。
`reports/cleanup_20261014` 保存清理清单、此前哈希和中间版本资源报告；
这里只保留验证证据，不复制中间工程的Vivado项目、网表和仿真构建目录。
参考快照里的旧绝对路径仅用于历史追溯，现行验证脚本使用项目内路径。
