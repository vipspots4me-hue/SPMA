import os
import sys
import time
import subprocess
import tempfile
import urllib.request
import threading
import shutil
import signal

import streamlit as st


# ============================================================
# CONFIG
# ============================================================

SPOTDL_VENV = os.path.join(os.getcwd(), ".spotdl_venv")

SPOTDL_PYTHON = os.path.join(
    SPOTDL_VENV,
    "bin",
    "python"
)

SPOTDL_CMD = os.path.join(
    SPOTDL_VENV,
    "bin",
    "spotdl"
)

YT_DLP_VERSION = "2026.06.09"

SPOTDL_GIT = (
    "git+https://github.com/TzurSoffer/"
    "spotify-downloader@"
    "29cb0b0669d5c107331b0912fdef73967b47493e"
)

CFWARP_URL = (
    "https://raw.githubusercontent.com/"
    "yonggekkk/warp-yg/main/CFwarp.sh"
)


# ============================================================
# HELPERS
# ============================================================

def run_command(cmd, input_text=None, cwd=None):
    print()
    print("Running:")
    print(" ".join(str(x) for x in cmd))
    print()

    try:
        result = subprocess.run(
            cmd,
            input=input_text,
            text=True,
            capture_output=True,
            cwd=cwd
        )

        if result.stdout:
            print(result.stdout)

        if result.stderr:
            print(result.stderr)

        print("Exit code:", result.returncode)

        return result

    except Exception as e:
        print("COMMAND ERROR:", repr(e))
        return None


# ============================================================
# CPU INFO
# ============================================================

def cpu_info():

    print()
    print("========== CPU INFO ==========")

    run_command(["nproc"])

    run_command(["lscpu"])

    print("========= END CPU INFO ==========")


# ============================================================
# ROOT TEST
# ============================================================

def root_test():

    print()
    print("========== ROOT TEST ==========")

    try:
        print("Python UID:", os.getuid())
    except Exception as e:
        print("Cannot get UID:", e)

    print("USER:", os.environ.get("USER"))
    print("HOME:", os.environ.get("HOME"))

    run_command(
        [
            "bash",
            "-c",
            "id; echo '--- whoami ---'; whoami; "
            "echo '--- sudo ---'; command -v sudo || true; "
            "echo '--- sudo id ---'; sudo -n id 2>&1 || true"
        ]
    )

    try:
        if os.getuid() == 0:
            print("ROOT STATUS: ROOT")
            return True
        else:
            print("ROOT STATUS: NOT ROOT")
            return False
    except Exception:
        return False


# ============================================================
# CFWARP
# ============================================================

def run_cfwarp():

    print()
    print("========== CFwarp ==========")

    print("Downloading CFwarp.sh ...")

    script_path = "/tmp/CFwarp.sh"

    try:
        urllib.request.urlretrieve(
            CFWARP_URL,
            script_path
        )

        os.chmod(script_path, 0o755)

        print("CFwarp downloaded successfully.")

    except Exception as e:
        print("CFwarp download error:", repr(e))
        print("========== END CFwarp ==========")
        return False

    # --------------------------------------------------------
    # Check root
    # --------------------------------------------------------

    try:
        uid = os.getuid()
    except Exception:
        uid = -1

    if uid != 0:

        print()
        print("WARNING: Streamlit process is NOT root.")
        print("CFwarp requires root privileges.")
        print("Skipping CFwarp because root is unavailable.")

        print("========== END CFwarp ==========")

        return False

    # --------------------------------------------------------
    # Run CFwarp
    # Requested order:
    # 3 -> 1 -> 3
    # --------------------------------------------------------

    print()
    print("ROOT detected.")
    print("Running CFwarp: 3 -> 1 -> 3")
    print()

    try:

        result = subprocess.run(
            ["bash", script_path],
            input="3\n1\n3\n",
            text=True,
            capture_output=True
        )

        print("CFwarp STDOUT:")
        print(result.stdout)

        print()
        print("CFwarp STDERR:")
        print(result.stderr)

        print()
        print("CFwarp exit code:", result.returncode)

        if result.returncode == 0:
            print("CFwarp command finished.")
        else:
            print("CFwarp failed.")

        print("========== END CFwarp ==========")

        return result.returncode == 0

    except Exception as e:

        print("CFwarp execution error:", repr(e))

        print("========== END CFwarp ==========")

        return False


