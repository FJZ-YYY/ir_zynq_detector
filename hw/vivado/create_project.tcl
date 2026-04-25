set origin_dir [file normalize [file dirname [info script]]]
set repo_root  [file normalize [file join $origin_dir .. ..]]

set project_name "ir_zynq_detector"
set bd_name "system"
set build_root [file normalize [file join $repo_root build vivado]]
set xsa_dir [file normalize [file join $build_root export]]
set rtl_files [list \
    [file normalize [file join $repo_root zynq_pl rtl ir_preprocess_stub.sv]] \
    [file normalize [file join $repo_root zynq_pl rtl mobilenet_dw3x3_accel.sv]] \
    [file normalize [file join $repo_root zynq_pl rtl mobilenet_dw3x3_channel_core.sv]] \
    [file normalize [file join $repo_root zynq_pl rtl mobilenet_dw3x3_channel_mmio.sv]] \
    [file normalize [file join $repo_root zynq_pl rtl mobilenet_dw3x3_channel_axi.v]] \
    [file normalize [file join $repo_root zynq_pl rtl mobilenet_dw3x3_channel_axi.sv]] \
    [file normalize [file join $repo_root zynq_pl rtl mobilenet_dw3x3_channel_full_mmio.sv]] \
    [file normalize [file join $repo_root zynq_pl rtl mobilenet_dw3x3_channel_full_axi.v]] \
    [file normalize [file join $repo_root zynq_pl rtl mobilenet_dw3x3_channel_full_axi.sv]] \
]

if {[info exists ::env(ZYNQ_PART)]} {
    set part_name $::env(ZYNQ_PART)
} else {
    set part_name "xc7z020clg400-1"
}

if {[info exists ::env(IRDET_BUILD_BITSTREAM)]} {
    set build_bitstream $::env(IRDET_BUILD_BITSTREAM)
} else {
    set build_bitstream 0
}

file mkdir $build_root
file mkdir $xsa_dir

create_project -force $project_name $build_root -part $part_name
set_property target_language Verilog [current_project]

foreach rtl_file $rtl_files {
    if {![file exists $rtl_file]} {
        error "RTL source not found: $rtl_file"
    }
}
add_files -norecurse $rtl_files

source [file join $origin_dir bd create_zynq_ps_uart_bd.tcl]
irdet_bd::create_design $bd_name

set bd_file [get_files ${bd_name}.bd]
generate_target all $bd_file
make_wrapper -files $bd_file -top -force

set wrapper_file [file normalize [file join $build_root ${project_name}.gen sources_1 bd $bd_name hdl ${bd_name}_wrapper.v]]
add_files -norecurse $wrapper_file
set_property top ${bd_name}_wrapper [current_fileset]

update_compile_order -fileset sources_1

if {$build_bitstream} {
    launch_runs impl_1 -to_step write_bitstream -jobs 4
    wait_on_run impl_1
    write_hw_platform -fixed -include_bit -force -file [file join $xsa_dir ${project_name}.xsa]
} else {
    write_hw_platform -fixed -force -file [file join $xsa_dir ${project_name}.xsa]
}

puts "INFO: Project created at $build_root"
puts "INFO: Using part $part_name"
puts "INFO: XSA exported to [file join $xsa_dir ${project_name}.xsa]"
puts "INFO: build_bitstream=$build_bitstream"
