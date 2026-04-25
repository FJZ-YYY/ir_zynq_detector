namespace eval irdet_bd {

proc apply_ac880_ps_preset {ps} {
    # These PS settings follow the local AC880 Xilinx Zynq bare-metal UART example.
    set_property -dict [list \
        CONFIG.PCW_ACT_APU_PERIPHERAL_FREQMHZ {666.666687} \
        CONFIG.PCW_ACT_CAN_PERIPHERAL_FREQMHZ {10.000000} \
        CONFIG.PCW_ACT_DCI_PERIPHERAL_FREQMHZ {10.158730} \
        CONFIG.PCW_ACT_ENET0_PERIPHERAL_FREQMHZ {10.000000} \
        CONFIG.PCW_ACT_ENET1_PERIPHERAL_FREQMHZ {10.000000} \
        CONFIG.PCW_ACT_FPGA0_PERIPHERAL_FREQMHZ {50.000000} \
        CONFIG.PCW_ACT_FPGA1_PERIPHERAL_FREQMHZ {10.000000} \
        CONFIG.PCW_ACT_FPGA2_PERIPHERAL_FREQMHZ {10.000000} \
        CONFIG.PCW_ACT_FPGA3_PERIPHERAL_FREQMHZ {10.000000} \
        CONFIG.PCW_ACT_PCAP_PERIPHERAL_FREQMHZ {200.000000} \
        CONFIG.PCW_ACT_QSPI_PERIPHERAL_FREQMHZ {10.000000} \
        CONFIG.PCW_ACT_SDIO_PERIPHERAL_FREQMHZ {10.000000} \
        CONFIG.PCW_ACT_SMC_PERIPHERAL_FREQMHZ {10.000000} \
        CONFIG.PCW_ACT_SPI_PERIPHERAL_FREQMHZ {10.000000} \
        CONFIG.PCW_ACT_TPIU_PERIPHERAL_FREQMHZ {200.000000} \
        CONFIG.PCW_ACT_TTC0_CLK0_PERIPHERAL_FREQMHZ {111.111115} \
        CONFIG.PCW_ACT_TTC0_CLK1_PERIPHERAL_FREQMHZ {111.111115} \
        CONFIG.PCW_ACT_TTC0_CLK2_PERIPHERAL_FREQMHZ {111.111115} \
        CONFIG.PCW_ACT_TTC1_CLK0_PERIPHERAL_FREQMHZ {111.111115} \
        CONFIG.PCW_ACT_TTC1_CLK1_PERIPHERAL_FREQMHZ {111.111115} \
        CONFIG.PCW_ACT_TTC1_CLK2_PERIPHERAL_FREQMHZ {111.111115} \
        CONFIG.PCW_ACT_UART_PERIPHERAL_FREQMHZ {100.000000} \
        CONFIG.PCW_ACT_WDT_PERIPHERAL_FREQMHZ {111.111115} \
        CONFIG.PCW_ARMPLL_CTRL_FBDIV {40} \
        CONFIG.PCW_CAN_PERIPHERAL_DIVISOR0 {1} \
        CONFIG.PCW_CAN_PERIPHERAL_DIVISOR1 {1} \
        CONFIG.PCW_CLK0_FREQ {50000000} \
        CONFIG.PCW_CLK1_FREQ {10000000} \
        CONFIG.PCW_CLK2_FREQ {10000000} \
        CONFIG.PCW_CLK3_FREQ {10000000} \
        CONFIG.PCW_CPU_CPU_PLL_FREQMHZ {1333.333} \
        CONFIG.PCW_CPU_PERIPHERAL_DIVISOR0 {2} \
        CONFIG.PCW_DCI_PERIPHERAL_DIVISOR0 {15} \
        CONFIG.PCW_DCI_PERIPHERAL_DIVISOR1 {7} \
        CONFIG.PCW_DDRPLL_CTRL_FBDIV {32} \
        CONFIG.PCW_DDR_DDR_PLL_FREQMHZ {1066.667} \
        CONFIG.PCW_DDR_PERIPHERAL_DIVISOR0 {2} \
        CONFIG.PCW_DDR_RAM_HIGHADDR {0x3FFFFFFF} \
        CONFIG.PCW_ENET0_PERIPHERAL_DIVISOR0 {1} \
        CONFIG.PCW_ENET0_PERIPHERAL_DIVISOR1 {1} \
        CONFIG.PCW_ENET1_PERIPHERAL_DIVISOR0 {1} \
        CONFIG.PCW_ENET1_PERIPHERAL_DIVISOR1 {1} \
        CONFIG.PCW_EN_UART1 {1} \
        CONFIG.PCW_FCLK0_PERIPHERAL_DIVISOR0 {6} \
        CONFIG.PCW_FCLK0_PERIPHERAL_DIVISOR1 {6} \
        CONFIG.PCW_FCLK1_PERIPHERAL_DIVISOR0 {1} \
        CONFIG.PCW_FCLK1_PERIPHERAL_DIVISOR1 {1} \
        CONFIG.PCW_FCLK2_PERIPHERAL_DIVISOR0 {1} \
        CONFIG.PCW_FCLK2_PERIPHERAL_DIVISOR1 {1} \
        CONFIG.PCW_FCLK3_PERIPHERAL_DIVISOR0 {1} \
        CONFIG.PCW_FCLK3_PERIPHERAL_DIVISOR1 {1} \
        CONFIG.PCW_FPGA_FCLK0_ENABLE {1} \
        CONFIG.PCW_FPGA_FCLK1_ENABLE {0} \
        CONFIG.PCW_FPGA_FCLK2_ENABLE {0} \
        CONFIG.PCW_FPGA_FCLK3_ENABLE {0} \
        CONFIG.PCW_I2C_PERIPHERAL_FREQMHZ {25} \
        CONFIG.PCW_IOPLL_CTRL_FBDIV {54} \
        CONFIG.PCW_IO_IO_PLL_FREQMHZ {1800.000} \
        CONFIG.PCW_MIO_48_DIRECTION {out} \
        CONFIG.PCW_MIO_48_IOTYPE {LVCMOS 1.8V} \
        CONFIG.PCW_MIO_48_PULLUP {enabled} \
        CONFIG.PCW_MIO_48_SLEW {slow} \
        CONFIG.PCW_MIO_49_DIRECTION {in} \
        CONFIG.PCW_MIO_49_IOTYPE {LVCMOS 1.8V} \
        CONFIG.PCW_MIO_49_PULLUP {enabled} \
        CONFIG.PCW_MIO_49_SLEW {slow} \
        CONFIG.PCW_MIO_TREE_PERIPHERALS {unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#UART 1#UART 1#unassigned#unassigned#unassigned#unassigned} \
        CONFIG.PCW_MIO_TREE_SIGNALS {unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#unassigned#tx#rx#unassigned#unassigned#unassigned#unassigned} \
        CONFIG.PCW_PCAP_PERIPHERAL_DIVISOR0 {9} \
        CONFIG.PCW_PRESET_BANK1_VOLTAGE {LVCMOS 1.8V} \
        CONFIG.PCW_QSPI_PERIPHERAL_DIVISOR0 {1} \
        CONFIG.PCW_SDIO_PERIPHERAL_DIVISOR0 {1} \
        CONFIG.PCW_SMC_PERIPHERAL_DIVISOR0 {1} \
        CONFIG.PCW_SPI_PERIPHERAL_DIVISOR0 {1} \
        CONFIG.PCW_TPIU_PERIPHERAL_DIVISOR0 {1} \
        CONFIG.PCW_UART1_GRP_FULL_ENABLE {0} \
        CONFIG.PCW_UART1_PERIPHERAL_ENABLE {1} \
        CONFIG.PCW_UART1_UART1_IO {MIO 48 .. 49} \
        CONFIG.PCW_UART_PERIPHERAL_DIVISOR0 {18} \
        CONFIG.PCW_UART_PERIPHERAL_FREQMHZ {100} \
        CONFIG.PCW_UART_PERIPHERAL_VALID {1} \
        CONFIG.PCW_UIPARAM_ACT_DDR_FREQ_MHZ {533.333374} \
        CONFIG.PCW_UIPARAM_DDR_BANK_ADDR_COUNT {3} \
        CONFIG.PCW_UIPARAM_DDR_CL {7} \
        CONFIG.PCW_UIPARAM_DDR_COL_ADDR_COUNT {10} \
        CONFIG.PCW_UIPARAM_DDR_CWL {6} \
        CONFIG.PCW_UIPARAM_DDR_DEVICE_CAPACITY {4096 MBits} \
        CONFIG.PCW_UIPARAM_DDR_DRAM_WIDTH {16 Bits} \
        CONFIG.PCW_UIPARAM_DDR_PARTNO {MT41K256M16 RE-125} \
        CONFIG.PCW_UIPARAM_DDR_ROW_ADDR_COUNT {15} \
        CONFIG.PCW_UIPARAM_DDR_SPEED_BIN {DDR3_1066F} \
        CONFIG.PCW_UIPARAM_DDR_T_FAW {40.0} \
        CONFIG.PCW_UIPARAM_DDR_T_RAS_MIN {35.0} \
        CONFIG.PCW_UIPARAM_DDR_T_RC {48.75} \
        CONFIG.PCW_UIPARAM_DDR_T_RCD {7} \
        CONFIG.PCW_UIPARAM_DDR_T_RP {7} \
    ] $ps
}

proc create_design {design_name} {
    if {[get_files -quiet ${design_name}.bd] ne ""} {
        remove_files [get_files ${design_name}.bd]
    }

    create_bd_design $design_name
    current_bd_design $design_name

    create_bd_intf_port -mode Master -vlnv xilinx.com:interface:ddrx_rtl:1.0 DDR
    create_bd_intf_port -mode Master -vlnv xilinx.com:display_processing_system7:fixedio_rtl:1.0 FIXED_IO

    set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 processing_system7_0]
    apply_ac880_ps_preset $ps
    set_property -dict [list \
        CONFIG.PCW_USE_M_AXI_GP0 {1} \
    ] $ps

    set dw3x3 [create_bd_cell -type module -reference mobilenet_dw3x3_channel_axi dw3x3_accel_0]
    set dw3x3_full [create_bd_cell -type module -reference mobilenet_dw3x3_channel_full_axi dw3x3_full_0]
    set axi_ic [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 axi_interconnect_0]
    set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {3}] $axi_ic
    set axi_pc [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_protocol_converter:2.1 axi_protocol_converter_0]
    set axi_full_pc [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_protocol_converter:2.1 axi_protocol_converter_1]
    set axi_gpio [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 axi_gpio_0]
    set_property -dict [list \
        CONFIG.C_ALL_OUTPUTS {1} \
        CONFIG.C_GPIO_WIDTH {32} \
        CONFIG.C_INTERRUPT_PRESENT {0} \
        CONFIG.C_IS_DUAL {0} \
    ] $axi_gpio
    set ps_reset [create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 proc_sys_reset_0]
    set reset_inv [create_bd_cell -type ip -vlnv xilinx.com:ip:util_vector_logic:2.0 reset_inv_0]
    set_property -dict [list CONFIG.C_OPERATION {not} CONFIG.C_SIZE {1}] $reset_inv
    set const_one [create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 xlconstant_0]
    set_property -dict [list CONFIG.CONST_VAL {1}] $const_one

    connect_bd_intf_net [get_bd_intf_ports DDR] [get_bd_intf_pins $ps/DDR]
    connect_bd_intf_net [get_bd_intf_ports FIXED_IO] [get_bd_intf_pins $ps/FIXED_IO]
    connect_bd_net [get_bd_pins $ps/FCLK_CLK0] [get_bd_pins $ps/M_AXI_GP0_ACLK]
    connect_bd_net [get_bd_pins $ps/FCLK_CLK0] [get_bd_pins $dw3x3/s_axi_aclk]
    connect_bd_net [get_bd_pins $ps/FCLK_CLK0] [get_bd_pins $dw3x3_full/s_axi_aclk]
    connect_bd_net [get_bd_pins $ps/FCLK_CLK0] [get_bd_pins $axi_pc/aclk]
    connect_bd_net [get_bd_pins $ps/FCLK_CLK0] [get_bd_pins $axi_full_pc/aclk]
    connect_bd_net [get_bd_pins $ps/FCLK_CLK0] [get_bd_pins $axi_gpio/s_axi_aclk]
    connect_bd_net [get_bd_pins $ps/FCLK_CLK0] [get_bd_pins $axi_ic/ACLK]
    connect_bd_net [get_bd_pins $ps/FCLK_CLK0] [get_bd_pins $axi_ic/S00_ACLK]
    connect_bd_net [get_bd_pins $ps/FCLK_CLK0] [get_bd_pins $axi_ic/M00_ACLK]
    connect_bd_net [get_bd_pins $ps/FCLK_CLK0] [get_bd_pins $axi_ic/M01_ACLK]
    connect_bd_net [get_bd_pins $ps/FCLK_CLK0] [get_bd_pins $axi_ic/M02_ACLK]
    connect_bd_net [get_bd_pins $ps/FCLK_CLK0] [get_bd_pins $ps_reset/slowest_sync_clk]
    connect_bd_net [get_bd_pins $ps/FCLK_RESET0_N] [get_bd_pins $reset_inv/Op1]
    connect_bd_net [get_bd_pins $reset_inv/Res] [get_bd_pins $ps_reset/ext_reset_in]
    connect_bd_net [get_bd_pins $const_one/dout] [get_bd_pins $ps_reset/dcm_locked]
    connect_bd_net [get_bd_pins $ps_reset/interconnect_aresetn] [get_bd_pins $axi_ic/ARESETN]
    connect_bd_net [get_bd_pins $ps_reset/interconnect_aresetn] [get_bd_pins $axi_ic/S00_ARESETN]
    connect_bd_net [get_bd_pins $ps_reset/interconnect_aresetn] [get_bd_pins $axi_ic/M00_ARESETN]
    connect_bd_net [get_bd_pins $ps_reset/interconnect_aresetn] [get_bd_pins $axi_ic/M01_ARESETN]
    connect_bd_net [get_bd_pins $ps_reset/interconnect_aresetn] [get_bd_pins $axi_ic/M02_ARESETN]
    connect_bd_net [get_bd_pins $ps_reset/peripheral_aresetn] [get_bd_pins $dw3x3/s_axi_aresetn]
    connect_bd_net [get_bd_pins $ps_reset/peripheral_aresetn] [get_bd_pins $dw3x3_full/s_axi_aresetn]
    connect_bd_net [get_bd_pins $ps_reset/peripheral_aresetn] [get_bd_pins $axi_gpio/s_axi_aresetn]
    connect_bd_net [get_bd_pins $ps_reset/interconnect_aresetn] [get_bd_pins $axi_pc/aresetn]
    connect_bd_net [get_bd_pins $ps_reset/interconnect_aresetn] [get_bd_pins $axi_full_pc/aresetn]
    connect_bd_intf_net [get_bd_intf_pins $ps/M_AXI_GP0] [get_bd_intf_pins $axi_ic/S00_AXI]
    connect_bd_intf_net [get_bd_intf_pins $axi_ic/M00_AXI] [get_bd_intf_pins $axi_pc/S_AXI]
    connect_bd_intf_net [get_bd_intf_pins $axi_pc/M_AXI] [get_bd_intf_pins $dw3x3/S_AXI]
    connect_bd_intf_net [get_bd_intf_pins $axi_ic/M01_AXI] [get_bd_intf_pins $axi_gpio/S_AXI]
    connect_bd_intf_net [get_bd_intf_pins $axi_ic/M02_AXI] [get_bd_intf_pins $axi_full_pc/S_AXI]
    connect_bd_intf_net [get_bd_intf_pins $axi_full_pc/M_AXI] [get_bd_intf_pins $dw3x3_full/S_AXI]

    assign_bd_address -offset 0x43C00000 -range 0x00010000 \
        -target_address_space [get_bd_addr_spaces $ps/Data] \
        [get_bd_addr_segs $dw3x3/S_AXI/reg0] -force
    assign_bd_address -offset 0x43C10000 -range 0x00010000 \
        -target_address_space [get_bd_addr_spaces $ps/Data] \
        [get_bd_addr_segs $dw3x3_full/S_AXI/reg0] -force
    assign_bd_address -offset 0x41200000 -range 0x00010000 \
        -target_address_space [get_bd_addr_spaces $ps/Data] \
        [get_bd_addr_segs $axi_gpio/S_AXI/Reg] -force

    validate_bd_design
    save_bd_design
    return [current_bd_design]
}

}
