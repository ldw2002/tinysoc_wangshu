# Emit ROM and DDR images for the BC NPU case.  The whole case working set is
# in DDR, so sram.bin stays a one-word placeholder and ddr.bin carries the
# .vta_data section.
SRAM_IMAGE := sram.bin
DDR_IMAGE := ddr.bin

case_firmware: $(SRAM_IMAGE) $(DDR_IMAGE)

bios.bin: bios.elf
	$(OBJCOPY) -O binary --remove-section=.vta_data $< $@
ifneq ($(OS),Windows_NT)
	chmod -x $@
endif
ifeq ($(CPUENDIANNESS),little)
	$(PYTHON) -m litex.soc.software.crcfbigen $@ --little
else
	$(PYTHON) -m litex.soc.software.crcfbigen $@
endif

# The SoC preloader always reads a SRAM image; the BC case does not use SRAM
# storage, so write a single zero word to keep the file well formed.
$(SRAM_IMAGE): bios.elf
	printf '\0\0\0\0' > $@
ifneq ($(OS),Windows_NT)
	chmod -x $@
endif

$(DDR_IMAGE): bios.elf
	$(OBJCOPY) -O binary --only-section=.vta_data $< $@
ifneq ($(OS),Windows_NT)
	chmod -x $@
endif
