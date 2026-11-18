// Independent FPGA implementation of the shared-memory, instruction-driven
// architecture in Kestel et al., SOCC 2022, Sections II-C and III-D.
// Fixed N=512, K=64; ROM generated from the local frozen set.
module polar_sc_kestel #(
    parameter integer LLR_BITS=8,
    parameter integer FAST=1,
    parameter ROM_FILE = "",
    parameter integer ROM_DEPTH=512
) (
    input wire clk, rst, start,
    output wire ready,
    input wire in_valid,
    input wire signed [LLR_BITS-1:0] in_llr,
    output reg done,
    output reg [63:0] decoded_info
);
    localparam integer W=4*LLR_BITS;
    localparam integer SW=LLR_BITS+10;
    localparam [4:0] END_OP=0,F=1,G=2,G0=3,ZERO=4,HD=5,H=6,COPY=7,
        REP_INIT=8,REP_ACC=9,REP_FILL=10,SPC_INIT=11,SPC_ACC=12,SPC_FLIP=13,EXTRACT=14;
    localparam [2:0] IDLE=0,LOAD=1,FETCH=2,PREP=3,RD1=4,RD2=5,EXEC=6;
    reg [2:0] state;
    reg [8:0] load_index;
    reg [W-1:0] load_word;
    reg [$clog2(ROM_DEPTH)-1:0] pc;
    (* rom_style="block" *) reg [63:0] rom [0:ROM_DEPTH-1];
    reg [63:0] ir;
    initial begin
        if(ROM_FILE!="") $readmemh(ROM_FILE,rom);
        else if(FAST) $readmemh("generated/fast.mem",rom);
        else $readmemh("generated/exact.mem",rom);
    end
    // Single-port synchronous memories, never reset: every live word is
    // written before it is read. Both use the same active-path stack layout.
    (* ram_style="block" *) reg [W-1:0] mem_a [0:511];
    (* ram_style="block" *) reg [3:0] mem_b [0:511];
    reg [W-1:0] aq,a_hold;
    reg [3:0] bq,b_hold;
    reg [8:0] a_addr,b_addr;
    reg a_we,b_we;
    reg [W-1:0] a_write;
    reg [3:0] b_write;
    reg [7:0] word_offset;
    reg signed [SW-1:0] rep_sum;
    reg spc_parity;
    reg [LLR_BITS:0] spc_min;
    reg [8:0] spc_addr;
    reg [1:0] spc_lane;
    reg extract_acc;

    wire [4:0] op=ir[4:0];
    wire [8:0] aa=ir[13:5]+word_offset;
    wire [8:0] ab=ir[22:14]+word_offset;
    wire [8:0] bb=ir[31:23]+word_offset;
    wire [8:0] dst=ir[40:32]+word_offset;
    wire [1:0] sa=ir[42:41],sb=ir[44:43];
    wire [2:0] count=ir[47:45];
    wire [3:0] mask=ir[51:48];
    wire [5:0] out_index=ir[57:52];
    wire [2:0] flags=ir[60:58];
    wire [7:0] run_words=8'd1 << ir[63:61];
    wire [W-1:0] shifted_a=a_hold >> (sa*LLR_BITS);
    wire [W-1:0] shifted_b=aq >> (sb*LLR_BITS);
    assign ready=state==IDLE;

    function automatic signed [LLR_BITS-1:0] f_value(
        input signed [LLR_BITS-1:0] a,b);
        reg signed [LLR_BITS:0] ma,mb,m;
        begin
            ma=a<0 ? -$signed({a[LLR_BITS-1],a}) : $signed({a[LLR_BITS-1],a});
            mb=b<0 ? -$signed({b[LLR_BITS-1],b}) : $signed({b[LLR_BITS-1],b});
            m=ma<mb ? ma : mb;
            if(m>((1<<(LLR_BITS-1))-1)) m=(1<<(LLR_BITS-1))-1;
            f_value=(a[LLR_BITS-1]^b[LLR_BITS-1]) ? -m : m;
        end
    endfunction
    function automatic signed [LLR_BITS-1:0] g_value(
        input signed [LLR_BITS-1:0] a,b,input c);
        reg signed [LLR_BITS:0] s;
        begin
            s=(c ? -$signed({a[LLR_BITS-1],a}) : $signed({a[LLR_BITS-1],a}))
                +$signed({b[LLR_BITS-1],b});
            if(s>((1<<(LLR_BITS-1))-1)) g_value=(1<<(LLR_BITS-1))-1;
            else if(s<-(1<<(LLR_BITS-1))) g_value=-(1<<(LLR_BITS-1));
            else g_value=s[LLR_BITS-1:0];
        end
    endfunction

    integer lane;
    reg signed [LLR_BITS-1:0] av,bv;
    reg signed [SW-1:0] lane_sum;
    reg [LLR_BITS:0] min_next,magnitude;
    reg [8:0] min_addr_next;
    reg [1:0] min_lane_next;
    reg parity_next;
    reg [W-1:0] fg_result;
    reg [3:0] hard_bits,combined;
    always @* begin
        fg_result=0; hard_bits=0; lane_sum=0;
        min_next=spc_min; min_addr_next=spc_addr; min_lane_next=spc_lane;
        parity_next=spc_parity; magnitude=0; av=0; bv=0;
        for(lane=0;lane<4;lane=lane+1) begin
            av=$signed(shifted_a[lane*LLR_BITS+:LLR_BITS]);
            bv=$signed(shifted_b[lane*LLR_BITS+:LLR_BITS]);
            if(lane<count) begin
                fg_result[lane*LLR_BITS+:LLR_BITS]=op==F ? f_value(av,bv) :
                    g_value(av,bv,(op==G) && b_hold[lane]);
                av=$signed(a_hold[lane*LLR_BITS+:LLR_BITS]);
                hard_bits[lane]=av<0;
                lane_sum=lane_sum+av;
                magnitude=av<0 ? -$signed({av[LLR_BITS-1],av}) : $signed({av[LLR_BITS-1],av});
                if(magnitude<min_next) begin
                    min_next=magnitude; min_addr_next=dst; min_lane_next=lane;
                end
                parity_next=parity_next^(av<0);
            end
        end
        // H packs both children in one word for 2- and 4-bit parent nodes.
        combined=b_hold^bq;
        if(flags[0]) begin
            combined=0;
            for(lane=0;lane<4;lane=lane+1)
                if(lane<count) begin
                    combined[lane]=b_hold[lane]^bq[lane];
                    combined[lane+count]=bq[lane];
                end
        end
    end

    always @* begin
        a_addr=0; b_addr=0; a_we=0; b_we=0; a_write=0; b_write=0;
        case(state)
            LOAD: begin
                a_addr={2'b00,load_index[8:2]};
                a_write=load_word;
                a_write[3*LLR_BITS+:LLR_BITS]=in_llr;
                a_we=in_valid && load_index[1:0]==3;
            end
            RD1: begin
                a_addr=aa;
                b_addr=op==G ? bb : (op==SPC_FLIP ? spc_addr : aa);
            end
            RD2: begin a_addr=ab; b_addr=ab; end
            EXEC: begin
                a_addr=dst; b_addr=dst;
                case(op)
                    F,G,G0: begin a_we=1; a_write=fg_result; end
                    ZERO: begin b_we=1; b_write=0; end
                    HD,SPC_ACC: begin b_we=1; b_write=hard_bits; end
                    H: begin b_we=1; b_write=combined; end
                    COPY: begin b_we=1; b_write=b_hold; end
                    REP_FILL: begin
                        b_we=1; b_write=rep_sum<0 ? ((5'b1<<count)-1) : 0;
                    end
                    SPC_FLIP: begin
                        b_addr=spc_addr; b_we=spc_parity;
                        b_write=b_hold^(4'b1<<spc_lane);
                    end
                    default: begin end
                endcase
            end
            default: begin end
        endcase
    end

    always @(posedge clk) begin
        if(a_we) mem_a[a_addr]<=a_write;
        else aq<=mem_a[a_addr];
        if(b_we) mem_b[b_addr]<=b_write;
        else bq<=mem_b[b_addr];
        if(state==FETCH) ir<=rom[pc];
    end

    always @(posedge clk) begin
        if(rst) begin
            state<=IDLE; pc<=0; done<=0; decoded_info<=0;
            load_index<=0; load_word<=0; word_offset<=0;
            rep_sum<=0; spc_parity<=0; spc_min<={LLR_BITS+1{1'b1}};
            spc_addr<=0; spc_lane<=0; extract_acc<=0;
            a_hold<=0; b_hold<=0;
        end else begin
            done<=0;
            case(state)
                IDLE: if(start) begin
                    state<=LOAD; load_index<=0; load_word<=0; decoded_info<=0; pc<=0;
                end
                LOAD: if(in_valid) begin
                    load_word[load_index[1:0]*LLR_BITS+:LLR_BITS]<=in_llr;
                    if(load_index==511) state<=FETCH;
                    else load_index<=load_index+1'b1;
                end
                FETCH: begin state<=PREP; word_offset<=0; end
                PREP: begin
                    if(op==END_OP) begin state<=IDLE; done<=1; end
                    else if(op==REP_INIT || op==SPC_INIT) begin
                        rep_sum<=0; spc_parity<=0; spc_min<={LLR_BITS+1{1'b1}};
                        spc_addr<=0; spc_lane<=0; pc<=pc+1'b1; state<=FETCH;
                    end else state<=RD1;
                end
                RD1: state<=RD2;
                RD2: begin a_hold<=aq; b_hold<=bq; state<=EXEC; end
                EXEC: begin
                    if(op==REP_ACC) rep_sum<=rep_sum+lane_sum;
                    if(op==SPC_ACC) begin
                        spc_min<=min_next; spc_addr<=min_addr_next;
                        spc_lane<=min_lane_next; spc_parity<=parity_next;
                    end
                    if(op==EXTRACT) begin
                        extract_acc<=(flags[0] ? 1'b0 : extract_acc)^(^(b_hold&mask));
                        if(flags[1]) decoded_info[out_index]<=
                            (flags[0] ? 1'b0 : extract_acc)^(^(b_hold&mask));
                    end
                    if(word_offset+1<run_words) begin
                        word_offset<=word_offset+1'b1; state<=RD1;
                    end else begin pc<=pc+1'b1; state<=FETCH; end
                end
                default: state<=IDLE;
            endcase
        end
    end
endmodule
