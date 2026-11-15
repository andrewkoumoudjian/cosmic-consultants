import functools
import gzip
import http.client
import importlib.util
import tempfile
import threading
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "serve_planner.py"
spec = importlib.util.spec_from_file_location("serve_planner", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class QuietHandler(module.Handler):
    def log_message(self, *args):
        pass


class PreviewHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.raw = b"Synthetic compiled asset.\n" * 20
        self.gz = gzip.compress(self.raw, mtime=0)
        # Opaque sidecar stand-in: these tests check selection and transport,
        # not the correctness of the external Brotli compressor.
        self.br = b"synthetic-brotli-wire-fixture"
        (root / "planner.html").write_bytes(self.raw)
        (root / "planner.html.gz").write_bytes(self.gz)
        (root / "planner.html.br").write_bytes(self.br)
        self.server = module.Server(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(root)))
        self.thread = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=0.01), daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, encoding=None, extra=None, method="GET"):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        try:
            connection.putrequest(method, "/planner.html", skip_accept_encoding=True)
            if encoding is not None:
                connection.putheader("Accept-Encoding", encoding)
            for key, value in (extra or {}).items():
                connection.putheader(key, value)
            connection.endheaders()
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_q_zero_never_selects_refused_brotli(self):
        status, headers, body = self.request("br;q=0, gzip;q=1")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("Content-Encoding"), "gzip")
        self.assertEqual(gzip.decompress(body), self.raw)

    def test_highest_acceptable_quality_wins(self):
        _, headers, body = self.request("br;q=0.2, gzip;q=0.9, identity;q=0.1")
        self.assertEqual(headers.get("Content-Encoding"), "gzip")
        self.assertEqual(body, self.gz)

    def test_identity_can_be_preferred_explicitly(self):
        _, headers, body = self.request("br;q=0.5, gzip;q=0.5, identity;q=1")
        self.assertNotIn("Content-Encoding", headers)
        self.assertEqual(body, self.raw)

    def test_empty_and_absent_encoding_use_identity(self):
        for encoding in (None, ""):
            with self.subTest(encoding=encoding):
                status, headers, body = self.request(encoding)
                self.assertEqual(status, 200)
                self.assertNotIn("Content-Encoding", headers)
                self.assertEqual(body, self.raw)

    def test_wildcard_and_specific_refusal(self):
        _, headers, body = self.request("*;q=1, br;q=0, identity;q=0")
        self.assertEqual(headers.get("Content-Encoding"), "gzip")
        self.assertEqual(body, self.gz)
        status, headers, body = self.request("*;q=0")
        self.assertEqual((status, body), (406, b""))

    def test_identity_fallback_when_compressions_refused(self):
        status, headers, body = self.request("br;q=0, gzip;q=0")
        self.assertEqual(status, 200)
        self.assertNotIn("Content-Encoding", headers)
        self.assertEqual(body, self.raw)

    def test_missing_sidecars_fall_back_or_refuse(self):
        root = Path(self.temp.name)
        (root / "planner.html.br").unlink()
        (root / "planner.html.gz").unlink()
        status, headers, body = self.request("br, gzip")
        self.assertEqual((status, body), (200, self.raw))
        self.assertNotIn("Content-Encoding", headers)
        self.assertEqual(self.request("gzip, identity;q=0")[0], 406)

    def test_malformed_weights_and_duplicate_refusal(self):
        for encoding in ("br;q=NaN", "br;q=2", "br;q=-1", "br;q=nope", "br;q=0, br;q=1"):
            with self.subTest(encoding=encoding):
                status, headers, body = self.request(encoding + ", gzip;q=1")
                self.assertEqual((status, body), (200, self.gz))
                self.assertEqual(headers.get("Content-Encoding"), "gzip")

    def test_each_byte_representation_has_a_distinct_etag(self):
        tags = []
        for encoding, expected in (("identity", self.raw), ("gzip", self.gz), ("br", self.br)):
            status, headers, body = self.request(encoding)
            self.assertEqual(status, 200)
            self.assertEqual(body, expected)
            tags.append(headers["ETag"])
        self.assertEqual(len(set(tags)), 3)

    def test_conditionals_are_selected_variant_specific_and_keep_vary(self):
        _, identity, _ = self.request("identity")
        status, compressed, body = self.request("gzip", {"If-None-Match": identity["ETag"]})
        self.assertEqual(status, 200)
        self.assertEqual(body, self.gz)
        status, headers, body = self.request("gzip", {"If-None-Match": compressed["ETag"]})
        self.assertEqual((status, body), (304, b""))
        self.assertEqual(headers.get("Vary"), "Accept-Encoding")
        self.assertEqual(headers["ETag"], compressed["ETag"])

    def test_conditional_tag_lists_and_weak_comparison(self):
        _, headers, _ = self.request("gzip")
        status, _, body = self.request("gzip", {"If-None-Match": '"other", W/' + headers["ETag"]})
        self.assertEqual((status, body), (304, b""))
        self.assertEqual(self.request("identity", {"If-None-Match": "*"})[0], 304)

    def test_head_preserves_compressed_headers_without_body(self):
        status, headers, body = self.request("gzip", method="HEAD")
        self.assertEqual((status, body), (200, b""))
        self.assertEqual(headers["Content-Encoding"], "gzip")
        self.assertEqual(int(headers["Content-Length"]), len(self.gz))


if __name__ == "__main__":
    unittest.main()
