# Kestel 架构对应关系与实现边界

来源：Claus Kestel et al., *Towards More Secure PUF Applications: A Low-Area
Polar Decoder Implementation*, SOCC 2022, DOI 10.1109/SOCC56010.2022.9908130。
本地原文位于 `D:/program/参考文献/Towards_More_Secure_PUF_Applications_A_Low-Area_Polar_Decoder_Implementation.pdf`。
核对位置为 II-C（PDF 第 2–3 页）、III-D 及 Fig. 3（第 4–5 页）。

| 原文设计 | 本项目对应实现 | 差异/说明 |
|---|---|---|
| Mem-A 与 Mem-B 分别保存 alpha、beta | `mem_a`、`mem_b`，单端口同步读写 | 在 FPGA 上推断 BRAM，非 ASIC SRAM 宏 |
| alpha 存储约 2Nq bit，重复使用中间存储 | 每层仅分配当前子树 alpha，左右子树复用同一区域 | 四元素对齐后 257 个 word，即 1028 个 LLR 槽；物理 RAM 配置为 512 word |
| beta 独立保存并复用 | 每层保留左右子树 beta；完成父节点后可复用子层 | 当前布局 258 个 4-bit word；物理 RAM 512×4 bit |
| 预编译指令存储 + 控制器 | `compile_schedule.py` 生成指令 ROM 与可读 JSON | 地址由离线编译器安排，硬件通过 word_offset 循环更新；并非作者原指令格式 |
| f/g 处理单元复用与并行 | 四路 min-sum f / 饱和 g，每组先后读取两个 word | 8-bit 配置 word=32 bit；4-bit 配置 word=16 bit。原文 q=4 的 Mem-A word=32 bit |
| Rate-0、Rate-1、REP、SPC 剪枝 | ZERO、HD、REP、SPC，G0、H、COPY 运算 | 当前 fast 冻结树实际用到 REP=52、SPC=4；其他运算的存在不代表均被当前树使用 |
| 重复使用小核心输出较长信息 | `polar_sc_2048` 复用单个核心处理 32 块 | 16384 个 PUF/输入 LLR 位置对应 2048-bit 名义信息维度，码率仍为 1/8 |

## 为什么保留 exact 和 fast 两个配置

原始 RTL 在每个 f/g 后执行有限位宽截断/饱和。直接 REP 求和、SPC
奇偶修正与逐位、逐层饱和 SC 并非对所有输入都逐位等价。零值/并列
可靠度也需要明确的决策规则。

- `exact8`：使用共享 RAM 和指令控制，剪除 Rate-0 子树及不需要的根
  combine；其余仍按原版逐位 SC 语义执行。它用于检验仅改变存储架构
  后的功能等价性，延迟不保证下降。
- `fast8`：使用 REP/SPC/Rate-1 快速节点。REP 使用足够宽、无中途饱和
  的累加器（LLR_BITS+10 bit）；SPC 选择绝对值最小的位置，并列时选择
  最小局部索引；LLR=0 判 0。各节点输出 beta 后，利用 polar 变换的
  自逆性提取局部 u 信息位。
- `fast4`：同一快速架构的 4-bit 整数输入版本。没有实现原文模拟 PUF
  测量值到 LLR 的标定/量化表，不能直接绑定原文 FER 曲线。

验证程序分别将 exact/fast RTL 与独立递归模型比较，并报告两种算法
输出的差异数。该差异数来自混合的饱和、随机及零 LLR 压力向量，
不代表任一真实信道上的 FER 或性能优劣。

## 硬件比较口径

三种 core 配置与原版使用同一器件 `xczu3eg-sbva484-1-i`、Vivado 2022.2、
5 ns 内部时钟约束及顶层综合。记录 LUT、FF、RAMB18、RAMB36、DSP，
避免只比较 LUT 而遗漏新增 RAM。WNS 是综合估计，不是最终频率；
尚无外部引脚时序/引脚约束，也未完成布局布线。

2048-bit wrapper 是内部总线，使用 OOC 综合，避免把 2048 位都当作
外部 FPGA I/O 引脚。其数值与 core 的顶层综合需注明范围差异。

本项目是按照公开架构描述独立实现的 Kestel-inspired FPGA RTL。
原作者的 HLS 工程、完整冻结位、SRAM 编译器和 22 nm 工艺库均未
在本项目中使用，因此不能宣称复现 4211 μm²、500 MHz、3857 周期
或原文的 15% BER / 10^-6 FER 结果。

与原始项目比较的资源下降，仅说明原始直观 RTL 的存储/寻址开销
可以显著缩减，不能作为优于已有优化 Polar 硬件的证据。
