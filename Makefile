VARIANTS := $(patsubst variants/%.yaml,%,$(wildcard variants/*.yaml))
V ?= normal
LOC ?=
SITES ?= linkedin,indeed,hellowork
LIMIT ?= 10
LANGS ?= en,fr
COUNTRY ?= France
JOB ?=

.DEFAULT_GOAL := help
.PHONY: help render render-all all watch ats ats-all job search score extract reset hooks-maintainer

help:
	@echo "RenderCV AI Toolkit — Available commands:"
	@echo "  make extract                                  Extract text/links from raw files in input/"
	@echo "  make render V=<variant>                       Render variants/<V>.yaml to PDF/HTML/MD/PNG"
	@echo "  make render-all                               Render all variants in variants/*.yaml"
	@echo "  make watch V=<variant>                        Live-preview variants/<V>.yaml while editing"
	@echo "  make ats V=<variant> [JOB=jobs/<job>.md]      Render + run ATS & job keyword check"
	@echo "  make ats-all                                  Render + run ATS check on all variants"
	@echo "  make job URL=\"https://...\"                    Import a job posting by URL into jobs/"
	@echo "  make search Q=\"...\" [LOC=\"...\"] [COUNTRY=...] Search job boards & score against variants"
	@echo "  make score [JOB=jobs/<job>.md]                Score archived jobs against all variants"
	@echo "  make reset                                    Remove personal files to start fresh"
	@echo "  make hooks-maintainer                         Template maintainers only: block committing personal data"

render:
	@if [ -z "$(V)" ]; then echo "Usage: make render V=<variant>"; exit 1; fi
	uv run rendercv render variants/$(V).yaml

watch:
	@if [ -z "$(V)" ]; then echo "Usage: make watch V=<variant>"; exit 1; fi
	uv run rendercv render variants/$(V).yaml --watch

render-all all:
	@if [ -z "$(VARIANTS)" ]; then echo "No variants found in variants/*.yaml"; exit 0; fi
	@for v in $(VARIANTS); do \
		echo "==> $$v"; \
		uv run rendercv render variants/$$v.yaml || exit 1; \
	done

ats:
	@if [ -z "$(V)" ]; then echo "Usage: make ats V=<variant> [JOB=jobs/<job>.md]"; exit 1; fi
	uv run rendercv render variants/$(V).yaml
	uv run python scripts/ats_check.py variants/$(V).yaml --langs "$(LANGS)" $(foreach j,$(JOB),--job $(j))

ats-all:
	@if [ -z "$(VARIANTS)" ]; then echo "No variants found in variants/*.yaml"; exit 0; fi
	@status=0; \
	for v in $(VARIANTS); do \
		echo "==> $$v"; \
		uv run rendercv render variants/$$v.yaml || { status=1; continue; }; \
		uv run python scripts/ats_check.py variants/$$v.yaml --langs "$(LANGS)" || status=1; \
	done; \
	exit $$status

job:
	@if [ -z "$(URL)" ]; then echo "Usage: make job URL=\"https://...\""; exit 1; fi
	uv run python scripts/jobs.py import $(foreach u,$(URL),'$(u)') --langs "$(LANGS)"

search:
	@if [ -z "$(Q)" ]; then echo "Usage: make search Q=\"<query>\" [LOC=\"<location>\"] [COUNTRY=<country>] [SITES=...]"; exit 1; fi
	uv run python scripts/jobs.py search "$(Q)" --location "$(LOC)" --country "$(COUNTRY)" --sites "$(SITES)" --limit $(LIMIT) --langs "$(LANGS)" $(if $(SAVE),--save "$(SAVE)")

score:
	uv run python scripts/jobs.py score $(JOB) --langs "$(LANGS)"

extract:
	uv run python scripts/extract_input.py

reset:
	uv run python scripts/reset_workspace.py

hooks-maintainer:
	git config core.hooksPath .githooks
	@echo "Maintainer Git hooks enabled (.githooks): commits of personal files in input/, variants/, jobs/ are now blocked"
