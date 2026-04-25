#include "ir_pl_dw3x3_selftest.h"

#include "sleep.h"
#include "xil_printf.h"
#include "xparameters.h"
#include "xstatus.h"
#include "xuartps.h"

#ifndef XPAR_XUARTPS_0_DEVICE_ID
#error "PS UART is not enabled in the exported hardware platform."
#endif

#define IRDET_UART_DEVICE_ID  XPAR_XUARTPS_0_DEVICE_ID
#define IRDET_UART_BAUDRATE   921600U

static XUartPs g_uart;

static int uart_init(uint16_t device_id, uint32_t baudrate) {
    XUartPs_Config* config_ptr;
    int status;

    config_ptr = XUartPs_LookupConfig(device_id);
    if (config_ptr == 0) {
        return -1;
    }

    status = XUartPs_CfgInitialize(&g_uart, config_ptr, config_ptr->BaseAddress);
    if (status != XST_SUCCESS) {
        return -2;
    }

    XUartPs_SetBaudRate(&g_uart, baudrate);
    XUartPs_SetOperMode(&g_uart, XUARTPS_OPER_MODE_NORMAL);
    return 0;
}

int main(void) {
    int status;

    status = uart_init(IRDET_UART_DEVICE_ID, IRDET_UART_BAUDRATE);
    if (status != 0) {
        xil_printf("UART init failed, rc=%d\r\n", status);
        return status;
    }

    xil_printf("\r\nIR detector PL dw3x3 bare-metal selftest\r\n");
    xil_printf("This app assumes the PL bitstream is already programmed.\r\n");
    irdet_dw3x3_pl_selftest_report();

    status = irdet_dw3x3_pl_selftest_run();
    xil_printf("PL dw3x3 selftest rc=%d\r\n", status);

    while (1) {
        usleep(1000000U);
    }
}
