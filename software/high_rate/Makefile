# =========================================================
# LDPC Fuzzy Extractor Project Makefile
# 支持自动头文件映射 (Auto Header Mapping)
# =========================================================

CC = gcc
CFLAGS = -Wall -O3 -std=c99 -lm -fopenmp

# 默认目标
all: help

# 帮助信息
help:
	@echo "Available targets:"
	@echo "  make rate_1_2   - Compile for Rate 1/2 (N=1024, K=512)"
	@echo "  make rate_2_3   - Compile for Rate 2/3 (N=768, K=512)"
	@echo "  make rate_3_4   - Compile for Rate 3/4 (N=1024, K=768)"
	@echo "  make clean      - Remove generated files"

# ---------------------------------------------------------
# Rate 1/2 Target
# ---------------------------------------------------------
rate_1_2: multi_rate_test.c ldpc.c matrix_data_1_2.c h_matrix_1_2.h g_matrix_1_2.h
	@echo "-> [Config] Mapping Rate 1/2 headers..."
	@cp h_matrix_1_2.h h_matrix.h
	@cp g_matrix_1_2.h g_matrix.h
	@echo "-> [Build] Compiling test_r12..."
	$(CC) $(CFLAGS) -DTEST_RATE_1_2 -o test_r12 multi_rate_test.c ldpc.c matrix_data_1_2.c
	@echo "✅ Build success! Run with: ./test_r12"

# ---------------------------------------------------------
# Rate 2/3 Target
# ---------------------------------------------------------
rate_2_3: multi_rate_test.c ldpc.c matrix_data_2_3.c h_matrix_2_3.h g_matrix_2_3.h
	@echo "-> [Config] Mapping Rate 2/3 headers..."
	@cp h_matrix_2_3.h h_matrix.h
	@cp g_matrix_2_3.h g_matrix.h
	@echo "-> [Build] Compiling test_r23..."
	$(CC) $(CFLAGS) -DTEST_RATE_2_3 -o test_r23 multi_rate_test.c ldpc.c matrix_data_2_3.c
	@echo "✅ Build success! Run with: ./test_r23"

# ---------------------------------------------------------
# Rate 3/4 Target (The Hell Mode)
# ---------------------------------------------------------
rate_3_4: multi_rate_test.c ldpc.c matrix_data_3_4.c h_matrix_3_4.h g_matrix_3_4.h
	@echo "-> [Config] Mapping Rate 3/4 headers..."
	@cp h_matrix_3_4.h h_matrix.h
	@cp g_matrix_3_4.h g_matrix.h
	@echo "-> [Build] Compiling test_r34..."
	$(CC) $(CFLAGS) -DTEST_RATE_3_4 -o test_r34 multi_rate_test.c ldpc.c matrix_data_3_4.c
	@echo "✅ Build success! Run with: ./test_r34"

# 运行所有实验
run_all:
	@echo "=== 编译并运行所有码率实验 ==="
	@echo "使用默认scale值: 2.0"
	@echo "================================"
	@$(MAKE) rate_1_2
	@echo "--------------------------------"
	@echo "运行 1/2 码率实验..."
	@./test_r12 2.0
	@echo "--------------------------------"
	@$(MAKE) rate_2_3
	@echo "--------------------------------"
	@echo "运行 2/3 码率实验..."
	@./test_r23 2.0
	@echo "--------------------------------"
	@$(MAKE) rate_3_4
	@echo "--------------------------------"
	@echo "运行 3/4 码率实验..."
	@./test_r34 2.0
	@echo "================================"
	@echo "✅ 所有实验运行完成！"
	@echo "Results are stored in: ./scale=2.0"

# 清理
clean:
	rm -f test_r12 test_r23 test_r34 h_matrix.h g_matrix.h
