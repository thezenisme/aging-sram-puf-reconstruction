// Parameterized from the production five-bit flooding NMS implementation.
// Arithmetic, update order, BRAM prefetch and handshake schedule are preserved.
module formal_nms_core #(
    parameter integer N=4096, K=2048, Z=128, BASE_EDGES=123,
    parameter integer MAX_ROW_DEGREE=8,
    parameter MATRIX_DIR="generated/n4096",
    parameter integer N_AW=$clog2(N), M_AW=$clog2(N-K),
    parameter integer Z_AW=$clog2(Z), E_AW=$clog2(BASE_EDGES*Z),
    parameter integer B_AW=$clog2(BASE_EDGES), K_AW=$clog2(K),
    parameter integer WORD_AW=$clog2(K/64)
)(
    input wire clk, rst, start,
    input wire [7:0] maxiter,
    input wire in_valid,
    input wire signed [7:0] in_llr,
    output wire ready, input_ready, busy,
    output reg done, fail,
    output reg [7:0] iter_count,
    input wire out_ready,
    output wire out_valid, out_last,
    output wire [WORD_AW-1:0] out_index,
    output wire [63:0] out_word
);
    localparam integer M=N-K, EDGE_COUNT=BASE_EDGES*Z;
    localparam IDLE=0, LOAD=1, CLEAR=2, CN1=3, CN2=4,
               VRESET=5, VADD=6, CHECK=7, READOUT=8, WORD=9, FINISH=10;
    reg [3:0] state;
    reg [7:0] limit;
    reg [N_AW-1:0] index;
    reg [E_AW-1:0] clear_index;
    reg [M_AW-1:0] row;
    reg [K_AW-1:0] output_bit;
    reg [3:0] edge_index;
    reg [3:0] min1, min2, min_index;
    reg [MAX_ROW_DEGREE-1:0] signs;
    reg total_sign, check_parity;
    reg [63:0] output_shift;

    reg [N_AW-1:0] base_edges [0:BASE_EDGES-1];
    reg [B_AW+3:0] base_rows [0:M/Z-1];
    reg [N_AW-1:0] output_positions [0:K-1];
    initial begin
        $readmemh({MATRIX_DIR,"/base_edges.hex"},base_edges);
        $readmemh({MATRIX_DIR,"/base_rows.hex"},base_rows);
        $readmemh({MATRIX_DIR,"/output_positions.hex"},output_positions);
    end
    wire [B_AW+3:0] row_desc=base_rows[row[M_AW-1:Z_AW]];
    wire [B_AW-1:0] base_start=row_desc[B_AW+3:4];
    wire [3:0] degree=row_desc[3:0];
    wire [B_AW-1:0] base_address=base_start+edge_index;
    wire [N_AW-1:0] edge_desc=base_edges[base_address];
    wire [Z_AW-1:0] within_col=row[Z_AW-1:0]+edge_desc[Z_AW-1:0];
    wire [N_AW-1:0] column={edge_desc[N_AW-1:Z_AW],within_col};
    // Matrices are row-balanced: degree is MAX_ROW_DEGREE or one less.
    // Constant shift/subtract avoids a multiplier and preserves the N=4096 path.
    wire [E_AW-1:0] row_z={{(E_AW-Z_AW){1'b0}},row[Z_AW-1:0]};
    wire [E_AW-1:0] row_stride=(MAX_ROW_DEGREE==8)?(row_z<<3):
                                                   ((row_z<<3)-row_z);
    wire [E_AW-1:0] row_offset={base_start,{Z_AW{1'b0}}}+row_stride
                                - ((degree==MAX_ROW_DEGREE-1)?row_z:{E_AW{1'b0}});
    wire [E_AW-1:0] message_address=row_offset+edge_index;
    wire last_edge=(edge_index==degree-1);
    wire [N_AW-1:0] read_column=(state==VRESET)?index:
                                   (state==READOUT)?output_positions[output_bit]:column;
    wire signed [4:0] clipped_input=(in_llr>8'sd15)?5'sd15:
                                  (in_llr< -8'sd15)?-5'sd15:in_llr[4:0];
    wire signed [4:0] vn_read, channel_read, message_read;
    wire signed [5:0] difference={vn_read[4],vn_read}-{message_read[4],message_read};
    wire signed [4:0] extrinsic=(difference>6'sd15)?5'sd15:
                               (difference< -6'sd15)?-5'sd15:difference[4:0];
    wire [4:0] absolute=extrinsic[4]?-extrinsic:extrinsic;
    wire [3:0] magnitude=absolute[3:0];
    wire [3:0] selected_min=(edge_index==min_index)?min2:min1;
    wire [3:0] normalized=selected_min-(selected_min>>2);
    wire signed [4:0] new_message=(total_sign ^ signs[edge_index])?
                          -$signed({1'b0,normalized}):$signed({1'b0,normalized});
    wire signed [5:0] sum={vn_read[4],vn_read}+{message_read[4],message_read};
    wire signed [4:0] new_vn=(sum>6'sd15)?5'sd15:(sum< -6'sd15)?-5'sd15:sum[4:0];
    wire load_write=(!rst && state==LOAD && in_valid);
    wire var_write=load_write || (!rst && (state==VRESET || state==VADD));
    wire [N_AW-1:0] var_write_address=(load_write || state==VRESET)?index:column;
    wire signed [4:0] var_write_data=load_write?clipped_input:(state==VRESET)?channel_read:new_vn;
    wire message_write=(!rst && (state==CLEAR || state==CN2));
    wire [E_AW-1:0] message_write_address=(state==CLEAR)?clear_index:message_address;
    wire signed [4:0] message_write_data=(state==CLEAR)?5'sd0:new_message;
    formal_async_ram #(.ADDR_W(N_AW),.DEPTH(N)) var_store
      (clk,var_write,var_write_address,var_write_data,read_column,vn_read);
    formal_async_ram #(.ADDR_W(N_AW),.DEPTH(N)) input_store
      (clk,load_write,index,clipped_input,index,channel_read);
    wire message_prime=(state==CLEAR && clear_index==EDGE_COUNT-1) ||
                       (state==VRESET && index==N-1) ||
                       (state==CHECK && last_edge &&
                        (check_parity ^ vn_read[4]) && iter_count<limit);
    wire message_advance=(state==CN1 && !last_edge) ||
                         (state==CN2 && last_edge && row!=M-1) ||
                         (state==VADD && !(last_edge && row==M-1));
    wire message_read_enable=!rst && (message_prime || message_advance);
    wire [E_AW-1:0] message_read_address=message_prime?{E_AW{1'b0}}:
                                                     message_address+1'b1;
    formal_sync_ram #(.ADDR_W(E_AW),.DEPTH(EDGE_COUNT)) message_store
      (clk,message_write,message_write_address,message_write_data,
       message_read_enable,message_read_address,message_read);
    assign ready=(state==IDLE) && !rst;
    assign input_ready=(state==LOAD) && !rst;
    assign busy=(state!=IDLE) && !rst;
    assign out_valid=(state==WORD) && !rst;
    assign out_index=output_bit[K_AW-1:6];
    assign out_last=out_valid && (output_bit==K-1);
    assign out_word=output_shift;

    always @(posedge clk) begin
        if(rst) begin
            state<=IDLE;limit<=1;index<=0;clear_index<=0;row<=0;edge_index<=0;
            min1<=15;min2<=15;min_index<=15;signs<=0;total_sign<=0;
            check_parity<=0;output_bit<=0;output_shift<=0;
            done<=0;fail<=0;iter_count<=0;
        end else begin
            done<=0;
            case(state)
              IDLE: if(start) begin
                  limit<=(maxiter==0)?1:(maxiter>200)?200:maxiter;
                  index<=0;fail<=0;iter_count<=0;state<=LOAD;
              end
              LOAD: if(in_valid) begin
                  if(index==N-1) begin clear_index<=0;state<=CLEAR;end
                  else index<=index+1'b1;
              end
              CLEAR: if(clear_index==EDGE_COUNT-1) begin
                  row<=0;edge_index<=0;iter_count<=1;
                  min1<=15;min2<=15;min_index<=15;total_sign<=0;state<=CN1;
              end else clear_index<=clear_index+1'b1;
              CN1: begin
                  signs[edge_index]<=extrinsic[4];total_sign<=total_sign^extrinsic[4];
                  if(magnitude<min1) begin min2<=min1;min1<=magnitude;min_index<=edge_index;end
                  else if(magnitude<min2) min2<=magnitude;
                  if(last_edge) begin edge_index<=0;state<=CN2;end
                  else edge_index<=edge_index+1'b1;
              end
              CN2: if(last_edge) begin
                  edge_index<=0;min1<=15;min2<=15;min_index<=15;total_sign<=0;
                  if(row==M-1) begin index<=0;state<=VRESET;end
                  else begin row<=row+1'b1;state<=CN1;end
              end else edge_index<=edge_index+1'b1;
              VRESET: if(index==N-1) begin row<=0;edge_index<=0;state<=VADD;end
                      else index<=index+1'b1;
              VADD: if(last_edge) begin
                  edge_index<=0;
                  if(row==M-1) begin row<=0;check_parity<=0;state<=CHECK;end
                  else row<=row+1'b1;
              end else edge_index<=edge_index+1'b1;
              CHECK: if(last_edge) begin
                  edge_index<=0;check_parity<=0;
                  if(check_parity ^ vn_read[4]) begin
                      if(iter_count>=limit) begin fail<=1;output_bit<=0;state<=READOUT;end
                      else begin
                          iter_count<=iter_count+1'b1;row<=0;min1<=15;min2<=15;
                          min_index<=15;total_sign<=0;state<=CN1;
                      end
                  end else if(row==M-1) begin fail<=0;output_bit<=0;state<=READOUT;end
                  else row<=row+1'b1;
              end else begin check_parity<=check_parity^vn_read[4];edge_index<=edge_index+1'b1;end
              READOUT: begin
                  output_shift[output_bit[5:0]]<=vn_read[4];
                  if(output_bit[5:0]==63) state<=WORD;
                  else output_bit<=output_bit+1'b1;
              end
              WORD: if(out_ready) begin
                  if(output_bit==K-1) state<=FINISH;
                  else begin output_bit<=output_bit+1'b1;state<=READOUT;end
              end
              FINISH: begin done<=1;state<=IDLE;end
              default:state<=IDLE;
            endcase
        end
    end
endmodule

module formal_sync_ram #(parameter ADDR_W=14,DEPTH=15744)(
    input wire clk,we,
    input wire [ADDR_W-1:0] waddr,
    input wire signed [4:0] wdata,
    input wire re,
    input wire [ADDR_W-1:0] raddr,
    output reg signed [4:0] rdata
);
    (* ram_style="block" *) reg signed [4:0] mem [0:DEPTH-1];
    always @(posedge clk) begin
        if(we) mem[waddr]<=wdata;
        if(re) rdata<=mem[raddr];
    end
endmodule

module formal_async_ram #(parameter ADDR_W=12,DEPTH=4096)(
    input wire clk,we,
    input wire [ADDR_W-1:0] waddr,
    input wire signed [4:0] wdata,
    input wire [ADDR_W-1:0] raddr,
    output wire signed [4:0] rdata
);
    (* ram_style="distributed" *) reg signed [4:0] mem [0:DEPTH-1];
    always @(posedge clk) if(we) mem[waddr]<=wdata;
    assign rdata=mem[raddr];
endmodule
