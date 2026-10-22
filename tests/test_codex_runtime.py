"""Optional real-CLI lifecycle test; no model service or user configuration is used.

Run with VIBEBOARD_TEST_CODEX=/absolute/path/to/codex pytest -q.
"""

import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from adapters.codex import install


@pytest.mark.skipif(not os.environ.get("VIBEBOARD_TEST_CODEX"), reason="Codex CLI not supplied")
def test_real_codex_start_and_end(tmp_path):
    class FixedResponse(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):  # noqa: N802 - stdlib handler method
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            message = {
                "id": "msg_probe",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": "Probe complete.", "annotations": []}],
            }
            response = {
                "id": "resp_probe",
                "object": "response",
                "created_at": 0,
                "status": "completed",
                "model": "vibeboard-test",
                "output": [message],
                "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            }
            events = [
                {
                    "type": "response.created",
                    "response": {**response, "output": [], "status": "in_progress"},
                },
                {
                    "type": "response.output_item.added",
                    "output_index": 0,
                    "item": {**message, "status": "in_progress", "content": []},
                },
                {
                    "type": "response.output_text.delta",
                    "output_index": 0,
                    "content_index": 0,
                    "item_id": message["id"],
                    "delta": "Probe complete.",
                },
                {"type": "response.output_item.done", "output_index": 0, "item": message},
                {"type": "response.completed", "response": response},
            ]
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for event in events:
                self.wfile.write(f"event: {event['type']}\ndata: {json.dumps(event)}\n\n".encode())
                self.wfile.flush()

    server = ThreadingHTTPServer(("127.0.0.1", 0), FixedResponse)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    config = tmp_path / "codex-config"
    config.mkdir()
    (config / "config.toml").write_text(
        'model="vibeboard-test"\nmodel_provider="vibeboard-test"\n'
        '[model_providers.vibeboard-test]\nname="Local fixed-response test"\n'
        f'base_url="http://127.0.0.1:{server.server_port}/v1"\nwire_api="responses"\n'
    )
    install.configure(config)
    env = {
        **os.environ,
        "CODEX_HOME": str(config),
        "VIBEBOARD_HOME": str(tmp_path / "board"),
        "TERM_SESSION_ID": "w0t0p0:runtime-probe",
    }
    env.pop("TMUX", None)
    env.pop("ITERM_SESSION_ID", None)
    try:
        result = subprocess.run(
            [
                os.environ["VIBEBOARD_TEST_CODEX"],
                # Only this isolated invocation runs our reviewed/generated hooks without
                # persisted trust. Never apply this flag to the installed user setup.
                "--dangerously-bypass-hook-trust",
                "--no-daemon",
                "exec",
                "--json",
                "--skip-git-repo-check",
                "-C",
                str(tmp_path),
                "Return the fixed probe response.",
            ],
            env=env,
            text=True,
            capture_output=True,
            timeout=45,
            check=True,
        )
        events = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
        session = next(e["thread_id"] for e in events if e.get("type") == "thread.started")
        assert any(e.get("type") == "turn.completed" for e in events)
        record = json.loads((tmp_path / "board/panes/RUNTIME-PROBE.json").read_text())
        assert record["session"] == session
        assert record["project"] == str(tmp_path)
        assert record["started_at"] and record["ended_at"]
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
