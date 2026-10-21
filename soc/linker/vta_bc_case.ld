INCLUDE generated/output_format.ld
ENTRY(_start)
INCLUDE generated/regions.ld

SECTIONS
{
	.text : {
		_ftext = .;
		KEEP(*(.isr_vector))
		*crt0*(.text)
		KEEP(*crt0*(.text))
		KEEP(*(.text.isr))
		*(.text .stub .text.* .gnu.linkonce.t.*)
		_etext = .;
	} > rom

	.rodata : {
		. = ALIGN(8); _frodata = .;
		*(.rodata .rodata.* .gnu.linkonce.r.*)
		*(.srodata .srodata.*)
		*(.rodata1) *(.got .got.*) *(.toc .toc.*)
		FILL(0); . = ALIGN(8); _erodata = .;
	} > rom

	.commands : {
		PROVIDE_HIDDEN(__bios_cmd_start = .);
		KEEP(*(.bios_cmd))
		PROVIDE_HIDDEN(__bios_cmd_end = .);
	} > rom

	.init : {
		PROVIDE_HIDDEN(__bios_init_start = .);
		KEEP(*(.bios_init))
		PROVIDE_HIDDEN(__bios_init_end = .);
	} > rom

	/* Keep crt0's ROM-to-RAM copy range empty; the case image is preloaded by
	 * the simulation memory model instead. */
	.data_copy_none : {
		. = ALIGN(8);
		_fdata = .;
		_edata = .;
		_fdata_rom = .;
		_edata_rom = .;
	} > rom

	/* BC NPU working set: insn/uop/buf/wgt/acc plus the golden reference.
	 * It is larger than the on-chip SRAM, so everything lives in DDR. */
	.vta_data : {
		. = ALIGN(128); _frodata_ai = .;
		KEEP(*(.rodata_ai .rodata_ai.*))
		. = ALIGN(8); _erodata_ai = .; _fdata_ai = .;
		KEEP(*(.data_ai .data_ai.init))
		. = ALIGN(8); _edata_ai_init = .;
		KEEP(*(.data_ai.out))
		. = ALIGN(8); _edata_ai = .;
		*(.data .data.* .gnu.linkonce.d.*)
		*(.data1) *(.sdata .sdata.* .gnu.linkonce.s.*)
		FILL(0); . = ALIGN(8);
	} > main_ram

	.bss : {
		. = ALIGN(8); _fbss = .;
		*(.dynsbss) *(.sbss .sbss.* .gnu.linkonce.sb.*) *(.scommon)
		*(.dynbss) *(.bss .bss.* .gnu.linkonce.b.*) *(COMMON)
		. = ALIGN(8); _ebss = .; _end = .;
	} > main_ram

	/DISCARD/ : { *(.eh_frame) *(.comment) }
}

PROVIDE(_fstack = ORIGIN(main_ram) + LENGTH(main_ram));

ASSERT(_fdata == _edata, "VTA case must not copy initialized data with the CPU")
ASSERT(LOADADDR(.vta_data) == ADDR(.vta_data),
       "VTA case data must be loaded directly into DDR")
