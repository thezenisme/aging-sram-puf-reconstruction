# One configuration per fresh batch process. Matches production OOC/no-clock scope.
set root [file normalize [file join [file dirname [info script]] ..]]
if {$argc != 1} {error "Usage: vivado -mode batch -source synth.tcl -tclargs 1024|2048|4096"}
set n [lindex $argv 0]
if {$n ni {1024 2048 4096}} {error "Unsupported code length $n"}
set output [file join $root build n$n synthesis]
file mkdir $output
cd $root
set_param general.maxThreads 2
read_verilog -sv [file join $root rtl formal_nms_core.sv]
read_verilog -sv [file join $root rtl proposed_formal_stream.sv]
read_verilog -sv [file join $root generated n$n top.sv]
synth_design -top proposed_n$n -part xczu3eg-sfvc784-1-i -mode out_of_context
report_utilization -file [file join $output utilization_synth.rpt]
report_utilization -hierarchical -file [file join $output utilization_hierarchy.rpt]
check_timing -file [file join $output check_timing.rpt]
write_checkpoint -force [file join $output synthesized.dcp]
write_verilog -force -mode funcsim [file join $output netlist.v]
puts "SCALING_SYNTH_COMPLETE N=$n CLOCKS=[llength [get_clocks -quiet]] PART=[get_property PART [current_design]]"
exit
