`timescale 1ns/1ps

module mobilenet_dw3x3_channel_core_tb;

    localparam int DATA_W = 16;
    localparam int COEF_W = 16;
    localparam int BIAS_W = 32;
    localparam int ACC_W  = 48;
    localparam int OUT_W  = 32;
    localparam int MAX_H  = 8;
    localparam int MAX_W  = 8;
    localparam int DIM_W  = 16;

    logic clk;
    logic rst_n;
    logic cfg_valid;
    logic cfg_ready;
    logic [DIM_W-1:0] cfg_width;
    logic [DIM_W-1:0] cfg_height;
    logic signed [BIAS_W-1:0] cfg_bias;
    logic feat_wr_en;
    logic [3:0] feat_wr_addr;
    logic signed [DATA_W-1:0] feat_wr_data;
    logic weight_wr_en;
    logic [3:0] weight_wr_addr;
    logic signed [COEF_W-1:0] weight_wr_data;
    logic start;
    logic busy;
    logic done;
    logic out_valid;
    logic out_ready;
    logic [DIM_W-1:0] out_x;
    logic [DIM_W-1:0] out_y;
    logic signed [OUT_W-1:0] out_data;

    integer idx;

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
    ) dut (
        .clk(clk),
        .rst_n(rst_n),
        .cfg_valid(cfg_valid),
        .cfg_ready(cfg_ready),
        .cfg_width(cfg_width),
        .cfg_height(cfg_height),
        .cfg_bias(cfg_bias),
        .feat_wr_en(feat_wr_en),
        .feat_wr_addr(feat_wr_addr),
        .feat_wr_data(feat_wr_data),
        .weight_wr_en(weight_wr_en),
        .weight_wr_addr(weight_wr_addr),
        .weight_wr_data(weight_wr_data),
        .start(start),
        .busy(busy),
        .done(done),
        .out_valid(out_valid),
        .out_ready(out_ready),
        .out_x(out_x),
        .out_y(out_y),
        .out_data(out_data)
    );

    always #5 clk = ~clk;

    task automatic write_feature(input integer addr, input integer value);
        begin
            @(posedge clk);
            feat_wr_en <= 1'b1;
            feat_wr_addr <= addr[3:0];
            feat_wr_data <= value[DATA_W-1:0];
            @(posedge clk);
            feat_wr_en <= 1'b0;
        end
    endtask

    task automatic write_weight(input integer addr, input integer value);
        begin
            @(posedge clk);
            weight_wr_en <= 1'b1;
            weight_wr_addr <= addr[3:0];
            weight_wr_data <= value[COEF_W-1:0];
            @(posedge clk);
            weight_wr_en <= 1'b0;
        end
    endtask

    initial begin
        clk = 1'b0;
        rst_n = 1'b0;
        cfg_valid = 1'b0;
        cfg_width = '0;
        cfg_height = '0;
        cfg_bias = '0;
        feat_wr_en = 1'b0;
        feat_wr_addr = '0;
        feat_wr_data = '0;
        weight_wr_en = 1'b0;
        weight_wr_addr = '0;
        weight_wr_data = '0;
        start = 1'b0;
        out_ready = 1'b1;

        repeat (4) @(posedge clk);
        rst_n <= 1'b1;

        @(posedge clk);
        cfg_width <= 16'd3;
        cfg_height <= 16'd3;
        cfg_bias <= 0;
        cfg_valid <= 1'b1;
        @(posedge clk);
        cfg_valid <= 1'b0;

        for (idx = 0; idx < 9; idx++) begin
            write_feature(idx, idx + 1);
            write_weight(idx, 1);
        end

        @(posedge clk);
        start <= 1'b1;
        @(posedge clk);
        start <= 1'b0;

        while (!done) begin
            @(posedge clk);
            if (out_valid && out_ready) begin
                if ((out_x !== 0) || (out_y !== 0)) begin
                    $error("Expected single-window coordinate (0,0), got (%0d,%0d)", out_x, out_y);
                    $fatal(1);
                end
                if (out_data !== 45) begin
                    $error("Mismatch expected=45 got=%0d", out_data);
                    $fatal(1);
                end
                $display("PASS core result=%0d", out_data);
            end
        end

        $display("mobilenet_dw3x3_channel_core_tb PASS");
        $finish;
    end

endmodule
