import os
import sys
import time
import fcntl
import shutil
import logging
import subprocess
import threading
import urllib.request
import urllib.error
import zipfile
import tarfile
from pathlib import Path

import streamlit as st


# ============================================================
# SPMA - FULL SELF-CONTAINED VERSION
# ============================================================

BASE_DIR = Path("/mount/src/spma")

# ------------------------------------------------------------
# Versions - DO NOT CHANGE
# ------------------------------------------------------------

SPOTDL_VERSION = "4.4.11"
YTDLP_VERSION = "2026.06.09"
YTDLP_EJS_VERSION = "0.8.0"
BGUTIL_VERSION = "2.0.0"
DENO_VERSION = "2.9.6"
FFMPEG_VERSION = "7.0.2"

SPOTDL_GIT = (
    "git+https://github.com/TzurSoffer/spotify-downloader"
    "@29cb0b0669d5c107331b0912fdef73967b47493e"
)

# ------------------------------------------------------------
# Local directories
# ------------------------------------------------------------

BIN_DIR = BASE_DIR / ".bin"

SPOTDL_VENV = BASE_DIR / ".spotdl_venv"
SPOTDL_PYTHON = SPOTDL_VENV / "bin" / "python"
SPOTDL_BIN = SPOTDL_VENV / "bin" / "spotdl"

BGUTIL_DIR = BASE_DIR / ".bgutil-ytdlp-pot-provider"

DOWNLOAD_DIR = BASE_DIR / "downloads"
YOUTUBE_TEST_DIR = BASE_DIR / ".youtube_test"

CACHE_DIR = BASE_DIR / ".spma_cache"

DENO_BIN = BIN_DIR / "deno"
FFMPEG_BIN = BIN_DIR / "ffmpeg"
FFPROBE_BIN = BIN_DIR / "ffprobe"

# ------------------------------------------------------------
# bgutil
# ------------------------------------------------------------

BGUTIL_HOST = "127.0.0.1"
BGUTIL_PORT = 4416
BGUTIL_URL = f"http://{BGUTIL_HOST}:{BGUTIL_PORT}"

# ------------------------------------------------------------
# Telegram lock
# ------------------------------------------------------------

BOT_LOCK_FILE = "/tmp/spma_telegram_bot.lock"

BOT_LOCK_FD = None
BGUTIL_PROCESS = None
TELEGRAM_UPDATER = None

# ------------------------------------------------------------
# YouTube configuration
# ------------------------------------------------------------

# IMPORTANT:
#
# DO NOT use android_vr.
#
# The previous setup generated an ANDROID_VR googlevideo URL
# which resulted in HTTP 403 during the actual audio download.
#
# mweb + fetch_pot=always + bgutil is used instead.
#
YOUTUBE_CLIENT_ARGS = (
    "youtube:player_client=mweb;fetch_pot=always"
)

YOUTUBE_POT_ARGS = (
    f"youtubepot-bgutilhttp:base_url={BGUTIL_URL}"
)


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger("SPMA")


# ============================================================
# STREAMLIT SECRETS
# ============================================================

def get_secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, default)

        if value is None:
            return default

        return str(value).strip()

    except Exception:
        return os.environ.get(name, default).strip()


TELEGRAM_TOKEN = get_secret("TELEGRAM_TOKEN")

SPOTIFY_CLIENT_ID = get_secret(
    "SPOTIFY_CLIENT_ID"
)

SPOTIFY_CLIENT_SECRET = get_secret(
    "SPOTIFY_CLIENT_SECRET"
)


# ============================================================
# DIRECTORY SETUP
# ============================================================

def create_directories():
    directories = [
        BASE_DIR,
        BIN_DIR,
        SPOTDL_VENV,
        DOWNLOAD_DIR,
        YOUTUBE_TEST_DIR,
        CACHE_DIR,
    ]

    for directory in directories:
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )


# ============================================================
# ENVIRONMENT
# ============================================================

