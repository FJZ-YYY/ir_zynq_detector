set origin_dir [file normalize [file dirname [info script]]]
set repo_root  [file normalize [file join $origin_dir .. ..]]

source [file join $origin_dir create_project.tcl]

launch_runs synth_1 -jobs 4
wait_on_run synth_1

open_run synth_1

set report_dir [file normalize [file join $repo_root build vivado reports]]
file mkdir $report_dir

report_utilization -file [file join $report_dir synth_utilization.rpt]
report_timing_summary -max_paths 10 -file [file join $report_dir synth_timing_summary.rpt]

puts "INFO: Synthesis utilization report: [file join $report_dir synth_utilization.rpt]"
puts "INFO: Synthesis timing report: [file join $report_dir synth_timing_summary.rpt]"
