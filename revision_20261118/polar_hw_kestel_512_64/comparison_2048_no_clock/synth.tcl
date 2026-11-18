# Same-scope area comparison: one N=512,K=64,Q=8 decoder reused for 32 blocks.
# No clock or I/O timing constraints are loaded. No timing-closure claim is made.
set output_root [file normalize [file dirname [info script]]]
set optimized_project [file dirname $output_root]
set baseline_project $optimized_project
if {$argc != 1} {error "Usage: synth.tcl original|optimized"}
set variant [lindex $argv 0]
if {$variant ni {original optimized}} {error "Unknown variant $variant"}
set source_project $baseline_project
set core_file polar_sc_core.sv
if {$variant eq "optimized"} {
    set source_project $optimized_project
    set core_file polar_sc_kestel.sv
}
cd $source_project
set output_dir [file join $output_root build $variant]
file mkdir $output_dir
set_param general.maxThreads 2
read_verilog -sv [file join $source_project rtl $core_file]
read_verilog -sv [file join $source_project rtl polar_sc_2048.sv]
synth_design -top polar_sc_2048 -part xczu3eg-sbva484-1-i -mode out_of_context
report_utilization -file [file join $output_dir utilization_synth.rpt]
report_utilization -hierarchical -file [file join $output_dir utilization_hierarchy.rpt]
check_timing -file [file join $output_dir check_timing.rpt]
write_checkpoint -force [file join $output_dir synthesized.dcp]
puts "AREA_COMPARISON_COMPLETE $variant clocks=[llength [get_clocks -quiet]]"
exit
