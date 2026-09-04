#!/usr/bin/env python3
"""macOS counterpart to linux/collect_shared_libs.py and windows/
collect_dlls.py: resolves the full dylib dependency closure for one
or more seed dylibs/executables via recursive `otool -L`, copies every
resolved dylib into an output directory, and rewrites each dylib's
own install name and every reference to it (via `install_name_tool`)
to `@rpath/<name>` -- the standard way a relocatable macOS .app bundle
is built. build_macos.sh sets an @executable_path-relative rpath on
the bundle's own Python interpreter so those @rpath references
resolve to Contents/Frameworks at runtime.

A denylist excludes dylibs the host macOS must supply instead of the
bundle: system frameworks and libSystem.

Usage:
    collect_dylibs.py --out DIR SEED [SEED ...]
"""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

_DENYLIST_PATTERNS = [
    r"^/usr/lib/",
    r"^/System/Library/Frameworks/",
    r"^/System/Library/PrivateFrameworks/",
]
_DENYLIST_RE = re.compile("(" + "|".join(_DENYLIST_PATTERNS) + ")")

_OTOOL_LINE_RE = re.compile(r"^\s*(\S+)\s+\(compatibility version")
_LC_RPATH_RE = re.compile(r"^\s*path\s+(\S+)\s+\(offset", re.MULTILINE)


def _dependencies(path):
    """Direct dylib dependencies of `path`, excluding its own install
    name (the first line of otool -L's output)."""
    result = subprocess.run(["otool", "-L", str(path)], capture_output=True, text=True)
    lines = result.stdout.splitlines()[1:]
    deps = []
    for i, line in enumerate(lines):
        match = _OTOOL_LINE_RE.match(line)
        if not match:
            continue
        if i == 0:
            id_result = subprocess.run(["otool", "-D", str(path)], capture_output=True, text=True)
            id_lines = [l for l in id_result.stdout.splitlines() if l.strip() and not l.endswith(":")]
            if id_lines and id_lines[0].strip() == match.group(1):
                continue
        deps.append(match.group(1))
    return deps


def _own_rpaths(path):
    """The LC_RPATH entries embedded in `path`'s own Mach-O load
    commands. A Homebrew-built dylib commonly references a sibling
    formula's own lib/ directory this way, not just its own
    directory."""
    result = subprocess.run(["otool", "-l", str(path)], capture_output=True, text=True)
    return [Path(m.group(1)) for m in _LC_RPATH_RE.finditer(result.stdout)]


def _resolve(name, loader_path, rpaths):
    """Resolves an @rpath/@loader_path/@executable_path-relative name
    against the file's own directory and its own LC_RPATH entries;
    absolute paths pass through unchanged."""
    if name.startswith(("@rpath/", "@loader_path/", "@executable_path/")):
        basename = name.split("/")[-1]
        for directory in [loader_path, *rpaths]:
            candidate = directory / basename
            if candidate.is_file():
                return candidate
        return None
    return Path(name)


def collect_closure(seeds):
    """Returns {resolved_path: original_dependency_name}, denylisted
    entries excluded."""
    closure = {}
    queue = [Path(s).resolve() for s in seeds]
    seen = set()

    while queue:
        current = queue.pop()
        if current in seen or not current.is_file():
            continue
        seen.add(current)

        rpaths = _own_rpaths(current)
        for name in _dependencies(current):
            if _DENYLIST_RE.match(name):
                continue
            resolved = _resolve(name, current.parent, rpaths)
            if resolved is None or not resolved.is_file():
                print(f"warning: could not resolve {name} (depended on by {current.name})", file=sys.stderr)
                continue
            resolved = resolved.resolve()
            if resolved not in closure:
                closure[resolved] = name
            queue.append(resolved)

    return closure


def _rewrite_install_names(out_dir, collected_names):
    """Rewrites each collected dylib's own install name to
    @rpath/<name>, then every other collected dylib's reference to it
    the same way, then re-signs with a fresh ad-hoc signature (
    install_name_tool invalidates whatever Homebrew originally
    applied)."""
    dylib_paths = sorted(out_dir.glob("*.dylib"))
    for dylib in dylib_paths:
        subprocess.run(["install_name_tool", "-id", f"@rpath/{dylib.name}", str(dylib)], check=True)

    for dylib in dylib_paths:
        for name in collected_names:
            basename = Path(name).name
            old_ref = name
            subprocess.run(
                ["install_name_tool", "-change", old_ref, f"@rpath/{basename}", str(dylib)],
                capture_output=True,
            )

    for dylib in dylib_paths:
        subprocess.run(["codesign", "--force", "--sign", "-", str(dylib)], capture_output=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="Output directory for resolved dylibs")
    parser.add_argument("seeds", nargs="+", help="Seed dylibs/executables to resolve from")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    closure = collect_closure(args.seeds)

    for resolved, original_name in closure.items():
        dest = out_dir / resolved.name
        shutil.copy2(resolved, dest, follow_symlinks=True)
        dest.chmod(0o755)

    _rewrite_install_names(out_dir, list(closure.values()))

    print(f"Collected {len(closure)} dylibs into {out_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
