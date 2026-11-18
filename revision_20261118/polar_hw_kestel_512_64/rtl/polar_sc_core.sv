module polar_sc_core #(
    parameter integer N = 512,
    parameter integer K = 64,
    parameter integer LOG_N = 9,
    parameter integer LLR_BITS = 8,
    // Bit i is 1 when polar input position i is frozen.
    parameter [N-1:0] FROZEN_MASK = 512'h1777577f577f7fff177f7f7f7f7f7fff177f7f7f777f7fff777f7fff7fffffff177f7f7f777f7fff777f7fff7fffffff777f7fff7fffffff7fffffff7fffffff
) (
    input  wire                         clk,
    input  wire                         rst,
    input  wire                         start,
    output wire                         ready,
    input  wire                         in_valid,
    input  wire signed [LLR_BITS-1:0]   in_llr,
    output reg                          done,
    output reg  [K-1:0]                 decoded_info
);
    localparam [1:0] IDLE = 2'd0, LOAD = 2'd1, RUN = 2'd2;
    localparam [1:0] LEFT = 2'd0, RIGHT = 2'd1, COMBINE = 2'd2;

    reg [1:0] state;
    reg [LOG_N-1:0] load_index;
    reg [LOG_N:0] depth;
    reg [LOG_N-1:0] op_index;
    reg [LOG_N-1:0] node_start [0:LOG_N];
    reg [1:0] phase [0:LOG_N];
    reg [LOG_N:0] info_index;

    // Separate node-level storage makes the schedule explicit. Memory packing
    // is intentionally left for a later low-area architecture pass.
    reg signed [LLR_BITS-1:0] alpha [0:(LOG_N+1)*N-1];
    reg beta [0:(LOG_N+1)*N-1];

    wire [LOG_N:0] half_size = N >> (depth + 1);
    wire [LOG_N:0] node_size = N >> depth;
    wire [LOG_N:0] left_pos = node_start[depth] + op_index;
    wire [LOG_N:0] right_pos = left_pos + half_size;
    wire signed [LLR_BITS-1:0] left_llr = alpha[depth*N + left_pos];
    wire signed [LLR_BITS-1:0] right_llr = alpha[depth*N + right_pos];
    wire left_beta = beta[(depth+1)*N + left_pos];
    wire right_beta = beta[(depth+1)*N + right_pos];
    wire leaf_bit = !FROZEN_MASK[node_start[depth]] &&
                    alpha[depth*N + node_start[depth]] < 0;

    assign ready = (state == IDLE);

    function automatic signed [LLR_BITS-1:0] f_min_sum(
        input signed [LLR_BITS-1:0] a,
        input signed [LLR_BITS-1:0] b
    );
        reg signed [LLR_BITS:0] aa, bb, magnitude;
        begin
            aa = a < 0 ? -$signed({a[LLR_BITS-1], a}) : $signed({a[LLR_BITS-1], a});
            bb = b < 0 ? -$signed({b[LLR_BITS-1], b}) : $signed({b[LLR_BITS-1], b});
            magnitude = aa < bb ? aa : bb;
            if (magnitude > (2**(LLR_BITS-1)-1))
                magnitude = 2**(LLR_BITS-1)-1;
            f_min_sum = (a[LLR_BITS-1] ^ b[LLR_BITS-1]) ? -magnitude : magnitude;
        end
    endfunction

    function automatic signed [LLR_BITS-1:0] g_saturate(
        input signed [LLR_BITS-1:0] a,
        input signed [LLR_BITS-1:0] b,
        input bit left_bit
    );
        reg signed [LLR_BITS:0] sum;
        begin
            sum = (left_bit ? -$signed({a[LLR_BITS-1], a}) :
                              $signed({a[LLR_BITS-1], a})) +
                  $signed({b[LLR_BITS-1], b});
            if (sum > (2**(LLR_BITS-1)-1))
                g_saturate = 2**(LLR_BITS-1)-1;
            else if (sum < -(2**(LLR_BITS-1)))
                g_saturate = -(2**(LLR_BITS-1));
            else
                g_saturate = sum[LLR_BITS-1:0];
        end
    endfunction

    always @(posedge clk) begin
        if (rst) begin
            state <= IDLE;
            load_index <= 0;
            depth <= 0;
            op_index <= 0;
            info_index <= 0;
            decoded_info <= 0;
            done <= 0;
        end else begin
            done <= 0;
            case (state)
                IDLE: if (start) begin
                    state <= LOAD;
                    load_index <= 0;
                    decoded_info <= 0;
                    info_index <= 0;
                end
                LOAD: if (in_valid) begin
                    alpha[load_index] <= in_llr;
                    if (load_index == N-1) begin
                        state <= RUN;
                        depth <= 0;
                        node_start[0] <= 0;
                        phase[0] <= LEFT;
                        op_index <= 0;
                    end else begin
                        load_index <= load_index + 1'b1;
                    end
                end
                RUN: if (node_size == 1) begin
                    beta[depth*N + node_start[depth]] <= leaf_bit;
                    if (!FROZEN_MASK[node_start[depth]]) begin
                        decoded_info[info_index] <= leaf_bit;
                        info_index <= info_index + 1'b1;
                    end
                    depth <= depth - 1'b1;
                    op_index <= 0;
                end else begin
                    case (phase[depth])
                        LEFT: begin
                            alpha[(depth+1)*N + left_pos] <=
                                f_min_sum(left_llr, right_llr);
                            if (op_index == half_size-1) begin
                                phase[depth] <= RIGHT;
                                node_start[depth+1] <= node_start[depth];
                                phase[depth+1] <= LEFT;
                                depth <= depth + 1'b1;
                                op_index <= 0;
                            end else begin
                                op_index <= op_index + 1'b1;
                            end
                        end
                        RIGHT: begin
                            alpha[(depth+1)*N + right_pos] <=
                                g_saturate(left_llr, right_llr, left_beta);
                            if (op_index == half_size-1) begin
                                phase[depth] <= COMBINE;
                                node_start[depth+1] <= node_start[depth] + half_size;
                                phase[depth+1] <= LEFT;
                                depth <= depth + 1'b1;
                                op_index <= 0;
                            end else begin
                                op_index <= op_index + 1'b1;
                            end
                        end
                        COMBINE: begin
                            beta[depth*N + left_pos] <= left_beta ^ right_beta;
                            beta[depth*N + right_pos] <= right_beta;
                            if (op_index == half_size-1) begin
                                op_index <= 0;
                                if (depth == 0) begin
                                    state <= IDLE;
                                    done <= 1;
                                end else begin
                                    depth <= depth - 1'b1;
                                end
                            end else begin
                                op_index <= op_index + 1'b1;
                            end
                        end
                        default: state <= IDLE;
                    endcase
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule
