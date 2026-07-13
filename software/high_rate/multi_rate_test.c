#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <time.h>
#include <sys/stat.h>
#include <errno.h>
#include <omp.h>

// 定义要测试的码率
// 注意：编译时通过命令行定义，如 -DTEST_RATE_1_2
//#define TEST_RATE_1_2
//#define TEST_RATE_2_3
//#define TEST_RATE_3_4

// 根据码率选择相应的头文件
#ifdef TEST_RATE_1_2
    #include "h_matrix_1_2.h"
    #include "g_matrix_1_2.h"
    #define RATE_SUFFIX "1_2"
    #define N N_1_2
    #define K K_1_2
    #define M M_1_2
    #define H_row_indices H_row_indices_1_2
    #define H_row_degrees H_row_degrees_1_2
    #define G_row_indices G_row_indices_1_2
    #define G_row_degrees G_row_degrees_1_2
#elif defined(TEST_RATE_2_3)
    #include "h_matrix_2_3.h"
    #include "g_matrix_2_3.h"
    #define RATE_SUFFIX "2_3"
    #define N N_2_3
    #define K K_2_3
    #define M M_2_3
    #define H_row_indices H_row_indices_2_3
    #define H_row_degrees H_row_degrees_2_3
    #define G_row_indices G_row_indices_2_3
    #define G_row_degrees G_row_degrees_2_3
#elif defined(TEST_RATE_3_4)
    #include "h_matrix_3_4.h"
    #include "g_matrix_3_4.h"
    #define RATE_SUFFIX "3_4"
    #define N N_3_4
    #define K K_3_4
    #define M M_3_4
    #define H_row_indices H_row_indices_3_4
    #define H_row_degrees H_row_degrees_3_4
    #define G_row_indices G_row_indices_3_4
    #define G_row_degrees G_row_degrees_3_4
#else
    #error "No rate defined"
#endif

#include "ldpc.h"
#include "puf_profile.h"  

// ==========================================
// 核心优化算法实现
// ==========================================

// 基于误码率的动态感知 LLR 初始化 (与 multi_weights_analysis 一致)
void initialize_llr_reliability_aware(int8_t* llr_out, const uint8_t* logical_data,
                                      const int* permutation, int length,
                                      double scale, double min_noise_floor) {
    (void)permutation;

    for (int i = 0; i < length; i++) {
        // 1. 获取该位的物理错误率 (模拟读取 Profile)
        int p_idx = i % PUF_N; 
        double p_puf = REAL_PUF_ERROR_RATES[p_idx]; // 获取原始 PUF 错误率

        // 2. 检查当前位是否位于强列
        int is_strong_column = 0;
        int bit_index = i;
        for (int j = 0; j < NUM_STRONG_ANCHORS; j++) {
            int anchor_bit = STRONG_ANCHOR_COLS[j];
            int anchor_start = anchor_bit;
            int anchor_end = anchor_bit + EXPANSION_FACTOR_Z - 1;
            if (bit_index >= anchor_start && bit_index <= anchor_end) {
                is_strong_column = 1;
                break;
            }
        }

        // 3. [关键] 抹除判断 (Erasure Check)
        // 基于位置判断坏块：每16位中有3位是热点
        int position_idx = i % 16;
        if (is_strong_column && position_idx < 3) {
            // 💀 它是坏块且位于强列：直接闭嘴，不发表意见
            // LLR = 0 表示 "我对我是 0 还是 1 完全不确定"
            llr_out[i] = 0; 
            continue; // 直接跳过后续计算
        }
        
        // 4. 计算缩放后的错误率
        double p_amplified = p_puf * scale;
        double scaled_p_puf = p_amplified + min_noise_floor;
        if (scaled_p_puf > 0.5) scaled_p_puf = 0.5;

        // 4. 好块或弱列中的块：正常计算 LLR (叠加环境噪声)
        double p_total = scaled_p_puf;
        
        // 安全钳位
        if (p_total < 0.001) p_total = 0.001;
        if (p_total > 0.49) p_total = 0.49;

        // 计算 LLR
        // 使用错误率计算 LLR：LLR = log((1-p)/p)
        double llr_value = log((1.0 - p_total) / p_total);
        // 确保值在int8_t范围内
        if (llr_value > 127.0) llr_value = 127.0;
        if (llr_value < -128.0) llr_value = -128.0;
        int8_t val = (int8_t)llr_value;

        // 设置符号
        llr_out[i] = (logical_data[i] == 0) ? val : -val;
    }
}

