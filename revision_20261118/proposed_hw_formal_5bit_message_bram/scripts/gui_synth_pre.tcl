# Project-mode synthesis runs in its own working directory. Copy only these
# immutable generated initialization inputs into that run's generated folder.
set root [file normalize [file join [file dirname [info script]] ..]]
file mkdir [file join [pwd] generated]
foreach name {base_edges.hex base_rows.hex output_positions.hex} {
    file copy -force [file join $root generated $name] [file join [pwd] generated $name]
}
