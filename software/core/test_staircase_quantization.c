#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <time.h>
#include <errno.h>
#include <omp.h>

#ifdef _WIN32
    #define NOMINMAX  // 禁用 Windows 的 min/max 宏
    #include <direct.h>
    #include <io.h>
    #include <windows.h> // 包含Sleep函数定义
#else
    #include <sys/stat.h>
    #include <unistd.h> // 包含usleep函数定义
    #include <time.h> // 包含timespec结构定义
#endif

// ==========================================
// 码长配置选择 (通过编译器宏定义控制)
// ==========================================
// 编译时使用 -DTEST_LENGTH_SHORT 等参数控制
//#define TEST_LENGTH_SHORT
//#define TEST_LENGTH_STANDARD
//#define TEST_LENGTH_LONG
//#define TEST_LENGTH_XL

#include "ldpc_config.h"

#include "ldpc.h"

// ==========================================
// 辅助函数
// ==========================================

#define PROFILE_HOT_THRESHOLD 0.10

static uint8_t paper_hotspot_mask[N];
static int paper_hotspot_mask_ready = 0;

static int target_hotspot_count(void) {
    return EXPANSION_FACTOR_Z;
}

static int expected_hotspot_degree(void) {
    if (N == 1024) return 6;
    if (N == 2048) return 10;
    if (N == 4096) return 12;
    if (N == 256) return 6;
    return 0;
}

// 确保目录存在的函数
void ensure_directory_exists(const char *dir_path) {
    #ifdef _WIN32
        _mkdir(dir_path);
    #else
        mkdir(dir_path, 0755);
    #endif
}

// 检查是否位于强列
int check_if_strong_column(int bit_index) {
    for (int j = 0; j < NUM_STRONG_ANCHORS; j++) {
        int anchor_bit = STRONG_ANCHOR_COLS[j];
        int anchor_start = anchor_bit;
        int anchor_end = anchor_bit + EXPANSION_FACTOR_Z - 1;
        if (bit_index >= anchor_start && bit_index <= anchor_end) {
            return 1;
        }
    }
    return 0;
}

static void build_paper_hotspot_mask(int length) {
    if (paper_hotspot_mask_ready) return;

    memset(paper_hotspot_mask, 0, sizeof(paper_hotspot_mask));

    int target = target_hotspot_count();
    if (target > length) target = length;

    for (int rank = 0; rank < target; rank++) {
        int best_idx = -1;
        double best_p = -1.0;

        for (int i = 0; i < length; i++) {
            if (paper_hotspot_mask[i]) continue;

            double p = REAL_PUF_ERROR_RATES[i % PUF_N];
            if (p > best_p || (fabs(p - best_p) < 1e-12 && (best_idx < 0 || i < best_idx))) {
                best_p = p;
                best_idx = i;
            }
        }

        if (best_idx >= 0) {
            paper_hotspot_mask[best_idx] = 1;
        }
    }

    paper_hotspot_mask_ready = 1;
}

static uint32_t rng_next_u32(uint32_t *state) {
    uint32_t x = *state;
    if (x == 0) x = 0x6D2B79F5u;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    *state = x;
    return x;
}

static double rng_uniform_01(uint32_t *state) {
    return (double)(rng_next_u32(state) >> 8) * (1.0 / 16777216.0);
}

static void build_column_degrees(uint16_t *col_degrees) {
    memset(col_degrees, 0, N * sizeof(uint16_t));

    for (int row = 0; row < M; row++) {
        for (int k = 0; k < H_row_degrees[row]; k++) {
            uint16_t col = H_row_indices[row][k];
            if (col < N && col_degrees[col] < UINT16_MAX) {
                col_degrees[col]++;
            }
        }
    }
}

