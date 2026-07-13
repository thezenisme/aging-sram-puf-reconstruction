// LDPC解码算法实现 - 使用C++ LDPC库的版本

#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "ldpc.h"
#include "ldpc_wrapper.h"

// 根据编译时定义的码率包含相应的头文件
#ifdef TEST_RATE_1_2
    #include "h_matrix_1_2.h"
    #include "g_matrix_1_2.h"
    #define N N_1_2
    #define K K_1_2
    #define M M_1_2
    #define H_row_indices H_row_indices_1_2
    #define H_row_degrees H_row_degrees_1_2
    #define G_row_indices G_row_indices_1_2
    #define G_row_degrees G_row_degrees_1_2
    #define MAX_ROW_DEGREE 64
    #define G_ROWS K
#elif defined(TEST_RATE_2_3)
    #include "h_matrix_2_3.h"
    #include "g_matrix_2_3.h"
    #define N N_2_3
    #define K K_2_3
    #define M M_2_3
    #define H_row_indices H_row_indices_2_3
    #define H_row_degrees H_row_degrees_2_3
    #define G_row_indices G_row_indices_2_3
    #define G_row_degrees G_row_degrees_2_3
    #define MAX_ROW_DEGREE 64
    #define G_ROWS K
#elif defined(TEST_RATE_3_4)
    #include "h_matrix_3_4.h"
    #include "g_matrix_3_4.h"
    #define N N_3_4
    #define K K_3_4
    #define M M_3_4
    #define H_row_indices H_row_indices_3_4
    #define H_row_degrees H_row_degrees_3_4
    #define G_row_indices G_row_indices_3_4
    #define G_row_degrees G_row_degrees_3_4
    #define MAX_ROW_DEGREE 64
    #define G_ROWS K
#else
    #error "No rate defined"
#endif

// 符号函数
int8_t sign(int8_t x) {
    return (x >= 0) ? 1 : -1;
}

// 绝对值
int8_t my_abs(int8_t x) {
    return (x >= 0) ? x : -x;
}

// 最小值
int8_t min(int8_t a, int8_t b) {
    return (a < b) ? a : b;
}

// LLR初始化函数
// 将PUF响应和辅助数据转换为LDPC解码器可处理的LLR格式
void initialize_llr(int8_t* llr_input, const uint8_t* puf_response, const uint8_t* helper_data, int length) {
    for (int i = 0; i < length; i++) {
        // 计算带噪码字 C' = R' ^ W
        uint8_t noisy_bit = puf_response[i] ^ helper_data[i];
        
        // 0 -> 正置信度, 1 -> 负置信度
        // 基于PUF误码率，使用更强的LLR值以提高解码成功率
        llr_input[i] = (noisy_bit == 0) ? 8 : -8;
    }
}

// 将int8_t类型的LLR转换为double类型，用于C++ LDPC库
void convert_llr_int8_to_double(const int8_t* llr_int8, double* llr_double, int length) {
    for (int i = 0; i < length; i++) {
        llr_double[i] = (double)llr_int8[i];
    }
}

// LDPC编码函数 - 使用生成的G矩阵实现
void ldpc_encode(const uint8_t* message, uint8_t* codeword) {
    // 初始化码字为全0
    memset(codeword, 0, N * sizeof(uint8_t));
    
    // 1. 系统位直接复制原始信息位（前K位）
    for (int i = 0; i < K; i++) {
        codeword[i] = message[i];
    }
    
    // 2. 计算校验位（后M位）
    // G矩阵是系统形式 [I | P^T]，所以校验位是 message * P^T
    for (int row = 0; row < G_ROWS; row++) {
        if (message[row] == 1) {
            // 遍历G矩阵中对应行的P^T部分（即列索引 >= K的部分）
            for (int i = 0; i < MAX_G_ROW_DEGREE; i++) {
                uint16_t col = G_row_indices[row][i];
                if (col == 0 && i > 0) { // 假设0是填充值
                    break;
                }
                if (col >= K) { // 只处理校验位部分
                    codeword[col] ^= 1;
                }
            }
        }
    }
}

// 归一化因子 (0.75 * 128 = 96, 用于定点计算)
// 或者简单位移: x * 0.75 = x - (x >> 2)
#define NORM_FACTOR_0_75(x) ((x) - ((x) >> 2))

