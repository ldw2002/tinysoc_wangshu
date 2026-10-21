# Standalone synthesis entry points. Run from soc/: make -f synth/server.mk ...
# Does not replace or include the server's existing SoC Makefile.
SYNTH_ENV_DIR ?= $(HOME)/.local/share/tinysoc-synth-centos7
SYNTH_PYTHON ?= $(SYNTH_ENV_DIR)/venv/bin/python
SYNTH_YOSYS ?= $(SYNTH_ENV_DIR)/venv/bin/yowasp-yosys
SYNTH_PROFILE ?= vcr
SYNTH_STAGE ?= coarse
# Keep compiled Wasm caches off quota-limited home directories by default.
# Override this to a project/scratch path when running a reference project in HOME.
YOWASP_CACHE_DIR ?= $(abspath build/yowasp-cache)
export YOWASP_CACHE_DIR
DC_PYTHON ?= $(SYNTH_PYTHON)
DC_SHELL ?= dc_shell
DC_STAGE ?= elaborate
DC_CONFIG ?=

.PHONY: synth synth-dc-prepare synth-dc
synth:
	"$(SYNTH_PYTHON)" tools/run_synthesis.py --profile "$(SYNTH_PROFILE)" --stage "$(SYNTH_STAGE)" --yosys "$(SYNTH_YOSYS)" $(SYNTH_ARGS)

synth-dc-prepare:
	"$(DC_PYTHON)" tools/run_dc_synthesis.py --profile "$(SYNTH_PROFILE)" --stage "$(DC_STAGE)" $(if $(DC_CONFIG),--config "$(DC_CONFIG)") --prepare-only $(DC_ARGS)

synth-dc:
	"$(DC_PYTHON)" tools/run_dc_synthesis.py --profile "$(SYNTH_PROFILE)" --stage "$(DC_STAGE)" $(if $(DC_CONFIG),--config "$(DC_CONFIG)") --dc "$(DC_SHELL)" $(DC_ARGS)