def configure_environment():
    create_directories()

    path_parts = [
        str(BIN_DIR),
        str(SPOTDL_VENV / "bin"),
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
    ]

    current_path = os.environ.get(
        "PATH",
        "",
    )

    for item in current_path.split(":"):
        if item and item not in path_parts:
            path_parts.append(item)

    os.environ["PATH"] = ":".join(path_parts)

    # Spotify
    if SPOTIFY_CLIENT_ID:
        os.environ["SPOTIPY_CLIENT_ID"] = (
            SPOTIFY_CLIENT_ID
        )

        os.environ["SPOTIFY_CLIENT_ID"] = (
            SPOTIFY_CLIENT_ID
        )

    if SPOTIFY_CLIENT_SECRET:
        os.environ["SPOTIPY_CLIENT_SECRET"] = (
            SPOTIFY_CLIENT_SECRET
        )

        os.environ["SPOTIFY_CLIENT_SECRET"] = (
            SPOTIFY_CLIENT_SECRET
        )

    # FFmpeg
    if FFMPEG_BIN.exists():
        os.environ["FFMPEG_BINARY"] = (
            str(FFMPEG_BIN)
        )

    if FFPROBE_BIN.exists():
        os.environ["FFPROBE_BINARY"] = (
            str(FFPROBE_BIN)
        )

    # Deno
    if DENO_BIN.exists():
        os.environ["DENO_BINARY"] = (
            str(DENO_BIN)
        )

    logger.info(
        "Environment configured."
    )


# ============================================================
# COMMAND HELPER
# ============================================================

def run_command(
    command,
    timeout=None,
    cwd=None,
    env=None,
    check=False,
):
    logger.info(
        "Running: %s",
        " ".join(map(str, command)),
    )

    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=env,
        )

        if result.stdout:
            output = result.stdout

            if len(output) > 16000:
                output = output[-16000:]

            logger.info(
                "\n%s",
                output,
            )

        if (
            check
            and result.returncode != 0
        ):
            raise RuntimeError(
                f"Command failed: "
                f"{result.returncode}"
            )

        return result

    except subprocess.TimeoutExpired:
        logger.error(
            "Command timed out."
        )
        return None

    except Exception as exc:
        logger.exception(
            "Command error: %s",
            exc,
        )
        return None


# ============================================================
# DOWNLOAD HELPER
# ============================================================

def download_file(
    url: str,
    destination: Path,
    timeout: int = 300,
):
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_file = destination.with_suffix(
        destination.suffix + ".tmp"
    )

    if temp_file.exists():
        try:
            temp_file.unlink()
        except Exception:
            pass

    logger.info(
        "Downloading: %s",
        url,
    )

    logger.info(
        "Destination: %s",
        destination,
    )

    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent":
                    "Mozilla/5.0 "
                    "(X11; Linux x86_64) "
                    "AppleWebKit/537.36 "
                    "Chrome/140 Safari/537.36"
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=timeout,
        ) as response:

            total = response.headers.get(
                "Content-Length"
            )

            total = (
                int(total)
                if total
                else None
            )

            downloaded = 0

            with open(
                temp_file,
                "wb",
            ) as output:

                while True:
                    chunk = response.read(
                        1024 * 1024
                    )

                    if not chunk:
                        break

                    output.write(chunk)

                    downloaded += len(chunk)

                    if total:
                        percent = (
                            downloaded
                            * 100
                            / total
                        )

                        logger.info(
                            "Download %.1f%%",
                            percent,
                        )

        temp_file.replace(
            destination
        )

        logger.info(
            "Download complete."
        )

        return True

    except Exception as exc:
        logger.exception(
            "Download failed: %s",
            exc,
        )

        try:
            if temp_file.exists():
                temp_file.unlink()
        except Exception:
            pass

        return False


# ============================================================
# DENO
# ============================================================