// 标准固定 LLR (对照组)
void initialize_llr_standard(int8_t* llr_out, const uint8_t* data, int length, double fixed_p) {
    // 确保与Staircase量化方案的缩放比例一致，使用相同的量纲
    double scaled_magnitude = log((1.0 - fixed_p) / fixed_p) * 10.0;
    // 安全钳位对齐译码器的CLIP_VAL (60)
    if (scaled_magnitude > 60.0) scaled_magnitude = 60.0;
    if (scaled_magnitude < -60.0) scaled_magnitude = -60.0;
    int8_t val = (int8_t)scaled_magnitude;
    
    for (int i = 0; i < length; i++) {
        llr_out[i] = (data[i] == 0) ? val : -val;
    }
}

// 阶梯型量化 LLR 初始化 (与 one_bit_mask_llr_experiment 一致)
void initialize_llr_staircase_quantization(int8_t* llr_out, const uint8_t* logical_data,
                                      const int* permutation, int length,
                                      double scale, double min_noise_floor) {
    (void)permutation;

    // 抹除判断基于位置信息，不需要固定阈值

    for (int i = 0; i < length; i++) {
        // 1. 获取该位的物理错误率 (模拟读取 Profile)
        int p_idx = i % PUF_N; 
        double p_puf = REAL_PUF_ERROR_RATES[p_idx]; // 获取原始 PUF 错误率

        // 2. 检查当前位是否位于强列
        int is_strong_column = 0;
        int bit_index = i;
        for (int j = 0; j < NUM_STRONG_ANCHORS; j++) {
            int anchor_bit = STRONG_ANCHOR_COLS[j];
            int anchor_start = anchor_bit;
            int anchor_end = anchor_bit + EXPANSION_FACTOR_Z - 1;
            if (bit_index >= anchor_start && bit_index <= anchor_end) {
                is_strong_column = 1;
                break;
            }
        }

        // 3. [第一层防御] 抹除判断 (Erasure Check)
        int position_idx = i % 16;
        if (is_strong_column && position_idx < 3) {
            // 💀 它是坏块且位于强列：直接闭嘴，不发表意见
            // LLR = 0 构成了最大的"信息盲区"
            llr_out[i] = 0; 
            continue; 
        }
        
        // 4. 计算缩放后的错误率
        double p_amplified = p_puf * scale;
        double scaled_p_puf = p_amplified + min_noise_floor;
        if (scaled_p_puf > 0.5) scaled_p_puf = 0.5;

        // 安全钳位
        double p_total = scaled_p_puf;
        if (p_total < 0.001) p_total = 0.001;
        if (p_total > 0.49) p_total = 0.49;

        // 5. 计算原始的理论连续 LLR (仅作参考映射依据)
        double raw_abs_llr = log((1.0 - p_total) / p_total);
        
        // =================================================================
        // 6. [第二层防御] 阶梯型量化 (Staircase Quantization)
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

        // 7. 设置符号位
        llr_out[i] = (logical_data[i] == 0) ? quantized_magnitude : -quantized_magnitude;
    }
}

// UEP 映射 (物理 -> 逻辑) - 在多码率实验中暂时不使用
void apply_uep_mapping(const uint8_t* physical, uint8_t* logical) {
    // 在多码率实验中，直接复制物理数据，不使用UEP映射
    memcpy(logical, physical, N * sizeof(uint8_t));
}

