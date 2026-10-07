# Test downloads

[Download the alignment-corrected HCTP RVD to PSP SVR 2007 test bundle](https://github.com/RyosSplitter/Wrestler-Importer/raw/refs/heads/main/downloads/RVD-HCTP-to-PSP-test-bundle-aligned.zip).

This experimental bundle includes the converted PAC, model and texture exports,
Blender review file, pose previews, reports, and installation/test instructions.
It replaces Kurt's slot using the supplied PSP SVR 2007 base. Playability has
not yet been confirmed in PPSSPP. Back up your original files and follow
`README-test.txt` inside the bundle.

The PAC is larger than the original base; the containing archive must be
repacked with updated offsets and sizes. See
[conversion status](../docs/conversion-status.md) for known limitations.

This bundle replaces the first download, which triggered an alignment warning
in PAC Editor v6.7.1. The native relocation chunk and PAC section starts are now
16-byte aligned; Windows editor verification is pending.

PAC SHA-256: `7250868aab7a728ebd7ef198421039ffbd1c2f90a42274c84be2a2f89e9e1c78`.
