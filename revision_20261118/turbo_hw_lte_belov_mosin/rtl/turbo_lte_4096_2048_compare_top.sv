`timescale 1ns/1ps

// Common comparison endpoint: one 4096-LLR input block to 2048 decoded bits.
module turbo_lte_4096_2048_compare_top #(
    parameter RATE_MAP_FILE = "rtl/generated/turbo_rm_v0_k2048_e4096.mem"
) (
    input  logic                 CLK,
    input  logic                 RST,
    input  logic                 START,
    output logic                 READY,
    output logic                 INPUT_READY,
    input  logic                 IN_VALID,
    input  logic signed [7:0]    IN_LLR,
    output logic                 BUSY,
    output logic                 DONE,
    output logic [2047:0]        DECODED_INFO
);
    localparam integer INPUT_BITS = 4096;
    localparam integer K = 2048;
    localparam integer DECODER_SLOTS = K + 4;
    localparam integer LAST_SLOT = DECODER_SLOTS - 1;

    localparam logic [2:0] ST_IDLE    = 3'd0;
    localparam logic [2:0] ST_INIT    = 3'd1;
    localparam logic [2:0] ST_CLEAR   = 3'd2;
    localparam logic [2:0] ST_RECEIVE = 3'd3;
    localparam logic [2:0] ST_PRIME   = 3'd4;
    localparam logic [2:0] ST_FEED    = 3'd5;
    localparam logic [2:0] ST_DECODE  = 3'd6;

    logic [2:0] state;
    logic [11:0] clear_addr;
    logic [12:0] input_count;
    logic input_complete;
    logic pending_valid;
    logic signed [4:0] pending_llr;
    logic [13:0] rate_map [0:INPUT_BITS-1];
    logic [13:0] rate_map_q;
    logic [11:0] feed_index;
    logic [11:0] output_count;
    logic [11:0] stream_rd_addr;
    logic [11:0] stream_wr_addr;
    logic signed [4:0] stream_wr_data;
    logic stream0_wr_en, stream1_wr_en, stream2_wr_en;

    logic signed [4:0] stream0_q, stream1_q, stream2_q;

    logic core_init, core_fdvi, core_dvi, core_rfd;
    logic core_t_dvo, core_fdvo, core_dvo, core_do;
    logic [7:0] core_t_do;

    function automatic logic signed [4:0] saturate_llr(input logic signed [7:0] value);
        if (value > 8'sd15)
            saturate_llr = 5'sd15;
        else if (value < -8'sd15)
            saturate_llr = -5'sd15;
        else
            saturate_llr = value[4:0];
    endfunction

    initial $readmemh(RATE_MAP_FILE, rate_map);

    assign READY = (state == ST_IDLE);
    assign INPUT_READY = (state == ST_RECEIVE) && (input_count < INPUT_BITS);
    assign BUSY = (state != ST_IDLE);
    assign core_init = (state == ST_INIT);
    assign core_fdvi = (state == ST_FEED) && (feed_index == 0);
    assign core_dvi = (state == ST_FEED);

    always_comb begin
        if (state == ST_PRIME)
            stream_rd_addr = 12'd0;
        else if ((state == ST_FEED) && (feed_index < LAST_SLOT))
            stream_rd_addr = feed_index + 1'b1;
        else
            stream_rd_addr = feed_index;
    end

    // The map follows the same LTE RV0 selection used by the software Turbo baseline.
    always_ff @(posedge CLK) begin
        if ((state == ST_RECEIVE) && IN_VALID && INPUT_READY)
            rate_map_q <= rate_map[input_count[11:0]];
    end

    // Clear punctured positions to zero, then write received LLRs by stream lane.
    always_comb begin
        stream_wr_addr = clear_addr;
        stream_wr_data = 5'sd0;
        stream0_wr_en = (state == ST_CLEAR);
        stream1_wr_en = (state == ST_CLEAR);
        stream2_wr_en = (state == ST_CLEAR);
        if ((state == ST_RECEIVE) && pending_valid) begin
            stream_wr_addr = rate_map_q[11:0];
            stream_wr_data = pending_llr;
            stream0_wr_en = (rate_map_q[13:12] == 0);
            stream1_wr_en = (rate_map_q[13:12] == 1);
            stream2_wr_en = (rate_map_q[13:12] == 2);
        end
    end

    turbo_derate_stream_sram stream0_buffer (
        .CLK(CLK), .WE(stream0_wr_en), .ADDR(stream_wr_addr), .DIN(stream_wr_data),
        .RD_ADDR(stream_rd_addr), .DOUT(stream0_q)
    );
    turbo_derate_stream_sram stream1_buffer (
        .CLK(CLK), .WE(stream1_wr_en), .ADDR(stream_wr_addr), .DIN(stream_wr_data),
        .RD_ADDR(stream_rd_addr), .DOUT(stream1_q)
    );
    turbo_derate_stream_sram stream2_buffer (
        .CLK(CLK), .WE(stream2_wr_en), .ADDR(stream_wr_addr), .DIN(stream_wr_data),
        .RD_ADDR(stream_rd_addr), .DOUT(stream2_q)
    );

    always_ff @(posedge CLK or posedge RST) begin
        if (RST) begin
            state <= ST_IDLE;
            clear_addr <= '0;
            input_count <= '0;
            input_complete <= 1'b0;
            pending_valid <= 1'b0;
            pending_llr <= '0;
            feed_index <= '0;
            output_count <= '0;
            DECODED_INFO <= '0;
            DONE <= 1'b0;
        end else begin
            DONE <= 1'b0;
            case (state)
                ST_IDLE: begin
                    if (START) begin
                        clear_addr <= '0;
                        input_count <= '0;
                        input_complete <= 1'b0;
                        pending_valid <= 1'b0;
                        output_count <= '0;
                        DECODED_INFO <= '0;
                        state <= ST_INIT;
                    end
                end
                ST_INIT: begin
                    clear_addr <= '0;
                    state <= ST_CLEAR;
                end
                ST_CLEAR: begin
                    if (clear_addr == LAST_SLOT) begin
                        state <= ST_RECEIVE;
                    end else begin
                        clear_addr <= clear_addr + 1'b1;
                    end
                end
                ST_RECEIVE: begin
                    if (IN_VALID && INPUT_READY) begin
                        pending_llr <= saturate_llr(IN_LLR);
                        pending_valid <= 1'b1;
                        input_count <= input_count + 1'b1;
                        if (input_count == INPUT_BITS-1)
                            input_complete <= 1'b1;
                    end else begin
                        pending_valid <= 1'b0;
                    end

                    if (input_complete && !pending_valid) begin
                        feed_index <= '0;
                        state <= ST_PRIME;
                    end
                end
                ST_PRIME: begin
                    feed_index <= '0;
                    state <= ST_FEED;
                end
                ST_FEED: begin
                    if (feed_index == LAST_SLOT) begin
                        state <= ST_DECODE;
                    end else begin
                        feed_index <= feed_index + 1'b1;
                    end
                end
                ST_DECODE: begin
                    if (core_dvo) begin
                        DECODED_INFO[output_count] <= core_do;
                        if (output_count == K-1) begin
                            state <= ST_IDLE;
                            DONE <= 1'b1;
                        end else begin
                            output_count <= output_count + 1'b1;
                        end
                    end
                end
                default: state <= ST_IDLE;
            endcase
        end
    end

    lte_turbo_decoder core (
        .CLK(CLK),
        .RST(RST),
        .INIT(core_init),
        .ITERATIONS(4'b1010),
        .SIZE_INDEX(8'd123),
        .FDVI(core_fdvi),
        .DVI(core_dvi),
        .DI0(stream0_q),
        .DI1(stream1_q),
        .DI2(stream2_q),
        .RFD(core_rfd),
        .t_dvo(core_t_dvo),
        .t_do(core_t_do),
        .FDVO(core_fdvo),
        .DVO(core_dvo),
        .DO(core_do)
    );
endmodule