def install_deno():
    if (
        DENO_BIN.exists()
        and os.access(
            DENO_BIN,
            os.X_OK,
        )
    ):
        result = run_command(
            [
                str(DENO_BIN),
                "--version",
            ],
            timeout=30,
        )

        if (
            result
            and result.returncode == 0
        ):
            logger.info(
                "Deno already installed."
            )
            return True

    logger.info(
        "Installing Deno %s...",
        DENO_VERSION,
    )

    url = (
        "https://dl.deno.land/release/"
        f"v{DENO_VERSION}/"
        "deno-x86_64-unknown-linux-gnu.zip"
    )

    archive = (
        CACHE_DIR
        / f"deno-{DENO_VERSION}.zip"
    )

    if not archive.exists():
        if not download_file(
            url,
            archive,
        ):
            return False

    extract_dir = (
        CACHE_DIR
        / f"deno-{DENO_VERSION}"
    )

    extract_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:
        with zipfile.ZipFile(
            archive,
            "r",
        ) as zf:
            zf.extractall(
                extract_dir
            )

        extracted = (
            extract_dir / "deno"
        )

        if not extracted.exists():
            logger.error(
                "Deno binary missing "
                "after extraction."
            )
            return False

        shutil.copy2(
            extracted,
            DENO_BIN,
        )

        os.chmod(
            DENO_BIN,
            0o755,
        )

    except Exception as exc:
        logger.exception(
            "Deno extraction failed: %s",
            exc,
        )
        return False

    result = run_command(
        [
            str(DENO_BIN),
            "--version",
        ],
        timeout=30,
    )

    if (
        result
        and result.returncode == 0
    ):
        logger.info(
            "Deno %s: OK",
            DENO_VERSION,
        )
        return True

    return False


# ============================================================
# FFMPEG
# ============================================================

def install_ffmpeg():
    if (
        FFMPEG_BIN.exists()
        and FFPROBE_BIN.exists()
        and os.access(
            FFMPEG_BIN,
            os.X_OK,
        )
    ):
        result = run_command(
            [
                str(FFMPEG_BIN),
                "-version",
            ],
            timeout=30,
        )

        if (
            result
            and result.returncode == 0
        ):
            logger.info(
                "FFmpeg already installed."
            )
            return True

    logger.info(
        "Installing FFmpeg %s...",
        FFMPEG_VERSION,
    )

    # Pinned immutable mirror of the
    # John Van Sickle FFmpeg 7.0.2 build.
    url = (
        "https://github.com/"
        "publicala/ffmpeg-static/"
        "releases/download/"
        "v7.0.2/"
        "ffmpeg-7.0.2-amd64-static.tar.xz"
    )

    archive = (
        CACHE_DIR
        / f"ffmpeg-{FFMPEG_VERSION}.tar.xz"
    )

    if not archive.exists():
        if not download_file(
            url,
            archive,
        ):
            return False

    extract_dir = (
        CACHE_DIR
        / f"ffmpeg-{FFMPEG_VERSION}"
    )

    extract_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:
        # Avoid extracting again if binary already exists.
        extracted_ffmpeg = None
        extracted_ffprobe = None

        for path in extract_dir.rglob(
            "ffmpeg"
        ):
            if path.is_file():
                extracted_ffmpeg = path
                break

        for path in extract_dir.rglob(
            "ffprobe"
        ):
            if path.is_file():
                extracted_ffprobe = path
                break

        if (
            extracted_ffmpeg is None
            or extracted_ffprobe is None
        ):
            with tarfile.open(
                archive,
                "r:xz",
            ) as tar:
                tar.extractall(
                    extract_dir
                )

            for path in extract_dir.rglob(
                "ffmpeg"
            ):
                if path.is_file():
                    extracted_ffmpeg = path
                    break

            for path in extract_dir.rglob(
                "ffprobe"
            ):
                if path.is_file():
                    extracted_ffprobe = path
                    break

        if (
            extracted_ffmpeg is None
            or extracted_ffprobe is None
        ):
            logger.error(
                "FFmpeg binaries not found "
                "after extraction."
            )
            return False

        shutil.copy2(
            extracted_ffmpeg,
            FFMPEG_BIN,
        )

        shutil.copy2(
            extracted_ffprobe,
            FFPROBE_BIN,
        )

        os.chmod(
            FFMPEG_BIN,
            0o755,
        )

        os.chmod(
            FFPROBE_BIN,
            0o755,
        )

    except Exception as exc:
        logger.exception(
            "FFmpeg extraction failed: %s",
            exc,
        )
        return False

    result = run_command(
        [
            str(FFMPEG_BIN),
            "-version",
        ],
        timeout=30,
    )

    if (
        result
        and result.returncode == 0
    ):
        logger.info(
            "FFmpeg %s: OK",
            FFMPEG_VERSION,
        )
        return True

    return False


