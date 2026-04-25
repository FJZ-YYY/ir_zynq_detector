set origin_dir [file normalize [file dirname [info script]]]
set repo_root  [file normalize [file join $origin_dir ..]]
set workspace  [file normalize [file join $repo_root build vitis]]
set xsa_file   [file normalize [file join $repo_root build vivado export ir_zynq_detector.xsa]]

set platform_name "irdet_platform"
set app_name      "irdet_uart_rx"
set domain_name   "standalone_domain"
set app_src_dir   [file normalize [file join $workspace $app_name src]]

set source_files [list \
    [file normalize [file join $repo_root zynq_ps src ir_detector_stub.c]] \
    [file normalize [file join $repo_root zynq_ps src ir_image_preprocess.c]] \
    [file normalize [file join $repo_root zynq_ps src ir_model_runner.c]] \
    [file normalize [file join $repo_root zynq_ps src ir_pl_dw3x3.c]] \
    [file normalize [file join $repo_root zynq_ps src ir_pl_dw3x3_full.c]] \
    [file normalize [file join $repo_root zynq_ps src ir_pl_dw3x3_selftest.c]] \
    [file normalize [file join $repo_root zynq_ps src ir_ssd_postprocess.c]] \
    [file normalize [file join $repo_root zynq_ps src uart_image_receiver_baremetal.c]] \
    [file normalize [file join $repo_root zynq_ps src uart_image_proto.c]] \
    [file normalize [file join $repo_root zynq_ps include ir_detector_stub.h]] \
    [file normalize [file join $repo_root zynq_ps include ir_image_preprocess.h]] \
    [file normalize [file join $repo_root zynq_ps include ir_model_runner.h]] \
    [file normalize [file join $repo_root zynq_ps include ir_pl_dw3x3.h]] \
    [file normalize [file join $repo_root zynq_ps include ir_pl_dw3x3_full.h]] \
    [file normalize [file join $repo_root zynq_ps include ir_pl_dw3x3_full_channel_data.h]] \
    [file normalize [file join $repo_root zynq_ps include ir_pl_dw3x3_realcase_batch_data.h]] \
    [file normalize [file join $repo_root zynq_ps include ir_pl_dw3x3_realcase_channel_data.h]] \
    [file normalize [file join $repo_root zynq_ps include ir_pl_dw3x3_realcase_data.h]] \
    [file normalize [file join $repo_root zynq_ps include ir_pl_dw3x3_selftest.h]] \
    [file normalize [file join $repo_root zynq_ps include ir_ssd_raw_sample_data.h]] \
    [file normalize [file join $repo_root zynq_ps include ir_ssd_postprocess.h]] \
    [file normalize [file join $repo_root zynq_ps include uart_image_proto.h]] \
]

if {![file exists $xsa_file]} {
    error "XSA file not found: $xsa_file. Run Vivado create_project.tcl first."
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

set debug_makefile [file join $workspace $app_name Debug makefile]
if {![file exists $debug_makefile]} {
    error "Debug makefile not found after app build: $debug_makefile"
}

set fp [open $debug_makefile r]
set makefile_text [read $fp]
close $fp

set lib_token {$(LIBS)}
set lib_token_with_math {$(LIBS) -lm}

if {[string first "-lm" $makefile_text] < 0} {
    if {[string first $lib_token $makefile_text] < 0} {
        error "Could not patch math library into makefile: $debug_makefile"
    }
    set makefile_text [string map [list $lib_token $lib_token_with_math] $makefile_text]
    set fp [open $debug_makefile w]
    puts -nonewline $fp $makefile_text
    close $fp
}

set old_pwd [pwd]
cd [file join $workspace $app_name Debug]
if {[catch {exec make all} build_msg]} {
    cd $old_pwd
    error "Final make step failed for $app_name: $build_msg"
}
cd $old_pwd

puts "INFO: Vitis workspace created at $workspace"
puts "INFO: Application built: [file join $workspace $app_name]"
