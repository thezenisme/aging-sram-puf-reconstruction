read_verilog -sv ../rtl/LDPC_scaling_folded_core.v
read_xdc timing.xdc
synth_design -top LDPC_scaling_n4096 -part xczu3eg-sbva484-1-i -flatten_hierarchy none
report_utilization -hierarchical -file scaling_n4096_utilization_synth.rpt
report_timing_summary -file scaling_n4096_timing_synth.rpt
