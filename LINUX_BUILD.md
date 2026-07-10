# StormFuse Linux Build

Linux is a secondary, experimental StormFuse target. Windows remains the
officially packaged release target; Linux currently produces only a PyInstaller
onedir executable.

## Target

| Concern | Status |
|---------|--------|
| Tested desktop | Kubuntu 26.04, KDE Plasma, native Linux |
| Build output | `dist/StormFuse/StormFuse` |
| Packaging | No `.deb`, snap, AppImage, Flatpak, or `.desktop` file yet |
| FFmpeg | System `ffmpeg` / `ffprobe` from `PATH`; not bundled |

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
Windows ffmpeg build used by the Windows installer.

## Build The Onedir Executable

```bash
make installer
./dist/StormFuse/StormFuse
```

On Linux, `make installer` stops after PyInstaller. It does not run NSIS and
does not create an installer package.

## Desktop Integration

There is no `.desktop` file or application-menu integration yet. That work is
planned alongside the Linux packaging decision: snap vs AppImage vs Flatpak vs
`.deb` / `.rpm`.

## Theme Detection

System light/dark theme detection requires a running XDG desktop portal,
including `xdg-desktop-portal` and `xdg-desktop-portal-kde`. Kubuntu installs
these by default.
