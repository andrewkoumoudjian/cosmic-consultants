import functools
import gzip
import http.client
import importlib.util
import os
import shutil
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
        return self.request_from(self.server, encoding, extra, method)

    def request_from(self, server, encoding=None, extra=None, method="GET"):
        connection = http.client.HTTPConnection(*server.server_address, timeout=3)
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

    def test_stale_sidecars_are_skipped_after_a_rebuild(self):
        root = Path(self.temp.name)
        status, headers, body = self.request("gzip")
        self.assertEqual((status, headers.get("Content-Encoding"), body), (200, "gzip", self.gz))

        rebuilt = b"Rebuilt compiled asset.\n" * 20
        (root / "planner.html").write_bytes(rebuilt)
        newer = (root / "planner.html.gz").stat().st_mtime_ns + 1_000_000_000
        os.utime(root / "planner.html", ns=(newer, newer))

        for encoding in ("gzip, identity", "br, identity"):
            with self.subTest(encoding=encoding):
                status, headers, body = self.request(encoding)
                self.assertEqual((status, body), (200, rebuilt))
                self.assertNotIn("Content-Encoding", headers)

        status, headers, body = self.request("gzip;q=1, identity;q=0")
        self.assertEqual((status, body), (406, b""))

        fresh_gz = gzip.compress(rebuilt, mtime=0)
        (root / "planner.html.gz").write_bytes(fresh_gz)
        os.utime(root / "planner.html.gz", ns=(newer, newer))
        status, headers, body = self.request("gzip")
        self.assertEqual((status, headers.get("Content-Encoding"), body), (200, "gzip", fresh_gz))

    def test_sidecar_with_equal_mtime_stays_fresh(self):
        root = Path(self.temp.name)
        timestamp = (root / "planner.html.gz").stat().st_mtime_ns
        os.utime(root / "planner.html", ns=(timestamp, timestamp))
        status, headers, body = self.request("gzip")
        self.assertEqual((status, headers.get("Content-Encoding"), body), (200, "gzip", self.gz))

    def test_x_gzip_is_treated_as_gzip(self):
        status, headers, body = self.request("x-gzip;q=0.5, identity;q=0.1")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("Content-Encoding"), "gzip")
        self.assertEqual(body, self.gz)

    def test_startup_builds_a_fresh_brotli_sidecar(self):
        if shutil.which("brotli") is None:
            self.skipTest("brotli CLI is not installed")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "planner.html").write_bytes(b"Fresh startup asset.\n" * 20)
            totals = module.build_sidecars(root)
            br = root / "planner.html.br"
            self.assertIsNotNone(totals[3])
            self.assertGreater(totals[2], 0)
            self.assertGreaterEqual(br.stat().st_mtime_ns, (root / "planner.html").stat().st_mtime_ns)

            server = module.Server(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(root)))
            thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
            thread.start()
            try:
                status, headers, body = self.request_from(server, "br, gzip")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
            self.assertEqual(status, 200)
            self.assertEqual(headers.get("Content-Encoding"), "br")
            self.assertEqual(body, br.read_bytes())


if __name__ == "__main__":
    unittest.main()
