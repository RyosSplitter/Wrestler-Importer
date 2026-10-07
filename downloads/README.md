# Test downloads

[Download the 144 KiB compact PAC with Noesis model/textures](https://github.com/RyosSplitter/Wrestler-Importer/raw/refs/heads/main/downloads/RVD-HCTP-to-PSP-compact-test-bundle.zip).
This is the next test candidate after the 424 KiB build crashed. Extract the
ZIP and open `preview/prepared.yobj` in Noesis; its named PNG/GIM textures are
beside it. That YOBJ is byte-for-byte identical to the compact PAC's model.
See [compact conversion and archive checks](../docs/compact-candidate.md).
Compact playability is unverified; start from clean game archives for re-testing.
The user tests in SVR 2011 PSP. This candidate still uses the supplied SVR 2007
Kurt base; the original 2011 destination PAC is needed for a version-matched base.

[Download the alignment-corrected HCTP RVD to PSP SVR 2007 test bundle](https://github.com/RyosSplitter/Wrestler-Importer/raw/refs/heads/main/downloads/RVD-HCTP-to-PSP-test-bundle-aligned.zip).

[Download the model with named preview textures](https://github.com/RyosSplitter/Wrestler-Importer/raw/refs/heads/main/downloads/RVD-Noesis-texture-preview.zip).
Extract this preview ZIP to a folder and open `prepared.yobj` or `prepared.dae`
there. PNG/GIM textures sit beside the model under its expected texture names.
This fixes the original export's missing external image paths. Automatic YOBJ
texture loading still depends on your Noesis plugin. The aligned test PAC is
unchanged and already includes its 15 main GIM textures.

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
