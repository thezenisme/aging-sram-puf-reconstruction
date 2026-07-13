// Parameterized folded LDPC-like scaling prototype.
// Purpose: synthesize N=256/512/1024 variants with the same folded datapath
// while scaling only the circulant factor Z and associated memories.
module LDPC_scaling_folded_core #(
    parameter integer LLR_W = 5,
    parameter integer Z = 16,
    parameter integer Z_W = 4,
    parameter integer N_BASE = 16,
    parameter integer M_BASE = 8,
    parameter integer ROW_W = 4,
    parameter integer EDGE_COUNT = 32,
    parameter integer N_ADDR_W = 8,
    parameter integer E_ADDR_W = 9
)(
    input  wire        CLK,
    input  wire        RESET_N,
    input  wire        start,
    input  wire [5:0]  maxiter,
    input  wire [15:0] seed,

    output reg         busy,
    output reg         done,
    output reg         fail,
    output reg  [5:0]  iter_count,
    output reg  [15:0] checksum
);

localparam S_IDLE      = 4'd0;
localparam S_CLEAR_VAR = 4'd1;
localparam S_CLEAR_C2V = 4'd2;
localparam S_INIT_Z    = 4'd3;
localparam S_PASS1     = 4'd4;
localparam S_PASS2     = 4'd5;
localparam S_NEXT_Z    = 4'd6;
localparam S_CHECK     = 4'd7;
localparam S_CHECK_ACC = 4'd8;
localparam S_OUT       = 4'd9;

reg [3:0] state;
reg [3:0] layer_idx;
reg [Z_W-1:0] z_idx;
reg [1:0] edge_sel;
reg [3:0] check_layer;
reg [Z_W-1:0] check_z;
reg [1:0] check_edge;
reg check_parity;
reg syndrome_error;

reg [N_ADDR_W-1:0] var_clear_addr;
reg [E_ADDR_W-1:0] c2v_clear_addr;
reg var_we;
reg c2v_we;
reg [N_ADDR_W-1:0] var_waddr;
reg [E_ADDR_W-1:0] c2v_waddr;
reg signed [LLR_W-1:0] var_wdata;
reg signed [LLR_W-1:0] c2v_wdata;
wire signed [LLR_W-1:0] var_rdata;
wire signed [LLR_W-1:0] c2v_rdata;

reg signed [LLR_W-1:0] v2c_buf [0:ROW_W-1];
reg [LLR_W-2:0] min1;
reg [LLR_W-2:0] min2;
reg [1:0] minpos;
reg sign_all;

integer i;
reg signed [LLR_W-1:0] old_msg;
reg signed [LLR_W-1:0] v2c_now;
reg signed [LLR_W-1:0] new_msg;
reg signed [LLR_W-1:0] mag_msg;
reg [LLR_W-2:0] abs_now;
reg [3:0] col_now;
reg [Z_W-1:0] sh_now;
reg [Z_W-1:0] var_z_now;
reg [N_ADDR_W-1:0] var_addr_now;
reg [E_ADDR_W-1:0] msg_addr_now;

ldpc_scaling_1r1w_ram #(
    .DATA_W(LLR_W),
    .ADDR_W(N_ADDR_W),
    .DEPTH(N_BASE*Z)
) var_store (
    .clk(CLK),
    .we(var_we),
    .waddr(var_waddr),
    .wdata(var_wdata),
    .raddr(var_addr_now),
    .rdata(var_rdata)
);

ldpc_scaling_1r1w_ram #(
    .DATA_W(LLR_W),
    .ADDR_W(E_ADDR_W),
    .DEPTH(EDGE_COUNT*Z)
) c2v_store (
    .clk(CLK),
    .we(c2v_we),
    .waddr(c2v_waddr),
    .wdata(c2v_wdata),
    .raddr(msg_addr_now),
    .rdata(c2v_rdata)
);

function [3:0] base_col;
    input [3:0] row;
    input [1:0] edge_id;
    begin
        case (row)
            4'd0: base_col = (edge_id==0) ? 4'd0  : (edge_id==1) ? 4'd1  : (edge_id==2) ? 4'd5  : 4'd9;
            4'd1: base_col = (edge_id==0) ? 4'd1  : (edge_id==1) ? 4'd2  : (edge_id==2) ? 4'd6  : 4'd10;
            4'd2: base_col = (edge_id==0) ? 4'd2  : (edge_id==1) ? 4'd3  : (edge_id==2) ? 4'd7  : 4'd11;
            4'd3: base_col = (edge_id==0) ? 4'd3  : (edge_id==1) ? 4'd4  : (edge_id==2) ? 4'd8  : 4'd12;
            4'd4: base_col = (edge_id==0) ? 4'd4  : (edge_id==1) ? 4'd5  : (edge_id==2) ? 4'd9  : 4'd13;
            4'd5: base_col = (edge_id==0) ? 4'd6  : (edge_id==1) ? 4'd7  : (edge_id==2) ? 4'd10 : 4'd14;
            4'd6: base_col = (edge_id==0) ? 4'd8  : (edge_id==1) ? 4'd11 : (edge_id==2) ? 4'd13 : 4'd15;
            default: base_col = (edge_id==0) ? 4'd0 : (edge_id==1) ? 4'd12 : (edge_id==2) ? 4'd14 : 4'd15;
        endcase
    end
