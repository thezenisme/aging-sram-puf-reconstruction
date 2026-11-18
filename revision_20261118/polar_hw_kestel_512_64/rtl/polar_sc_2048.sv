module polar_sc_2048 #(parameter integer FAST=1, parameter integer LLR_BITS=8) (
    input  wire                clk,
    input  wire                rst,
    input  wire                start,
    output wire                ready,
    output wire                input_ready,
    input  wire                in_valid,
    input  wire signed [LLR_BITS-1:0] in_llr,
    output reg                 done,
    output reg  [2047:0]      decoded_info
);
    localparam integer BLOCKS = 32;
    localparam integer N = 512;
    localparam [1:0] IDLE = 0, START_BLOCK = 1, FEED = 2, WAIT_DONE = 3;
    reg [1:0] state;
    reg [4:0] block_index;
    reg [8:0] input_index;
    wire core_ready, core_done;
    wire [63:0] core_info;

    wire core_start = state == START_BLOCK;
    assign ready = state == IDLE;
    assign input_ready = state == FEED;

    polar_sc_kestel #(.LLR_BITS(LLR_BITS),.FAST(FAST),.ROM_DEPTH(FAST ? 512 : 1024)) core (
        .clk(clk), .rst(rst), .start(core_start), .ready(core_ready),
        .in_valid(in_valid && input_ready), .in_llr(in_llr),
        .done(core_done), .decoded_info(core_info)
    );

    always @(posedge clk) begin
        if (rst) begin
            state <= IDLE;
            block_index <= 0;
            input_index <= 0;
            decoded_info <= 0;
            done <= 0;
        end else begin
            done <= 0;
            case (state)
                IDLE: if (start) begin
                    decoded_info <= 0;
                    block_index <= 0;
                    state <= START_BLOCK;
                end
                START_BLOCK: if (core_ready) begin
                    input_index <= 0;
                    state <= FEED;
                end
                FEED: if (in_valid) begin
                    if (input_index == N-1) begin
                        state <= WAIT_DONE;
                    end else begin
                        input_index <= input_index + 1'b1;
                    end
                end
                WAIT_DONE: if (core_done) begin
                    decoded_info[block_index*64 +: 64] <= core_info;
                    if (block_index == BLOCKS-1) begin
                        state <= IDLE;
                        done <= 1;
                    end else begin
                        block_index <= block_index + 1'b1;
                        state <= START_BLOCK;
                    end
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule
