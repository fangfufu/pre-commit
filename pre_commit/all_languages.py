from __future__ import annotations

from pre_commit.lang_base import Language
from pre_commit.languages import conda
from pre_commit.languages import coursier
from pre_commit.languages import dart
from pre_commit.languages import docker
from pre_commit.languages import docker_image
from pre_commit.languages import dotnet
from pre_commit.languages import download
from pre_commit.languages import fail
from pre_commit.languages import golang
from pre_commit.languages import haskell
from pre_commit.languages import lua
from pre_commit.languages import node
from pre_commit.languages import perl
from pre_commit.languages import pygrep
from pre_commit.languages import python
from pre_commit.languages import r
from pre_commit.languages import ruby
from pre_commit.languages import rust
from pre_commit.languages import script
from pre_commit.languages import swift
from pre_commit.languages import system


languages: dict[str, Language] = {
    'conda': conda,
    'coursier': coursier,
    'dart': dart,
    'docker': docker,
    'docker_image': docker_image,
    'dotnet': dotnet,
    'download': download,
    'fail': fail,
    'golang': golang,
    'haskell': haskell,
    'lua': lua,
    'node': node,
    'perl': perl,
    'pygrep': pygrep,
    'python': python,
    'r': r,
    'ruby': ruby,
    'rust': rust,
    'script': script,
    'swift': swift,
    'system': system,
    # TODO: fully deprecate `python_venv`
    'python_venv': python,
}
language_names = sorted(languages)
