# Additional artifacts supplied for the reviewer revision

Start with [REVIEWER_GUIDE.md](REVIEWER_GUIDE.md), which links each reviewer
request to the exact code, frozen results, configuration and reproduction entry.
This addition covers three same-channel software baselines, the current five-bit
Proposed RTL, the three-length hardware study, and local Polar/Turbo hardware.
It does not include the revised leakage diagnostic. Earlier repository artifacts
are retained independently; the old scaling core is not the current decoder.

Software correctness tests and short smoke runs are distinct from full FER
reproduction. No full Monte Carlo sweep is launched by the package verification.
Third-party sources retain their accompanying licenses and provenance.
SOURCE_MANIFEST.json records original and packaged hashes; the only source edits
are path/build portability changes, not channel or decoder algorithm changes.
SHA256SUMS.txt identifies all packaged files except itself and generated outputs.
