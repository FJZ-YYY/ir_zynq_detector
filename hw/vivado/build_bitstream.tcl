set origin_dir [file normalize [file dirname [info script]]]
set ::env(IRDET_BUILD_BITSTREAM) 1
source [file join $origin_dir create_project.tcl]
