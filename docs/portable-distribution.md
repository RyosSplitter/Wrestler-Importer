# Portable distribution boundaries

The application is a collection of separate programs/libraries. Blender runs as
a separate offline process; Noesis, YOBJ Mesh Editor, PAC Editor and uploaded tool
executables are not included or invoked. User-supplied PACs provide the base
skeleton and opaque native rendering templates locally. No reference PAC, YOBJ,
texture, reference-model ZIP or generated game art is included in the release.

The builder retains the official Blender ZIP's licenses/copyright notices and
ships the corresponding `blender-4.3.2.tar.xz` source archive under `sources/`.
Blender is GPL licensed; consult the included Blender GPL and third-party notices.
The source archive is fetched over official HTTPS; its computed SHA-256 is recorded
in the manifest. The runtime ZIP additionally has a published checksum comparison.
The complete official runtime remains intact, including Python and its notices.

Frozen dependencies include CPython/Tcl/Tk, NumPy, Pillow, SciPy, Trimesh, Rtree,
TkinterDnD2/TkDND and PyInstaller's bootloader. Installed distributions' license
files are copied to `licenses/`, together with their versions/license metadata,
Python's license and Tcl/Tk notices. Runtime-specific bundled notices remain
alongside the runtime. PyInstaller's bootloader exception and each library's terms
must be retained; the package manifest is evidence of contents, not a legal opinion
or a substitute for reading the actual notices before commercial redistribution.

Converter/QA/worker source is included under `sources/converter/`. This does not
grant rights to the user's game assets or to unrelated historical repository
downloads. Development-only CI fixtures reconstruct existing reference geometry
with generated checkerboard textures; they and their resulting PACs remain outside
the portable release. References historically tracked in this repository are not
thereby authorized for inclusion in a new application bundle.

The build is not code-signed. Windows preview validation is recorded separately
from PPSSPP tests; the application must not label analytical QA as gameplay proof.
