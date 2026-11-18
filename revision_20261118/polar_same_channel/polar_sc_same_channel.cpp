// Polar-SC baseline for the canonical 4096-bit SRAM-PUF aging profile.
//
// This is a decoder-only reconstruction experiment. It uses the same
// profile-driven channel law as the manuscript artifact, but does not use
// the proposed UEP mapping, mask, or post-aging error labels.
// Encoder and SC traversal semantics were cross-checked against
// py-polar-codes 1.2.2 (MIT): https://github.com/mcba1n/polar-codes

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <random>
#include <sstream>
#include <string>
#include <vector>

namespace {

constexpr int N = 4096;
#ifndef POLAR_K
#define POLAR_K 512
#endif
constexpr int K = POLAR_K;
constexpr int LOG_N = 12;
constexpr double DESIGN_BER = 0.15;

struct Config {
    std::string profile_path =
        "D:/program/paper_artifact_minimal/software/core/puf_profile_long.h";
    std::string output_dir = "D:/program/polar_same_channel/results_100k";
    std::uint64_t seed = 20260916ULL;
    int frames = 1000;
    double fixed_scale = 2.0;
    std::vector<double> noise_floors;
    std::string construction = "profile-enrollment";
    std::string llr_mode = "continuous";
};

struct Counts {
    std::uint64_t raw_errors = 0;
    std::uint64_t message_failures = 0;
    std::uint64_t codeword_failures = 0;
    std::uint64_t total_bits = 0;
};

int bit_reverse(int value) {
    int result = 0;
    for (int bit = 0; bit < LOG_N; ++bit) {
        if (value & (1 << bit)) {
            result |= 1 << (LOG_N - 1 - bit);
        }
    }
    return result;
}

int active_llr_level(int index) {
    int mask = 1 << (LOG_N - 1);
    int count = 1;
    for (int i = 0; i < LOG_N; ++i) {
        if ((mask & index) == 0) {
            ++count;
            mask >>= 1;
        } else {
            break;
        }
    }
    return std::min(count, LOG_N);
}

int active_bit_level(int index) {
    int mask = 1 << (LOG_N - 1);
    int count = 1;
    for (int i = 0; i < LOG_N; ++i) {
        if ((mask & index) != 0) {
            ++count;
            mask >>= 1;
        } else {
            break;
        }
    }
    return std::min(count, LOG_N);
}

// Stable exact f-function for LLR SC decoding.
double upper_llr(double a, double b) {
    const double sign = (a * b < 0.0) ? -1.0 : 1.0;
    const double magnitude = std::min(std::abs(a), std::abs(b));
    const double correction = std::log1p(std::exp(-std::abs(a + b)))
                            - std::log1p(std::exp(-std::abs(a - b)));
    return sign * magnitude + correction;
}

double lower_llr(double bottom, double top, std::uint8_t top_bit) {
    return top_bit == 0 ? bottom + top : bottom - top;
}

std::vector<double> load_profile(const std::string& path) {
    std::ifstream input(path);
    if (!input) {
        throw std::runtime_error("Cannot open profile: " + path);
    }
    std::stringstream buffer;
    buffer << input.rdbuf();
    const std::string source = buffer.str();
    const std::string marker = "REAL_PUF_ERROR_RATES";
    const std::size_t marker_pos = source.find(marker);
    if (marker_pos == std::string::npos) {
        throw std::runtime_error("Profile initializer not found: " + path);
    }
    const std::size_t open = source.find('{', marker_pos);
    const std::size_t close = source.find('}', open);
    if (open == std::string::npos || close == std::string::npos) {
        throw std::runtime_error("Profile initializer bounds not found: " + path);
    }

    std::vector<double> profile;
    const char* cursor = source.c_str() + open + 1;
    const char* end = source.c_str() + close;
    while (cursor < end) {
        char* next = nullptr;
        const double value = std::strtod(cursor, &next);
        if (next != cursor) {
            profile.push_back(value);
            cursor = next;
        } else {
            ++cursor;
        }
    }
    if (profile.size() != N) {
        throw std::runtime_error("Profile must contain exactly 4096 rates; got " +
                                 std::to_string(profile.size()));
    }
    for (double p : profile) {
        if (!(p > 0.0 && p < 0.5)) {
            throw std::runtime_error("Profile probability outside (0, 0.5)");
        }
    }
    return profile;
}

long double log_add(long double a, long double b) {
    const long double high = std::max(a, b);
    const long double low = std::min(a, b);
    return high + std::log1p(std::exp(low - high));
}

long double log_sub(long double a, long double b) {
    if (!(a > b)) {
        throw std::runtime_error("Invalid log-domain Bhattacharyya subtraction");
    }
    return a + std::log1p(-std::exp(b - a));
}

std::vector<int> construct_frozen_from_log_z(std::vector<long double> log_z) {
    // Same Bhattacharyya-bound recursion as py-polar-codes, evaluated in the
    // log domain so long codes do not collapse many channels to exact 0 or 1.
    for (int stage = 0; stage < LOG_N; ++stage) {
        const int half = 1 << stage;
        const int block = 2 * half;
        std::vector<long double> next(N);
        for (int start = 0; start < N; start += block) {
            for (int k = 0; k < half; ++k) {
                const long double top = log_z[start + k];
                const long double bottom = log_z[start + half + k];
                const long double product = top + bottom;
                next[start + k] = log_sub(log_add(top, bottom), product);
                next[start + half + k] = product;
            }
        }
        log_z.swap(next);
    }

    std::vector<int> order(N);
    for (int i = 0; i < N; ++i) order[i] = i;
    std::stable_sort(order.begin(), order.end(), [&](int a, int b) {
        return log_z[a] < log_z[b];
    });

    std::vector<int> frozen(N, 0);
    for (int i = K; i < N; ++i) frozen[order[i]] = 1;
    return frozen;
}

std::vector<int> construct_frozen_bsc(double design_ber) {
    const long double z = 2.0L * std::sqrt(
        static_cast<long double>(design_ber) * (1.0L - design_ber));
    return construct_frozen_from_log_z(std::vector<long double>(N, std::log(z)));
}

std::vector<int> construct_frozen_profile(const std::vector<double>& profile) {
    std::vector<long double> log_z(N);
    for (int i = 0; i < N; ++i) {
        const long double p = profile[i];
        log_z[i] = std::log(2.0L * std::sqrt(p * (1.0L - p)));
    }
    return construct_frozen_from_log_z(std::move(log_z));
}

double staircase_quantize_magnitude(double magnitude) {
    if (magnitude < 0.5) return 2.0;
    if (magnitude < 1.0) return 4.0;
    if (magnitude < 1.5) return 6.0;
    if (magnitude < 2.0) return 9.0;
    if (magnitude < 2.8) return 14.0;
    if (magnitude < 3.5) return 20.0;
    if (magnitude < 4.5) return 28.0;
    return 35.0;
}

void encode(std::vector<std::uint8_t>& u) {
    for (int block = N; block > 1; block >>= 1) {
        const int half = block >> 1;
        for (int start = 0; start < N; start += block) {
            for (int k = 0; k < half; ++k) {
                u[start + k] ^= u[start + half + k];
            }
        }
    }
}

class ScDecoder {
public:
    explicit ScDecoder(const std::vector<int>& frozen)
        : frozen_(frozen), llr_(N * (LOG_N + 1), 0.0),
          bits_(N * (LOG_N + 1), 0) {}

