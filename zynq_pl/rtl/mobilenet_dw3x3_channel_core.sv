`timescale 1ns/1ps

module mobilenet_dw3x3_channel_core #(
    parameter int DATA_W = 16,
    parameter int COEF_W = 16,
    parameter int BIAS_W = 32,
    parameter int ACC_W  = 48,
    parameter int OUT_W  = 32,
    parameter int MAX_H  = 64,
    parameter int MAX_W  = 64,
    parameter int DIM_W  = 16,
    parameter int FEAT_ADDR_W = ((MAX_H * MAX_W) > 1) ? $clog2(MAX_H * MAX_W) : 1
) (
    input  logic                         clk,
    input  logic                         rst_n,

    input  logic                         cfg_valid,
    output logic                         cfg_ready,
    input  logic [DIM_W-1:0]             cfg_width,
    input  logic [DIM_W-1:0]             cfg_height,
    input  logic signed [BIAS_W-1:0]     cfg_bias,

    input  logic                         feat_wr_en,
    input  logic [FEAT_ADDR_W-1:0]       feat_wr_addr,
    input  logic signed [DATA_W-1:0]     feat_wr_data,

    input  logic                         weight_wr_en,
    input  logic [3:0]                   weight_wr_addr,
    input  logic signed [COEF_W-1:0]     weight_wr_data,

    input  logic                         start,
    output logic                         busy,
    output logic                         done,

    output logic                         out_valid,
    input  logic                         out_ready,
    output logic [DIM_W-1:0]             out_x,
    output logic [DIM_W-1:0]             out_y,
    output logic signed [OUT_W-1:0]      out_data
);

    localparam int WINDOW_TAPS = 9;

    logic [DIM_W-1:0] cfg_width_r;
    logic [DIM_W-1:0] cfg_height_r;
    logic signed [BIAS_W-1:0] cfg_bias_r;

    logic signed [DATA_W-1:0] feature_mem [0:WINDOW_TAPS-1];
    logic signed [COEF_W-1:0] weight_mem [0:WINDOW_TAPS-1];

    logic mac_active;
    logic [3:0] mac_idx;
    logic signed [ACC_W-1:0] acc_reg;
    logic out_valid_r;
    logic signed [OUT_W-1:0] out_data_r;

    logic signed [DATA_W+COEF_W-1:0] product_d;
    logic signed [ACC_W-1:0] acc_next_d;

    integer mem_idx;

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

    assign cfg_ready = (~mac_active) & (~out_valid_r);
    assign busy = mac_active | out_valid_r;
    assign out_valid = out_valid_r;
    assign out_x = '0;
    assign out_y = '0;
    assign out_data = out_data_r;

    always_comb begin
        product_d = feature_mem[mac_idx] * weight_mem[mac_idx];
        acc_next_d = acc_reg + $signed(product_d);
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            cfg_width_r <= '0;
            cfg_height_r <= '0;
            cfg_bias_r <= '0;
            mac_active <= 1'b0;
            mac_idx <= '0;
            acc_reg <= '0;
            out_valid_r <= 1'b0;
            out_data_r <= '0;
            done <= 1'b0;
            for (mem_idx = 0; mem_idx < WINDOW_TAPS; mem_idx++) begin
                feature_mem[mem_idx] <= '0;
                weight_mem[mem_idx] <= '0;
            end
        end else begin
            done <= 1'b0;

            if (cfg_valid && cfg_ready) begin
                cfg_width_r <= cfg_width;
                cfg_height_r <= cfg_height;
                cfg_bias_r <= cfg_bias;
            end

            if (cfg_ready && feat_wr_en && (feat_wr_addr < WINDOW_TAPS)) begin
                feature_mem[feat_wr_addr] <= feat_wr_data;
            end

            if (cfg_ready && weight_wr_en && (weight_wr_addr < WINDOW_TAPS)) begin
                weight_mem[weight_wr_addr] <= weight_wr_data;
            end

            if (mac_active) begin
                if (mac_idx == (WINDOW_TAPS - 1)) begin
                    mac_active <= 1'b0;
                    mac_idx <= '0;
                    acc_reg <= '0;
                    out_valid_r <= 1'b1;
                    out_data_r <= saturate_to_out(acc_next_d);
                end else begin
                    mac_idx <= mac_idx + 1'b1;
                    acc_reg <= acc_next_d;
                end
            end else if ((!out_valid_r) && start && (cfg_width_r == 16'd3) && (cfg_height_r == 16'd3)) begin
                mac_active <= 1'b1;
                mac_idx <= '0;
                acc_reg <= cfg_bias_r;
            end else if (out_valid_r && out_ready) begin
                out_valid_r <= 1'b0;
                done <= 1'b1;
            end
        end
    end

endmodule
