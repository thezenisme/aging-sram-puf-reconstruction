set root [file normalize [file join [file dirname [info script]] ..]]
cd $root
set output [file join $root build message_bram]
file mkdir $output
set_param general.maxThreads 2
read_verilog -sv [file join $root rtl formal_nms_core.sv]
read_verilog -sv [file join $root rtl proposed_formal_stream.sv]
synth_design -top proposed_formal_stream -part xczu3eg-sbva484-1-i -mode out_of_context
report_utilization -file [file join $output utilization_synth.rpt]
report_utilization -hierarchical -file [file join $output utilization_hierarchy.rpt]
check_timing -file [file join $output check_timing.rpt]
write_checkpoint -force [file join $output synthesized.dcp]
write_verilog -force -mode funcsim [file join $output netlist.v]
puts "MESSAGE_BRAM_SYNTH_COMPLETE clocks=[llength [get_clocks -quiet]]"
exit
