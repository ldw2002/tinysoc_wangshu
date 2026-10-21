#!/usr/bin/env python3
"""Exercise the functional SRAM contract with Icarus, independently of LiteX."""
import argparse
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / 'soc/sim/models/npu_sram_behavioral.sv'
MACROS = [
    ('sram2p8x128', 3, 128, False),
    ('sram2p64x128', 6, 128, False),
    ('sram2p1024x32', 10, 32, False),
    ('sram2p256x64', 8, 64, False),
    ('sram2p32x59', 5, 59, False),
    ('sram1p128x32', 7, 32, True),
    ('sram1p32x32', 5, 32, True),
]


def positive_bench(name, aw, dw, single):
    header = '''`timescale 1ns/1ps
module tb;
localparam AW = %d, DW = %d, DEPTH = 1<<AW;
integer i, background;
reg [DW-1:0] held;
function automatic [DW-1:0] pattern(input integer index);
    integer bit_index;
    for(bit_index=0; bit_index<DW; bit_index=bit_index+1)
        pattern[bit_index] = (index >> (bit_index %% AW)) ^ (bit_index / AW);
endfunction
''' % (aw, dw)
    if single:
        declarations = '''
reg CLK=0, ME=0, WE=0;
reg [AW-1:0] ADR=0;
reg [DW-1:0] D=0;
wire [DW-1:0] Q;
MACRO dut(.Q(Q),.ADR(ADR),.D(D),.CLK(CLK),.WE(WE),.ME(ME),
    .TEST1(1'b0),.RME(1'b0),.RM(4'b0),.LS(1'b0),.DS(1'b0),.SD(1'b0));
task automatic write_word(input [AW-1:0] address, input [DW-1:0] value,
                          input selected, input writing);
    reg [DW-1:0] previous;
    begin
        previous=Q; ADR=address; D=value; ME=selected; WE=writing;
        #2; CLK=1; #1; CLK=0; #1;
        if(writing && Q !== previous) $fatal(1,"FAIL write changed read output");
    end
endtask
task automatic read_word(input [AW-1:0] address, input selected,
                         input [DW-1:0] expected);
    reg [DW-1:0] previous;
    begin
        previous=Q; ADR=address; ME=selected; WE=0;
        #2;
        if(Q !== previous) $fatal(1,"FAIL asynchronous read output");
        CLK=1; #1;
        if(Q !== expected) $fatal(1,"FAIL read addr=%h expected=%h actual=%h",address,expected,Q);
        CLK=0; #1;
    end
endtask
'''.replace('MACRO', name)
        output = 'Q'
        tail = '''
write_word(0,~pattern(0),0,1);
read_word(0,1,pattern(0));
held=Q; read_word('x,0,held);
read_word('x,1,{DW{1'bx}});
write_word(0,{DW{1'bx}},1,1);
read_word(0,1,{DW{1'bx}});
'''
    else:
        declarations = '''
reg CLKA=0, CLKB=0, MEA=0, MEB=0, WEA=0;
reg [AW-1:0] ADRA=0, ADRB=0;
reg [DW-1:0] DA=0;
wire [DW-1:0] QB;
MACRO dut(.QB(QB),.ADRA(ADRA),.ADRB(ADRB),.DA(DA),.WEA(WEA),
    .MEA(MEA),.MEB(MEB),.CLKA(CLKA),.CLKB(CLKB),.TEST1A(1'b0),.TEST1B(1'b0),
    .RMEA(1'b0),.RMEB(1'b0),.RMA(4'b0),.RMB(4'b0),.LS(1'b0),.DS(1'b0),.SD(1'b0));
task automatic write_word(input [AW-1:0] address, input [DW-1:0] value,
                          input selected, input writing);
    reg [DW-1:0] previous;
    begin
        previous=QB; ADRA=address; DA=value; MEA=selected; WEA=writing;
        #2; CLKA=1; #1; CLKA=0; #1;
        if(QB !== previous) $fatal(1,"FAIL write changed independent read output");
    end
endtask
task automatic read_word(input [AW-1:0] address, input selected,
                         input [DW-1:0] expected);
    reg [DW-1:0] previous;
    begin
        previous=QB; ADRB=address; MEB=selected;
        #2;
        if(QB !== previous) $fatal(1,"FAIL asynchronous read output");
        CLKB=1; #1;
        if(QB !== expected) $fatal(1,"FAIL read addr=%h expected=%h actual=%h",address,expected,QB);
        CLKB=0; #1;
    end
endtask
'''.replace('MACRO', name)
        output = 'QB'
        tail = '''
write_word(0,~pattern(0),0,1);
write_word(0,~pattern(0),1,0);
read_word(0,1,pattern(0));
held=QB; read_word('x,0,held);
// Coincident edges to DIFFERENT addresses are legal.
ADRA=DEPTH-1; DA=~pattern(DEPTH-1); MEA=1; WEA=1;
ADRB=0; MEB=1;
#2; CLKA=1; CLKB=1; #1;
if(QB !== pattern(0)) $fatal(1,"FAIL independent simultaneous read/write");
CLKA=0; CLKB=0; #1;
read_word(DEPTH-1,1,~pattern(DEPTH-1));
read_word('x,1,{DW{1'bx}});
write_word(0,{DW{1'bx}},1,1);
read_word(0,1,{DW{1'bx}});
'''
    body = '''
initial begin
    #1;
    if(OUTPUT !== {DW{1'bx}}) $fatal(1,"FAIL initialized output hides unwritten memory");
    read_word(DEPTH-1,1,{DW{1'bx}});
    // Both backgrounds cover every address and drive every bit to 0 and 1.
    for(background=0; background<2; background=background+1) begin
        for(i=0; i<DEPTH; i=i+1)
            write_word(i,background ? ~pattern(i) : pattern(i),1,1);
        for(i=DEPTH-1; i>=0; i=i-1)
            read_word(i,1,background ? ~pattern(i) : pattern(i));
    end
    write_word(0,pattern(0),1,1);
TAIL
    $display("PASS_ALL MACRO");
    $finish;
end
endmodule
'''.replace('OUTPUT', output).replace('TAIL', tail).replace('MACRO', name)
    return header + declarations + body


