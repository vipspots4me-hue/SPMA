import os
import sys
import time
import signal
import shutil
import subprocess
import tempfile
import urllib.request
import threading
from pathlib import Path

import streamlit as st
from dotenv import dotenv_values


# ============================================================
# GLOBALS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
SPOTDL_VENV = BASE_DIR / ".spotdl_venv"
SPOTDL_PYTHON = SPOTDL_VENV / "bin" / "python"

# Prevent Streamlit reruns from starting another Telegram bot
BOT_STARTED = False
BOT_LOCK = threading.Lock()


# ============================================================
# CPU INFO
# ============================================================

def show_cpu_info():
    try:
        print("\n========== CPU INFO ==========\n")

        result = subprocess.run(
            ["nproc"],
            capture_output=True,
            text=True
        )
        print(result.stdout.strip())

        print()

        result = subprocess.run(
            ["lscpu"],
            capture_output=True,
            text=True
        )
        print(result.stdout)

        print("========== END CPU INFO ==========\n")

    except Exception as e:
        print(f"CPU info error: {e}")


# ============================================================
# CF WARP
# ============================================================

def run_cfwarp():
    print("\n========== CFwarp ==========\n")

    cfwarp_url = (
        "https://raw.githubusercontent.com/yonggekkk/warp-yg/main/CFwarp.sh"
    )

    script_path = Path(tempfile.gettempdir()) / "CFwarp.sh"

    try:
        print("Downloading CFwarp.sh ...")

        urllib.request.urlretrieve(
            cfwarp_url,
            script_path
        )

        os.chmod(script_path, 0o755)

        print("Running CFwarp: 2 -> 1 -> 3")

        process = subprocess.run(
            ["bash", str(script_path)],
            input="2\n1\n3\n",
            text=True,
            capture_output=True
        )

        print(process.stdout)

        if process.stderr:
            print("CFwarp stderr:")
            print(process.stderr)

        print("CFwarp exit code:", process.returncode)

    except Exception as e:
        print("CFwarp error:", e)

    print("\n========== END CFwarp ==========\n")


# ============================================================
# CREATE ISOLATED SPOTDL ENVIRONMENT
# ============================================================

def setup_spotdl():
    """
    Installs spotDL in a separate virtual environment.

    This is necessary because Streamlit installs a newer Starlette,
    while spotDL 4.4.11 requires the older FastAPI/Starlette stack.
    """

    print("\n========== SPOTDL SETUP ==========\n")

    if SPOTDL_PYTHON.exists():
        print("spotDL isolated environment already exists.")
        return

    print("Creating isolated spotDL virtual environment...")

    subprocess.run(
        [
            sys.executable,
            "-m",
            "venv",
            str(SPOTDL_VENV)
        ],
        check=True
    )

    print("Upgrading pip/setuptools...")

    subprocess.run(
        [
            str(SPOTDL_PYTHON),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "pip",
            "setuptools"
        ],
        check=True
    )

    print("Installing spotDL 4.4.11...")

    subprocess.run(
        [
            str(SPOTDL_PYTHON),
            "-m",
            "pip",
            "install",
            "git+https://github.com/TzurSoffer/spotify-downloader@29cb0b0669d5c107331b0912fdef73967b47493e"
        ],
        check=True
    )

    print("Installing yt-dlp 2026.06.09...")

    subprocess.run(
        [
            str(SPOTDL_PYTHON),
            "-m",
            "pip",
            "install",
            "yt-dlp==2026.06.09"
        ],
        check=True
    )

    print("\nspotDL isolated environment ready.\n")


# ============================================================
# FFMPEG
# ============================================================

def setup_ffmpeg():
    print("\n========== FFMPEG ==========\n")

    ffmpeg = shutil.which("ffmpeg")

    if ffmpeg:
        print("FFmpeg already available:")
        print(ffmpeg)

        try:
            subprocess.run(
                ["ffmpeg", "-version"],
                check=False
            )
        except Exception:
            pass

        return

    print("FFmpeg not found.")
    print("Asking spotDL to download FFmpeg...")

    try:
        subprocess.run(
            [
                str(SPOTDL_PYTHON),
                "-m",
                "spotdl",
                "--download-ffmpeg"
            ],
            check=False
        )
    except Exception as e:
        print("FFmpeg setup error:", e)

    print("\n========== END FFMPEG ==========\n")


# ============================================================
# CONFIG
# ============================================================

class Config:
    def __init__(self):
        env_file = BASE_DIR / ".env"

        values = {}

        if env_file.exists():
            values = dotenv_values(env_file)

        self.TELEGRAM_TOKEN = (
            os.getenv("TELEGRAM_TOKEN")
            or values.get("TELEGRAM_TOKEN")
        )

        self.SPOTIFY_CLIENT_ID = (
            os.getenv("SPOTIFY_CLIENT_ID")
            or values.get("SPOTIFY_CLIENT_ID")
            or "5844159a9506462fa5fd2d190238c37e"
        )

        self.SPOTIFY_CLIENT_SECRET = (
            os.getenv("SPOTIFY_CLIENT_SECRET")
            or values.get("SPOTIFY_CLIENT_SECRET")
            or "7736ac0c637c45f0958cb7cb6976db61"
        )


