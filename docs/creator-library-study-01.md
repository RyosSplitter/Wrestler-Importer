# Creator library study 01 — Models for Codex.zip

This is a read-only study for the next creator iteration. The app, converter,
accepted PACs and original files are unchanged. No assembled PAC was built or
gameplay-tested in this study.

## Results

- **CONFIRMED:** 31 PACs, 4,376,576 bytes uncompressed. Every extracted PAC still
  matches its original SHA-256. The archive is 2,919,419 bytes.
- **CONFIRMED:** 25 main YOBJs pass the existing native auditor directly. Six
  contain two named descriptor records and need diagnostic interpretation before
  the existing single-descriptor auditor can inspect their other buffers.
- **CONFIRMED:** 649 texture entries decode: 620 indexed4 and 29 indexed8. No
  texture decode failures.
- **CONFIRMED:** The current creator importer accepts 21 files. Six are withheld
  by its descriptor-count assumption; four by its short-FF-fill guard. These are
  implementation-support classifications, not judgments that originals are corrupt.
- **CONFIRMED:** Common named body-bone local transforms match the original Kenny
  reference within 1e-5 for 28 models. Total bone counts range from 77 to 107.
  A common-body match does not establish face, seam, accessory or game compatibility.
- **CONFIRMED:** 22 source PACs are within the current 148,000-byte creator export
  target; nine exceed it. Sizes range from 102,400 to 198,656 bytes. Larger source
  files should still be browseable and previewable. These sizes do not establish
  a new runtime limit.
- **UNKNOWN:** exact originating SVR releases, original/modded provenance, game
  memory limits and compatibility of each assembled combination. Filenames and
  successful decoding alone do not establish them.

## Descriptor discovery

**CONFIRMED observations:** header uint32 at YOBJ byte 52 is 1 in 25 files and 2
in six. The relative pointer at byte 48 addresses contiguous 32-byte named records.
Across all 31 files, summing uint32 values at record+24 equals the global mesh
count at header+24. Corresponding trailing mesh buffers use these hair textures:

| File | Descriptor mesh counts | Second descriptor | Textures in trailing group |
|---|---|---|---|
| CM-Punk-Ring.PAC | 24 + 1 | hair | cm_a_hair |
| Joey-Mercury-Ring.PAC | 25 + 5 | Mercury_hair | mel_haira, mel_hairb |
| Matt-Hardy.PAC | 27 + 4 | hair01 | _a_hair_01, _a_hair_02 |
| Umaga (2).PAC | 23 + 2 | 1500 | u_hair |
| Yoshi-Tatsu.PAC | 27 + 4 | YoshiTatsu_hair | 283_haira, 283_hairb, 283_haird, 283_haire |
| Zack-Ryder.PAC | 25 + 2 | zack_hair | zack_hair_a, zack_hair_b |

**INFERRED interpretation:** these records describe ordered mesh groups,
including separately rendered hair. Mesh ownership and runtime semantics remain
unproven. Record+16/+20/+28 values are 1/0/0 in this corpus; their meanings are not
established merely by observing those values.

The existing auditor expects the first descriptor to cover every mesh. That is
the exact rejection for these six files. For **diagnostic previews only**, the
scanner changes that one count in a memory copy, reusing the unchanged auditor
to inspect the other buffers. It writes neither that modified YOBJ nor a PAC.
Original descriptors remain preserved and unsupported for rewriting. These views
do not establish that the originals passed the single-descriptor audit.

## Other import and rig findings

**CONFIRMED:** Batista, Chris Jericho, Danny Basham and John Cena contain 20-byte
FF runs before some vertex-pointer cells. The current prepared-pair creator
permits FF allocation gaps only up to 16 bytes. These files pass the native
auditor but are withheld by the writer-preparation guard. **INFERRED:** the runs
are allocation fill. Do not merely increase a limit or discard the runs without
checking pointer targets and native allocation ownership.

**CONFIRMED:** Jeff and Matt Hardy have different `kubi` local translations,
maximum component difference 0.2158997 native units versus Kenny. JBL Suit has
different leg/foot binds and rotations. Small finger-rotation differences are
recorded too. These require explicit bind-aware compatibility decisions.

**CONFIRMED:** Booker's `Dummy03` has four weighted vertex records used by
`bt_han` hand materials. Sabu has extra root-parented controller chains; 18 vertex
records influenced by their children occur in `sab_obi` material geometry.
**UNKNOWN:** their complete animation semantics. Do not discard a bone because
it is named Dummy or classify `kami*` as hair from its name alone. Part ownership
must consider actual weighted geometry, materials and parent dependencies.

**CONFIRMED:** optional Kenny helpers (`root_d`, `l_sakotsu_d`, `r_sakotsu_d`) are
absent in many models. None of these three names has nonzero vertex weights in
the supplied models where present. **UNKNOWN:** any non-skinning runtime role;
zero weights are not blanket permission to discard metadata.

**CONFIRMED:** only Cody Rhodes, Dolph Ziggler and Kofi pass both the current
importer and its complete named-rig gate against Kenny. That narrow prototype
gate does not describe every potentially usable model. Actual mixed-PAC and
attachment tests have not been run here.

**CONFIRMED:** Rob Van Dam has a 256×128 indexed4 `rvd_body` texture, which
decodes successfully. **UNKNOWN:** compatibility in every SVR 2011 slot/profile.
Do not automatically add it to the optimizer's validated output whitelist.

## Next iteration — proposed, not implemented

1. Add a read-only folder library, search, cached front/rear thumbnails and source
   hashes. Show unsupported/conditional entries with specific reasons. Preview
   eligibility must remain separate from the export-size target.