def negative_bench(action, single=False):
    if single:
        return '''`timescale 1ns/1ps
module tb;
reg CLK=0, WE=0, ME=0, TEST1=0, LS=0, DS=0, SD=0;
reg [4:0] ADR=0;
wire [31:0] Q;
sram1p32x32 dut(.Q(Q),.CLK(CLK),.WE(WE),.ME(ME),.ADR(ADR),.D(32'b0),
 .TEST1(TEST1),.LS(LS),.DS(DS),.SD(SD),.RME(1'b0),.RM(4'b0));
initial begin
 #2; ACTION
 #2; $display("FAIL expected rejection did not occur"); $finish;
end
endmodule
'''.replace('ACTION', action)
    return '''`timescale 1ns/1ps
module tb;
reg CLKA=0, CLKB=0, MEA=0, MEB=0, WEA=0, LS=0, DS=0, SD=0, TEST1A=0, TEST1B=0;
reg [2:0] ADRA=0, ADRB=0;
wire [127:0] QB;
sram2p8x128 dut(.QB(QB),.ADRA(ADRA),.ADRB(ADRB),.DA(128'b0),.WEA(WEA),
 .MEA(MEA),.MEB(MEB),.CLKA(CLKA),.CLKB(CLKB),.TEST1A(TEST1A),.TEST1B(TEST1B),
 .RMEA(1'b0),.RMEB(1'b0),.RMA(4'b0),.RMB(4'b0),.LS(LS),.DS(DS),.SD(SD));
initial begin
 #2; ACTION
 #2; $display("FAIL expected rejection did not occur"); $finish;
end
endmodule
'''.replace('ACTION', action)


