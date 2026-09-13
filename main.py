import os
import sys
import time
import subprocess
import threading
import shutil
import platform
import fcntl

import streamlit as st


# =========================================================
# CONFIG
# =========================================================

BASE_DIR = "/mount/src/spma"
SPOTDL_VENV = os.path.join(BASE_DIR, ".spotdl_venv")
SPOTDL_PYTHON = os.path.join(SPOTDL_VENV, "bin", "python")
SPOTDL_BIN = os.path.join(SPOTDL_VENV, "bin", "spotdl")

FFMPEG_PATH = os.path.expanduser("~/.config/spotdl/ffmpeg")

LOCK_FILE = "/tmp/spma_bot.lock"


# =========================================================
# HELPERS
# =========================================================

def run_cmd(cmd, timeout=300, env=None):
    print("\n$ " + " ".join(map(str, cmd)))

    try:
        result = subprocess.run(
            cmd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            env=env,
        )

        print(result.stdout)
        print(f"Exit code: {result.returncode}")

        return result.returncode, result.stdout

    except subprocess.TimeoutExpired:
        print("COMMAND TIMEOUT")
        return -1, ""

    except Exception as e:
        print("COMMAND ERROR:", e)
        return -1, ""


# =========================================================
# CPU INFO
# =========================================================

def cpu_info():
    print("\n" + "=" * 60)
    print("CPU INFO")
    print("=" * 60)

    print("Python:", sys.version)
    print("Platform:", platform.platform())
    print("CPU count:", os.cpu_count())

    run_cmd(["nproc"], timeout=20)
    run_cmd(["lscpu"], timeout=20)


# =========================================================
# ROOT TEST
# =========================================================

def root_test():
    print("\n" + "=" * 60)
    print("ROOT TEST")
    print("=" * 60)

    print("Python UID:", os.getuid())
    print("USER:", os.getenv("USER"))
    print("HOME:", os.getenv("HOME"))

    run_cmd(["id"], timeout=20)
    run_cmd(["whoami"], timeout=20)

    sudo = shutil.which("sudo")

    if sudo:
        print("sudo:", sudo)
        run_cmd(["sudo", "-n", "id"], timeout=20)

    if os.getuid() == 0:
        print("ROOT STATUS: ROOT")
    else:
        print("ROOT STATUS: NOT ROOT")


# =========================================================
# SPOTDL SETUP
# =========================================================

def setup_spotdl():
    print("\n" + "=" * 60)
    print("SPOTDL SETUP")
    print("=" * 60)

    os.makedirs(BASE_DIR, exist_ok=True)

    # -----------------------------------------------------
    # Create isolated venv
    # -----------------------------------------------------

    if not os.path.exists(SPOTDL_PYTHON):
        print("Creating isolated spotDL virtual environment...")

        run_cmd(
            [
                sys.executable,
                "-m",
                "venv",
                SPOTDL_VENV,
            ],
            timeout=300,
        )

    # -----------------------------------------------------
    # Upgrade pip
    # -----------------------------------------------------

    run_cmd(
        [
            SPOTDL_PYTHON,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "pip",
            "setuptools",
            "wheel",
        ],
        timeout=600,
    )

    # -----------------------------------------------------
    # Install spotDL
    # -----------------------------------------------------

    print("\nInstalling spotDL 4.4.11...")

    run_cmd(
        [
            SPOTDL_PYTHON,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "git+https://github.com/TzurSoffer/spotify-downloader@29cb0b0669d5c107331b0912fdef73967b47493e",
        ],
        timeout=900,
    )

    # -----------------------------------------------------
    # Force known yt-dlp version
    # -----------------------------------------------------

    print("\nInstalling yt-dlp...")

    run_cmd(
        [
            SPOTDL_PYTHON,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "yt-dlp==2026.06.09",
        ],
        timeout=600,
    )

    # -----------------------------------------------------
    # Version check
    # -----------------------------------------------------

    print("\nChecking versions...")

    run_cmd(
        [
            SPOTDL_PYTHON,
            "-m",
            "spotdl",
            "--version",
        ],
        timeout=60,
    )

    run_cmd(
        [
            SPOTDL_PYTHON,
            "-m",
            "yt_dlp",
            "--version",
        ],
        timeout=60,
    )


# =========================================================
# FFMPEG
# =========================================================

def setup_ffmpeg():
    print("\n" + "=" * 60)
    print("FFMPEG SETUP")
    print("=" * 60)

    if os.path.exists(FFMPEG_PATH):
        print("FFmpeg already exists:")
        print(FFMPEG_PATH)
    else:
        print("FFmpeg not found.")
        print("Asking spotDL to download FFmpeg...")

        run_cmd(
            [
                SPOTDL_PYTHON,
                "-m",
                "spotdl",
                "--download-ffmpeg",
            ],
            timeout=900,
        )

    if os.path.exists(FFMPEG_PATH):
        print("FFmpeg successfully found:")
        print(FFMPEG_PATH)

        # Put FFmpeg directory at the beginning of PATH
        ffmpeg_dir = os.path.dirname(FFMPEG_PATH)

        os.environ["PATH"] = (
            ffmpeg_dir
            + os.pathsep
            + os.environ.get("PATH", "")
        )

        print("PATH updated.")

        run_cmd(
            [FFMPEG_PATH, "-version"],
            timeout=30,
        )

    else:
        print("WARNING: FFmpeg still not found.")


