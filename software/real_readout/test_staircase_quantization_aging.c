#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <errno.h>
#include <omp.h>

#ifdef _WIN32
    #define NOMINMAX
    #include <direct.h>
#else
    #include <sys/stat.h>
#endif

#include "ldpc_config.h"
#include "ldpc.h"
#include "puf_profile_long.h"

#define PROFILE_HOT_THRESHOLD 0.10

static uint8_t paper_hotspot_mask[N];
static int paper_hotspot_mask_ready = 0;
static const double *runtime_error_rates = NULL;
static const char *runtime_label = "no_aging";

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

static void ensure_directory_exists(const char *dir_path) {
#ifdef _WIN32
    _mkdir(dir_path);
#else
    mkdir(dir_path, 0755);
#endif
}

static int check_if_strong_column(int bit_index) {
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
            double p = ENROLL_PUF_ERROR_RATES[i % PUF_N];
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
    int masked_min_degree = 1000000;
    int masked_max_degree = 0;
    long long masked_degree_sum = 0;

    for (int i = 0; i < N; i++) {
        double p = ENROLL_PUF_ERROR_RATES[i % PUF_N];
        if (p >= PROFILE_HOT_THRESHOLD) profile_hot_count++;
        if (paper_hotspot_mask[i]) {
            int degree = col_degrees[i];
            masked_count++;
            if (p >= PROFILE_HOT_THRESHOLD) masked_profile_hot_count++;
            if (check_if_strong_column(i)) masked_in_declared_anchor++;
            if (expected_degree > 0 && degree >= expected_degree) masked_expected_degree_count++;
            if (degree < masked_min_degree) masked_min_degree = degree;
            if (degree > masked_max_degree) masked_max_degree = degree;
            masked_degree_sum += degree;
        }
    }

    if (masked_count == 0) masked_min_degree = 0;
    printf("=== Aging-case sanity check ===\n");
    printf("[QC] base matrix %dx%d, Z=%d, rate=%.3f\n",
           m_base, n_base, EXPANSION_FACTOR_Z, (double)K / (double)N);
    printf("[Profiles] enroll_mean=%.6f runtime_mean=%.6f level=%s\n",
           (double)({double s=0.0; for(int i=0;i<PUF_N;i++) s+=ENROLL_PUF_ERROR_RATES[i]; s/PUF_N;}),
           (double)({double s=0.0; for(int i=0;i<PUF_N;i++) s+=runtime_error_rates[i]; s/PUF_N;}),
           runtime_label);
    printf("[Paper Mask] target A=%d selected=%d profile-hot-selected=%d profile-hot-total=%d\n",
           target, masked_count, masked_profile_hot_count, profile_hot_count);
    printf("[Paper Mask] selected in anchors=%d/%d, selected with degree>=d_vs=%d/%d, degree min/avg/max=%d/%.2f/%d\n",
           masked_in_declared_anchor, masked_count, masked_expected_degree_count, masked_count,
           masked_min_degree,
           (masked_count > 0 ? (double)masked_degree_sum / masked_count : 0.0),
           masked_max_degree);
}

static void initialize_llr_staircase_quantization(int8_t* llr_out, const uint8_t* logical_data,
                                                   int length, double scale, double min_noise_floor) {
    build_paper_hotspot_mask(length);

    for (int i = 0; i < length; i++) {
        double p_puf = ENROLL_PUF_ERROR_RATES[i % PUF_N];
        if (paper_hotspot_mask[i]) {
            llr_out[i] = 0;
            continue;
        }

        double p_amplified = p_puf * scale;
        double scaled_p_puf = p_amplified + min_noise_floor;
        if (scaled_p_puf > 0.5) scaled_p_puf = 0.5;

        double p_total = scaled_p_puf;
        if (p_total < 0.001) p_total = 0.001;
        if (p_total > 0.49) p_total = 0.49;

        double raw_abs_llr = log((1.0 - p_total) / p_total);
        int8_t quantized_magnitude;
        if (raw_abs_llr < 0.5) quantized_magnitude = 2;
        else if (raw_abs_llr < 1.0) quantized_magnitude = 4;
        else if (raw_abs_llr < 1.5) quantized_magnitude = 6;
        else if (raw_abs_llr < 2.0) quantized_magnitude = 9;
        else if (raw_abs_llr < 2.8) quantized_magnitude = 14;
        else if (raw_abs_llr < 3.5) quantized_magnitude = 20;
        else if (raw_abs_llr < 4.5) quantized_magnitude = 28;
        else quantized_magnitude = 35;

        llr_out[i] = (logical_data[i] == 0) ? quantized_magnitude : -quantized_magnitude;
    }
}

void initialize_llr_standard(int8_t* llr_out, const uint8_t* data, int length, double fixed_p) {
    double p_used = fixed_p;
    if (p_used < 0.01) p_used = 0.01;
    double scaled_magnitude = log((1.0 - p_used) / p_used) * 10.0;
    if (scaled_magnitude > 60.0) scaled_magnitude = 60.0;
    if (scaled_magnitude < -60.0) scaled_magnitude = -60.0;
    int8_t val = (int8_t)scaled_magnitude;
    for (int i = 0; i < length; i++) {
        llr_out[i] = (data[i] == 0) ? val : -val;
    }
}

