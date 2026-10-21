// Behavioural simulation model; no timing, no vendor primitives.
// file SZFA55_8X128X1CM2 (8 words x 128 bits).  Port A performs a synchronous
// read, port B a synchronous write.  Chip selects and WEB are active low.
module SZFA55_8X128X1CM2 (A, B, DO, DI, CKA, CKB, CSAN, CSBN, DVSE, DVS, WEB);

output [127:0] DO;
input  [127:0] DI;
input  [2:0]   A;
input  [2:0]   B;
input  [2:0]   DVS;
input          WEB;
input          CKA;
input          CKB;
input          CSAN;
input          CSBN;
input          DVSE;

reg [127:0] DO;
reg [127:0] mem [0:7];

integer i;
initial begin
    for (i = 0; i < 8; i = i + 1)
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
