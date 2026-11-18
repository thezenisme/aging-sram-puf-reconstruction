module proposed_formal_stream #(
    parameter integer N=4096, K=2048, Z=128, BASE_EDGES=123,
    parameter integer MAX_ROW_DEGREE=8,
    parameter MATRIX_DIR="generated/n4096",
    parameter integer WORD_AW=$clog2(K/64)
)(
    input wire clk,rst,start,
    input wire [7:0] maxiter,
    input wire in_valid,
    input wire signed [7:0] in_llr,
    output wire ready,input_ready,busy,done,fail,
    output wire [7:0] iter_count,
    input wire out_ready,
    output wire out_valid,out_last,
    output wire [WORD_AW-1:0] out_index,
    output wire [63:0] out_word
);
    formal_nms_core #(.N(N),.K(K),.Z(Z),.BASE_EDGES(BASE_EDGES),
        .MAX_ROW_DEGREE(MAX_ROW_DEGREE),.MATRIX_DIR(MATRIX_DIR)) core(.*);
endmodule
