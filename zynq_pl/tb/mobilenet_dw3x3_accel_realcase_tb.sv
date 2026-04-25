`timescale 1ns/1ps
`include "depthwise_window_case.svh"

module mobilenet_dw3x3_accel_realcase_tb;

    localparam int DATA_W = 16;
    localparam int COEF_W = 16;
    localparam int BIAS_W = 32;
    localparam int ACC_W  = 48;
    localparam int OUT_W  = 32;

    logic clk;
    logic rst_n;
    logic in_valid;
    logic in_ready;
    logic signed [DATA_W-1:0] pixel_window [0:8];
    logic signed [COEF_W-1:0] weight_window [0:8];
    logic signed [BIAS_W-1:0] bias;
    logic out_valid;
    logic out_ready;
    logic signed [OUT_W-1:0] out_data;

    real got_float;
    real golden_float;
    real quantized_float;

    mobilenet_dw3x3_accel #(
        .DATA_W(DATA_W),
        .COEF_W(COEF_W),
        .BIAS_W(BIAS_W),
        .ACC_W(ACC_W),
        .OUT_W(OUT_W),
        .SHIFT(0)
    ) dut (
        .clk(clk),
        .rst_n(rst_n),
        .in_valid(in_valid),
        .in_ready(in_ready),
        .pixel_window(pixel_window),
        .weight_window(weight_window),
        .bias(bias),
        .out_valid(out_valid),
        .out_ready(out_ready),
        .out_data(out_data)
    );

    always #5 clk = ~clk;

    task automatic load_real_case;
        begin
            pixel_window[0] = `DW_CASE_PIXEL_0;
            pixel_window[1] = `DW_CASE_PIXEL_1;
            pixel_window[2] = `DW_CASE_PIXEL_2;
            pixel_window[3] = `DW_CASE_PIXEL_3;
            pixel_window[4] = `DW_CASE_PIXEL_4;
            pixel_window[5] = `DW_CASE_PIXEL_5;
            pixel_window[6] = `DW_CASE_PIXEL_6;
            pixel_window[7] = `DW_CASE_PIXEL_7;
            pixel_window[8] = `DW_CASE_PIXEL_8;

            weight_window[0] = `DW_CASE_WEIGHT_0;
            weight_window[1] = `DW_CASE_WEIGHT_1;
            weight_window[2] = `DW_CASE_WEIGHT_2;
            weight_window[3] = `DW_CASE_WEIGHT_3;
            weight_window[4] = `DW_CASE_WEIGHT_4;
            weight_window[5] = `DW_CASE_WEIGHT_5;
            weight_window[6] = `DW_CASE_WEIGHT_6;
            weight_window[7] = `DW_CASE_WEIGHT_7;
            weight_window[8] = `DW_CASE_WEIGHT_8;
            bias = `DW_CASE_BIAS;
        end
    endtask

    initial begin
        clk = 1'b0;
        rst_n = 1'b0;
        in_valid = 1'b0;
        out_ready = 1'b1;
        bias = '0;
        pixel_window = '{default:'0};
        weight_window = '{default:'0};

        repeat (4) @(posedge clk);
        rst_n <= 1'b1;

        @(posedge clk);
        while (!in_ready) begin
            @(posedge clk);
        end

        load_real_case();
        in_valid <= 1'b1;
        @(posedge clk);
        in_valid <= 1'b0;

        @(posedge clk);
        while (!out_valid) begin
            @(posedge clk);
        end

        if (out_data !== `DW_CASE_EXPECTED_ACC) begin
            $error(
                "Expected acc=%0d but got %0d for channel=%0d y=%0d x=%0d",
                `DW_CASE_EXPECTED_ACC,
                out_data,
                `DW_CASE_CHANNEL,
                `DW_CASE_Y,
                `DW_CASE_X
            );
            $fatal(1);
        end

        got_float = out_data;
        got_float = got_float / `DW_CASE_ACC_SCALE;
        golden_float = `DW_CASE_GOLDEN_FLOAT;
        quantized_float = `DW_CASE_QUANTIZED_FLOAT;

        $display(
            "PASS realcase channel=%0d y=%0d x=%0d acc=%0d dequant=%0f golden=%0f quantized=%0f",
            `DW_CASE_CHANNEL,
            `DW_CASE_Y,
            `DW_CASE_X,
            out_data,
            got_float,
            golden_float,
            quantized_float
        );
        $display("mobilenet_dw3x3_accel_realcase_tb PASS");
        $finish;
    end

endmodule