static void print_experiment_sanity(void) {
    build_paper_hotspot_mask(N);

    uint16_t col_degrees[N];
    build_column_degrees(col_degrees);

    int target = target_hotspot_count();
    int expected_degree = expected_hotspot_degree();
    int n_base = N / EXPANSION_FACTOR_Z;
    int m_base = M / EXPANSION_FACTOR_Z;
    int profile_hot_count = 0;
    int masked_count = 0;
    int masked_profile_hot_count = 0;
    int masked_in_declared_anchor = 0;
    int masked_expected_degree_count = 0;
    int masked_zero_degree_count = 0;
    int masked_min_degree = 1000000;
    int masked_max_degree = 0;
    long long masked_degree_sum = 0;

    for (int i = 0; i < N; i++) {
        double p = REAL_PUF_ERROR_RATES[i % PUF_N];
        if (p >= PROFILE_HOT_THRESHOLD) profile_hot_count++;

        if (paper_hotspot_mask[i]) {
            int degree = col_degrees[i];
            masked_count++;
            if (p >= PROFILE_HOT_THRESHOLD) masked_profile_hot_count++;
            if (check_if_strong_column(i)) masked_in_declared_anchor++;
            if (expected_degree > 0 && degree >= expected_degree) masked_expected_degree_count++;
            if (degree == 0) masked_zero_degree_count++;
            if (degree < masked_min_degree) masked_min_degree = degree;
            if (degree > masked_max_degree) masked_max_degree = degree;
            masked_degree_sum += degree;
        }
    }

    if (masked_count == 0) masked_min_degree = 0;
    double masked_avg_degree = (masked_count > 0) ? (double)masked_degree_sum / masked_count : 0.0;

    printf("=== Paper-logic sanity check ===\n");
    printf("[QC] base matrix %dx%d, Z=%d, rate=%.3f\n",
           m_base, n_base, EXPANSION_FACTOR_Z, (double)K / (double)N);
    printf("[Paper Mask] target A=%d (Z=%d), selected=%d, profile-hot-selected=%d, profile-hot-total=%d\n",
           target, EXPANSION_FACTOR_Z, masked_count, masked_profile_hot_count, profile_hot_count);
    printf("[Paper Mask] selected in declared anchors=%d/%d, selected with expected high degree=%d/%d, degree min/avg/max=%d/%.2f/%d, zero-degree selected=%d\n",
           masked_in_declared_anchor, masked_count, masked_expected_degree_count, masked_count,
           masked_min_degree, masked_avg_degree, masked_max_degree, masked_zero_degree_count);

    if (profile_hot_count != target) {
        printf("[WARN] Profile hot count (%d) does not match paper target A (%d). Tied normal cells will be selected by index order.\n",
               profile_hot_count, target);
    }
    if (expected_degree > 0 && masked_expected_degree_count != masked_count) {
        printf("[WARN] Not every paper-mask bit is protected by the expected high column weight d_vs=%d.\n",
               expected_degree);
    }

    for (int anchor_idx = 0; anchor_idx < NUM_STRONG_ANCHORS; anchor_idx++) {
        int start = STRONG_ANCHOR_COLS[anchor_idx];
        int end = start + EXPANSION_FACTOR_Z - 1;
        if (start >= N) {
            printf("[UEP Anchor %d] [%d..%d] outside N=%d\n", anchor_idx, start, end, N);
            continue;
        }
        if (end >= N) end = N - 1;

        int count = 0;
        int masked_here = 0;
        int profile_hot_here = 0;
        int zero_here = 0;
        int min_degree = 1000000;
        int max_degree = 0;
        long long degree_sum = 0;

        for (int col = start; col <= end; col++) {
            int degree = col_degrees[col];
            count++;
            if (paper_hotspot_mask[col]) masked_here++;
            if (REAL_PUF_ERROR_RATES[col % PUF_N] >= PROFILE_HOT_THRESHOLD) profile_hot_here++;
            if (degree == 0) zero_here++;
            if (degree < min_degree) min_degree = degree;
            if (degree > max_degree) max_degree = degree;
            degree_sum += degree;
        }

        double avg_degree = (count > 0) ? (double)degree_sum / count : 0.0;
        const char *status = "OK";
        if (expected_degree > 0 && min_degree < expected_degree) status = "MISMATCH";

        printf("[UEP Anchor %d] [%d..%d]: degree min/avg/max=%d/%.2f/%d, zero=%d, paper-mask=%d, profile-hot=%d, %s\n",
               anchor_idx, start, end, min_degree, avg_degree, max_degree,
               zero_here, masked_here, profile_hot_here, status);
    }

    printf("================================\n");
}

