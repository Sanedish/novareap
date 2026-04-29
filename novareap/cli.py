#!/usr/bin/env python3
"""
NovaReap - A high-quality music downloader for Tidal, Spotify, and Apple Music.

    Supports direct master/AAC download from Tidal (track, album, playlist),
Spotify URL resolution with Spotify-first fallback matching, and Apple Music
metadata scraping with YouTube as the fallback audio source.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from functools import wraps

import click
import requests
from bs4 import BeautifulSoup
from rich import box
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.table import Table
from rich.theme import Theme

try:
    import mutagen
    from mutagen.id3 import (
        APIC, COMM, ID3, ID3NoHeaderError, TIT2, TPE1, TALB, TRCK, TDRC, TCON
    )
    from mutagen.mp4 import MP4, MP4Cover
    from mutagen.flac import FLAC, Picture
    HAS_MUTAGEN = True
except ImportError:
    HAS_MUTAGEN = False

try:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials
    HAS_SPOTIPY = True
except ImportError:
    HAS_SPOTIPY = False

try:
    import tidalapi
    HAS_TIDAL = True
except ImportError:
    HAS_TIDAL = False

try:
    import yt_dlp
    HAS_YTDLP = True
except ImportError:
    HAS_YTDLP = False


# ---------------------------------------------------------------------------
# Theme & Console
# ---------------------------------------------------------------------------

THEME = Theme({
    "info":     "cyan",
    "success":  "bold green",
    "warning":  "bold yellow",
    "error":    "bold red",
    "muted":    "dim white",
    "track":    "bold white",
    "artist":   "cyan",
    "source":   "magenta",
    "quality":  "bold green",
})

console = Console(theme=THEME)

logging.basicConfig(
    level=logging.WARNING,
    handlers=[RichHandler(console=console, show_path=False, markup=True)],
    format="%(message)s",
)
log = logging.getLogger("novareap")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "novareap" / "config.json"
DEFAULT_DOWNLOAD_DIR = Path.home() / "Music" / "NovaReap"
DEFAULT_SESSION_FILE = Path.home() / ".config" / "novareap" / "tidal_session.json"
MIN_PYTHON = (3, 10)


def _normalize_tidal_quality(name: str) -> str:
    value = (name or "master").lower().replace("-", "_")
    if value in ("low", "high", "lossless", "master", "max", "hires", "hi_res"):
        return value
    return "master"

@dataclass
class Config:
    download_dir:        Path   = field(default_factory=lambda: DEFAULT_DOWNLOAD_DIR)
    session_file:        Path   = field(default_factory=lambda: DEFAULT_SESSION_FILE)
    spotify_client_id:   str    = ""
    spotify_client_secret: str  = ""
    tidal_quality:       str    = "master"        # low | high | lossless | master
    youtube_quality:     str    = "320"           # 128 | 192 | 256 | 320
    concurrent_downloads: int   = 3
    retry_attempts:      int    = 3
    retry_delay:         float  = 2.0             # seconds, doubles each retry
    skip_existing:       bool   = True
    embed_metadata:      bool   = True
    filename_template:   str    = "{artist} - {title}"

    @classmethod
    def load(cls, path: Path = DEFAULT_CONFIG_PATH) -> "Config":
        if not path.exists():
            return cls()
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        cfg = cls()
        for k, v in data.items():
            if hasattr(cfg, k):
                val = Path(v) if k in ("download_dir", "session_file") else v
                if k == "tidal_quality":
                    val = _normalize_tidal_quality(str(val))
                setattr(cfg, k, val)
        return cfg

    def save(self, path: Path = DEFAULT_CONFIG_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            k: str(v) if isinstance(v, Path) else v
            for k, v in self.__dict__.items()
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)


@dataclass
class SetupCheck:
    name: str
    status: str
    detail: str
    fix: str


def _ok(condition: bool) -> str:
    return "ok" if condition else "missing"


def _path_exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def collect_setup_checks(cfg: Config, config_path: Path = DEFAULT_CONFIG_PATH) -> list[SetupCheck]:
    """Return first-run diagnostics with concrete fix hints."""
    python_ok = sys.version_info >= MIN_PYTHON
    ffmpeg_path = shutil.which("ffmpeg")
    output_ready = _path_exists(cfg.download_dir) and cfg.download_dir.is_dir()
    config_ready = _path_exists(config_path)

    return [
        SetupCheck(
            "Python",
            _ok(python_ok),
            f"{sys.version.split()[0]} at {sys.executable}",
            "Install Python 3.10+ and enable 'Add python.exe to PATH'." if not python_ok else "No action needed.",
        ),
        SetupCheck(
            "FFmpeg",
            _ok(bool(ffmpeg_path)),
            ffmpeg_path or "Not found on PATH",
            "Install FFmpeg and restart the terminal so ffmpeg is on PATH." if not ffmpeg_path else "No action needed.",
        ),
        SetupCheck(
            "yt-dlp",
            _ok(HAS_YTDLP),
            "Python package installed" if HAS_YTDLP else "Python package missing",
            "Run `python -m pip install -r requirements.txt`." if not HAS_YTDLP else "No action needed.",
        ),
        SetupCheck(
            "mutagen",
            _ok(HAS_MUTAGEN),
            "Metadata tagging enabled" if HAS_MUTAGEN else "Metadata tagging package missing",
            "Run `python -m pip install -r requirements.txt`." if not HAS_MUTAGEN else "No action needed.",
        ),
        SetupCheck(
            "Spotify",
            "ok" if cfg.spotify_client_id and cfg.spotify_client_secret else "optional",
            "Configured" if cfg.spotify_client_id and cfg.spotify_client_secret else "Not configured",
            "Run `python novareap.py configure` if you want Spotify URLs/fallback matching.",
        ),
        SetupCheck(
            "Download directory",
            _ok(output_ready),
            str(cfg.download_dir),
            "Run `python novareap.py setup` to create it." if not output_ready else "No action needed.",
        ),
        SetupCheck(
            "Config file",
            _ok(config_ready),
            str(config_path),
            "Run `python novareap.py setup` or `python novareap.py configure`." if not config_ready else "No action needed.",
        ),
    ]


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class TrackInfo:
    title:        str
    artist:       str
    album:        str         = ""
    track_number: int         = 0
    year:         str         = ""
    genre:        str         = ""
    cover_url:    str         = ""
    duration_sec: int         = 0
    tidal_id:     Optional[int] = None
    spotify_id:   Optional[str] = None
    audio_info:   str         = ""


@dataclass
class DownloadResult:
    track:    TrackInfo
    success:  bool
    path:     Optional[Path] = None
    source:   str            = ""   # "tidal" | "youtube" | "skipped"
    error:    str            = ""


@dataclass
class TidalStreamSource:
    urls: list[str]
    extension: str
    quality: str = ""
    codec: str = ""
    bit_depth: int = 0
    sample_rate: int = 0
    from_manifest: bool = False


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def sanitize_filename(name: str) -> str:
    """Remove characters illegal on Windows/Linux/macOS."""
    name = re.sub(r'[\\/*?:"<>|]', "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:200]


def _truncate(s: str, max_len: int = 30) -> str:
    """Truncate *s* to at most *max_len* characters, adding '…' when trimmed."""
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def sniff_audio_extension(path: Path) -> Optional[str]:
    """Infer a supported audio extension from the file header."""
    try:
        with open(path, "rb") as f:
            header = f.read(8192)
    except OSError:
        return None

    # Skip ID3 tag if present to check underlying audio stream
    offset = 0
    if header.startswith(b"ID3") and len(header) >= 10:
        size = (header[6] << 21) | (header[7] << 14) | (header[8] << 7) | header[9]
        offset = 10 + size
        try:
            with open(path, "rb") as f:
                f.seek(offset)
                audio_header = f.read(64)
        except OSError:
            audio_header = b""
        
        if audio_header.startswith(b"fLaC"):
            return ".flac"

    if header.startswith(b"fLaC"):
        return ".flac"
    if len(header) >= 12 and header[4:8] == b"ftyp":
        return ".m4a"
    if header.startswith(b"ID3"):
        return ".mp3"
    if len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0:
        return ".mp3"
    return None


def unique_path(path: Path) -> Path:
    """Return path or a numbered sibling that does not exist."""
    if not path.exists():
        return path
    for i in range(1, 1000):
        candidate = path.with_name(f"{path.stem} ({i}){path.suffix}")
        if not candidate.exists():
            return candidate
    return path.with_name(f"{path.stem} ({int(time.time())}){path.suffix}")


def normalize_audio_extension(path: Path) -> Path:
    """Rename a completed download when its extension disagrees with its bytes."""
    detected = sniff_audio_extension(path)
    if not detected or detected == path.suffix.lower():
        return path

    target = unique_path(path.with_suffix(detected))
    try:
        path.rename(target)
        log.debug(f"Renamed {path.name} to {target.name} after detecting {detected} container")
        return target
    except OSError as e:
        log.warning(f"Could not rename {path.name} to {target.name}: {e}")
        return path


def retry(attempts: int = 3, delay: float = 2.0, exceptions=(Exception,)):
    """Decorator: retry on failure with exponential back-off."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt < attempts:
                        wait = delay * (2 ** (attempt - 1))
                        log.debug(f"Retry {attempt}/{attempts} for {fn.__name__} in {wait:.1f}s: {exc}")
                        time.sleep(wait)
            raise last_exc
        return wrapper
    return decorator


