// LDPC解码算法头文件

#ifndef LDPC_H
#define LDPC_H

#include <stdint.h>
// 注意：h_matrix.h不再直接包含，由调用者根据码率选择包含不同版本
#include "ldpc_wrapper.h"

// LDPC解码相关常量
#define MAX_ITER 50       // 最大迭代次数（从20增加到200）
#define CLIP_VAL 60        // LLR截断值，防止溢出
#define STRONG_LLR 30      // LLR初始强度，基于PUF误码率(5%)
#define KEY_LENGTH 256     // 密钥长度 (bits)

// 使用h_matrix.h中定义的QC-LDPC矩阵参数
// 不再取消之前定义的宏，因为h_matrix.h已经正确定义了这些参数

// 注意：R, K, N, M现在从h_matrix.h中获取，不再本地定义

// 符号函数
int8_t sign(int8_t x);

// 绝对值
int8_t my_abs(int8_t x);

// 最小值
int8_t min(int8_t a, int8_t b);

// LLR初始化函数
void initialize_llr(int8_t* llr_input, const uint8_t* puf_response, const uint8_t* helper_data, int length);

// 将int8_t类型的LLR转换为double类型，用于C++ LDPC库
void convert_llr_int8_to_double(const int8_t* llr_int8, double* llr_double, int length);

// LDPC归一化最小和(NMS)解码函数
int ldpc_decode_nms(int8_t* llr_in, uint8_t* decoded_out);

// LDPC编码函数
void ldpc_encode(const uint8_t* message, uint8_t* codeword);

#endif // LDPC_H
