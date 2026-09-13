import os
import sys
import time
import fcntl
import shutil
import signal
import logging
import subprocess
import threading
import urllib.request
import urllib.error
from pathlib import Path

import streamlit as st


# ============================================================
# CONFIG
# ============================================================

BASE_DIR = Path("/mount/src/spma")

SPOTDL_VENV = BASE_DIR / ".spotdl_venv"
SPOTDL_BIN = SPOTDL_VENV / "bin" / "spotdl"
SPOTDL_PYTHON = SPOTDL_VENV / "bin" / "python"

BIN_DIR = BASE_DIR / ".bin"
DENO_BIN = BIN_DIR / "deno"
FFMPEG_BIN = BIN_DIR / "ffmpeg"
FFPROBE_BIN = BIN_DIR / "ffprobe"

BGUTIL_DIR = BASE_DIR / ".bgutil-ytdlp-pot-provider"

BGUTIL_HOST = "127.0.0.1"
BGUTIL_PORT = 4416
BGUTIL_URL = f"http://{BGUTIL_HOST}:{BGUTIL_PORT}"

DOWNLOAD_DIR = BASE_DIR / "downloads"
YOUTUBE_TEST_DIR = BASE_DIR / ".youtube_test"

BOT_LOCK_FILE = "/tmp/spma_telegram_bot.lock"

SPOTDL_GIT = (
    "git+https://github.com/TzurSoffer/spotify-downloader"
    "@29cb0b0669d5c107331b0912fdef73967b47493e"
)

YTDLP_VERSION = "2026.06.09"
YTDLP_EJS_VERSION = "0.8.0"
BGUTIL_VERSION = "2.0.0"
DENO_VERSION = "2.9.6"

# IMPORTANT:
# Do NOT use android_vr.
# Current YouTube behavior can generate a 403 download URL
# with android_vr. mweb + bgutil PO token is the intended setup.
YOUTUBE_CLIENT_ARGS = (
    "youtube:player_client=mweb;fetch_pot=always"
)

YOUTUBE_POT_ARGS = (
    f"youtubepot-bgutilhttp:base_url={BGUTIL_URL}"
)

