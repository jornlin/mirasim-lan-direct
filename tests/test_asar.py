import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mld import asar  # noqa: E402


def make_tree(files):
    tree = {"files": {}}
    contents = {}
    entries = []
    for path, data in files.items():
        parts = path.strip("/").split("/")
        node = tree
        for part in parts[:-1]:
            node = node["files"].setdefault(part, {"files": {}})
        node["files"][parts[-1]] = {"size": 0, "offset": "0", "integrity": {}}
        full = "/" + path.strip("/")
        contents[full] = data
        entries.append((full, node["files"][parts[-1]]))
    return asar.Asar(tree, entries, contents)


FILES = {
    "package.json": b'{"name":"fake","version":"9.9.9"}',
    "dist/renderer/index.html": b'<html><head><meta http-equiv="Content-Security-Policy" content="default-src \'self\'; connect-src \'self\'; img-src \'self\'; media-src \'self\'; object-src \'self\'; frame-src \'self\'"></head><body>x</body></html>',
    "dist/renderer/assets/default-space.js": (
        b'const M="wss://rendezvous.example/x";'
        b"function K(e){return!!e.grant}"
        b"function N(e){return {}}"
        b'function L(e){const t=e.gatewayUrl??"";return{mode:"remote",host:"",token:e.token??"",'
        b"...K(e)&&!e.token?{grant:e.grant}:{},...typeof e.grantAt==\"number\"?{grantAt:e.grantAt}:{},"
        b'...t?{gatewayUrl:t}:{},nodeId:e.nodeId,e2e:e.e2e,rendezvous:e.rendezvous||M,...N(e)}}'
    ),
}


class AsarTests(unittest.TestCase):
    def test_round_trip(self):
        a = make_tree(FILES)
        raw = asar.build(a)
        asar.verify_bytes(raw)
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".asar", delete=False) as fh:
            fh.write(raw)
            name = fh.name
        try:
            b = asar.load(name)
        finally:
            Path(name).unlink()
        self.assertEqual(a.contents, b.contents)

    def test_verify_rejects_corruption(self):
        raw = bytearray(asar.build(make_tree(FILES)))
        raw[-1] ^= 0xFF
        with self.assertRaises(ValueError):
            asar.verify_bytes(bytes(raw))


if __name__ == "__main__":
    unittest.main()