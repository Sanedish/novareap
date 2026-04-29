# NovaReap

NovaReap is a single-file music downloader for Tidal, Spotify, Apple Music
links, and YouTube fallback audio.

It can download directly from Tidal where your account allows it, resolve
Spotify links into track metadata, scrape Apple Music page metadata, and embed
tags/cover art into MP3, M4A, AAC, and FLAC files.

## Features

- Direct Tidal downloads for tracks, albums, and playlists.
- Spotify track, album, and playlist URL resolution.
- Apple Music metadata scraping for track and album pages.
- YouTube fallback audio through `yt-dlp`.
- Metadata and cover-art tagging through `mutagen`.
- Resume-friendly skip-existing behavior.
- Concurrent downloads with Rich terminal progress.
- First-run `setup` and `doctor` commands for clean installs.

## Requirements

- Python 3.10 or newer.
- FFmpeg on PATH for YouTube fallback conversion.
- A Tidal account for Tidal downloads.
- Optional Spotify API credentials for Spotify URLs and better fallback matches.

## Fresh Windows Install

After a Windows reinstall, install Python and FFmpeg before running NovaReap:

```powershell
winget install Python.Python.3.12
winget install Gyan.FFmpeg
```

Close and reopen PowerShell, then verify:

```powershell
python --version
ffmpeg -version
```

If `python` is still not found, reinstall Python and enable **Add python.exe to
PATH** in the installer.

## Install

```powershell
cd C:\path\to\musync
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python novareap.py setup
python novareap.py doctor
```

On macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python novareap.py setup
python novareap.py doctor
```

## First-Time Setup

Run:

```bash
python novareap.py setup
```

This creates the config file, creates the download directory, and prints
diagnostics for Python, FFmpeg, `yt-dlp`, metadata tagging, Spotify config, and
the output directory.

Spotify credentials are optional. Skip them if you only use Tidal or Apple
Music links:

```bash
python novareap.py setup --skip-spotify
```

Authenticate with Tidal when you want direct Tidal downloads:

```bash
python novareap.py auth
```

## Usage

```bash
python novareap.py download https://tidal.com/track/210615097
python novareap.py download https://tidal.com/album/123456789
python novareap.py download https://tidal.com/playlist/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
python novareap.py download https://open.spotify.com/track/...
python novareap.py download https://music.apple.com/us/album/...
```

Multiple URLs are supported:

```bash
python novareap.py download <url1> <url2> <url3>
```

## Commands

| Command | Purpose |
| --- | --- |
| `setup` | Create config/directories and run first-run checks. |
| `doctor` | Print dependency and setup diagnostics. |
| `info` | Show diagnostics plus current config values. |
| `configure` | Edit config interactively. |
| `auth` | Log in to Tidal and save the session. |
| `download` | Download one or more URLs. |
| `meta` | Append metadata to an existing audio file. |

## Download Options

| Option | Default | Description |
| --- | --- | --- |
| `--quality`, `-q` | `master` | Tidal quality: `low`, `high`, or `master`. |
| `--output`, `-o` | `~/Music/NovaReap` | Download directory. |
| `--concurrent`, `-c` | `3` | Parallel download workers. |
| `--no-skip` | off | Re-download existing files. |
| `--no-metadata` | off | Skip metadata and cover-art embedding. |
| `--config` | `~/.config/novareap/config.json` | Custom config file path. |

## Manual Metadata

Append metadata to a file you already have:

```powershell
python novareap.py meta "path/to/file.flac"
python novareap.py meta "path/to/file.m4a" --title "Song" --artist "Artist" --album "Album"
```

Without `--title` or `--artist`, NovaReap infers them from filenames like
`Artist - Song.flac`. The command also accepts `--track-number`, `--year`,
`--genre`, and `--cover-url`.

## Configuration

Default config path:

```text
~/.config/novareap/config.json
```

Example:

```json
{
  "download_dir": "C:/Users/you/Music/NovaReap",
  "session_file": "C:/Users/you/.config/novareap/tidal_session.json",
  "spotify_client_id": "",
  "spotify_client_secret": "",
  "tidal_quality": "master",
  "concurrent_downloads": 3,
  "retry_attempts": 3,
  "retry_delay": 2.0,
  "skip_existing": true,
  "embed_metadata": true,
  "filename_template": "{artist} - {title}"
}
```

`filename_template` currently supports `{artist}` and `{title}`.

## Spotify Credentials

Spotify audio is not downloaded from Spotify. Credentials are used only to
resolve Spotify links and improve fallback metadata.

1. Create an app at <https://developer.spotify.com/dashboard>.
2. Copy the client ID and client secret.
3. Run `python novareap.py configure`.
4. Paste the credentials when prompted.

## Troubleshooting

Run this first:

```bash
python novareap.py doctor
```

Common fresh-install problems:

- `python` is not recognized: install Python 3.10+ and enable PATH integration.
- `ffmpeg` is not recognized: install FFmpeg and restart the terminal.
- YouTube fallback fails: update dependencies with `python -m pip install -U -r requirements.txt`.
- Metadata tags are missing: make sure `mutagen` is installed and do not pass `--no-metadata`.
- Spotify URLs fail: configure Spotify credentials or use non-Spotify links.
- Tidal session fails after upgrades: delete `~/.config/novareap/tidal_session.json` and run `python novareap.py auth`.
- Tidal downloads AAC/M4A when a 24-bit file is available: delete the saved Tidal session, then run `python novareap.py auth --quality master` so tidalapi uses PKCE/get_stream for master quality.
- Tidal hi-res streams can use MP4/DASH fragments while still carrying FLAC audio. NovaReap uses the manifest codec, not only the file header, to decide whether a stream is FLAC.

## Legal

Use NovaReap only for personal, offline access to music you are legally allowed
to download. Do not distribute copyrighted content without permission.

## License

MIT
