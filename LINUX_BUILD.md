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
| Snap | `sudo snap install --dangerous ./StormFuse-*.snap` | Ubuntu's `ffmpeg` package is staged inside the snap. |

> **RPM users:** Fedora and RHEL official repositories do not ship the full
> `ffmpeg` package because of codec licensing. Enable RPM Fusion (or an
> equivalent third-party multimedia repository) before installing the
> StormFuse RPM, or `dnf` will be unable to resolve its `ffmpeg` dependency.

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

## Theme Detection

System light/dark theme detection requires a running XDG desktop portal,
including `xdg-desktop-portal` and `xdg-desktop-portal-kde`. Kubuntu installs
these by default.
