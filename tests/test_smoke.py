"""The server binds to 127.0.0.1 and the dashboard answers HTTP 200."""

import threading
import urllib.request
from pathlib import Path

from werkzeug.serving import make_server

from carcareclock.rules import load_defaults, load_rules
from carcareclock.web import create_app

ROOT = Path(__file__).resolve().parents[1]


def test_server_on_loopback_returns_200(tmp_path: Path):
    app = create_app(
        tmp_path / "carcareclock.sqlite",
        load_rules(ROOT / "rules" / "maryland.yaml"),
        load_defaults(ROOT / "rules" / "maintenance_defaults.yaml"),
    )
    server = make_server("127.0.0.1", 0, app, threaded=True)
    host, port = server.server_address
    assert host == "127.0.0.1"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=10) as response:
            body = response.read().decode()
            assert response.status == 200
        assert "CarCareClock" in body
        assert "Demo Kia" in body
        assert "Log mileage" in body
    finally:
        server.shutdown()
