"""GUI entry point, also used by the frozen Windows worker process."""
import sys


def main():
    if len(sys.argv) == 3 and sys.argv[1] == '--worker':
        from app.worker import main as worker
        return worker(sys.argv[2])
    if len(sys.argv) == 3 and sys.argv[1] == '--smoke-test':
        import json
        from pathlib import Path
        from app.gui import BetaApp, make_root
        from app.pipeline import verify_backend
        root, drag_drop = make_root()
        app = BetaApp(root, drag_drop)
        root.update()
        profile = verify_backend()
        result = {'gui_started': True, 'drag_drop': drag_drop, 'profile': profile['profile_id'],
                  'bundled_references_found': all(Path(app.values[k]).is_file() for k in ('base', 'reference'))}
        root.destroy()
        Path(sys.argv[2]).write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
        return 0 if all((drag_drop, result['bundled_references_found'])) else 1
    from app.gui import launch
    launch()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
