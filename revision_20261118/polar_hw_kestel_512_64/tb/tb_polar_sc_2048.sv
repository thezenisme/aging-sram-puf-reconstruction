module tb_polar_sc_2048;
    parameter integer FAST=1;
    localparam integer N = 512;
    localparam integer BLOCKS = 32;
    reg clk = 0;
    always #5 clk = ~clk;
    reg rst = 1;
    reg start = 0;
    reg in_valid = 0;
    reg signed [7:0] in_llr = 0;
    wire ready, input_ready, done;
    wire [2047:0] decoded_info;
    reg [7:0] stimuli [0:BLOCKS*N-1];
    reg [63:0] expected [0:BLOCKS-1];
    reg [1023:0] stimulus_path, expected_path;
    integer index, cycles;

    polar_sc_2048 #(.FAST(FAST)) dut (
        .clk(clk), .rst(rst), .start(start), .ready(ready),
        .input_ready(input_ready), .in_valid(in_valid), .in_llr(in_llr),
        .done(done), .decoded_info(decoded_info)
    );

    initial begin
        if (!$value$plusargs("stimuli=%s", stimulus_path) ||
            !$value$plusargs("expected=%s", expected_path))
            $fatal(1, "Provide +stimuli=PATH and +expected=PATH");
        $readmemh(stimulus_path, stimuli);
        $readmemh(expected_path, expected);
        repeat (4) @(negedge clk);
        rst = 0;
        if (!ready) $fatal(1, "Wrapper not ready");
        start = 1;
        @(negedge clk);
        start = 0;
        index = 0;
        cycles = 0;
        while (!done && cycles < 400000) begin
            if (input_ready && index < BLOCKS*N) begin
                in_valid = 1;
                in_llr = stimuli[index];
                index = index + 1;
            end else begin
                in_valid = 0;
            end
            @(negedge clk);
            cycles = cycles + 1;
        end
        if (!done) $fatal(1, "Wrapper timed out after %0d inputs", index);
        if (index != BLOCKS*N)
            $fatal(1, "Consumed %0d inputs, expected %0d", index, BLOCKS*N);
        for (integer block = 0; block < BLOCKS; block = block + 1)
            if (decoded_info[block*64 +: 64] !== expected[block])
                $fatal(1, "Block %0d: got %h, expected %h", block,
                       decoded_info[block*64 +: 64], expected[block]);
        $display("PASS: 32 sequential blocks match reference in %0d cycles", cycles);
        $finish;
    end
endmodule