    std::vector<std::uint8_t> decode(const std::vector<double>& channel_llr) {
        std::fill(llr_.begin(), llr_.end(), 0.0);
        std::fill(bits_.begin(), bits_.end(), 0);
        for (int i = 0; i < N; ++i) at_llr(i, 0) = channel_llr[i];

        for (int i = 0; i < N; ++i) {
            const int l = bit_reverse(i);
            update_llrs(l);
            at_bits(l, LOG_N) = frozen_[l] ? 0 : (at_llr(l, LOG_N) >= 0.0 ? 0 : 1);
            update_bits(l);
        }

        std::vector<std::uint8_t> message;
        message.reserve(K);
        for (int i = 0; i < N; ++i) {
            if (!frozen_[i]) message.push_back(at_bits(i, LOG_N));
        }
        return message;
    }

private:
    double& at_llr(int row, int stage) { return llr_[row * (LOG_N + 1) + stage]; }
    std::uint8_t& at_bits(int row, int stage) { return bits_[row * (LOG_N + 1) + stage]; }

    void update_llrs(int l) {
        for (int stage = LOG_N - active_llr_level(l); stage < LOG_N; ++stage) {
            const int block = 1 << (stage + 1);
            const int branch = block >> 1;
            for (int j = l; j < N; j += block) {
                if (j % block < branch) {
                    at_llr(j, stage + 1) = upper_llr(at_llr(j, stage),
                                                     at_llr(j + branch, stage));
                } else {
                    const double bottom = at_llr(j, stage);
                    const double top = at_llr(j - branch, stage);
                    at_llr(j, stage + 1) = lower_llr(bottom, top,
                                                     at_bits(j - branch, stage + 1));
                }
            }
        }
    }