def binding_bench():
    instances = []
    for index, (_, aw, dw, single) in enumerate(MACROS):
        # The tag wrapper uses only the lower half of the physical 32-word macro.
        if dw == 59:
            aw = 4
        if single:
            ports = ".clk(1'b0),.ce_n(1'b1),.we(1'b0),.addr(%d'b0),.wdata(%d'b0),.rdata(),.RME(1'b0),.RM(4'b0)" % (aw, dw)
        else:
            ports = ".wclk(1'b0),.wce_n(1'b1),.we(1'b0),.waddr(%d'b0),.wdata(%d'b0),.rclk(1'b0),.rce_n(1'b1),.raddr(%d'b0),.rdata(),.RMEA(1'b0),.RMA(4'b0),.RMBE(1'b0),.RMB(4'b0)" % (aw, dw, aw)
        instances.append("NPU_sram_asic_%s #(.DW(%d),.AW(%d),.WW(1)) u%d(%s,.ls(1'b0),.ds(1'b0),.sd(1'b0));" % ('sp' if single else '2p', dw, aw, index, ports))
    return '`timescale 1ns/1ps\nmodule tb;\n' + '\n'.join(instances) + '\nendmodule\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iverilog', default=shutil.which('iverilog'))
    parser.add_argument('--vvp', default=shutil.which('vvp'))
    parser.add_argument('--ivl-base')
    parser.add_argument('--vpi-dir')
    parser.add_argument('--build-dir', type=Path, default=ROOT / 'soc/build/sram_models')
    args = parser.parse_args()
    if not args.iverilog or not args.vvp:
        parser.error('Icarus Verilog and vvp are required; use --iverilog and --vvp to select tools')
    work = args.build_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    compiler = [args.iverilog] + (['-B', args.ivl_base] if args.ivl_base else []) + ['-g2012', '-Wall', '-s', 'tb']
    simulator = [args.vvp] + (['-M', args.vpi_dir] if args.vpi_dir else [])

    def execute(command, log):
        result = subprocess.run(command, capture_output=True, text=True, timeout=15)
        output = result.stdout + result.stderr
        (work / log).write_text(output, encoding='utf-8')
        return result.returncode, output

    def check(name, text, rejection=None):
        source = work / (name + '.sv')
        binary = work / (name + '.vvp')
        source.write_text(text, encoding='utf-8')
        code, output = execute(compiler + ['-o', str(binary), str(source), str(MODEL)], name + '_compile.log')
        if code or 'error:' in output.lower():
            raise RuntimeError(name + ' compile failed:\n' + output)
        code, output = execute(simulator + [str(binary)], name + '_run.log')
        if rejection:
            # Icarus 10.3 can return 0 on $fatal; validate the diagnostic itself.
            passed = rejection in output and 'FAIL expected rejection' not in output
        else:
            passed = code == 0 and 'PASS_ALL' in output and not any(marker in output for marker in ['FAIL', 'FATAL', 'ERROR'])
        if not passed:
            raise RuntimeError(name + ' simulation failed:\n' + output)
        print('PASS', name)

    for item in MACROS:
        check(item[0], positive_bench(*item))
    rejected = [
        ('collision_write_first', "MEA=1; WEA=1; MEB=1; CLKA=1; #0; CLKB=1;", 'COLLISION', False),
        ('collision_read_first', "MEA=1; WEA=1; MEB=1; CLKB=1; #0; CLKA=1;", 'COLLISION', False),
        ('unknown_write_address', "MEA=1; WEA=1; ADRA='x; CLKA=1;", 'UNKNOWN_WRITE_ADDRESS', False),
        ('unknown_write_control', "MEA=1; WEA=1'bx; CLKA=1;", 'UNKNOWN_CONTROL', False),
        ('unknown_read_control', "MEB=1'bx; CLKB=1;", 'UNKNOWN_CONTROL', False),
        ('light_sleep', 'LS=1; CLKA=1;', 'UNSUPPORTED_MODE', False),
        ('deep_sleep', 'DS=1; CLKB=1;', 'UNSUPPORTED_MODE', False),
        ('shutdown', 'SD=1; CLKA=1;', 'UNSUPPORTED_MODE', False),
        ('test_port_a', 'TEST1A=1; CLKA=1;', 'UNSUPPORTED_MODE', False),
        ('test_port_b', 'TEST1B=1; CLKB=1;', 'UNSUPPORTED_MODE', False),
        ('sp_unknown_write_address', "ME=1; WE=1; ADR='x; CLK=1;", 'UNKNOWN_WRITE_ADDRESS', True),
        ('sp_unknown_control', "ME=1; WE=1'bx; CLK=1;", 'UNKNOWN_CONTROL', True),
        ('sp_test_mode', 'TEST1=1; CLK=1;', 'UNSUPPORTED_MODE', True),
    ]
    for name, action, marker, single in rejected:
        check(name, negative_bench(action, single), 'TINYSOC_SRAM_' + marker)

    source = work / 'macro_bindings.sv'
    source.write_text(binding_bench(), encoding='utf-8')
    wrappers = ROOT / 'generated/vta-ip/server-memory-20261020/rtl/bist_rtl'
    code, output = execute(compiler + ['-tnull', '-DASIC', '-DSMIC40LL', '-DSYNOPSYS_MEM', str(source), str(MODEL),
                                     str(wrappers / 'NPU_sram_asic_2p.v'), str(wrappers / 'NPU_sram_asic_sp.v')], 'macro_bindings_compile.log')
    if code or 'error:' in output.lower():
        raise RuntimeError('server macro bindings failed:\n' + output)
    print('PASS server ASIC wrapper bindings (7 configurations; elaboration only)')
    print('PASS_ALL: 7 macro contracts, 13 rejection cases, 7 wrapper bindings')
    print('Logs:', work)


if __name__ == '__main__':
    main()
