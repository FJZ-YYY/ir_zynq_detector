set origin_dir [file normalize [file dirname [info script]]]
set repo_root  [file normalize [file join $origin_dir ..]]

set elf_file     [file normalize [file join $repo_root build vitis_dw3x3_selftest irdet_dw3x3_selftest Debug irdet_dw3x3_selftest.elf]]
set ps7_init_tcl [file normalize [file join $repo_root build vitis_dw3x3_selftest irdet_dw3x3_selftest _ide psinit ps7_init.tcl]]
set bit_file     [file normalize [file join $repo_root build vivado ir_zynq_detector.runs impl_1 system_wrapper.bit]]

proc irdet_select_target {filters} {
    foreach f $filters {
        if {![catch {targets -set -filter $f}]} {
            puts "INFO: Selected target filter: $f"
            return 0
        }
    }
    return -1
}

proc irdet_try_stop_core {} {
    if {[catch {stop} stop_msg]} {
        puts "INFO: stop skipped: $stop_msg"
    } else {
        puts "INFO: CPU halted."
    }
}

proc irdet_print_file_info {label path} {
    puts "INFO: $label: $path"
    puts "INFO: $label size: [file size $path] bytes"
}

proc irdet_try_system_reset {} {
    if {[catch {rst -system} rst_msg]} {
        puts "INFO: system reset skipped: $rst_msg"
    } else {
        puts "INFO: System reset asserted."
    }
}

proc irdet_program_fpga {bit_file} {
    puts "INFO: Programming PL bitstream..."
    if {[catch {fpga -file $bit_file} fpga_msg]} {
        puts "ERROR: PL bitstream programming failed before PS app download."
        puts "ERROR: The bare-metal selftest ELF has NOT run yet; this is not UART output."
        puts "ERROR: Typical checks: board power/JTAG cable, boot/config jumpers, stale hw_server, and exact FPGA part match."
        puts "ERROR: This project currently builds for xc7z020clg400-1 unless ZYNQ_PART is overridden."
        puts "ERROR: Run vitis/probe_jtag_targets.tcl and send back the complete target list if this repeats."
        error $fpga_msg
    }
    puts "INFO: Bitstream programmed: $bit_file"
}

if {![file exists $elf_file]} {
    error "ELF file not found: $elf_file. Build the dw3x3 selftest app first."
}
if {![file exists $bit_file]} {
    error "Bitstream not found: $bit_file. Run hw/vivado/build_bitstream.tcl first."
}

irdet_print_file_info "ELF" $elf_file
irdet_print_file_info "Bitstream" $bit_file

connect
after 1000

puts "INFO: Available XSCT targets:"
targets

if {[irdet_select_target [list {name =~ "APU*"} {name =~ "*PS7*"}]] != 0} {
    error "Could not select the APU or PS7 target. Please send back the printed target list."
}

irdet_try_system_reset
after 2000

if {[irdet_select_target [list {name =~ "*A9*#0"} {name =~ "Cortex-A9 MPCore #0"}]] != 0} {
    error "Could not select Cortex-A9 core 0. Please send back the printed target list."
}

if {[catch {rst -processor} rst_msg]} {
    puts "INFO: processor reset skipped: $rst_msg"
} else {
    puts "INFO: Processor reset asserted."
}

after 1000
irdet_try_stop_core

if {[file exists $ps7_init_tcl]} {
    source $ps7_init_tcl
    ps7_init
    puts "INFO: PS7 init applied before PL configuration."
}

after 1000
irdet_try_stop_core

if {[irdet_select_target [list {name =~ "APU*"} {name =~ "*PS7*"}]] != 0} {
    error "Could not reselect the APU or PS7 target before FPGA programming."
}

irdet_program_fpga $bit_file

if {[irdet_select_target [list {name =~ "*A9*#0"} {name =~ "Cortex-A9 MPCore #0"}]] != 0} {
    error "Could not reselect Cortex-A9 core 0 after FPGA programming."
}

if {[info commands ps7_post_config] ne ""} {
    ps7_post_config
    puts "INFO: PS7 post-config applied after PL configuration."
}

after 500
irdet_try_stop_core

dow -force $elf_file
con

puts "INFO: ELF downloaded and CPU resumed."
