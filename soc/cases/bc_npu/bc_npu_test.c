#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

#include "bc_npu_model.h"
#include "bc_test_data.h"
#include "vta_case_platform.h"

int main(void) {
    uint32_t check_flag = 0x0;

    if (bc_inp_data[0] == 0) {
        vta_case_finish(0);
        return 0;
    }

    printf("VTA case bc_npu: start\r\n");
    npu_run((void *)bc_inp_data, (void *)bc_out_data);

    int8_t *pRef = (int8_t *)(bc_ref_data);
    int8_t *pOut = (int8_t *)(bc_out_data);
    for (int32_t i = 0; i < 2; i++) {
        if (pRef[i] != pOut[i]) {
            check_flag = 0x1;
            break;
        }
    }

    if (check_flag) {
        printf("VTA case FAIL\r\n");
        vta_case_finish(1);
        return 1;
    }
    printf("VTA case PASS\r\n");
    vta_case_finish(0);
    return 0;
}