config = Config()


# ============================================================
# TELEGRAM BOT
# ============================================================

def start_telegram_bot():

    global BOT_STARTED

    with BOT_LOCK:

        if BOT_STARTED:
            print("Telegram bot already started. Skipping.")
            return

        BOT_STARTED = True

    print("\n========== TELEGRAM BOT ==========\n")

    if not config.TELEGRAM_TOKEN:
        print("ERROR: TELEGRAM_TOKEN not found.")
        return

    try:
        from telegram.ext import (
            Updater,
            CommandHandler,
            MessageHandler,
            Filters,
            CallbackContext,
        )

        from telegram import Update

        print("Starting Telegram bot...")

        updater = Updater(
            token=config.TELEGRAM_TOKEN,
            use_context=True
        )

        dispatcher = updater.dispatcher

        # ----------------------------------------------------
        # /start
        # ----------------------------------------------------

        def start(update: Update, context: CallbackContext):
            update.message.reply_text(
                "سلام 👋\n"
                "لینک آهنگ Spotify را ارسال کنید."
            )

        # ----------------------------------------------------
        # DOWNLOAD
        # ----------------------------------------------------

        def get_single_song(update: Update, context: CallbackContext):

            url = update.message.text.strip()

            if not url:
                return

            message_id = update.message.message_id
            chat_id = update.effective_chat.id

            temp_dir = BASE_DIR / f".temp{message_id}{chat_id}"

            temp_dir.mkdir(
                parents=True,
                exist_ok=True
            )

            try:

                update.message.reply_text(
                    "⏳ در حال دانلود..."
                )

                command = [
                    str(SPOTDL_PYTHON),
                    "-m",
                    "spotdl",
                    "download",
                    url,

                    "--no-cache",

                    "--client-id",
                    config.SPOTIFY_CLIENT_ID,

                    "--client-secret",
                    config.SPOTIFY_CLIENT_SECRET,

                    "--threads",
                    "8",

                    "--format",
                    "mp3",

                    "--bitrate",
                    "320k",

                    "--output",
                    str(temp_dir / "{title}.{output-ext}"),

                    "--yt-dlp-args",
                    '--extractor-args "youtube:player_client=web_embedded"',
                ]

                print("Running:")
                print(" ".join(command))

                result = subprocess.run(
                    command,
                    cwd=str(temp_dir),
                    capture_output=True,
                    text=True
                )

                print("spotDL stdout:")
                print(result.stdout)

                if result.stderr:
                    print("spotDL stderr:")
                    print(result.stderr)

                if result.returncode != 0:
                    update.message.reply_text(
                        "❌ دانلود ناموفق بود."
                    )
                    return

                mp3_files = list(
                    temp_dir.rglob("*.mp3")
                )

                if not mp3_files:
                    update.message.reply_text(
                        "❌ فایل MP3 پیدا نشد."
                    )
                    return

                for mp3 in mp3_files:

                    print(
                        "Sending:",
                        mp3
                    )

                    with open(mp3, "rb") as audio:

                        update.message.reply_audio(
                            audio=audio,
                            filename=mp3.name
                        )

            except Exception as e:

                print(
                    "Download error:",
                    repr(e)
                )

                try:
                    update.message.reply_text(
                        "❌ خطا در دانلود."
                    )
                except Exception:
                    pass

            finally:

                shutil.rmtree(
                    temp_dir,
                    ignore_errors=True
                )

        # ----------------------------------------------------
        # HANDLERS
        # ----------------------------------------------------

        dispatcher.add_handler(
            CommandHandler(
                "start",
                start
            )
        )

        dispatcher.add_handler(
            MessageHandler(
                Filters.text & ~Filters.command,
                get_single_song
            )
        )

        # ----------------------------------------------------
        # START POLLING
        # ----------------------------------------------------

        updater.start_polling(
            poll_interval=0.5,
            timeout=30,
            drop_pending_updates=True
        )

        print("Bot started successfully.")

        # IMPORTANT:
        # Do NOT call updater.idle() in Streamlit.
        # It attempts to install signal handlers.

        while True:
            time.sleep(3600)

    except Exception as e:

        print(
            "Telegram bot fatal error:",
            repr(e)
        )


# ============================================================
# STREAMLIT
# ============================================================

st.set_page_config(
    page_title="SPMA",
    page_icon="🎵"
)

st.title("🎵 SPMA")
st.write("Spotify Downloader Bot is running.")


# ============================================================
# STARTUP
# ============================================================

if "startup_done" not in st.session_state:

    st.session_state.startup_done = True

    # 1. CPU
    show_cpu_info()

    # 2. CFwarp
    run_cfwarp()

    # 3. Isolated spotDL
    setup_spotdl()

    # 4. FFmpeg
    setup_ffmpeg()


# ============================================================
# START TELEGRAM ONLY ONCE
# ============================================================

if not BOT_STARTED:

    thread = threading.Thread(
        target=start_telegram_bot,
        daemon=True
    )

    thread.start()

    print(
        "Telegram bot thread started."
    )