endfunction

function [Z_W-1:0] base_shift;
    input [3:0] row;
    input [1:0] edge_id;
    reg [Z_W-1:0] raw_shift;
    begin
        raw_shift = (row * 3 + edge_id * 5 + row[1:0] * edge_id) % Z;
        base_shift = raw_shift;
    end
endfunction

function [4:0] edge_index;
    input [3:0] row;
    input [1:0] edge_id;
    begin
        edge_index = {row, 2'b00} + edge_id;
    end
endfunction

function signed [LLR_W-1:0] sat_add;
    input signed [LLR_W-1:0] a;
    input signed [LLR_W-1:0] b;
    reg signed [LLR_W:0] s;
    begin
        s = a + b;
        if (s > 15)
            sat_add = 5'sd15;
        else if (s < -15)
            sat_add = -5'sd15;
        else
            sat_add = s[LLR_W-1:0];
    end
endfunction

function signed [LLR_W-1:0] sat_sub;
    input signed [LLR_W-1:0] a;
    input signed [LLR_W-1:0] b;
    begin
        sat_sub = sat_add(a, -b);
    end
endfunction

function [LLR_W-2:0] abs5;
    input signed [LLR_W-1:0] a;
    begin
        abs5 = a[LLR_W-1] ? -a : a;
    end
endfunction

function [LLR_W-2:0] norm075;
    input [LLR_W-2:0] a;
    begin
        norm075 = a - (a >> 2);
    end
endfunction

always @(*) begin
    col_now = base_col(layer_idx, edge_sel);
    sh_now = base_shift(layer_idx, edge_sel);
    var_z_now = (z_idx + Z[Z_W-1:0] - sh_now) % Z;
    var_addr_now = col_now * Z + var_z_now;
    msg_addr_now = edge_index(layer_idx, edge_sel) * Z + z_idx;
end

always @(posedge CLK or negedge RESET_N) begin
    if (!RESET_N) begin
        state <= S_IDLE;
        busy <= 1'b0;
        done <= 1'b0;
        fail <= 1'b0;
        iter_count <= 6'd0;
        checksum <= 16'd0;
        layer_idx <= 4'd0;
        z_idx <= {Z_W{1'b0}};
        edge_sel <= 2'd0;
        check_layer <= 4'd0;
        check_z <= {Z_W{1'b0}};
        check_edge <= 2'd0;
        check_parity <= 1'b0;
        syndrome_error <= 1'b0;
        var_clear_addr <= {N_ADDR_W{1'b0}};
        c2v_clear_addr <= {E_ADDR_W{1'b0}};
        var_we <= 1'b0;
        c2v_we <= 1'b0;
        var_waddr <= {N_ADDR_W{1'b0}};
        c2v_waddr <= {E_ADDR_W{1'b0}};
        var_wdata <= 5'sd0;
        c2v_wdata <= 5'sd0;
        min1 <= 4'd15;
        min2 <= 4'd15;
        minpos <= 2'd0;
        sign_all <= 1'b0;
        for (i = 0; i < ROW_W; i = i + 1)
            v2c_buf[i] <= 5'sd0;
    end else begin
        done <= 1'b0;
        var_we <= 1'b0;
        c2v_we <= 1'b0;

        case (state)
            S_IDLE: begin
                busy <= 1'b0;
                if (start) begin
                    busy <= 1'b1;
                    fail <= 1'b0;
                    iter_count <= 6'd0;
                    checksum <= seed;
                    var_clear_addr <= {N_ADDR_W{1'b0}};
                    c2v_clear_addr <= {E_ADDR_W{1'b0}};
                    layer_idx <= 4'd0;
                    z_idx <= {Z_W{1'b0}};
                    edge_sel <= 2'd0;
                    state <= S_CLEAR_VAR;
                end
            end

            S_CLEAR_VAR: begin
                var_we <= 1'b1;
                var_waddr <= var_clear_addr;
                var_wdata <= seed[var_clear_addr[3:0]] ? -5'sd9 : 5'sd9;
                if (var_clear_addr == N_BASE*Z-1) begin
                    var_clear_addr <= {N_ADDR_W{1'b0}};
                    c2v_clear_addr <= {E_ADDR_W{1'b0}};
                    state <= S_CLEAR_C2V;
                end else begin
                    var_clear_addr <= var_clear_addr + 1'b1;
                end
            end

            S_CLEAR_C2V: begin
                c2v_we <= 1'b1;
                c2v_waddr <= c2v_clear_addr;
                c2v_wdata <= 5'sd0;
                if (c2v_clear_addr == EDGE_COUNT*Z-1) begin
                    c2v_clear_addr <= {E_ADDR_W{1'b0}};
                    state <= S_INIT_Z;
                end else begin
                    c2v_clear_addr <= c2v_clear_addr + 1'b1;
                end
            end

            S_INIT_Z: begin
                edge_sel <= 2'd0;
                min1 <= 4'd15;
                min2 <= 4'd15;
                minpos <= 2'd0;
                sign_all <= 1'b0;
                state <= S_PASS1;
            end

            S_PASS1: begin
                old_msg = c2v_rdata;
                v2c_now = sat_sub(var_rdata, old_msg);
                v2c_buf[edge_sel] <= v2c_now;
                abs_now = abs5(v2c_now);
                sign_all <= sign_all ^ v2c_now[LLR_W-1];
                if (abs_now <= min1) begin
                    min2 <= min1;
                    min1 <= abs_now;
                    minpos <= edge_sel;
                end else if (abs_now < min2) begin
                    min2 <= abs_now;
                end

                if (edge_sel == ROW_W-1) begin
                    edge_sel <= 2'd0;
                    state <= S_PASS2;
                end else begin
                    edge_sel <= edge_sel + 2'd1;
                end
            end

            S_PASS2: begin
                if (minpos == edge_sel)
                    mag_msg = {1'b0, norm075(min2)};
                else
                    mag_msg = {1'b0, norm075(min1)};
                if (sign_all ^ v2c_buf[edge_sel][LLR_W-1])
                    new_msg = -mag_msg;
                else
                    new_msg = mag_msg;
                c2v_we <= 1'b1;
                c2v_waddr <= msg_addr_now;
                c2v_wdata <= new_msg;
                var_we <= 1'b1;
                var_waddr <= var_addr_now;
                var_wdata <= sat_add(v2c_buf[edge_sel], new_msg);

                if (edge_sel == ROW_W-1) begin
                    edge_sel <= 2'd0;
                    state <= S_NEXT_Z;
                end else begin
                    edge_sel <= edge_sel + 2'd1;
                end
            end

            S_NEXT_Z: begin
                if (z_idx == Z-1) begin
                    z_idx <= {Z_W{1'b0}};
                    if (layer_idx == M_BASE-1) begin
                        layer_idx <= 4'd0;
                        iter_count <= iter_count + 6'd1;
                        check_layer <= 4'd0;
                        check_z <= {Z_W{1'b0}};
                        check_edge <= 2'd0;
                        check_parity <= 1'b0;
                        syndrome_error <= 1'b0;
                        state <= S_CHECK;
                    end else begin
                        layer_idx <= layer_idx + 4'd1;
                        state <= S_INIT_Z;
                    end
                end else begin
                    z_idx <= z_idx + 1'b1;
                    state <= S_INIT_Z;
                end
            end

            S_CHECK: begin
                layer_idx <= check_layer;
                z_idx <= check_z;
                edge_sel <= check_edge;
                state <= S_CHECK_ACC;
            end

            S_CHECK_ACC: begin
                check_parity <= check_parity ^ var_rdata[LLR_W-1];
                checksum <= {checksum[14:0], checksum[15] ^ var_rdata[0] ^ var_rdata[LLR_W-1]};
                if (check_edge == ROW_W-1) begin
                    syndrome_error <= syndrome_error | (check_parity ^ var_rdata[LLR_W-1]);
                    check_parity <= 1'b0;
                    check_edge <= 2'd0;
                    if (check_z == Z-1) begin
                        check_z <= {Z_W{1'b0}};
                        if (check_layer == M_BASE-1) begin
                            if (!(syndrome_error | (check_parity ^ var_rdata[LLR_W-1]))) begin
                                fail <= 1'b0;
                                state <= S_OUT;
                            end else if (iter_count >= maxiter) begin
                                fail <= 1'b1;
                                state <= S_OUT;
                            end else begin
                                layer_idx <= 4'd0;
                                z_idx <= {Z_W{1'b0}};
                                edge_sel <= 2'd0;
                                state <= S_INIT_Z;
                            end
                        end else begin
                            check_layer <= check_layer + 4'd1;
                            state <= S_CHECK;
                        end
                    end else begin
                        check_z <= check_z + 1'b1;
                        state <= S_CHECK;
                    end
                end else begin
                    check_edge <= check_edge + 2'd1;
                    state <= S_CHECK;
                end
            end

            S_OUT: begin
                busy <= 1'b0;
                done <= 1'b1;
                state <= S_IDLE;
            end

            default: state <= S_IDLE;
        endcase
    end
end

endmodule

module ldpc_scaling_1r1w_ram #(
    parameter integer DATA_W = 5,
    parameter integer ADDR_W = 9,
    parameter integer DEPTH = 512
)(
    input  wire                     clk,
    input  wire                     we,
    input  wire [ADDR_W-1:0]        waddr,
    input  wire signed [DATA_W-1:0] wdata,
    input  wire [ADDR_W-1:0]        raddr,
    output wire signed [DATA_W-1:0] rdata
);

(* ram_style = "distributed" *) reg signed [DATA_W-1:0] mem [0:DEPTH-1];

assign rdata = mem[raddr];

always @(posedge clk) begin
    if (we)
        mem[waddr] <= wdata;
end

endmodule

module LDPC_scaling_n256 (
    input  wire CLK,
    input  wire RESET_N,
    input  wire start,
    input  wire [5:0] maxiter,
    input  wire [15:0] seed,
    output wire busy,
    output wire done,
    output wire fail,
    output wire [5:0] iter_count,
    output wire [15:0] checksum
);
LDPC_scaling_folded_core #(.Z(16), .Z_W(4), .N_ADDR_W(8), .E_ADDR_W(9)) u_core (
    .CLK(CLK), .RESET_N(RESET_N), .start(start), .maxiter(maxiter), .seed(seed),
    .busy(busy), .done(done), .fail(fail), .iter_count(iter_count), .checksum(checksum)
);
endmodule

module LDPC_scaling_n512 (
    input  wire CLK,
    input  wire RESET_N,
    input  wire start,
    input  wire [5:0] maxiter,
    input  wire [15:0] seed,
    output wire busy,
    output wire done,
    output wire fail,
    output wire [5:0] iter_count,
    output wire [15:0] checksum
);
LDPC_scaling_folded_core #(.Z(32), .Z_W(5), .N_ADDR_W(9), .E_ADDR_W(10)) u_core (
    .CLK(CLK), .RESET_N(RESET_N), .start(start), .maxiter(maxiter), .seed(seed),
    .busy(busy), .done(done), .fail(fail), .iter_count(iter_count), .checksum(checksum)
);
endmodule

module LDPC_scaling_n1024 (
    input  wire CLK,
    input  wire RESET_N,
    input  wire start,
    input  wire [5:0] maxiter,
    input  wire [15:0] seed,
    output wire busy,
    output wire done,
    output wire fail,
    output wire [5:0] iter_count,
    output wire [15:0] checksum
);
LDPC_scaling_folded_core #(.Z(64), .Z_W(6), .N_ADDR_W(10), .E_ADDR_W(11)) u_core (
    .CLK(CLK), .RESET_N(RESET_N), .start(start), .maxiter(maxiter), .seed(seed),
    .busy(busy), .done(done), .fail(fail), .iter_count(iter_count), .checksum(checksum)
);
endmodule

module LDPC_scaling_n2048 (
    input  wire CLK,
    input  wire RESET_N,
    input  wire start,
    input  wire [5:0] maxiter,
    input  wire [15:0] seed,
    output wire busy,
    output wire done,
    output wire fail,
    output wire [5:0] iter_count,
    output wire [15:0] checksum
);
LDPC_scaling_folded_core #(.Z(128), .Z_W(7), .N_ADDR_W(11), .E_ADDR_W(12)) u_core (
    .CLK(CLK), .RESET_N(RESET_N), .start(start), .maxiter(maxiter), .seed(seed),
    .busy(busy), .done(done), .fail(fail), .iter_count(iter_count), .checksum(checksum)
);
endmodule

module LDPC_scaling_n4096 (
    input  wire CLK,
    input  wire RESET_N,
    input  wire start,
    input  wire [5:0] maxiter,
    input  wire [15:0] seed,
    output wire busy,
    output wire done,
    output wire fail,
    output wire [5:0] iter_count,
    output wire [15:0] checksum
);
LDPC_scaling_folded_core #(.Z(256), .Z_W(8), .N_ADDR_W(12), .E_ADDR_W(13)) u_core (
    .CLK(CLK), .RESET_N(RESET_N), .start(start), .maxiter(maxiter), .seed(seed),
    .busy(busy), .done(done), .fail(fail), .iter_count(iter_count), .checksum(checksum)
);
endmodule
