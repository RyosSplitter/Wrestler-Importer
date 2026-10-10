"""Read-only file/purpose/size inventory of the published standalone bpy ZIP.

Uses only the Python standard library; never extracts or edits the application.
Sizes are ZIP member payload sizes, plus separately accounted ZIP overhead.
"""
import argparse
import ast
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile


NATIVE_PURPOSES = {
    '__init__.pyd': 'Compiled Blender engine and bpy Python interface; executes geometry operations',
    'usd_ms.dll': 'Universal Scene Description scene interchange runtime',
    'oslexec.dll': 'Open Shading Language shader execution runtime',
    'oslcomp.dll': 'Open Shading Language compiler',
    'oslnoise.dll': 'Open Shading Language noise functions',
    'oslquery.dll': 'Open Shading Language shader metadata queries',
    'cycles_kernel_oneapi_aot.dll': 'Precompiled Intel oneAPI GPU kernels for Cycles rendering',
    'embree4.dll': 'Intel Embree CPU ray tracing acceleration',
    'aom.dll': 'Alliance for Open Media AV1 video codec',
    'ceres.dll': 'Ceres numerical optimization/solver library',
    'draco.dll': 'Draco compressed geometry interchange',
    'epoxy-0.dll': 'OpenGL function dispatch',
    'gmp-10.dll': 'GNU multiple-precision arithmetic',
    'libgmpxx.dll': 'C++ bindings for GNU multiple-precision arithmetic',
    'hiprt0200564.dll': 'AMD HIP ray tracing runtime',
    'Iex.dll': 'OpenEXR exception utilities',
    'IlmThread.dll': 'OpenEXR threading utilities',
    'imath.dll': 'Imath mathematical types used by image/scene libraries',
    'meshoptimizer.dll': 'Meshoptimizer geometry optimization library',
    'OpenAL32.dll': 'OpenAL audio playback',
    'opencolorio_2_5.dll': 'OpenColorIO image color-management runtime',
    'openimageio.dll': 'OpenImageIO image loading/processing runtime',
    'openimageio_util.dll': 'OpenImageIO utility runtime',
    'openjph.0.25.dll': 'OpenJPH JPEG 2000/HTJ2K image codec',
    'openvdb.dll': 'OpenVDB sparse volumetric data runtime',
    'SDL3.dll': 'SDL window/input/audio platform support',
    'shaderc_shared.dll': 'Shaderc GLSL/SPIR-V shader compiler',
    'sndfile.dll': 'libsndfile audio file decoding/encoding',
    'sycl8.dll': 'Intel SYCL heterogeneous-compute runtime',
    'tbb12.dll': 'Intel Threading Building Blocks parallel task runtime',
    'ur_adapter_level_zero_v2.dll': 'Intel Unified Runtime Level Zero GPU adapter',
    'ur_loader.dll': 'Intel Unified Runtime compute loader',
    'ur_win_proxy_loader.dll': 'Intel Unified Runtime Windows proxy loader',
    'vulkan-1.dll': 'Vulkan graphics/compute loader',
}

PROJECT_PURPOSES = {
    'hctp-v1.json': 'Generalized HCTP conversion/weight/geometry policy profile',
    'hctp-provisional-v1.json': 'Provisional HCTP geometric QA tolerances and anatomical regions',
    'jericho-elbow-decimation-experiment.json': 'Isolated elbow-protection experiment QA profile; not a general acceptance rule',
    'REIMPLEMENTATION_GUIDE.txt': 'Instructions for independently implementing the converter',
    'requirements.txt': 'Legacy app Python dependency requirements',
    'requirements-desktop.txt': 'Portable desktop Python dependency requirements',
    'requirements-qa.txt': 'Read-only geometric QA Python dependency requirements',
}


def module_description(archive, item):
    if not item.filename.endswith('.py'):
        return PROJECT_PURPOSES.get(PurePosixPath(item.filename).name)
    try:
        doc = ast.get_docstring(ast.parse(archive.read(item).decode('utf-8-sig')))
        return doc.splitlines()[0] if doc else None
    except (UnicodeError, SyntaxError):
        return None


