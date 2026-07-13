import numpy as np
import sys
import os

# ==============================================================================
# 配置区域
# ==============================================================================
CONFIGS = {
    "long": {
        "n": 4096, 
        "k": 2048,
        "z": 128,       
        "high_deg": 12, 
        "suffix": "1_2_long",
        "strong_cols": [0, 10, 20]
    }
}

# 默认好块的列重
DEFAULT_DEGREE = 3

# ==============================================================================
# 优化点 1: 概率性验证 (解决 LONG 模式内存崩溃)
# ==============================================================================
def verify_orthogonality_probabilistic(G, H, num_tests=50):
    """
    概率性验证 G * H.T = 0.
    不再进行全量矩阵乘法，而是随机抽取向量 u 进行编码和校验。
    """
    K, N = G.shape

    print(f"   [Verify] 启动概率性验证 (随机测试 {num_tests} 次)...")

    for i in range(num_tests):
        # 1. 随机生成消息 u (0/1分布)
        u = np.random.randint(0, 2, K).astype(np.int8)

        # 2. 编码: c = u * G (分步计算节省内存)
        c = np.dot(u, G) % 2

        # 3. 校验: s = c * H.T
        s = np.dot(c, H.T) % 2

        # 4. 检查校验子是否全为 0
        if np.sum(s) != 0:
            print(f"   [Fail] 测试 {i+1}/{num_tests} 失败! 发现非零校验子。")
            return False

    return True

# ==============================================================================
# 核心算法：生成与 H 完美正交的 G (高斯消元)
# ==============================================================================
def compute_g_orthogonal(H):
    """
    输入: 校验矩阵 H (M x N)
    输出: 生成矩阵 G (K x N), 满足 G * H.T = 0 (mod 2)
    """
    M, N = H.shape
    K = N - M
    H_sys = H.copy()
    col_permutation = np.arange(N)
    pivot_row = 0

    for col_idx in range(K, N):
        if pivot_row >= M: break
        pivot_found = False
        for r in range(pivot_row, M):
            if H_sys[r, col_idx] == 1:
                if r != pivot_row:
                    H_sys[[pivot_row, r], :] = H_sys[[r, pivot_row], :]
                pivot_found = True
                break
        
        if not pivot_found:
            swap_target = -1
            for candidate_col in range(0, K):
                for r in range(pivot_row, M):
                    if H_sys[r, candidate_col] == 1:
                        if r != pivot_row:
                            H_sys[[pivot_row, r], :] = H_sys[[r, pivot_row], :]
                        swap_target = candidate_col
                        break
                if swap_target != -1: break
            
            if swap_target != -1:
                H_sys[:, [col_idx, swap_target]] = H_sys[:, [swap_target, col_idx]]
                col_permutation[[col_idx, swap_target]] = col_permutation[[swap_target, col_idx]]
            else:
                print("Error: 矩阵秩不足")
                return None

        for r in range(M):
            if r != pivot_row and H_sys[r, col_idx] == 1:
                H_sys[r, :] ^= H_sys[pivot_row, :]
        pivot_row += 1

    P_prime = H_sys[:, 0:K]
    I_K = np.eye(K, dtype=int)
    G_sys = np.hstack((I_K, P_prime.T))
    inverse_permutation = np.argsort(col_permutation)
    G_final = G_sys[:, inverse_permutation]
    return G_final