    void update_bits(int l) {
        if (l < N / 2) return;
        for (int stage = LOG_N;
             stage > LOG_N - active_bit_level(l); --stage) {
            const int block = 1 << stage;
            const int branch = block >> 1;
            for (int j = l; j >= 0; j -= block) {
                if (j % block >= branch) {
                    at_bits(j - branch, stage - 1) =
                        at_bits(j, stage) ^ at_bits(j - branch, stage);
                    at_bits(j, stage - 1) = at_bits(j, stage);
                }
            }
        }
    }

    const std::vector<int>& frozen_;
    std::vector<double> llr_;
    std::vector<std::uint8_t> bits_;
};

double expected_ber(const std::vector<double>& profile,
                   double scale, double noise_floor) {
    double total = 0.0;
    for (double p : profile) {
        total += std::min(scale * p + noise_floor, 0.5);
    }
    return total / static_cast<double>(profile.size());
}

void ensure_directory(const std::string& path) {
    std::string command = "if not exist \"" + path + "\" mkdir \"" + path + "\"";
    const int status = std::system(command.c_str());
    if (status != 0) throw std::runtime_error("Cannot create output directory: " + path);
}

void parse_args(int argc, char** argv, Config& config) {
    for (int i = 1; i < argc; ++i) {
        const std::string arg(argv[i]);
        auto value = [&](const std::string& prefix) -> std::string {
            if (arg.rfind(prefix, 0) != 0) return "";
            return arg.substr(prefix.size());
        };
        if (arg == "--help") {
            std::cout << "Options: --frames=N --seed=N --profile=PATH --output=DIR "
                         "--fixed-scale=S --noise-floors=0.001,0.002,... "
                         "--construction=profile-enrollment|homogeneous-bsc "
                         "--llr-mode=continuous|staircase-enrollment\n";
            std::exit(0);
        } else if (!value("--frames=").empty()) {
            config.frames = std::stoi(value("--frames="));
        } else if (!value("--seed=").empty()) {
            config.seed = std::stoull(value("--seed="));
        } else if (!value("--profile=").empty()) {
            config.profile_path = value("--profile=");
        } else if (!value("--output=").empty()) {
            config.output_dir = value("--output=");
        } else if (!value("--fixed-scale=").empty()) {
            config.fixed_scale = std::stod(value("--fixed-scale="));
        } else if (!value("--noise-floors=").empty()) {
            config.noise_floors.clear();
            std::stringstream stream(value("--noise-floors="));
            std::string item;
            while (std::getline(stream, item, ',')) config.noise_floors.push_back(std::stod(item));
        } else if (!value("--construction=").empty()) {
            config.construction = value("--construction=");
        } else if (!value("--llr-mode=").empty()) {
            config.llr_mode = value("--llr-mode=");
        } else {
            throw std::runtime_error("Unknown argument: " + arg);
        }
    }
    if (config.frames < 1 || config.fixed_scale < 0.0 || config.noise_floors.empty()) {
        throw std::runtime_error("Invalid frames, fixed scale, or noise-floor list");
    }
    for (double floor : config.noise_floors) {
        if (floor < 0.0 || floor >= 0.5) {
            throw std::runtime_error("Fixed-scale noise floors must be in [0, 0.5)");
        }
    }
    if (config.construction != "profile-enrollment" &&
        config.construction != "homogeneous-bsc") {
        throw std::runtime_error(
            "Construction must be profile-enrollment or homogeneous-bsc");
    }
    if (config.llr_mode != "continuous" &&
        config.llr_mode != "staircase-enrollment") {
        throw std::runtime_error(
            "LLR mode must be continuous or staircase-enrollment");
    }
}

void write_metadata(const Config& config, const std::vector<double>& profile,
                    const std::vector<int>& frozen, double profile_mean) {
    std::ofstream out(config.output_dir + "/provenance.json");
    out << "{\n"
        << "  \"algorithm\": \"Polar-SC\",\n"
        << "  \"N\": " << N << ",\n"
        << "  \"K\": " << K << ",\n"
        << "  \"rate\": " << static_cast<double>(K) / N << ",\n"
        << "  \"reference_configuration\": \"4096-bit same-channel Polar-SC rate sweep\",\n"
        << "  \"construction_mode\": \"" << config.construction << "\",\n"
        << "  \"design_channel_ber\": ";
    if (config.construction == "homogeneous-bsc") out << DESIGN_BER;
    else out << "null";
    out << ",\n"
        << "  \"construction_information\": \""
        << (config.construction == "profile-enrollment"
                ? "enrollment profile only; no aged probabilities"
                : "homogeneous BSC design BER only")
        << "\",\n"
        << "  \"sc_reference\": \"py-polar-codes 1.2.2 Encode/SCD semantics (MIT)\",\n"
        << "  \"profile\": \"" << config.profile_path << "\",\n"
        << "  \"profile_mean\": " << std::setprecision(17) << profile_mean << ",\n"
        << "  \"profile_p_0.15_count\": "
        << std::count_if(profile.begin(), profile.end(), [](double p) { return p == 0.15; }) << ",\n"
        << "  \"profile_p_0.01_count\": "
        << std::count_if(profile.begin(), profile.end(), [](double p) { return p == 0.01; }) << ",\n"
        << "  \"frozen_count\": "
        << std::count(frozen.begin(), frozen.end(), 1) << ",\n"
        << "  \"sweep_mode\": \"fixed_scale_noise_floor\",\n"
        << "  \"fixed_scale\": " << config.fixed_scale << ",\n"
        << "  \"noise_floor\": null,\n"
        << "  \"noise_floors\": [";
    for (std::size_t i = 0; i < config.noise_floors.size(); ++i) {
        if (i != 0) out << ", ";
        out << config.noise_floors[i];
    }
    out << "],\n"
        << "  \"frames_per_point\": " << config.frames << ",\n"
        << "  \"seed\": " << config.seed << ",\n"
        << "  \"llr_mode\": \"" << config.llr_mode << "\",\n"
        << "  \"llr_source\": \"enrollment p_i; no post-aging labels or hotspot mask\",\n"
        << "  \"llr_quantizer\": "
        << (config.llr_mode == "staircase-enrollment"
                ? "{\"thresholds\":[0,0.5,1.0,1.5,2.0,2.8,3.5,4.5],\"magnitudes\":[2,4,6,9,14,20,28,35]}"
                : "null")
        << ",\n"
        << "  \"channel_law\": \"p_i_aged=min(scale*p_i+noise_floor,0.5)\",\n"
        << "  \"fer_definition\": \"decoded K-bit message differs from transmitted message\",\n"
        << "  \"comparison_boundary\": \"same canonical profile and channel law; no hash/KDF; decoder-only FER\"\n"
        << "}\n";
}

}  // namespace

