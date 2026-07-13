#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <time.h>
#include <errno.h>

#ifdef _WIN32
    #include <direct.h>
#else
    #include <sys/stat.h>
#endif

#define _USE_MATH_DEFINES
#define PI 3.14159265358979323846

#include "ldpc_config.h"
#include "ldpc.h"

static uint8_t paper_hotspot_mask[N];
static int paper_hotspot_mask_ready = 0;

static int target_hotspot_count(void) {
    return EXPANSION_FACTOR_Z;
}

static void ensure_directory_exists(const char *dir_path) {
#ifdef _WIN32
    _mkdir(dir_path);
#else
    mkdir(dir_path, 0755);
#endif
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

static void compute_psd(const double* signal, int n, double* psd) {
    for (int k = 0; k < n; k++) {
        double sum_real = 0.0;
        double sum_imag = 0.0;
        for (int t = 0; t < n; t++) {
            double angle = 2.0 * PI * k * t / n;
            sum_real += signal[t] * cos(angle);
            sum_imag -= signal[t] * sin(angle);
        }
        psd[k] = (sum_real * sum_real + sum_imag * sum_imag) / n;
    }
}

static void compute_autocorrelation(const double* signal, int n, double* autocorr) {
    for (int lag = 0; lag < n; lag++) {
        double sum = 0.0;
        int count = 0;
        for (int i = 0; i < n - lag; i++) {
            sum += signal[i] * signal[i + lag];
            count++;
        }
        autocorr[lag] = (count > 0) ? sum / count : 0.0;
    }
}

static void save_signal_data(const double* signal, int n, const char* filename, const char* header) {
    FILE* fp = fopen(filename, "w");
    if (!fp) {
        printf("Cannot open file: %s\n", filename);
        return;
    }
    fprintf(fp, "%s\n", header);
    for (int i = 0; i < n; i++) {
        fprintf(fp, "%d,%.10f\n", i, signal[i]);
    }
    fclose(fp);
}

static void save_error_probability_vector(const double* error_vec, int n, const char* filename) {
    FILE* fp = fopen(filename, "w");
    if (!fp) {
        printf("Cannot open file: %s\n", filename);
        return;
    }
    for (int i = 0; i < n; i++) {
        fprintf(fp, "%.10f", error_vec[i]);
        if (i < n - 1) fprintf(fp, ",");
    }
    fclose(fp);
}

static int check_if_strong_column(int bit_index) {
    for (int j = 0; j < NUM_STRONG_ANCHORS; j++) {
        int start = STRONG_ANCHOR_COLS[j];
        int end = start + EXPANSION_FACTOR_Z - 1;
        if (bit_index >= start && bit_index <= end) return 1;
    }
    return 0;
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

static void print_mapping_sanity(void) {
    build_paper_hotspot_mask(N);
    uint16_t col_degrees[N];
    build_column_degrees(col_degrees);

    int selected = 0;
    int selected_hot = 0;
    int selected_strong = 0;
    int selected_deg12 = 0;
    int hot_total = 0;
    int min_degree = 1000000;
    int max_degree = 0;
    long long degree_sum = 0;

    for (int i = 0; i < N; i++) {
        double p = REAL_PUF_ERROR_RATES[i % PUF_N];
        if (p >= 0.10) hot_total++;
        if (paper_hotspot_mask[i]) {
            int degree = col_degrees[i];
            selected++;
            if (p >= 0.10) selected_hot++;
            if (check_if_strong_column(i)) selected_strong++;
            if (degree >= 12) selected_deg12++;
            if (degree < min_degree) min_degree = degree;
            if (degree > max_degree) max_degree = degree;
            degree_sum += degree;
        }
    }

    if (selected == 0) min_degree = 0;
    printf("=== Current PSD mapping sanity ===\n");
    printf("N=%d, K=%d, M=%d, Z=%d, A=%d, anchors=%d\n",
           N, K, M, EXPANSION_FACTOR_Z, target_hotspot_count(), NUM_STRONG_ANCHORS);
    printf("Selected top-A=%d, selected profile-hot=%d, profile-hot-total=%d\n",
           selected, selected_hot, hot_total);
    printf("Selected in declared strong anchors=%d/%d, degree>=12=%d/%d, degree min/avg/max=%d/%.2f/%d\n",
           selected_strong, selected, selected_deg12, selected,
           min_degree, selected ? (double)degree_sum / selected : 0.0, max_degree);
    printf("==================================\n");
}

static void initialize_llr_staircase_quantization(int8_t* llr_out,
                                                  const uint8_t* logical_data,
                                                  int length,
                                                  double scale,
                                                  double min_noise_floor) {
    build_paper_hotspot_mask(length);

    for (int i = 0; i < length; i++) {
        int p_idx = i % PUF_N;
        double p_puf = REAL_PUF_ERROR_RATES[p_idx];

        if (paper_hotspot_mask[i]) {
            llr_out[i] = 0;
            continue;
        }

        double p_total = p_puf * scale + min_noise_floor;
        if (p_total < 0.001) p_total = 0.001;
        if (p_total > 0.49) p_total = 0.49;

        double raw_abs_llr = log((1.0 - p_total) / p_total);
        int8_t magnitude;
        if (raw_abs_llr < 0.5) {
            magnitude = 2;
        } else if (raw_abs_llr < 1.0) {
            magnitude = 4;
        } else if (raw_abs_llr < 1.5) {
            magnitude = 6;
        } else if (raw_abs_llr < 2.0) {
            magnitude = 9;
        } else if (raw_abs_llr < 2.8) {
            magnitude = 14;
        } else if (raw_abs_llr < 3.5) {
            magnitude = 20;
        } else if (raw_abs_llr < 4.5) {
            magnitude = 28;
        } else {
            magnitude = 35;
        }

        llr_out[i] = (logical_data[i] == 0) ? magnitude : -magnitude;
    }
}

static void initialize_llr_standard_fixed(int8_t* llr_out, const uint8_t* data,
                                          int length, double fixed_p) {
    if (fixed_p < 0.01) fixed_p = 0.01;
    if (fixed_p > 0.49) fixed_p = 0.49;
    double magnitude = log((1.0 - fixed_p) / fixed_p) * 0.8;
    if (magnitude > 127.0) magnitude = 127.0;
    int8_t val = (int8_t)magnitude;
    for (int i = 0; i < length; i++) {
        llr_out[i] = (data[i] == 0) ? val : -val;
    }
}

static void initialize_llr_standard_masked(int8_t* llr_out, const uint8_t* data,
                                           int length, double fixed_p) {
    build_paper_hotspot_mask(length);

    if (fixed_p < 0.01) fixed_p = 0.01;
    if (fixed_p > 0.49) fixed_p = 0.49;
    double magnitude = log((1.0 - fixed_p) / fixed_p) * 0.8;
    if (magnitude > 127.0) magnitude = 127.0;
    int8_t val = (int8_t)magnitude;

    for (int i = 0; i < length; i++) {
        if (paper_hotspot_mask[i]) {
            llr_out[i] = 0;
            continue;
        }
        llr_out[i] = (data[i] == 0) ? val : -val;
    }
}

static void generate_puf_response(uint8_t* response, const uint8_t* golden,
                                  double env_factor, double global_noise_floor,
                                  int length) {
    for (int i = 0; i < length; i++) {
        int idx = i % PUF_N;
        double p_total = REAL_PUF_ERROR_RATES[idx] * env_factor + global_noise_floor;
        if (p_total > 0.5) p_total = 0.5;
        response[i] = (((double)rand() / RAND_MAX) < p_total) ? (golden[i] ^ 1) : golden[i];
    }
}

int main(int argc, char *argv[]) {
    double scale_value = 2.0;
    double target_noise_rate = 0.045;
    int max_tests = 1000;
    int seed_val = (int)time(NULL);

    if (argc > 1) scale_value = atof(argv[1]);
    if (argc > 2) target_noise_rate = atof(argv[2]);
    if (argc > 3) max_tests = atoi(argv[3]);
    if (argc > 4) seed_val = atoi(argv[4]);
    srand(seed_val);

    print_mapping_sanity();
    printf("Scale=%.3f, noise=%.3f, frames=%d, seed=%d\n",
           scale_value, target_noise_rate, max_tests, seed_val);

    char output_root[160] = "psd_current_long";
    if (argc > 5) {
        snprintf(output_root, sizeof(output_root), "%s", argv[5]);
    }
    char output_dir[160];
    sprintf(output_dir, "%s/psd_results_scale_%.3f_noise_%.3f",
            output_root, scale_value, target_noise_rate);
    ensure_directory_exists(output_root);
    ensure_directory_exists(output_dir);

    char csv_filename[220];
    sprintf(csv_filename, "%s/fer_comparison_length_%s.csv", output_dir, LENGTH_SUFFIX);
    FILE *csv_file = fopen(csv_filename, "w");
    if (!csv_file) {
        perror("Error opening CSV file");
        return 1;
    }
    fprintf(csv_file, "Test_ID,Actual_BER,Baseline_FER,Masked_Baseline_FER,Optimized_FER,Improvement,Avg_Iter_Baseline,Avg_Iter_Masked_Baseline,Avg_Iter_Optimized\n");

    double* raw_error = (double*)calloc(N, sizeof(double));
    double* baseline_error = (double*)calloc(N, sizeof(double));
    double* masked_baseline_error = (double*)calloc(N, sizeof(double));
    double* optimized_error = (double*)calloc(N, sizeof(double));
    if (!raw_error || !baseline_error || !masked_baseline_error || !optimized_error) {
        printf("Allocation failed\n");
        return 1;
    }

    long long total_fail_base = 0;
    long long total_fail_masked = 0;
    long long total_fail_opt = 0;
    long long total_bit_errors = 0;
    long long total_iter_base = 0;
    long long total_iter_masked = 0;
    long long total_iter_opt = 0;
    long long success_count_base = 0;
    long long success_count_masked = 0;
    long long success_count_opt = 0;
    int valid_samples = 0;

    for (int test_id = 0; test_id < max_tests; test_id++) {
        uint8_t message[K];
        uint8_t codeword[N];
        uint8_t noisy_codeword[N];
        uint8_t decoded_baseline[N];
        uint8_t decoded_masked[N];
        uint8_t decoded_optimized[N];
        int8_t llr_baseline[N];
        int8_t llr_masked[N];
        int8_t llr_optimized[N];

        memset(message, 0, sizeof(message));
        ldpc_encode(message, codeword);

        int syndrome_failed = 0;
        for (int i = 0; i < M; i++) {
            int parity = 0;
            for (int k = 0; k < H_row_degrees[i]; k++) {
                parity ^= codeword[H_row_indices[i][k]];
            }
            if (parity != 0) {
                syndrome_failed = 1;
                break;
            }
        }
        if (syndrome_failed) continue;

        generate_puf_response(noisy_codeword, codeword, scale_value, target_noise_rate, N);

        int bit_errors = 0;
        for (int i = 0; i < N; i++) {
            if (noisy_codeword[i] != codeword[i]) {
                raw_error[i] += 1.0;
                bit_errors++;
            }
        }

        initialize_llr_standard_fixed(llr_baseline, noisy_codeword, N, target_noise_rate + 0.03);
        int iter_base = ldpc_decode_nms(llr_baseline, decoded_baseline);
        int fail_base = (iter_base == 0);
        if (!fail_base) {
            success_count_base++;
            total_iter_base += iter_base;
            for (int i = 0; i < K; i++) {
                if (decoded_baseline[i] != codeword[i]) {
                    fail_base = 1;
                    break;
                }
            }
        }
        total_fail_base += fail_base;
        for (int i = 0; i < N; i++) {
            if (decoded_baseline[i] != codeword[i]) baseline_error[i] += 1.0;
        }

        initialize_llr_standard_masked(llr_masked, noisy_codeword, N, target_noise_rate + 0.03);
        int iter_masked = ldpc_decode_nms(llr_masked, decoded_masked);
        int fail_masked = (iter_masked == 0);
        if (!fail_masked) {
            success_count_masked++;
            total_iter_masked += iter_masked;
            for (int i = 0; i < K; i++) {
                if (decoded_masked[i] != codeword[i]) {
                    fail_masked = 1;
                    break;
                }
            }
        }
        total_fail_masked += fail_masked;
        for (int i = 0; i < N; i++) {
            if (decoded_masked[i] != codeword[i]) masked_baseline_error[i] += 1.0;
        }

        initialize_llr_staircase_quantization(llr_optimized, noisy_codeword,
                                              N, scale_value, target_noise_rate);
        int iter_opt = ldpc_decode_nms(llr_optimized, decoded_optimized);
        int fail_opt = (iter_opt == 0);
        if (!fail_opt) {
            success_count_opt++;
            total_iter_opt += iter_opt;
            for (int i = 0; i < K; i++) {
                if (decoded_optimized[i] != codeword[i]) {
                    fail_opt = 1;
                    break;
                }
            }
        }
        total_fail_opt += fail_opt;
        for (int i = 0; i < N; i++) {
            if (decoded_optimized[i] != codeword[i]) optimized_error[i] += 1.0;
        }

        total_bit_errors += bit_errors;
        valid_samples++;

        if ((test_id + 1) % 200 == 0) {
            printf("  frame %d/%d, actual_ber=%.5f\n",
                   test_id + 1, max_tests,
                   (double)total_bit_errors / ((long long)valid_samples * N));
            fflush(stdout);
        }
    }

    if (valid_samples == 0) {
        printf("No valid samples\n");
        return 1;
    }

    for (int i = 0; i < N; i++) {
        raw_error[i] /= valid_samples;
        baseline_error[i] /= valid_samples;
        masked_baseline_error[i] /= valid_samples;
        optimized_error[i] /= valid_samples;
    }

    double actual_ber = (double)total_bit_errors / ((long long)valid_samples * N);
    double fer_base = (double)total_fail_base / valid_samples;
    double fer_masked = (double)total_fail_masked / valid_samples;
    double fer_opt = (double)total_fail_opt / valid_samples;
    double improvement = (fer_base > 0.0) ? (fer_base - fer_opt) / fer_base * 100.0 : 0.0;
    double avg_iter_base = success_count_base ? (double)total_iter_base / success_count_base : 0.0;
    double avg_iter_masked = success_count_masked ? (double)total_iter_masked / success_count_masked : 0.0;
    double avg_iter_opt = success_count_opt ? (double)total_iter_opt / success_count_opt : 0.0;

    fprintf(csv_file, "%d,%.5f,%.6f,%.6f,%.6f,%.1f,%.2f,%.2f,%.2f\n",
            valid_samples, actual_ber, fer_base, fer_masked, fer_opt, improvement,
            avg_iter_base, avg_iter_masked, avg_iter_opt);
    fclose(csv_file);

    printf("Final: ber=%.5f, baseline_fer=%.6f, optimized_fer=%.6f, avg_iter=%.2f/%.2f\n",
           actual_ber, fer_base, fer_opt, avg_iter_base, avg_iter_opt);
    printf("Masked continuous control: fer=%.6f, avg_iter=%.2f\n",
           fer_masked, avg_iter_masked);

    double* psd_raw = (double*)malloc(N * sizeof(double));
    double* psd_baseline = (double*)malloc(N * sizeof(double));
    double* psd_masked_baseline = (double*)malloc(N * sizeof(double));
    double* psd_optimized = (double*)malloc(N * sizeof(double));
    double* autocorr_raw = (double*)malloc(N * sizeof(double));
    double* autocorr_baseline = (double*)malloc(N * sizeof(double));
    double* autocorr_masked_baseline = (double*)malloc(N * sizeof(double));
    double* autocorr_optimized = (double*)malloc(N * sizeof(double));

    compute_psd(raw_error, N, psd_raw);
    compute_psd(baseline_error, N, psd_baseline);
    compute_psd(masked_baseline_error, N, psd_masked_baseline);
    compute_psd(optimized_error, N, psd_optimized);
    compute_autocorrelation(raw_error, N, autocorr_raw);
    compute_autocorrelation(baseline_error, N, autocorr_baseline);
    compute_autocorrelation(masked_baseline_error, N, autocorr_masked_baseline);
    compute_autocorrelation(optimized_error, N, autocorr_optimized);

    char filename[220];
    sprintf(filename, "%s/raw_error_vector.csv", output_dir);
    save_error_probability_vector(raw_error, N, filename);
    sprintf(filename, "%s/baseline_error_vector.csv", output_dir);
    save_error_probability_vector(baseline_error, N, filename);
    sprintf(filename, "%s/masked_baseline_error_vector.csv", output_dir);
    save_error_probability_vector(masked_baseline_error, N, filename);
    sprintf(filename, "%s/optimized_error_vector.csv", output_dir);
    save_error_probability_vector(optimized_error, N, filename);

    sprintf(filename, "%s/psd_raw.csv", output_dir);
    save_signal_data(psd_raw, N, filename, "Frequency_Index,PSD_Value");
    sprintf(filename, "%s/psd_baseline.csv", output_dir);
    save_signal_data(psd_baseline, N, filename, "Frequency_Index,PSD_Value");
    sprintf(filename, "%s/psd_masked_baseline.csv", output_dir);
    save_signal_data(psd_masked_baseline, N, filename, "Frequency_Index,PSD_Value");
    sprintf(filename, "%s/psd_optimized.csv", output_dir);
    save_signal_data(psd_optimized, N, filename, "Frequency_Index,PSD_Value");
    sprintf(filename, "%s/autocorr_raw.csv", output_dir);
    save_signal_data(autocorr_raw, N, filename, "Lag,Autocorrelation");
    sprintf(filename, "%s/autocorr_baseline.csv", output_dir);
    save_signal_data(autocorr_baseline, N, filename, "Lag,Autocorrelation");
    sprintf(filename, "%s/autocorr_masked_baseline.csv", output_dir);
    save_signal_data(autocorr_masked_baseline, N, filename, "Lag,Autocorrelation");
    sprintf(filename, "%s/autocorr_optimized.csv", output_dir);
    save_signal_data(autocorr_optimized, N, filename, "Lag,Autocorrelation");

    free(raw_error);
    free(baseline_error);
    free(masked_baseline_error);
    free(optimized_error);
    free(psd_raw);
    free(psd_baseline);
    free(psd_masked_baseline);
    free(psd_optimized);
    free(autocorr_raw);
    free(autocorr_baseline);
    free(autocorr_masked_baseline);
    free(autocorr_optimized);

    printf("Saved PSD/ACF results to %s\n", output_dir);
    return 0;
}
