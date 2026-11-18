`timescale 1ns/1ps
`include "netlist_config.vh"
module tb_netlist;
    localparam N=`CODE_N, K=`CODE_K, WORDS=K/64, WORD_AW=$clog2(WORDS), FRAMES=3;
    reg clk=0;
    always #5 clk=~clk;
    reg rst=1,start=0,in_valid=0,out_ready=1;
    reg [7:0] maxiter=1;
    reg signed [7:0] in_llr=0;
    wire ready,input_ready,busy,done,fail,out_valid,out_last;
    wire [7:0] iter_count;
    wire [WORD_AW-1:0] out_index;
    wire [63:0] out_word;
    `CODE_TOP dut(.*);
    reg [7:0] inputs[0:FRAMES*N-1];
    reg [K-1:0] expected[0:FRAMES-1];
    reg [23:0] meta[0:FRAMES-1];
    reg [31:0] expected_cycles[0:FRAMES-1];
    integer frame=0,sent=0,accepted=0,words=0,tick=0,start_tick=-1;
    reg measured=0;
    always @(posedge clk) if(!rst) begin
        tick=tick+1;
        if(start && ready) begin start_tick=tick;accepted=0;words=0;measured=0;end
        if(start_tick>=0 && !measured) begin
            if(in_valid && input_ready) accepted=accepted+1;
            if(out_valid && out_ready) begin
                if(words>=WORDS || out_index!==words[WORD_AW-1:0] || out_last!==(words==WORDS-1))
                    $fatal(1,"Netlist output protocol mismatch");
                if(out_word!==expected[frame][words*64 +:64])
                    $fatal(1,"Netlist output data mismatch frame=%0d word=%0d",frame,words);
                words=words+1;
            end
            // UNISIM FDRE exposes Q 100 ps after the edge. Observe DONE
            // after settling on this same edge, without adding a clock cycle.
            #1;
            if(done) begin
                if(accepted!=N || words!=WORDS || iter_count!==meta[frame][7:0] || fail!==meta[frame][8])
                    $fatal(1,"Netlist frame/iteration/failure mismatch");
                if(tick-start_tick!=expected_cycles[frame])
                    $fatal(1,"Netlist cycle mismatch got=%0d expected=%0d",tick-start_tick,expected_cycles[frame]);
                $display("NETLIST_PASS N=%0d frame=%0d iterations=%0d fail=%0d cycles=%0d",N,frame,iter_count,fail,tick-start_tick);
                measured=1;
            end
            if(tick-start_tick>1000000) $fatal(1,"Netlist simulation timeout");
        end
    end
    initial begin
        $readmemh("inputs.hex",inputs);
        $readmemh("expected.hex",expected);
        $readmemh("meta.hex",meta);
        $readmemh("cycles.hex",expected_cycles);
        // Wait beyond the 100 ns UNISIM global reset.
        repeat(25) @(negedge clk);rst=0;
        for(frame=0;frame<FRAMES;frame=frame+1) begin
            @(negedge clk);while(!ready) @(negedge clk);
            start=1;maxiter=meta[frame][23:16];@(negedge clk);start=0;
            for(sent=0;sent<N;sent=sent+1) begin
                while(!input_ready) @(negedge clk);
                in_valid=1;in_llr=inputs[frame*N+sent];@(negedge clk);
            end
            in_valid=0;in_llr=0;
            while(!measured) @(negedge clk);
        end
        $display("NETLIST_ALL_PASS N=%0d frames=%0d",N,FRAMES);
        $finish;
    end
endmodule
