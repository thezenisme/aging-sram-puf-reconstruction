N = 4096
Z = 128

P_TOP_HOT = 0.15
P_SECONDARY_HOT = 0.12
P_NORMAL = 0.01

rates = [P_NORMAL] * N

# Top-A cells after enrollment mapping: these are assigned to the single
# high-degree QC block and will be soft-erased by the decoder.
for i in range(Z):
    rates[i] = P_TOP_HOT

# Additional profiled hotspots remain in the physical profile but are below
# the top-A threshold.  This keeps the channel non-uniform without assigning
# every hotspot to the UEP budget.
for i in range(Z, N):
    if (i % 16) < 3:
        rates[i] = P_SECONDARY_HOT

with open("puf_profile_long.h", "w", encoding="ascii") as f:
    f.write("// Mapped multi-hotspot long profile.\n")
    f.write("// Top A=Z=128 cells are mapped to strong block [0..127] with p=0.15.\n")
    f.write("// Secondary hotspots use p=0.12 and are not selected by top-A masking.\n")
    f.write("#ifndef PUF_PROFILE_LONG_H\n")
    f.write("#define PUF_PROFILE_LONG_H\n")
    f.write("#define PUF_N_LONG 4096\n")
    f.write("static const double REAL_PUF_ERROR_RATES[4096] = {\n")
    for start in range(0, N, 8):
        values = ", ".join(f"{v:.4f}" for v in rates[start:start + 8])
        suffix = "," if start + 8 < N else ""
        f.write(f"    {values}{suffix}\n")
    f.write("};\n")
    f.write("#endif // PUF_PROFILE_LONG_H\n")