2. Support complete descriptor arrays in reader, writer, relocation/allocation
   audits and roundtrip checks. Preserve group order and accessory dependencies.
3. Replace whole-skeleton equality with explicit per-part bind and controller
   checks. Preserve selected heads' facial/jaw/eye rigs and all actually weighted
   extra controllers, including those outside the head subtree.
4. Establish anatomical attachment profiles. Common binds do not prove neck,
   armhole, waist or clothing boundaries match the original two-model cut planes.
5. Separate output-container selection from the library list. Preserve unrelated
   payloads and investigate nested section-100 PAC dependencies before dropping data.
6. Reuse QA and actual serialized-size enforcement on each assembled candidate.
   Check seams, poses, facial motion, cutouts and palettes. Keep experimental
   outputs separate until PPSSPP testing.

## Reproduce

Unpack your own archive into a private folder. From the repository, with desktop
dependencies installed, compare against your original Kenny PSP PAC:

```sh
python -m tools.creator_library_inventory --folder "Models for Codex" --reference "Kenny-Dykstra.PAC" --output NEW_STUDY_FOLDER --previews
```

The reference is optional. The tool writes inventory JSON/CSV and optional
front/back PNGs. It never writes a PAC/native YOBJ and refuses an existing report
directory. Auditor and creator behavior remain unchanged. No source PACs or
derived renders are committed.

Verified: 31 real PACs, 62 views, 649 decoded GIMs and input hash preservation.
Original synthetic fixtures additionally verified scanning, four previews,
existing-output rejection and the ordinary zero-header convention. No game or
assembled-part QA is claimed for this read-only stage.

## Per-file inventory

Descriptor-based diagnostic reads are described above. Import eligibility does
not certify export or gameplay compatibility.

| File | PAC bytes | Meshes | Vertices | Triangles | Bones | Descriptors | v0.1 import |
|---|---:|---:|---:|---:|---:|---:|---|
| Batista.PAC | 112,640 | 26 | 1514 | 1497 | 79 | 1 | FF allocation guard |
| Booker-T.PAC | 114,688 | 26 | 1525 | 1500 | 97 | 1 | Yes |
| Bret-Hart.PAC | 112,640 | 30 | 1504 | 1502 | 96 | 1 | Yes |
| British-Bulldog.PAC | 104,448 | 24 | 1424 | 1500 | 79 | 1 | Yes |
| Carlito.PAC | 112,640 | 25 | 1628 | 1500 | 79 | 1 | Yes |
| Charlie-Haas.PAC | 116,736 | 25 | 1658 | 1452 | 78 | 1 | Yes |
| Chavo-Guerrero.PAC | 102,400 | 20 | 1370 | 1500 | 79 | 1 | Yes |
| Chris-Benoit.PAC | 102,400 | 23 | 1308 | 1499 | 77 | 1 | Yes |
| Chris-Jericho.PAC | 116,736 | 27 | 1522 | 1500 | 97 | 1 | FF allocation guard |
| Chris-Masters.PAC | 106,496 | 25 | 1352 | 1499 | 79 | 1 | Yes |
| Christian.PAC | 106,496 | 26 | 1417 | 1494 | 79 | 1 | Yes |
| CM-Punk-Ring.PAC | 139,264 | 25 | 1411 | 1725 | 83 | 2 | Descriptor support needed |
| Cody-Rhodes-Ring.PAC | 147,456 | 26 | 1573 | 1820 | 83 | 1 | Yes |
| Danny-Basham.PAC | 178,176 | 26 | 1343 | 1500 | 79 | 1 | FF allocation guard |
| Dolph-Ziggler.PAC | 147,456 | 27 | 1532 | 1780 | 83 | 1 | Yes |
| Edge.PAC | 178,176 | 28 | 1395 | 1497 | 97 | 1 | Yes |
| JBL(Suit).PAC | 169,984 | 25 | 1397 | 1417 | 79 | 1 | Yes |
| Jeff-Hardy.PAC | 143,360 | 27 | 1372 | 1741 | 98 | 1 | Yes |
| Joey-Mercury-Ring.PAC | 190,464 | 30 | 1426 | 1486 | 107 | 2 | Descriptor support needed |
| John-Cena-Ring(Green).PAC | 198,656 | 28 | 1557 | 1500 | 79 | 1 | FF allocation guard |
| KOFI_KINGSTON.pac | 139,264 | 25 | 1442 | 1739 | 83 | 1 | Yes |
| Matt-Hardy.PAC | 176,128 | 31 | 1402 | 1496 | 91 | 2 | Descriptor support needed |
| Randy-Orton.PAC | 108,544 | 28 | 1478 | 1497 | 79 | 1 | Yes |
| Rob-Van-Dam.PAC | 190,464 | 30 | 1499 | 1485 | 84 | 1 | Yes |
| Sabu-Ring.PAC | 110,592 | 26 | 1407 | 1759 | 101 | 1 | Yes |
| Tyson-kidd.PAC | 141,312 | 23 | 1374 | 1748 | 83 | 1 | Yes |
| Umaga (2).PAC | 137,216 | 25 | 1411 | 1715 | 97 | 2 | Descriptor support needed |
| Umaga.PAC | 188,416 | 25 | 1440 | 1496 | 97 | 1 | Yes |
| Undertaker.PAC | 198,656 | 26 | 1557 | 1495 | 99 | 1 | Yes |
| Yoshi-Tatsu.PAC | 145,408 | 31 | 1468 | 1745 | 101 | 2 | Descriptor support needed |
| Zack-Ryder.PAC | 139,264 | 27 | 1372 | 1710 | 98 | 2 | Descriptor support needed |
