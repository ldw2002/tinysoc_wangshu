# Example only: choose constraints for the actual target and library time units.
# This file is NOT selected automatically by the DC backend.
create_clock -name sys_clk -period 5.0 [get_ports clock]
# Complete input/output delays, uncertainty, reset exceptions and load/drive
# assumptions for the server target before interpreting mapped timing reports.
