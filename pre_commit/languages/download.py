from __future__ import annotations

import contextlib
import hashlib
import os.path
import platform
import stat
from base64 import standard_b64decode as b64decode
from base64 import standard_b64encode as b64encode
from dataclasses import dataclass
from os import chmod
from pathlib import Path
from pathlib import PurePath
from types import MappingProxyType
from typing import Final
from typing import Generator
from typing import Iterator
from typing import Mapping
from typing import Protocol
from typing import Sequence
from typing import Type
from urllib.parse import urlparse
from urllib.request import urlopen

from pre_commit import lang_base
from pre_commit.envcontext import envcontext
from pre_commit.envcontext import PatchesT
from pre_commit.envcontext import Var
from pre_commit.prefix import Prefix

ENVIRONMENT_DIR = 'download'
get_default_version = lang_base.basic_get_default_version
run_hook = lang_base.basic_run_hook
IO_BUF_SIZE = 4096


def get_env_patch(target_dir: str) -> PatchesT:
    return (
        ('PATH', (target_dir, os.pathsep, Var('PATH'))),
    )


@contextlib.contextmanager
def in_env(prefix: Prefix, version: str) -> Generator[None, None, None]:
    envdir = lang_base.environment_dir(prefix, ENVIRONMENT_DIR, version)
    with envcontext(get_env_patch(envdir)):
        yield


class Platform:
    OS: Final[Mapping[str, str]] = MappingProxyType({
        'Linux': 'linux',
        'Darwin': 'darwin',
        'Windows': 'windows',
        'DragonFly': 'dragonfly',
        'FreeBSD': 'freebsd',
    })
    CPU: Final[Mapping[str, str]] = MappingProxyType({
        'aarch64': 'arm64',
        'aarch64_be': 'arm64be',
        'arm': 'arm',
        'i386': '386',
        'i686': '386',
        'x86_64': 'amd64',
        'AMD64': 'amd64',
        'ppc': 'ppc',
        'ppc64': 'ppc64',
        'ppc64le': 'ppc64le',
    })

    def __init__(self, value: str) -> None:
        self.__value = value
        os, cpu = self.parts
        if os not in self.OS.values():
            raise ValueError(f"invalid operating system `{os}`, \
valid values are: {','.join(self.OS.values())}")
        if cpu not in self.CPU.values():
            raise ValueError(f"invalid CPU `{cpu}`, \
valid values are: {','.join(self.CPU.values())}")

    @property
    def parts(self) -> tuple[str, str]:
        first, second = self.value.split('/', 1)
        return (first, second)

    @property
    def os(self) -> str:
        os, _ = self.parts
        return os

    @property
    def cpu(self) -> str:
        _, cpu = self.parts
        return cpu

    @property
    def value(self) -> str:
        return self.__value

    @classmethod
    def host(cls: Type[Platform]) -> Platform:
        os = cls.OS[platform.system()]
        cpu = cls.CPU[platform.machine()]
        return cls(f'{os}/{cpu}')

    def __str__(self) -> str:
        return f'{self.os}/{self.cpu}'

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Platform):
            return False
        return other.os == self.os and other.cpu == self.cpu


class ChecksumMismatchError(ValueError):
    def __init__(
        self, *, expected: str, actual: str,
        message: str = 'checksum mismatch',
    ):
        self.__expected = expected
        self.__actual = actual
        self.__message = message

    @property
    def expected(self) -> str:
        return self.__expected

    @property
    def actual(self) -> str:
        return self.__actual

    @property
    def message(self) -> str:
        return self.__message

    def __str__(self) -> str:
        return f'''{self.__message}:
 - expected: {self.expected}
 - actual  : {self.actual}
'''


class HasBinaryRead(Protocol):
    def read(self, __size: int = -1) -> bytes | None: ...


