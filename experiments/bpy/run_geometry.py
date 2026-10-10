"""Run the existing geometry stage in an unfrozen standalone bpy interpreter."""
import json
import sys
import time

from desktop.geometry_worker import run

if __name__=='__main__':
    import bpy
    start = time.perf_counter()
    run(*sys.argv[1:])
    print(json.dumps(dict(bpy=bpy.app.version_string, build_hash=bpy.app.build_hash.decode(),
        python=sys.version, seconds=time.perf_counter()-start)))
