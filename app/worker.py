"""Separate conversion process; GUI cancellation cannot alter source assets."""
import contextlib
import json
from pathlib import Path
import traceback

from app.pipeline import Job, run_job


def main(request_path):
    request = Path(request_path).resolve()
    events, result, log = [request.parent / n for n in ('events.jsonl', 'result.json', 'worker.log')]
    with events.open('w', encoding='utf-8') as stream, log.open('w', encoding='utf-8') as output:
        def progress(percent, message):
            stream.write(json.dumps({'percent': percent, 'message': message})+'\n')
            stream.flush()
        try:
            job = Job(**json.loads(request.read_text(encoding='utf-8')))
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                response = run_job(job, progress)
            response['ok'] = True
        except Exception as exc:
            traceback.print_exc(file=output)
            response = {'ok': False, 'error': str(exc), 'log': str(log)}
        result.write_text(json.dumps(response, indent=2)+'\n', encoding='utf-8')
        return 0 if response['ok'] else 1
