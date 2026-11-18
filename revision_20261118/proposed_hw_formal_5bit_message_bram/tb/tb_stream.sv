`timescale 1ns/1ps
module tb_stream;
    reg clk=0; always #5 clk=~clk;
    reg rst=1,start=0,in_valid=0,out_ready=1;
    reg [7:0] maxiter=1; reg signed [7:0] in_llr=0;
    wire ready,input_ready,busy,done,fail,out_valid,out_last;
    wire [7:0] iter_count; wire [4:0] out_index; wire [63:0] out_word;
    proposed_formal_stream dut(.*);
`ifdef LOCKSTEP
    wire b_ready,b_input_ready,b_busy,b_done,b_fail,b_out_valid,b_out_last;
    wire [7:0] b_iter_count; wire [4:0] b_out_index; wire [63:0] b_out_word;
    baseline_formal_stream baseline(
        .clk(clk),.rst(rst),.start(start),.maxiter(maxiter),.in_valid(in_valid),.in_llr(in_llr),
        .out_ready(out_ready),.ready(b_ready),.input_ready(b_input_ready),.busy(b_busy),
        .done(b_done),.fail(b_fail),.iter_count(b_iter_count),.out_valid(b_out_valid),
        .out_last(b_out_last),.out_index(b_out_index),.out_word(b_out_word));
    always @(posedge clk) if(!rst) begin
        if({ready,input_ready,busy,done,fail,iter_count,out_valid,out_last,out_index,out_word}!==
           {b_ready,b_input_ready,b_busy,b_done,b_fail,b_iter_count,b_out_valid,b_out_last,b_out_index,b_out_word})
            $fatal(1,"Lockstep public interface mismatch");
        if({dut.core.state,dut.core.row,dut.core.edge_index,dut.core.index}!==
           {baseline.core.state,baseline.core.row,baseline.core.edge_index,baseline.core.index})
            $fatal(1,"Lockstep schedule mismatch");
        if(dut.core.var_write!==baseline.core.var_write || dut.core.message_write!==baseline.core.message_write)
            $fatal(1,"Lockstep write enable mismatch");
        if(dut.core.var_write && {dut.core.var_write_address,dut.core.var_write_data}!==
                                 {baseline.core.var_write_address,baseline.core.var_write_data})
            $fatal(1,"Lockstep variable write mismatch");
        if(dut.core.message_write && {dut.core.message_write_address,dut.core.message_write_data}!==
                                     {baseline.core.message_write_address,baseline.core.message_write_data})
            $fatal(1,"Lockstep message write mismatch");
        if((dut.core.state==3 || dut.core.state==6) && dut.core.message_read!==baseline.core.message_read)
            $fatal(1,"Lockstep consumed message mismatch");
    end
`endif
    reg [7:0] inputs[0:65535]; reg [2047:0] expected[0:15];
    reg [4095:0] full_expected[0:15];
    reg [23:0] meta[0:15]; integer frames,f,i,c,cycles,words; reg [2047:0] got;
    reg collecting=0,held=0; reg [63:0] held_word;reg [4:0] held_index;reg held_last;
    integer stall_cycles=0,stall_phase=0,no_output_stalls=0;
`ifndef SYNTH_NETLIST
    // Check the synchronous response at every consumed edge, including
    // row, QC-block and iteration boundaries, not just final output bits.
    reg msg_tag_valid=0;
    reg [13:0] msg_tag;
    integer checked_message_reads=0;
    always @(posedge clk) begin
        if(rst) msg_tag_valid<=0;
        else begin
            if(dut.core.state==3 || dut.core.state==6) begin
                if(!msg_tag_valid || msg_tag!==dut.core.message_address)
                    $fatal(1,"BRAM prefetch tag mismatch state=%0d row=%0d edge=%0d",dut.core.state,dut.core.row,dut.core.edge_index);
                if(dut.core.message_read!==dut.core.message_store.mem[dut.core.message_address])
                    $fatal(1,"BRAM stale or wrong response address=%0d",dut.core.message_address);
                checked_message_reads=checked_message_reads+1;
            end
            if(dut.core.message_read_enable) begin
                if(dut.core.message_read_address>=15744) $fatal(1,"BRAM read out of range");
                if(dut.core.message_write && dut.core.message_read_address==dut.core.message_write_address)
                    $fatal(1,"BRAM read/write collision");
                msg_tag<=dut.core.message_read_address;
                msg_tag_valid<=1;
            end
        end
    end