def fetch_cover_art(url: str) -> Optional[bytes]:
    """Download cover art bytes, return None on failure."""
    if not url:
        return None
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.content
    except Exception:
        return None


def metadata_info_from_file(
    path: Path,
    title: str = "",
    artist: str = "",
    album: str = "",
    track_number: int = 0,
    year: str = "",
    genre: str = "",
    cover_url: str = "",
) -> TrackInfo:
    inferred_artist = ""
    inferred_title = path.stem
    if " - " in path.stem:
        inferred_artist, inferred_title = path.stem.split(" - ", 1)
    return TrackInfo(
        title=title or inferred_title,
        artist=artist or inferred_artist,
        album=album,
        track_number=track_number,
        year=year,
        genre=genre,
        cover_url=cover_url,
    )


# ---------------------------------------------------------------------------
# Metadata embedding
# ---------------------------------------------------------------------------

class MetadataTagger:
    """Embeds track metadata + cover art into downloaded files."""

    @staticmethod
    def tag(path: Path, info: TrackInfo):
        """Tag the file. Returns the resolved Path (which may differ from
        the input if a container was unwrapped) on success, or None on
        failure. Existing callers that only care about the bool can use
        ``bool(MetadataTagger.tag(...))``.
        """
        if not HAS_MUTAGEN:
            log.warning(f"Metadata tagging skipped for {path.name}: mutagen is not installed.")
            return None

        # If the file is FLAC-in-MP4 (Tidal hi-res), unwrap it to native FLAC
        # first. ffmpeg stream-copies the FLAC frames into a real .flac
        # container — bit-for-bit identical samples, but every library reads
        # length/bitrate/bit-depth correctly and tagging goes through Vorbis
        # comments where it belongs.
        path = MetadataTagger._unwrap_flac_in_mp4_if_needed(path)

        # Trust the extension (caller has already run normalize_audio_extension).
        # Only fall back to sniffing when the extension is unrecognised; previously
        # the sniffer could disagree with the suffix on real-world files (e.g. an
        # mp3 with an embedded fLaC artefact, or a real FLAC reported as mp3 by
        # the ID3-skip path) and we'd write tags into the wrong atom/tag area —
        # mutagen would then "succeed" but readers wouldn't see the tags.
        ext = path.suffix.lower()
        if ext in (".mp3", ".m4a", ".aac", ".flac"):
            effective_ext = ext
        else:
            effective_ext = sniff_audio_extension(path) or ext
        cover_data = fetch_cover_art(info.cover_url)
        try:
            if effective_ext == ".mp3":
                MetadataTagger._tag_mp3(path, info, cover_data)
            elif effective_ext in (".m4a", ".aac"):
                MetadataTagger._tag_m4a(path, info, cover_data)
            elif effective_ext == ".flac":
                MetadataTagger._tag_flac(path, info, cover_data)
            else:
                if MetadataTagger._tag_generic(path, info):
                    return path
                return None
        except Exception as e:
            log.warning(f"Metadata tagging failed for {path.name}: {e}")
            return None
        # Verify tags actually landed by reading the file back. Without this
        # the CLI would print "Metadata appended" even when a tagger silently
        # wrote into a frame mutagen.File() can't surface.
        if MetadataTagger._verify_tags_present(path, info):
            return path
        return None

    @staticmethod
    def _verify_tags_present(path: Path, info: TrackInfo) -> bool:
        """Re-open the file and confirm at least one written field is readable."""
        try:
            written = mutagen.File(path)
        except Exception as e:
            log.warning(f"Metadata write could not be verified for {path.name}: {e}")
            return False
        if written is None or written.tags is None:
            log.warning(f"Metadata appears empty after write for {path.name}.")
            return False
        # Require at least the title (or artist) to round-trip. We compare
        # against the values we tried to write, not "any tag", because the
        # source file may already have had an encoder/comment tag.
        expected_title = (info.title or "").strip()
        expected_artist = (info.artist or "").strip()
        if not expected_title and not expected_artist:
            return True  # nothing to verify
        try:
            easy = mutagen.File(path, easy=True)
        except Exception:
            easy = None
        if easy is not None and easy.tags is not None:
            got_title = (easy.tags.get("title") or [""])[0]
            got_artist = (easy.tags.get("artist") or [""])[0]
            if expected_title and got_title == expected_title:
                return True
            if expected_artist and got_artist == expected_artist:
                return True
        log.warning(f"Metadata write did not round-trip for {path.name}.")
        return False

    @staticmethod
    def _unwrap_flac_in_mp4_if_needed(path: Path) -> Path:
        """Extract FLAC samples from an MP4 container into a native .flac file.

        Tidal hi-res arrives as fragmented MP4 carrying a FLAC stream. mutagen
        and most players can read it, but bitrate reports as 0 and tags live
        in MP4 atoms instead of Vorbis comments. ffmpeg can stream-copy the
        FLAC frames into a real FLAC container — bit-for-bit identical PCM,
        proper STREAMINFO, smaller file, all libraries happy.

        Only fires when the file is .m4a/.mp4/.aac AND mutagen identifies the
        codec as FLAC. Returns the new path on success, original on no-op or
        failure.
        """
        ext = path.suffix.lower()
        if ext not in (".m4a", ".mp4", ".aac"):
            return path
        # Confirm it actually contains FLAC. Reading codec is cheap.
        try:
            probe = MP4(path)
        except Exception:
            return path
        codec = (getattr(probe.info, "codec", "") or "").lower() if probe.info else ""
        if "flac" not in codec:
            return path  # leave AAC etc. alone

        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            log.debug(f"FLAC unwrap skipped for {path.name}: ffmpeg not on PATH.")
            return path

        target = unique_path(path.with_suffix(".flac"))
        try:
            import subprocess
            result = subprocess.run(
                [
                    ffmpeg, "-y", "-loglevel", "error",
                    "-i", str(path),
                    "-c:a", "copy",
                    "-f", "flac",
                    str(target),
                ],
                capture_output=True,
                timeout=120,
            )
            if result.returncode != 0 or not target.exists() or target.stat().st_size == 0:
                log.debug(
                    f"FLAC unwrap failed for {path.name}: "
                    f"{result.stderr.decode('utf-8', errors='replace').strip()}"
                )
                if target.exists():
                    target.unlink(missing_ok=True)
                return path
            # Validate the output before deleting the source.
            try:
                check = FLAC(target)
                if check.info is None or check.info.length <= 0:
                    raise ValueError("extracted FLAC has no readable info")
            except Exception as e:
                log.debug(f"FLAC unwrap produced an unreadable file for {path.name}: {e}")
                target.unlink(missing_ok=True)
                return path
            try:
                path.unlink()
            except OSError as e:
                log.debug(f"Could not remove original MP4 after FLAC unwrap ({path.name}): {e}")
            log.debug(f"Unwrapped FLAC-in-MP4 to native FLAC: {path.name} -> {target.name}")
            return target
        except Exception as e:
            log.debug(f"FLAC unwrap skipped for {path.name}: {e}")
            if target.exists():
                target.unlink(missing_ok=True)
            return path

    @staticmethod
    def _remux_fragmented_mp4_if_needed(path: Path) -> Path:
        """Convert a fragmented MP4 (DASH-style) to a regular MP4 in place.

        Tidal hi-res streams arrive as fragmented MP4 with the mp41dash brand,
        which mutagen can read but reports as length=0/bitrate=0 because
        per-segment timing lives in moof boxes. ffmpeg can stream-copy the
        fragments into a normal MP4 with mvhd/mdhd duration in seconds —
        no re-encoding, lossless. Returns the path either way.
        """
        try:
            probe = MP4(path)
        except Exception:
            return path
        if probe.info is None or probe.info.length > 0:
            return path  # already a well-formed MP4 with usable duration

        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            log.debug(f"Skipping fragmented-MP4 remux for {path.name}: ffmpeg not on PATH.")
            return path

        # ffmpeg will not stream-copy FLAC into the .m4a (iPod) muxer, but the
        # generic mp4 muxer accepts it. Write to a temp file alongside, then
        # atomically replace the original on success.
        tmp_path = path.with_name(f".{path.name}.remux.mp4")
        try:
            import subprocess
            result = subprocess.run(
                [
                    ffmpeg, "-y", "-loglevel", "error",
                    "-i", str(path),
                    "-c", "copy",
                    "-f", "mp4",
                    "-movflags", "+faststart",
                    str(tmp_path),
                ],
                capture_output=True,
                timeout=120,
            )
            if result.returncode != 0 or not tmp_path.exists() or tmp_path.stat().st_size == 0:
                log.debug(
                    f"ffmpeg remux failed for {path.name}: "
                    f"{result.stderr.decode('utf-8', errors='replace').strip()}"
                )
                if tmp_path.exists():
                    tmp_path.unlink(missing_ok=True)
                return path
            # Validate the output before swapping.
            try:
                check = MP4(tmp_path)
                if check.info is None or check.info.length <= 0:
                    raise ValueError("remuxed file still reports zero length")
            except Exception as e:
                log.debug(f"ffmpeg remux produced an unreadable file for {path.name}: {e}")
                tmp_path.unlink(missing_ok=True)
                return path
            tmp_path.replace(path)
            log.debug(f"Remuxed fragmented MP4 in place: {path.name}")
            return path
        except Exception as e:
            log.debug(f"Fragmented-MP4 remux skipped for {path.name}: {e}")
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            return path

    @staticmethod
    def _tag_mp3(path: Path, info: TrackInfo, cover: Optional[bytes]):
        try:
            tags = ID3(path, v2_version=3)
        except ID3NoHeaderError:
            tags = ID3()
        if info.title:
            tags["TIT2"] = TIT2(encoding=3, text=info.title)
        if info.artist:
            tags["TPE1"] = TPE1(encoding=3, text=info.artist)
        if info.album:
            tags["TALB"] = TALB(encoding=3, text=info.album)
        if info.track_number:
            tags["TRCK"] = TRCK(encoding=3, text=str(info.track_number))
        if info.year:
            tags["TDRC"] = TDRC(encoding=3, text=info.year)
        if info.genre:
            tags["TCON"] = TCON(encoding=3, text=info.genre)
        if cover:
            tags["APIC"] = APIC(
                encoding=3, mime="image/jpeg",
                type=3, desc="Cover", data=cover,
            )
        if info.audio_info:
            tags.add(COMM(encoding=3, lang="eng", desc="Audio Info", text=[info.audio_info]))
        tags.update_to_v23()
        tags.save(path, v2_version=3)

    @staticmethod
    def _tag_m4a(path: Path, info: TrackInfo, cover: Optional[bytes]):
        # Tidal hi-res arrives as fragmented MP4 (mp41dash brand). mutagen can
        # tag it and players can decode it, but the duration/bitrate atoms
        # live in the moof segments, so libraries report length 0. Remux to a
        # plain MP4 with ffmpeg (no re-encode) before tagging when we detect
        # this case, so library scanners get a real duration.
        path = MetadataTagger._remux_fragmented_mp4_if_needed(path)

        # Load the file, but only mutate the tags atom and save through the
        # tags object. Calling MP4(path).save() rewrote the moov tree on some
        # streaming-origin m4a files (yt-dlp/Tidal) and dropped the esds
        # descriptor — players then reported 0 bitrate / unknown sample rate
        # even though the audio samples were still intact. Saving via
        # mp4.tags.save(path) only touches the udta box.
        mp4 = MP4(path)
        if mp4.tags is None:
            mp4.add_tags()
        tags = mp4.tags
        if info.title:
            tags["\xa9nam"] = [info.title]
        if info.artist:
            tags["\xa9ART"] = [info.artist]
        if info.album:
            tags["\xa9alb"] = [info.album]
        if info.track_number:
            tags["trkn"] = [(info.track_number, 0)]
        if info.year:
            tags["\xa9day"] = [info.year]
        if info.genre:
            tags["\xa9gen"] = [info.genre]
        if cover:
            tags["covr"] = [MP4Cover(cover, imageformat=MP4Cover.FORMAT_JPEG)]
        if info.audio_info:
            tags["\xa9cmt"] = [info.audio_info]
        tags.save(path)

    @staticmethod
    def _tag_flac(path: Path, info: TrackInfo, cover: Optional[bytes]):
        tags = FLAC(path)
        if info.title:
            tags["title"] = info.title
        if info.artist:
            tags["artist"] = info.artist
        if info.album:
            tags["album"] = info.album
        if info.track_number:
            tags["tracknumber"] = str(info.track_number)
        if info.year:
            tags["date"] = info.year
        if info.genre:
            tags["genre"] = info.genre
        if cover:
            pic = Picture()
            pic.type = 3
            pic.mime = "image/jpeg"
            pic.data = cover
            tags.add_picture(pic)
        if info.audio_info:
            tags["description"] = info.audio_info
        tags.save()

    @staticmethod
    def _tag_generic(path: Path, info: TrackInfo):
        tags = mutagen.File(path, easy=True)
        if tags is None:
            log.warning(f"Metadata tagging skipped for {path.name}: mutagen could not read this file type.")
            return False
        if info.title:
            tags["title"] = [info.title]
        if info.artist:
            tags["artist"] = [info.artist]
        if info.album:
            tags["album"] = [info.album]
        if info.track_number:
            tags["tracknumber"] = [str(info.track_number)]
        if info.year:
            tags["date"] = [info.year]
        if info.genre:
            tags["genre"] = [info.genre]
        tags.save()
        return True


