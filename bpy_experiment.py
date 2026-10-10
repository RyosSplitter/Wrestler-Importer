"""Standalone-bpy prototype entry. Production ps2psp_converter is unchanged."""
from experiments.bpy.entry import main

if __name__ == '__main__':
    import traceback
    try: raise SystemExit(main())
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
