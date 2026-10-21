#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

#include "mlperf_resnet8_qconv_test.h"
#include "vta_case_platform.h"

int main(void) {
    struct vta_case_job job = {
        .insn_count = MLPERF_RESNET8_QCONV_INSN_COUNT,
        .insn = {mlperf_resnet8_qconv_insn, sizeof(mlperf_resnet8_qconv_insn)},
        .uop = {mlperf_resnet8_qconv_uop, sizeof(mlperf_resnet8_qconv_uop)},
        .inp = {mlperf_resnet8_qconv_inp, sizeof(mlperf_resnet8_qconv_inp)},
        .wgt = {mlperf_resnet8_qconv_wgt, sizeof(mlperf_resnet8_qconv_wgt)},
        .acc = {mlperf_resnet8_qconv_acc, sizeof(mlperf_resnet8_qconv_acc)},
        .out = mlperf_resnet8_qconv_out,
        .out_size = sizeof(mlperf_resnet8_qconv_out),
    };
    uint32_t insn = vta_case_dma_address(job.insn.cpu_address);
    uint32_t uop = vta_case_dma_address(job.uop.cpu_address);
    uint32_t inp = vta_case_dma_address(job.inp.cpu_address);
    uint32_t wgt = vta_case_dma_address(job.wgt.cpu_address);
    uint32_t acc = vta_case_dma_address(job.acc.cpu_address);
    uint32_t out = vta_case_dma_address(job.out);

    printf("VTA case mlperf_resnet8_qconv: insn=%u\r\n", (unsigned int)MLPERF_RESNET8_QCONV_INSN_COUNT);
    printf("insn=%08x uop=%08x inp=%08x\r\n",
           (unsigned int)insn, (unsigned int)uop, (unsigned int)inp);
    printf("wgt=%08x acc=%08x out=%08x\r\n",
           (unsigned int)wgt, (unsigned int)acc, (unsigned int)out);

    uint32_t cycles = 0;
    int run_status = vta_case_run(&job, &cycles);
    if (run_status != VTA_CASE_OK) {
        printf("VTA case FAIL: platform status=%d\r\n", run_status);
        vta_case_finish(run_status);
        return 1;
    }
    printf("VTA case counters: cycles=%u insns=%u\r\n",
           (unsigned int)cycles, (unsigned int)MLPERF_RESNET8_QCONV_INSN_COUNT);
    for (size_t offset = 0; offset < MLPERF_RESNET8_QCONV_EXPECTED_SIZE; offset += 4U) {
        uint32_t actual = *(volatile uint32_t *)((uintptr_t)out + offset);
        uint32_t expected = *(const uint32_t *)((uintptr_t)mlperf_resnet8_qconv_expected + offset);
        if (actual != expected) {
            printf("VTA case FAIL: offset=0x%zx expected=%08x actual=%08x\r\n",
                   offset, (unsigned int)expected, (unsigned int)actual);
            vta_case_finish(1);
            return 1;
        }
    }
    printf("VTA case PASS\r\n");
    vta_case_finish(0);
    return 0;
}
