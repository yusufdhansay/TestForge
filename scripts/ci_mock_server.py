"""Minimal local HTTP server for TestForge CI contract tests."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = "127.0.0.1"
PORT = 8765


class MockAPIHandler(BaseHTTPRequestHandler):
    """Serve deterministic responses for the CI OpenAPI specification."""

    def do_GET(self):
        if self.path == "/health":
            self.send_json(
                200,
                {"status": "ok"},
            )
        elif self.path == "/version":
            self.send_json(
                200,
                {"version": "1.0.0"},
            )
        else:
            self.send_json(
                404,
                {"error": "Not found"},
            )

    def send_json(self, status_code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")

        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format_string, *args):
        """Suppress request logs during CI runs."""


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), MockAPIHandler)

    print(
        f"TestForge CI mock API listening on http://{HOST}:{PORT}",
        flush=True,
    )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