# ============================================================
# CREATE SPOTDL VENV
# ============================================================

def setup_spotdl():

    print()
    print("========== SPOTDL SETUP ==========")

    if not os.path.exists(SPOTDL_VENV):

        print("Creating isolated spotDL virtual environment...")

        r = run_command(
            [
                sys.executable,
                "-m",
                "venv",
                SPOTDL_VENV
            ]
        )

        if r is None or r.returncode != 0:
            raise RuntimeError(
                "Could not create spotDL virtual environment."
            )

    else:

        print("spotDL virtual environment already exists.")

    # --------------------------------------------------------
    # Upgrade pip/setuptools
    # --------------------------------------------------------

    print("Upgrading pip/setuptools...")

    run_command(
        [
            SPOTDL_PYTHON,
            "-m",
            "pip",
            "install",
            "-U",
            "pip",
            "setuptools"
        ]
    )

    # --------------------------------------------------------
    # Install spotDL fork
    # --------------------------------------------------------

    print("Installing spotDL 4.4.11...")

    r = run_command(
        [
            SPOTDL_PYTHON,
            "-m",
            "pip",
            "install",
            "--upgrade",
            SPOTDL_GIT
        ]
    )

    if r is None or r.returncode != 0:
        raise RuntimeError(
            "spotDL installation failed."
        )

    # --------------------------------------------------------
    # Force requested yt-dlp version
    # --------------------------------------------------------

    print(
        "Installing yt-dlp "
        + YT_DLP_VERSION
        + "..."
    )

    r = run_command(
        [
            SPOTDL_PYTHON,
            "-m",
            "pip",
            "install",
            "--force-reinstall",
            "yt-dlp==" + YT_DLP_VERSION
        ]
    )

    if r is None or r.returncode != 0:
        raise RuntimeError(
            "yt-dlp installation failed."
        )

    # --------------------------------------------------------
    # Verify versions
    # --------------------------------------------------------

    print()
    print("========== SPOTDL VERSION ==========")

    run_command(
        [
            SPOTDL_PYTHON,
            "-m",
            "spotdl",
            "--version"
        ]
    )

    print()
    print("========== YT-DLP VERSION ==========")

    run_command(
        [
            SPOTDL_PYTHON,
            "-m",
            "yt_dlp",
            "--version"
        ]
    )

    print()
    print("spotDL isolated environment ready.")


# ============================================================
# FFMPEG
# ============================================================

def setup_ffmpeg():

    print()
    print("========== FFMPEG ==========")

    # First check system FFmpeg

    system_ffmpeg = shutil.which("ffmpeg")

    if system_ffmpeg:

        print("System FFmpeg found:")
        print(system_ffmpeg)

    else:

        print("FFmpeg not found.")
        print("Asking spotDL to download FFmpeg...")

        result = run_command(
            [
                SPOTDL_PYTHON,
                "-m",
                "spotdl",
                "--download-ffmpeg"
            ]
        )

        if result is None:
            print("FFmpeg command failed.")

    print("========== END FFMPEG ==========")


# ============================================================
# DIRECT YT-DLP NETWORK TEST
# ============================================================

def test_youtube():

    print()
    print("========== YOUTUBE / YT-DLP TEST ==========")

    test_url = (
        "https://www.youtube.com/watch?v=0loPj-nIG7c"
    )

    print("Testing:")
    print(test_url)

    result = run_command(
        [
            SPOTDL_PYTHON,
            "-m",
            "yt_dlp",
            "-v",
            "--skip-download",
            test_url
        ]
    )

    if result is not None and result.returncode == 0:
        print()
        print("YT-DLP TEST: SUCCESS")
    else:
        print()
        print("YT-DLP TEST: FAILED")

    print("========== END YOUTUBE TEST ==========")


