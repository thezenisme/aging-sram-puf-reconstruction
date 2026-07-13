# 基于多码率 QC-LDPC 的 PUF 密钥再生系统 Makefile
# 支持多码率、多码长配置编译

# 编译器设置
CC = gcc
CFLAGS = -std=c99 -Wall -Wextra -O3 -g -fopenmp
LDFLAGS = -lm -fopenmp

# Python 解释器
PYTHON = python

# 源文件
LDPC_SRC = ldpc_advanced.c
MATRIX_GEN = generate_uep_peg_matrices.py

# 头文件依赖
LDPC_HDR = ldpc.h ldpc_wrapper.h

# 默认目标
all: compile_all_staircase

# ==========================================
# 阶梯型量化测试程序 - 多码长支持
# ==========================================

# 编译阶梯型量化测试程序 - 短配置 (N=256, K=128)
compile_staircase_short:
	@echo "=== 编译阶梯型量化测试程序 - 短配置 (N=256, K=128) ==="
	$(CC) $(CFLAGS) -DTEST_LENGTH_SHORT ldpc.c matrix_data_1_2_short.c test_staircase_quantization.c -o test_staircase_short.exe $(LDFLAGS)

# 编译阶梯型量化测试程序 - 标准配置 (N=1024, K=512)
compile_staircase_standard:
	@echo "=== 编译阶梯型量化测试程序 - 标准配置 (N=1024, K=512) ==="
	$(CC) $(CFLAGS) -DTEST_LENGTH_STANDARD ldpc.c matrix_data_1_2_standard.c test_staircase_quantization.c -o test_staircase_standard.exe $(LDFLAGS)

# 编译阶梯型量化测试程序 - 中等配置 (N=2048, K=1024)
compile_staircase_medium:
	@echo "=== 编译阶梯型量化测试程序 - 中等配置 (N=2048, K=1024) ==="
	$(CC) $(CFLAGS) -DTEST_LENGTH_MEDIUM ldpc.c matrix_data_1_2_medium.c test_staircase_quantization.c -o test_staircase_medium.exe $(LDFLAGS)

# 编译阶梯型量化测试程序 - 长配置 (N=4096, K=2048)
compile_staircase_long:
	@echo "=== 编译阶梯型量化测试程序 - 长配置 (N=4096, K=2048) ==="
	$(CC) $(CFLAGS) -DTEST_LENGTH_LONG ldpc.c matrix_data_1_2_long.c test_staircase_quantization.c -o test_staircase_long.exe $(LDFLAGS)

# 编译所有阶梯型量化测试程序
compile_all_staircase:
	@echo "=== 编译所有码长的阶梯型量化测试程序 ==="
	$(MAKE) compile_staircase_short
	$(MAKE) compile_staircase_standard
	$(MAKE) compile_staircase_medium
	$(MAKE) compile_staircase_long

# ==========================================
# 运行阶梯型量化测试 - 多码长
# ==========================================

# 运行阶梯型量化测试 - 短配置
run_staircase_short:
	@echo "=== 运行阶梯型量化测试 - 短配置 ==="
	.\test_staircase_short.exe

# 运行阶梯型量化测试 - 标准配置
run_staircase_standard:
	@echo "=== 运行阶梯型量化测试 - 标准配置 ==="
	.\test_staircase_standard.exe

# 运行阶梯型量化测试 - 中等配置
run_staircase_medium:
	@echo "=== 运行阶梯型量化测试 - 中等配置 ==="
	.\test_staircase_medium.exe

# 运行阶梯型量化测试 - 长配置
run_staircase_long:
	@echo "=== 运行阶梯型量化测试 - 长配置 ==="
	.\test_staircase_long.exe

# 运行所有码长的阶梯型量化测试
run_all_staircase:
	@echo "=== 运行所有码长的阶梯型量化测试 ==="
	$(MAKE) run_staircase_short
	$(MAKE) run_staircase_standard
	$(MAKE) run_staircase_medium
	$(MAKE) run_staircase_long

# ==========================================
# 多 scale 值测试
# ==========================================

# 测试所有 scale 值 - 短配置
test_all_scales_short:
	@echo "=== 测试所有 scale 值 - 短配置 ==="
	@.\test_staircase_short.exe 0
	@.\test_staircase_short.exe 0.5
	@.\test_staircase_short.exe 1
	@.\test_staircase_short.exe 1.5
	@.\test_staircase_short.exe 2

