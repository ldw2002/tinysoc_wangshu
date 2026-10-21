#include "vta_case_platform.h"

#if defined(VTA_CASE_LITEX_SIM)
#include <sim_debug.h>
#include <system.h>
#endif

enum {
    VTA_REG_CONTROL = 0x00u,
    VTA_REG_CYCLE_COUNT = 0x04u,
    VTA_REG_INSN_COUNT = 0x08u,
    VTA_REG_INSN_ADDR = 0x0cu,
    VTA_REG_UOP_ADDR = 0x10u,
    VTA_REG_INP_ADDR = 0x14u,
    VTA_REG_WGT_ADDR = 0x18u,
    VTA_REG_ACC_ADDR = 0x1cu,
    VTA_REG_OUT_ADDR = 0x20u,
    VTA_CONTROL_START = 1u,
    VTA_CONTROL_DONE = 2u,
};

volatile uint32_t vta_case_result = VTA_CASE_RESULT_NOT_RUN;

__attribute__((weak)) uint32_t vta_case_dma_address(const void *cpu_address) {
    return (uint32_t)(uintptr_t)cpu_address;
}

__attribute__((weak)) void vta_case_cache_clean(
    const void *cpu_address, size_t size) {
    (void)cpu_address;
    (void)size;
    __sync_synchronize();
#if defined(VTA_CASE_LITEX_SIM)
    flush_cpu_dcache();
#endif
    __sync_synchronize();
}

__attribute__((weak)) void vta_case_cache_invalidate(
    void *cpu_address, size_t size) {
    (void)cpu_address;
    (void)size;
    __sync_synchronize();
#if defined(VTA_CASE_LITEX_SIM)
    flush_cpu_dcache();
#endif
    __sync_synchronize();
}

__attribute__((weak)) uint32_t vta_case_reg_read(uint32_t offset) {
    volatile uint32_t *reg =
        (volatile uint32_t *)(uintptr_t)(VTA_VCR_BASE + offset);
    return *reg;
}

__attribute__((weak)) void vta_case_reg_write(
    uint32_t offset, uint32_t value) {
    volatile uint32_t *reg =
        (volatile uint32_t *)(uintptr_t)(VTA_VCR_BASE + offset);
    *reg = value;
}

static void prepare_buffer(const struct vta_case_buffer *buffer) {
    vta_case_cache_clean(buffer->cpu_address, buffer->size);
}

int vta_case_run(const struct vta_case_job *job, uint32_t *cycles) {
    if (job == NULL || job->insn_count == 0u || job->out == NULL ||
        job->out_size == 0u) {
        return VTA_CASE_ERR_ARGUMENT;
    }
    if ((vta_case_reg_read(VTA_REG_CONTROL) & VTA_CONTROL_START) != 0u) {
        return VTA_CASE_ERR_BUSY;
    }

    prepare_buffer(&job->insn);
    prepare_buffer(&job->uop);
    prepare_buffer(&job->inp);
    prepare_buffer(&job->wgt);
    prepare_buffer(&job->acc);
    vta_case_cache_clean(job->out, job->out_size);

    vta_case_reg_write(VTA_REG_INSN_COUNT, job->insn_count);
    vta_case_reg_write(VTA_REG_INSN_ADDR,
                       vta_case_dma_address(job->insn.cpu_address));
    vta_case_reg_write(VTA_REG_UOP_ADDR,
                       vta_case_dma_address(job->uop.cpu_address));
    vta_case_reg_write(VTA_REG_INP_ADDR,
                       vta_case_dma_address(job->inp.cpu_address));
    vta_case_reg_write(VTA_REG_WGT_ADDR,
                       vta_case_dma_address(job->wgt.cpu_address));
    vta_case_reg_write(VTA_REG_ACC_ADDR,
                       vta_case_dma_address(job->acc.cpu_address));
    vta_case_reg_write(VTA_REG_OUT_ADDR, vta_case_dma_address(job->out));
    __sync_synchronize();
    vta_case_reg_write(VTA_REG_CONTROL, VTA_CONTROL_START);

    for (uint32_t poll = 0; poll < VTA_CASE_TIMEOUT_POLLS; ++poll) {
        if ((vta_case_reg_read(VTA_REG_CONTROL) & VTA_CONTROL_DONE) != 0u) {
            if (cycles != NULL) {
                *cycles = vta_case_reg_read(VTA_REG_CYCLE_COUNT);
            }
            vta_case_cache_invalidate(job->out, job->out_size);
            return VTA_CASE_OK;
        }
    }
    return VTA_CASE_ERR_TIMEOUT;
}

void vta_case_finish(int status) {
    vta_case_result = status == 0 ? VTA_CASE_RESULT_PASS : VTA_CASE_RESULT_FAIL;
    __sync_synchronize();
#if defined(VTA_CASE_LITEX_SIM)
    sim_finish();
#endif
}
