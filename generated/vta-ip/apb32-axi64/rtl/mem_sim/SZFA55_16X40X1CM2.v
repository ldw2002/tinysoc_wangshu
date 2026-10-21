// Behavioural simulation model; no timing, no vendor primitives.
// (16 words x 40 bits), synchronous read on A and write on B.
module SZFA55_16X40X1CM2 (A, B, DO, DI, CKA, CKB, CSAN, CSBN, DVSE, DVS, WEB);

output [39:0] DO;
input  [39:0] DI;
input  [3:0]  A;
input  [3:0]  B;
input  [2:0]  DVS;
input         WEB;
input         CKA;
input         CKB;
input         CSAN;
input         CSBN;
input         DVSE;

reg [39:0] DO;
reg [39:0] mem [0:15];

integer i;
initial begin
    for (i = 0; i < 16; i = i + 1)
        mem[i] = 40'd0;
    DO = 40'd0;
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
