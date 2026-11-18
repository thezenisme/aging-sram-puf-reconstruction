`timescale 1ns/1ps
module tb_compare;
    parameter integer Q=8, FAST=1, BASELINE=0;
    reg clk=0; always #5 clk=~clk;
    reg rst=1,start=0,in_valid=0;
    reg signed [Q-1:0] in_llr=0;
    wire ready,done; wire [63:0] decoded_info;
    reg [Q-1:0] stimuli[0:512*512-1];
    reg [63:0] expected[0:511];
    reg [2047:0] stimulus_path,expected_path;
    integer frames,frame,i,cycles,ref_cycles,total_cycles;
`ifdef SYNTH_NETLIST
    polar_sc_kestel dut(.*);
`else
    generate if(BASELINE) begin
        polar_sc_core #(.LLR_BITS(Q)) dut(.*);
    end else begin
        polar_sc_kestel #(.LLR_BITS(Q),.FAST(FAST),
            .ROM_DEPTH(FAST ? 512 : 1024)) dut(.*);
    end endgenerate
`endif
    initial begin
`ifdef SYNTH_NETLIST
        stimulus_path="input.hex"; expected_path="expected.hex"; frames=8;
`else
        if(!$value$plusargs("stimuli=%s",stimulus_path) ||
           !$value$plusargs("expected=%s",expected_path) ||
           !$value$plusargs("frames=%d",frames)) $fatal(1,"Missing paths");
`endif
        $readmemh(stimulus_path,stimuli,0,frames*512-1);
        $readmemh(expected_path,expected,0,frames-1);
        repeat(20) @(negedge clk); rst=0;
        // Abandon a partial load; stale memory must not affect next frame.
        start=1; @(negedge clk); start=0; in_valid=1;
        repeat(13) @(negedge clk); rst=1; in_valid=0;
        @(negedge clk); rst=0; ref_cycles=0; total_cycles=0;
        for(frame=0;frame<frames;frame=frame+1) begin
            if(!ready) $fatal(1,"Not ready");
            start=1; @(negedge clk); start=0;
            for(i=0;i<512;i=i+1) begin
                if(i%29==0) begin in_valid=0; @(negedge clk); end
                in_valid=1; in_llr=stimuli[frame*512+i]; @(negedge clk);
            end
            in_valid=0; cycles=0;
            while(!done && cycles<30000) begin @(negedge clk); cycles=cycles+1; end
            if(!done) $fatal(1,"Timeout frame %0d",frame);
            if(decoded_info !== expected[frame])
                $fatal(1,"Frame %0d actual %h expected %h",frame,decoded_info,expected[frame]);
            if(frame==0) ref_cycles=cycles;
            else if(cycles!=ref_cycles) $fatal(1,"Data-dependent cycle count");
            total_cycles=total_cycles+cycles;
            @(negedge clk); if(done) $fatal(1,"Done not a pulse");
        end
        $display("PASS frames=%0d Q=%0d fast=%0d baseline=%0d decode_cycles=%0d",
            frames,Q,FAST,BASELINE,ref_cycles); $finish;
    end
endmodule