# ============================================================
# TELEGRAM BOT
# ============================================================

def start_bot():

    print()
    print("Starting Telegram bot...")

    try:

        from telegram.ext import (
            Updater,
            CommandHandler,
            MessageHandler,
            Filters
        )

        from dotenv import load_dotenv

        load_dotenv()

        token = (
            os.environ.get("TELEGRAM_TOKEN")
            or st.secrets.get("TELEGRAM_TOKEN", "")
        )

        if not token:
            raise RuntimeError(
                "TELEGRAM_TOKEN was not found."
            )

        print("Telegram token found.")

        # ----------------------------------------------------
        # IMPORTANT:
        # Put your existing bot handlers here.
        # ----------------------------------------------------

        updater = Updater(
            token=token,
            use_context=True
        )

        dispatcher = updater.dispatcher

        # ----------------------------------------------------
        # Example /start
        # ----------------------------------------------------

        def start(update, context):

            update.message.reply_text(
                "🎵 SPMA\n\n"
                "Spotify Downloader Bot is running."
            )

        dispatcher.add_handler(
            CommandHandler(
                "start",
                start
            )
        )

        # ----------------------------------------------------
        # Your existing Spotify handler should be added here.
        # ----------------------------------------------------

        updater.start_polling(
            drop_pending_updates=True
        )

        print()
        print("Bot started successfully.")
        print("Telegram polling is active.")

        # DO NOT use updater.idle()
        # because Streamlit can raise signal errors.

        while True:
            time.sleep(3600)

    except Exception as e:

        print()
        print("TELEGRAM BOT ERROR:")
        print(repr(e))


# ============================================================
# START BOT ONLY ONCE
# ============================================================

def start_bot_thread():

    if globals().get("_BOT_STARTED", False):

        print(
            "Telegram bot already started; "
            "not starting another instance."
        )

        return

    globals()["_BOT_STARTED"] = True

    thread = threading.Thread(
        target=start_bot,
        daemon=True
    )

    thread.start()

    print("Telegram bot thread started.")


# ============================================================
# MAIN SETUP
# ============================================================

def main():

    print()
    print("======================================")
    print("             SPMA START")
    print("======================================")

    # --------------------------------------------------------
    # 1. CPU
    # --------------------------------------------------------

    cpu_info()

    # --------------------------------------------------------
    # 2. ROOT TEST
    # --------------------------------------------------------

    is_root = root_test()

    # --------------------------------------------------------
    # 3. CFwarp
    # --------------------------------------------------------

    run_cfwarp()

    # --------------------------------------------------------
    # 4. spotDL
    # --------------------------------------------------------

    setup_spotdl()

    # --------------------------------------------------------
    # 5. FFmpeg
    # --------------------------------------------------------

    setup_ffmpeg()

    # --------------------------------------------------------
    # 6. Direct YouTube test
    # --------------------------------------------------------

    test_youtube()

    # --------------------------------------------------------
    # 7. Telegram
    # --------------------------------------------------------

    print()
    print("========== TELEGRAM BOT ==========")

    start_bot_thread()


# ============================================================
# STREAMLIT UI
# ============================================================

st.set_page_config(
    page_title="SPMA",
    page_icon="🎵"
)

st.title("🎵 SPMA")

st.write(
    "Spotify Downloader Bot"
)

# Run initialization once per Python process
if not globals().get("_SPMA_INITIALIZED", False):

    globals()["_SPMA_INITIALIZED"] = True

    try:

        main()

    except Exception as e:

        print()
        print("========== FATAL ERROR ==========")
        print(repr(e))
        print("========== END FATAL ERROR ==========")

        st.error(
            "SPMA startup error: "
            + str(e)
        )

else:

    print(
        "SPMA already initialized."
    )
