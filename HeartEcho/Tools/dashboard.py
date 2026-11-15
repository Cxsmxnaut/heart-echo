#!/usr/bin/env python3
"""Read-only, loopback-only dashboard for collect_study.py output. No dependencies."""
import argparse
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import threading
import time
from urllib.parse import urlsplit

CONDITIONS = ['Quiet', 'Background sound', 'Brief repositioning', 'Off chest']


def number(value):
    return value if isinstance(value, (int, float)) and math.isfinite(value) else None


class Dashboard:
    def __init__(self, directory):
        self.directory = directory
        self.cache = {}
        self.archive_signature = None
        self.rows = []
        self.history = deque(maxlen=1800)
        self.events = deque(maxlen=60)
        self.last_key = None
        self.completed = {}
        self.lock = threading.Lock()

    def read(self, filename):
        try:
            value = json.loads((self.directory / filename).read_text())
            if isinstance(value, dict): self.cache[filename] = value
        except (OSError, ValueError):
            pass  # The collector may be replacing a file; retain the last good copy.
        return self.cache.get(filename, {})

    def state(self):
        with self.lock:
            now = time.time()
            summary = self.read('summary.json')
            status = summary.get('status') if summary.get('connection_ok') else None
            status = status or self.read('status.json')
            plan = self.read('study-state.json')
            total_cycles = max(1, min(5, int(plan.get('repetitions') or 5)))
            total_tests = total_cycles * 4
            study = plan.get('id') or status.get('study')
            ending = self.read('study-ended.json')
            ended = bool(study and ending.get('study') == study)
            poll_age = max(0, now - (number(summary.get('polled_at')) or 0))
            age = max(0, now - (number(status.get('time')) or 0) / 1000)
            connected = bool(summary.get('connection_ok') and poll_age < 20)
            current = not study or status.get('study') == study
            fresh = connected and age < 12 and current
            running = fresh and not ended and status.get('running') and status.get('state') == 'recording'
            phone = number(status.get('phoneBPM')) if running else None
            watch_age = max(0, now - (number(status.get('watchTime')) or 0) / 1000)
            watch = number(status.get('watchBPM')) if fresh and watch_age < 12 else None
            key = (status.get('run'), status.get('sequence'))
            if key != self.last_key and current and status.get('time'):
                self.last_key = key
                self.events.append({k: status.get(k) for k in
                                    ('time', 'event', 'sequence', 'state', 'message', 'condition', 'step')})
                if fresh:
                    self.history.append(dict(time=status['time'] / 1000, phone=phone, watch=watch,
                                             watchTime=status.get('watchTime'), test=status.get('test')))
                if status.get('state') == 'completed' and status.get('test') and status.get('study') == study:
                    self.completed[status['test']] = dict(status)
            archive = self.directory / 'captured.ndjson'
            try:
                stat = archive.stat()
                signature = (stat.st_size, stat.st_mtime_ns)
                if signature != self.archive_signature:
                    rows = []
                    for line in archive.read_text().splitlines():
                        try: rows.append(json.loads(line))
                        except ValueError: pass
                    self.rows, self.archive_signature = rows, signature
            except OSError:
                pass
            for row in self.rows:
                if (row.get('study') == study and row.get('test') and row.get('event') == 'test_ended'
                        and row.get('message') == 'timed_test_complete'):
                    self.completed[row['test']] = row
            completed_steps = sorted({r['step'] for r in self.completed.values()
                                      if r.get('study') == study and isinstance(r.get('step'), int)})
            step = status.get('step') if current else None
            step = step or min(total_tests, (max(completed_steps, default=0) + 1))
            step = max(1, min(total_tests, int(step)))
            latest_done = current and status.get('state') == 'completed'
            next_step = min(total_tests, step + 1) if latest_done else step
            condition = status.get('condition') if fresh and current and not latest_done else CONDITIONS[((next_step - 1) % 4 + (next_step - 1) // 4) % 4]
            remaining = max(0, (number(status.get('remaining')) or 0) - age) if running else None
            phase = status.get('state', 'idle') if fresh else ('waiting' if connected else 'disconnected')
            if len(completed_steps) == total_tests: phase = 'completed'
            elif ended: phase = 'ended'
            return dict(now=now, connected=connected, pollAge=poll_age, snapshotAge=age,
                        studyEnded=ended, endReason=ending.get('reason') if ended else None,
                        watchAge=watch_age, phone=phone, watch=watch, phase=phase, running=bool(running),
                        remaining=remaining, condition=condition, step=next_step, cycle=(next_step - 1) // 4 + 1,
                        totalTests=total_tests, totalCycles=total_cycles,
                        completed=completed_steps, participant=plan.get('participant') or status.get('participant', 'A'),
                        history=list(self.history), events=list(self.events)[-35:][::-1],
                        sequence=status.get('sequence', 0), captured=summary.get('captured_events', len(self.rows)),
                        error=summary.get('error') if not connected else None,
                        archiveErrors=summary.get('archive_errors', []),
                        source=self.directory.name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args()
    dashboard = Dashboard(args.input.resolve())
    page = Path(__file__).with_name('dashboard.html').read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            # Keep private health logs on this Mac, including against DNS rebinding.
            if self.headers.get('Host') not in {f'localhost:{args.port}', f'127.0.0.1:{args.port}'}:
                self.send_error(403); return
            route = urlsplit(self.path).path
            if route == '/api/state':
                data, content_type = json.dumps(dashboard.state(), allow_nan=False).encode(), 'application/json'
            elif route == '/':
                data, content_type = page, 'text/html; charset=utf-8'
            elif route == '/favicon.ico':
                self.send_response(204); self.end_headers(); return
            else:
                self.send_error(404); return
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            try: self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError): pass

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Heart Echo dashboard: http://localhost:{args.port} (only this Mac)', flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()


if __name__ == '__main__': main()
