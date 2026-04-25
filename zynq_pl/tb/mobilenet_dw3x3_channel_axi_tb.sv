`timescale 1ns/1ps

module mobilenet_dw3x3_channel_axi_tb;

    localparam int ADDR_W = 8;
    localparam int DATA_W = 32;

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
    logic [ADDR_W-1:0] s_axi_awaddr;
    logic [2:0] s_axi_awprot;
    logic s_axi_awvalid;
    logic s_axi_awready;
    logic [DATA_W-1:0] s_axi_wdata;
    logic [(DATA_W/8)-1:0] s_axi_wstrb;
    logic s_axi_wvalid;
    logic s_axi_wready;
    logic [1:0] s_axi_bresp;
    logic s_axi_bvalid;
    logic s_axi_bready;
    logic [ADDR_W-1:0] s_axi_araddr;
    logic [2:0] s_axi_arprot;
    logic s_axi_arvalid;
    logic s_axi_arready;
    logic [DATA_W-1:0] s_axi_rdata;
    logic [1:0] s_axi_rresp;
    logic s_axi_rvalid;
    logic s_axi_rready;
    logic irq_done;

    integer idx;

    mobilenet_dw3x3_channel_axi #(
        .C_S_AXI_ADDR_WIDTH(ADDR_W),
        .C_S_AXI_DATA_WIDTH(DATA_W),
        .MAX_H(8),
        .MAX_W(8)
    ) dut (
        .s_axi_aclk(clk),
        .s_axi_aresetn(rst_n),
        .s_axi_awaddr(s_axi_awaddr),
        .s_axi_awprot(s_axi_awprot),
        .s_axi_awvalid(s_axi_awvalid),
        .s_axi_awready(s_axi_awready),
        .s_axi_wdata(s_axi_wdata),
        .s_axi_wstrb(s_axi_wstrb),
        .s_axi_wvalid(s_axi_wvalid),
        .s_axi_wready(s_axi_wready),
        .s_axi_bresp(s_axi_bresp),
        .s_axi_bvalid(s_axi_bvalid),
        .s_axi_bready(s_axi_bready),
        .s_axi_araddr(s_axi_araddr),
        .s_axi_arprot(s_axi_arprot),
        .s_axi_arvalid(s_axi_arvalid),
        .s_axi_arready(s_axi_arready),
        .s_axi_rdata(s_axi_rdata),
        .s_axi_rresp(s_axi_rresp),
        .s_axi_rvalid(s_axi_rvalid),
        .s_axi_rready(s_axi_rready),
        .irq_done(irq_done)
    );

    always #5 clk = ~clk;

    task automatic axi_write(input logic [ADDR_W-1:0] addr, input logic [DATA_W-1:0] data);
        begin
            @(posedge clk);
            s_axi_awaddr <= addr;
            s_axi_awvalid <= 1'b1;
            s_axi_wdata <= data;
            s_axi_wvalid <= 1'b1;
            s_axi_bready <= 1'b1;
            while (!(s_axi_awready && s_axi_wready)) begin
                @(posedge clk);
            end
            @(posedge clk);
            s_axi_awvalid <= 1'b0;
            s_axi_wvalid <= 1'b0;
            while (!s_axi_bvalid) begin
                @(posedge clk);
            end
            @(posedge clk);
            s_axi_bready <= 1'b0;
        end
    endtask

    task automatic axi_write_aw_first(input logic [ADDR_W-1:0] addr, input logic [DATA_W-1:0] data);
        integer timeout;
        begin
            @(posedge clk);
            s_axi_awaddr <= addr;
            s_axi_awvalid <= 1'b1;
            s_axi_bready <= 1'b1;

            timeout = 0;
            while (!s_axi_awready) begin
                @(posedge clk);
                timeout++;
                if (timeout > 100) begin
                    $fatal(1, "AXI AW-first write timeout waiting for AWREADY");
                end
            end

            @(posedge clk);
            s_axi_awvalid <= 1'b0;
            repeat (3) @(posedge clk);

            s_axi_wdata <= data;
            s_axi_wvalid <= 1'b1;

            timeout = 0;
            while (!s_axi_wready) begin
                @(posedge clk);
                timeout++;
                if (timeout > 100) begin
                    $fatal(1, "AXI AW-first write timeout waiting for WREADY");
                end
            end

            @(posedge clk);
            s_axi_wvalid <= 1'b0;

            timeout = 0;
            while (!s_axi_bvalid) begin
                @(posedge clk);
                timeout++;
                if (timeout > 100) begin
                    $fatal(1, "AXI AW-first write timeout waiting for BVALID");
                end
            end

            @(posedge clk);
            s_axi_bready <= 1'b0;
        end
    endtask

    task automatic axi_write_w_first(input logic [ADDR_W-1:0] addr, input logic [DATA_W-1:0] data);
        integer timeout;
        begin
            @(posedge clk);
            s_axi_wdata <= data;
            s_axi_wvalid <= 1'b1;
            s_axi_bready <= 1'b1;

            timeout = 0;
            while (!s_axi_wready) begin
                @(posedge clk);
                timeout++;
                if (timeout > 100) begin
                    $fatal(1, "AXI W-first write timeout waiting for WREADY");
                end
            end

            @(posedge clk);
            s_axi_wvalid <= 1'b0;
            repeat (3) @(posedge clk);

            s_axi_awaddr <= addr;
            s_axi_awvalid <= 1'b1;

            timeout = 0;
            while (!s_axi_awready) begin
                @(posedge clk);
                timeout++;
                if (timeout > 100) begin
                    $fatal(1, "AXI W-first write timeout waiting for AWREADY");
                end
            end

            @(posedge clk);
            s_axi_awvalid <= 1'b0;

            timeout = 0;
            while (!s_axi_bvalid) begin
                @(posedge clk);
                timeout++;
                if (timeout > 100) begin
                    $fatal(1, "AXI W-first write timeout waiting for BVALID");
                end
            end

            @(posedge clk);
            s_axi_bready <= 1'b0;
        end
    endtask

    task automatic axi_read(input logic [ADDR_W-1:0] addr, output logic [DATA_W-1:0] data);
        begin
            @(posedge clk);
            s_axi_araddr <= addr;
            s_axi_arvalid <= 1'b1;
            s_axi_rready <= 1'b1;
            while (!s_axi_arready) begin
                @(posedge clk);
            end
            @(posedge clk);
            s_axi_arvalid <= 1'b0;
            while (!s_axi_rvalid) begin
                @(posedge clk);
            end
            data = s_axi_rdata;
            @(posedge clk);
            s_axi_rready <= 1'b0;
        end
    endtask

    initial begin
        logic [31:0] rd_data;

        clk = 1'b0;
        rst_n = 1'b0;
        s_axi_awaddr = '0;
        s_axi_awprot = '0;
        s_axi_awvalid = 1'b0;
        s_axi_wdata = '0;
        s_axi_wstrb = '1;
        s_axi_wvalid = 1'b0;
        s_axi_bready = 1'b0;
        s_axi_araddr = '0;
        s_axi_arprot = '0;
        s_axi_arvalid = 1'b0;
        s_axi_rready = 1'b0;

        repeat (4) @(posedge clk);
        rst_n <= 1'b1;

        axi_write_aw_first(REG_CFG_DIMS, {16'd3, 16'd3});
        axi_write_w_first(REG_BIAS, 32'd0);

        for (idx = 0; idx < 9; idx++) begin
            axi_write(REG_FEAT_ADDR, idx);
            axi_write(REG_FEAT_DATA, idx + 1);
            axi_write(REG_WEIGHT_ADDR, idx);
            axi_write(REG_WEIGHT_DATA, 32'd1);
        end

        axi_write(REG_CONTROL, 32'h1);

        rd_data = 32'h0;
        while ((rd_data[1] == 1'b0) && (irq_done == 1'b0)) begin
            axi_read(REG_CONTROL, rd_data);
        end

        axi_write(REG_OUT_ADDR, 32'd0);
        axi_read(REG_OUT_DATA, rd_data);
        if ($signed(rd_data) !== 45) begin
            $error("AXI mismatch expected=45 got=%0d", $signed(rd_data));
            $fatal(1);
        end

        $display("PASS axi result=%0d", $signed(rd_data));
        $display("mobilenet_dw3x3_channel_axi_tb PASS");
        $finish;
    end

endmodule
