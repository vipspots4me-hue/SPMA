import os
import sys
import time
import json
import shutil
import signal
import subprocess
import threading
import logging
import urllib.request
import zipfile
import tarfile
from pathlib import Path

import streamlit as st


# ============================================================
# CONFIG
# ============================================================

BASE_DIR = Path("/mount/src/spma")

BIN_DIR = BASE_DIR / ".bin"
SPOTDL_VENV = BASE_DIR / ".spotdl_venv"

SPOTDL_PYTHON = SPOTDL_VENV / "bin" / "python"
SPOTDL_BIN = SPOTDL_VENV / "bin" / "spotdl"

BGUTIL_DIR = BASE_DIR / ".bgutil-ytdlp-pot-provider"
BGUTIL_SERVER_DIR = BGUTIL_DIR / "server"
BGUTIL_NODE_MODULES = BGUTIL_SERVER_DIR / "node_modules"
BGUTIL_MAIN_TS = BGUTIL_SERVER_DIR / "src" / "main.ts"

DOWNLOAD_DIR = BASE_DIR / "downloads"
CACHE_DIR = BASE_DIR / ".spma_cache"

DENO_BIN = BIN_DIR / "deno"
FFMPEG_BIN = BIN_DIR / "ffmpeg"
FFPROBE_BIN = BIN_DIR / "ffprobe"

BGUTIL_HOST = "127.0.0.1"
BGUTIL_PORT = 4416
BGUTIL_URL = f"http://{BGUTIL_HOST}:{BGUTIL_PORT}"

SPOTDL_GIT = (
    "git+https://github.com/TzurSoffer/"
    "spotify-downloader@"
    "29cb0b0669d5c107331b0912fdef73967b47493e"
)

YT_DLP_VERSION = "2026.06.09"
YT_DLP_EJS_VERSION = "0.8.0"
BGUTIL_VERSION = "2.0.0"
DENO_VERSION = "2.9.6"
FFMPEG_VERSION = "7.0.2"

YOUTUBE_CLIENT_ARGS = (
    "youtube:player_client=mweb;fetch_pot=always"
)

YOUTUBE_POT_ARGS = (
    f"youtubepot-bgutilhttp:base_url={BGUTIL_URL}"
)

BOT_LOCK_FILE = "/tmp/spma_telegram_bot.lock"
BOT_LOCK_FD = None

BGUTIL_PROCESS = None

_SPMA_INITIALIZED = False


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger("SPMA")


# ============================================================
# HELPERS
# ============================================================

def run_command(
    cmd,
    cwd=None,
    env=None,
    timeout=None,
    check=True,
    capture_output=False,
):
    logger.info("Running: %s", " ".join(map(str, cmd)))

    return subprocess.run(
        [str(x) for x in cmd],
        cwd=str(cwd) if cwd else None,
        env=env,
        timeout=timeout,
        check=check,
        text=True,
        capture_output=capture_output,
    )


def command_exists(path):
    return Path(path).exists() and os.access(path, os.X_OK)