YTDLP_ARGS = (
    f'--no-update '
    f'--socket-timeout 20 '
    f'--retries 2 '
    f'--fragment-retries 2 '
    f'--extractor-retries 2 '
    f'--retry-sleep 1 '
    f'--js-runtimes "deno:{DENO_BIN}" '
    f'--extractor-args "{YOUTUBE_CLIENT_ARGS}" '
    f'--extractor-args "{YOUTUBE_POT_ARGS}"'
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
SPOTIFY_CLIENT_ID = get_secret("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = get_secret("SPOTIFY_CLIENT_SECRET")


# ============================================================
# ENVIRONMENT
# ============================================================

def configure_environment():
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    YOUTUBE_TEST_DIR.mkdir(parents=True, exist_ok=True)

    # Local binaries first
    current_path = os.environ.get("PATH", "")

    path_parts = [
        str(BIN_DIR),
        str(SPOTDL_VENV / "bin"),
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
    ]

    for item in current_path.split(":"):
        if item and item not in path_parts:
            path_parts.append(item)

    os.environ["PATH"] = ":".join(path_parts)

    # Spotify variables used by spotDL / spotipy
    if SPOTIFY_CLIENT_ID:
        os.environ["SPOTIPY_CLIENT_ID"] = SPOTIFY_CLIENT_ID
        os.environ["SPOTIFY_CLIENT_ID"] = SPOTIFY_CLIENT_ID

    if SPOTIFY_CLIENT_SECRET:
        os.environ["SPOTIPY_CLIENT_SECRET"] = SPOTIFY_CLIENT_SECRET
        os.environ["SPOTIFY_CLIENT_SECRET"] = SPOTIFY_CLIENT_SECRET

    # Force local FFmpeg
    if FFMPEG_BIN.exists():
        os.environ["FFMPEG_BINARY"] = str(FFMPEG_BIN)

    if FFPROBE_BIN.exists():
        os.environ["FFPROBE_BINARY"] = str(FFPROBE_BIN)

    # Deno
    if DENO_BIN.exists():
        os.environ["DENO_BINARY"] = str(DENO_BIN)

    logger.info("Environment configured.")


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
    logger.info("Running: %s", " ".join(map(str, command)))

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
            logger.info(result.stdout[-12000:])

        if check and result.returncode != 0:
            raise RuntimeError(
                f"Command failed with exit code {result.returncode}"
            )

        return result

    except subprocess.TimeoutExpired:
        logger.error("Command timed out.")
        return None

    except Exception as exc:
        logger.exception("Command error: %s", exc)
        return None


# ============================================================
# CHECKS
# ============================================================

def check_binary(path: Path, name: str) -> bool:
    if path.exists() and os.access(path, os.X_OK):
        logger.info("%s: OK -> %s", name, path)
        return True

    logger.warning("%s not found: %s", name, path)
    return False


def check_spotdl() -> bool:
    if not SPOTDL_BIN.exists():
        logger.error("spotDL not found: %s", SPOTDL_BIN)
        return False

    result = run_command(
        [str(SPOTDL_BIN), "--version"],
        timeout=30,
    )

    if result and result.returncode == 0:
        logger.info("spotDL: OK")
        return True

    logger.error("spotDL check failed.")
    return False


def check_ffmpeg() -> bool:
    if not FFMPEG_BIN.exists():
        logger.error("FFmpeg not found: %s", FFMPEG_BIN)
        return False

    result = run_command(
        [str(FFMPEG_BIN), "-version"],
        timeout=20,
    )

    if result and result.returncode == 0:
        logger.info("FFmpeg: OK")
        return True

    logger.error("FFmpeg check failed.")
    return False


def check_deno() -> bool:
    if not DENO_BIN.exists():
        logger.error("Deno not found: %s", DENO_BIN)
        return False

    result = run_command(
        [str(DENO_BIN), "--version"],
        timeout=20,
    )

    if result and result.returncode == 0:
        logger.info("Deno: OK")
        return True

    logger.error("Deno check failed.")
    return False


# ============================================================
# BGUTIL
# ============================================================

def is_bgutil_server_running() -> bool:
    try:
        with urllib.request.urlopen(
            BGUTIL_URL,
            timeout=2,
        ) as response:
            return response.status in (200, 404)

    except urllib.error.HTTPError as exc:
        # HTTP 404 still means the HTTP server is alive.
        return exc.code in (400, 404)

    except Exception:
        return False


def start_bgutil_server() -> bool:
    if is_bgutil_server_running():
        logger.info("bgutil PO Token server: already running.")
        return True

    if not BGUTIL_DIR.exists():
        logger.error("bgutil directory not found: %s", BGUTIL_DIR)
        return False

    deno_json = BGUTIL_DIR / "deno.json"

    if not deno_json.exists():
        logger.error("bgutil deno.json not found.")
        return False

    logger.info("Starting bgutil PO Token server...")

    command = [
        str(DENO_BIN),
        "run",
        "--allow-all",
        "server.ts",
        "--port",
        str(BGUTIL_PORT),
    ]

    try:
        process = subprocess.Popen(
            command,
            cwd=str(BGUTIL_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=os.environ.copy(),
        )

        # Keep a reference so the process is not garbage collected.
        globals()["_BGUTIL_PROCESS"] = process

        def read_bgutil_output():
            try:
                for line in process.stdout:
                    line = line.rstrip()
                    if line:
                        logger.info("[bgutil] %s", line)
            except Exception:
                pass

        thread = threading.Thread(
            target=read_bgutil_output,
            daemon=True,
        )
        thread.start()

    except Exception as exc:
        logger.exception("Unable to start bgutil: %s", exc)
        return False

    for _ in range(30):
        if is_bgutil_server_running():
            logger.info("bgutil PO Token server: OK")
            return True

        time.sleep(1)

    logger.error("bgutil server did not start.")
    return False


# ============================================================
# YT-DLP CHECK
# ============================================================

def check_ytdlp() -> bool:
    if not SPOTDL_PYTHON.exists():
        logger.error("spotDL Python not found.")
        return False

    result = run_command(
        [
            str(SPOTDL_PYTHON),
            "-m",
            "yt_dlp",
            "--version",
        ],
        timeout=30,
    )

    if result and result.returncode == 0:
        logger.info("yt-dlp check: OK")
        return True

    logger.error("yt-dlp check failed.")
    return False


# ============================================================
# YOUTUBE TEST
# ============================================================

def test_youtube_metadata(url: str) -> bool:
    logger.info("Testing YouTube metadata...")

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
        timeout=90,
    )

    if result and result.returncode == 0:
        logger.info("YouTube metadata test: SUCCESS")
        return True

    logger.error("YouTube metadata test: FAILED")
    return False


# ============================================================
# SPOTDL DOWNLOAD
# ============================================================

def download_song(spotify_url: str, output_dir: Path) -> Path | None:
    """
    Download a Spotify track using the isolated spotDL environment.

    The important part here is --yt-dlp-args:
        player_client=mweb
        fetch_pot=always
        bgutil HTTP provider
        Deno runtime
    """

    output_dir.mkdir(parents=True, exist_ok=True)

    # Remove old files from this download directory.
    for item in output_dir.iterdir():
        try:
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)
        except Exception:
            pass

    yt_dlp_args = (
        f'--no-update '
        f'--socket-timeout 20 '
        f'--retries 2 '
        f'--fragment-retries 2 '
        f'--extractor-retries 2 '
        f'--retry-sleep 1 '
        f'--js-runtimes "deno:{DENO_BIN}" '
        f'--extractor-args "{YOUTUBE_CLIENT_ARGS}" '
        f'--extractor-args "{YOUTUBE_POT_ARGS}"'
    )

    command = [
        str(SPOTDL_BIN),

        "--output",
        str(output_dir / "{artist} - {title}.{output-ext}"),

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

    logger.info("Starting spotDL download.")
    logger.info("Spotify URL: %s", spotify_url)
    logger.info("yt-dlp args: %s", yt_dlp_args)

    result = run_command(
        command,
        timeout=600,
    )

    if result is None:
        logger.error("spotDL process failed to start.")
        return None

    if result.returncode != 0:
        logger.error(
            "spotDL exited with code %s",
            result.returncode,
        )

    # Search for resulting audio.
    audio_extensions = {
        ".mp3",
        ".m4a",
        ".opus",
        ".webm",
        ".wav",
        ".flac",
        ".ogg",
    }

    files = []

    for path in output_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in audio_extensions:
            files.append(path)

    if not files:
        logger.warning("No audio file found after download.")
        return None

    # Usually there should only be one.
    files.sort(
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    audio_file = files[0]

    logger.info(
        "Downloaded audio: %s (%d bytes)",
        audio_file,
        audio_file.stat().st_size,
    )

    return audio_file


# ============================================================
# TELEGRAM
# ============================================================

BOT_LOCK_FD = None


def acquire_bot_lock() -> bool:
    global BOT_LOCK_FD

    try:
        BOT_LOCK_FD = open(BOT_LOCK_FILE, "w")

        fcntl.flock(
            BOT_LOCK_FD,
            fcntl.LOCK_EX | fcntl.LOCK_NB,
        )

        logger.info("Telegram bot lock acquired.")
        return True

    except BlockingIOError:
        logger.warning("Telegram bot already running.")
        return False

    except Exception as exc:
        logger.exception(
            "Bot lock error: %s",
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


def telegram_start(update, context):
    try:
        update.message.reply_text(
            "سلام 👋\n"
            "لینک آهنگ Spotify را بفرست تا MP3 با کیفیت 320kbps دانلود و ارسال شود."
        )
    except Exception:
        logger.exception("Telegram /start error")


def telegram_help(update, context):
    try:
        update.message.reply_text(
            "لینک Spotify آهنگ را ارسال کن.\n"
            "ربات آن را با spotDL دریافت و به صورت MP3 320kbps ارسال می‌کند."
        )
    except Exception:
        logger.exception("Telegram /help error")


def telegram_message(update, context):
    message = update.effective_message

    if message is None:
        return

    text = (message.text or "").strip()

    if not text:
        return

    chat_id = message.chat_id
    message_id = message.message_id
    username = (
        update.effective_user.username
        if update.effective_user
        else None
    )

    logger.info(
        "Starting song download. "
        "Chat ID: %s, Message ID: %s, Username: %s",
        chat_id,
        message_id,
        username,
    )

    # Accept Spotify track URLs.
    if "open.spotify.com/track/" not in text:
        message.reply_text(
            "لطفاً لینک آهنگ Spotify را ارسال کن."
        )
        return

    status_message = None

    try:
        status_message = message.reply_text(
            "⏳ در حال دانلود آهنگ..."
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

        logger.info("Sending song to user...")

        with open(audio_file, "rb") as audio:
            message.reply_audio(
                audio=audio,
                filename=audio_file.name,
                title=audio_file.stem,
                read_timeout=120,
                write_timeout=120,
                connect_timeout=30,
            )

        logger.info("Song sent successfully.")

        if status_message:
            try:
                status_message.delete()
            except Exception:
                pass

        # Cleanup
        try:
            shutil.rmtree(output_dir)
        except Exception:
            pass

    except Exception as exc:
        logger.exception(
            "Error while processing Telegram message: %s",
            exc,
        )

        if status_message:
            try:
                status_message.edit_text(
                    "❌ هنگام دانلود یا ارسال آهنگ خطایی رخ داد."
                )
            except Exception:
                pass


def start_telegram_bot():
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

        dispatcher = updater.dispatcher

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
                Filters.text & ~Filters.command,
                telegram_message,
            )
        )

        # Do NOT use updater.idle() here.
        # Streamlit has its own signal/thread behavior.
        updater.start_polling(
            drop_pending_updates=True,
        )

        logger.info("Telegram bot started.")

        return updater

    except Exception as exc:
        logger.exception(
            "Unable to start Telegram bot: %s",
            exc,
        )
        release_bot_lock()
        return None


# ============================================================
# INITIALIZATION
# ============================================================

def initialize():
    logger.info("========================================")
    logger.info("SPMA initialization started")
    logger.info("========================================")

    configure_environment()

    # Basic checks
    check_spotdl()
    check_ytdlp()
    check_ffmpeg()
    check_deno()

    # Start bgutil
    bgutil_ok = start_bgutil_server()

    if bgutil_ok:
        logger.info("bgutil PO Token: OK")
    else:
        logger.warning(
            "bgutil PO Token: FAILED"
        )

    # Metadata test is optional and only performed when
    # everything needed exists.
    if bgutil_ok and DENO_BIN.exists():
        test_url = (
            "https://www.youtube.com/watch?v=0loPj-nIG7c"
        )

        metadata_ok = test_youtube_metadata(test_url)

        if metadata_ok:
            logger.info(
                "YouTube mweb metadata: OK"
            )
        else:
            logger.warning(
                "YouTube mweb metadata test failed."
            )

    # Start Telegram
    updater = start_telegram_bot()

    if updater is not None:
        globals()["_TELEGRAM_UPDATER"] = updater

    logger.info("========================================")
    logger.info("SPMA initialization finished")
    logger.info("========================================")


# ============================================================
# STREAMLIT ENTRYPOINT
# ============================================================

if not globals().get("_SPMA_INITIALIZED", False):
    globals()["_SPMA_INITIALIZED"] = True

    try:
        initialize()
    except Exception as exc:
        logger.exception(
            "Fatal initialization error: %s",
            exc,
        )


# ============================================================
# KEEP STREAMLIT PROCESS ALIVE
# ============================================================

while True:
    time.sleep(3600)
