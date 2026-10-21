#pragma once

#include <stddef.h>
#include <stdint.h>

#if defined(VTA_CASE_LITEX_SIM)
#include <generated/soc.h>
#endif

#ifndef VTA_VCR_BASE
#define VTA_VCR_BASE 0xf0001000u
#endif

#ifndef VTA_CASE_TIMEOUT_POLLS
#define VTA_CASE_TIMEOUT_POLLS 100000000u
#endif

enum {
    VTA_CASE_OK = 0,
    VTA_CASE_ERR_ARGUMENT = -1,
    VTA_CASE_ERR_BUSY = -2,
    VTA_CASE_ERR_TIMEOUT = -3,
};

enum {
    VTA_CASE_RESULT_NOT_RUN = 0x56544100u,
    VTA_CASE_RESULT_PASS = 0x56544150u,
    VTA_CASE_RESULT_FAIL = 0x56544146u,
};

struct vta_case_buffer {
    const void *cpu_address;
    size_t size;
};

struct vta_case_job {
    uint32_t insn_count;
    struct vta_case_buffer insn;
    struct vta_case_buffer uop;
    struct vta_case_buffer inp;
    struct vta_case_buffer wgt;
    struct vta_case_buffer acc;
    void *out;
    size_t out_size;
};

extern volatile uint32_t vta_case_result;

/* Override these weak hooks in the remote TY1B board support package when
 * CPU and NPU addresses differ or the DMA path is not cache coherent. */
uint32_t vta_case_dma_address(const void *cpu_address);
void vta_case_cache_clean(const void *cpu_address, size_t size);
void vta_case_cache_invalidate(void *cpu_address, size_t size);
uint32_t vta_case_reg_read(uint32_t offset);
void vta_case_reg_write(uint32_t offset, uint32_t value);

int vta_case_run(const struct vta_case_job *job, uint32_t *cycles);
void vta_case_finish(int status);