static void generate_puf_response_aging(uint8_t* response, const uint8_t* golden,
                                        double env_factor, double global_noise_floor,
                                        int length, uint32_t *rng_state) {
    for (int i = 0; i < length; i++) {
        int idx = i % PUF_N;
        double p_intrinsic = runtime_error_rates[idx];
        double p_amplified = p_intrinsic * env_factor;
        double p_total = p_amplified + global_noise_floor;
        if (p_total > 0.5) p_total = 0.5;
        double rand_val = rng_uniform_01(rng_state);
        response[i] = (rand_val < p_total) ? (golden[i] ^ 1u) : golden[i];
    }
}

static double mean_profile_rate(const double *profile) {
    double sum = 0.0;
    for (int i = 0; i < PUF_N; i++) sum += profile[i];
    return sum / (double)PUF_N;
}

static double compute_actual_raw_ber(const double *profile, double env_factor, double global_noise_floor) {
    double sum = 0.0;
    for (int i = 0; i < PUF_N; i++) {
        double p = profile[i] * env_factor + global_noise_floor;
        if (p > 0.5) p = 0.5;
        sum += p;
    }
    return sum / (double)PUF_N;
}

int main(int argc, char *argv[]) {
    double scale_value = 2.0;
    if (argc > 1) scale_value = atof(argv[1]);

    uint32_t base_seed = 12345u;
    int target_errors = 20;
    long long max_tests = 3000;
    double min_noise_rate = 0.001;
    double max_noise_rate = 0.08;
    int sanity_only = 0;
    const char *output_tag = NULL;
    int aging_level = 0;

    int numeric_arg = 0;
    for (int argi = 2; argi < argc; argi++) {
        if (strcmp(argv[argi], "--sanity-only") == 0) {
            sanity_only = 1;
        } else if (strncmp(argv[argi], "--tag=", 6) == 0) {
            output_tag = argv[argi] + 6;
        } else if (strncmp(argv[argi], "--aging-level=", 14) == 0) {
            aging_level = atoi(argv[argi] + 14);
        } else if (strncmp(argv[argi], "--min-noise=", 12) == 0) {
            min_noise_rate = atof(argv[argi] + 12);
        } else {
            if (numeric_arg == 0) base_seed = (uint32_t)strtoul(argv[argi], NULL, 10);
            else if (numeric_arg == 1) target_errors = atoi(argv[argi]);
            else if (numeric_arg == 2) max_tests = strtoll(argv[argi], NULL, 10);
            else if (numeric_arg == 3) max_noise_rate = atof(argv[argi]);
            numeric_arg++;
        }
    }

    runtime_error_rates = ENROLL_PUF_ERROR_RATES;
    runtime_label = "no_aging";
    if (aging_level == 12) {
        runtime_error_rates = RUNTIME_PUF_ERROR_RATES_12M;
        runtime_label = "aging_12m";
    } else if (aging_level == 24) {
        runtime_error_rates = RUNTIME_PUF_ERROR_RATES_24M;
        runtime_label = "aging_24m";
    }

    print_experiment_sanity();
    if (sanity_only) return 0;

    char output_dir[512];
    if (output_tag && output_tag[0]) {
        sprintf(output_dir, "test_results_%s_%s", runtime_label, output_tag);
    } else {
        sprintf(output_dir, "test_results_%s", runtime_label);
    }
    ensure_directory_exists(output_dir);

    char csv_filename[768];
    sprintf(csv_filename, "%s/fer_comparison_length_%s.csv", output_dir, LENGTH_SUFFIX);
    FILE *csv_file = fopen(csv_filename, "w");
    if (!csv_file) {
        fprintf(stderr, "Cannot open %s: %s\n", csv_filename, strerror(errno));
        return 1;
    }
    fprintf(csv_file, "Noise_Rate,Actual_BER,Baseline_FER,Staircase_FER,Improvement,Avg_Iter_Baseline,Avg_Iter_Staircase,Tested_Frames,Frame_Errors_Baseline,Frame_Errors_Staircase,Aging_Level,Enroll_BER,Runtime_BER\n");

    uint8_t input_message[K];
    memset(input_message, 0, sizeof(input_message));
    uint8_t codeword[N];
    ldpc_encode(input_message, codeword);

    double enroll_mean = mean_profile_rate(ENROLL_PUF_ERROR_RATES);
    double runtime_mean = mean_profile_rate(runtime_error_rates);

    printf("PUF Scale: %.3f\n", scale_value);
    printf("Seed: %u\n", base_seed);
    printf("Aging Level: %s\n", runtime_label);
    printf("Enrollment BER: %.6f Runtime BER: %.6f\n", enroll_mean, runtime_mean);

    for (int step = 0; step < 200; step++) {
        double noise_rate = min_noise_rate + 0.001 * step;
        if (noise_rate > max_noise_rate + 1e-12) break;

        const int TARGET_ERRORS = target_errors;
        const long long MAX_TESTS = max_tests;
        long long total_tests_run = 0;
        long long total_fail_base = 0;
        long long total_fail_staircase = 0;
        long long total_iter_base = 0;
        long long total_iter_staircase = 0;
        long long success_count_base = 0;
        long long success_count_staircase = 0;

#pragma omp parallel
        {
            int thread_id = omp_get_thread_num();
            uint32_t rng_state = base_seed + 0x9E3779B9u * (uint32_t)(thread_id + 1) + (uint32_t)(step * 97);
            long long local_tests = 0;
            long long local_fail_base = 0;
            long long local_fail_staircase = 0;
            long long local_iter_base = 0;
            long long local_iter_staircase = 0;
            long long local_success_base = 0;
            long long local_success_staircase = 0;

            uint8_t noisy_codeword[N];
            uint8_t decoded_base[N];
            uint8_t decoded_staircase[N];
            int8_t llr_base[N];
            int8_t llr_staircase[N];

            while (1) {
                int stop_now = 0;
#pragma omp critical(test_budget)
                {
                    if (total_tests_run + local_tests >= MAX_TESTS ||
                        (total_fail_base + local_fail_base >= TARGET_ERRORS &&
                         total_fail_staircase + local_fail_staircase >= TARGET_ERRORS)) {
                        stop_now = 1;
                    } else {
                        total_tests_run++;
                        local_tests++;
                    }
                }
                if (stop_now) break;

                generate_puf_response_aging(noisy_codeword, codeword, scale_value, noise_rate, N, &rng_state);

                initialize_llr_standard(llr_base, noisy_codeword, N, noise_rate);
                int iter_base = ldpc_decode_nms(llr_base, decoded_base);
                int fail_base = 0;
                for (int i = 0; i < N; i++) {
                    if (decoded_base[i] != codeword[i]) {
                        fail_base = 1;
                        break;
                    }
                }
                if (fail_base) local_fail_base++;
                else {
                    local_success_base++;
                    local_iter_base += iter_base;
                }

                initialize_llr_staircase_quantization(llr_staircase, noisy_codeword, N, scale_value, noise_rate);
                int iter_staircase = ldpc_decode_nms(llr_staircase, decoded_staircase);
                int fail_staircase = 0;
                for (int i = 0; i < N; i++) {
                    if (decoded_staircase[i] != codeword[i]) {
                        fail_staircase = 1;
                        break;
                    }
                }
                if (fail_staircase) local_fail_staircase++;
                else {
                    local_success_staircase++;
                    local_iter_staircase += iter_staircase;
                }
            }

#pragma omp atomic
            total_fail_base += local_fail_base;
#pragma omp atomic
            total_fail_staircase += local_fail_staircase;
#pragma omp atomic
            total_iter_base += local_iter_base;
#pragma omp atomic
            total_iter_staircase += local_iter_staircase;
#pragma omp atomic
            success_count_base += local_success_base;
#pragma omp atomic
            success_count_staircase += local_success_staircase;
        }

        double actual_ber = compute_actual_raw_ber(runtime_error_rates, scale_value, noise_rate);
        double fer_base = (total_tests_run > 0) ? (double)total_fail_base / total_tests_run : 0.0;
        double fer_staircase = (total_tests_run > 0) ? (double)total_fail_staircase / total_tests_run : 0.0;
        double improve = (fer_base > 0.0) ? (fer_base - fer_staircase) / fer_base * 100.0 : 0.0;
        double avg_iter_base = (success_count_base > 0) ? (double)total_iter_base / success_count_base : 0.0;
        double avg_iter_staircase = (success_count_staircase > 0) ? (double)total_iter_staircase / success_count_staircase : 0.0;

        printf("%.3f,%.6f,%.6f,%.6f,%.2f,%.2f,%.2f,%lld,%lld,%lld,%s,%.6f,%.6f\n",
               noise_rate, actual_ber, fer_base, fer_staircase, improve,
               avg_iter_base, avg_iter_staircase, total_tests_run, total_fail_base, total_fail_staircase,
               runtime_label, enroll_mean, runtime_mean);
        fprintf(csv_file, "%.3f,%.6f,%.6f,%.6f,%.2f,%.2f,%.2f,%lld,%lld,%lld,%s,%.6f,%.6f\n",
                noise_rate, actual_ber, fer_base, fer_staircase, improve,
                avg_iter_base, avg_iter_staircase, total_tests_run, total_fail_base, total_fail_staircase,
                runtime_label, enroll_mean, runtime_mean);

        if (fer_base >= 0.99 && fer_staircase >= 0.99 && noise_rate >= 0.12) break;
    }

    fclose(csv_file);
    printf("Saved %s\n", csv_filename);
    return 0;
}