def classify(archive, item):
    parts = PurePosixPath(item.filename).parts[1:]
    name = parts[-1]
    # Each return: component, purpose, evidence for purpose, removal assessment.
    if parts[0] == 'sources':
        if name.endswith('.tar.xz'):
            return ('Blender source archive', 'Matching Blender 5.2.2 upstream source; already compressed; not loaded by conversion',
                    'CONFIRMED', 'Separate delivery candidate only with corresponding-source obligations maintained')
        desc = module_description(archive, item)
        return ('Converter source and documentation', 'Source/reference copy: ' + (desc or '/'.join(parts[2:])),
                'CONFIRMED' if desc else 'INFERRED', 'Not runtime-loaded from sources/; retain a compliant source distribution')
    if parts[0] == 'licenses':
        return ('License notices', 'Redistribution license/attribution or installed-distribution provenance: ' + name,
                'CONFIRMED', 'Retain applicable license and attribution obligations')
    if parts[0] != '_internal':
        purposes = {
            'PS2PSP-bpy-Experiment.exe': 'PyInstaller launcher, embedded app bytecode/PYZ and frozen job/QA dispatch',
            'MANIFEST.json': 'Per-file SHA-256 hashes and upstream wheel/source provenance',
            'README.txt': 'Prototype usage, clean-Windows self-check and licensing notes',
            'RunSelfCheck.cmd': 'Windows command launcher for procedural bpy/native/GUI self-check and logs',
        }
        return ('Launcher' if name.endswith('.exe') else 'Readme, self-check and manifest',
                purposes.get(name, 'Unclassified top-level file: '+name),
                'CONFIRMED' if name in purposes else 'UNKNOWN', 'Keep for current tested bundle')
    sub = parts[1:]
    if sub[0] == 'bpy':
        tail = sub[1:]
        if len(tail) == 1:
            purpose = NATIVE_PURPOSES.get(name)
            if name.startswith('OpenImageDenoise'):
                purpose = 'Open Image Denoise render denoising '+name.removesuffix('.dll').replace('OpenImageDenoise', '').strip('_')+' runtime'
            elif name.startswith('MaterialX'):
                purpose = 'MaterialX shader/material interchange '+name.removesuffix('.dll').replace('MaterialX', '')+' runtime'
            elif name.startswith('OpenEXR'):
                purpose = 'OpenEXR high-dynamic-range image '+name.removesuffix('.dll')+' runtime'
            elif name.startswith(('avcodec-', 'avdevice-', 'avfilter-', 'avformat-', 'avutil-', 'swresample-', 'swscale-')):
                purpose = 'FFmpeg media codec/device/filter/container/utility or resampling library: '+name
            core = name == '__init__.pyd'
            return ('bpy core extension' if core else 'bpy native dependencies',
                    purpose or 'Unresolved Blender native library: '+name,
                    'CONFIRMED' if core else ('INFERRED' if purpose else 'UNKNOWN'),
                    'Required geometry engine' if core else 'Dependency-coupled; removal safety UNKNOWN; no deletion tested')
        if tail[:3] == ('5.2', 'scripts', 'addons_core'):
            cycles = len(tail)>3 and tail[3]=='cycles'
            return ('bpy Cycles resources' if cycles else 'bpy bundled add-ons',
                    ('Cycles GPU/render kernel or integration resource: ' if cycles else 'Blender built-in add-on resource: ')+'/'.join(tail[3:]),
                    'INFERRED', 'Feature not explicitly used; startup/native resource dependency UNKNOWN')
        if tail[:3] == ('5.2', 'python', 'lib'):
            return ('bpy additional Python bindings', 'Blender image/scene/volume Python binding: '+'/'.join(tail[3:]),
                    'INFERRED', 'Optional feature candidate; import/resource dependency UNKNOWN')
        if tail[:2] == ('5.2', 'datafiles'):
            category = tail[2]
            roles = {'fonts': 'Blender UI/international font', 'assets': 'Blender brush/node asset library',
                     'colormanagement': 'Blender OpenColorIO configuration, transform or lookup table',
                     'studiolights': 'Blender studio-light/HDR environment', 'icons': 'Blender UI icon'}
            return ('bpy '+category+' resources', roles.get(category,'Blender data resource')+': '+name,
                    'INFERRED', 'Not explicitly used by geometry reducer; initialization dependency UNKNOWN')
        if tail[:2] == ('5.2', 'scripts'):
            return ('bpy startup, modules and templates', 'Blender '+tail[2]+' script/resource: '+'/'.join(tail[3:]),
                    'INFERRED', 'Startup/modules may be required; template/preset pruning untested')
        if tail[0] in ('usd','materialx'):
            return ('bpy scene/shader metadata', tail[0]+' plugin/schema/shader/scene resource: '+'/'.join(tail[1:]),
                    'INFERRED', 'Feature resource candidate; transitive dependency UNKNOWN')
        return ('bpy other resources', 'Blender resource: '+'/'.join(tail), 'INFERRED', 'Removal safety UNKNOWN')
    root = sub[0]
    if root.endswith('.dist-info'):
        return ('Python distribution metadata', 'Installed package version/dependency/license metadata: '+root+'/'+name,
                'CONFIRMED', 'Metadata may be queried at runtime; removal untested')
    if root in ('desktop', 'tools', 'model_qa', 'experiments'):
        desc = module_description(archive,item)
        return ('Converter, QA and experiment runtime files', desc or 'Project module/profile: '+'/'.join(sub),
                'CONFIRMED' if desc else 'INFERRED', 'Keep active modules/profiles; historical helpers are pruning candidates pending dependency tracing')
    if root.startswith(('_tcl', '_tk')) or root in ('tcl8','tkinterdnd2','tcl86t.dll','tk86t.dll','_tkinter.pyd'):
        return ('GUI, Tcl/Tk and drag/drop', 'Tk GUI/Tcl script, encoding, widget or drag/drop support: '+'/'.join(sub),
                'INFERRED', 'GUI uses Tk and drag/drop; platform/encoding subset pruning untested')
    if root in ('numpy','numpy.libs','scipy','scipy.libs','rtree','trimesh'):
        roles={'numpy':'Array/matrix math', 'numpy.libs':'NumPy native BLAS/Fortran libraries',
               'scipy':'Scientific/spatial algorithms', 'scipy.libs':'SciPy native BLAS library',
               'rtree':'Spatial-index acceleration for surface proximity', 'trimesh':'Mesh/surface geometry for QA'}
        return ('Geometry and QA math libraries', roles[root]+': '+'/'.join(sub), 'INFERRED', 'Used by converter/QA; unused submodule pruning untested')
    if root=='PIL':
        return ('Image libraries', 'Pillow image decoding/encoding/color/font support: '+name, 'INFERRED', 'Pillow used for textures/previews; optional codecs pruning untested')
    if root=='Cython':
        return ('Cython collection', 'Cython compiler/build utility or extension: '+'/'.join(sub), 'INFERRED', 'Collected as bpy dependency; conversion does not explicitly compile extensions; pruning untested')
    if root in ('requests','certifi','charset_normalizer','cattrs','zstandard','setuptools'):
        roles={'requests':'HTTP client', 'certifi':'HTTPS certificate bundle', 'charset_normalizer':'Text-encoding detection',
               'cattrs':'Attribute-class serialization', 'zstandard':'Zstandard compression', 'setuptools':'Python package/bootstrap utility'}
        return ('Other collected Python dependencies', roles[root]+': '+'/'.join(sub), 'INFERRED', 'Declared/collected dependency; actual startup/workflow dependency requires tracing')
    if name in ('python313.dll','python3.dll','base_library.zip'):
        return ('Python interpreter and standard library', {'python313.dll':'CPython 3.13 interpreter',
                'python3.dll':'CPython stable-ABI forwarding library','base_library.zip':'Frozen Python standard-library bootstrap bytecode archive'}[name],
                'CONFIRMED', 'Keep frozen runtime bootstrap')
    if name.startswith(('api-ms-','MSVCP','VCRUNTIME')) or name=='ucrtbase.dll':
        return ('Windows C/C++ runtime support', 'Windows/Microsoft C/C++ runtime or API compatibility DLL: '+name,
                'INFERRED', 'Native dependencies may require these; clean-Windows pruning untested')
    if name.endswith('.pyd'):
        return ('Python interpreter and standard library', 'CPython compiled standard-library extension: '+name,
                'INFERRED', 'Workflow/stdlib dependencies; unused extension pruning untested')
    if name in ('libcrypto-3.dll','libssl-3.dll','libffi-8.dll','zlib1.dll'):
        return ('Python native support libraries', 'Python SSL/cryptography/foreign-function/compression native dependency: '+name,
                'INFERRED', 'Transitive native dependencies; removal untested')
    return ('Unclassified support', 'Unresolved bundled file: '+'/'.join(sub), 'UNKNOWN', 'Investigate before any removal')


