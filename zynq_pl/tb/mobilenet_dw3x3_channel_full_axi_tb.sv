`timescale 1ns/1ps

module mobilenet_dw3x3_channel_full_axi_tb;

    localparam int ADDR_W = 8;
    localparam int DATA_W = 32;
    localparam int TEST_H = 4;
    localparam int TEST_W = 4;
    localparam int TEST_ELEMS = TEST_H * TEST_W;

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

    int feature [0:TEST_ELEMS-1];
    int weights [0:8];
    int bias;
    integer idx;

    mobilenet_dw3x3_channel_full_axi #(
        .C_S_AXI_ADDR_WIDTH(ADDR_W),
        .C_S_AXI_DATA_WIDTH(DATA_W),
        .MAX_H(TEST_H),
        .MAX_W(TEST_W)
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
        integer timeout;
        begin
            @(posedge clk);
            s_axi_awaddr <= addr;
            s_axi_awvalid <= 1'b1;
            s_axi_wdata <= data;
            s_axi_wvalid <= 1'b1;
            s_axi_bready <= 1'b1;

            timeout = 0;
            while (!(s_axi_awready && s_axi_wready)) begin
                @(posedge clk);
                timeout++;
                if (timeout > 100) begin
                    $fatal(1, "AXI write timeout addr=0x%02h", addr);
                end
            end

            @(posedge clk);
            s_axi_awvalid <= 1'b0;
            s_axi_wvalid <= 1'b0;

            timeout = 0;
            while (!s_axi_bvalid) begin
                @(posedge clk);
                timeout++;
                if (timeout > 100) begin
                    $fatal(1, "AXI bvalid timeout addr=0x%02h", addr);
                end
            end

            @(posedge clk);
            s_axi_bready <= 1'b0;
        end
    endtask

    task automatic axi_read(input logic [ADDR_W-1:0] addr, output logic [DATA_W-1:0] data);
        integer timeout;
        begin
            @(posedge clk);
            s_axi_araddr <= addr;
            s_axi_arvalid <= 1'b1;
            s_axi_rready <= 1'b1;

            timeout = 0;
            while (!s_axi_arready) begin
                @(posedge clk);
                timeout++;
                if (timeout > 100) begin
                    $fatal(1, "AXI arready timeout addr=0x%02h", addr);
                end
            end

            @(posedge clk);
            s_axi_arvalid <= 1'b0;

            timeout = 0;
            while (!s_axi_rvalid) begin
                @(posedge clk);
                timeout++;
                if (timeout > 100) begin
                    $fatal(1, "AXI rvalid timeout addr=0x%02h", addr);
                end
            end

            data = s_axi_rdata;
            @(posedge clk);
            s_axi_rready <= 1'b0;
        end
    endtask

    function automatic int expected_at(input int y, input int x);
        int acc;
        int ky;
        int kx;
        int sy;
        int sx;
        int tap;
        begin
            acc = bias;
            tap = 0;
            for (ky = -1; ky <= 1; ky++) begin
                for (kx = -1; kx <= 1; kx++) begin
                    sy = y + ky;
                    sx = x + kx;
                    if ((sy >= 0) && (sy < TEST_H) && (sx >= 0) && (sx < TEST_W)) begin
                        acc += feature[(sy * TEST_W) + sx] * weights[tap];
                    end
                    tap++;
                end
            end
            expected_at = acc;
        end
    endfunction

    initial begin
        logic [31:0] rd_data;
        int exp;
        int y;
        int x;
        int poll_count;

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

        bias = 3;
        for (idx = 0; idx < TEST_ELEMS; idx++) begin
            feature[idx] = idx + 1;
        end
        for (idx = 0; idx < 9; idx++) begin
            weights[idx] = idx + 1;
        end

        repeat (4) @(posedge clk);
        rst_n <= 1'b1;

        axi_write(REG_CFG_DIMS, {16'(TEST_H), 16'(TEST_W)});
        axi_write(REG_BIAS, bias[31:0]);

        for (idx = 0; idx < TEST_ELEMS; idx++) begin
            axi_write(REG_FEAT_ADDR, idx[31:0]);
            axi_write(REG_FEAT_DATA, feature[idx][31:0]);
        end

        for (idx = 0; idx < 9; idx++) begin
            axi_write(REG_WEIGHT_ADDR, idx[31:0]);
            axi_write(REG_WEIGHT_DATA, weights[idx][31:0]);
        end

        axi_write(REG_CONTROL, 32'h1);

        rd_data = 32'h0;
        poll_count = 0;
        while ((rd_data[1] == 1'b0) && (irq_done == 1'b0)) begin
            axi_read(REG_CONTROL, rd_data);
            poll_count++;
            if (poll_count > 1000) begin
                $fatal(1, "Timeout waiting for full-channel done");
            end
        end

        for (y = 0; y < TEST_H; y++) begin
            for (x = 0; x < TEST_W; x++) begin
                idx = (y * TEST_W) + x;
                exp = expected_at(y, x);
                axi_write(REG_OUT_ADDR, idx[31:0]);
                axi_read(REG_OUT_DATA, rd_data);
                if ($signed(rd_data) !== exp) begin
                    $fatal(1, "Mismatch idx=%0d y=%0d x=%0d expected=%0d got=%0d",
                           idx, y, x, exp, $signed(rd_data));
                end
            end
        end

        $display("PASS full-channel axi outputs=%0d", TEST_ELEMS);
        $display("mobilenet_dw3x3_channel_full_axi_tb PASS");
        $finish;
    end

endmodule
