PYTHON ?= .venv/bin/python
CONFIG ?= config/ty1b_simple_npu.json
# DrvFS files receive timestamps from Windows. If the WSL clock lags behind
# the host, Meson rejects freshly generated files as being "in the future".
# Keep generated output on WSL's native filesystem by default. Use a persistent
# cache so a stopped WSL instance does not discard a simulator built in /tmp.
ifdef WSL_DISTRO_NAME
BUILD_DIR ?= $(HOME)/.cache/tinyvta-simple-soc/build
else
BUILD_DIR ?= build
endif
CASE_PATH = $(if $(wildcard $(CASE)),$(abspath $(CASE)),$(abspath cases/$(CASE)))
SYNTH_ENV_DIR ?= $(HOME)/.local/share/tinysoc-synth
SYNTH_PYTHON ?= $(SYNTH_ENV_DIR)/venv/bin/python
SYNTH_YOSYS ?= $(SYNTH_ENV_DIR)/venv/bin/yowasp-yosys
SYNTH_PROFILE ?= vta-local
SYNTH_STAGE ?= coarse
DC_PYTHON ?= python3
DC_SHELL ?= dc_shell
DC_STAGE ?= elaborate
DC_CONFIG ?=

.PHONY: env-check check generate rtl rtl-sync rtl-check interface-sync interface-check interface-test sram-model-test synth-setup synth synth-dc-prepare synth-dc sim run

env-check:
	@if [ ! -x "$(PYTHON)" ] || [ ! -s "$(PYTHON)" ]; then \
		echo "invalid SoC Python environment: $(PYTHON)" >&2; \
		echo "recreate soc/.venv with Python 3.10; copied virtualenvs are not portable" >&2; \
		exit 2; \
	fi
	$(PYTHON) tools/check_env.py

check:
	$(PYTHON) tools/soc_config.py check --config $(CONFIG)

generate: env-check check rtl-check
	$(PYTHON) tools/soc_config.py generate --config $(CONFIG) --output $(BUILD_DIR)/generated
	$(PYTHON) litex/vta_soc.py --config $(CONFIG) --build-dir $(BUILD_DIR)/architecture

# This minimal package consumes frozen RTL. After editing vta.v, synchronize
# its checksum, manifest metadata, and generated interface mapping.
rtl: env-check
	$(PYTHON) tools/update_vta_rtl_package.py $(RTL_ARGS)
	$(PYTHON) tools/update_vta_interface.py --config $(CONFIG) $(INTERFACE_ARGS)

rtl-sync:
	$(PYTHON) tools/update_vta_rtl_package.py $(RTL_ARGS)

interface-sync: env-check
	$(PYTHON) tools/update_vta_interface.py --config $(CONFIG) $(INTERFACE_ARGS)

interface-check: env-check
	$(PYTHON) tools/update_vta_interface.py --config $(CONFIG) --check

interface-test: env-check
	$(PYTHON) -m unittest discover -s tests -v

# Standalone SRAM contract tests; requires Icarus Verilog, not the LiteX environment.
sram-model-test:
	$(PYTHON) tools/test_sram_models.py $(SRAM_TEST_ARGS)

# Generic synthesis is independent of LiteX/Verilator and preserves RAM arrays.
synth-setup:
	SYNTH_BOOTSTRAP_PYTHON="$(SYNTH_BOOTSTRAP_PYTHON)" SYNTH_ENV_DIR="$(SYNTH_ENV_DIR)" bash scripts/setup_synth_env.sh

synth:
	"$(SYNTH_PYTHON)" tools/run_synthesis.py --profile "$(SYNTH_PROFILE)" --stage "$(SYNTH_STAGE)" --yosys "$(SYNTH_YOSYS)" $(SYNTH_ARGS)

# DC reads the same RTL profiles directly; neither Yosys nor LiteX is required.
synth-dc-prepare:
	"$(DC_PYTHON)" tools/run_dc_synthesis.py --profile "$(SYNTH_PROFILE)" --stage "$(DC_STAGE)" $(if $(DC_CONFIG),--config "$(DC_CONFIG)") --prepare-only $(DC_ARGS)

synth-dc:
	"$(DC_PYTHON)" tools/run_dc_synthesis.py --profile "$(SYNTH_PROFILE)" --stage "$(DC_STAGE)" $(if $(DC_CONFIG),--config "$(DC_CONFIG)") --dc "$(DC_SHELL)" $(DC_ARGS)

rtl-check: env-check
	$(PYTHON) tools/update_vta_rtl_package.py --check
	$(PYTHON) tools/update_vta_interface.py --config $(CONFIG) --check

sim: env-check check rtl-check
	@if [ -z "$(CASE)" ]; then \
		echo "usage: make sim CASE=case-name-or-path" >&2; exit 2; \
	elif ls "$(CASE_PATH)"/*_test.c >/dev/null 2>&1; then \
		./scripts/sim_build.sh $(BUILD_DIR)/case-$(notdir $(CASE_PATH)) $(CONFIG) "$(CASE_PATH)"; \
	else \
		echo "invalid case (expected *_test.c): $(CASE_PATH)" >&2; exit 2; \
	fi

run:
	@if [ -z "$(CASE)" ]; then \
		echo "usage: make run CASE=case-name-or-path" >&2; exit 2; \
	elif ls "$(CASE_PATH)"/*_test.c >/dev/null 2>&1; then \
		./scripts/sim_run.sh $(BUILD_DIR)/case-$(notdir $(CASE_PATH))/gateware; \
	else \
		echo "invalid case (expected *_test.c): $(CASE_PATH)" >&2; exit 2; \
	fi