def inventory(path, output):
    path=Path(path); output=Path(output); output.mkdir(parents=True,exist_ok=True)
    rows=[]; groups=defaultdict(lambda:dict(files=0,compressed_bytes=0,expanded_bytes=0))
    identical=defaultdict(list)
    with zipfile.ZipFile(path) as archive:
        files=[i for i in archive.infolist() if not i.is_dir()]
        if any(len(PurePosixPath(i.filename).parts)<2 for i in files):
            raise ValueError('Expected one root directory containing the bundle')
        roots={PurePosixPath(i.filename).parts[0] for i in files}
        if len(roots)!=1: raise ValueError('Expected a single bundle root')
        root=roots.pop()
        manifest_raw=archive.read(root+'/MANIFEST.json')
        manifest=json.loads(manifest_raw)
        paths={'/'.join(PurePosixPath(i.filename).parts[1:]) for i in files}
        if paths != set(manifest['files'])|{'MANIFEST.json'}:
            raise ValueError('ZIP members disagree with manifest inventory')
        for item in sorted(files,key=lambda i:i.filename):
            relative='/'.join(PurePosixPath(item.filename).parts[1:])
            group,purpose,evidence,removal=classify(archive,item)
            digest=manifest['files'].get(relative) or hashlib.sha256(manifest_raw).hexdigest()
            row=dict(path=relative,component=group,purpose=purpose,purpose_evidence=evidence,
                     compressed_bytes=item.compress_size,expanded_bytes=item.file_size,
                     compressed_mib=round(item.compress_size/2**20,6),expanded_mib=round(item.file_size/2**20,6),
                     sha256=digest,removal_assessment=removal)
            rows.append(row)
            g=groups[group];g['files']+=1;g['compressed_bytes']+=item.compress_size;g['expanded_bytes']+=item.file_size
            if item.file_size: identical[(digest,item.file_size)].append(row)
    duplicates=[]
    for (digest,size),members in identical.items():
        if len(members)>1:
            duplicates.append(dict(sha256=digest,expanded_bytes_each=size,paths=[r['path'] for r in members],
                repeated_expanded_bytes=size*(len(members)-1),
                repeated_compressed_bytes=sum(r['compressed_bytes'] for r in members)-max(r['compressed_bytes'] for r in members)))
    payload=sum(r['compressed_bytes'] for r in rows)
    result=dict(archive=path.name,sha256=hashlib.file_digest(path.open('rb'),'sha256').hexdigest(),
                zip_bytes=path.stat().st_size,files=len(rows),expanded_bytes=sum(r['expanded_bytes'] for r in rows),
                compressed_payload_bytes=payload,zip_container_overhead_bytes=path.stat().st_size-payload,
                components=dict(sorted(groups.items(),key=lambda kv:-kv[1]['compressed_bytes'])),
                largest_files=sorted(rows,key=lambda r:-r['compressed_bytes'])[:40],
                duplicate_groups=sorted(duplicates,key=lambda g:-g['repeated_expanded_bytes']),
                duplicate_repeated_expanded_bytes=sum(g['repeated_expanded_bytes'] for g in duplicates),
                duplicate_repeated_compressed_bytes=sum(g['repeated_compressed_bytes'] for g in duplicates),
                unclassified_paths=[r['path'] for r in rows if r['purpose_evidence']=='UNKNOWN'],
                hash_provenance='Member hashes read from previously verified published MANIFEST.json; manifest itself hashed here. ZIP independently hashed here. This inventory does not rehash every payload.',
                caveats=['Compressed member bytes exclude ZIP headers/directories; overhead accounted separately.',
                         'Expanded sizes are logical file bytes, not NTFS allocated size.',
                         'Source .tar.xz and base_library.zip remain archives; contents are not double-counted.',
                         'Purpose labels distinguish measured/project-docstring claims from library-name inference.',
                         'No dependency stripping or removal-safety tests were performed. Duplicates are not automatically removable.'])
    with (output/'file-inventory.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    (output/'file-inventory-summary.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    if sum(g['files'] for g in groups.values())!=len(rows):raise AssertionError('File accounting')
    if sum(g['expanded_bytes'] for g in groups.values())!=result['expanded_bytes']:raise AssertionError('Size accounting')
    print(json.dumps({k:result[k] for k in ('archive','files','zip_bytes','expanded_bytes','zip_container_overhead_bytes','unclassified_paths','duplicate_repeated_expanded_bytes')},indent=2))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();inventory(args.archive,args.output)
