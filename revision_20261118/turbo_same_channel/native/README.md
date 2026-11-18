# Native Turbo adapter

This isolated adapter compiles the original srsLTE release_17_12 scalar encoder,
float Max-Log-MAP decoder, LTE QPP generator, and scalar rate matcher unchanged.
The exact upstream commit is `8f9ce13b1cb1892ba971dba66f49f6e4e579ecaa`.
The original sources, copyright notice, and AGPL-3.0-or-later license are in
`../vendor/srslte_17_12/`. Local adapter files use the same license.

`decoder_bridge.c` includes the unmodified decoder source so a validation API can
call its otherwise static constituent MAP routine. It does not substitute a
different decoder. `shim_support.c` supplies scalar memory, packed-bit, LTE size
table, and interleaver allocation helpers in place of the complete radio stack.

Run `native/build_native.ps1` to build `turbo_native.dll` and run the native
self-test. The build uses GCC 15.2 with `-O3 -fno-fast-math`; no SIMD or integer
LLR quantization is enabled. The DLL needs only Windows system runtime libraries.

The public C ABI is in `turbo_native.h`. Information and encoded bits use one
`uint8_t` per bit. LLRs and component posteriors use `float` and `log(P0/P1)`.
The adapter negates LLRs at the upstream decoder boundary. Information length is
2048, terminated mother-code length 6156, and RV0 transmission length 4096.
There is no CRC or LTE transport-block wrapper. Eight iterations mean sixteen
constituent decodes; all requested iterations run, with no early termination.

`turbo_rate_indices` obtains each transmitted mother-code index by passing 13
binary index planes through the original rate matcher. `turbo_rate_encode` and
`turbo_rate_recover` expose the original scalar matching/recovery for audits.
Rate recovery rejects a received LLR exactly equal to the upstream sentinel
10000. Ordinary experiment LLRs are far below this sentinel.

One context must not be shared concurrently among decoder calls. Distinct
contexts own independent decoder state, and encoder table initialization uses
Windows `InitOnceExecuteOnce`. The scalar encoder's shared tables last for the
DLL lifetime. `turbo_free` therefore releases decoder/context storage without
calling upstream's process-global encoder table cleanup.

Native self-tests exhaustively enumerate all 64 terminated paths for 20 random
six-bit constituent channels, check 4096 unique RV0 indices and their type
counts, compare original RM/recovery with indexed extraction, and decode 48
zero/one/random noiseless mother and punctured codewords across two lifetimes.