# =========================================================
# YOUTUBE TEST
# =========================================================

def test_youtube():
    print("\n" + "=" * 60)
    print("YOUTUBE / YT-DLP TEST")
    print("=" * 60)

    test_url = "https://www.youtube.com/watch?v=0loPj-nIG7c"

    env = os.environ.copy()

    if os.path.exists(FFMPEG_PATH):
        env["PATH"] = (
            os.path.dirname(FFMPEG_PATH)
            + os.pathsep
            + env.get("PATH", "")
        )

    # -----------------------------------------------------
    # Metadata test
    # -----------------------------------------------------

    print("\nTesting YouTube metadata...")

    code, output = run_cmd(
        [
            SPOTDL_PYTHON,
            "-m",
            "yt_dlp",
            "--no-playlist",
            "--skip-download",
            test_url,
        ],
        timeout=180,
        env=env,
    )

    if code == 0:
        print("YT-DLP METADATA TEST: SUCCESS")
    else:
        print("YT-DLP METADATA TEST: FAILED")

    # -----------------------------------------------------
    # Actual small download test
    # -----------------------------------------------------

    print("\nTesting actual YouTube download...")

    test_dir = "/tmp/yt_test"
    os.makedirs(test_dir, exist_ok=True)

    code, output = run_cmd(
        [
            SPOTDL_PYTHON,
            "-m",
            "yt_dlp",
            "--no-playlist",
            "-f",
            "18",
            "-o",
            os.path.join(test_dir, "%(id)s.%(ext)s"),
            test_url,
        ],
        timeout=300,
        env=env,
    )

    if code == 0:
        print("YT-DLP DOWNLOAD TEST: SUCCESS")
    else:
        print("YT-DLP DOWNLOAD TEST: FAILED")

    return code == 0


# =========================================================
# TELEGRAM BOT LOCK
# =========================================================

def acquire_bot_lock():
    """
    Prevent multiple Telegram polling instances
    inside the same Streamlit container.
    """

    lock_fp = open(LOCK_FILE, "w")

    try:
        fcntl.flock(
            lock_fp,
            fcntl.LOCK_EX | fcntl.LOCK_NB
        )

        print("Telegram bot lock acquired.")
        return lock_fp

    except BlockingIOError:
        print("Telegram bot is already running.")
        lock_fp.close()
        return None


# =========================================================
# BOT
# =========================================================

def start_bot():
    print("\n" + "=" * 60)
    print("STARTING TELEGRAM BOT")
    print("=" * 60)

    token = os.getenv("TELEGRAM_TOKEN")

    if not token:
        print("ERROR: TELEGRAM_TOKEN not found.")
        return

    print("Telegram token found.")

    # -----------------------------------------------------
    # Import here so Streamlit environment stays isolated
    # -----------------------------------------------------

    from telegram.ext import (
        Updater,
        CommandHandler,
        MessageHandler,
        Filters,
    )

    def start(update, context):
        update.message.reply_text(
            "SPMA bot is online."
        )

    updater = Updater(
        token=token,
        use_context=True,
    )

    dispatcher = updater.dispatcher

    dispatcher.add_handler(
        CommandHandler("start", start)
    )

    updater.start_polling(
        drop_pending_updates=True
    )

    print("Telegram polling is active.")

    # IMPORTANT:
    # Do NOT use updater.idle()
    # because Streamlit owns the process signals.

    while True:
        time.sleep(3600)


# =========================================================
# BOT THREAD
# =========================================================

def start_bot_thread():
    global _BOT_LOCK_FP

    if globals().get("_BOT_THREAD_STARTED", False):
        print("Bot thread already started.")
        return

    lock_fp = acquire_bot_lock()

    if lock_fp is None:
        return

    _BOT_LOCK_FP = lock_fp

    _BOT_THREAD_STARTED = True

    thread = threading.Thread(
        target=start_bot,
        daemon=True,
        name="telegram-bot",
    )

    thread.start()

    print("Telegram bot thread started.")


# =========================================================
# MAIN
# =========================================================

def main():
    print("\n")
    print("=" * 70)
    print("SPMA START")
    print("=" * 70)

    cpu_info()

    # NO CFwarp here
    print("\nCFwarp: DISABLED")

    root_test()

    setup_spotdl()

    setup_ffmpeg()

    youtube_ok = test_youtube()

    if not youtube_ok:
        print("\nWARNING:")
        print("YouTube actual download test failed.")
        print("Bot will NOT be started until this is fixed.")
        return

    start_bot_thread()

    print("\n" + "=" * 70)
    print("SPMA INITIALIZATION COMPLETE")
    print("=" * 70)


# =========================================================
# STREAMLIT
# =========================================================

st.title("SPMA")

if not globals().get("_SPMA_INITIALIZED", False):
    globals()["_SPMA_INITIALIZED"] = True

    try:
        main()
    except Exception as e:
        print("\nFATAL ERROR:")
        print(repr(e))
        raise
else:
    print("SPMA already initialized.")
