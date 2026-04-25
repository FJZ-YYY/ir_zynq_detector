`timescale 1ns/1ps

module mobilenet_dw3x3_accel_tb;

    localparam int DATA_W = 16;
    localparam int COEF_W = 16;
    localparam int BIAS_W = 32;
    localparam int ACC_W  = 48;
    localparam int OUT_W  = 16;

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

    task automatic drive_case(
        input logic signed [DATA_W-1:0] p0,
        input logic signed [DATA_W-1:0] p1,
        input logic signed [DATA_W-1:0] p2,
        input logic signed [DATA_W-1:0] p3,
        input logic signed [DATA_W-1:0] p4,
        input logic signed [DATA_W-1:0] p5,
        input logic signed [DATA_W-1:0] p6,
        input logic signed [DATA_W-1:0] p7,
        input logic signed [DATA_W-1:0] p8,
        input logic signed [COEF_W-1:0] w0,
        input logic signed [COEF_W-1:0] w1,
        input logic signed [COEF_W-1:0] w2,
        input logic signed [COEF_W-1:0] w3,
        input logic signed [COEF_W-1:0] w4,
        input logic signed [COEF_W-1:0] w5,
        input logic signed [COEF_W-1:0] w6,
        input logic signed [COEF_W-1:0] w7,
        input logic signed [COEF_W-1:0] w8,
        input logic signed [BIAS_W-1:0] b
    );
        begin
            @(posedge clk);
            while (!in_ready) begin
                @(posedge clk);
            end
            pixel_window[0] <= p0;
            pixel_window[1] <= p1;
            pixel_window[2] <= p2;
            pixel_window[3] <= p3;
            pixel_window[4] <= p4;
            pixel_window[5] <= p5;
            pixel_window[6] <= p6;
            pixel_window[7] <= p7;
            pixel_window[8] <= p8;
            weight_window[0] <= w0;
            weight_window[1] <= w1;
            weight_window[2] <= w2;
            weight_window[3] <= w3;
            weight_window[4] <= w4;
            weight_window[5] <= w5;
            weight_window[6] <= w6;
            weight_window[7] <= w7;
            weight_window[8] <= w8;
            bias <= b;
            in_valid <= 1'b1;
            @(posedge clk);
            in_valid <= 1'b0;
        end
    endtask

    task automatic expect_output(input logic signed [OUT_W-1:0] expected);
        begin
            @(posedge clk);
            while (!out_valid) begin
                @(posedge clk);
            end
            if (out_data !== expected) begin
                $error("Expected out_data=%0d but got %0d", expected, out_data);
                $fatal(1);
            end
            $display("PASS out_data=%0d", out_data);
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

        // Case-1: sum(1..9) = 45
        drive_case(
            16'sd1, 16'sd2, 16'sd3,
            16'sd4, 16'sd5, 16'sd6,
            16'sd7, 16'sd8, 16'sd9,
            16'sd1, 16'sd1, 16'sd1,
            16'sd1, 16'sd1, 16'sd1,
            16'sd1, 16'sd1, 16'sd1,
            32'sd0
        );
        expect_output(16'sd45);

        // Case-2: signed accumulation with bias.
        drive_case(
            16'sd10, 16'sd0, 16'sd0,
            16'sd0, 16'sd20, 16'sd0,
            16'sd0, 16'sd0, 16'sd30,
            16'sd2, 16'sd0, 16'sd0,
            16'sd0, -16'sd1, 16'sd0,
            16'sd0, 16'sd0, 16'sd1,
            32'sd7
        );
        // 10*2 + 20*(-1) + 30*1 + 7 = 37
        expect_output(16'sd37);

        repeat (4) @(posedge clk);
        $display("mobilenet_dw3x3_accel_tb PASS");
        $finish;
    end

endmodule