def compute_g_nullspace_fallback(H, target_k):
    """
    Robust GF(2) nullspace fallback.
    If H contains redundant checks, its nullity can be larger than N-M.  The
    experiment still uses target_k encoder rows, so we export the first target_k
    independent nullspace vectors.
    """
    M, N = H.shape
    pivots = {}

    for r in range(M):
        x = 0
        for col in np.flatnonzero(H[r]):
            x |= 1 << int(col)

        while x:
            pivot = x.bit_length() - 1
            if pivot in pivots:
                x ^= pivots[pivot]
            else:
                pivots[pivot] = x
                break

    rank = len(pivots)
    nullity = N - rank
    print(f"   [Fallback] rank(H)={rank}, nullity={nullity}; exporting {target_k} generator rows.")

    if nullity < target_k:
        print("   [Fallback] Error: nullity is smaller than requested K.")
        return None

    # Reduce pivot rows so each pivot column appears in exactly one pivot row.
    pivot_cols = sorted(pivots.keys())
    for pivot in pivot_cols:
        pivot_row = pivots[pivot]
        mask = 1 << pivot
        for other in pivot_cols:
            if other != pivot and (pivots[other] & mask):
                pivots[other] ^= pivot_row

    pivot_set = set(pivot_cols)
    free_cols = [c for c in range(N) if c not in pivot_set]

    G = np.zeros((target_k, N), dtype=np.uint8)
    for row_idx, free_col in enumerate(free_cols[:target_k]):
        vec = 1 << free_col
        for pivot, pivot_row in pivots.items():
            if (pivot_row >> free_col) & 1:
                vec |= 1 << pivot

        x = vec
        while x:
            lsb = x & -x
            col = lsb.bit_length() - 1
            G[row_idx, col] = 1
            x ^= lsb

    return G

# ==============================================================================
# 优化点 2 & 3: 严格 QC-PEG 构造 (消除 4 环 + 强锚点均衡)
# ==============================================================================

def has_4_cycle_qc(H_base, row, col, current_shift, Z):
    """
    检查在 (row, col) 放置 current_shift 是否会构成 QC-LDPC 4 环
    """
    rows_in_this_col = np.where(H_base[:, col] != -1)[0]
    for r_prev in rows_in_this_col:
        diff_curr = (current_shift - H_base[r_prev, col]) % Z
        for c_other in range(H_base.shape[1]):
            if c_other == col: continue
            val_at_row = H_base[row, c_other]
            val_at_prev = H_base[r_prev, c_other]
            if val_at_row != -1 and val_at_prev != -1:
                diff_other = (val_at_row - val_at_prev) % Z
                if diff_curr == diff_other:
                    return True 
    return False

def generate_qc_peg_matrix_optimized(n, k, z, high_deg, strong_cols=None):
    """
    Strict PEG 构造函数
    包含：4环检查、行稀释策略、回退机制
    """
    n_base = n // z
    m_base = n_base // 2

    H_base = np.full((m_base, n_base), -1, dtype=int)

    # 使用传入的强列索引列表，默认使用前m_base个列
    if strong_cols is None:
        strong_base_cols = [i for i in range(m_base)]
    else:
        # 确保强列索引不超过基矩阵列数
        strong_base_cols = [col for col in strong_cols if col < n_base]

    strong_base_set = set(strong_base_cols)
    
    print(f"   [Strict-PEG] 开始构造: Base {m_base}x{n_base}, Z={z}")
    print(f"   [Config] 强锚点列索引: {strong_base_cols}")

    for col in range(n_base):
        is_strong = (col in strong_base_set)
        
        # 目标度数设定
        if is_strong:
            target_deg = high_deg
            # Short 码的物理极限修正
            if m_base <= 8 and target_deg > 6:
                target_deg = 6
        else:
            target_deg = DEFAULT_DEGREE
        
        deg_count = 0
        
        # 尝试添加边
        for _ in range(target_deg):
            # PEG 策略：普通列优先选择度数最小的行；
            # 强列先均衡每行已有强锚点边数，再比较总行重。
            current_row_weights = np.sum(H_base != -1, axis=1)
            if is_strong and strong_base_cols:
                strong_row_counts = np.sum(H_base[:, strong_base_cols] != -1, axis=1)
                sorted_rows = np.lexsort((current_row_weights, strong_row_counts))
            else:
                sorted_rows = np.argsort(current_row_weights)
            
            edge_placed = False
            
            for r in sorted_rows:
                if H_base[r, col] != -1: continue 
                
                # --- 优化点 2: 4环检查 ---
                shifts = np.random.permutation(z)
                for s in shifts:
                    if not has_4_cycle_qc(H_base, r, col, s, z):
                        H_base[r, col] = s
                        edge_placed = True
                        deg_count += 1
                        break 
                
                if edge_placed: break
            
            # 回退策略：如果找不到无环边，这列就少一条边，不要强行加
            if not edge_placed:
                pass 
                
    # 扩展为 H 矩阵
    M = m_base * z
    N = n_base * z
    H = np.zeros((M, N), dtype=int)
    for r in range(m_base):
        for c in range(n_base):
            shift = H_base[r, c]
            if shift != -1:
                for i in range(z):
                    H[r*z+i, c*z+((i+shift)%z)] = 1
    
    return H, strong_base_cols