# ============================================================
# SPOTDL ENVIRONMENT
# ============================================================

def install_spotdl():
    if (
        SPOTDL_PYTHON.exists()
        and SPOTDL_BIN.exists()
    ):
        result = run_command(
            [
                str(SPOTDL_PYTHON),
                "-m",
                "pip",
                "show",
                "spotdl",
            ],
            timeout=30,
        )

        if (
            result
            and result.returncode == 0
        ):
            logger.info(
                "spotDL environment already installed."
            )
            return True

    logger.info(
        "Creating spotDL virtual environment..."
    )

    if not SPOTDL_PYTHON.exists():
        result = run_command(
            [
                sys.executable,
                "-m",
                "venv",
                str(SPOTDL_VENV),
            ],
            timeout=180,
        )

        if (
            result is None
            or result.returncode != 0
        ):
            logger.error(
                "Unable to create spotDL venv."
            )
            return False

    logger.info(
        "Upgrading pip..."
    )

    result = run_command(
        [
            str(SPOTDL_PYTHON),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "pip",
            "wheel",
            "setuptools",
        ],
        timeout=300,
    )

    if (
        result is None
        or result.returncode != 0
    ):
        return False

    logger.info(
        "Installing spotDL %s...",
        SPOTDL_VERSION,
    )

    result = run_command(
        [
            str(SPOTDL_PYTHON),
            "-m",
            "pip",
            "install",
            "--upgrade",
            SPOTDL_GIT,
        ],
        timeout=900,
    )

    if (
        result is None
        or result.returncode != 0
    ):
        logger.error(
            "spotDL installation failed."
        )
        return False

    logger.info(
        "Pinning yt-dlp %s...",
        YTDLP_VERSION,
    )

    result = run_command(
        [
            str(SPOTDL_PYTHON),
            "-m",
            "pip",
            "install",
            "--upgrade",
            f"yt-dlp=={YTDLP_VERSION}",
        ],
        timeout=300,
    )

    if (
        result is None
        or result.returncode != 0
    ):
        return False

    logger.info(
        "Installing yt-dlp-ejs %s...",
        YTDLP_EJS_VERSION,
    )

    result = run_command(
        [
            str(SPOTDL_PYTHON),
            "-m",
            "pip",
            "install",
            "--upgrade",
            f"yt-dlp-ejs=={YTDLP_EJS_VERSION}",
        ],
        timeout=300,
    )

    if (
        result is None
        or result.returncode != 0
    ):
        return False

    logger.info(
        "Checking spotDL..."
    )

    result = run_command(
        [
            str(SPOTDL_BIN),
            "--version",
        ],
        timeout=30,
    )

    if (
        result
        and result.returncode == 0
    ):
        logger.info(
            "spotDL %s: OK",
            SPOTDL_VERSION,
        )
        return True

    return False


# ============================================================
# BGUTIL
# ============================================================

def install_bgutil():
    if (
        BGUTIL_DIR.exists()
        and (
            BGUTIL_DIR / "deno.json"
        ).exists()
    ):
        logger.info(
            "bgutil source already exists."
        )
        return True

    logger.info(
        "Cloning bgutil %s...",
        BGUTIL_VERSION,
    )

    result = run_command(
        [
            "git",
            "clone",
            "--single-branch",
            "--branch",
            BGUTIL_VERSION,
            "https://github.com/"
            "Brainicism/"
            "bgutil-ytdlp-pot-provider.git",
            str(BGUTIL_DIR),
        ],
        timeout=300,
    )

    if (
        result is None
        or result.returncode != 0
    ):
        logger.error(
            "bgutil clone failed."
        )
        return False

    return True


def install_bgutil_dependencies():
    marker = (
        BGUTIL_DIR
        / "node_modules"
    )

    if marker.exists():
        logger.info(
            "bgutil dependencies already installed."
        )
        return True

    logger.info(
        "Installing bgutil dependencies..."
    )

    result = run_command(
        [
            str(DENO_BIN),
            "install",
            "--allow-scripts=npm:canvas",
            "--frozen",
        ],
        timeout=900,
        cwd=str(BGUTIL_DIR),
    )

    if (
        result is None
        or result.returncode != 0
    ):
        logger.error(
            "bgutil dependency installation failed."
        )
        return False

    return True


