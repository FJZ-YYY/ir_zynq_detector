`timescale 1ns/1ps

module mobilenet_dw3x3_channel_axi_impl #(
    parameter int C_S_AXI_ADDR_WIDTH = 8,
    parameter int C_S_AXI_DATA_WIDTH = 32,
    parameter int DATA_W = 16,
    parameter int COEF_W = 16,
    parameter int BIAS_W = 32,
    parameter int ACC_W  = 48,
    parameter int OUT_W  = 32,
    parameter int MAX_H  = 64,
    parameter int MAX_W  = 64,
    parameter int DIM_W  = 16
) (
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME S_AXI_ACLK, ASSOCIATED_BUSIF S_AXI, ASSOCIATED_RESET S_AXI_ARESETN, FREQ_HZ 50000000" *)
    input  logic                         s_axi_aclk,
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME S_AXI_ARESETN, POLARITY ACTIVE_LOW" *)
    input  logic                         s_axi_aresetn,

    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWADDR" *)
    input  logic [C_S_AXI_ADDR_WIDTH-1:0] s_axi_awaddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWPROT" *)
    input  logic [2:0]                  s_axi_awprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWVALID" *)
    input  logic                         s_axi_awvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWREADY" *)
    output logic                         s_axi_awready,

    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WDATA" *)
    input  logic [C_S_AXI_DATA_WIDTH-1:0] s_axi_wdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WSTRB" *)
    input  logic [(C_S_AXI_DATA_WIDTH/8)-1:0] s_axi_wstrb,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WVALID" *)
    input  logic                         s_axi_wvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WREADY" *)
    output logic                         s_axi_wready,

    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BRESP" *)
    output logic [1:0]                  s_axi_bresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BVALID" *)
    output logic                         s_axi_bvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BREADY" *)
    input  logic                         s_axi_bready,

    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARADDR" *)
    input  logic [C_S_AXI_ADDR_WIDTH-1:0] s_axi_araddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARPROT" *)
    input  logic [2:0]                  s_axi_arprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARVALID" *)
    input  logic                         s_axi_arvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARREADY" *)
    output logic                         s_axi_arready,

    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RDATA" *)
    output logic [C_S_AXI_DATA_WIDTH-1:0] s_axi_rdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RRESP" *)
    output logic [1:0]                  s_axi_rresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RVALID" *)
    output logic                         s_axi_rvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RREADY" *)
    input  logic                         s_axi_rready,

    output logic                         irq_done
);

    logic                         mmio_wr_en;
    logic [7:0]                   mmio_wr_addr;
    logic [31:0]                  mmio_wr_data;
    logic                         mmio_rd_en;
    logic [7:0]                   mmio_rd_addr;
    logic [31:0]                  mmio_rd_data;

    logic [C_S_AXI_ADDR_WIDTH-1:0] awaddr_r;
    logic [C_S_AXI_DATA_WIDTH-1:0] wdata_r;
    logic [(C_S_AXI_DATA_WIDTH/8)-1:0] wstrb_r;
    logic awaddr_valid_r;
    logic wdata_valid_r;
    logic mmio_wr_en_r;
    logic [7:0] mmio_wr_addr_r;
    logic [31:0] mmio_wr_data_r;

    logic aw_hs;
    logic w_hs;
    logic ar_hs;

    assign s_axi_awready = (~awaddr_valid_r) & (~s_axi_bvalid);
    assign s_axi_wready = (~wdata_valid_r) & (~s_axi_bvalid);
    assign s_axi_arready = ~s_axi_rvalid;
    assign s_axi_bresp = 2'b00;
    assign s_axi_rresp = 2'b00;

    assign aw_hs = s_axi_awvalid & s_axi_awready;
    assign w_hs = s_axi_wvalid & s_axi_wready;
    assign ar_hs = s_axi_arvalid & s_axi_arready;

    assign mmio_wr_en = mmio_wr_en_r;
    assign mmio_wr_addr = mmio_wr_addr_r;
    assign mmio_wr_data = mmio_wr_data_r;
    assign mmio_rd_en = ar_hs;
    assign mmio_rd_addr = s_axi_araddr[7:0];

    mobilenet_dw3x3_channel_mmio #(
        .DATA_W(DATA_W),
        .COEF_W(COEF_W),
        .BIAS_W(BIAS_W),
        .ACC_W(ACC_W),
        .OUT_W(OUT_W),
        .MAX_H(MAX_H),
        .MAX_W(MAX_W),
        .DIM_W(DIM_W)
    ) u_mmio (
        .clk(s_axi_aclk),
        .rst_n(s_axi_aresetn),
        .mmio_wr_en(mmio_wr_en),
        .mmio_wr_addr(mmio_wr_addr),
        .mmio_wr_data(mmio_wr_data),
        .mmio_rd_en(mmio_rd_en),
        .mmio_rd_addr(mmio_rd_addr),
        .mmio_rd_data(mmio_rd_data),
        .irq_done(irq_done)
    );

    always_ff @(posedge s_axi_aclk or negedge s_axi_aresetn) begin
        if (!s_axi_aresetn) begin
            awaddr_r <= '0;
            wdata_r <= '0;
            wstrb_r <= '0;
            awaddr_valid_r <= 1'b0;
            wdata_valid_r <= 1'b0;
            mmio_wr_en_r <= 1'b0;
            mmio_wr_addr_r <= '0;
            mmio_wr_data_r <= '0;
            s_axi_bvalid <= 1'b0;
            s_axi_rvalid <= 1'b0;
            s_axi_rdata <= '0;
        end else begin
            mmio_wr_en_r <= 1'b0;

            if (aw_hs) begin
                awaddr_r <= s_axi_awaddr;
                awaddr_valid_r <= 1'b1;
            end

            if (w_hs) begin
                wdata_r <= s_axi_wdata;
                wstrb_r <= s_axi_wstrb;
                wdata_valid_r <= 1'b1;
            end

            if ((!s_axi_bvalid) && awaddr_valid_r && wdata_valid_r) begin
                mmio_wr_en_r <= 1'b1;
                mmio_wr_addr_r <= awaddr_r[7:0];
                mmio_wr_data_r <= wdata_r;
                s_axi_bvalid <= 1'b1;
                awaddr_valid_r <= 1'b0;
                wdata_valid_r <= 1'b0;
            end else if (s_axi_bvalid && s_axi_bready) begin
                s_axi_bvalid <= 1'b0;
            end

            if (ar_hs) begin
                s_axi_rvalid <= 1'b1;
                s_axi_rdata <= mmio_rd_data;
            end else if (s_axi_rvalid && s_axi_rready) begin
                s_axi_rvalid <= 1'b0;
            end
        end
    end

endmodule
