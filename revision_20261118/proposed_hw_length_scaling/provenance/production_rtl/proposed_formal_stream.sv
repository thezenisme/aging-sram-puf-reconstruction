// No internal 2048-bit result cache. The receiver accepts 32x64-bit words.
module proposed_formal_stream (
    input wire clk,rst,start,
    input wire [7:0] maxiter,
    input wire in_valid,
    input wire signed [7:0] in_llr,
    output wire ready,input_ready,busy,done,fail,
    output wire [7:0] iter_count,
    input wire out_ready,
    output wire out_valid,out_last,
    output wire [4:0] out_index,
    output wire [63:0] out_word
);
    formal_nms_core core(.*);
endmodule