`endif
    always @(posedge clk) begin
        if(rst) held=0;
        else begin
            if(held && (!out_valid || out_word!==held_word || out_index!==held_index || out_last!==held_last))
                $fatal(1,"Output changed while stalled");
            if(collecting && out_valid && out_ready) begin
                if(words>=32 || out_index!==words[4:0]) $fatal(1,"word index");
                if(out_last!==(words==31)) $fatal(1,"last flag");
                if(out_word!==expected[f][words*64 +:64]) $fatal(1,"word mismatch f=%0d word=%0d",f,words);
                got[words*64 +:64]=out_word; words=words+1;
            end
            held=out_valid && !out_ready;
            held_word=out_word;held_index=out_index;held_last=out_last;
        end
    end
    initial begin
        if($test$plusargs("no_output_stalls")) no_output_stalls=1;
`ifdef SYNTH_NETLIST
        frames=3;
        $readmemh("build/netlist_vectors/inputs.hex",inputs,0,frames*4096-1);
        $readmemh("build/netlist_vectors/expected.hex",expected,0,frames-1);
        $readmemh("build/netlist_vectors/meta.hex",meta,0,frames-1);
`else
        if(!$value$plusargs("frames=%d",frames)) frames=12;
        $readmemh("build/verification/inputs.hex",inputs,0,frames*4096-1);
        $readmemh("build/verification/expected.hex",expected,0,frames-1);
        $readmemh("build/verification/meta.hex",meta,0,frames-1);
        $readmemh("build/verification/full.hex",full_expected,0,frames-1);
`endif
        repeat(20) @(negedge clk); rst=0;
        // Aborted loading and an aborted CN pass must not leak stale RAM data.
        start=1;@(negedge clk);start=0;
        repeat(17) begin in_valid=1;in_llr=-35;@(negedge clk);end
        rst=1;in_valid=0;repeat(3) @(negedge clk);rst=0;
        start=1;@(negedge clk);start=0;
        for(i=0;i<4096;i=i+1) begin in_valid=1;in_llr=35;@(negedge clk);end
        in_valid=0;repeat(15800) @(negedge clk);
        if(!busy || done) $fatal(1,"Unexpected state before abort");
        rst=1;repeat(3) @(negedge clk);rst=0;
        for(f=0;f<frames;f=f+1) begin
            while(!ready) @(negedge clk);
            maxiter=meta[f][23:16]; start=1; @(negedge clk); start=0;
            i=0; cycles=0; words=0; got=0;collecting=1;stall_cycles=0;stall_phase=0;
            while(!done && cycles<30000000) begin
                if(input_ready && i<4096 && cycles%19!=7) begin in_valid=1;in_llr=inputs[f*4096+i];i=i+1;end
                else begin in_valid=0;in_llr=0;end
                if(i==4096) maxiter=1;
                // Long stalls on first and last word exercise valid/data
                // retention and ensure done waits for final acceptance.
                out_ready=1;
                if(!no_output_stalls) begin
                    out_ready=(cycles%7!=2);
                    if(stall_phase==0 && out_valid) begin stall_cycles=25;stall_phase=1;end
                    if(stall_phase==1 && out_valid && out_last) begin stall_cycles=25;stall_phase=2;end
                    if(stall_cycles>0) begin out_ready=0;stall_cycles=stall_cycles-1;end
                end
                @(negedge clk); cycles=cycles+1;
                if(done && words!=32) $fatal(1,"done before last acceptance");
            end
            if(!done || i!=4096 || words!=32) $fatal(1,"completion f=%0d i=%0d words=%0d",f,i,words);
            if(got!==expected[f]) $fatal(1,"output mismatch f=%0d",f);
            if(iter_count!==meta[f][7:0] || fail!==meta[f][8]) $fatal(1,"status mismatch f=%0d",f);
`ifndef SYNTH_NETLIST
            for(c=0;c<4096;c=c+1)
                if(dut.core.var_store.mem[c][4]!==full_expected[f][c]) $fatal(1,"full output mismatch f=%0d c=%0d",f,c);
`endif
            $display("PASS frame=%0d iterations=%0d fail=%0d words=%0d cycles=%0d",f,iter_count,fail,words,cycles);
            collecting=0;in_valid=0;out_ready=1;repeat(3) @(negedge clk);
            if(done || out_valid) $fatal(1,"pulse completion");
        end
`ifndef SYNTH_NETLIST
        $display("PREFETCH_PASS reads=%0d",checked_message_reads);
`endif
`ifdef LOCKSTEP
        $display("LOCKSTEP_PASS frames=%0d",frames);
`endif
        $display("ALL_PASS frames=%0d",frames); $finish;
    end
endmodule
