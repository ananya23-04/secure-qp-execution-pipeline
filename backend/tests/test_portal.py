import re
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"
pytestmark = pytest.mark.skipif(not STATIC.is_dir(), reason="portal bundle not built")


def test_root_redirects_to_portal(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307) and r.headers["location"] == "/app/"


def test_portal_html_and_every_referenced_asset_are_served(client):
    html = client.get("/app/")
    assert html.status_code == 200 and 'id="root"' in html.text
    refs = re.findall(r'(?:src|href)="(/app/assets/[^"]+)"', html.text)
    assert any(x.endswith(".js") for x in refs) and any(x.endswith(".css") for x in refs)
    for ref in refs:
        r = client.get(ref)
        assert r.status_code == 200 and len(r.content) > 500, ref
    css = next(client.get(x).text for x in refs if x.endswith(".css"))
    fonts = re.findall(r"url\((?:/app/)?(assets/[^)\"']+\.woff2)\)", css) or re.findall(r"url\(\.?/?(assets/[^)\"']+\.woff2)\)", css)
    assert fonts, "KaTeX fonts should be bundled so maths renders offline"
    assert client.get("/app/" + fonts[0]).status_code == 200


def test_api_routes_still_win_over_portal(client):
    assert client.get("/health").json() == {"ok": True}
    assert client.get("/docs").status_code == 200