def download_file(url, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Downloading: %s", url)

    urllib.request.urlretrieve(url, destination)

    return destination


def extract_zip(zip_path, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(destination)


def extract_tar_xz(tar_path, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)

    with tarfile.open(tar_path, "r:xz") as tar:
        tar.extractall(destination)


def ensure_dir(path):
    Path(path).mkdir(parents=True, exist_ok=True)


# ============================================================
# PYTHON / PIP
# ============================================================

def ensure_spotdl_environment():

    ensure_dir(BASE_DIR)
    ensure_dir(BIN_DIR)
    ensure_dir(DOWNLOAD_DIR)
    ensure_dir(CACHE_DIR)

    if not SPOTDL_PYTHON.exists():

        logger.info("Creating spotDL virtual environment...")

        run_command(
            [
                sys.executable,
                "-m",
                "venv",
                str(SPOTDL_VENV),
            ]
        )

    logger.info("Installing/checking spotDL stack...")

    run_command(
        [
            str(SPOTDL_PYTHON),
            "-m",
            "pip",
            "install",
            "--upgrade",
            SPOTDL_GIT,
        ],
        timeout=1200,
    )

    run_command(
        [
            str(SPOTDL_PYTHON),
            "-m",
            "pip",
            "install",
            "--upgrade",
            f"yt-dlp=={YT_DLP_VERSION}",
            f"yt-dlp-ejs=={YT_DLP_EJS_VERSION}",
            f"bgutil-ytdlp-pot-provider=={BGUTIL_VERSION}",
        ],
        timeout=1200,
    )

    logger.info("Environment configured.")
    logger.info("spotDL: OK")
    logger.info("spotDL Python: OK")


# ============================================================
# DENO
# ============================================================

def ensure_deno():

    if command_exists(DENO_BIN):

        try:
            result = run_command(
                [
                    str(DENO_BIN),
                    "--version",
                ],
                check=False,
                capture_output=True,
            )

            if result.returncode == 0:
                logger.info("Deno: OK")
                return

        except Exception:
            pass

    logger.info("Installing Deno %s...", DENO_VERSION)

    zip_path = BIN_DIR / f"deno-{DENO_VERSION}.zip"

    url = (
        f"https://dl.deno.land/release/v{DENO_VERSION}/"
        "deno-x86_64-unknown-linux-gnu.zip"
    )

    download_file(url, zip_path)

    temp_dir = BIN_DIR / "deno_extract"

    if temp_dir.exists():
        shutil.rmtree(temp_dir)

    extract_zip(zip_path, temp_dir)

    extracted = temp_dir / "deno"

    if not extracted.exists():
        raise RuntimeError("Deno binary not found after extraction.")

    shutil.move(str(extracted), str(DENO_BIN))
    DENO_BIN.chmod(0o755)

    shutil.rmtree(temp_dir, ignore_errors=True)
    zip_path.unlink(missing_ok=True)

    logger.info("Deno: OK")


# ============================================================
# FFMPEG
# ============================================================

def ensure_ffmpeg():

    if command_exists(FFMPEG_BIN) and command_exists(FFPROBE_BIN):

        try:
            result = run_command(
                [
                    str(FFMPEG_BIN),
                    "-version",
                ],
                check=False,
                capture_output=True,
            )

            if result.returncode == 0:
                logger.info("FFmpeg: OK")
                return

        except Exception:
            pass

    logger.info("Installing FFmpeg %s...", FFMPEG_VERSION)

    archive = BIN_DIR / f"ffmpeg-{FFMPEG_VERSION}-amd64-static.tar.xz"

    url = (
        "https://www.johnvansickle.com/ffmpeg/releases/"
        f"ffmpeg-{FFMPEG_VERSION}-amd64-static.tar.xz"
    )

    download_file(url, archive)

    temp_dir = BIN_DIR / "ffmpeg_extract"

    if temp_dir.exists():
        shutil.rmtree(temp_dir)

    extract_tar_xz(archive, temp_dir)

    extracted_dir = (
        temp_dir /
        f"ffmpeg-{FFMPEG_VERSION}-amd64-static"
    )

    extracted_ffmpeg = extracted_dir / "ffmpeg"
    extracted_ffprobe = extracted_dir / "ffprobe"

    if not extracted_ffmpeg.exists():
        raise RuntimeError("FFmpeg binary not found.")

    if not extracted_ffprobe.exists():
        raise RuntimeError("FFprobe binary not found.")

    shutil.move(str(extracted_ffmpeg), str(FFMPEG_BIN))
    shutil.move(str(extracted_ffprobe), str(FFPROBE_BIN))

    FFMPEG_BIN.chmod(0o755)
    FFPROBE_BIN.chmod(0o755)

    shutil.rmtree(temp_dir, ignore_errors=True)
    archive.unlink(missing_ok=True)

    logger.info("FFmpeg: OK")


# ============================================================
# BGUTIL
# ============================================================

def ensure_bgutil_source():

    if BGUTIL_MAIN_TS.exists() and BGUTIL_NODE_MODULES.exists():
        logger.info("bgutil source/dependencies: OK")
        return

    if BGUTIL_DIR.exists():
        shutil.rmtree(BGUTIL_DIR)

    logger.info("Cloning bgutil %s...", BGUTIL_VERSION)

    run_command(
        [
            "git",
            "clone",
            "--single-branch",
            "--branch",
            BGUTIL_VERSION,
            "https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git",
            str(BGUTIL_DIR),
        ],
        timeout=1200,
    )

    if not BGUTIL_MAIN_TS.exists():
        raise RuntimeError(
            f"bgutil server source not found: {BGUTIL_MAIN_TS}"
        )

    logger.info("Installing bgutil Deno dependencies...")

    run_command(
        [
            str(DENO_BIN),
            "install",
            "--allow-scripts=npm:canvas",
            "--frozen",
        ],
        cwd=BGUTIL_SERVER_DIR,
        timeout=1200,
    )

    logger.info("bgutil dependencies: OK")


def is_bgutil_server_running():

    try:
        req = urllib.request.Request(
            f"{BGUTIL_URL}/ping",
            method="GET",
        )

        with urllib.request.urlopen(req, timeout=3) as response:
            return response.status == 200

    except Exception:
        return False


def bgutil_log_reader(process):

    try:
        for line in process.stdout:

            line = line.rstrip()

            if line:
                logger.info("[bgutil] %s", line)

    except Exception as e:
        logger.debug("bgutil log reader stopped: %s", e)


def start_bgutil_server():

    global BGUTIL_PROCESS

    if is_bgutil_server_running():

        logger.info("bgutil PO Token server already running.")
        return

    ensure_bgutil_source()

    logger.info("Starting bgutil PO Token server...")

    cmd = [
        str(DENO_BIN),
        "run",
        "--allow-env",
        "--allow-net",
        "--allow-ffi=.",
        "--allow-read=.",
        "../src/main.ts",
        "--port",
        str(BGUTIL_PORT),
    ]

    BGUTIL_PROCESS = subprocess.Popen(
        cmd,
        cwd=str(BGUTIL_NODE_MODULES),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    thread = threading.Thread(
        target=bgutil_log_reader,
        args=(BGUTIL_PROCESS,),
        daemon=True,
    )

    thread.start()

    for _ in range(30):

        if is_bgutil_server_running():

            logger.info("bgutil PO Token server: OK")
            return

        if BGUTIL_PROCESS.poll() is not None:

            raise RuntimeError(
                "bgutil server exited unexpectedly."
            )

        time.sleep(1)

    raise RuntimeError(
        "bgutil server did not start within the expected time."
    )


# ============================================================
# YT-DLP TEST
# ============================================================

def test_bgutil_ytdlp():

    logger.info("Checking yt-dlp bgutil plugin...")

    test_url = (
        "https://www.youtube.com/watch?v=0loPj-nIG7c"
    )

    cmd = [
        str(SPOTDL_PYTHON),
        "-m",
        "yt_dlp",

        "--no-update",
        "--no-playlist",
        "--socket-timeout",
        "20",

        "--extractor-retries",
        "2",

        "--extractor-args",
        YOUTUBE_CLIENT_ARGS,

        "--extractor-args",
        YOUTUBE_POT_ARGS,

        "--js-runtimes",
        f"deno:{DENO_BIN}",

        "--print",
        "title",

        "--skip-download",
        "--verbose",

        test_url,
    ]

    result = run_command(
        cmd,
        check=False,
        timeout=180,
        capture_output=True,
    )

    output = (result.stdout or "") + "\n" + (result.stderr or "")

    print(output)

    if result.returncode != 0:
        raise RuntimeError(
            "yt-dlp bgutil test failed."
        )

    logger.info(
        "yt-dlp %s: OK",
        YT_DLP_VERSION,
    )

    logger.info(
        "YouTube mweb + bgutil test: SUCCESS"
    )


# ============================================================
# TELEGRAM LOCK
# ============================================================

def acquire_bot_lock():

    global BOT_LOCK_FD

    try:
        import fcntl
    except ImportError:
        logger.warning(
            "fcntl unavailable; Telegram process lock disabled."
        )
        return True

    try:

        BOT_LOCK_FD = open(
            BOT_LOCK_FILE,
            "w",
        )

        fcntl.flock(
            BOT_LOCK_FD,
            fcntl.LOCK_EX | fcntl.LOCK_NB,
        )

        BOT_LOCK_FD.write(str(os.getpid()))
        BOT_LOCK_FD.flush()

        return True

    except BlockingIOError:

        logger.warning(
            "Telegram bot already running."
        )

        return False

    except Exception as e:

        logger.warning(
            "Could not acquire Telegram bot lock: %s",
            e,
        )

        return False


# ============================================================
# TELEGRAM BOT
# ============================================================

def get_secret(name):

    try:
        value = st.secrets.get(name)

        if value:
            return str(value).strip()

    except Exception:
        pass

    return os.environ.get(name, "").strip()


def find_audio_file(directory):

    audio_extensions = {
        ".mp3",
        ".m4a",
        ".opus",
        ".ogg",
        ".flac",
        ".wav",
        ".aac",
    }

    files = []

    for path in Path(directory).rglob("*"):

        if not path.is_file():
            continue

        if path.suffix.lower() in audio_extensions:
            files.append(path)

    if not files:
        return None

    files.sort(
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    return files[0]


def run_spotdl_download(
    spotify_url,
    output_dir,
):

    ensure_dir(output_dir)

    cmd = [
        str(SPOTDL_BIN),

        "--output",
        str(
            Path(output_dir) /
            "{artist} - {title}.{output-ext}"
        ),

        "--format",
        "mp3",

        "--bitrate",
        "320k",

        "--threads",
        "4",

        "--no-cache",

        # IMPORTANT:
        # spotDL 4.4.11 requires a value for --overwrite.
        "--overwrite",
        "force",

        "--yt-dlp-args",
        (
            "--no-update "
            "--socket-timeout 20 "
            "--retries 2 "
            "--fragment-retries 2 "
            "--extractor-retries 2 "
            "--retry-sleep 1 "
            f'--js-runtimes "deno:{DENO_BIN}" '
            f'--extractor-args "{YOUTUBE_CLIENT_ARGS}" '
            f'--extractor-args "{YOUTUBE_POT_ARGS}"'
        ),

        spotify_url,
    ]

    logger.info(
        "Starting spotDL download..."
    )

    logger.info(
        "Spotify URL: %s",
        spotify_url,
    )

    logger.info(
        "Running: %s",
        " ".join(map(str, cmd)),
    )

    result = subprocess.run(
        cmd,
        cwd=str(BASE_DIR),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=900,
    )

    if result.stdout:
        logger.info("\n%s", result.stdout)

    logger.info(
        "spotDL exited with code %s",
        result.returncode,
    )

    return result.returncode


def start_telegram_bot():

    token = get_secret("TELEGRAM_TOKEN")

    if not token:

        logger.warning(
            "TELEGRAM_TOKEN missing. "
            "Add TELEGRAM_TOKEN to Streamlit Secrets."
        )

        return

    if not acquire_bot_lock():
        return

    try:

        from telegram import Update
        from telegram.ext import (
            Updater,
            CommandHandler,
            MessageHandler,
            Filters,
            CallbackContext,
        )

    except Exception as e:

        logger.exception(
            "Could not import python-telegram-bot: %s",
            e,
        )

        return

    def start(update: Update, context: CallbackContext):

        update.message.reply_text(
            "سلام 👋\n"
            "لینک آهنگ Spotify را ارسال کن تا دانلود شود."
        )

    def help_command(
        update: Update,
        context: CallbackContext,
    ):

        update.message.reply_text(
            "لینک آهنگ Spotify را ارسال کن."
        )

    def handle_message(
        update: Update,
        context: CallbackContext,
    ):

        if not update.message:
            return

        text = update.message.text or ""

        if "open.spotify.com/track/" not in text:

            update.message.reply_text(
                "لطفاً لینک آهنگ Spotify را ارسال کن."
            )

            return

        spotify_url = text.strip()

        chat_id = update.message.chat_id
        message_id = update.message.message_id

        output_dir = (
            DOWNLOAD_DIR /
            str(chat_id) /
            str(message_id)
        )

        ensure_dir(output_dir)

        status_message = None

        try:

            status_message = update.message.reply_text(
                "⏳ در حال دانلود آهنگ..."
            )

            return_code = run_spotdl_download(
                spotify_url,
                output_dir,
            )

            if return_code != 0:

                logger.error(
                    "spotDL exited with code %s",
                    return_code,
                )

                if status_message:
                    status_message.edit_text(
                        "❌ دانلود انجام نشد."
                    )

                return

            audio_file = find_audio_file(
                output_dir
            )

            if not audio_file:

                logger.warning(
                    "No audio file found after download."
                )

                if status_message:
                    status_message.edit_text(
                        "❌ فایل صوتی بعد از دانلود پیدا نشد."
                    )

                return

            logger.info(
                "Audio file found: %s",
                audio_file,
            )

            with open(audio_file, "rb") as audio:

                update.message.reply_audio(
                    audio=audio,
                    filename=audio_file.name,
                )

            if status_message:
                status_message.delete()

        except subprocess.TimeoutExpired:

            logger.error(
                "spotDL download timed out."
            )

            if status_message:
                status_message.edit_text(
                    "❌ دانلود بیش از حد طول کشید."
                )

        except Exception as e:

            logger.exception(
                "Telegram download error: %s",
                e,
            )

            if status_message:
                try:
                    status_message.edit_text(
                        "❌ خطا هنگام دانلود."
                    )
                except Exception:
                    pass

        finally:

            try:
                shutil.rmtree(
                    output_dir,
                    ignore_errors=True,
                )
            except Exception:
                pass

    updater = Updater(
        token=token,
        use_context=True,
    )

    dispatcher = updater.dispatcher

    dispatcher.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    dispatcher.add_handler(
        CommandHandler(
            "help",
            help_command,
        )
    )

    dispatcher.add_handler(
        MessageHandler(
            Filters.text & ~Filters.command,
            handle_message,
        )
    )

    updater.start_polling(
        drop_pending_updates=True
    )

    logger.info(
        "Telegram bot started."
    )


# ============================================================
# INITIALIZATION
# ============================================================

def initialize_spma():

    global _SPMA_INITIALIZED

    if _SPMA_INITIALIZED:
        return

    logger.info(
        "========================================"
    )

    logger.info(
        "Initializing SPMA..."
    )

    ensure_dir(BASE_DIR)
    ensure_dir(BIN_DIR)
    ensure_dir(DOWNLOAD_DIR)
    ensure_dir(CACHE_DIR)

    ensure_spotdl_environment()

    ensure_deno()

    ensure_ffmpeg()

    start_bgutil_server()

    test_bgutil_ytdlp()

    start_telegram_bot()

    _SPMA_INITIALIZED = True

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
# STREAMLIT
# ============================================================

st.set_page_config(
    page_title="SPMA",
    page_icon="🎵",
)

st.title("🎵 SPMA")

st.write(
    "Spotify downloader bot is running."
)

try:

    initialize_spma()

except Exception as e:

    logger.exception(
        "SPMA initialization failed: %s",
        e,
    )

    st.error(
        f"SPMA initialization failed: {e}"
    )


# ============================================================
# KEEP STREAMLIT PROCESS ALIVE
# ============================================================

while True:

    time.sleep(3600)
