`timescale 1ns/1ps

module tb_turbo_compare;
    parameter real CLK_PERIOD_NS = 10.0;
    logic CLK = 1'b0;
    always #(CLK_PERIOD_NS/2.0) CLK = ~CLK;

    logic RST = 1'b1;
    logic START = 1'b0;
    logic IN_VALID = 1'b0;
    logic signed [7:0] IN_LLR = '0;
    wire READY, INPUT_READY, BUSY, DONE;
    wire [2047:0] DECODED_INFO;

    turbo_lte_4096_2048_compare_top dut (
        .CLK(CLK), .RST(RST), .START(START), .READY(READY),
        .INPUT_READY(INPUT_READY), .IN_VALID(IN_VALID), .IN_LLR(IN_LLR),
        .BUSY(BUSY), .DONE(DONE), .DECODED_INFO(DECODED_INFO)
    );

    integer input_index = 0;
    integer cycle_count = 0;
    integer output_count = 0;
    integer feed_count = 0;
    integer decoder_count = 0;
    integer interleaver_count = 0;
    integer qpp_write_count = 0;
    integer llr_write_count = 0;
    integer alpha_write_count = 0;
    integer first_bad_llr_write = -1;
    integer first_bad_alpha_write = -1;
    integer mismatch_count;
    integer unknown_count;
    logic [2047:0] observed_bits = '0;
    logic [7:0] stimulus [0:4095];
    logic [2047:0] expected_bits = '0;
    logic [2047:0] expected_word [0:0];
    bit have_expected = 0;
    string vector_prefix;
    string vector_llr_file;
    string vector_payload_file;

    // Count elapsed rising-edge intervals, not time since reset release.
    integer latency_edge = 0;
    integer start_edge = -1;
    integer first_input_edge = -1;
    integer last_input_edge = -1;
    integer first_core_edge = -1;
    integer accepted_inputs = 0;
    bit latency_reported = 0;
    always @(posedge CLK) begin
        if (RST) begin
            latency_edge = 0;
            start_edge = -1;
            first_input_edge = -1;
            last_input_edge = -1;
            first_core_edge = -1;
            accepted_inputs = 0;
            latency_reported = 0;
        end else begin
            latency_edge = latency_edge + 1;
            if (START && READY) start_edge = latency_edge;
            if (IN_VALID && INPUT_READY) begin
                if (first_input_edge < 0) first_input_edge = latency_edge;
                last_input_edge = latency_edge;
                accepted_inputs = accepted_inputs + 1;
            end
            if (dut.core_dvi && first_core_edge < 0)
                first_core_edge = latency_edge;
            // Observe DONE and output register after nonblocking assignments.
            #0.001;
            if (DONE && !latency_reported) begin
                if (start_edge < 0 || accepted_inputs != 4096 || first_core_edge < 0)
                    $fatal(1, "invalid latency measurement endpoints");
                if (DECODED_INFO !== expected_bits)
                    $fatal(1, "final output register differs from expected payload");
                $display("TURBO_LATENCY_CONFIG input_llr_bits=5 output_bits=2048 inputs=4096 iterations=10 period_ns=%0.3f", CLK_PERIOD_NS);
                $display("TURBO_LATENCY start_to_done=%0d clk first_input_to_done=%0d clk last_input_to_done=%0d clk core_first_input_to_done=%0d clk",
                    latency_edge-start_edge, latency_edge-first_input_edge,
                    latency_edge-last_input_edge, latency_edge-first_core_edge);
                $display("TURBO_LATENCY_INPUT accepted=%0d input_transfer_cycles=%0d final_payload=PASS",
                    accepted_inputs, last_input_edge-first_input_edge+1);
                latency_reported = 1;
            end
        end
    end

    initial begin
`ifdef TB_VECTOR_ZEROS
        vector_prefix = "turbo_zeros";
`elsif TB_VECTOR_ONES
        vector_prefix = "turbo_ones";
`elsif TB_VECTOR_SEED19
        vector_prefix = "turbo_seed19";
