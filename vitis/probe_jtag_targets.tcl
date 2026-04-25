set origin_dir [file normalize [file dirname [info script]]]
set repo_root  [file normalize [file join $origin_dir ..]]
set bit_file   [file normalize [file join $repo_root build vivado ir_zynq_detector.runs impl_1 system_wrapper.bit]]

puts "INFO: IR detector JTAG target probe"
puts "INFO: This script only connects and prints targets. It does not program PL or run CPU code."

if {[file exists $bit_file]} {
    puts "INFO: Current bitstream: $bit_file"
    puts "INFO: Current bitstream size: [file size $bit_file] bytes"
} else {
    puts "WARNING: Current bitstream not found: $bit_file"
}

if {[catch {connect} connect_msg]} {
    puts "ERROR: XSCT connect failed: $connect_msg"
    error $connect_msg
}

after 1000

puts "INFO: Available XSCT targets:"
targets

puts "INFO: Target probe complete."
puts "INFO: If programming fails with DONE PIN not HIGH, confirm the actual FPGA part marking matches xc7z020clg400-1 or rebuild with ZYNQ_PART."
