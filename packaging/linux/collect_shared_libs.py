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


def collect_closure(seeds, walk_only_seeds=()):
    """Returns {library_name: resolved_path}, denylisted entries
    excluded. Includes `seeds` themselves, not just their discovered
    dependencies: a seed only ends up copied into the bundle today if
    something else in the seed set happens to link against it
    directly, so anything seeded specifically because nothing else in
    the set depends on it would otherwise be silently missing from
    the output (found and fixed for exactly this reason in the macOS
    collector's own librsvg seed). `walk_only_seeds` are walked for
    their own dependencies the same way, but never added to the
    output themselves -- for a seed that's only here to make sure its
    *dependencies* get discovered, because the seed file itself is
    already being copied to some other, more specific destination by
    the caller (confirmed necessary directly: without this
    distinction, gdk-pixbuf's loader plugins -- seeded so libpng/
    libjpeg/etc. get discovered, but already copied to their own
    gdk-pixbuf-2.0/loaders/ subdirectory separately -- ended up
    duplicated uselessly into this script's own flat output too). If
    a walk-only seed also turns out to be some other file's regular
    dependency, it's still collected normally through that path --
    this only suppresses adding the seed *as a seed*."""
    closure = {}
    walk_only_paths = {Path(s).resolve() for s in walk_only_seeds}
    queue = list(seeds) + list(walk_only_seeds)
    seen_paths = set()

    while queue:
        current = queue.pop()
        current_path = Path(current).resolve()
        if current_path in seen_paths or not current_path.is_file():
            continue
        seen_paths.add(current_path)
        # Path(current).name, not current_path.name: the pre-resolution
        # name matches the soname convention _ldd_dependencies uses for
        # a discovered dependency (ldd itself reports a soname-named
        # symlink as the resolved path, not the further-versioned real
        # file it may itself point to), whereas resolving symlinks
        # first can land on that real file's own longer name instead.
        # Mismatching between the two produced a real, measured
        # duplicate here: the same library ending up copied under both
        # names, e.g. libXau.so.6 (correct) and libXau.so.6.0.0 (the
        # resolved real file, unnecessary and unreferenced under that
        # name by anything).
        seed_name = Path(current).name
        if seed_name not in closure and current_path not in walk_only_paths:
            closure[seed_name] = str(current_path)

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
    parser.add_argument(
        "--walk-only", action="append", default=[], dest="walk_only",
        help="Seed to walk for dependencies without copying the seed itself (repeatable) -- "
             "for a seed already copied to its own destination by the caller",
    )
    parser.add_argument("seeds", nargs="+", help="Seed libraries/executables to resolve from")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    closure = collect_closure(args.seeds, args.walk_only)

    for name, resolved in sorted(closure.items()):
        dest = out_dir / name
        shutil.copy2(resolved, dest, follow_symlinks=True)
        dest.chmod(0o755)

    print(f"Collected {len(closure)} shared libraries into {out_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
