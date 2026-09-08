# Packaging

Builds Simple Initiative Tracker into all four of its distribution
formats: a Debian package (`.deb`), a portable Linux bundle
(`.tar.gz`), a portable Windows build (`.zip`), and a macOS app
bundle (`.app`).

## Layout

```
packaging/
  common/
    app_metadata.sh      -- packaging-only identity constants (display name, launcher command, bundle id)
    project_metadata.sh  -- reads $VERSION/$PKG_NAME/$DESCRIPTION/$MAINTAINER from pyproject.toml (single source of truth)
    signing.sh            -- optional GPG/Authenticode/Developer ID signing, gated on credential env vars
  net.mystive.sit.svg    -- app icon, shared by all four build scripts

  build_deb.sh            -- .deb          (Linux, run anywhere with dpkg-deb)
  build_linux_portable.sh -- .tar.gz       (Linux, run on the target arch)
  build_windows.sh        -- .zip          (Windows, MSYS2 MINGW64 shell only)
  build_macos.sh          -- .app          (macOS only)
  build_all.sh             -- runs whichever of the above are possible on this machine

  dist/    -- build output (gitignored)
  build/   -- build scratch space (gitignored)
```

## Quick start

```sh
./packaging/build_all.sh
```

This builds whatever your current machine can natively build, and
tells you plainly what it couldn't. **No single machine can build all
four** -- a real Windows build needs an actual Windows/MSYS2
toolchain, a real macOS `.app` needs actual macOS, and there's no
reliable way to cross-compile a GTK4 + GObject Introspection +
PyGObject application for a different OS than the one doing the
building. This isn't a shortcut particular to this project; it's why
GIMP, Inkscape, and every other cross-platform GTK app build their
releases on three separate machines (or CI runners), not one.

For all four archives from a single trigger, use the CI workflow
instead:

```sh
gh workflow run release.yml
```

(or trigger `.github/workflows/release.yml` from the Actions tab, or
by pushing a tag like `v1.0.0`). It builds each format on its own
native GitHub-hosted runner (`ubuntu-latest`, `windows-latest`,
`macos-latest`) and collects every artifact from the one run -- the
CI equivalent of running `build_all.sh` on three machines at once. A
tag push additionally publishes the four archives to a GitHub
Release.

## Running one format directly

