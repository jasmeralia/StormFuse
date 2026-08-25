# StormFuse on Linux

Linux is a secondary StormFuse target. Every tagged release provides DEB, RPM,
AppImage, Flatpak, and Snap packages for both amd64 and arm64 as sideloadable
GitHub release assets. No package is published to an external store or package
repository.

## Target

| Concern | Status |
|---------|--------|
| Tested desktop | Kubuntu 26.04, KDE Plasma, native Linux |
| Architectures | amd64 (`x86_64`) and arm64 (`aarch64`) |
| Release packages | `.deb`, `.rpm`, `.AppImage`, `.flatpak`, `.snap` |
| Local staging output | `dist/StormFuse/StormFuse` |
| Desktop integration | Shared `.desktop` entry and StormFuse icon in every package |

## Choose a Package

Download the file for your architecture from
[GitHub Releases](https://github.com/jasmeralia/StormFuse/releases).

| Format | Installation | FFmpeg source |
|--------|--------------|---------------|
| DEB | `sudo apt install ./StormFuse-<version>-<arch>.deb` | The package depends on the distribution's `ffmpeg` package. |
| RPM | `sudo dnf install ./StormFuse-<version>-<arch>.rpm` | The package requires `ffmpeg`; see the warning below. |
| AppImage | `chmod +x StormFuse-*.AppImage` and run it directly | Pinned static `ffmpeg` and `ffprobe` are bundled. |
| Flatpak | `flatpak install --user ./StormFuse-*.flatpak` | The Freedesktop `ffmpeg-full` runtime extension supplies full codec support. |
| Snap | `sudo snap install --classic --dangerous ./StormFuse-*.snap` | Ubuntu's `ffmpeg` package is staged inside the snap. |

> **RPM users:** Fedora and RHEL official repositories do not ship the full
> `ffmpeg` package because of codec licensing. Enable RPM Fusion (or an
> equivalent third-party multimedia repository) before installing the
> StormFuse RPM, or `dnf` will be unable to resolve its `ffmpeg` dependency.

> **Snap users:** the Snap uses classic (unconfined) confinement, not strict
> — strict confinement's `home`/`removable-media` plugs can't reliably reach
> files outside your home directory (external drives, `/mnt`, `/run/media`)
> without portal support StormFuse doesn't implement, which would silently
> break combining/compressing files from those locations. `--classic` is
> required at install time as a result.
>
> `--dangerous` is also required and is not a red flag specific to
> StormFuse — it just tells `snapd` to skip the assertion/signature checks
> it normally requires from the Snap Store. Since this Snap isn't published
> there, the file has no store signature, the same reason a local `.deb` or
> `.flatpak` needs "install this unsigned file anyway" handling too.

## System Requirements: glibc Baseline

The bundled StormFuse binary is built on `ubuntu-latest` /
`ubuntu-24.04-arm` (Ubuntu 24.04 LTS, glibc 2.39) and, like any PyInstaller
Linux build, is only forward-compatible — it will not run on an older glibc.
This is a hard floor, not a soft recommendation:

| Format | Enforcement |
|--------|-------------|
| DEB | Depends on `libc6 (>= 2.39)`. `apt`/`dpkg` refuses to install on an older system. |
| RPM | Requires `glibc >= 2.39`. `dnf`/`rpm` refuses to install on an older system. |
| AppImage | `AppRun` checks the host's glibc version at startup and exits with a clear error on an older system, rather than crashing with an opaque dynamic-linker error. |
| Flatpak | Unaffected — runs against the `org.kde.Platform` runtime's own bundled glibc, not the host's. |
| Snap | Unaffected — runs against the `core24` base snap's own bundled glibc, not the host's. |

Practically, this means Ubuntu 24.04 LTS or newer (and comparably current
Debian/Fedora/RHEL releases) for DEB/RPM/AppImage. Anyone on an older system
should use Flatpak, Snap, or build from source instead — see
[Building From Source](#run-from-source) below.

## System Dependencies

The package names below were verified on Kubuntu 26.04:

```bash
sudo apt install python3.14 python3.14-venv make ffmpeg
```

NVIDIA's proprietary driver is required for NVENC hardware encoding, but it is
optional. StormFuse automatically falls back to `libx264` when NVENC is not
available.

## Verify FFmpeg And NVENC

Confirm FFmpeg exposes NVENC encoders:

```bash
ffmpeg -hide_banner -encoders | grep nvenc
```

Confirm the NVIDIA driver sees the GPU:

```bash
nvidia-smi -L
```

If either command fails, StormFuse can still run with the CPU `libx264`
fallback as long as `ffmpeg` and `ffprobe` are on `PATH`.

## Run From Source

```bash
make venv
make deps
make run
```

On Linux, `make fetch-ffmpeg` is not needed. That target downloads the pinned
Windows build. The `fetch-ffmpeg-linux-*` targets are reserved for AppImage CI;
normal source, DEB/RPM, Flatpak, and Snap builds use their system/runtime
mechanisms.

## Build The Onedir Executable

```bash
make installer
./dist/StormFuse/StormFuse
```

On Linux, `make installer` stops after PyInstaller. Release CI uses this onedir
tree as the input to each dedicated packaging tool.

## Desktop Integration

Packaged builds install or export `resources/linux/stormfuse.desktop` and the
existing StormFuse icon. DEB and RPM packages place the application under
`/usr/lib/stormfuse` and expose `/usr/bin/stormfuse`; the sandboxed and portable
formats provide their own equivalent launch entry.
