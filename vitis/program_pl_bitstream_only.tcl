set origin_dir [file normalize [file dirname [info script]]]
set repo_root  [file normalize [file join $origin_dir ..]]
set bit_file   [file normalize [file join $repo_root build vivado ir_zynq_detector.runs impl_1 system_wrapper.bit]]

proc irdet_select_target {filters} {
    foreach f $filters {
        if {![catch {targets -set -filter $f}]} {
            puts "INFO: Selected target filter: $f"
            return 0
        }
    }
    return -1
}

proc irdet_print_file_info {label path} {
    puts "INFO: $label: $path"
    puts "INFO: $label size: [file size $path] bytes"
}

if {![file exists $bit_file]} {
    error "Bitstream not found: $bit_file. Run hw/vivado/build_bitstream.tcl first."
}

puts "INFO: IR detector PL bitstream-only programmer"
puts "INFO: This script programs the PL over JTAG and does not reset the PS or download an ELF."
irdet_print_file_info "Bitstream" $bit_file

if {[catch {connect} connect_msg]} {
    puts "ERROR: XSCT connect failed: $connect_msg"
    error $connect_msg
}

after 1000

puts "INFO: Available XSCT targets:"
targets

if {[irdet_select_target [list {name =~ "APU*"} {name =~ "*PS7*"}]] != 0} {
    error "Could not select the APU or PS7 target. Please send back the printed target list."
}

puts "INFO: Programming PL bitstream without disturbing the running Linux userspace..."
if {[catch {fpga -file $bit_file} fpga_msg]} {
    puts "ERROR: PL bitstream programming failed."
    puts "ERROR: Typical checks: board power/JTAG cable, boot/config jumpers, stale hw_server, and exact FPGA part match."
    puts "ERROR: This project currently builds for xc7z020clg400-1 unless ZYNQ_PART is overridden."
    error $fpga_msg
}

puts "INFO: Bitstream programmed successfully: $bit_file"
puts "INFO: You can now rerun the Linux-side PL selftest without rebooting Linux."