class PostDownloadMetadataScript:
    """Runs immediately after a download and appends metadata when enabled."""

    @staticmethod
    def append(path: Path, info: TrackInfo, enabled: bool = True):
        """Returns the resolved Path on success (may differ from input if a
        container was unwrapped), or None on failure. Falsy on failure so
        existing ``if not append(...)`` checks keep working.
        """
        if not enabled:
            return path
        return MetadataTagger.tag(path, info)


# ---------------------------------------------------------------------------
# Tidal client
# ---------------------------------------------------------------------------

def _pick_tidal_quality(*names):
    """Return the first available tidalapi.Quality enum member from this install."""
    if not HAS_TIDAL:
        return None
    for name in names:
        value = getattr(tidalapi.Quality, name, None)
        if value is not None:
            return value
    return None


TIDAL_QUALITY_ALIASES = {
    "low":      ("low_96k",),
    "high":     ("low_320k",),
    "lossless": ("high_lossless",),
    "master":   ("hi_res_lossless",),
    "max":      ("hi_res_lossless",),
    "hires":    ("hi_res_lossless",),
    "hi_res":   ("hi_res_lossless",),
}


def _tidal_quality_for(name: str):
    """Return the tidalapi Quality value for a config quality name."""
    key = _normalize_tidal_quality(name)
    aliases = TIDAL_QUALITY_ALIASES.get(key, TIDAL_QUALITY_ALIASES["master"])
    return _pick_tidal_quality(*aliases)


def _is_hires_quality(name: str) -> bool:
    value = (name or "").lower().replace("-", "_")
    return value in ("master", "max", "hires", "hi_res") or "hi_res" in value


def _is_lossless_quality(name: str) -> bool:
    value = (name or "").lower().replace("-", "_")
    return (
        value in ("lossless", "master", "max", "hires", "hi_res")
        or "lossless" in value
        or "hi_res" in value
    )


class TidalClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.cfg.tidal_quality = _normalize_tidal_quality(self.cfg.tidal_quality)
        self.session: Optional["tidalapi.Session"] = None
        if not HAS_TIDAL:
            return

        quality = (
            _tidal_quality_for(cfg.tidal_quality)
            or _pick_tidal_quality("high_lossless", "lossless", "high", "low")
        )

        try:
            config = tidalapi.Config(quality=quality) if quality is not None else tidalapi.Config()
        except TypeError:
            config = tidalapi.Config()

        self.session = tidalapi.Session(config)

        if not self._restore_session():
            self._login_oauth()

    # --- Session -----------------------------------------------------------

    def _restore_session(self) -> bool:
        path = self.cfg.session_file
        if not path.exists():
            return False
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if not data.get("access_token"):
                return False

            expiry_time = None
            if raw := data.get("expiry_time", ""):
                try:
                    expiry_time = datetime.fromisoformat(raw)
                    if expiry_time.tzinfo is None:
                        expiry_time = expiry_time.replace(tzinfo=timezone.utc)
                except Exception:
                    pass

            try:
                ok = self.session.load_oauth_session(
                    token_type=data.get("token_type", "Bearer"),
                    access_token=data["access_token"],
                    refresh_token=data.get("refresh_token"),
                    expiry_time=expiry_time,
                    is_pkce=data.get("is_pkce", False),
                )
            except TypeError:
                ok = self.session.load_oauth_session(
                    token_type=data.get("token_type", "Bearer"),
                    access_token=data["access_token"],
                    refresh_token=data.get("refresh_token"),
                    expiry_time=expiry_time,
                )
            if not ok:
                return False
            if hasattr(self.session, "check_login") and not self.session.check_login():
                return False

            quality = getattr(self.session, "audio_quality", "unknown")
            self._auto_bump_quality_to_session(quality)
            console.print(f"  [muted]Restored Tidal session · quality: [quality]{quality}[/quality][/muted]")
            return True
        except Exception as e:
            log.debug(f"Session restore failed: {e}")
            return False

    def _auto_bump_quality_to_session(self, session_quality: str):
        """If the live session reports a higher tier than the config asked
        for, follow the session. The config default of "master" is an
        *intent* (best available), not a hard floor — when the live session
        says HI_RES_LOSSLESS we should request hi-res from
        track.get_stream(), not whatever the Config was initialized with.
        Without this, restored sessions on hi-res subscriptions can still
        end up on the plain-lossless code path.
        """
        if not session_quality:
            return

        def rank(name: str) -> int:
            n = (name or "").lower().replace("-", "_")
            if "hi_res_lossless" in n:
                return 4
            if "hi_res" in n or n in ("master", "max", "hires"):
                return 3
            if "lossless" in n or "high" in n:
                return 2
            if "low" in n:
                return 0
            return -1

        cfg_rank = rank(self.cfg.tidal_quality)
        live_rank = rank(session_quality)
        if live_rank <= cfg_rank:
            return

        old = self.cfg.tidal_quality
        if live_rank >= 3:
            self.cfg.tidal_quality = "master"
        elif live_rank == 2:
            self.cfg.tidal_quality = "lossless"
        elif live_rank == 1:
            self.cfg.tidal_quality = "high"
        else:
            self.cfg.tidal_quality = "low"
        log.debug(
            f"Auto-bumped Tidal quality from {old!r} to {self.cfg.tidal_quality!r} "
            f"(session reports {session_quality!r})."
        )

        # Re-apply to the live session so track.get_stream() asks for the
        # right tier rather than the default the Config was built with.
        new_quality = _tidal_quality_for(self.cfg.tidal_quality)
        if new_quality is not None:
            try:
                if hasattr(self.session, "config") and self.session.config is not None:
                    self.session.config.quality = new_quality
            except Exception as e:
                log.debug(f"Could not update session config quality: {e}")

    def _save_session(self):
        path = self.cfg.session_file
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "token_type": getattr(self.session, "token_type", None),
            "access_token": getattr(self.session, "access_token", None),
            "refresh_token": getattr(self.session, "refresh_token", None),
            "expiry_time": str(getattr(self.session, "expiry_time", "") or ""),
            "is_pkce": getattr(self.session, "is_pkce", False),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _login_oauth(self):
        console.print("\n[info]Tidal login required.[/info]")

        # PKCE is the ONLY way to unlock lossless / hi-res streams.
        # Standard OAuth is capped at 320 kbps AAC regardless of what
        # quality tier is requested.
        use_pkce = (
            _is_lossless_quality(self.cfg.tidal_quality)
            and hasattr(self.session, "login_pkce")
        )

        try:
            if use_pkce:
                console.print(Panel(
                    "[bold]PKCE login is required for lossless / hi-res quality.[/bold]\n\n"
                    "1. A URL will appear below — open it in your browser.\n"
                    "2. Log in to Tidal normally.\n"
                    "3. You will be redirected to an [bold cyan]'Oops'[/bold cyan] page — "
                    "[bold]this is expected![/bold]\n"
                    "4. Copy the [bold]full URL[/bold] from that 'Oops' page.\n"
                    "5. Paste it below and press Enter.",
                    title="Tidal PKCE Auth",
                    border_style="cyan",
                ))
                self.session.login_pkce(
                    fn_print=lambda text: console.print(f"  [muted]{text}[/muted]")
                )
            else:
                login, future = self.session.login_oauth()
                console.print(Panel(
                    f"[bold]Open this URL in your browser:[/bold]\n\n"
                    f"[link={login.verification_uri_complete}]{login.verification_uri_complete}[/link]\n\n"
                    f"[muted]Then press Enter here.[/muted]",
                    title="Tidal OAuth",
                    border_style="cyan",
                ))
                input()
                future.result()

            if hasattr(self.session, "check_login") and not self.session.check_login():
                console.print("[error]Login failed — session invalid.[/error]")
                self.session = None
                return

            quality = getattr(self.session, "audio_quality", "unknown")
            console.print(f"[success]Logged in![/success] Quality: [quality]{quality}[/quality]")
            self._save_session()
        except Exception as e:
            console.print(f"[error]OAuth error: {e}[/error]")
            self.session = None

    def is_available(self) -> bool:
        return self.session is not None

    # --- Track metadata extraction -----------------------------------------

    def _track_to_info(self, t) -> TrackInfo:
        album = getattr(t, "album", None)
        album_name = album.name if album else ""
        cover_url = ""
        if album:
            try:
                cover_url = album.image(1280) or album.image(640) or ""
            except Exception:
                pass

        return TrackInfo(
            title=t.name,
            artist=t.artist.name,
            album=album_name,
            track_number=getattr(t, "track_num", 0),
            year=str(getattr(getattr(t, "album", None), "release_date", "") or "")[:4],
            cover_url=cover_url,
            duration_sec=getattr(t, "duration", 0),
            tidal_id=t.id,
        )

    # --- Stream URL --------------------------------------------------------

    def _get_stream_url(self, track) -> Optional[str]:
        try:
            return track.get_url()
        except AttributeError:
            pass
        except Exception as e:
            log.debug(f"get_url() failed: {e}")
        try:
            return self.session.get_media_url(track.id)
        except Exception as e:
            log.debug(f"get_media_url() failed: {e}")
        return None

    def _wants_hires(self) -> bool:
        return _is_hires_quality(self.cfg.tidal_quality) or _is_hires_quality(
            str(getattr(self.session, "audio_quality", ""))
        )

    def _wants_lossless(self) -> bool:
        return _is_lossless_quality(self.cfg.tidal_quality)



    def _extension(self) -> str:
        quality = str(getattr(self.session, "audio_quality", "")).lower()
        if self._wants_hires() or any(q in quality for q in ("lossless", "master", "hi_res", "hires")):
            return "flac"
        return "m4a"

    @staticmethod
    def _existing_audio_download(dest: Path, stem: str) -> Optional[Path]:
        for suffix in (".flac", ".m4a", ".aac", ".mp3"):
            candidate = dest / f"{stem}{suffix}"
            if candidate.exists() and candidate.stat().st_size > 0:
                normalized = normalize_audio_extension(candidate)
                if normalized.exists() and normalized.stat().st_size > 0:
                    return normalized
        return None

    def _tag_if_enabled(self, path: Path, info: TrackInfo):
        PostDownloadMetadataScript.append(path, info, enabled=self.cfg.embed_metadata)

    @staticmethod
    def _extension_from_manifest(manifest) -> Optional[str]:
        codec = TidalClient._codec_from_manifest(manifest)
        mime = TidalClient._mime_from_manifest(manifest)
        # Tidal hi-res often delivers FLAC samples inside an MP4/DASH container
        # (mime audio/mp4, brand mp41dash). Saving such a stream as ".flac"
        # means mutagen later can't parse it as FLAC, and the file appears to
        # have zero length/bitrate. Use the container mime-type to pick the
        # extension and only fall back to codec when mime is unavailable.
        if "mp4" in mime or "m4a" in mime:
            return ".m4a"
        if "flac" in mime:
            return ".flac"
        if "FLAC" in codec:
            return ".flac"
        if codec in ("AAC", "MP4A") or "AAC" in codec or "MP4A" in codec:
            return ".m4a"
        ext = getattr(manifest, "file_extension", None)
        if ext:
            ext = str(ext)
            return ext if ext.startswith(".") else f".{ext}"
        return None

    @staticmethod
    def _codec_from_manifest(manifest) -> str:
        try:
            return str(manifest.get_codecs()).upper()
        except Exception:
            return ""

    @staticmethod
    def _mime_from_manifest(manifest) -> str:
        for attr in ("mime_type", "get_mimetype", "get_mime_type", "content_type"):
            try:
                value = getattr(manifest, attr, None)
                if callable(value):
                    value = value()
                if value:
                    return str(value).lower()
            except Exception:
                continue
        return ""

    def _get_manifest_stream_source(self, track) -> Optional[TidalStreamSource]:
        try:
            stream = track.get_stream()
            manifest = stream.get_stream_manifest()
            urls = list(manifest.get_urls())
        except AttributeError:
            return None
        except Exception as e:
            log.debug(f"get_stream() failed: {e}")
            return None

        if not urls:
            return None

        # The DASH manifest's get_codecs() often reports "mp4a.40.2" even
        # when the actual audio payload is FLAC (Tidal wraps lossless FLAC
        # inside an MP4/DASH container). Derive the real codec from the
        # stream's audio_quality attribute which is always truthful.
        stream_quality = str(getattr(stream, "audio_quality", "") or "").upper()
        manifest_codec = self._codec_from_manifest(manifest)

        if "LOSSLESS" in stream_quality or "HI_RES" in stream_quality:
            codec = "FLAC"
        else:
            codec = manifest_codec

        ext = self._extension_from_manifest(manifest) or f".{self._extension()}"
        return TidalStreamSource(
            urls=urls,
            extension=ext,
            quality=stream_quality,
            codec=codec,
            bit_depth=int(getattr(stream, "bit_depth", 0) or 0),
            sample_rate=int(getattr(stream, "sample_rate", 0) or 0),
            from_manifest=True,
        )

    def _get_direct_stream_source(self, track) -> Optional[TidalStreamSource]:
        url = self._get_stream_url(track)
        if not url:
            return None
        return TidalStreamSource(
            [url],
            f".{self._extension()}",
            quality=str(getattr(self.session, "audio_quality", "") or ""),
        )

    def _get_stream_source(self, track) -> Optional[TidalStreamSource]:
        """Try the user's requested quality, then walk *down* through every
        lower tier before giving up.  This guarantees we always get the
        highest quality Tidal can actually serve for this track.

        tidalapi 0.8.11 Quality enum members (descending):
            hi_res_lossless  — 24-bit FLAC / MQA (up to 192 kHz)
            high_lossless    — 16-bit 44.1 kHz FLAC (CD quality)
            low_320k         — 320 kbps AAC
            low_96k          — 96 kbps AAC
        """
        # Ordered from best to worst — every value that exists in this
        # install of tidalapi.
        _ALL_TIERS = ["hi_res_lossless", "high_lossless", "low_320k", "low_96k"]

        # Map the user-facing config name to the starting position in the
        # ladder.  Anything at or below that position will be attempted.
        _START_FOR = {
            "master":   0,  # start at hi_res_lossless
            "max":      0,
            "hires":    0,
            "hi_res":   0,
            "lossless": 1,  # start at high_lossless (16-bit FLAC)
            "high":     2,  # start at low_320k
            "low":      3,  # start at low_96k
        }

        current = _normalize_tidal_quality(self.cfg.tidal_quality)
        start = _START_FOR.get(current, 0)

        # Build the list of concrete enum values to try, skipping any that
        # this tidalapi version doesn't expose.
        enums_to_try = []
        for name in _ALL_TIERS[start:]:
            q = _pick_tidal_quality(name)
            if q is not None:
                enums_to_try.append(q)

        # Snapshot the session's current quality so we can restore it.
        original_quality = None
        try:
            if hasattr(self.session, "config") and self.session.config is not None:
                original_quality = getattr(self.session.config, "quality", None)
        except Exception:
            pass

        def _restore():
            if original_quality is not None:
                try:
                    self.session.config.quality = original_quality
                except Exception:
                    pass

        # Walk the ladder from the user's preferred tier downward.
        for q in enums_to_try:
            try:
                if hasattr(self.session, "config") and self.session.config is not None:
                    self.session.config.quality = q
            except Exception as e:
                log.debug(f"Could not switch session to quality {q}: {e}")
                continue

            source = self._get_manifest_stream_source(track)
            if source:
                _restore()
                return source

        _restore()
        return self._get_direct_stream_source(track)

    # --- Download ----------------------------------------------------------

    @retry(attempts=3, delay=2.0, exceptions=(requests.RequestException, IOError))
    def _stream_to_disk(self, url: str, path: Path, progress: Progress, task: TaskID):
        headers = {"User-Agent": "Mozilla/5.0"}
        with requests.get(url, headers=headers, stream=True, timeout=60) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            progress.update(task, total=total)
            with open(path, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        progress.advance(task, len(chunk))

    @retry(attempts=3, delay=2.0, exceptions=(requests.RequestException, IOError))
    def _stream_urls_to_disk(self, urls: list[str], path: Path, progress: Progress, task: TaskID):
        headers = {"User-Agent": "Mozilla/5.0"}
        with open(path, "wb") as f:
            for url in urls:
                with requests.get(url, headers=headers, stream=True, timeout=60) as r:
                    r.raise_for_status()
                    for chunk in r.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
                            progress.advance(task, len(chunk))

    def download(
        self,
        track,
        progress: Progress,
        task: TaskID,
    ) -> DownloadResult:
        info = self._track_to_info(track)
        dest = self.cfg.download_dir
        dest.mkdir(parents=True, exist_ok=True)

        stem = sanitize_filename(
            self.cfg.filename_template.format(artist=info.artist, title=info.title)
        )
        try:
            stream_source = self._get_stream_source(track)
        except Exception as e:
            return DownloadResult(track=info, success=False, error=str(e))
        if not stream_source:
            existing = self._existing_audio_download(dest, stem) if self.cfg.skip_existing else None
            if existing:
                self._tag_if_enabled(existing, info)
                progress.update(task, description=f"[muted]Skipped  {info.artist} - {_truncate(info.title)}[/muted]")
                return DownloadResult(track=info, success=True, path=existing, source="skipped")
            return DownloadResult(track=info, success=False, error="No stream URL available")

        ext = (stream_source.extension or f".{self._extension()}").lstrip(".")
        path = dest / f"{stem}.{ext}"

        if path.exists() and path.stat().st_size > 0:
            path = normalize_audio_extension(path)

        if self.cfg.skip_existing and path.exists() and path.stat().st_size > 0:
            self._tag_if_enabled(path, info)
            progress.update(task, description=f"[muted]Skipped  {info.artist} - {_truncate(info.title)}[/muted]")
            return DownloadResult(track=info, success=True, path=path, source="skipped")

        if self.cfg.skip_existing:
            existing = self._existing_audio_download(dest, stem)
            if existing:
                self._tag_if_enabled(existing, info)
                progress.update(task, description=f"[muted]Skipped  {info.artist} - {_truncate(info.title)}[/muted]")
                return DownloadResult(track=info, success=True, path=existing, source="skipped")

        audio_info_list = []
        if stream_source.codec:
            audio_info_list.append(stream_source.codec)
        if stream_source.bit_depth:
            audio_info_list.append(f"{stream_source.bit_depth}-bit")
        if stream_source.sample_rate:
            audio_info_list.append(f"{stream_source.sample_rate/1000:g}kHz")

        audio_info_str = " ".join(audio_info_list)
        info.audio_info = audio_info_str

        desc = f"[source]Tidal[/source] [track]{_truncate(info.title)}[/track] [muted]·[/muted] [artist]{info.artist}[/artist]"
        if audio_info_str:
            desc += f" [muted]·[/muted] [quality]{audio_info_str}[/quality]"

        progress.update(
            task,
            description=desc,
        )

        try:
            if len(stream_source.urls) == 1:
                self._stream_to_disk(stream_source.urls[0], path, progress, task)
            else:
                self._stream_urls_to_disk(stream_source.urls, path, progress, task)
        except Exception as e:
            return DownloadResult(track=info, success=False, error=str(e))

        # Determine actual codec by probing the file. Tidal's hi-res streams
        # are delivered via an MPEG-DASH manifest whose Representation@codecs
        # attribute often reports "mp4a.40.2" even though the audio samples
        # inside the MP4 segments are FLAC. Trusting the manifest string here
        # caused legitimate hi-res FLAC downloads to be flagged as AAC and
        # rejected. mutagen reads the real codec from the container header.
        actual_codec = stream_source.codec.upper()
        if HAS_MUTAGEN and path.exists() and path.stat().st_size > 0:
            probe_suffix = path.suffix.lower()
            if probe_suffix in (".m4a", ".mp4", ".aac"):
                try:
                    probe = MP4(path)
                    probed = (getattr(probe.info, "codec", "") or "").upper() if probe.info else ""
                    if probed:
                        actual_codec = probed
                except Exception as e:
                    log.debug(f"Codec probe failed for {path.name}: {e}")
            elif probe_suffix == ".flac":
                actual_codec = "FLAC"

        # Now run the extension/remux pass. If the file is FLAC-in-MP4 we
        # leave the .m4a extension alone here — the unwrap helper called by
        # the metadata tagger will convert it to a native .flac container.
        if "FLAC" not in actual_codec:
            path = normalize_audio_extension(path)

        got_flac = "FLAC" in actual_codec or path.suffix.lower() == ".flac"
        if self._wants_lossless() and not got_flac:
            # Tidal couldn't give us lossless for this track (region lock,
            # not-yet-mastered, subscription cap, …). That's a soft fail:
            # we still have a working AAC/MP4 file from Tidal, which is
            # better than dropping to YouTube. Note it and move on.
            returned = actual_codec or path.suffix
            log.info(
                f"Tidal returned {returned} for '{info.title}' "
                f"(requested {self.cfg.tidal_quality or 'master'}); using it as-is."
            )

        self._tag_if_enabled(path, info)

        return DownloadResult(track=info, success=True, path=path, source="tidal")

    # --- URL parsing -------------------------------------------------------

    @staticmethod
    def _find(url: str, patterns: list[str]) -> Optional[str]:
        for p in patterns:
            m = re.search(p, url)
            if m:
                return m.group(1)
        return None

    def track_id(self, url: str) -> Optional[str]:
        return self._find(url, [r"/track/(\d+)", r"browse/track/(\d+)"])

    def playlist_id(self, url: str) -> Optional[str]:
        return self._find(url, [r"/playlist/([a-zA-Z0-9-]+)", r"browse/playlist/([a-zA-Z0-9-]+)"])

    def album_id(self, url: str) -> Optional[str]:
        return self._find(url, [r"/album/(\d+)", r"browse/album/(\d+)"])

    def resolve_tracks(self, url: str) -> tuple[list, str]:
        """Return (list_of_tidal_track_objects, collection_name)."""
        if tid := self.track_id(url):
            t = self.session.track(int(tid))
            return [t], t.name

        if pid := self.playlist_id(url):
            pl = self.session.playlist(pid)
            return pl.tracks(), pl.name

        if aid := self.album_id(url):
            al = self.session.album(int(aid))
            return al.tracks(), f"{al.name} — {al.artist.name}"

        return [], ""


# ---------------------------------------------------------------------------
# Apple Music scraper
# ---------------------------------------------------------------------------

class AppleMusicScraper:
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }

    @retry(attempts=3, delay=1.5, exceptions=(requests.RequestException,))
    def fetch(self, url: str) -> list[TrackInfo]:
        r = requests.get(url, headers=self.HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        tracks = self._parse_ld_json(soup) or self._parse_og(soup)
        return [t for t in tracks if t.title]

    def _parse_ld_json(self, soup) -> list[TrackInfo]:
        tag = (
            soup.find("script", {"name": "schema:music-album"})
            or soup.find("script", {"type": "application/ld+json"})
        )
        if not (tag and tag.string):
            return []
        try:
            data = json.loads(tag.string)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("@type") == "MusicRecording":
                        return [TrackInfo(
                            title=item.get("name", ""),
                            artist=item.get("byArtist", {}).get("name", ""),
                            album=item.get("inAlbum", {}).get("name", ""),
                        )]
                    if isinstance(item, dict) and "track" in item:
                        return [
                            TrackInfo(
                                title=track_item.get("name", ""),
                                artist=track_item.get("byArtist", {}).get("name", ""),
                                album=item.get("name", ""),
                            )
                            for track_item in item["track"]
                        ]

            if data.get("@type") == "MusicRecording":
                return [TrackInfo(
                    title=data.get("name", ""),
                    artist=data.get("byArtist", {}).get("name", ""),
                    album=data.get("inAlbum", {}).get("name", ""),
                )]
            if "track" in data:
                return [
                    TrackInfo(
                        title=item.get("name", ""),
                        artist=item.get("byArtist", {}).get("name", ""),
                        album=data.get("name", ""),
                    )
                    for item in data["track"]
                ]
        except Exception as e:
            log.debug(f"LD+JSON parse failed: {e}")
        return []

    def _parse_og(self, soup) -> list[TrackInfo]:
        meta = soup.find("meta", property="og:title")
        if not (meta and meta.get("content")):
            return []
        content = (
            meta["content"]
            .replace(" on Apple Music", "")
            .replace(" on Apple\xa0Music", "")
            .strip()
        )
        if " by " in content:
            title, artist = content.split(" by ", 1)
            return [TrackInfo(title=title.strip(), artist=artist.strip())]
        return [TrackInfo(title=content, artist="")]


# ---------------------------------------------------------------------------
# Spotify metadata enrichment
# ---------------------------------------------------------------------------

class SpotifyEnricher:
    def __init__(self, client_id: str, client_secret: str):
        self.client = None
        if not (HAS_SPOTIPY and client_id and client_secret):
            return
        try:
            self.client = spotipy.Spotify(
                auth_manager=SpotifyClientCredentials(
                    client_id=client_id,
                    client_secret=client_secret,
                )
            )
        except Exception as e:
            log.warning(f"Spotify init failed: {e}")

    def is_available(self) -> bool:
        return self.client is not None

    @staticmethod
    def _find(url: str, patterns: list[str]) -> Optional[str]:
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def can_resolve_url(self, url: str) -> bool:
        return any((
            self.track_id(url),
            self.album_id(url),
            self.playlist_id(url),
        ))

    def track_id(self, url: str) -> Optional[str]:
        return self._find(url, [
            r"open\.spotify\.com/track/([A-Za-z0-9]+)",
            r"spotify:track:([A-Za-z0-9]+)",
        ])

    def album_id(self, url: str) -> Optional[str]:
        return self._find(url, [
            r"open\.spotify\.com/album/([A-Za-z0-9]+)",
            r"spotify:album:([A-Za-z0-9]+)",
        ])

    def playlist_id(self, url: str) -> Optional[str]:
        return self._find(url, [
            r"open\.spotify\.com/playlist/([A-Za-z0-9]+)",
            r"spotify:playlist:([A-Za-z0-9]+)",
        ])

    @staticmethod
    def _artists_text(artists: list[dict]) -> str:
        names = [artist.get("name", "") for artist in artists if artist.get("name")]
        return ", ".join(names)

    @staticmethod
    def _album_year(album: Optional[dict]) -> str:
        return (album or {}).get("release_date", "")[:4]

    @staticmethod
    def _album_cover(album: Optional[dict]) -> str:
        images = (album or {}).get("images", [])
        return images[0]["url"] if images else ""

    def _merge_info(self, base: TrackInfo, spotify_info: TrackInfo) -> TrackInfo:
        return TrackInfo(
            title=spotify_info.title or base.title,
            artist=spotify_info.artist or base.artist,
            album=spotify_info.album or base.album,
            track_number=spotify_info.track_number or base.track_number,
            year=spotify_info.year or base.year,
            genre=spotify_info.genre or base.genre,
            cover_url=spotify_info.cover_url or base.cover_url,
            duration_sec=spotify_info.duration_sec or base.duration_sec,
            tidal_id=base.tidal_id,
            spotify_id=spotify_info.spotify_id,
        )

    def _track_from_item(self, item: dict, album_override: Optional[dict] = None) -> TrackInfo:
        album = album_override or item.get("album") or {}
        return TrackInfo(
            title=item.get("name", ""),
            artist=self._artists_text(item.get("artists", [])),
            album=album.get("name", ""),
            track_number=item.get("track_number", 0),
            year=self._album_year(album),
            cover_url=self._album_cover(album),
            duration_sec=int((item.get("duration_ms") or 0) / 1000),
            spotify_id=item.get("id"),
        )

    def _page_items(self, page: dict) -> list[dict]:
        if not self.client:
            return []
        items = list(page.get("items", []))
        while page.get("next"):
            page = self.client.next(page)
            items.extend(page.get("items", []))
        return items

    def resolve_tracks(self, url: str) -> tuple[list[TrackInfo], str]:
        if not self.client:
            return [], ""
        try:
            if track_id := self.track_id(url):
                track = self.client.track(track_id)
                return [self._track_from_item(track)], track.get("name", "Spotify track")

            if album_id := self.album_id(url):
                album = self.client.album(album_id)
                album_tracks = self._page_items(album.get("tracks", {}))
                tracks = [self._track_from_item(track, album_override=album) for track in album_tracks]
                return tracks, album.get("name", "Spotify album")

            if playlist_id := self.playlist_id(url):
                playlist = self.client.playlist(playlist_id)
                playlist_items = self._page_items(
                    self.client.playlist_items(playlist_id, additional_types=("track",))
                )
                tracks = []
                for item in playlist_items:
                    track = item.get("track")
                    if track and track.get("type") == "track":
                        tracks.append(self._track_from_item(track))
                return tracks, playlist.get("name", "Spotify playlist")
        except Exception as e:
            log.debug(f"Spotify resolve failed: {e}")
        return [], ""

    def match_track(self, info: TrackInfo) -> Optional[TrackInfo]:
        if not self.client:
            return None
        try:
            query_parts = [f"track:{info.title}", f"artist:{info.artist}"]
            if info.album:
                query_parts.append(f"album:{info.album}")
            res = self.client.search(
                q=" ".join(query_parts),
                type="track",
                limit=1,
            )
            items = res.get("tracks", {}).get("items", [])
            if not items:
                return None
            return self._track_from_item(items[0])
        except Exception as e:
            log.debug(f"Spotify match failed: {e}")
            return None

    def enrich(self, info: TrackInfo) -> TrackInfo:
        """Return a copy of TrackInfo with cleaned/enriched metadata."""
        match = self.match_track(info)
        return self._merge_info(info, match) if match else info


# ---------------------------------------------------------------------------
# YouTube downloader (fallback)
# ---------------------------------------------------------------------------

class YouTubeDownloader:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    @staticmethod
    def _find_audio_file(dest: Path, filename: str) -> Optional[Path]:
        candidates = sorted(
            dest.glob(f"{filename}.*"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for candidate in candidates:
            if candidate.suffix.lower() in (".mp3", ".m4a", ".aac", ".flac"):
                return candidate
        return None

    def download(
        self,
        info: TrackInfo,
        progress: Progress,
        task: TaskID,
        source_label: str = "YouTube",
        result_source: str = "youtube",
    ) -> DownloadResult:
        if not HAS_YTDLP:
            return DownloadResult(track=info, success=False, error="yt-dlp not installed")

        dest = self.cfg.download_dir
        dest.mkdir(parents=True, exist_ok=True)

        query = f"{info.title} {info.artist} official audio"
        filename = sanitize_filename(
            self.cfg.filename_template.format(artist=info.artist, title=info.title)
        )
        out_tmpl = str(dest / f"{filename}.%(ext)s")

        existing = self._find_audio_file(dest, filename)
        if self.cfg.skip_existing and existing and existing.stat().st_size > 0:
            progress.update(task, description=f"[muted]Skipped  {info.artist} - {_truncate(info.title)}[/muted]")
            return DownloadResult(track=info, success=True, path=existing, source="skipped")

        progress.update(
            task,
            description=(
                f"[source]{source_label}[/source] [track]{_truncate(info.title)}[/track] "
                f"[muted]-[/muted] [artist]{info.artist}[/artist]"
            ),
        )

        class ProgressHook:
            def __init__(self, prog, t):
                self.prog = prog
                self.task = t
                self._started = False

            def __call__(self, d):
                if d["status"] == "downloading":
                    total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                    dl = d.get("downloaded_bytes", 0)
                    if not self._started and total:
                        self.prog.update(self.task, total=total)
                        self._started = True
                    self.prog.update(self.task, completed=dl)

        opts = {
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": self.cfg.youtube_quality,
            }],
            "outtmpl": out_tmpl,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "progress_hooks": [ProgressHook(progress, task)],
        }

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([f"ytsearch1:{query}"])
        except Exception as e:
            return DownloadResult(track=info, success=False, error=f"yt-dlp failed: {e}")

        candidate = self._find_audio_file(dest, filename)
        if candidate:
            PostDownloadMetadataScript.append(candidate, info, enabled=self.cfg.embed_metadata)
            return DownloadResult(
                track=info,
                success=True,
                path=candidate,
                source=result_source,
            )

        return DownloadResult(
            track=info,
            success=False,
            error=f"Downloaded file not found for tagging: {filename}",
        )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class NovaReap:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.tidal: Optional[TidalClient] = None
        self.youtube = YouTubeDownloader(cfg)
        self.spotify = SpotifyEnricher(
            cfg.spotify_client_id,
            cfg.spotify_client_secret,
        )

    def _get_tidal(self) -> Optional[TidalClient]:
        if not HAS_TIDAL:
            return None
        if self.tidal is None:
            self.tidal = TidalClient(self.cfg)
        return self.tidal

    def _make_progress(self) -> Progress:
        return Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}", justify="left"),
            BarColumn(bar_width=30),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=console,
            transient=False,
        )

    def _download_one(
        self,
        tidal_track,
        info: Optional[TrackInfo],
        progress: Progress,
    ) -> DownloadResult:
        task = progress.add_task("", total=None)
        used_spotify_fallback = bool(info and info.spotify_id)

        if tidal_track and self.tidal and self.tidal.is_available():
            result = self.tidal.download(tidal_track, progress, task)
            if result.success:
                progress.update(task, completed=progress.tasks[task].total or 1)
                return result
            if info is None:
                info = self.tidal._track_to_info(tidal_track)
            spotify_match = self.spotify.match_track(info)
            if spotify_match:
                info = self.spotify._merge_info(info, spotify_match)
                used_spotify_fallback = True
                console.print(
                    f"  [warning]Tidal failed ({result.error}), trying Spotify-matched fallback...[/warning]"
                )
            else:
                console.print(f"  [warning]Tidal failed ({result.error}), trying YouTube...[/warning]")

        if info:
            if not info.spotify_id:
                enriched = self.spotify.enrich(info)
                used_spotify_fallback = used_spotify_fallback or bool(enriched.spotify_id)
                info = enriched
            result = self.youtube.download(
                info,
                progress,
                task,
                source_label="Spotify->YT" if used_spotify_fallback or info.spotify_id else "YouTube",
                result_source="spotify->youtube" if used_spotify_fallback or info.spotify_id else "youtube",
            )
            progress.update(task, completed=progress.tasks[task].total or 1)
            return result
        return DownloadResult(
            track=info or TrackInfo(title="?", artist="?"),
            success=False,
            error="No download method available",
        )

    def download_url(self, url: str):
        """Main entry point: resolve a URL and download everything in it."""
        console.print()
        url_lower = url.lower()

        if "tidal.com" in url_lower:
            tidal = self._get_tidal()
            if not (tidal and tidal.is_available()):
                console.print("[error]Tidal is not available. Check your session.[/error]")
                return

            tracks, name = tidal.resolve_tracks(url)
            if not tracks:
                console.print("[error]Could not resolve any tracks from that URL.[/error]")
                return

            self._run_queue(
                [(t, None) for t in tracks],
                collection=name,
                source_label="Tidal",
            )

        elif self.spotify.can_resolve_url(url):
            if not self.spotify.is_available():
                console.print(
                    "[error]Spotify URL support requires spotipy and a Spotify client ID/secret. "
                    "Run `python novareap.py configure` first.[/error]"
                )
                return

            console.print("[info]Fetching Spotify metadata...[/info]")
            track_infos, name = self.spotify.resolve_tracks(url)
            if not track_infos:
                console.print("[error]No tracks found at that Spotify URL.[/error]")
                return
            self._run_queue(
                [(None, info) for info in track_infos],
                collection=name or track_infos[0].album or "Spotify",
                source_label="Spotify -> YouTube",
            )

        else:
            console.print("[info]Fetching Apple Music metadata...[/info]")
            track_infos = AppleMusicScraper().fetch(url)
            if not track_infos:
                console.print("[error]No tracks found at that URL.[/error]")
                return
            self._run_queue(
                [(None, info) for info in track_infos],
                collection=track_infos[0].album or "Apple Music",
                source_label="Apple Music -> YouTube",
            )

    def _run_queue(
        self,
        queue: list[tuple],
        collection: str,
        source_label: str,
    ):
        total = len(queue)
        console.print(Panel(
            f"[bold]{collection}[/bold]\n"
            f"[muted]{total} track{'s' if total != 1 else ''} · source: {source_label}[/muted]\n"
            f"[muted]Output: {self.cfg.download_dir}[/muted]",
            border_style="cyan",
        ))

        results: list[DownloadResult] = []

        with self._make_progress() as progress:
            overall = progress.add_task(
                f"[muted]0/{total}[/muted]", total=total
            )

            with ThreadPoolExecutor(max_workers=self.cfg.concurrent_downloads) as pool:
                future_map = {
                    pool.submit(self._download_one, tidal_t, info_t, progress): i
                    for i, (tidal_t, info_t) in enumerate(queue)
                }
                for future in as_completed(future_map):
                    result = future.result()
                    results.append(result)
                    done = len(results)
                    progress.update(overall, completed=done, description=f"[muted]{done}/{total}[/muted]")
                    time.sleep(0.4)

        self._print_summary(results)

    def _print_summary(self, results: list[DownloadResult]):
        ok = [r for r in results if r.success and r.source != "skipped"]
        skipped = [r for r in results if r.source == "skipped"]
        failed = [r for r in results if not r.success]

        table = Table(box=box.ROUNDED, border_style="dim", show_header=True, expand=False)
        table.add_column("Status", style="bold", width=8)
        table.add_column("Track", style="track")
        table.add_column("Artist", style="artist")
        table.add_column("Source", style="source")

        for r in sorted(results, key=lambda x: x.track.title):
            if r.source == "skipped":
                status = "[muted]SKIP[/muted]"
            elif r.success:
                status = "[success]OK[/success]"
            else:
                status = "[error]FAIL[/error]"
            table.add_row(
                status,
                _truncate(r.track.title),
                r.track.artist,
                r.source if r.success else r.error[:40],
            )

        console.print()
        console.print(table)
        console.print(
            f"\n[success]{len(ok)} downloaded[/success]  "
            f"[muted]{len(skipped)} skipped  [/muted]"
            f"{'[error]' + str(len(failed)) + ' failed[/error]' if failed else ''}"
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """NovaReap - master-quality music sync."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command()
@click.argument("urls", nargs=-1, required=True)
@click.option("--quality", "-q", default=None, help="Tidal quality: low | high | master")
@click.option("--output", "-o", default=None, help="Download directory")
@click.option("--concurrent", "-c", default=None, type=int, help="Concurrent downloads (default: 3)")
@click.option("--no-skip", is_flag=True, help="Re-download even if file exists")
@click.option("--no-metadata", is_flag=True, help="Skip metadata/cover-art embedding")
@click.option("--config", default=str(DEFAULT_CONFIG_PATH), show_default=True,
              help="Path to config file")
def download(urls, quality, output, concurrent, no_skip, no_metadata, config):
    """Download one or more Tidal/Spotify/Apple Music URLs."""
    _print_banner()

    cfg = Config.load(Path(config))
    if quality:
        cfg.tidal_quality = _normalize_tidal_quality(quality)
    if output:
        cfg.download_dir = Path(output)
    if concurrent:
        cfg.concurrent_downloads = concurrent
    if no_skip:
        cfg.skip_existing = False
    if no_metadata:
        cfg.embed_metadata = False

    syncer = NovaReap(cfg)
    for url in urls:
        syncer.download_url(url)


@cli.command()
@click.option("--spotify-id", default="", help="Spotify client ID")
@click.option("--spotify-secret", default="", help="Spotify client secret")
@click.option("--output", default="", help="Default download directory")
@click.option("--quality", default="master", help="Tidal quality: low | high | master")
@click.option("--concurrent", default=3, type=int, help="Concurrent downloads")
def configure(spotify_id, spotify_secret, output, quality, concurrent):
    """Interactively set up NovaReap configuration."""
    _print_banner()

    path = DEFAULT_CONFIG_PATH
    cfg = Config.load(path)

    console.print(Panel("[bold]NovaReap configuration[/bold]", border_style="cyan"))

    if not spotify_id:
        spotify_id = click.prompt(
            "Spotify client ID (needed for Spotify URLs + preferred fallback)", default=cfg.spotify_client_id
        )
    if not spotify_secret:
        spotify_secret = click.prompt(
            "Spotify client secret (needed for Spotify URLs + preferred fallback)", default=cfg.spotify_client_secret
        )
    if not output:
        output = click.prompt("Download directory", default=str(cfg.download_dir))

    quality = click.prompt("Tidal quality [low/high/master]", default=cfg.tidal_quality)
    concurrent = click.prompt("Concurrent downloads", default=cfg.concurrent_downloads)

    cfg.spotify_client_id = spotify_id
    cfg.spotify_client_secret = spotify_secret
    cfg.download_dir = Path(output)
    cfg.tidal_quality = _normalize_tidal_quality(quality)
    cfg.concurrent_downloads = concurrent

    cfg.download_dir.mkdir(parents=True, exist_ok=True)
    cfg.save(path)
    console.print(f"[success]Config saved -> {path}[/success]")
    console.print(f"[success]Download directory ready -> {cfg.download_dir}[/success]\n")
    _print_setup_checks(cfg, path)


@cli.command()
@click.option("--quality", "-q", default=None, help="Tidal quality: low | high | master")
def auth(quality):
    """Authenticate with Tidal (saves session for future use)."""
    _print_banner()
    cfg = Config.load()
    if quality:
        cfg.tidal_quality = _normalize_tidal_quality(quality)
    if not HAS_TIDAL:
        console.print("[error]tidalapi is not installed.[/error]")
        sys.exit(1)
    TidalClient(cfg)
    console.print("[success]Tidal session ready.[/success]")


@cli.command()
@click.argument("file_path")
@click.option("--title", default="", help="Track title")
@click.option("--artist", default="", help="Track artist")
@click.option("--album", default="", help="Album name")
@click.option("--track-number", default=0, type=int, help="Track number")
@click.option("--year", default="", help="Release year/date")
@click.option("--genre", default="", help="Genre")
@click.option("--cover-url", default="", help="Cover art image URL")
def meta(file_path, title, artist, album, track_number, year, genre, cover_url):
    """Append metadata to an existing audio file."""
    _print_banner()
    path = Path(file_path).expanduser()
    if not path.exists() or not path.is_file():
        console.print(f"[error]File not found -> {path}[/error]")
        sys.exit(1)
    path = normalize_audio_extension(path)

    info = metadata_info_from_file(
        path,
        title=title,
        artist=artist,
        album=album,
        track_number=track_number,
        year=year,
        genre=genre,
        cover_url=cover_url,
    )
    resolved = PostDownloadMetadataScript.append(path, info, enabled=True)
    if not resolved:
        console.print(f"[error]Metadata could not be appended -> {path}[/error]")
        sys.exit(1)
    console.print(f"[success]Metadata appended -> {resolved}[/success]")


def _status_markup(status: str) -> str:
    if status == "ok":
        return "[success]ok[/success]"
    if status == "optional":
        return "[warning]optional[/warning]"
    return "[error]missing[/error]"


def _print_setup_checks(cfg: Config, config_path: Path = DEFAULT_CONFIG_PATH):
    table = Table(box=box.SIMPLE, show_header=True)
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Detail", style="muted")
    table.add_column("Fix")
    for check in collect_setup_checks(cfg, config_path):
        table.add_row(check.name, _status_markup(check.status), check.detail, check.fix)
    console.print(table)


@cli.command()
@click.option("--spotify-id", default="", help="Spotify client ID")
@click.option("--spotify-secret", default="", help="Spotify client secret")
@click.option("--skip-spotify", is_flag=True, help="Skip optional Spotify credentials")
@click.option("--output", default="", help="Default download directory")
@click.option("--quality", default="master", help="Tidal quality: low | high | master")
@click.option("--concurrent", default=3, type=int, help="Concurrent downloads")
def setup(spotify_id, spotify_secret, skip_spotify, output, quality, concurrent):
    """Create config/directories and print first-run diagnostics."""
    _print_banner()
    cfg = Config.load()

    console.print(Panel("[bold]First-time setup[/bold]", border_style="cyan"))
    if not output:
        output = click.prompt("Download directory", default=str(cfg.download_dir))
    if not skip_spotify and not spotify_id:
        spotify_id = click.prompt(
            "Spotify client ID (optional; press Enter to skip)",
            default=cfg.spotify_client_id,
            show_default=False,
        )
    if not skip_spotify and not spotify_secret:
        spotify_secret = click.prompt(
            "Spotify client secret (optional; press Enter to skip)",
            default=cfg.spotify_client_secret,
            show_default=False,
            hide_input=True,
        )

    cfg.download_dir = Path(output)
    cfg.tidal_quality = _normalize_tidal_quality(quality)
    cfg.concurrent_downloads = concurrent
    if not skip_spotify:
        cfg.spotify_client_id = spotify_id
        cfg.spotify_client_secret = spotify_secret

    cfg.download_dir.mkdir(parents=True, exist_ok=True)
    cfg.save(DEFAULT_CONFIG_PATH)

    console.print(f"[success]Config saved -> {DEFAULT_CONFIG_PATH}[/success]")
    console.print(f"[success]Download directory ready -> {cfg.download_dir}[/success]\n")
    _print_setup_checks(cfg)


@cli.command()
def doctor():
    """Check Python packages, FFmpeg, config, and output directory."""
    _print_banner()
    cfg = Config.load()
    _print_setup_checks(cfg)


@cli.command()
def info():
    """Show current configuration and dependency status."""
    _print_banner()
    cfg = Config.load()

    _print_setup_checks(cfg)
    console.print()

    table = Table(box=box.SIMPLE, show_header=False)
    table.add_column(style="muted", width=22)
    table.add_column(style="bold")

    def dep(name, available):
        return "[success]✓ installed[/success]" if available else "[error]✗ missing[/error]"

    table.add_row("tidalapi", dep("tidalapi", HAS_TIDAL))
    table.add_row("yt-dlp", dep("yt-dlp", HAS_YTDLP))
    table.add_row("spotipy", dep("spotipy", HAS_SPOTIPY))
    table.add_row("spotify ready", str(bool(cfg.spotify_client_id and cfg.spotify_client_secret)))
    table.add_row("mutagen", dep("mutagen", HAS_MUTAGEN))
    table.add_row("", "")
    table.add_row("quality", cfg.tidal_quality)
    table.add_row("output", str(cfg.download_dir))
    table.add_row("concurrent", str(cfg.concurrent_downloads))
    table.add_row("skip exist", str(cfg.skip_existing))
    table.add_row("metadata", str(cfg.embed_metadata))
    table.add_row("config", str(DEFAULT_CONFIG_PATH))
    table.add_row("session", str(cfg.session_file))

    console.print(table)


def _print_banner():
    console.print(Panel(
        "[bold cyan]NovaReap[/bold cyan]  [muted]master-quality music sync[/muted]",
        border_style="dim",
        padding=(0, 2),
    ))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cli()