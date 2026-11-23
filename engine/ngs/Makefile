# Makefile -- NGS engine (meta-app M1 entry for the fleet bake-off).
#
# Targets:
#   make            build the static library + run all gates
#   make lib        build libnougenshards.a only
#   make check      header gate: spec's ngs_header_check.c + Phoebus's
#                   header_contract.c (C11 and C++11) against include/ngs.h
#   make test       build + run the M1 unit suite
#   make crash      build + run the crash/tamper harness
#   make standalone prove the amalgamation compiles on its own
#
# The engine itself is strict ISO C11: -std=c11 -pedantic. The test
# programs use POSIX facilities (fork, mkdtemp) and say so via
# -D_DEFAULT_SOURCE.

CC      ?= cc
CXX     ?= c++
AR      ?= ar
CFLAGS  ?= -O2 -g
WARN     = -Wall -Wextra -pedantic -Werror
STD      = -std=c11
INC      = -I include
BUILD    = build
SRC      = src/nougenshards.c
HDR      = include/ngs.h

TESTCFLAGS = $(CFLAGS) $(WARN) -std=c11 -D_DEFAULT_SOURCE -D_POSIX_C_SOURCE=200809L

.PHONY: all lib check test crash standalone clean
all: lib check test crash standalone

$(BUILD):
	mkdir -p $(BUILD)

lib: $(BUILD)/libnougenshards.a
$(BUILD)/libnougenshards.a: $(SRC) $(HDR) | $(BUILD)
	$(CC) $(STD) $(WARN) $(CFLAGS) $(INC) -c $(SRC) -o $(BUILD)/nougenshards.o
	$(AR) rcs $@ $(BUILD)/nougenshards.o

standalone: $(SRC) $(HDR) | $(BUILD)
	$(CC) $(STD) $(WARN) $(CFLAGS) $(INC) -c $(SRC) -o $(BUILD)/standalone.o
	@echo "standalone amalgamation compile: OK"

check: include/check/ngs_header_check.c | $(BUILD)
	$(CC) $(STD) $(WARN) $(CFLAGS) $(INC) include/check/ngs_header_check.c -o $(BUILD)/ngs_header_check
	$(BUILD)/ngs_header_check
	$(CC) -std=c11 $(WARN) $(CFLAGS) $(INC) -c test/header_contract.c -o $(BUILD)/header_contract_c.o
	$(CXX) -std=c++11 $(WARN) $(CFLAGS) $(INC) -c test/header_contract.c -o $(BUILD)/header_contract_cpp.o
	@echo "header contract (C11 + C++11): OK"

test: $(BUILD)/test_m1
	$(BUILD)/test_m1
$(BUILD)/test_m1: test/test_m1.c test/kat_shim.c $(SRC) $(HDR) | $(BUILD)
	$(CC) $(TESTCFLAGS) $(INC) test/test_m1.c test/kat_shim.c -o $@

crash: $(BUILD)/crash_harness
	$(BUILD)/crash_harness
$(BUILD)/crash_harness: test/crash_harness.c $(SRC) $(HDR) | $(BUILD)
	$(CC) $(TESTCFLAGS) $(INC) test/crash_harness.c -o $@

clean:
	rm -rf $(BUILD)
