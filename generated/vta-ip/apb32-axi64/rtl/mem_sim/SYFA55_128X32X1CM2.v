// Behavioural simulation model; no timing, no vendor primitives.
// Single-port register file SYFA55_128X32X1CM2 (128 words x 32 bits).
// CSB selects the chip; WEB low selects a write, WEB high a synchronous read.
// Both are sampled on the CK rising edge.
module SYFA55_128X32X1CM2 (A, DO, DI, DVSE, DVS, WEB, CK, CSB);

output [31:0] DO;
input  [31:0] DI;
input  [6:0]  A;
input  [3:0]  DVS;
input         WEB;
input         CK;
input         CSB;
input         DVSE;

reg [31:0] DO;
reg [31:0] mem [0:127];

integer i;
initial begin
    for (i = 0; i < 128; i = i + 1)
        mem[i] = 32'd0;
    DO = 32'd0;
end

always @(posedge CK) begin
    if (!CSB) begin
        if (!WEB)
            mem[A] <= DI;
        else
            DO <= mem[A];
    end
end

endmodule
