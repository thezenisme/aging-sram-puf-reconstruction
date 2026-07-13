// LDPC C++库的C接口包装器
// 用于连接C项目和C++ LDPC库

#ifndef LDPC_WRAPPER_H
#define LDPC_WRAPPER_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// 初始化LDPC编解码器
// 参数：
//   block_length: 码字长度N
//   info_length: 信息位长度K
//   rate_index: 码率索引 (0: 1/2, 1: 2/3, 2: 3/4, 3: 5/6)
//   use_wifi: 是否使用WiFi标准LDPC码 (1: 是, 0: 否)
// 返回值：
//   0: 成功
//   -1: 失败
int ldpc_wrapper_init(unsigned block_length, unsigned info_length, unsigned rate_index, int use_wifi);

// 释放LDPC编解码器资源
void ldpc_wrapper_free();

// LDPC编码函数
// 参数：
//   message: 输入信息位 (长度为K)
//   codeword: 输出码字 (长度为N)
// 返回值：
//   0: 成功
//   -1: 失败
int ldpc_wrapper_encode(const uint8_t* message, uint8_t* codeword);

// LDPC解码函数
// 参数：
//   llr_in: 输入LLR值 (长度为N)
//   decoded_out: 输出解码后的码字 (长度为N)
//   max_iter: 最大迭代次数
//   use_min_sum: 是否使用最小和解码算法 (1: 是, 0: 否)
// 返回值：
//   0: 解码失败
//   1: 解码成功
int ldpc_wrapper_decode(const double* llr_in, uint8_t* decoded_out, unsigned max_iter, int use_min_sum);

// 检查码字是否有效
// 参数：
//   codeword: 输入码字 (长度为N)
// 返回值：
//   0: 无效
//   1: 有效
int ldpc_wrapper_check_codeword(const uint8_t* codeword);

// 获取当前LDPC码参数
// 参数：
//   pN: 输出码字长度N
//   pK: 输出信息位长度K
//   pM: 输出校验位长度M
void ldpc_wrapper_get_params(unsigned* pN, unsigned* pK, unsigned* pM);

#ifdef __cplusplus
}
#endif

#endif // LDPC_WRAPPER_H
