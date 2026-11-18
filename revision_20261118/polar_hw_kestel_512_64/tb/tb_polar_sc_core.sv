module tb_polar_sc_core;
    localparam integer N = 512;
    localparam integer K = 64;
    localparam integer FRAMES = 8;
    reg clk = 0;
    always #5 clk = ~clk;
    reg rst = 1;
    reg start = 0;
    reg in_valid = 0;
    reg signed [7:0] in_llr = 0;
    wire ready, done;
    wire [K-1:0] decoded_info;
    reg [7:0] stimuli [0:FRAMES*N-1];
    reg [K-1:0] expected [0:FRAMES-1];
    reg [1023:0] stimulus_path, expected_path;
    integer frame, i, timeout;

    polar_sc_core dut (
        .clk(clk), .rst(rst), .start(start), .ready(ready),
        .in_valid(in_valid), .in_llr(in_llr), .done(done),
        .decoded_info(decoded_info)
    );

    initial begin
        if (!$value$plusargs("stimuli=%s", stimulus_path) ||
            !$value$plusargs("expected=%s", expected_path))
            $fatal(1, "Provide +stimuli=PATH and +expected=PATH");
        $readmemh(stimulus_path, stimuli);
        $readmemh(expected_path, expected);
        repeat (4) @(negedge clk);
        rst = 0;
        for (frame = 0; frame < FRAMES; frame = frame + 1) begin
            if (!ready) $fatal(1, "Not ready at frame %0d", frame);
            start = 1;
            @(negedge clk);
            start = 0;
            for (i = 0; i < N; i = i + 1) begin
                in_valid = 1;
                in_llr = stimuli[frame*N+i];
                @(negedge clk);
            end
            in_valid = 0;
            timeout = 0;
            while (!done && timeout < 10000) begin
                @(negedge clk);
                timeout = timeout + 1;
            end
            if (!done) $fatal(1, "Decoder timeout on frame %0d", frame);
            if (decoded_info !== expected[frame])
                $fatal(1, "Frame %0d: got %h, expected %h", frame,
                       decoded_info, expected[frame]);
            @(negedge clk);
        end
        $display("PASS: %0d frames match independent min-sum SC reference", FRAMES);
        $finish;
    end
endmodule
