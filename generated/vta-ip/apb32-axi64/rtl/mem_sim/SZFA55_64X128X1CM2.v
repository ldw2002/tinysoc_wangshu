// Behavioural simulation model; no timing, no vendor primitives.
// (64 words x 128 bits), synchronous read on A and write on B.
module SZFA55_64X128X1CM2 (A, B, DO, DI, CKA, CKB, CSAN, CSBN, DVSE, DVS, WEB);

output [127:0] DO;
input  [127:0] DI;
input  [5:0]   A;
input  [5:0]   B;
input  [2:0]   DVS;
input          WEB;
input          CKA;
input          CKB;
input          CSAN;
input          CSBN;
input          DVSE;

reg [127:0] DO;
reg [127:0] mem [0:63];

integer i;
initial begin
    for (i = 0; i < 64; i = i + 1)
        mem[i] = 128'd0;
    DO = 128'd0;
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
