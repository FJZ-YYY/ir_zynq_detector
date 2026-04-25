`timescale 1ns/1ps

module mobilenet_dw3x3_accel #(
    parameter int DATA_W = 16,
    parameter int COEF_W = 16,
    parameter int BIAS_W = 32,
    parameter int ACC_W  = 48,
    parameter int OUT_W  = 16,
    parameter int SHIFT  = 0
) (
    input  logic                         clk,
    input  logic                         rst_n,
    input  logic                         in_valid,
    output logic                         in_ready,
    input  logic signed [DATA_W-1:0]     pixel_window [0:8],
    input  logic signed [COEF_W-1:0]     weight_window [0:8],
    input  logic signed [BIAS_W-1:0]     bias,
    output logic                         out_valid,
    input  logic                         out_ready,
    output logic signed [OUT_W-1:0]      out_data
);

    logic signed [ACC_W-1:0] mac_sum_d;
    logic signed [ACC_W-1:0] shifted_sum_d;
    logic signed [OUT_W-1:0] sat_sum_d;
    logic signed [ACC_W-1:0] mult_terms [0:8];
    integer idx;

    function automatic logic signed [OUT_W-1:0] saturate_to_out(input logic signed [ACC_W-1:0] value);
        logic signed [ACC_W-1:0] max_val;
        logic signed [ACC_W-1:0] min_val;
        begin
            max_val = (1 <<< (OUT_W - 1)) - 1;
            min_val = -1 * (1 <<< (OUT_W - 1));
            if (value > max_val) begin
                saturate_to_out = max_val[OUT_W-1:0];
            end else if (value < min_val) begin
                saturate_to_out = min_val[OUT_W-1:0];
            end else begin
                saturate_to_out = value[OUT_W-1:0];
            end
        end
    endfunction

    always_comb begin
        mac_sum_d = bias;
        for (idx = 0; idx < 9; idx++) begin
            mult_terms[idx] = pixel_window[idx] * weight_window[idx];
            mac_sum_d = mac_sum_d + mult_terms[idx];
        end

        if (SHIFT > 0) begin
            shifted_sum_d = mac_sum_d >>> SHIFT;
        end else begin
            shifted_sum_d = mac_sum_d;
        end
        sat_sum_d = saturate_to_out(shifted_sum_d);
    end

    assign in_ready = (~out_valid) | out_ready;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            out_valid <= 1'b0;
            out_data  <= '0;
        end else if (in_ready) begin
            out_valid <= in_valid;
            out_data  <= sat_sum_d;
        end
    end

endmodule