# ==============================================================================
# 导出函数 (保持不变)
# ==============================================================================
def export_files(H, G, config, strong_base_cols):
    suffix = config["suffix"]
    N, K = config["n"], config["k"]
    M = N - K
    z = config["z"]
    c_name = "matrix_data_" + suffix + ".c"
    h_name = "h_matrix_" + suffix + ".h"
    g_name = "g_matrix_" + suffix + ".h"
    
    print("   [Export] 写入 " + c_name + " ...")
    strong_col_indices = [col * z for col in strong_base_cols]
    strong_idx_str = ", ".join(map(str, strong_col_indices))
    
    # 生成列类型掩码：1表示强列，0表示弱列
    n_base = N // z
    col_type_mask = []
    for col in range(n_base):
        if col in strong_base_cols:
            # 强列对应的z个位都是STRONG
            col_type_mask.extend([1] * z)
        else:
            # 弱列对应的z个位都是WEAK
            col_type_mask.extend([0] * z)
    col_type_mask_str = ", ".join(map(str, col_type_mask))
    
    with open(h_name, "w") as f:
        f.write("#ifndef H_MAT_" + suffix.upper() + "\n")
        f.write("#define H_MAT_" + suffix.upper() + "\n")
        f.write("#include <stdint.h>\n")
        f.write("#define N_" + suffix.upper() + " " + str(N) + "\n")
        f.write("#define K_" + suffix.upper() + " " + str(K) + "\n")
        f.write("#define M_" + suffix.upper() + " " + str(M) + "\n")
        f.write("#define EXPANSION_FACTOR_Z " + str(z) + "\n")
        f.write("extern const uint16_t H_row_indices_" + suffix + "[" + str(M) + "][64];\n")
        f.write("extern const uint8_t H_row_degrees_" + suffix + "[" + str(M) + "];\n")
        f.write("\n// Distributed UEP Config\n")
        f.write("#define NUM_STRONG_ANCHORS " + str(len(strong_col_indices)) + "\n")
        f.write("static const int STRONG_ANCHOR_COLS[] = {{ {0} }};\n".format(strong_idx_str))
        f.write("\n// LLR Scaling\n")
        f.write("#define LLR_SCALE_ERASURE 0.0f\n")
        f.write("#define LLR_SCALE_STRONG  1.0f\n")
        f.write("#define LLR_SCALE_WEAK    0.6f\n")
        f.write("extern const uint8_t COL_TYPE_MASK[];\n")
        f.write("#endif\n")
    
    with open(g_name, "w") as f:
        f.write("#ifndef G_MAT_" + suffix.upper() + "\n")
        f.write("#define G_MAT_" + suffix.upper() + "\n")
        f.write("#include <stdint.h>\n")
        f.write("#define G_ROWS_" + suffix.upper() + " " + str(K) + "\n")
        f.write("#define MAX_G_ROW_DEGREE " + str(N) + "\n")
        f.write("extern const uint16_t G_row_indices_" + suffix + "[" + str(K) + "][MAX_G_ROW_DEGREE];\n")
        f.write("extern const uint16_t G_row_degrees_" + suffix + "[" + str(K) + "];\n")
        f.write("#endif\n")
    
    with open(c_name, "w") as f:
        f.write('#include "' + h_name + '"\n')
        f.write('#include "' + g_name + '"\n')
        f.write('\n')
        # H Indices
        f.write('const uint16_t H_row_indices_' + suffix + '[' + str(M) + '][64] = {\n')
        for r in range(M):
            idx = np.where(H[r]==1)[0]
            pad = [0]*(64-len(idx))
            f.write('    {' + ','.join(map(str, list(idx)+pad)) + '},\n')
        f.write('};\n')
        # H Degrees
        f.write('const uint8_t H_row_degrees_' + suffix + '[' + str(M) + '] = {')
        f.write(','.join(map(str, np.sum(H, axis=1))))
        f.write('};\n\n')
        # H Col Degrees
        f.write('const uint8_t H_col_degrees_' + suffix + '[' + str(N) + '] = {')
        f.write(','.join(map(str, np.sum(H, axis=0))))
        f.write('};\n\n')
        # Column Type Mask
        f.write('const uint8_t COL_TYPE_MASK[] = {\n')
        # 每行输出16个元素，方便阅读
        for i in range(0, N, 16):
            line = col_type_mask[i:i+16]
            f.write('    ' + ','.join(map(str, line)) + ',\n')
        f.write('};\n\n')
        # G Indices
        g_row_deg = np.sum(G, axis=1)
        max_deg = int(np.max(g_row_deg))
        f.write('const uint16_t G_row_indices_' + suffix + '[' + str(K) + '][MAX_G_ROW_DEGREE] = {\n')
        for r in range(K):
            idx = np.where(G[r]==1)[0]
            pad = [0]*(max_deg-len(idx))
            f.write('    {' + ','.join(map(str, list(idx)+pad)) + '},\n')
        f.write('};\n')
        # G Degrees
        f.write('const uint16_t G_row_degrees_' + suffix + '[' + str(K) + '] = {')
        f.write(','.join(map(str, g_row_deg)))
        f.write('};\n')

