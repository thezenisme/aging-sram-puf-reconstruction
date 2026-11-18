`timescale 1ns/1ps
module tb_stream;
    parameter integer N=4096,K=2048,Z=128,BASE_EDGES=123,MAX_ROW_DEGREE=8;
    parameter integer FRAMES=10;
    parameter MATRIX_DIR="generated/n4096", VECTOR_DIR="build/n4096/vectors";
    localparam WORDS=K/64, WORD_AW=$clog2(WORDS), E=BASE_EDGES*Z;
    reg clk=0;
    always #5 clk=~clk;
    reg rst=1,start=0,in_valid=0,out_ready=1;
    reg [7:0] maxiter=1;
    reg signed [7:0] in_llr=0;
    wire ready,input_ready,busy,done,fail,out_valid,out_last;
    wire [7:0] iter_count;
    wire [WORD_AW-1:0] out_index;
    wire [63:0] out_word;
    proposed_formal_stream #(.N(N),.K(K),.Z(Z),.BASE_EDGES(BASE_EDGES),
      .MAX_ROW_DEGREE(MAX_ROW_DEGREE),.MATRIX_DIR(MATRIX_DIR)) dut(.*);
`ifdef LOCKSTEP
    wire old_ready,old_input_ready,old_busy,old_done,old_fail,old_out_valid,old_out_last;
    wire [7:0] old_iter_count;
    wire [4:0] old_out_index;
    wire [63:0] old_out_word;
    proposed_formal_stream_legacy legacy(.clk(clk),.rst(rst),.start(start),
      .maxiter(maxiter),.in_valid(in_valid),.in_llr(in_llr),.out_ready(out_ready),
      .ready(old_ready),.input_ready(old_input_ready),.busy(old_busy),
      .done(old_done),.fail(old_fail),.iter_count(old_iter_count),
      .out_valid(old_out_valid),.out_last(old_out_last),.out_index(old_out_index),.out_word(old_out_word));
    integer lockstep_ticks=0;
    always @(posedge clk) if(!rst) begin
        lockstep_ticks=lockstep_ticks+1;
        if({ready,input_ready,busy,done,fail,iter_count,out_valid,out_last,out_index,out_word}
          !=={old_ready,old_input_ready,old_busy,old_done,old_fail,old_iter_count,
              old_out_valid,old_out_last,old_out_index,old_out_word})
            $fatal(1,"Production interface lockstep mismatch tick=%0d",tick);
        if({dut.core.state,dut.core.index,dut.core.row,dut.core.edge_index,
            dut.core.message_address,dut.core.message_read_enable,dut.core.message_read_address,
            dut.core.var_write,dut.core.var_write_address,dut.core.var_write_data,
            dut.core.message_write,dut.core.message_write_address,dut.core.message_write_data}
          !=={legacy.core.state,legacy.core.index,legacy.core.row,legacy.core.edge_index,
            legacy.core.message_address,legacy.core.message_read_enable,legacy.core.message_read_address,
            legacy.core.var_write,legacy.core.var_write_address,legacy.core.var_write_data,
            legacy.core.message_write,legacy.core.message_write_address,legacy.core.message_write_data})
            $fatal(1,"Production datapath lockstep mismatch tick=%0d",tick);
    end
