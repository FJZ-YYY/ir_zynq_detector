module ir_preprocess_stub #(
    parameter int DATA_W = 8,
    parameter int USER_W = 1
) (
    input  logic              clk,
    input  logic              rst_n,

    input  logic              s_axis_tvalid,
    output logic              s_axis_tready,
    input  logic [DATA_W-1:0] s_axis_tdata,
    input  logic              s_axis_tlast,
    input  logic [USER_W-1:0] s_axis_tuser,

    output logic              m_axis_tvalid,
    input  logic              m_axis_tready,
    output logic [DATA_W-1:0] m_axis_tdata,
    output logic              m_axis_tlast,
    output logic [USER_W-1:0] m_axis_tuser
);

    // Phase-1 stub:
    // 1. keeps AXI-Stream interface stable
    // 2. forwards pixels without resize/normalize
    // 3. can later be replaced by a real preprocess pipeline

    assign s_axis_tready = (~m_axis_tvalid) | m_axis_tready;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            m_axis_tvalid <= 1'b0;
            m_axis_tdata  <= '0;
            m_axis_tlast  <= 1'b0;
            m_axis_tuser  <= '0;
        end else if (s_axis_tready) begin
            m_axis_tvalid <= s_axis_tvalid;
            m_axis_tdata  <= s_axis_tdata;
            m_axis_tlast  <= s_axis_tlast;
            m_axis_tuser  <= s_axis_tuser;
        end
    end

endmodule

