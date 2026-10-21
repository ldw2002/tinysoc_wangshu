# Emit independent ROM, SRAM and DDR images from the case ELF.  The working
# set goes to SRAM and the cold golden data goes to DDR, while both stay out
# of bios.bin to avoid binary holes and CPU startup copies.
SRAM_IMAGE := sram.bin
DDR_IMAGE := ddr.bin

case_firmware: $(SRAM_IMAGE) $(DDR_IMAGE)

bios.bin: bios.elf
	$(OBJCOPY) -O binary --remove-section=.vta_data --remove-section=.expected_data $< $@
ifneq ($(OS),Windows_NT)
	chmod -x $@
endif
ifeq ($(CPUENDIANNESS),little)
	$(PYTHON) -m litex.soc.software.crcfbigen $@ --little
else
	$(PYTHON) -m litex.soc.software.crcfbigen $@
endif

$(SRAM_IMAGE): bios.elf
	$(OBJCOPY) -O binary --only-section=.vta_data $< $@
ifneq ($(OS),Windows_NT)
	chmod -x $@
endif

$(DDR_IMAGE): bios.elf
	$(OBJCOPY) -O binary --only-section=.expected_data $< $@
ifneq ($(OS),Windows_NT)
	chmod -x $@
endif
