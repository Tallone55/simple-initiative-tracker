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
    own_name = _own_install_name(path)
    deps = []
    for i, line in enumerate(lines):
        match = _OTOOL_LINE_RE.match(line)
        if not match:
            continue
        if i == 0 and match.group(1) == own_name:
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


def _own_install_name(path):
    """The file's own compiled install name (via `otool -D`) -- the
    exact string other files reference it by in their own load
    commands -- or None if it doesn't have one (e.g. an executable
    rather than a dylib)."""
    result = subprocess.run(["otool", "-D", str(path)], capture_output=True, text=True)
    lines = [l for l in result.stdout.splitlines() if l.strip() and not l.endswith(":")]
    return lines[0].strip() if lines else None


def collect_closure(seeds, walk_only_seeds=()):
    """Returns {resolved_path: original_dependency_name}, denylisted
    entries excluded. Includes `seeds` themselves, not just their
    discovered dependencies: a seed only ends up copied into the
    bundle today if something else in the seed set happens to link
    against it directly (confirmed directly -- this silently failed
    for librsvg, seeded specifically because nothing else in this set
    depends on it, so it was correctly walked for its own
    dependencies but never itself copied, since the copy step in
    main() only ever iterated over discovered dependencies, not
    seeds). Recorded under the seed's own compiled install name where
    it has one, matching how a discovered dependency is recorded --
    that's the exact string another file's load commands would
    reference it by, which a bare filename isn't guaranteed to be.
    `walk_only_seeds` are walked for their own dependencies the same
    way, but never added to the output themselves -- for a seed
    that's only here to make sure its *dependencies* get discovered,
    because the seed file itself is already being copied to some
    other, more specific destination by the caller (confirmed
    necessary directly: the gi/cairo Python extension modules and the
    bundled interpreter binary are each already copied elsewhere by
    build_macos.sh -- as part of the whole gi/cairo package copy, and
    to Resources/python/bin/, respectively -- so seeding them as
    regular seeds here would duplicate them uselessly into Frameworks
    too, the same bug just fixed for librsvg). If a walk-only seed
    also turns out to be some other file's regular dependency, it's
    still collected normally through that path -- this only
    suppresses adding the seed *as a seed*."""
    closure = {}
    walk_only_paths = {Path(s).resolve() for s in walk_only_seeds}
    queue = [Path(s).resolve() for s in seeds] + [Path(s).resolve() for s in walk_only_seeds]
    seen = set()

    while queue:
        current = queue.pop()
        if current in seen or not current.is_file():
            continue
        seen.add(current)
        if current not in closure and current not in walk_only_paths:
            closure[current] = _own_install_name(current) or current.name

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
    parser.add_argument(
        "--walk-only", action="append", default=[], dest="walk_only",
        help="Seed to walk for dependencies without copying the seed itself (repeatable) -- "
             "for a seed already copied to its own destination by the caller",
    )
    parser.add_argument("seeds", nargs="+", help="Seed dylibs/executables to resolve from")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    closure = collect_closure(args.seeds, args.walk_only)

    for resolved, original_name in closure.items():
        dest = out_dir / resolved.name
        shutil.copy2(resolved, dest, follow_symlinks=True)
        dest.chmod(0o755)

    _rewrite_install_names(out_dir, list(closure.values()))

    print(f"Collected {len(closure)} dylibs into {out_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