class SRI:
    def __init__(self, value: str):
        self.__value = value
        self.__algorithm, self.__checksum = self.value.split('-', 1)
        if self.algorithm not in hashlib.algorithms_available:
            raise ValueError(f"`{self.algorithm}` is not available, \
choose one of: {','.join(hashlib.algorithms_available)}`")

        if b64encode(b64decode(self.checksum)).decode('utf-8') !=\
                self.checksum:
            raise ValueError('Invalid checksum string, \
the checksum string has to be encoded in base64.')

        hasher = hashlib.new(self.algorithm)

        checksum_len = len(b64decode(self.checksum))
        if checksum_len != hasher.digest_size:
            raise ValueError(
                f'Invalid checksum string length of {checksum_len} for \
{self.algorithm}, expected {hasher.digest_size}',
            )

    @property
    def value(self) -> str:
        return self.__value

    @property
    def algorithm(self) -> str:
        return self.__algorithm

    @property
    def checksum(self) -> str:
        return self.__checksum

    def __str__(self) -> str:
        return self.value

    def check(self, io: HasBinaryRead, chunk: int = 4096) -> Iterator[bytes]:
        hasher = hashlib.new(self.algorithm)
        while buffer := io.read(chunk):
            hasher.update(buffer)
            yield buffer
        digest = b64encode(hasher.digest()).decode('utf-8)')
        if digest != self.checksum:
            raise ChecksumMismatchError(
                expected=self.checksum,
                actual=digest,
            )


@dataclass(frozen=True)
class URI:
    value: str

    def __post_init__(self) -> None:
        url = urlparse(self.value)
        if not all([url.scheme, url.netloc]):
            raise ValueError(f'Invalid URI: {self.value}')

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Metadata:
    value: str

    @property
    def parts(self) -> tuple[str, str, str, str]:
        first, second, third, fourth = self.value.splitlines()
        return (first, second, third, fourth)

    @property
    def platform(self) -> Platform:
        platform, _, _, _ = self.parts
        return Platform(platform)

    @property
    def sri(self) -> SRI:
        _, sri, _, _ = self.parts
        return SRI(sri)

    @property
    def uri(self) -> URI:
        _, _, uri, _ = self.parts
        return URI(uri)

    @property
    def filename(self) -> PurePath:
        _, _, _, path = self.parts
        return PurePath(path)


def download(uri: URI, sri: SRI, filename: Path) -> None:
    with urlopen(str(uri)) as ws:
        with filename.open('wb') as fp:
            for buffer in sri.check(ws):
                fp.write(buffer)
            fp.flush()
    chmod(filename, stat.S_IRUSR | stat.S_IXUSR)


def install_environment(
        prefix: Prefix,
        version: str,
        additional_dependencies: Sequence[str],
) -> None:
    host = Platform.host()
    for dep in additional_dependencies:
        m = Metadata(dep)
        if host == m.platform:
            envdir = Path(
                lang_base.environment_dir(
                    prefix, ENVIRONMENT_DIR,
                    version,
                ),
            )
            envdir.mkdir(parents=True, exist_ok=True)
            filename = Path(m.filename)
            download(m.uri, m.sri, envdir / filename)
            srisum = envdir / 'health.srisum'
            with srisum.open('w', encoding='utf8') as stream:
                stream.write(f'{m.sri}  {filename}\n')
            return
    raise KeyError(f'Failed to find platform `{host}` in \
`additional_dependencies`: {additional_dependencies}')


def health_check(prefix: Prefix, version: str) -> str | None:
    envdir = Path(lang_base.environment_dir(prefix, ENVIRONMENT_DIR, version))
    srisum = envdir / 'health.srisum'
    with srisum.open(encoding='utf8') as stream:
        for line in stream:
            sri_str, filepath = line.strip().split(' ', 1)
            sri_str = sri_str.strip()
            filepath = filepath.strip()
            filename = envdir / filepath
            sri = SRI(sri_str)
            with filename.open('rb') as fp:
                try:
                    for _ in sri.check(fp):
                        pass
                except ChecksumMismatchError as err:
                    return f'{filepath} {err}\
Please reinstall the Download environment'
    return None
