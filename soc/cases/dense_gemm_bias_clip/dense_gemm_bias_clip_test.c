#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

#include "dense_gemm_bias_clip_test.h"
#include "vta_case_platform.h"

int main(void) {
    struct vta_case_job job = {
        .insn_count = DENSE_GEMM_BIAS_CLIP_INSN_COUNT,
        .insn = {dense_gemm_bias_clip_insn, sizeof(dense_gemm_bias_clip_insn)},
        .uop = {dense_gemm_bias_clip_uop, sizeof(dense_gemm_bias_clip_uop)},
        .inp = {dense_gemm_bias_clip_inp, sizeof(dense_gemm_bias_clip_inp)},
        .wgt = {dense_gemm_bias_clip_wgt, sizeof(dense_gemm_bias_clip_wgt)},
        .acc = {dense_gemm_bias_clip_acc, sizeof(dense_gemm_bias_clip_acc)},
        .out = dense_gemm_bias_clip_out,
        .out_size = sizeof(dense_gemm_bias_clip_out),
    };
    uint32_t insn = vta_case_dma_address(job.insn.cpu_address);
    uint32_t uop = vta_case_dma_address(job.uop.cpu_address);
    uint32_t inp = vta_case_dma_address(job.inp.cpu_address);
    uint32_t wgt = vta_case_dma_address(job.wgt.cpu_address);
    uint32_t acc = vta_case_dma_address(job.acc.cpu_address);
    uint32_t out = vta_case_dma_address(job.out);

    printf("VTA case dense_gemm_bias_clip: insn=%u\r\n", (unsigned int)DENSE_GEMM_BIAS_CLIP_INSN_COUNT);
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
           (unsigned int)cycles, (unsigned int)DENSE_GEMM_BIAS_CLIP_INSN_COUNT);

    for (size_t offset = 0; offset < DENSE_GEMM_BIAS_CLIP_EXPECTED_SIZE; offset += 4U) {
        uint32_t actual = *(volatile uint32_t *)((uintptr_t)dense_gemm_bias_clip_out + offset);
        uint32_t expected = *(const uint32_t *)((uintptr_t)dense_gemm_bias_clip_expected + offset);
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
