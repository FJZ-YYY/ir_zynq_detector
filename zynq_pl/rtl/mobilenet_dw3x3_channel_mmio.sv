`timescale 1ns/1ps

module mobilenet_dw3x3_channel_mmio #(
    parameter int DATA_W = 16,
    parameter int COEF_W = 16,
    parameter int BIAS_W = 32,
    parameter int ACC_W  = 48,
    parameter int OUT_W  = 32,
    parameter int MAX_H  = 64,
    parameter int MAX_W  = 64,
    parameter int DIM_W  = 16
) (
    input  logic                         clk,
    input  logic                         rst_n,

    input  logic                         mmio_wr_en,
    input  logic [7:0]                   mmio_wr_addr,
    input  logic [31:0]                  mmio_wr_data,

    input  logic                         mmio_rd_en,
    input  logic [7:0]                   mmio_rd_addr,
    output logic [31:0]                  mmio_rd_data,

    output logic                         irq_done
);

    localparam int WINDOW_TAPS = 9;

    localparam logic [7:0] REG_CONTROL     = 8'h00;
    localparam logic [7:0] REG_CFG_DIMS    = 8'h04;
    localparam logic [7:0] REG_BIAS        = 8'h08;
    localparam logic [7:0] REG_FEAT_ADDR   = 8'h0C;
    localparam logic [7:0] REG_FEAT_DATA   = 8'h10;
    localparam logic [7:0] REG_WEIGHT_ADDR = 8'h14;
    localparam logic [7:0] REG_WEIGHT_DATA = 8'h18;
    localparam logic [7:0] REG_OUT_ADDR    = 8'h1C;
    localparam logic [7:0] REG_OUT_DATA    = 8'h20;
    localparam logic [7:0] REG_INFO        = 8'h24;

    localparam logic [31:0] CTRL_START      = 32'h0000_0001;
    localparam logic [31:0] CTRL_CLEAR_DONE = 32'h0000_0002;

    logic [DIM_W-1:0] cfg_width_reg;
    logic [DIM_W-1:0] cfg_height_reg;
    logic signed [BIAS_W-1:0] cfg_bias_reg;
    logic [3:0] feat_addr_reg;
    logic [3:0] weight_addr_reg;
    logic [31:0] out_addr_reg;

    logic core_feat_wr_en;
    logic [3:0] core_feat_wr_addr;
    logic signed [DATA_W-1:0] core_feat_wr_data;

    logic core_weight_wr_en;
    logic [3:0] core_weight_wr_addr;
    logic signed [COEF_W-1:0] core_weight_wr_data;

    logic core_start_pulse;
    logic core_cfg_ready;
    logic core_busy;
    logic core_done;
    logic core_out_valid;
    logic [DIM_W-1:0] core_out_x;
    logic [DIM_W-1:0] core_out_y;
    logic signed [OUT_W-1:0] core_out_data;

    logic done_latched;
    logic signed [OUT_W-1:0] result_reg;

    mobilenet_dw3x3_channel_core #(
        .DATA_W(DATA_W),
        .COEF_W(COEF_W),
        .BIAS_W(BIAS_W),
        .ACC_W(ACC_W),
        .OUT_W(OUT_W),
        .MAX_H(MAX_H),
        .MAX_W(MAX_W),
        .DIM_W(DIM_W),
        .FEAT_ADDR_W(4)
    ) u_core (
        .clk(clk),
        .rst_n(rst_n),
        .cfg_valid(1'b1),
        .cfg_ready(core_cfg_ready),
        .cfg_width(cfg_width_reg),
        .cfg_height(cfg_height_reg),
        .cfg_bias(cfg_bias_reg),
        .feat_wr_en(core_feat_wr_en),
        .feat_wr_addr(core_feat_wr_addr),
        .feat_wr_data(core_feat_wr_data),
        .weight_wr_en(core_weight_wr_en),
        .weight_wr_addr(core_weight_wr_addr),
        .weight_wr_data(core_weight_wr_data),
        .start(core_start_pulse),
        .busy(core_busy),
        .done(core_done),
        .out_valid(core_out_valid),
        .out_ready(1'b1),
        .out_x(core_out_x),
        .out_y(core_out_y),
        .out_data(core_out_data)
    );

    assign irq_done = done_latched;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            cfg_width_reg <= 16'd3;
            cfg_height_reg <= 16'd3;
            cfg_bias_reg <= '0;
            feat_addr_reg <= '0;
            weight_addr_reg <= '0;
            out_addr_reg <= '0;
            core_feat_wr_en <= 1'b0;
            core_feat_wr_addr <= '0;
            core_feat_wr_data <= '0;
            core_weight_wr_en <= 1'b0;
            core_weight_wr_addr <= '0;
            core_weight_wr_data <= '0;
            core_start_pulse <= 1'b0;
            done_latched <= 1'b0;
            result_reg <= '0;
        end else begin
            core_feat_wr_en <= 1'b0;
            core_weight_wr_en <= 1'b0;
            core_start_pulse <= 1'b0;

            if (core_out_valid) begin
                result_reg <= core_out_data;
            end

            if (core_done) begin
                done_latched <= 1'b1;
            end

            if (mmio_wr_en) begin
                case (mmio_wr_addr)
                    REG_CONTROL: begin
                        if ((mmio_wr_data & CTRL_CLEAR_DONE) != 32'h0) begin
                            done_latched <= 1'b0;
                        end
                        if (((mmio_wr_data & CTRL_START) != 32'h0) && (core_busy == 1'b0)) begin
                            done_latched <= 1'b0;
                            core_start_pulse <= 1'b1;
                        end
                    end
                    REG_CFG_DIMS: begin
                        if (core_busy == 1'b0) begin
                            cfg_width_reg <= mmio_wr_data[15:0];
                            cfg_height_reg <= mmio_wr_data[31:16];
                        end
                    end
                    REG_BIAS: begin
                        if (core_busy == 1'b0) begin
                            cfg_bias_reg <= mmio_wr_data[BIAS_W-1:0];
                        end
                    end
                    REG_FEAT_ADDR: begin
                        if (core_busy == 1'b0) begin
                            feat_addr_reg <= mmio_wr_data[3:0];
                        end
                    end
                    REG_FEAT_DATA: begin
                        if (core_busy == 1'b0) begin
                            core_feat_wr_en <= 1'b1;
                            core_feat_wr_addr <= feat_addr_reg;
                            core_feat_wr_data <= mmio_wr_data[DATA_W-1:0];
                        end
                    end
                    REG_WEIGHT_ADDR: begin
                        if (core_busy == 1'b0) begin
                            weight_addr_reg <= mmio_wr_data[3:0];
                        end
                    end
                    REG_WEIGHT_DATA: begin
                        if (core_busy == 1'b0) begin
                            core_weight_wr_en <= 1'b1;
                            core_weight_wr_addr <= weight_addr_reg;
                            core_weight_wr_data <= mmio_wr_data[COEF_W-1:0];
                        end
                    end
                    REG_OUT_ADDR: begin
                        out_addr_reg <= mmio_wr_data;
                    end
                    default: begin
                    end
                endcase
            end
        end
    end

    always_comb begin
        mmio_rd_data = 32'h0;
        if (mmio_rd_en) begin
            case (mmio_rd_addr)
                REG_CONTROL: begin
                    mmio_rd_data[1] = done_latched;
                    mmio_rd_data[2] = core_busy;
                    mmio_rd_data[3] = core_cfg_ready;
                end
                REG_CFG_DIMS: begin
                    mmio_rd_data[15:0] = cfg_width_reg;
                    mmio_rd_data[31:16] = cfg_height_reg;
                end
                REG_BIAS: begin
                    mmio_rd_data = cfg_bias_reg;
                end
                REG_FEAT_ADDR: begin
                    mmio_rd_data[3:0] = feat_addr_reg;
                end
                REG_WEIGHT_ADDR: begin
                    mmio_rd_data[3:0] = weight_addr_reg;
                end
                REG_OUT_ADDR: begin
                    mmio_rd_data = out_addr_reg;
                end
                REG_OUT_DATA: begin
                    mmio_rd_data = result_reg;
                end
                REG_INFO: begin
                    mmio_rd_data[7:0] = 8'h02;
                    mmio_rd_data[15:8] = 8'd3;
                    mmio_rd_data[23:16] = 8'd3;
                    mmio_rd_data[31:24] = 8'hD3;
                end
                default: begin
                    mmio_rd_data = 32'h0;
                end
            endcase
        end
    end

endmodule