// 标准 NMS 解码算法实现
// 返回值：
//   - 正数：解码成功，返回实际迭代次数
//   - 0：解码失败（达到最大迭代次数）
int ldpc_decode_nms(int8_t* llr_in, uint8_t* decoded_out) {
    // 变量节点 (Variable Nodes) 后验信息 LLR
    // 初始化为信道输入 LLR
    int8_t v_nodes[N];
    memcpy(v_nodes, llr_in, N * sizeof(int8_t));

    // 校验节点到变量节点的消息 (Check to Variable Messages)
    // 初始化为 0
    int8_t c_to_v[M][MAX_ROW_DEGREE];
    memset(c_to_v, 0, sizeof(c_to_v));

    int iter;
    for (iter = 1; iter <= MAX_ITER; iter++) {
        
        // --- 步骤 1: 校验节点更新 (Check Node Update) ---
        for (int i = 0; i < M; i++) {
            // 每一行（校验方程）需要找到绝对值最小的两个输入
            int8_t min1 = 127; // 最小值
            int8_t min2 = 127; // 次小值
            int min1_idx = -1; // 最小值的索引
            int8_t total_sign = 1; // 符号乘积

            // 1.1: 第一次遍历，计算 V->C 消息并寻找最小值
            for (int k = 0; k < H_row_degrees[i]; k++) {
                uint16_t col_idx = H_row_indices[i][k];
                
                // 跳过越界的列索引
                if (col_idx >= N) continue;
                
                // V->C 消息 = 当前变量节点后验 - 上一轮该校验节点发来的消息
                // (Extrinsic Message principle)
                int16_t v_msg_temp = v_nodes[col_idx] - c_to_v[i][k];
                
                // 饱和处理，防止溢出 int8
                if (v_msg_temp > 127) v_msg_temp = 127;
                if (v_msg_temp < -127) v_msg_temp = -127;
                int8_t v_msg = (int8_t)v_msg_temp;

                // 计算符号和绝对值
                int8_t abs_v = my_abs(v_msg);
                if (v_msg < 0) total_sign = -total_sign;

                // 更新最小值和次小值
                if (abs_v < min1) {
                    min2 = min1;
                    min1 = abs_v;
                    min1_idx = k;
                } else if (abs_v < min2) {
                    min2 = abs_v;
                }
            }

            // 1.2: 预计算归一化后的最小值和次小值，只计算一次
            int8_t norm_min1 = (min1 > 0) ? NORM_FACTOR_0_75(min1) : 0;
            int8_t norm_min2 = (min2 > 0) ? NORM_FACTOR_0_75(min2) : 0;
            
            // 1.3: 第二次遍历，计算并存储 C->V 消息
            for (int k = 0; k < H_row_degrees[i]; k++) {
                uint16_t col_idx = H_row_indices[i][k];
                
                // 跳过越界的列索引
                if (col_idx >= N) continue;
                
                // 重新获取 V->C 消息的符号
                int16_t v_msg_temp = v_nodes[col_idx] - c_to_v[i][k];
                // 饱和处理
                if (v_msg_temp > 127) v_msg_temp = 127;
                if (v_msg_temp < -127) v_msg_temp = -127;
                
                int8_t val_sign = (v_msg_temp < 0) ? -1 : 1;
                
                // 输出符号 = 总符号 * 当前输入符号 (相当于除以当前符号)
                int8_t out_sign = total_sign * val_sign;
                
                // 输出幅度：使用预计算的归一化值
                // (Min-Sum 近似的核心)
                int8_t magnitude = (k == min1_idx) ? norm_min2 : norm_min1;

                c_to_v[i][k] = out_sign * magnitude;
            }
        }

        // --- 步骤 2: 变量节点更新 (Variable Node Update) ---
        // 重置为信道输入 LLR
        memcpy(v_nodes, llr_in, N * sizeof(int8_t));
        
        // 累加所有连接的校验节点发来的消息
        for (int i = 0; i < M; i++) {
            for (int k = 0; k < H_row_degrees[i]; k++) {
                uint16_t col_idx = H_row_indices[i][k];
                
                // 跳过越界的列索引
                if (col_idx >= N) continue;
                
                int16_t sum = v_nodes[col_idx] + c_to_v[i][k];
                
                // 饱和截断 (Clipping)
                if (sum > CLIP_VAL) sum = CLIP_VAL;
                if (sum < -CLIP_VAL) sum = -CLIP_VAL;
                
                v_nodes[col_idx] = (int8_t)sum;
            }
        }

        // --- 步骤 3: 硬判决与伴随式校验 (Syndrome Check) ---
        int syndrome_error = 0;
        
        // 3.1 硬判决
        for (int j = 0; j < N; j++) {
            // LLR < 0 判为 1, LLR >= 0 判为 0
            decoded_out[j] = (v_nodes[j] < 0) ? 1 : 0;
        }
        
        // 3.2 计算校验子 H * C^T
        for (int i = 0; i < M; i++) {
            int parity = 0;
            for (int k = 0; k < H_row_degrees[i]; k++) {
                uint16_t col_idx = H_row_indices[i][k];
                
                // 跳过越界的列索引
                if (col_idx >= N) continue;
                
                parity ^= decoded_out[col_idx];
            }
            if (parity != 0) {
                syndrome_error = 1;
                break; // 只要有一个校验失败，即为失败
            }
        }

        if (syndrome_error == 0) {
            // 校验通过，提前结束迭代
            return iter;
        }
    }

    return 0; // 达到最大迭代次数仍未收敛
}