def is_bgutil_server_running():
    try:
        with urllib.request.urlopen(
            BGUTIL_URL,
            timeout=2,
        ) as response:
            return response.status in (
                200,
                400,
                404,
            )

    except urllib.error.HTTPError as exc:
        return exc.code in (
            400,
            404,
        )

    except Exception:
        return False


def start_bgutil_server():
    global BGUTIL_PROCESS

    if is_bgutil_server_running():
        logger.info(
            "bgutil PO Token server: already running."
        )
        return True

    logger.info(
        "Starting bgutil PO Token server..."
    )

    command = [
        str(DENO_BIN),
        "run",
        "--allow-all",
        "server.ts",
        "--port",
        str(BGUTIL_PORT),
    ]

    try:
        BGUTIL_PROCESS = subprocess.Popen(
            command,
            cwd=str(BGUTIL_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=os.environ.copy(),
        )

        def bgutil_logger():
            try:
                for line in BGUTIL_PROCESS.stdout:
                    line = line.rstrip()

                    if line:
                        logger.info(
                            "[bgutil] %s",
                            line,
                        )
            except Exception:
                pass

        thread = threading.Thread(
            target=bgutil_logger,
            daemon=True,
        )

        thread.start()

    except Exception as exc:
        logger.exception(
            "Could not start bgutil: %s",
            exc,
        )
        return False

    for _ in range(45):
        if is_bgutil_server_running():
            logger.info(
                "bgutil PO Token server: OK"
            )
            return True

        time.sleep(1)

    logger.error(
        "bgutil server did not become ready."
    )

    return False


# ============================================================
# YT-DLP CHECK
# ============================================================

def check_ytdlp():
    result = run_command(
        [
            str(SPOTDL_PYTHON),
            "-m",
            "yt_dlp",
            "--version",
        ],
        timeout=30,
    )

    if (
        result
        and result.returncode == 0
    ):
        logger.info(
            "yt-dlp %s: OK",
            YTDLP_VERSION,
        )
        return True

    return False


# ============================================================
# YOUTUBE METADATA TEST
# ============================================================

def test_youtube_metadata():
    url = (
        "https://www.youtube.com/watch"
        "?v=0loPj-nIG7c"
    )

    logger.info(
        "Testing YouTube metadata "
        "using mweb + bgutil..."
    )

    command = [
        str(SPOTDL_PYTHON),
        "-m",
        "yt_dlp",

        "--no-playlist",
        "--no-update",

        "--socket-timeout",
        "20",

        "--retries",
        "2",

        "--fragment-retries",
        "2",

        "--extractor-retries",
        "2",

        "--retry-sleep",
        "1",

        "--extractor-args",
        YOUTUBE_CLIENT_ARGS,

        "--extractor-args",
        YOUTUBE_POT_ARGS,

        "--js-runtimes",
        f"deno:{DENO_BIN}",

        "--print",
        "title",

        "--skip-download",

        url,
    ]

    result = run_command(
        command,
        timeout=120,
    )

    if (
        result
        and result.returncode == 0
    ):
        logger.info(
            "YouTube metadata test: SUCCESS"
        )
        return True

    logger.warning(
        "YouTube metadata test failed."
    )

    return False


# ============================================================
# YOUTUBE AUDIO TEST
# ============================================================

def test_youtube_audio():
    url = (
        "https://www.youtube.com/watch"
        "?v=0loPj-nIG7c"
    )

    YOUTUBE_TEST_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    logger.info(
        "Testing actual YouTube audio download..."
    )

    command = [
        str(SPOTDL_PYTHON),
        "-m",
        "yt_dlp",

        "--no-playlist",
        "--no-update",

        "--socket-timeout",
        "20",

        "--retries",
        "2",

        "--fragment-retries",
        "2",

        "--extractor-retries",
        "2",

        "--retry-sleep",
        "1",

        "--extractor-args",
        YOUTUBE_CLIENT_ARGS,

        "--extractor-args",
        YOUTUBE_POT_ARGS,

        "--js-runtimes",
        f"deno:{DENO_BIN}",

        "-f",
        "bestaudio/best",

        "-o",
        str(
            YOUTUBE_TEST_DIR
            / "%(id)s.%(ext)s"
        ),

        "--verbose",

        url,
    ]

    result = run_command(
        command,
        timeout=180,
    )

    if (
        result
        and result.returncode == 0
    ):
        logger.info(
            "YouTube audio test: SUCCESS"
        )
        return True

    logger.warning(
        "YouTube audio test failed."
    )

    return False


# ============================================================
# TELEGRAM LOCK
# ============================================================

def acquire_bot_lock():
    global BOT_LOCK_FD

    try:
        BOT_LOCK_FD = open(
            BOT_LOCK_FILE,
            "w",
        )

        fcntl.flock(
            BOT_LOCK_FD,
            fcntl.LOCK_EX | fcntl.LOCK_NB,
        )

        logger.info(
            "Telegram bot lock acquired."
        )

        return True

    except BlockingIOError:
        logger.warning(
            "Telegram bot already running."
        )
        return False

    except Exception as exc:
        logger.exception(
            "Telegram lock error: %s",
            exc,
        )
        return False


def release_bot_lock():
    global BOT_LOCK_FD

    if BOT_LOCK_FD is None:
        return

    try:
        fcntl.flock(
            BOT_LOCK_FD,
            fcntl.LOCK_UN,
        )
    except Exception:
        pass

    try:
        BOT_LOCK_FD.close()
    except Exception:
        pass

    BOT_LOCK_FD = None


# ============================================================
# TELEGRAM HANDLERS
# ============================================================

def telegram_start(
    update,
    context,
):
    try:
        update.message.reply_text(
            "سلام 👋\n"
            "لینک آهنگ Spotify را بفرست "
            "تا MP3 با کیفیت 320kbps دانلود و ارسال شود."
        )
    except Exception:
        logger.exception(
            "Telegram start error."
        )


def telegram_help(
    update,
    context,
):
    try:
        update.message.reply_text(
            "لینک Spotify آهنگ را ارسال کن.\n"
            "ربات آهنگ را با spotDL دانلود "
            "و به صورت MP3 320kbps ارسال می‌کند."
        )
    except Exception:
        logger.exception(
            "Telegram help error."
        )


def telegram_message(
    update,
    context,
):
    message = update.effective_message

    if message is None:
        return

    text = (
        message.text or ""
    ).strip()

    if not text:
        return

    chat_id = message.chat_id
    message_id = message.message_id

    username = None

    if update.effective_user:
        username = (
            update.effective_user.username
        )

    logger.info(
        "Starting song download. "
        "Chat ID: %s, Message ID: %s, Username: %s",
        chat_id,
        message_id,
        username,
    )

    if (
        "open.spotify.com/track/"
        not in text
    ):
        try:
            message.reply_text(
                "لطفاً لینک آهنگ Spotify را ارسال کن."
            )
        except Exception:
            pass

        return

    status_message = None

    try:
        status_message = (
            message.reply_text(
                "⏳ در حال دانلود آهنگ..."
            )
        )
    except Exception:
        pass

    output_dir = (
        DOWNLOAD_DIR
        / str(chat_id)
        / str(message_id)
    )

    try:
        audio_file = download_song(
            text,
            output_dir,
        )

        if audio_file is None:

            if status_message:
                try:
                    status_message.edit_text(
                        "❌ دانلود انجام نشد یا فایل صوتی پیدا نشد."
                    )
                except Exception:
                    pass

            return

        if status_message:
            try:
                status_message.edit_text(
                    "📤 فایل آماده شد، در حال ارسال..."
                )
            except Exception:
                pass

        logger.info(
            "Sending song to user..."
        )

        with open(
            audio_file,
            "rb",
        ) as audio:

            message.reply_audio(
                audio=audio,
                filename=audio_file.name,
                title=audio_file.stem,
                read_timeout=120,
                write_timeout=120,
                connect_timeout=30,
            )

        logger.info(
            "Song sent successfully."
        )

        if status_message:
            try:
                status_message.delete()
            except Exception:
                pass

        try:
            shutil.rmtree(
                output_dir
            )
        except Exception:
            pass

    except Exception as exc:

        logger.exception(
            "Telegram processing error: %s",
            exc,
        )

        if status_message:
            try:
                status_message.edit_text(
                    "❌ هنگام دانلود یا ارسال آهنگ خطایی رخ داد."
                )
            except Exception:
                pass


# ============================================================
# DOWNLOAD SONG
# ============================================================

def download_song(
    spotify_url: str,
    output_dir: Path,
):
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Remove previous files
    for item in output_dir.iterdir():
        try:
            if item.is_file():
                item.unlink()

            elif item.is_dir():
                shutil.rmtree(item)

        except Exception:
            pass

    # IMPORTANT:
    #
    # These arguments are passed directly to yt-dlp
    # through spotDL.
    #
    yt_dlp_args = (
        "--no-update "
        "--socket-timeout 20 "
        "--retries 2 "
        "--fragment-retries 2 "
        "--extractor-retries 2 "
        "--retry-sleep 1 "
        f'--js-runtimes "deno:{DENO_BIN}" '
        f'--extractor-args "{YOUTUBE_CLIENT_ARGS}" '
        f'--extractor-args "{YOUTUBE_POT_ARGS}"'
    )

    output_template = (
        str(output_dir)
        + "/{artist} - {title}.{output-ext}"
    )

    command = [
        str(SPOTDL_BIN),

        "--output",
        output_template,

        "--format",
        "mp3",

        "--bitrate",
        "320k",

        "--threads",
        "4",

        "--no-cache",

        "--overwrite",

        "--yt-dlp-args",
        yt_dlp_args,

        spotify_url,
    ]

    logger.info(
        "Downloading song..."
    )

    logger.info(
        "Spotify URL: %s",
        spotify_url,
    )

    logger.info(
        "yt-dlp args: %s",
        yt_dlp_args,
    )

    result = run_command(
        command,
        timeout=600,
    )

    if result is None:
        return None

    if result.returncode != 0:
        logger.error(
            "spotDL exited with code %s",
            result.returncode,
        )

    audio_extensions = {
        ".mp3",
        ".m4a",
        ".opus",
        ".webm",
        ".wav",
        ".flac",
        ".ogg",
    }

    audio_files = []

    if output_dir.exists():
        for path in output_dir.rglob("*"):
            if (
                path.is_file()
                and path.suffix.lower()
                in audio_extensions
            ):
                audio_files.append(path)

    if not audio_files:
        logger.warning(
            "No audio file found after download."
        )
        return None

    audio_files.sort(
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    audio_file = audio_files[0]

    logger.info(
        "Audio file found: %s",
        audio_file,
    )

    logger.info(
        "Audio size: %d bytes",
        audio_file.stat().st_size,
    )

    return audio_file


# ============================================================
# TELEGRAM BOT
# ============================================================

def start_telegram_bot():
    global TELEGRAM_UPDATER

    if not TELEGRAM_TOKEN:
        logger.warning(
            "TELEGRAM_TOKEN missing. "
            "Add TELEGRAM_TOKEN to Streamlit Secrets."
        )

        return None

    if not acquire_bot_lock():
        return None

    try:
        from telegram.ext import (
            Updater,
            CommandHandler,
            MessageHandler,
            Filters,
        )

    except Exception as exc:
        logger.exception(
            "python-telegram-bot import failed: %s",
            exc,
        )

        release_bot_lock()

        return None

    try:
        updater = Updater(
            token=TELEGRAM_TOKEN,
            use_context=True,
        )

        dispatcher = (
            updater.dispatcher
        )

        dispatcher.add_handler(
            CommandHandler(
                "start",
                telegram_start,
            )
        )

        dispatcher.add_handler(
            CommandHandler(
                "help",
                telegram_help,
            )
        )

        dispatcher.add_handler(
            MessageHandler(
                Filters.text
                & ~Filters.command,
                telegram_message,
            )
        )

        # Do NOT use updater.idle()
        # because Streamlit manages its own process.
        updater.start_polling(
            drop_pending_updates=True,
        )

        TELEGRAM_UPDATER = updater

        logger.info(
            "Telegram bot started."
        )

        return updater

    except Exception as exc:
        logger.exception(
            "Unable to start Telegram bot: %s",
            exc,
        )

        release_bot_lock()

        return None


# ============================================================
# FULL INITIALIZATION
# ============================================================

def initialize():
    logger.info(
        "========================================"
    )

    logger.info(
        "SPMA initialization started"
    )

    logger.info(
        "========================================"
    )

    # --------------------------------------------------------
    # 1. Environment
    # --------------------------------------------------------

    configure_environment()

    # --------------------------------------------------------
    # 2. Deno
    # --------------------------------------------------------

    if not install_deno():
        logger.error(
            "Deno installation failed."
        )

    # --------------------------------------------------------
    # 3. FFmpeg
    # --------------------------------------------------------

    if not install_ffmpeg():
        logger.error(
            "FFmpeg installation failed."
        )

    # --------------------------------------------------------
    # 4. spotDL + yt-dlp
    # --------------------------------------------------------

    if not install_spotdl():
        logger.error(
            "spotDL installation failed."
        )

    # --------------------------------------------------------
    # 5. bgutil source
    # --------------------------------------------------------

    if not install_bgutil():
        logger.error(
            "bgutil installation failed."
        )

    # --------------------------------------------------------
    # 6. bgutil dependencies
    # --------------------------------------------------------

    if BGUTIL_DIR.exists():

        if not install_bgutil_dependencies():
            logger.error(
                "bgutil dependency installation failed."
            )

    # --------------------------------------------------------
    # 7. Reconfigure PATH after installations
    # --------------------------------------------------------

    configure_environment()

    # --------------------------------------------------------
    # 8. Verify components
    # --------------------------------------------------------

    if SPOTDL_BIN.exists():
        logger.info(
            "spotDL: OK"
        )
    else:
        logger.error(
            "spotDL: FAILED"
        )

    if SPOTDL_PYTHON.exists():
        logger.info(
            "spotDL Python: OK"
        )
    else:
        logger.error(
            "spotDL Python: FAILED"
        )

    if FFMPEG_BIN.exists():
        logger.info(
            "FFmpeg: OK"
        )
    else:
        logger.error(
            "FFmpeg: FAILED"
        )

    if DENO_BIN.exists():
        logger.info(
            "Deno: OK"
        )
    else:
        logger.error(
            "Deno: FAILED"
        )

    # --------------------------------------------------------
    # 9. yt-dlp version
    # --------------------------------------------------------

    if SPOTDL_PYTHON.exists():
        check_ytdlp()

    # --------------------------------------------------------
    # 10. Start bgutil
    # --------------------------------------------------------

    bgutil_ok = False

    if (
        DENO_BIN.exists()
        and BGUTIL_DIR.exists()
    ):
        bgutil_ok = start_bgutil_server()

    if bgutil_ok:
        logger.info(
            "bgutil PO Token: OK"
        )
    else:
        logger.warning(
            "bgutil PO Token: FAILED"
        )

    # --------------------------------------------------------
    # 11. YouTube tests
    # --------------------------------------------------------

    if (
        bgutil_ok
        and DENO_BIN.exists()
        and SPOTDL_PYTHON.exists()
    ):
        metadata_ok = (
            test_youtube_metadata()
        )

        if metadata_ok:
            logger.info(
                "YouTube mweb metadata: OK"
            )

            # Only perform actual audio test
            # when metadata is successful.
            audio_ok = (
                test_youtube_audio()
            )

            if audio_ok:
                logger.info(
                    "YouTube actual audio download: OK"
                )
            else:
                logger.warning(
                    "YouTube actual audio download: FAILED"
                )

        else:
            logger.warning(
                "YouTube mweb metadata: FAILED"
            )

    # --------------------------------------------------------
    # 12. Telegram
    # --------------------------------------------------------

    start_telegram_bot()

    logger.info(
        "========================================"
    )

    logger.info(
        "SPMA initialization finished"
    )

    logger.info(
        "========================================"
    )


# ============================================================
# STREAMLIT INITIALIZATION GUARD
# ============================================================

if not globals().get(
    "_SPMA_INITIALIZED",
    False,
):

    globals()[
        "_SPMA_INITIALIZED"
    ] = True

    try:
        initialize()

    except Exception as exc:
        logger.exception(
            "Fatal initialization error: %s",
            exc,
        )


# ============================================================
# KEEP PROCESS ALIVE
# ============================================================

while True:
    time.sleep(3600)