// -----------------------------------------------------------------------------
// [创新点实现] 可靠性感知 LLR 初始化 (带 1-bit 抹除与阶梯型量化)
// -----------------------------------------------------------------------------
void initialize_llr_staircase_quantization(int8_t* llr_out, const uint8_t* logical_data,
                                      const int* permutation, int length,
                                      double scale, double min_noise_floor) {
    (void)permutation;

    build_paper_hotspot_mask(length);

    for (int i = 0; i < length; i++) {
        // 1. 获取该位的物理错误率 (模拟读取 Profile)
        int p_idx = i % PUF_N; 
        double p_puf = REAL_PUF_ERROR_RATES[p_idx]; // 获取原始 PUF 错误率

        // 2. [第一层防御] Profile-guided erasure.
        // This experiment does not perform a runtime physical-to-LDPC mapping.
        // The profile must already place the top-A hotspot cells on high-degree
        // LDPC positions; the mask only reads that enrollment-time placement.
        if (paper_hotspot_mask[i]) {
            llr_out[i] = 0; 
            continue; 
        }
        
        // 3. 计算缩放后的错误率
        double p_amplified = p_puf * scale;
        double scaled_p_puf = p_amplified + min_noise_floor;
        if (scaled_p_puf > 0.5) scaled_p_puf = 0.5;

        // 安全钳位
        double p_total = scaled_p_puf;
        if (p_total < 0.001) p_total = 0.001;
        if (p_total > 0.49) p_total = 0.49;

        // 4. 计算原始的理论连续 LLR (仅作参考映射依据)
        double raw_abs_llr = log((1.0 - p_total) / p_total);
        
        // =================================================================
        // 5. [第二层防御] 阶梯型量化 (Staircase Quantization)
        // 核心理念：抹平微观物理梯度，实现信息论上的 DPI 有损压缩
        // =================================================================
        int8_t quantized_magnitude;

        // 具体的台阶阈值和量化值 - 8个阶段，提供更精细的量化
        if (raw_abs_llr < 0.5) {
            // 台阶 1：极弱置信度 (对应 p_total 大于 ~0.38)
            // 保持弱比特的宽容度
            quantized_magnitude = 2;  
        } 
        else if (raw_abs_llr < 1.0) {
            // 台阶 2：很弱置信度 (对应 p_total 在 ~0.27 到 0.38 之间)
            // 保持弱比特的宽容度
            quantized_magnitude = 4;  
        } 
        else if (raw_abs_llr < 1.5) {
            // 台阶 3：弱置信度 (对应 p_total 在 ~0.18 到 0.27 之间)
            quantized_magnitude = 6;  
        } 
        else if (raw_abs_llr < 2.0) {
            // 台阶 4：偏弱置信度 (对应 p_total 在 ~0.12 到 0.18 之间)
            quantized_magnitude = 9;  
        } 
        else if (raw_abs_llr < 2.8) {
            // 台阶 5：中等置信度 (对应 p_total 在 ~0.06 到 0.12 之间)
            quantized_magnitude = 14;  
        } 
        else if (raw_abs_llr < 3.5) {
            // 台阶 6：偏强置信度 (对应 p_total 在 ~0.03 到 0.06 之间)
            quantized_magnitude = 20;  
        } 
        else if (raw_abs_llr < 4.5) {
            // 台阶 7：强置信度 (对应 p_total 在 ~0.01 到 0.03 之间)
            quantized_magnitude = 28;  
        } 
        else {
            // 台阶 8：很强置信度封顶 (对应 p_total 小于 ~0.01)
            // 将最高档从 60 压低到 35，剥夺强比特的绝对权威
            quantized_magnitude = 35; 
        }

        // 6. 设置符号位
        llr_out[i] = (logical_data[i] == 0) ? quantized_magnitude : -quantized_magnitude;
    }
}

