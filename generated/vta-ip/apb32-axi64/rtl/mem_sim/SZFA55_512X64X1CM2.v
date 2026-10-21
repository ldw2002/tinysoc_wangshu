// Behavioural simulation model; no timing, no vendor primitives.
// (512 words x 64 bits), synchronous read on A and write on B.
module SZFA55_512X64X1CM2 (A, B, DO, DI, CKA, CKB, CSAN, CSBN, DVSE, DVS, WEB);

output [63:0] DO;
input  [63:0] DI;
input  [8:0]  A;
input  [8:0]  B;
input  [2:0]  DVS;
input         WEB;
input         CKA;
input         CKB;
input         CSAN;
input         CSBN;
input         DVSE;

reg [63:0] DO;
reg [63:0] mem [0:511];

integer i;
initial begin
    for (i = 0; i < 512; i = i + 1)
        mem[i] = 64'd0;
    DO = 64'd0;
end

always @(posedge CKA) begin
    if (!CSAN)
        DO <= mem[A];
end

always @(posedge CKB) begin
    if (!CSBN && !WEB)
        mem[B] <= DI;
end

endmodule
