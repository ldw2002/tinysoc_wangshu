// TinySoC-owned functional simulation substitutes for the server SRAM macros.
// Port names and normal-mode semantics follow NPU_sram_asic_{2p,sp}.
// Select this file OR the foundry models, never both. No PVT/timing modelling.
`timescale 1ns/1ps
`default_nettype none

module tinysoc_sram_1w1r_model #(
    parameter integer AW = 3,
    parameter integer DW = 128
) (
    output reg [DW-1:0] QB,
    input wire [AW-1:0] ADRA, ADRB,
    input wire [DW-1:0] DA,
    input wire WEA, MEA, MEB, CLKA, CLKB,
    input wire TEST1A, TEST1B, LS, DS, SD
);
    reg [DW-1:0] mem [0:(1<<AW)-1];
    // The array and QB deliberately have no initialization or reset.
    // Blocking bookkeeping detects coincident read/write edges in either order.
    realtime last_write_time, last_read_time;
    reg [AW-1:0] last_write_addr, last_read_addr;
    reg write_seen = 0;
    reg read_seen = 0;

    always @(posedge CLKA) begin
        if ({LS, DS, SD, TEST1A} !== 4'b0000)
            $fatal(1, "TINYSOC_SRAM_UNSUPPORTED_MODE: %m requires LS/DS/SD/TEST1A=0");
        if (MEA === 1'b1) begin
            if (WEA === 1'b1) begin
                if ((^ADRA) === 1'bx)
                    $fatal(1, "TINYSOC_SRAM_UNKNOWN_WRITE_ADDRESS: %m");
                if (read_seen && last_read_time == $realtime && last_read_addr == ADRA)
                    $fatal(1, "TINYSOC_SRAM_COLLISION: %m coincident same-address read/write");
                last_write_time = $realtime;
                last_write_addr = ADRA;
                write_seen = 1;
                mem[ADRA] <= DA;
            end else if (WEA !== 1'b0)
                $fatal(1, "TINYSOC_SRAM_UNKNOWN_CONTROL: %m WEA");
        end else if (MEA !== 1'b0)
            $fatal(1, "TINYSOC_SRAM_UNKNOWN_CONTROL: %m MEA");
    end

    always @(posedge CLKB) begin
        if ({LS, DS, SD, TEST1B} !== 4'b0000)
            $fatal(1, "TINYSOC_SRAM_UNSUPPORTED_MODE: %m requires LS/DS/SD/TEST1B=0");
        if (MEB === 1'b1) begin
            if ((^ADRB) === 1'bx)
                QB <= {DW{1'bx}};
            else begin
                if (write_seen && last_write_time == $realtime && last_write_addr == ADRB)
                    $fatal(1, "TINYSOC_SRAM_COLLISION: %m coincident same-address read/write");
                last_read_time = $realtime;
                last_read_addr = ADRB;
                read_seen = 1;
                QB <= mem[ADRB];
            end
        end else if (MEB !== 1'b0)
            $fatal(1, "TINYSOC_SRAM_UNKNOWN_CONTROL: %m MEB");
        // MEB=0 holds QB; writes to other addresses may proceed independently.
    end
endmodule

module tinysoc_sram_sp_model #(
    parameter integer AW = 7,
    parameter integer DW = 32
) (
    output reg [DW-1:0] Q,
    input wire [AW-1:0] ADR,
    input wire [DW-1:0] D,
    input wire CLK, WE, ME, TEST1, LS, DS, SD
);
    reg [DW-1:0] mem [0:(1<<AW)-1];
    always @(posedge CLK) begin
        if ({LS, DS, SD, TEST1} !== 4'b0000)
            $fatal(1, "TINYSOC_SRAM_UNSUPPORTED_MODE: %m requires LS/DS/SD/TEST1=0");
        if (ME === 1'b1) begin
            if (WE === 1'b1) begin
                if ((^ADR) === 1'bx)
                    $fatal(1, "TINYSOC_SRAM_UNKNOWN_WRITE_ADDRESS: %m");
                mem[ADR] <= D;
            end else if (WE === 1'b0)
                Q <= ((^ADR) === 1'bx) ? {DW{1'bx}} : mem[ADR];
            else
                $fatal(1, "TINYSOC_SRAM_UNKNOWN_CONTROL: %m WE");
        end else if (ME !== 1'b0)
            $fatal(1, "TINYSOC_SRAM_UNKNOWN_CONTROL: %m ME");
        // Disabled cycles and writes hold Q. No array or output initialization.
    end
endmodule

// RME/RM and their A/B forms are accepted for interface compatibility only.
// Their timing/trim effects are intentionally absent from these models.
module sram2p8x128 (
    output wire [127:0] QB,
    input wire [2:0] ADRA, ADRB,
    input wire [127:0] DA,
    input wire WEA, MEA, MEB, CLKA, CLKB, TEST1A, TEST1B,
    input wire RMEA, RMEB, LS, DS, SD,
    input wire [3:0] RMA, RMB
);
    tinysoc_sram_1w1r_model #(.AW(3), .DW(128)) impl (.*);
endmodule

module sram2p64x128 (
    output wire [127:0] QB,
    input wire [5:0] ADRA, ADRB,
    input wire [127:0] DA,
    input wire WEA, MEA, MEB, CLKA, CLKB, TEST1A, TEST1B,
    input wire RMEA, RMEB, LS, DS, SD,
    input wire [3:0] RMA, RMB
);
    tinysoc_sram_1w1r_model #(.AW(6), .DW(128)) impl (.*);
endmodule

module sram2p1024x32 (
    output wire [31:0] QB,
    input wire [9:0] ADRA, ADRB,
    input wire [31:0] DA,
    input wire WEA, MEA, MEB, CLKA, CLKB, TEST1A, TEST1B,
    input wire RMEA, RMEB, LS, DS, SD,
    input wire [3:0] RMA, RMB
);
    tinysoc_sram_1w1r_model #(.AW(10), .DW(32)) impl (.*);
endmodule

module sram2p256x64 (
    output wire [63:0] QB,
    input wire [7:0] ADRA, ADRB,
    input wire [63:0] DA,
    input wire WEA, MEA, MEB, CLKA, CLKB, TEST1A, TEST1B,
    input wire RMEA, RMEB, LS, DS, SD,
    input wire [3:0] RMA, RMB
);
    tinysoc_sram_1w1r_model #(.AW(8), .DW(64)) impl (.*);
endmodule

module sram2p32x59 (
    output wire [58:0] QB,
    input wire [4:0] ADRA, ADRB,
    input wire [58:0] DA,
    input wire WEA, MEA, MEB, CLKA, CLKB, TEST1A, TEST1B,
    input wire RMEA, RMEB, LS, DS, SD,
    input wire [3:0] RMA, RMB
);
    tinysoc_sram_1w1r_model #(.AW(5), .DW(59)) impl (.*);
endmodule

module sram1p128x32 (
    output wire [31:0] Q,
    input wire [6:0] ADR,
    input wire [31:0] D,
    input wire CLK, WE, ME, TEST1, RME, LS, DS, SD,
    input wire [3:0] RM
);
    tinysoc_sram_sp_model #(.AW(7), .DW(32)) impl (.*);
endmodule

module sram1p32x32 (
    output wire [31:0] Q,
    input wire [4:0] ADR,
    input wire [31:0] D,
    input wire CLK, WE, ME, TEST1, RME, LS, DS, SD,
    input wire [3:0] RM
);
    tinysoc_sram_sp_model #(.AW(5), .DW(32)) impl (.*);
endmodule

`default_nettype wire
