`timescale 1ns/1ps

module mobilenet_dw3x3_channel_mmio_tb;

    localparam int DATA_W = 16;
    localparam int COEF_W = 16;
    localparam int BIAS_W = 32;
    localparam int ACC_W  = 48;
    localparam int OUT_W  = 32;
    localparam int MAX_H  = 8;
    localparam int MAX_W  = 8;
    localparam int DIM_W  = 16;

    localparam logic [7:0] REG_CONTROL     = 8'h00;
    localparam logic [7:0] REG_CFG_DIMS    = 8'h04;
    localparam logic [7:0] REG_BIAS        = 8'h08;
    localparam logic [7:0] REG_FEAT_ADDR   = 8'h0C;
    localparam logic [7:0] REG_FEAT_DATA   = 8'h10;
    localparam logic [7:0] REG_WEIGHT_ADDR = 8'h14;
    localparam logic [7:0] REG_WEIGHT_DATA = 8'h18;
    localparam logic [7:0] REG_OUT_ADDR    = 8'h1C;
    localparam logic [7:0] REG_OUT_DATA    = 8'h20;

    logic clk;
    logic rst_n;
    logic mmio_wr_en;
    logic [7:0] mmio_wr_addr;
    logic [31:0] mmio_wr_data;
    logic mmio_rd_en;
    logic [7:0] mmio_rd_addr;
    logic [31:0] mmio_rd_data;
    logic irq_done;

    integer idx;

    mobilenet_dw3x3_channel_mmio #(
        .DATA_W(DATA_W),
        .COEF_W(COEF_W),
        .BIAS_W(BIAS_W),
        .ACC_W(ACC_W),
        .OUT_W(OUT_W),
        .MAX_H(MAX_H),
        .MAX_W(MAX_W),
        .DIM_W(DIM_W)
    ) dut (
        .clk(clk),
        .rst_n(rst_n),
        .mmio_wr_en(mmio_wr_en),
        .mmio_wr_addr(mmio_wr_addr),
        .mmio_wr_data(mmio_wr_data),
        .mmio_rd_en(mmio_rd_en),
        .mmio_rd_addr(mmio_rd_addr),
        .mmio_rd_data(mmio_rd_data),
        .irq_done(irq_done)
    );

    always #5 clk = ~clk;

    task automatic mmio_write(input logic [7:0] addr, input logic [31:0] data);
        begin
            @(posedge clk);
            mmio_wr_en <= 1'b1;
            mmio_wr_addr <= addr;
            mmio_wr_data <= data;
            @(posedge clk);
            mmio_wr_en <= 1'b0;
            mmio_wr_addr <= '0;
            mmio_wr_data <= '0;
        end
    endtask

    task automatic mmio_set_read_addr(input logic [7:0] addr);
        begin
            @(posedge clk);
            mmio_rd_en <= 1'b1;
            mmio_rd_addr <= addr;
            @(posedge clk);
        end
    endtask

    initial begin
        clk = 1'b0;
        rst_n = 1'b0;
        mmio_wr_en = 1'b0;
        mmio_wr_addr = '0;
        mmio_wr_data = '0;
        mmio_rd_en = 1'b0;
        mmio_rd_addr = '0;

        repeat (4) @(posedge clk);
        rst_n <= 1'b1;

        mmio_write(REG_CFG_DIMS, {16'd3, 16'd3});
        mmio_write(REG_BIAS, 32'd0);

        for (idx = 0; idx < 9; idx++) begin
            mmio_write(REG_FEAT_ADDR, idx);
            mmio_write(REG_FEAT_DATA, idx + 1);
            mmio_write(REG_WEIGHT_ADDR, idx);
            mmio_write(REG_WEIGHT_DATA, 32'd1);
        end

        mmio_write(REG_CONTROL, 32'h1);

        mmio_set_read_addr(REG_CONTROL);
        while ((mmio_rd_data[1] == 1'b0) && (irq_done == 1'b0)) begin
            @(posedge clk);
        end

        mmio_write(REG_OUT_ADDR, 32'd0);
        mmio_set_read_addr(REG_OUT_DATA);
        if ($signed(mmio_rd_data) !== 45) begin
            $error("Mismatch expected=45 got=%0d", $signed(mmio_rd_data));
            $fatal(1);
        end

        $display("PASS mmio result=%0d", $signed(mmio_rd_data));
        $display("mobilenet_dw3x3_channel_mmio_tb PASS");
        $finish;
    end

endmodule