# 测试所有 scale 值 - 标准配置
test_all_scales_standard:
	@echo "=== 测试所有 scale 值 - 标准配置 ==="
	@.\test_staircase_standard.exe 0
	@.\test_staircase_standard.exe 0.5
	@.\test_staircase_standard.exe 1
	@.\test_staircase_standard.exe 1.5
	@.\test_staircase_standard.exe 2

# 测试所有 scale 值 - 中等配置
test_all_scales_medium:
	@echo "=== 测试所有 scale 值 - 中等配置 ==="
	@.\test_staircase_medium.exe 0
	@.\test_staircase_medium.exe 0.5
	@.\test_staircase_medium.exe 1
	@.\test_staircase_medium.exe 1.5
	@.\test_staircase_medium.exe 2

# 测试所有 scale 值 - 长配置
test_all_scales_long:
	@echo "=== 测试所有 scale 值 - 长配置 ==="
	@.\test_staircase_long.exe 0
	@.\test_staircase_long.exe 0.5
	@.\test_staircase_long.exe 1
	@.\test_staircase_long.exe 1.5
	@.\test_staircase_long.exe 2

# 测试所有 scale 值 - 所有码长
test_all_scales_all:
	@echo "=== 测试所有 scale 值 - 所有码长 ==="
	$(MAKE) test_all_scales_short
	$(MAKE) test_all_scales_standard
	$(MAKE) test_all_scales_medium
	$(MAKE) test_all_scales_long

# ==========================================
# 清理
# ==========================================

clean:
	@echo "=== 清理生成的文件 ==="
	@powershell -Command "Remove-Item -Path test_staircase_*.exe -Force -ErrorAction SilentlyContinue"
	@powershell -Command "Remove-Item -Path test_len_*.exe -Force -ErrorAction SilentlyContinue"
	@powershell -Command "Remove-Item -Path test_reliability_*.exe -Force -ErrorAction SilentlyContinue"
	@powershell -Command "Remove-Item -Path retest_negative_improvement.exe -Force -ErrorAction SilentlyContinue"
	@powershell -Command "Remove-Item -Path *.o -Force -ErrorAction SilentlyContinue"

# ==========================================
# 帮助信息
# ==========================================

help:
	@echo "阶梯型量化多码长测试 Makefile 选项:"
	@echo ""
	@echo "【编译选项】"
	@echo "  make compile_staircase_short    - 编译短配置 (N=256, K=128)"
	@echo "  make compile_staircase_standard - 编译标准配置 (N=1024, K=512)"
	@echo "  make compile_staircase_medium   - 编译中等配置 (N=2048, K=1024)"
	@echo "  make compile_staircase_long     - 编译长配置 (N=4096, K=2048)"
	@echo "  make compile_all_staircase      - 编译所有码长"
	@echo ""
	@echo "【运行选项】"
	@echo "  make run_staircase_short        - 运行短配置测试"
	@echo "  make run_staircase_standard     - 运行标准配置测试"
	@echo "  make run_staircase_medium       - 运行中等配置测试"
	@echo "  make run_staircase_long         - 运行长配置测试"
	@echo "  make run_all_staircase          - 运行所有码长测试"
	@echo ""
	@echo "【多 scale 测试】"
	@echo "  make test_all_scales_short      - 测试所有 scale 值 (短配置)"
	@echo "  make test_all_scales_standard   - 测试所有 scale 值 (标准配置)"
	@echo "  make test_all_scales_medium     - 测试所有 scale 值 (中等配置)"
	@echo "  make test_all_scales_long       - 测试所有 scale 值 (长配置)"
	@echo "  make test_all_scales_all        - 测试所有 scale 值 (所有码长)"
	@echo ""
	@echo "【其他】"
	@echo "  make clean                      - 清理所有生成文件"
	@echo "  make help                       - 显示此帮助信息"

.PHONY: all compile_staircase_short compile_staircase_standard compile_staircase_medium compile_staircase_long compile_all_staircase run_staircase_short run_staircase_standard run_staircase_medium run_staircase_long run_all_staircase test_all_scales_short test_all_scales_standard test_all_scales_medium test_all_scales_long test_all_scales_all clean help