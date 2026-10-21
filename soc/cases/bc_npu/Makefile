# BC NPU case for the TY1B-simple VTA SoC.
#
# This case keeps its whole working set in DDR (it exceeds the 128 KiB SRAM),
# so it uses the BC-specific linker script and image rules.
CASE_SOURCE_DIR := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
SOC_DIR := $(abspath $(CASE_SOURCE_DIR)/../..)
ifeq ($(abspath $(CURDIR)),$(CASE_SOURCE_DIR))
.PHONY: rtl sim run
rtl:
	$(MAKE) -C $(SOC_DIR) rtl
sim:
	$(MAKE) -C $(SOC_DIR) sim CASE=$(CASE_SOURCE_DIR)
run:
	$(MAKE) -C $(SOC_DIR) run CASE=$(CASE_SOURCE_DIR)
else
SOC_DIRECTORY := $(SOC_DIR)
LITEX_BIOS_DIRECTORY := $(SOC_DIRECTORY)/.venv/lib/python3.10/site-packages/litex/soc/software/bios
# This profile has no dedicated SRAM-only firmware flow, so build the case
# image directly instead of using LiteX's memusage helper.
.DEFAULT_GOAL := case_firmware
.PHONY: case_firmware
case_firmware: bios.bin
override LSCRIPT = ../../linker/vta_bc_case.ld
include $(LITEX_BIOS_DIRECTORY)/Makefile
include $(SOC_DIR)/firmware/vta_bc_case_images.mk
CFLAGS += -I$(LITEX_BIOS_DIRECTORY) -I$(CASE_SOURCE_DIR) -DVTA_CASE_LITEX_SIM=1
OBJECTS += vta_case_platform.o ty1b_simple_no_timer.o
vta_case_platform.o: $(SOC_DIR)/firmware/templates/vta_case_platform.c
vta_case_platform.o: $(SOC_DIR)/firmware/templates/vta_case_platform.h
bios.elf: ty1b_simple_no_timer.o
bios.elf: vta_case_platform.o
override VPATH := $(CASE_SOURCE_DIR):$(SOC_DIR)/firmware:$(LITEX_BIOS_DIRECTORY):$(LITEX_BIOS_DIRECTORY)/cmds:$(CPU_DIRECTORY)
main.o: $(CASE_SOURCE_DIR)/bc_npu_test.c
	$(compile)
endif