# ==============================================================================
# 主函数 (逻辑更新，支持命令行参数)
# ==============================================================================
def main():
    # 解析命令行参数
    seed_arg = None
    out_dir = None
    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--seed" and i+1 < len(sys.argv[1:]):
            seed_arg = int(sys.argv[i+2])
        elif arg.startswith("--seed="):
            seed_arg = int(arg.split("=")[1])
        elif arg == "--outdir" and i+1 < len(sys.argv[1:]):
            out_dir = sys.argv[i+2]
        elif arg.startswith("--outdir="):
            out_dir = arg.split("=")[1]

    if seed_arg is not None:
        np.random.seed(seed_arg)
        print(f">> 设置 numpy random seed = {seed_arg}")

    if out_dir is not None:
        os.makedirs(out_dir, exist_ok=True)
        orig_dir = os.getcwd()
        os.chdir(out_dir)
        print(f">> 输出目录: {out_dir}")

    for name, cfg in CONFIGS.items():
        print("\n>> 处理: " + name.upper() + " (N=" + str(cfg['n']) + ", K=" + str(cfg['k']) + ")")
        
        # 使用优化后的 Strictly-PEG 构造函数
        print("   [QC-PEG] 生成矩阵 (Strict Mode)...")
        H, strong_base_cols = generate_qc_peg_matrix_optimized(cfg['n'], cfg['k'], cfg['z'], cfg['high_deg'], cfg['strong_cols'])
        
        print("   [Math] 计算正交 G 矩阵...")
        G = compute_g_orthogonal(H)
        
        if G is None:
            print("   [Math] 系统化 G 生成失败，切换到零空间 fallback...")
            G = compute_g_nullspace_fallback(H, cfg['k'])
            if G is None:
                print("   [Error] G 生成失败，跳过")
                continue
            
        # 优化点 1: 根据矩阵大小选择验证方式
        if cfg['n'] >= 2048:
            is_valid = verify_orthogonality_probabilistic(G, H, num_tests=20)
        else:
            check = np.dot(G, H.T) % 2
            is_valid = (np.sum(check) == 0)

        if is_valid:
            print("   [Check] ✅ 验证通过！")
            export_files(H, G, cfg, strong_base_cols)
            print("   [Success] " + name.upper() + " 生成完成！")
        else:
            print("   [Check] ❌ 验证失败！")

    if out_dir is not None:
        os.chdir(orig_dir)

if __name__ == "__main__":
    main()