`endif
    reg [7:0] inputs[0:FRAMES*N-1];
    reg [K-1:0] expected[0:FRAMES-1];
    reg [N-1:0] full_expected[0:FRAMES-1];
    reg [23:0] meta[0:FRAMES-1];
    reg [K-1:0] received;
    integer frame=0,sent=0,accepted=0,words=0,tick=0,start_tick=-1;
    integer load_cycles=0,clear_cycles=0,cn_cycles=0,vn_cycles=0;
    integer check_cycles=0,output_cycles=0,finish_cycles=0;
    integer stall_mode=0,frames_to_run=FRAMES;
    reg measured=0;
    reg held=0;
    reg [63:0] held_word;
    reg [WORD_AW-1:0] held_index;
    reg held_last;
    always @(posedge clk) if(!rst) begin
        tick=tick+1;
        if(start && ready) begin
            start_tick=tick;accepted=0;words=0;received=0;measured=0;
            load_cycles=0;clear_cycles=0;cn_cycles=0;vn_cycles=0;
            check_cycles=0;output_cycles=0;finish_cycles=0;
        end
        if(held && {out_valid,out_word,out_index,out_last} !== {1'b1,held_word,held_index,held_last})
            $fatal(1,"Output changed under backpressure");
        held=out_valid && !out_ready;
        held_word=out_word;held_index=out_index;held_last=out_last;
        if(start_tick>=0 && !measured) begin
            case(dut.core.state)
              1:load_cycles=load_cycles+1;
              2:clear_cycles=clear_cycles+1;
              3,4:cn_cycles=cn_cycles+1;
              5,6:vn_cycles=vn_cycles+1;
              7:check_cycles=check_cycles+1;
              8,9:output_cycles=output_cycles+1;
              10:finish_cycles=finish_cycles+1;
            endcase
            if(in_valid && input_ready) accepted=accepted+1;
            if(out_valid && out_ready) begin
                if(words>=WORDS || out_index!==words[WORD_AW-1:0] || out_last!==(words==WORDS-1))
                    $fatal(1,"Output protocol frame=%0d word=%0d",frame,words);
                if(out_word!==expected[frame][words*64 +:64])
                    $fatal(1,"Output differs from independent reference frame=%0d word=%0d",frame,words);
                received[words*64 +:64]=out_word;
                words=words+1;
            end
            #0.001;
            if(done) begin
                if(accepted!=N || words!=WORDS || received!==expected[frame]) $fatal(1,"Incomplete frame");
                if(iter_count!==meta[frame][7:0] || fail!==meta[frame][8])
                    $fatal(1,"Iteration/failure mismatch frame=%0d got=%0d/%0d expected=%0d/%0d",frame,
                           iter_count,fail,meta[frame][7:0],meta[frame][8]);
                for(integer j=0;j<N;j=j+1)
                    if(dut.core.var_store.mem[j][4]!==full_expected[frame][j]) $fatal(1,"Full codeword mismatch bit=%0d",j);
                if(cn_cycles!=2*E*iter_count || vn_cycles!=(N+E)*iter_count || clear_cycles!=E)
                    $fatal(1,"Message update cycle count mismatch");
                if(!stall_mode && (load_cycles!=N || output_cycles!=K+WORDS)) $fatal(1,"Interface cycles mismatch");
                if(tick-start_tick!=load_cycles+clear_cycles+cn_cycles+vn_cycles+check_cycles+output_cycles+finish_cycles)
                    $fatal(1,"Cycle breakdown mismatch");
                $display("PASS N=%0d frame=%0d iterations=%0d fail=%0d cycles=%0d input=%0d clear=%0d CN=%0d VN=%0d syndrome=%0d output=%0d finish=%0d",
                    N,frame,iter_count,fail,tick-start_tick,load_cycles,clear_cycles,cn_cycles,vn_cycles,check_cycles,output_cycles,finish_cycles);
                measured=1;
            end
            if(tick-start_tick>30000000) $fatal(1,"Timeout");
        end
    end
    always @(negedge clk) if(stall_mode) out_ready=(tick%7>=3);
    initial begin
        if($test$plusargs("stalls")) stall_mode=1;
        if($value$plusargs("frames=%d",frames_to_run)) begin
            if(frames_to_run<1 || frames_to_run>FRAMES) $fatal(1,"Invalid frame prefix");
        end
        $readmemh({VECTOR_DIR,"/inputs.hex"},inputs);
        $readmemh({VECTOR_DIR,"/expected.hex"},expected);
        $readmemh({VECTOR_DIR,"/full.hex"},full_expected);
        $readmemh({VECTOR_DIR,"/meta.hex"},meta);
        repeat(5) @(negedge clk);rst=0;
        // Abort a partially loaded frame; ensure reset restores the interface.
        start=1; @(negedge clk);start=0;
        repeat(11) begin in_valid=1;in_llr=-128;@(negedge clk);end
        rst=1;in_valid=0;@(negedge clk);rst=0;@(negedge clk);
        start_tick=-1;held=0;
        if(!ready || busy || out_valid) $fatal(1,"Reset recovery failed");
        for(frame=0;frame<frames_to_run;frame=frame+1) begin
            while(!ready) @(negedge clk);
            maxiter=meta[frame][23:16];start=1;
            @(negedge clk);start=0;
            for(sent=0;sent<N;sent=sent+1) begin
                if(stall_mode && sent%13==0) begin in_valid=0;repeat(2) @(negedge clk);end
                while(!input_ready) @(negedge clk);
                in_valid=1;in_llr=inputs[frame*N+sent];@(negedge clk);
            end
            in_valid=0;in_llr=0;
            while(!measured) @(negedge clk);
            @(negedge clk);
        end
`ifdef LOCKSTEP
        $display("LOCKSTEP_PASS ticks=%0d",lockstep_ticks);
`endif
        $display("ALL_PASS N=%0d frames=%0d stalls=%0d reset_abort=PASS",N,frames_to_run,stall_mode);
        $finish;
    end
endmodule