int main(int argc, char** argv) {
    try {
        Config config;
        parse_args(argc, argv, config);
        ensure_directory(config.output_dir);
        const std::vector<double> profile = load_profile(config.profile_path);
        const std::vector<int> frozen =
            config.construction == "profile-enrollment"
                ? construct_frozen_profile(profile)
                : construct_frozen_bsc(DESIGN_BER);
        const double profile_mean = expected_ber(profile, 1.0, 0.0);
        write_metadata(config, profile, frozen, profile_mean);

        // Deterministic no-noise self-test for the encoder/decoder pair.
        {
            std::mt19937_64 self_rng(7);
            ScDecoder decoder(frozen);
            for (int trial = 0; trial < 10; ++trial) {
                std::vector<std::uint8_t> message(K);
                for (auto& bit : message) bit = static_cast<std::uint8_t>(self_rng() & 1ULL);
                std::vector<std::uint8_t> u(N, 0);
                int offset = 0;
                for (int i = 0; i < N; ++i) {
                    if (!frozen[i]) u[i] = message[offset++];
                }
                encode(u);
                std::vector<double> llr(N);
                for (int i = 0; i < N; ++i) llr[i] = u[i] ? -50.0 : 50.0;
                if (decoder.decode(llr) != message) {
                    const std::vector<std::uint8_t> decoded = decoder.decode(llr);
                    std::ostringstream detail;
                    detail << "Polar-SC no-noise self-test failed at trial " << trial
                           << "; decoded[0..7]=";
                    for (int i = 0; i < 8; ++i) detail << int(decoded[i]) << (i == 7 ? "" : ",");
                    detail << " message[0..7]=";
                    for (int i = 0; i < 8; ++i) detail << int(message[i]) << (i == 7 ? "" : ",");
                    throw std::runtime_error(detail.str());
                }
            }
        }
        std::cout << "Self-test passed: Polar encoder/SC decoder, N="
                  << N << " K=" << K << " rate="
                  << static_cast<double>(K) / N << "\n";

        std::ofstream csv(config.output_dir + "/fer_summary.csv");
        if (!csv) throw std::runtime_error("Cannot open CSV output");
        csv << "target_raw_ber,scale,expected_raw_ber,actual_raw_ber,frames,message_failures,";
        csv << "message_fer,codeword_failures,codeword_fer,noise_floor\n";

        std::mt19937_64 rng(config.seed);
        ScDecoder decoder(frozen);
        std::vector<std::uint8_t> message(K), u(N), received(N);
        std::vector<double> llr(N);
        struct SweepPoint {
            double target;
            double scale;
            double noise_floor;
        };
        std::vector<SweepPoint> sweep_points;
        for (double floor : config.noise_floors) {
            sweep_points.push_back({
                expected_ber(profile, config.fixed_scale, floor),
                config.fixed_scale,
                floor
            });
        }

        for (const SweepPoint& point : sweep_points) {
            const double target = point.target;
            const double scale = point.scale;
            const double point_noise_floor = point.noise_floor;
            const double expected = expected_ber(profile, scale, point_noise_floor);
            Counts counts;
            double expected_sum = 0.0;

            for (int frame = 0; frame < config.frames; ++frame) {
                std::fill(u.begin(), u.end(), 0);
                int offset = 0;
                for (int i = 0; i < N; ++i) {
                    if (!frozen[i]) {
                        message[offset] = static_cast<std::uint8_t>(rng() & 1ULL);
                        u[i] = message[offset++];
                    }
                }
                encode(u);

                std::uint64_t frame_raw_errors = 0;
                double frame_expected = 0.0;
                for (int i = 0; i < N; ++i) {
                    const double p_aged = std::min(scale * profile[i] + point_noise_floor, 0.5);
                    frame_expected += p_aged;
                    const bool flipped = std::generate_canonical<double, 53>(rng) < p_aged;
                    received[i] = static_cast<std::uint8_t>(u[i] ^ (flipped ? 1 : 0));
                    frame_raw_errors += flipped ? 1ULL : 0ULL;
                    const double p_enroll = profile[i];
                    double magnitude = std::log((1.0 - p_enroll) / p_enroll);
                    if (config.llr_mode == "staircase-enrollment") {
                        magnitude = staircase_quantize_magnitude(magnitude);
                    }
                    llr[i] = received[i] ? -magnitude : magnitude;
                }
                expected_sum += frame_expected / static_cast<double>(N);
                counts.raw_errors += frame_raw_errors;
                counts.total_bits += N;

                const std::vector<std::uint8_t> decoded = decoder.decode(llr);
                bool message_failure = false;
                for (int i = 0; i < K; ++i) {
                    if (decoded[i] != message[i]) {
                        message_failure = true;
                        break;
                    }
                }
                if (message_failure) ++counts.message_failures;

                std::vector<std::uint8_t> reconstructed(N, 0);
                offset = 0;
                for (int i = 0; i < N; ++i) {
                    if (!frozen[i]) reconstructed[i] = decoded[offset++];
                }
                encode(reconstructed);
                bool codeword_failure = reconstructed != u;
                if (codeword_failure) ++counts.codeword_failures;
            }

            const double actual = static_cast<double>(counts.raw_errors) /
                                  static_cast<double>(counts.total_bits);
            csv << std::fixed << std::setprecision(10)
                << target << "," << scale << "," << expected << "," << actual << ","
                << config.frames << "," << counts.message_failures << ","
                << static_cast<double>(counts.message_failures) / config.frames << ","
                << counts.codeword_failures << ","
                << static_cast<double>(counts.codeword_failures) / config.frames << ","
                << point_noise_floor << "\n";
            csv.flush();
            std::cout << "target=" << std::fixed << std::setprecision(2) << target
                      << " actual=" << std::setprecision(6) << actual
                      << " scale=" << scale
                      << " noise_floor=" << point_noise_floor
                      << " message_failures=" << counts.message_failures
                      << "/" << config.frames << "\n";
        }
        std::cout << "Results: " << config.output_dir << "/fer_summary.csv\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "ERROR: " << error.what() << "\n";
        return 1;
    }
}
