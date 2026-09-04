#!/usr/bin/env python3
"""Resolves the full shared-library dependency closure for one or more
seed libraries/executables, via recursive `ldd`, and copies every
resolved library into an output directory.

A denylist excludes libraries the host must supply instead of the
bundle: the loader/glibc family (must match the kernel/loader on the
target machine) and the graphics/X11/Wayland stack (must match the
host's GPU driver and display server).

Usage:
    collect_shared_libs.py --out DIR SEED [SEED ...]
"""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

_DENYLIST_PATTERNS = [
    # -- loader / glibc family --------------
    r"^ld-linux.*\.so",
    r"^ld64\.so",
    r"^libc\.so",
    r"^libm\.so",
    r"^libdl\.so",
    r"^libpthread\.so",
    r"^librt\.so",
    r"^libresolv\.so",
    r"^libnsl\.so",
    r"^libutil\.so",
    r"^libcrypt\.so",
    r"^libanl\.so",
    r"^linux-vdso\.so",
    # -- graphics stack --------------
    r"^libGL\.so",
    r"^libGLX.*\.so",
    r"^libGLdispatch\.so",
    r"^libGLESv\d.*\.so",
    r"^libEGL.*\.so",
    r"^libgbm\.so",
    r"^libdrm.*\.so",
    r"^libnvidia.*\.so",
    r"^libvulkan.*\.so",
    # -- X11 / Wayland --------------
    r"^libX11.*\.so",
    r"^libxcb.*\.so",
    r"^libXext\.so",
    r"^libXfixes\.so",
    r"^libXrender\.so",
    r"^libXcursor\.so",
    r"^libXi\.so",
    r"^libXrandr\.so",
    r"^libXcomposite\.so",
    r"^libXdamage\.so",
    r"^libXinerama\.so",
    r"^libwayland.*\.so",
    r"^libxkbcommon.*\.so",
]
_DENYLIST_RE = re.compile("(" + "|".join(_DENYLIST_PATTERNS) + ")")

_LDD_LINE_RE = re.compile(r"^\s*(\S+)\s+=>\s+(\S+)\s+\(0x[0-9a-fA-F]+\)\s*$")


def _ldd_dependencies(path):
    """Direct dependencies of `path` as {name: resolved_path}."""
    result = subprocess.run(["ldd", str(path)], capture_output=True, text=True)
    deps = {}
    for line in result.stdout.splitlines():
        match = _LDD_LINE_RE.match(line)
        if match:
            name, resolved = match.group(1), match.group(2)
            deps[name] = resolved
    return deps


def collect_closure(seeds):
    """Returns {library_name: resolved_path}, denylisted entries
    excluded."""
    closure = {}
    queue = list(seeds)
    seen_paths = set()

    while queue:
        current = queue.pop()
        current_path = Path(current).resolve()
        if current_path in seen_paths or not current_path.is_file():
            continue
        seen_paths.add(current_path)

        for name, resolved in _ldd_dependencies(current_path).items():
            if _DENYLIST_RE.match(name):
                continue
            if name not in closure:
                closure[name] = resolved
            queue.append(resolved)

    return closure


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="Output directory for resolved libraries")
    parser.add_argument("seeds", nargs="+", help="Seed libraries/executables to resolve from")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    closure = collect_closure(args.seeds)

    for name, resolved in sorted(closure.items()):
        dest = out_dir / name
        shutil.copy2(resolved, dest, follow_symlinks=True)
        dest.chmod(0o755)

    print(f"Collected {len(closure)} shared libraries into {out_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