// [修复] 真正的 PUF 噪声生成函数
// 参数 scale: 必须与 initialize_llr 中使用的 scale 保持一致 (通常是 3.0)
void generate_puf_response_optimized(uint8_t* response, const uint8_t* golden, 
                                   double env_factor, double global_noise_floor, 
                                   int length) {
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

        // 5. 蒙特卡洛掷骰子
        // 生成 0.0 到 1.0 的随机数
        double rand_val = (double)rand() / RAND_MAX;
        
        if (rand_val < p_total) {
            // 发生翻转
            response[i] = golden[i] ^ 1;
        } else {
            // 保持原值
            response[i] = golden[i];
        }
    }
}

// 确保目录存在的函数
void ensure_directory_exists(const char *dir_path) {
    #ifdef _WIN32
        mkdir(dir_path);
    #else
        mkdir(dir_path, 0755);
    #endif
}

// 主测试函数
int main(int argc, char *argv[]) {
    // 默认scale值为2.0，可以通过命令行参数指定
    double scale_value = 2.0;
    
    // 解析命令行参数
    if (argc > 1) {
        if (strcmp(argv[1], "--help") == 0 || strcmp(argv[1], "-h") == 0) {
            printf("Usage: %s [scale_value]\n", argv[0]);
            printf("scale_value: PUF error rate scaling factor (default: 2.0)\n");
            return 0;
        }
        scale_value = atof(argv[1]);
        if (scale_value < 0) {
            printf("Error: scale_value cannot be negative\n");
            return 1;
        }
    }
    
    // 使用与scale相关的随机种子，确保不同scale参数下生成不同的随机序列
    srand(time(NULL)); // 与 one_bit_mask_llr_experiment 一致
    
    // 定义输出目录
    char output_dir[100];
    char csv_filename[150];
    
    // 生成输出目录路径（支持跨平台）
    sprintf(output_dir, "./scale=%.1f", scale_value);
    ensure_directory_exists(output_dir);
    
    // 生成包含scale值的文件名和完整路径（支持跨平台）
    #ifdef _WIN32
        sprintf(csv_filename, "%s\\fer_comparison_%s.csv", output_dir, RATE_SUFFIX);
    #else
        sprintf(csv_filename, "%s/fer_comparison_%s.csv", output_dir, RATE_SUFFIX);
    #endif
    
    // 打开CSV文件 (写入模式 - 每次运行都会覆盖原有数据)
    FILE *csv_file = fopen(csv_filename, "w");
    if (csv_file == NULL) {
        printf("Error opening CSV file!\n");
        printf("Error code: %d, Error message: %s\n", errno, strerror(errno));
        return 1;
    }
    

    
    // 输出配置信息
    printf("=== LDPC Performance Test with PUF Real Data (Rate=%s) ===\n", RATE_SUFFIX);
    printf("码率: %s\n", RATE_SUFFIX);
    printf("N=%d, K=%d\n", N, K);
    printf("核心挑战: PUF 真实错误率 + 环境噪声\n");
    printf("LDPC矩阵: QC-PEG生成，强列位置和列重与多码长实验一致\n");
    printf("抹除阈值: 0.15 (降低后的值)\n");
    printf("噪声范围: 0.001 到 0.100，步长 0.001\n");
    printf("测试方法: 基于目标错误数的蒙特卡洛仿真 (TARGET_ERRORS=75, MAX_TESTS=10000000)\n"); // 匹配参考目录设置
    printf("PUF 错误率倍率: %.1f\n", scale_value);
    printf("scale=1表示使用正常的PUF错误率进行测试\n");
    printf("测试流程: 随机消息 → 编码 → 加噪(PUF+环境) → 解码 → 验证\n");

    
    // 写入CSV表头，增加 Actual_BER 列和平均迭代次数列
    fprintf(csv_file, "Noise_Rate,Actual_BER,Baseline_FER,Optimized_FER,Staircase_FER,Improvement,Avg_Iter_Baseline,Avg_Iter_Optimized,Avg_Iter_Staircase\n");
    printf("\nNoise_Rate, Actual_BER, Baseline_FER, Optimized_FER, Staircase_FER, Improvement, Avg_Iter_Baseline, Avg_Iter_Optimized, Avg_Iter_Staircase\n");
    printf("=======================================================================================================\n");
    
    // 定义噪声范围和步长
    double start_noise = 0.001;
    double end_noise = 0.100;
    double step = 0.001;
    
    // 使用整数计数来避免浮点数精度问题
    int num_steps = (int)((end_noise - start_noise) / step) + 1;
    
    printf("Number of noise steps: %d\n", num_steps);
    
    // 针对每种噪声率运行测试
    for (int step_idx = 0; step_idx < num_steps; step_idx++) {
        double noise_rate = start_noise + step_idx * step;
        printf("Testing noise rate: %.3f\n", noise_rate);
        
        // 基于目标错误数的蒙特卡洛仿真（与 one_bit_mask_llr_experiment 一致）
        const int TARGET_ERRORS = 50; // 目标错误数，用于统计可靠性
        const long long MAX_TESTS = 10000000; // 最大测试次数，防止无限循环
        
        long long total_tests_run = 0;
        long long total_fail_base = 0;
        long long total_fail_opt = 0;
        long long total_fail_staircase = 0;
        long long total_bit_errors = 0;
        long long total_bits_simulated = 0;
        long long total_iter_base = 0;
        long long total_iter_opt = 0;
        long long total_iter_staircase = 0;
        long long success_count_base = 0;
        long long success_count_opt = 0;
        long long success_count_staircase = 0;

        #pragma omp parallel
        {
            // 每个线程的局部变量
            long long local_tests_run = 0;
            long long local_fail_base = 0;
            long long local_fail_opt = 0;
            long long local_fail_staircase = 0;
            long long local_bit_errors = 0;
            long long local_iter_base = 0;
            long long local_iter_opt = 0;
            long long local_iter_staircase = 0;
            long long local_success_base = 0;
            long long local_success_opt = 0;
            long long local_success_staircase = 0;
            
            // 线程局部变量
            uint8_t message[K];
            uint8_t codeword[N];
            uint8_t noisy_codeword[N];
            uint8_t decoded_baseline[N];
            uint8_t decoded_optimized[N];
            uint8_t decoded_staircase[N];
            int8_t llr_baseline[N];
            int8_t llr_optimized[N];
            int8_t llr_staircase[N];
            
            // 循环直到达到目标错误数或最大测试次数
            while (1) {
                // 检查是否达到全局停止条件
                long long global_fail_base;
                long long global_fail_opt;
                long long global_fail_staircase;
                long long global_tests;
                
                #pragma omp atomic read
                global_fail_base = total_fail_base;
                #pragma omp atomic read
                global_fail_opt = total_fail_opt;
                #pragma omp atomic read
                global_fail_staircase = total_fail_staircase;
                #pragma omp atomic read
                global_tests = total_tests_run;
                
                // 所有三个方案都达到目标错误数或达到最大测试次数时停止
                if (global_fail_base >= TARGET_ERRORS && global_fail_opt >= TARGET_ERRORS && global_fail_staircase >= TARGET_ERRORS) break;
                if (global_tests >= MAX_TESTS) break;
                
                // 1. 使用全0消息作为测试
                for (int i = 0; i < K; i++) message[i] = 0; // 全0消息
                
                // 2. 编码
                ldpc_encode(message, codeword);
                
                // 3. 生成带噪声的码字
                generate_puf_response_optimized(noisy_codeword, codeword, scale_value, noise_rate, N);
                
                // 4. 统计解码前的误码数
                for (int i = 0; i < N; i++) {
                    if (noisy_codeword[i] != codeword[i]) {
                        local_bit_errors++;
                    }
                }
                
                // 5. A组: Baseline (传统方案)
                {
                    // 初始化LLR，只知道背景噪声
                    initialize_llr_standard(llr_baseline, noisy_codeword, N, noise_rate);
                    
                    // 解码，获取迭代次数
                    int iter_count = ldpc_decode_nms(llr_baseline, decoded_baseline);
                    
                    if (iter_count == 0) {
                        local_fail_base++;
                    } else {
                        // 检查是否与原始消息一致（只检查前K位信息位）
                        int has_error = 0;
                        for (int i = 0; i < K; i++) {
                            if (decoded_baseline[i] != message[i]) {
                                has_error = 1;
                                break;
                            }
                        }
                        if (has_error) {
                            local_fail_base++;
                        } else {
                            local_iter_base += iter_count;
                            local_success_base++;
                        }
                    }
                }
                
                // 6. B组: Optimized (Reliability LLR + Erasure only)
                {
                    // 初始化LLR：使用PUF可靠性感知和抹除策略，但不使用UEP映射
                    initialize_llr_reliability_aware(llr_optimized, noisy_codeword, NULL, N, scale_value, noise_rate);
                    
                    // 解码，获取迭代次数
                    int iter_count = ldpc_decode_nms(llr_optimized, decoded_optimized);
                    
                    if (iter_count == 0) {
                        local_fail_opt++;
                    } else {
                        // 检查是否与原始消息一致（只检查前K位信息位）
                        int has_error = 0;
                        for (int i = 0; i < K; i++) {
                            if (decoded_optimized[i] != message[i]) {
                                has_error = 1;
                                break;
                            }
                        }
                        if (has_error) {
                            local_fail_opt++;
                        } else {
                            local_iter_opt += iter_count;
                            local_success_opt++;
                        }
                    }
                }
                
                // 7. C组: Staircase Quantization (阶梯型量化)
                {
                    // 初始化LLR：使用阶梯型量化的LLR初始化
                    initialize_llr_staircase_quantization(llr_staircase, noisy_codeword, NULL, N, scale_value, noise_rate);
                    
                    // 解码，获取迭代次数
                    int iter_count = ldpc_decode_nms(llr_staircase, decoded_staircase);
                    
                    if (iter_count == 0) {
                        local_fail_staircase++;
                    } else {
                        // 检查是否与原始消息一致（只检查前K位信息位）
                        int has_error = 0;
                        for (int i = 0; i < K; i++) {
                            if (decoded_staircase[i] != message[i]) {
                                has_error = 1;
                                break;
                            }
                        }
                        if (has_error) {
                            local_fail_staircase++;
                        } else {
                            local_iter_staircase += iter_count;
                            local_success_staircase++;
                        }
                    }
                }
                
                local_tests_run++;
                
                // 定期合并局部统计到全局统计（每1000次测试）
                if (local_tests_run % 1000 == 0) {
                    #pragma omp atomic
                    total_tests_run += local_tests_run;
                    #pragma omp atomic
                    total_fail_base += local_fail_base;
                    #pragma omp atomic
                    total_fail_opt += local_fail_opt;
                    #pragma omp atomic
                    total_fail_staircase += local_fail_staircase;
                    #pragma omp atomic
                    total_bit_errors += local_bit_errors;
                    #pragma omp atomic
                    total_iter_base += local_iter_base;
                    #pragma omp atomic
                    total_iter_opt += local_iter_opt;
                    #pragma omp atomic
                    total_iter_staircase += local_iter_staircase;
                    #pragma omp atomic
                    success_count_base += local_success_base;
                    #pragma omp atomic
                    success_count_opt += local_success_opt;
                    #pragma omp atomic
                    success_count_staircase += local_success_staircase;
                    
                    // 重置局部变量
                    local_tests_run = 0;
                    local_fail_base = 0;
                    local_fail_opt = 0;
                    local_fail_staircase = 0;
                    local_bit_errors = 0;
                    local_iter_base = 0;
                    local_iter_opt = 0;
                    local_iter_staircase = 0;
                    local_success_base = 0;
                    local_success_opt = 0;
                    local_success_staircase = 0;
                }
            }
            
            // 合并剩余的局部统计
            if (local_tests_run > 0) {
                #pragma omp atomic
                total_tests_run += local_tests_run;
                #pragma omp atomic
                total_fail_base += local_fail_base;
                #pragma omp atomic
                total_fail_opt += local_fail_opt;
                #pragma omp atomic
                total_fail_staircase += local_fail_staircase;
                #pragma omp atomic
                total_bit_errors += local_bit_errors;
                #pragma omp atomic
                total_iter_base += local_iter_base;
                #pragma omp atomic
                total_iter_opt += local_iter_opt;
                #pragma omp atomic
                total_iter_staircase += local_iter_staircase;
                #pragma omp atomic
                success_count_base += local_success_base;
                #pragma omp atomic
                success_count_opt += local_success_opt;
                #pragma omp atomic
                success_count_staircase += local_success_staircase;
            }
        }
        
        // 计算总比特数
        total_bits_simulated = total_tests_run * N;
        
        // 计算FER
        double fer_base = (total_tests_run > 0) ? (double)total_fail_base / total_tests_run : 0.0;
        double fer_opt = (total_tests_run > 0) ? (double)total_fail_opt / total_tests_run : 0.0;
        double fer_staircase = (total_tests_run > 0) ? (double)total_fail_staircase / total_tests_run : 0.0;
        double improve = 0.0;
        if (fer_base > 0) {
            improve = (fer_base - fer_staircase) / fer_base * 100.0;
        }
        
        // 【新增】计算实际误码率
        double actual_ber = (total_bits_simulated > 0) ? (double)total_bit_errors / total_bits_simulated : 0.0;
        
        // 计算平均迭代次数
        double avg_iter_base = (success_count_base > 0) ? (double)total_iter_base / success_count_base : 0;
        double avg_iter_opt = (success_count_opt > 0) ? (double)total_iter_opt / success_count_opt : 0;
        double avg_iter_staircase = (success_count_staircase > 0) ? (double)total_iter_staircase / success_count_staircase : 0;
        
        // 输出结果到控制台和CSV文件
        printf("%.3f, %.5f, %.6f, %.6f, %.6f, %.1f%%, %.2f, %.2f, %.2f\n", 
               noise_rate, actual_ber, fer_base, fer_opt, fer_staircase, improve, 
               avg_iter_base, avg_iter_opt, avg_iter_staircase);
        fprintf(csv_file, "%.3f,%.5f,%.6f,%.6f,%.6f,%.1f,%.2f,%.2f,%.2f\n", 
                noise_rate, actual_ber, fer_base, fer_opt, fer_staircase, improve, 
                avg_iter_base, avg_iter_opt, avg_iter_staircase);
        fflush(stdout);
        fflush(csv_file);
        
        // 检查停止条件 - 当所有三种方案的 FER 都接近 1 时停止
        if (fer_base >= 0.999 && fer_opt >= 0.999 && fer_staircase >= 0.999) {
            // 当所有三种方案的 FER 都接近 1 时停止实验
            printf("⚠️  停止条件: 所有方案的 FER 都接近 1 (Baseline=%.6f, Optimized=%.6f, Staircase=%.6f)\n", fer_base, fer_opt, fer_staircase);
            break;
        } else if (noise_rate > 0.15) {
            // 当噪声率超过 0.15 时停止实验
            printf("⚠️  停止条件: Noise_Rate = %.3f > 0.15\n", noise_rate);
            break;
        }
    }
    
    // 关闭文件
    fclose(csv_file);
    
    printf("\n========================================================\n");
    printf("=== 测试完成！===\n");
    printf("结果已保存到 %s\n", csv_filename);
    
    return 0;
}