`else
        vector_prefix = "turbo_noiseless";
`endif
        vector_llr_file = {"generated/", vector_prefix, "_llr.mem"};
        vector_payload_file = {"generated/", vector_prefix, "_payload.mem"};
        $readmemh(vector_llr_file, stimulus);
        $readmemh(vector_payload_file, expected_word);
        expected_bits = expected_word[0];
        have_expected = 1;

        repeat (5) @(negedge CLK);
        RST = 1'b0;
        @(negedge CLK);
        START = 1'b1;
        @(negedge CLK);
        START = 1'b0;
    end

    always @(negedge CLK) begin
        if (!RST && INPUT_READY && input_index < 4096) begin
            IN_VALID = 1'b1;
            IN_LLR = stimulus[input_index];
            input_index = input_index + 1;
        end else begin
            IN_VALID = 1'b0;
        end
    end

    always @(posedge CLK) begin
        if (!RST) begin
            cycle_count <= cycle_count + 1;
            if (dut.core.lte_interleaver_inst.s_w_dvi) begin
                if (qpp_write_count < 6 || qpp_write_count == 100 || qpp_write_count >= 2044)
                    $display("QPP_WRITE idx=%0d addr=%h data=%h div=%h",
                             qpp_write_count, dut.core.lte_interleaver_inst.s_w_addr,
                             dut.core.lte_interleaver_inst.s_w_di,
                             dut.core.lte_interleaver_inst.div_fractional);
                qpp_write_count <= qpp_write_count + 1;
            end
            if (dut.core.bcjr_turbo_decoder_inst.sram_llrs_w_dvi) begin
                if (llr_write_count < 4 || llr_write_count >= 2047 && llr_write_count <= 2054 ||
                    ((^dut.core.bcjr_turbo_decoder_inst.sram_llrs_w_di) === 1'bx &&
                     first_bad_llr_write < 0)) begin
                    $display("LLR_WRITE idx=%0d addr=%h data=%h dvi=%b delayed=%h,%h",
                             llr_write_count,
                             dut.core.bcjr_turbo_decoder_inst.sram_llrs_addr_1,
                             dut.core.bcjr_turbo_decoder_inst.sram_llrs_w_di,
                             dut.core.bcjr_turbo_decoder_inst.d_dvi,
                             dut.core.bcjr_turbo_decoder_inst.d_di0,
                             dut.core.bcjr_turbo_decoder_inst.d_di1);
                end
                if ((^dut.core.bcjr_turbo_decoder_inst.sram_llrs_w_di) === 1'bx &&
                    first_bad_llr_write < 0)
                    first_bad_llr_write <= llr_write_count;
                llr_write_count <= llr_write_count + 1;
            end
            if (dut.core.bcjr_turbo_decoder_inst.alphas_w_dvi) begin
                if (alpha_write_count < 4 || alpha_write_count >= 2047 && alpha_write_count <= 2056 ||
                    ((^dut.core.bcjr_turbo_decoder_inst.alphas_w_di) === 1'bx &&
                     first_bad_alpha_write < 0))
                    $display("ALPHA_WRITE idx=%0d addr=%h data=%h stage=%h work=%h llrA=%h llrB=%h",
                             alpha_write_count,
                             dut.core.bcjr_turbo_decoder_inst.alphas_w_addr,
                             dut.core.bcjr_turbo_decoder_inst.alphas_w_di,
                             dut.core.bcjr_turbo_decoder_inst.stage,
                             dut.core.bcjr_turbo_decoder_inst.work_circle,
                             dut.core.bcjr_turbo_decoder_inst.sram_llrs_r1_do,
                             dut.core.bcjr_turbo_decoder_inst.sram_llrs_r2_do);
                if ((^dut.core.bcjr_turbo_decoder_inst.alphas_w_di) === 1'bx &&
                    first_bad_alpha_write < 0)
                    first_bad_alpha_write <= alpha_write_count;
                alpha_write_count <= alpha_write_count + 1;
            end
            if (dut.core_dvi) begin
                if (feed_count < 4 || feed_count >= 2048)
                    $display("FEED idx=%0d q=%h,%h,%h", feed_count, dut.stream0_q, dut.stream1_q, dut.stream2_q);
                feed_count <= feed_count + 1;
            end
            if (dut.core.decoder_dvo) begin
                if (decoder_count < 4)
                    $display("BCJR idx=%0d out=%h di0=%h di1=%h llr=%h,%h alpha=%h beta=%h prob=%h,%h",
                             decoder_count, dut.core.decoder_do, dut.core.decoder_di0,
                             dut.core.decoder_di1, dut.core.bcjr_turbo_decoder_inst.sram_llrs_r1_do,
                             dut.core.bcjr_turbo_decoder_inst.sram_llrs_r2_do,
                             dut.core.bcjr_turbo_decoder_inst.alphas_r_do,
                             dut.core.bcjr_turbo_decoder_inst.betas_r_do,
                             dut.core.bcjr_turbo_decoder_inst.prob0,
                             dut.core.bcjr_turbo_decoder_inst.prob1);
                decoder_count <= decoder_count + 1;
            end
            if (dut.core.interleaver_dvo) begin
                if (interleaver_count < 6 || interleaver_count == 100 || interleaver_count == 1000)
                    $display("INTERLEAVER idx=%0d out=%h,%h table=%h", interleaver_count,
                             dut.core.interleaver_do_0, dut.core.interleaver_do_1,
                             dut.core.lte_interleaver_inst.s_r_do);
                interleaver_count <= interleaver_count + 1;
            end
            if (dut.core_dvo) begin
                if (output_count < 4)
                    $display("OUTPUT idx=%0d bit=%b ap=%h apt=%h sram=%h b1=%h b2=%h i0=%h i1=%h",
                             output_count, dut.core_do, dut.core.a_p, dut.core.a_p_tmp,
                             dut.core.sram_a_c_r_do, dut.core.decoder_1_do, dut.core.decoder_2_do,
                             dut.core.interleaver_do_0, dut.core.interleaver_do_1);
                if (output_count >= 2048) $fatal(1, "more than 2048 output bits");
                observed_bits[output_count] <= dut.core_do;
                output_count <= output_count + 1;
            end
            if (DONE) begin
                if (input_index != 4096 || output_count != 2048)
                    $fatal(1, "wrong counts: inputs=%0d outputs=%0d", input_index, output_count);
                if (have_expected && observed_bits !== expected_bits) begin
                    mismatch_count = 0;
                    unknown_count = 0;
                    for (integer j = 0; j < 2048; j++) begin
                        if (observed_bits[j] !== 1'b0 && observed_bits[j] !== 1'b1)
                            unknown_count = unknown_count + 1;
                        if (observed_bits[j] !== expected_bits[j])
                            mismatch_count = mismatch_count + 1;
                    end
                    $display("TURBO_COMPARE_MISMATCH count=%0d unknown=%0d observed_low=%h expected_low=%h",
                             mismatch_count, unknown_count, observed_bits[63:0], expected_bits[63:0]);
                    $fatal(1, "decoded bits differ from reference");
                end
                $display("TURBO_COMPARE_PASS cycles=%0d inputs=%0d outputs=%0d",
                         cycle_count, input_index, output_count);
                $finish;
            end
            if (cycle_count >= 1500000)
                $fatal(1, "timeout: inputs=%0d outputs=%0d state=%0d core_stage=%0d",
                       input_index, output_count, dut.state, dut.core.stage);
        end
    end
endmodule
