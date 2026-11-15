#!/usr/bin/env python3
"""Serve only a compiled planner site on loopback, with precompressed assets."""
import argparse
import functools
import gzip
import re
import shutil
import subprocess
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

EXTENSIONS = ('.html', '.json', '.bin', '.js', '.mjs', '.css')


def encoding_qualities(value):
    """Parse weights conservatively; a malformed or duplicate refusal stays refused."""
    qualities = {}
    for item in value.split(','):
        parts = item.strip().lower().split(';')
        name = parts[0].strip()
        if not name:
            continue
        quality = 1.0
        for parameter in parts[1:]:
            key, _, weight = parameter.strip().partition('=')
            if key.strip() == 'q':
                weight = weight.strip()
                quality = float(weight) if re.fullmatch(r'(?:0(?:\.\d{0,3})?|1(?:\.0{0,3})?)', weight) else 0.0
        qualities[name] = min(qualities.get(name, quality), quality)
    return qualities


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        import sys
        exc = sys.exc_info()[1]
        if isinstance(exc, (BrokenPipeError, ConnectionResetError)):
            return
        super().handle_error(request, client_address)


class Handler(SimpleHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def send_head(self):
        path = Path(self.translate_path(self.path))
        if not path.is_file():
            return super().send_head()
        qualities = encoding_qualities(','.join(self.headers.get_all('Accept-Encoding', [])))
        identity_quality = qualities.get('identity', 0.0 if qualities.get('*') == 0 else 1.0)
        candidates = []
        for encoding, suffix in (('br', '.br'), ('gzip', '.gz'), ('identity', '')):
            candidate = path.with_name(path.name + suffix)
            quality = identity_quality if encoding == 'identity' else qualities.get(encoding, qualities.get('*', 0.0))
            if quality > 0 and candidate.is_file():
                candidates.append((quality, encoding, candidate))
        if not candidates:
            self.send_response(406)
            self.send_header('Vary', 'Accept-Encoding')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return None
        # max keeps the first candidate on ties: Brotli, gzip, then identity.
        _, encoding, selected = max(candidates, key=lambda candidate: candidate[0])
        st = selected.stat()
        etag = f'"{encoding}-{st.st_mtime_ns:x}-{st.st_size:x}"'
        cache_ctrl = 'no-cache' if path.suffix == '.html' else 'public, max-age=300'
        tags = re.findall(r'(?:W/)?"[^"\r\n]*"|\*', ','.join(self.headers.get_all('If-None-Match', [])))
        if any(tag == '*' or tag.removeprefix('W/') == etag for tag in tags):
            self.send_response(304)
            self.send_header('Vary', 'Accept-Encoding')
            self.send_header('ETag', etag)
            self.send_header('Cache-Control', cache_ctrl)
            self.end_headers()
            return None
        f = selected.open('rb')
        self.send_response(200)
        self.send_header('Content-Type', self.guess_type(str(path)))
        if encoding != 'identity':
            self.send_header('Content-Encoding', encoding)
        self.send_header('Vary', 'Accept-Encoding')
        self.send_header('ETag', etag)
        self.send_header('Cache-Control', cache_ctrl)
        self.send_header('Content-Length', str(st.st_size))
        self.end_headers()
        return f


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--port', type=int, default=4184)
    args = parser.parse_args()
    root = args.directory.resolve()
    if not (root / 'planner.html').is_file():
        raise SystemExit('Expected a compiled planner site.')
    brotli_bin = shutil.which('brotli')
    raw = gz_wire = br_wire = 0
    for p in root.rglob('*'):
        if p.suffix not in EXTENSIONS:
            continue
        b = p.read_bytes()
        gz = p.with_name(p.name + '.gz')
        if not gz.exists() or gz.stat().st_mtime < p.stat().st_mtime:
            gz.write_bytes(gzip.compress(b, compresslevel=6, mtime=0))
        if brotli_bin:
            br = p.with_name(p.name + '.br')
            if not br.exists() or br.stat().st_mtime < p.stat().st_mtime:
                subprocess.run([brotli_bin, '-f', '-q', '5', str(p), '-o', str(br)], check=True)
            br_wire += br.stat().st_size
        raw += len(b)
        gz_wire += gz.stat().st_size
    msg = f'Serving compiled site only: {raw:,} raw bytes -> {gz_wire:,} gzip'
    if brotli_bin:
        msg += f', {br_wire:,} brotli'
    print(f'{msg} bytes, loopback port {args.port}', flush=True)
    Server(('127.0.0.1', args.port), functools.partial(Handler, directory=str(root))).serve_forever()


if __name__ == '__main__':
    main()

