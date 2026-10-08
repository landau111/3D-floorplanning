.DEFAULT_GOAL := explore
.PHONY: explore quick optimize test help hotspot test-hotspot

ifeq ($(OS),Windows_NT)
SHELL := cmd.exe
.SHELLFLAGS := /C
RUN = run.cmd
else
PYTHON ?= python3
RUN = "$(PYTHON)" folding_dse/run.py
explore quick optimize: hotspot
endif

hotspot:
ifeq ($(OS),Windows_NT)
	$(RUN) hotspot
else
	$(MAKE) -C third_party/HotSpot hotspot SUPERLU=0 VERBOSE=0 EXTRAFLAGS=-std=gnu99
endif

test-hotspot: hotspot
	$(RUN) test-hotspot $(ARGS)

# Examples: make explore; make quick; make explore ARGS="--steps 10000 --restarts 5"
explore quick optimize test help:
	$(RUN) $@ $(ARGS)
