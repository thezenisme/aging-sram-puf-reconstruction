# Paper Table VII: standard top-level synthesis, NOT out-of-context.
set root [file normalize [file join [file dirname [info script]] ..]]
cd $root
set output [file join $root build paper_top_level]
file mkdir $output
read_verilog -sv [file join $root rtl turbo_lte_4096_2048_compare_top.sv]
foreach name {bcjr_turbo_decoder lte_interleaver lte_turbo_decoder ram_replacements} {
    read_vhdl -vhdl2008 [file join $root rtl ${name}.vhd]
}
synth_design -top turbo_lte_4096_2048_compare_top -part xczu3eg-sfvc784-1-i
report_utilization -file [file join $output utilization_synth.rpt]
report_utilization -hierarchical -file [file join $output utilization_hierarchical.rpt]
check_timing -file [file join $output check_timing.rpt]
puts "PAPER_TURBO_SYNTH_COMPLETE mode=top_level"
exit
