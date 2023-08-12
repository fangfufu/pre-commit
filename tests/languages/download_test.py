from __future__ import annotations

import _thread as thread
import platform
import stat
from http.server import BaseHTTPRequestHandler
from http.server import HTTPServer
from os import chmod
from pathlib import Path
from typing import Iterator

import pytest

import pre_commit.constants as C
from pre_commit import lang_base
from pre_commit.languages import download
from pre_commit.languages.download import ChecksumMismatchError
from pre_commit.languages.download import ENVIRONMENT_DIR
from pre_commit.languages.download import get_default_version
from pre_commit.prefix import Prefix
from testing.language_helpers import run_language

shellscript = b'#!/bin/sh\necho hello\nexit 123'
shell_checksum = 'oRJkj6Cr8nWIivZ9d3W+rVZt/aSW1l9YtxSVh+GtIHM='
batch_script = b'@echo off\necho hello\nexit 123'
batch_checksum = 'L63Nefq+fKVIm24IKqlcqbJmc1rrJD3dKhIvutFK+IA='
if platform.system() == 'Windows':
    correct_checksum = batch_checksum
else:
    correct_checksum = shell_checksum

healthy_dependencies = [
    f"""linux/amd64
sha256-{shell_checksum}
http://127.0.0.1:5555
test.bat""",
    f"""windows/amd64
sha256-{batch_checksum}
http://127.0.0.1:5555
test.bat""",
]

deps_invalid_length = [
    """linux/amd64
sha256-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
http://127.0.0.1:5555
test.bat""",
    """windows/amd64
sha256-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
http://127.0.0.1:5555
test.bat""",
]

deps_wrong_checksum = [
    """linux/amd64
sha256-oRJkj6Cr8nWIivZ9d4W+rVZt/aSW1l9YtxSVh+GtIHM=
http://127.0.0.1:5555
test.bat""",
    """windows/amd64
sha256-L63Nefq+fKVIm25IKqlcqbJmc1rrJD3dKhIvutFK+IA=
http://127.0.0.1:5555
test.bat""",
]


class HTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        if platform.system() == 'Windows':
            self.wfile.write(batch_script)
        else:
            self.wfile.write(shellscript)


class server():
    def __init__(self):
        self.httpd = HTTPServer(('localhost', 5555), HTTPRequestHandler)

    def start(self):
        thread.start_new_thread(self.httpd.serve_forever, ())

    def stop(self):
        self.httpd.shutdown()


@pytest.fixture
def download_dir(tmpdir):
    with tmpdir.as_cwd():
        prefix = tmpdir.join('prefix').ensure_dir()
        prefix = Prefix(str(prefix))
        yield prefix, tmpdir


def test_download_unhealthy_download(download_dir: Iterator[Prefix]) -> None:
    """
    This check against various errors during download.
    """
    prefix, _ = download_dir
    http = server()
    http.start()

    # This checks against invalid SRI string.
    try:
        download.install_environment(prefix, C.DEFAULT, deps_invalid_length)
    except ValueError as err:
        assert err.args[0] == 'Invalid checksum string length of 33 \
for sha256, expected 32'

    # This checks against mismatched checksum
    try:
        download.install_environment(prefix, C.DEFAULT, deps_wrong_checksum)
    except ChecksumMismatchError as err:
        assert err.actual == correct_checksum
    http.stop()


def test_download_healthy_health_check(download_dir: Iterator[Prefix]) -> None:
    """
    This performs a normal download and on-disk health check.
    """
    prefix, _ = download_dir
    http = server()
    http.start()
    download.install_environment(prefix, C.DEFAULT, healthy_dependencies)
    http.stop()
    assert download.health_check(prefix, C.DEFAULT) is None


def test_download_unhealthy_health_check(
    download_dir: Iterator[Prefix],
) -> None:
    """
    This is for simulating changes to pre-commit cache,
    e.g. unexpected changes to the on-disk cache.
    """
    prefix, _ = download_dir
    envdir = Path(
        lang_base.environment_dir(
            prefix, ENVIRONMENT_DIR,
            get_default_version(),
        ),
    )
    script = envdir / 'test.bat'
    http = server()
    http.start()
    download.install_environment(prefix, C.DEFAULT, healthy_dependencies)
    chmod(script, stat.S_IRUSR | stat.S_IWUSR)
    with script.open('w', encoding='utf8') as stream:
        stream.write('xxxxxxx')
    http.stop()
    assert download.health_check(prefix, C.DEFAULT) == \
        f'''test.bat checksum mismatch:
 - expected: {correct_checksum}
 - actual  : e3DTq0x2QVQuHxWLRY7q58+3vbgV1BEMxheLr8/fQ/g=
Please reinstall the Download environment'''


def test_download_healthy_script_run(tmp_path: Path) -> None:
    """
    This is for simulating a normal script run.
    """
    http = server()
    http.start()
    ret = run_language(
        tmp_path,
        download,
        'test.bat',
        deps=healthy_dependencies,
    )
    http.stop()
    assert ret == (123, b'hello\n')


def test_download_checksum_mismatch_script_run(tmp_path: Path) -> None:
    """
    This is for simulating checksum mismatch during download,
    e.g. content corruption during download
    """
    http = server()
    http.start()
    try:
        run_language(
            tmp_path,
            download,
            'test.bat',
            deps=deps_wrong_checksum,
        )
    except ChecksumMismatchError as err:
        assert err.actual == correct_checksum
    http.stop()
