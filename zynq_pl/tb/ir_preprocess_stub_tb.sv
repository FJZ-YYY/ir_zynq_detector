`timescale 1ns/1ps

module ir_preprocess_stub_tb;

    logic       clk;
    logic       rst_n;
    logic       s_axis_tvalid;
    logic       s_axis_tready;
    logic [7:0] s_axis_tdata;
    logic       s_axis_tlast;
    logic [0:0] s_axis_tuser;
    logic       m_axis_tvalid;
    logic       m_axis_tready;
    logic [7:0] m_axis_tdata;
    logic       m_axis_tlast;
    logic [0:0] m_axis_tuser;

    ir_preprocess_stub dut (
        .clk(clk),
        .rst_n(rst_n),
        .s_axis_tvalid(s_axis_tvalid),
        .s_axis_tready(s_axis_tready),
        .s_axis_tdata(s_axis_tdata),
        .s_axis_tlast(s_axis_tlast),
        .s_axis_tuser(s_axis_tuser),
        .m_axis_tvalid(m_axis_tvalid),
        .m_axis_tready(m_axis_tready),
        .m_axis_tdata(m_axis_tdata),
        .m_axis_tlast(m_axis_tlast),
        .m_axis_tuser(m_axis_tuser)
    );

    always #5 clk = ~clk;

    initial begin
        clk = 1'b0;
        rst_n = 1'b0;
        s_axis_tvalid = 1'b0;
        s_axis_tdata = '0;
        s_axis_tlast = 1'b0;
        s_axis_tuser = '0;
        m_axis_tready = 1'b1;

        repeat (4) @(posedge clk);
        rst_n <= 1'b1;

        @(posedge clk);
        s_axis_tvalid <= 1'b1;
        s_axis_tdata <= 8'h3C;
        s_axis_tuser <= 1'b1;
        s_axis_tlast <= 1'b0;

        @(posedge clk);
        s_axis_tdata <= 8'hA5;
        s_axis_tuser <= 1'b0;
        s_axis_tlast <= 1'b1;

        @(posedge clk);
        s_axis_tvalid <= 1'b0;
        s_axis_tdata <= '0;
        s_axis_tlast <= 1'b0;
        s_axis_tuser <= '0;

        repeat (4) @(posedge clk);
        $finish;
    end

    always @(posedge clk) begin
        if (rst_n && m_axis_tvalid && m_axis_tready) begin
            $display(
                "time=%0t data=0x%02h user=%0b last=%0b",
                $time,
                m_axis_tdata,
                m_axis_tuser,
                m_axis_tlast
            );
        end
    end

endmodule

