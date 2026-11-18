set root [file normalize [file join [file dirname [info script]] ..]]
cd $root
create_project proposed_formal_5bit_message_bram [file join $root build gui] -part xczu3eg-sbva484-1-i -force
add_files [list [file join $root rtl formal_nms_core.sv] [file join $root rtl proposed_formal_stream.sv]]
add_files [glob [file join $root generated *.hex]]
set_property file_type {Memory Initialization Files} [get_files *.hex]
set_property top proposed_formal_stream [current_fileset]
add_files -fileset utils_1 [file join $root scripts gui_synth_pre.tcl]
set_property STEPS.SYNTH_DESIGN.TCL.PRE [file join $root scripts gui_synth_pre.tcl] [get_runs synth_1]
update_compile_order -fileset sources_1
close_project
puts "PROJECT_CREATED_NOT_RUN"
exit
