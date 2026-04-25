set origin_dir [file normalize [file dirname [info script]]]
set repo_root  [file normalize [file join $origin_dir ..]]
set workspace  [file normalize [file join $repo_root build vitis_dw3x3_selftest]]
set xsa_file   [file normalize [file join $repo_root build vivado export ir_zynq_detector.xsa]]

set platform_name "irdet_platform"
set app_name      "irdet_dw3x3_selftest"
set domain_name   "standalone_domain"
set app_src_dir   [file normalize [file join $workspace $app_name src]]

set source_files [list \
    [file normalize [file join $repo_root zynq_ps src dw3x3_selftest_baremetal.c]] \
    [file normalize [file join $repo_root zynq_ps src ir_pl_dw3x3.c]] \
    [file normalize [file join $repo_root zynq_ps src ir_pl_dw3x3_full.c]] \
    [file normalize [file join $repo_root zynq_ps src ir_pl_dw3x3_selftest.c]] \
    [file normalize [file join $repo_root zynq_ps include ir_pl_dw3x3.h]] \
    [file normalize [file join $repo_root zynq_ps include ir_pl_dw3x3_full.h]] \
    [file normalize [file join $repo_root zynq_ps include ir_pl_dw3x3_full_channel_data.h]] \
    [file normalize [file join $repo_root zynq_ps include ir_pl_dw3x3_realcase_batch_data.h]] \
    [file normalize [file join $repo_root zynq_ps include ir_pl_dw3x3_realcase_channel_data.h]] \
    [file normalize [file join $repo_root zynq_ps include ir_pl_dw3x3_realcase_data.h]] \
    [file normalize [file join $repo_root zynq_ps include ir_pl_dw3x3_selftest.h]] \
]

if {![file exists $xsa_file]} {
    error "XSA file not found: $xsa_file. Run hw/vivado/create_project.tcl or build_bitstream.tcl first."
}

if {[file exists $workspace]} {
    puts "INFO: Removing existing generated Vitis workspace: $workspace"
    file delete -force $workspace
}
file mkdir $workspace

setws $workspace

platform create -name $platform_name -hw $xsa_file -proc ps7_cortexa9_0 -os standalone
platform generate

app create -name $app_name -platform $platform_name -domain $domain_name -template {Empty Application}

foreach f $source_files {
    if {![file exists $f]} {
        error "Source file not found: $f"
    }
}

set default_main [file join $app_src_dir main.c]
if {[file exists $default_main]} {
    file delete -force $default_main
}

foreach f $source_files {
    file copy -force $f $app_src_dir
}

app build -name $app_name

puts "INFO: Vitis workspace created at $workspace"
puts "INFO: Application built: [file join $workspace $app_name]"
