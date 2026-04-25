`timescale 1ns/1ps

module mobilenet_dw3x3_channel_full_mmio #(
    parameter int DATA_W = 16,
    parameter int COEF_W = 16,
    parameter int BIAS_W = 32,
    parameter int ACC_W  = 48,
    parameter int OUT_W  = 32,
    parameter int MAX_H  = 32,
    parameter int MAX_W  = 40,
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
    localparam int MAX_ELEMS = MAX_H * MAX_W;
    localparam int MEM_ADDR_W = (MAX_ELEMS > 1) ? $clog2(MAX_ELEMS) : 1;

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

    typedef enum logic [1:0] {
        PHASE_ISSUE = 2'd0,
        PHASE_WAIT  = 2'd1,
        PHASE_ACCUM = 2'd2
    } mac_phase_t;

    logic [DIM_W-1:0] cfg_width_reg;
    logic [DIM_W-1:0] cfg_height_reg;
    logic signed [BIAS_W-1:0] cfg_bias_reg;
    logic [MEM_ADDR_W-1:0] feat_addr_reg;
    logic [3:0] weight_addr_reg;
    logic [MEM_ADDR_W-1:0] out_addr_reg;

    (* ram_style = "block" *) logic signed [DATA_W-1:0] feature_mem [0:MAX_ELEMS-1];
    logic signed [COEF_W-1:0] weight_mem [0:WINDOW_TAPS-1];
    (* ram_style = "block" *) logic signed [OUT_W-1:0] output_mem [0:MAX_ELEMS-1];

    logic busy_reg;
    logic done_latched;
    logic [DIM_W-1:0] cur_x;
    logic [DIM_W-1:0] cur_y;
    logic [MEM_ADDR_W-1:0] out_index;
    logic [3:0] tap_idx;
    mac_phase_t mac_phase;
    logic signed [ACC_W-1:0] acc_reg;

    logic tap_valid_d;
    logic [31:0] tap_addr_d;
    logic last_output_d;

    logic [MEM_ADDR_W-1:0] feature_rd_addr;
    logic signed [DATA_W-1:0] feature_rd_data;
    logic tap_valid_r;
    logic signed [COEF_W-1:0] tap_weight_r;
    logic signed [DATA_W-1:0] tap_pixel_d;
    logic signed [DATA_W+COEF_W-1:0] tap_product_d;
    logic signed [ACC_W-1:0] acc_next_d;

    logic signed [OUT_W-1:0] out_read_data_reg;
    logic feature_wr_en_d;
    logic [MEM_ADDR_W-1:0] feature_wr_addr_d;
    logic signed [DATA_W-1:0] feature_wr_data_d;
    logic output_wr_en_d;
    logic [MEM_ADDR_W-1:0] output_wr_addr_d;
    logic signed [OUT_W-1:0] output_wr_data_d;

    integer weight_idx;

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

    assign irq_done = done_latched;
    assign last_output_d = (cur_x == (cfg_width_reg - 1'b1)) && (cur_y == (cfg_height_reg - 1'b1));
    assign tap_pixel_d = tap_valid_r ? feature_rd_data : '0;
    assign tap_product_d = tap_pixel_d * tap_weight_r;
    assign acc_next_d = acc_reg + $signed(tap_product_d);
    assign feature_wr_en_d =
        rst_n &&
        mmio_wr_en &&
        (mmio_wr_addr == REG_FEAT_DATA) &&
        (busy_reg == 1'b0) &&
        (feat_addr_reg < MAX_ELEMS);
    assign feature_wr_addr_d = feat_addr_reg;
    assign feature_wr_data_d = mmio_wr_data[DATA_W-1:0];
    assign output_wr_en_d = rst_n && busy_reg && (mac_phase == PHASE_ACCUM) && (tap_idx == (WINDOW_TAPS - 1));
    assign output_wr_addr_d = out_index;
    assign output_wr_data_d = saturate_to_out(acc_next_d);

    always_ff @(posedge clk) begin
        if (feature_wr_en_d) begin
            feature_mem[feature_wr_addr_d] <= feature_wr_data_d;
        end
        feature_rd_data <= feature_mem[feature_rd_addr];
    end

    always_ff @(posedge clk) begin
        if (output_wr_en_d) begin
            output_mem[output_wr_addr_d] <= output_wr_data_d;
        end
        out_read_data_reg <= output_mem[out_addr_reg];
    end

    always_comb begin
        tap_valid_d = 1'b0;
        tap_addr_d = 32'd0;

        unique case (tap_idx)
            4'd0: begin
                tap_valid_d = (cur_y > 0) && (cur_x > 0);
                tap_addr_d = ((cur_y - 1'b1) * cfg_width_reg) + (cur_x - 1'b1);
            end
            4'd1: begin
                tap_valid_d = (cur_y > 0);
                tap_addr_d = ((cur_y - 1'b1) * cfg_width_reg) + cur_x;
            end
            4'd2: begin
                tap_valid_d = (cur_y > 0) && ((cur_x + 1'b1) < cfg_width_reg);
                tap_addr_d = ((cur_y - 1'b1) * cfg_width_reg) + (cur_x + 1'b1);
            end
            4'd3: begin
                tap_valid_d = (cur_x > 0);
                tap_addr_d = (cur_y * cfg_width_reg) + (cur_x - 1'b1);
            end
            4'd4: begin
                tap_valid_d = 1'b1;
                tap_addr_d = (cur_y * cfg_width_reg) + cur_x;
            end
            4'd5: begin
                tap_valid_d = ((cur_x + 1'b1) < cfg_width_reg);
                tap_addr_d = (cur_y * cfg_width_reg) + (cur_x + 1'b1);
            end
            4'd6: begin
                tap_valid_d = ((cur_y + 1'b1) < cfg_height_reg) && (cur_x > 0);
                tap_addr_d = ((cur_y + 1'b1) * cfg_width_reg) + (cur_x - 1'b1);
            end
            4'd7: begin
                tap_valid_d = ((cur_y + 1'b1) < cfg_height_reg);
                tap_addr_d = ((cur_y + 1'b1) * cfg_width_reg) + cur_x;
            end
            4'd8: begin
                tap_valid_d = ((cur_y + 1'b1) < cfg_height_reg) && ((cur_x + 1'b1) < cfg_width_reg);
                tap_addr_d = ((cur_y + 1'b1) * cfg_width_reg) + (cur_x + 1'b1);
            end
            default: begin
                tap_valid_d = 1'b0;
                tap_addr_d = 32'd0;
            end
        endcase
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            cfg_width_reg <= DIM_W'(MAX_W);
            cfg_height_reg <= DIM_W'(MAX_H);
            cfg_bias_reg <= '0;
            feat_addr_reg <= '0;
            weight_addr_reg <= '0;
            out_addr_reg <= '0;
            busy_reg <= 1'b0;
            done_latched <= 1'b0;
            cur_x <= '0;
            cur_y <= '0;
            out_index <= '0;
            tap_idx <= '0;
            mac_phase <= PHASE_ISSUE;
            acc_reg <= '0;
            feature_rd_addr <= '0;
            tap_valid_r <= 1'b0;
            tap_weight_r <= '0;
            for (weight_idx = 0; weight_idx < WINDOW_TAPS; weight_idx++) begin
                weight_mem[weight_idx] <= '0;
            end
        end else begin
            if (busy_reg) begin
                unique case (mac_phase)
                    PHASE_ISSUE: begin
                        feature_rd_addr <= tap_addr_d[MEM_ADDR_W-1:0];
                        tap_valid_r <= tap_valid_d && (tap_addr_d < MAX_ELEMS);
                        tap_weight_r <= weight_mem[tap_idx];
                        mac_phase <= PHASE_WAIT;
                    end
                    PHASE_WAIT: begin
                        mac_phase <= PHASE_ACCUM;
                    end
                    PHASE_ACCUM: begin
                        if (tap_idx == (WINDOW_TAPS - 1)) begin
                            tap_idx <= '0;
                            acc_reg <= cfg_bias_reg;
                            mac_phase <= PHASE_ISSUE;

                            if (last_output_d) begin
                                busy_reg <= 1'b0;
                                done_latched <= 1'b1;
                                cur_x <= '0;
                                cur_y <= '0;
                                out_index <= '0;
                            end else begin
                                out_index <= out_index + 1'b1;
                                if (cur_x == (cfg_width_reg - 1'b1)) begin
                                    cur_x <= '0;
                                    cur_y <= cur_y + 1'b1;
                                end else begin
                                    cur_x <= cur_x + 1'b1;
                                end
                            end
                        end else begin
                            tap_idx <= tap_idx + 1'b1;
                            acc_reg <= acc_next_d;
                            mac_phase <= PHASE_ISSUE;
                        end
                    end
                    default: begin
                        mac_phase <= PHASE_ISSUE;
                    end
                endcase
            end

            if (mmio_wr_en) begin
                unique case (mmio_wr_addr)
                    REG_CONTROL: begin
                        if ((mmio_wr_data & CTRL_CLEAR_DONE) != 32'h0) begin
                            done_latched <= 1'b0;
                        end
                        if (((mmio_wr_data & CTRL_START) != 32'h0) &&
                            (busy_reg == 1'b0) &&
                            (cfg_width_reg > 0) &&
                            (cfg_height_reg > 0) &&
                            (cfg_width_reg <= DIM_W'(MAX_W)) &&
                            (cfg_height_reg <= DIM_W'(MAX_H))) begin
                            busy_reg <= 1'b1;
                            done_latched <= 1'b0;
                            cur_x <= '0;
                            cur_y <= '0;
                            out_index <= '0;
                            tap_idx <= '0;
                            mac_phase <= PHASE_ISSUE;
                            acc_reg <= cfg_bias_reg;
                        end
                    end
                    REG_CFG_DIMS: begin
                        if (busy_reg == 1'b0) begin
                            cfg_width_reg <= mmio_wr_data[15:0];
                            cfg_height_reg <= mmio_wr_data[31:16];
                        end
                    end
                    REG_BIAS: begin
                        if (busy_reg == 1'b0) begin
                            cfg_bias_reg <= mmio_wr_data[BIAS_W-1:0];
                        end
                    end
                    REG_FEAT_ADDR: begin
                        if (busy_reg == 1'b0) begin
                            feat_addr_reg <= mmio_wr_data[MEM_ADDR_W-1:0];
                        end
                    end
                    REG_FEAT_DATA: begin
                    end
                    REG_WEIGHT_ADDR: begin
                        if (busy_reg == 1'b0) begin
                            weight_addr_reg <= mmio_wr_data[3:0];
                        end
                    end
                    REG_WEIGHT_DATA: begin
                        if ((busy_reg == 1'b0) && (weight_addr_reg < WINDOW_TAPS)) begin
                            weight_mem[weight_addr_reg] <= mmio_wr_data[COEF_W-1:0];
                        end
                    end
                    REG_OUT_ADDR: begin
                        out_addr_reg <= mmio_wr_data[MEM_ADDR_W-1:0];
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
            unique case (mmio_rd_addr)
                REG_CONTROL: begin
                    mmio_rd_data[1] = done_latched;
                    mmio_rd_data[2] = busy_reg;
                    mmio_rd_data[3] = ~busy_reg;
                end
                REG_CFG_DIMS: begin
                    mmio_rd_data[15:0] = cfg_width_reg;
                    mmio_rd_data[31:16] = cfg_height_reg;
                end
                REG_BIAS: begin
                    mmio_rd_data = cfg_bias_reg;
                end
                REG_FEAT_ADDR: begin
                    mmio_rd_data[MEM_ADDR_W-1:0] = feat_addr_reg;
                end
                REG_WEIGHT_ADDR: begin
                    mmio_rd_data[3:0] = weight_addr_reg;
                end
                REG_OUT_ADDR: begin
                    mmio_rd_data[MEM_ADDR_W-1:0] = out_addr_reg;
                end
                REG_OUT_DATA: begin
                    mmio_rd_data = out_read_data_reg;
                end
                REG_INFO: begin
                    mmio_rd_data[7:0] = 8'h06;
                    mmio_rd_data[15:8] = 8'(MAX_W);
                    mmio_rd_data[23:16] = 8'(MAX_H);
                    mmio_rd_data[31:24] = 8'hF3;
                end
                default: begin
                    mmio_rd_data = 32'h0;
                end
            endcase
        end
    end

endmodule