// 标准固定 LLR (Baseline 对照组)
void initialize_llr_standard(int8_t* llr_out, const uint8_t* data, int length, double fixed_p) {
    // Baseline 盲目自信：只知道环境噪声，不知道 PUF 坏块
    // 如果 fixed_p 设得太小 (如0.001) 而实际有坏块 (0.45)，LLR 会极大，导致误码平层
    double p_used = fixed_p;
    if (p_used < 0.01) p_used = 0.01; // 最小钳位，给 Baseline 一点机会
    
    // 确保与Staircase量化方案的缩放比例一致，使用相同的量纲
    double scaled_magnitude = log((1.0 - p_used) / p_used) * 10.0;
    // 安全钳位对齐译码器的CLIP_VAL (60)
    if (scaled_magnitude > 60.0) scaled_magnitude = 60.0;
    if (scaled_magnitude < -60.0) scaled_magnitude = -60.0;
    int8_t val = (int8_t)scaled_magnitude;
    
    for (int i = 0; i < length; i++) {
        llr_out[i] = (data[i] == 0) ? val : -val;
    }
}

// 模拟 PUF 噪声注入 (非线性放大模型)
void generate_puf_response_optimized(uint8_t* response, const uint8_t* golden, 
                                   double env_factor, double global_noise_floor, 
                                   int length, uint32_t *rng_state) {
    for (int i = 0; i < length; i++) {
        // 1. 获取该位的"先天"翻转概率
        int idx = i % PUF_N;
        double p_intrinsic = REAL_PUF_ERROR_RATES[idx];
        
        // 2. 计算环境恶化后的概率 (核心修改)
        // 逻辑：环境越差(env_factor越大)，原本的不稳定性被放大的越严重
        double p_amplified = p_intrinsic * env_factor;
        
        // 3. 加上全局底噪 (模拟完全随机的辐射或电磁干扰)
        double p_total = p_amplified + global_noise_floor;
        
        // 4. 物理饱和限制 (关键！)
        // 翻转概率最高只能是 0.5 (即完全随机)，不会变成反向确定
        if (p_total > 0.5) {
            p_total = 0.5;
        }

        // 5. 蒙特卡洛随机采样
        double rand_val = rng_uniform_01(rng_state);
        
        if (rand_val < p_total) {
            // 发生翻转
            response[i] = golden[i] ^ 1;
        } else {
            // 保持原值
            response[i] = golden[i];
        }
    }
}

