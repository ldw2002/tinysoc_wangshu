#include <stdint.h>

/* The simple profile deliberately has no timer CSR. LiteX's generic BIOS
 * still emits these accessors, so keep link compatibility without adding
 * timer hardware. */
void timer0_en_write(uint32_t value) { (void)value; }
void timer0_reload_write(uint32_t value) { (void)value; }
void timer0_load_write(uint32_t value) { (void)value; }
void timer0_update_value_write(uint32_t value) { (void)value; }
uint32_t timer0_value_read(void) { return 0; }