Each script can also be run on its own, always from anywhere (they
resolve their own paths relative to the script's own location):

```sh
./packaging/build_deb.sh
./packaging/build_linux_portable.sh
./packaging/build_windows.sh   # from an MSYS2 MINGW64 shell
./packaging/build_macos.sh     # on macOS
```

Each prints its own prerequisites and exact output path when it runs
(and each script's own header comment has the full detail on what
gets bundled and why, including the one-time OS package it needs
beyond the project's own `uv sync --extra build` -- see "The
GIRepository-3.0 gap" below before running any of them for the first
time).

## Design notes

**Version, package name, description, and maintainer are all
single-sourced.** Every script reads them from `pyproject.toml` via
`common/project_metadata.sh` -- nothing hand-maintains a second copy
that can drift.

**Signing is optional and credential-gated, never fabricated.**
`common/signing.sh` provides GPG signing (`.deb`/`.tar.gz`), Windows
Authenticode, and macOS Developer ID codesigning + notarization
(`.app`), but every one of them only activates when its own
credential is present as an environment variable, and skips with a
clear message otherwise -- a GPG keypair, a Windows code-signing
certificate, and an Apple Developer ID are all things a human has to
obtain and supply (the latter two specifically require a paid CA
purchase or Apple Developer Program enrollment), not something a
build script can generate on its own. See the credential list at the
top of `.github/workflows/release.yml` for the exact secret names
each mechanism needs.

**The three non-.deb builds use PyInstaller.** Each script's own
`Analysis(...)`/`hooksconfig` is written directly in the shell script
that generates the `.spec` file, rather than hand-tracing the shared
library and stdlib dependency graph. This replaced an earlier,
hand-rolled dependency-closure walker (`ldd`/`objdump`/`otool`-based,
plus a runtime-exercise-based stdlib tracer) that produced somewhat
smaller bundles but needed a hand-maintained test harness to catch
lazy stdlib imports -- coverage that was only as good as what the
harness actually exercised, and failed silently (not with a build
warning) whenever a new code path went un-exercised. PyInstaller's own
static bytecode analysis finds these without needing a matching
harness to grow alongside the app, at the cost of a larger bundle
(roughly 140MB vs. roughly 50MB on Linux, measured directly) since its
bootloader `dlopen()`s libpython at runtime rather than shipping a
self-contained interpreter binary the way the previous approach did.

**Some of that gap has since been closed back up, on Linux only, and
only where it could be fully verified.** PyInstaller's own
`gi.repository.Gio` hook unconditionally bundles *every* plugin in the
build machine's `gio/modules/` directory, with no `hooksconfig` knob
to narrow it -- among them GIO's TLS backend and its two proxy-
resolution backends, which pull in a self-contained ~12MB cluster
(gnutls, OpenSSL, curl, LDAP, Kerberos, and their own transitive
dependencies) that nothing else in this app touches, since it has no
networking functionality anywhere in its own code. Confirmed directly
with `ldd` across the entire collected binary set, not assumed:
nothing outside that cluster references any library in it. Excluded
by exact filename in `build_linux_portable.sh`'s own `.spec`
generation, paired with a validation pass that checks the real, built
bundle for any dangling library reference after the exclusion --
which is what actually keeps this safe over time, not the exclude
list itself: if a future GTK/glib update ever makes something else
start needing one of these, the validation step fails the build
immediately with the exact missing library named, rather than
shipping something that only breaks once a user's machine happens to
exercise that path. UPX binary compression is also enabled on Linux,
verified to still produce a working build (full app regression suite,
a real Cinnamon-theme GSettings exercise, and a CSV-file-argument
launch, all re-run against the pruned and compressed bundle). Neither
of these is applied to the Windows or macOS scripts: UPX's support for
Windows PE and macOS Mach-O binaries is comparatively less reliable
than for Linux ELF, commonly triggers antivirus false-positives on
Windows specifically, and can conflict with macOS's own codesigning
and notarization step outright -- and the exact GIO module names and
transitive dependencies on those platforms haven't been verified at
all, unlike the Linux case above. Stacking unverified size
optimizations onto an already-unverified build pipeline isn't a good
trade, so both platforms are left as they were.

### The GIRepository-3.0 gap

PyGObject >= 3.52 links its own C extension against
`libgirepository-2.0`, which -- unlike the library it replaced -- has
no separate, introspectable `GIRepository` typelib of its own at all;
that functionality is native to the C library itself. PyInstaller's
own GTK4/`gi` hook still needs to introspect *something* named
`GIRepository` to discover what to collect, and specifically expects
one named `GIRepository` version `3.0` for this newer architecture
(see `PyInstaller/utils/hooks/gi.py`'s own `new_api` branch in an
installed PyInstaller). On Debian/Ubuntu, that introspection data
ships as a separate, not-installed-by-default package:

```sh
sudo apt-get install -y gir1.2-girepository-3.0
```

Confirmed directly on Linux: without it, the portable build produces
zero `.typelib` files at all, and the resulting app crashes on
startup with `AttributeError: 'gi.repository.GObject' object has no
attribute 'Property'` -- an error that doesn't point at the missing
package at all, which is why this is called out explicitly here and
in every build script's own header comment. Each script also runs a
pre-flight check for this and fails with a clear message pointing
back to this explanation, rather than letting PyInstaller fail
opaquely partway through a build.

Whether Homebrew's or MSYS2's own PyGObject builds hit the same gap,
and whether an equivalent package exists for either, is **not
confirmed** -- see the next section.

**Verified for real, on this machine, where the tooling allows it:**
`build_deb.sh` and `build_linux_portable.sh` are both Linux-native and
were actually run end-to-end -- the `.deb` was installed with `dpkg
-i` and confirmed to launch; the portable `.tar.gz` was extracted to
an unrelated directory and run with a real Cinnamon-theme exercise, a
CSV file-argument launch, and its About-dialog icon all confirmed
working, with `LD_LIBRARY_PATH`, `PYTHONPATH`, `GI_TYPELIB_PATH`, and
any venv entirely stripped from the environment, confirming it
doesn't quietly depend on anything from the machine it was built on.
GPG signing was verified the same way -- a real test keypair, a real
signature, and a real `gpg --verify` confirming it -- and confirmed to
degrade cleanly (build succeeds, just unsigned) with no key
configured, which is the default state for anyone who clones this
repo without setting up the secrets above.

`build_windows.sh` and `build_macos.sh` are **UNTESTED** -- each says
so plainly in its own header comment. They were written by adapting
the verified Linux script to each platform's own conventions and
PyInstaller's own documented `BUNDLE()`/`EXE()` support, but no
Windows or macOS machine was available to actually build or launch
either one. In particular, the GIRepository-3.0 gap above was
diagnosed and fixed on Linux specifically; whether it reproduces on
Homebrew/MSYS2's own PyGObject builds, and whether an equivalent
introspection-data package exists for either, is unconfirmed. Treat
the first real run of either script, on real hardware, as the actual
verification step -- not this document, and not the CI workflow's own
best-guess dependency lists for those two jobs.