// ==========================================
// 主函数
// ==========================================
int main(int argc, char *argv[]) {
    // 默认 scale
    double scale_value = 2.0;
    if (argc > 1) scale_value = atof(argv[1]);

    uint32_t base_seed = 12345u;
    // Public-artifact defaults: finish quickly unless full-run arguments are explicit.
    int target_errors = 5;
    long long max_tests = 1000;
    double max_noise_rate = 0.005;
    double single_noise_rate = -1.0;
    int sanity_only = 0;

    int numeric_arg = 0;
    for (int argi = 2; argi < argc; argi++) {
        if (strcmp(argv[argi], "--sanity-only") == 0) {
            sanity_only = 1;
        } else if (strncmp(argv[argi], "--single-noise=", 15) == 0) {
            single_noise_rate = atof(argv[argi] + 15);
        } else if (strcmp(argv[argi], "--single-noise") == 0 && argi + 1 < argc) {
            single_noise_rate = atof(argv[++argi]);
        } else {
            if (numeric_arg == 0) {
                base_seed = (uint32_t)strtoul(argv[argi], NULL, 10);
            } else if (numeric_arg == 1) {
                target_errors = atoi(argv[argi]);
                if (target_errors <= 0) target_errors = 1;
            } else if (numeric_arg == 2) {
                max_tests = strtoll(argv[argi], NULL, 10);
                if (max_tests <= 0) max_tests = 1;
            } else if (numeric_arg == 3) {
                max_noise_rate = atof(argv[argi]);
                if (max_noise_rate <= 0.0) max_noise_rate = 0.001;
                if (max_noise_rate > 0.15) max_noise_rate = 0.15;
            }
            numeric_arg++;
        }
    }
    if (single_noise_rate > 0.0) {
        if (single_noise_rate < 0.001) single_noise_rate = 0.001;
        if (single_noise_rate > 0.15) single_noise_rate = 0.15;
        max_noise_rate = single_noise_rate;
    }
    
    // === 系统自检 (Sanity Check) ===
    printf("=== Sanity Check ===\n");
    build_paper_hotspot_mask(N);

    int probe_indices[] = {0, 20, 40};
    for (int probe = 0; probe < 3; probe++) {
        int idx = probe_indices[probe];
        if (idx >= N) continue;
        double rate = REAL_PUF_ERROR_RATES[idx % PUF_N];
        printf("[Profile] Index %d Error Rate: %.6f, paper-mask=%s\n",
               idx, rate, paper_hotspot_mask[idx] ? "ERASE" : "KEEP");
    }

    printf("==================================\n");
    print_experiment_sanity();

    if (sanity_only) {
        printf("Sanity-only mode complete.\n");
        return 0;
    }
    
    // 暂停一下，让用户看到自检结果
    for (int i = 0; i < 3; i++) {
        printf(".");
        fflush(stdout);
        #ifdef _WIN32
            Sleep(500); // Windows下使用Sleep函数
        #else
            usleep(500000); // Linux下使用usleep函数，单位为微秒
        #endif
    }
    printf("\n");

    // 准备输出文件
    char output_dir[100];
    char csv_filename[150];
    if (single_noise_rate > 0.0) {
        sprintf(output_dir, "test_results_staircase_paper_scale_%.3f_single%.3f_te%d_mt%lld",
                scale_value, single_noise_rate, target_errors, max_tests);
    } else if (target_errors == 50 && max_tests == 10000000 && fabs(max_noise_rate - 0.15) < 1e-12) {
        sprintf(output_dir, "test_results_staircase_paper_scale_%.3f", scale_value);
    } else {
        sprintf(output_dir, "test_results_staircase_paper_scale_%.3f_te%d_mt%lld_mn%.3f",
                scale_value, target_errors, max_tests, max_noise_rate);
    }
    ensure_directory_exists(output_dir);
    sprintf(csv_filename, "%s/fer_comparison_length_%s.csv", output_dir, LENGTH_SUFFIX);
    
    // 检查文件是否已存在
    int file_exists = 0;
    FILE *check_file = fopen(csv_filename, "r");
    if (check_file) {
        file_exists = 1;
        fclose(check_file);
    }
    
    // 打开文件：如果文件存在则追加，否则创建新文件
    FILE *csv_file = fopen(csv_filename, file_exists ? "a" : "w");
    if (!csv_file) {
        perror("Error opening CSV file");
        return 1;
    }

    // --- 1. 打印配置信息 ---  
    printf("\n=== LDPC Staircase Quantization Test (Length=%s) ===\n", LENGTH_SUFFIX);
    printf("N=%d, K=%d (Rate=1/2)\n", N, K);
    printf("PUF Scale: %.3f\n", scale_value);
    printf("Seed: %u\n", base_seed);
    printf("Monte Carlo: target_errors=%d, max_tests=%lld, max_noise=%.3f\n",
           target_errors, max_tests, max_noise_rate);
    if (single_noise_rate > 0.0) {
        printf("Single-noise confidence mode: noise_rate=%.3f\n", single_noise_rate);
    }
    printf("Output: %s\n", csv_filename);
    printf("\nNoise_Rate, Actual_BER, Baseline_FER, Staircase_FER, Improvement, Avg_Iter_Baseline, Avg_Iter_Staircase, Tests, Fail_Baseline, Fail_Staircase, Rule3_95_UB\n");
    printf("==============================================================================================================\n");
    
    // 只有在创建新文件时才写入CSV头
    if (!file_exists) {
        fprintf(csv_file, "Noise_Rate, Actual_BER, Baseline_FER, Staircase_FER, Improvement, Avg_Iter_Baseline, Avg_Iter_Staircase, Tests, Fail_Baseline, Fail_Staircase, Rule3_95_UB\n");
    }

    // 确定起始step：如果文件存在，从最后一行的noise_rate开始继续
    int start_step = 0;
    if (file_exists && single_noise_rate <= 0.0) {
        // 重新打开文件读取最后一行
        FILE *read_file = fopen(csv_filename, "r");
        if (read_file) {
            char line[256];
            char last_line[256] = "";
            // 读取所有行，保存最后一行
            while (fgets(line, sizeof(line), read_file) != NULL) {
                strcpy(last_line, line);
            }
            fclose(read_file);
            
            // 解析最后一行的noise_rate
            if (strlen(last_line) > 0) {
                double last_noise_rate;
                if (sscanf(last_line, "%lf,", &last_noise_rate) == 1) {
                    // 计算对应的step，并从下一个step开始
                    start_step = (int)((last_noise_rate - 0.001) / 0.001) + 1;
                    printf("📋 从噪声率 %.3f 继续运行，起始step: %d\n", last_noise_rate, start_step);
                }
            }
        }
    }

    // --- 2. 仿真循环 ---
    // 噪声范围: 0.001 ~ 0.150 (从start_step开始继续运行)
    int end_step = 199;
    if (single_noise_rate > 0.0) {
        start_step = (int)((single_noise_rate - 0.001) / 0.001 + 0.5);
        end_step = start_step;
    }
    for (int step = start_step; step <= end_step; step++) {
        double noise_rate = (single_noise_rate > 0.0) ? single_noise_rate : (0.001 + step * 0.001); // 步长 0.001
        if (noise_rate > max_noise_rate) break;

        // 基于目标错误数的蒙特卡洛仿真
        const int TARGET_ERRORS = target_errors;
        const long long MAX_TESTS = max_tests;
        const long long FLUSH_INTERVAL = (MAX_TESTS < 1000) ? 10 : 1000;
        
        long long total_tests_run = 0;
        long long total_fail_base = 0;
        long long total_fail_staircase = 0;
        long long total_bit_errors = 0;
        long long total_bits_simulated = 0;
        long long total_iter_base = 0;
        long long total_iter_staircase = 0;
        long long success_count_base = 0;
        long long success_count_staircase = 0;

        #pragma omp parallel
        {
            int thread_id = omp_get_thread_num();
            uint32_t rng_state = base_seed
                               ^ ((uint32_t)(step + 1) * 0x9E3779B9u)
                               ^ ((uint32_t)(thread_id + 1) * 0x85EBCA6Bu);
            if (rng_state == 0) rng_state = 0xA5A5A5A5u;
            
            // 每个线程的局部变量
            long long local_tests_run = 0;
            long long local_fail_base = 0;
            long long local_fail_staircase = 0;
            long long local_bit_errors = 0;
            long long local_iter_base = 0;
            long long local_iter_staircase = 0;
            long long local_success_base = 0;
            long long local_success_staircase = 0;
            
            // 线程局部变量 - 去掉static关键字
            uint8_t message[K];
            uint8_t codeword[N];
            uint8_t noisy_codeword[N];
            uint8_t decoded_baseline[N];
            uint8_t decoded_staircase[N];
            int8_t llr_baseline[N];
            int8_t llr_staircase[N];
            
            // 循环直到达到目标错误数或最大测试次数
            while (1) {
                // 检查是否达到全局停止条件
                long long global_fail_base;
                long long global_fail_staircase;
                long long global_tests;
                
                #pragma omp atomic read
                global_fail_base = total_fail_base;
                #pragma omp atomic read
                global_fail_staircase = total_fail_staircase;
                #pragma omp atomic read
                global_tests = total_tests_run;
                
                if (global_fail_base >= TARGET_ERRORS && global_fail_staircase >= TARGET_ERRORS) break;
                if (global_tests >= MAX_TESTS) break;
                
                // 1. 使用全0消息作为测试
                for (int i = 0; i < K; i++) message[i] = 0; // 全0消息
                
                // 2. 编码
                ldpc_encode(message, codeword); // 假设 ldpc.c 中有此函数，或链接了 ldpc_wrapper
                
                // --- 在 ldpc_encode 之后插入 ---
                // 【架构师调试探针】验证生成的码字是否满足 H 矩阵校验
                int syndrome_failed = 0;
                for (int i = 0; i < M; i++) {
                    int parity = 0;
                    for (int k = 0; k < H_row_degrees[i]; k++) {
                        uint16_t col_idx = H_row_indices[i][k];
                        parity ^= codeword[col_idx];
                    }
                    if (parity != 0) {
                        syndrome_failed = 1;
                        break;
                    }
                }

                if (syndrome_failed) {
                    continue; // 跳过无效码字
                }
                // --- syndrome检查结束 ---
                
                // 3. 加噪 (PUF + Env)
                generate_puf_response_optimized(noisy_codeword, codeword, scale_value, noise_rate, N, &rng_state);
                
                // 统计 Actual BER
                for (int i = 0; i < N; i++) {
                    if (noisy_codeword[i] != codeword[i]) local_bit_errors++;
                }
                
                // 4. 解码 A: Baseline
                {
                    // Baseline 使用固定的盲目估计值，不知道PUF坏块
                    double est_ber = noise_rate + 0.03; // 盲目自信的估计
                    initialize_llr_standard(llr_baseline, noisy_codeword, N, est_ber);
                    
                    int iter_count = ldpc_decode_nms(llr_baseline, decoded_baseline);
                    
                    if (iter_count == 0) {
                        local_fail_base++;
                    } else {
                        local_success_base++;
                        local_iter_base += iter_count;
                        int decode_fail = 0;
                        for (int i = 0; i < N; i++) {
                            if (decoded_baseline[i] != codeword[i]) {
                                decode_fail = 1;
                                break;
                            }
                        }
                        if (decode_fail) local_fail_base++;
                    }
                }
                
                // 5. 解码 B: Staircase Quantization
                {
                    // Staircase Quantization 使用阶梯型量化的LLR初始化
                    initialize_llr_staircase_quantization(llr_staircase, noisy_codeword, NULL, N, scale_value, noise_rate);
                    int iter_count = ldpc_decode_nms(llr_staircase, decoded_staircase);
                    
                    if (iter_count == 0) {
                        local_fail_staircase++;
                    } else {
                        local_success_staircase++;
                        local_iter_staircase += iter_count;
                        int decode_fail = 0;
                        for (int i = 0; i < N; i++) {
                            if (decoded_staircase[i] != codeword[i]) {
                                decode_fail = 1;
                                break;
                            }
                        }
                        if (decode_fail) local_fail_staircase++;
                    }
                }
                
                local_tests_run++;
                
                // 小样本试跑时缩短汇总间隔，避免并行线程明显跑过 max_tests。
                if (local_tests_run % FLUSH_INTERVAL == 0) {
                    // 原子操作汇总结果
                    #pragma omp atomic
                    total_tests_run += local_tests_run;
                    #pragma omp atomic
                    total_fail_base += local_fail_base;
                    #pragma omp atomic
                    total_fail_staircase += local_fail_staircase;
                    #pragma omp atomic
                    total_bit_errors += local_bit_errors;
                    #pragma omp atomic
                    total_iter_base += local_iter_base;
                    #pragma omp atomic
                    total_iter_staircase += local_iter_staircase;
                    #pragma omp atomic
                    success_count_base += local_success_base;
                    #pragma omp atomic
                    success_count_staircase += local_success_staircase;
                    
                    // 重置局部变量
                    local_tests_run = 0;
                    local_fail_base = 0;
                    local_fail_staircase = 0;
                    local_bit_errors = 0;
                    local_iter_base = 0;
                    local_iter_staircase = 0;
                    local_success_base = 0;
                    local_success_staircase = 0;
                }
            }
            
            // 汇总剩余的结果
            if (local_tests_run > 0) {
                #pragma omp atomic
                total_tests_run += local_tests_run;
                #pragma omp atomic
                total_fail_base += local_fail_base;
                #pragma omp atomic
                total_fail_staircase += local_fail_staircase;
                #pragma omp atomic
                total_bit_errors += local_bit_errors;
                #pragma omp atomic
                total_iter_base += local_iter_base;
                #pragma omp atomic
                total_iter_staircase += local_iter_staircase;
                #pragma omp atomic
                success_count_base += local_success_base;
                #pragma omp atomic
                success_count_staircase += local_success_staircase;
            }
        }
        
        total_bits_simulated = (long long)total_tests_run * N; // 总比特数 = 测试次数 * 每帧比特数
        
        double fer_base = (total_tests_run > 0) ? (double)total_fail_base / total_tests_run : 0.0;
        double fer_staircase = (total_tests_run > 0) ? (double)total_fail_staircase / total_tests_run : 0.0;
        double improve = 0.0;
        if (fer_base > 0) improve = (fer_base - fer_staircase) / fer_base * 100.0;
        
        double actual_ber = (total_bits_simulated > 0) ? (double)total_bit_errors / total_bits_simulated : 0.0;
        
        // 计算平均迭代次数（只统计成功解码的情况）
        double avg_iter_base = (success_count_base > 0) ? (double)total_iter_base / success_count_base : 0.0;
        double avg_iter_staircase = (success_count_staircase > 0) ? (double)total_iter_staircase / success_count_staircase : 0.0;
        
        double rule3_95_ub = (total_fail_staircase == 0 && total_tests_run > 0) ? (3.0 / (double)total_tests_run) : -1.0;
        printf("%.3f, %.5f, %.9g, %.9g, %.1f, %.2f, %.2f, %lld, %lld, %lld, %.9g\n",
               noise_rate, actual_ber, fer_base, fer_staircase, improve,
               avg_iter_base, avg_iter_staircase, total_tests_run,
               total_fail_base, total_fail_staircase, rule3_95_ub);
        fprintf(csv_file, "%.3f,%.5f,%.9g,%.9g,%.1f,%.2f,%.2f,%lld,%lld,%lld,%.9g\n",
                noise_rate, actual_ber, fer_base, fer_staircase, improve,
                avg_iter_base, avg_iter_staircase, total_tests_run,
                total_fail_base, total_fail_staircase, rule3_95_ub);
        fflush(stdout);
        fflush(csv_file);

        // 检查停止条件
        if (fer_base >= 0.99 && fer_staircase >= 0.99 && noise_rate >= 0.12) {
            // 如果两条曲线都到了 1.0 (全错) 且噪声率超过 0.12，提前结束本码长测试
            break;
        }
    }
    
    fclose(csv_file);
    printf("\nTests finished for length configuration: %s\n", LENGTH_SUFFIX);
    return 0;
}
