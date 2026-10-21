# Tcl syntax/control-flow fixture only. This is NOT a Synopsys implementation.
set synopsys_version {MOCK: Tcl control-flow validation only}
proc define_design_lib {name option path} {
    if {$name ne "WORK" || $option ne "-path" || ![file isdirectory $path]} { error "bad WORK setup" }
}
proc get_app_var {name} { return [list .] }
proc set_app_var {name value} { return 1 }
proc analyze {format_option format define_option defines sources} {
    if {$format_option ne "-format" || $format ne "sverilog" || $define_option ne "-define"} { error "bad analyze arguments" }
    if {[lsearch -exact $defines SYNTHESIS] < 0} { error "missing SYNTHESIS" }
    foreach path $sources { if {![file isfile $path]} { error "missing source: $path" } }
    return 1
}
proc elaborate {top} { return $top }
proc current_design {top} { return $top }
proc get_designs {quiet top} {
    if {$quiet ne "-quiet"} { error "bad get_designs" }
    return [list $top]
}
proc sizeof_collection {collection} { return [llength $collection] }
proc mock_failed {step} {
    return [expr {[info exists ::env(DC_MOCK_FAILURE)] && $::env(DC_MOCK_FAILURE) eq $step}]
}
proc link {} { return [expr {![mock_failed link]}] }
proc check_design {} { return [expr {![mock_failed check_design]}] }
proc uniquify {} { return 1 }
proc compile {} { return [expr {![mock_failed compile]}] }
proc compile_ultra {} { return [compile] }
proc get_cells {args} {
    if {[mock_failed unmapped]} { return [list gtech_cell] }
    return [list]
}
proc create_clock {args} { return 1 }
proc get_ports {args} { return clock }
foreach command {report_resources report_design check_timing report_area report_timing report_qor} {
    proc $command {args} { return {MOCK report: not a synthesis result} }
}
proc redirect {option path script} {
    if {$option ne "-file"} { error "bad redirect" }
    set result [uplevel 1 $script]
    set channel [open $path w]
    puts $channel "MOCK report: $result"
    close $channel
}
proc write {args} {
    set index [lsearch -exact $args -output]
    if {$index < 0} { error "write needs -output" }
    set channel [open [lindex $args [expr {$index + 1}]] w]
    puts $channel {MOCK artifact: not usable as a netlist}
    close $channel
    return 1
}
proc write_sdc {path} { return [write -output $path] }
source [lindex $argv 0]
