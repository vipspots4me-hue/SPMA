import os
import sys
import time
import subprocess
import threading
import shutil

import streamlit as st


# ============================================================
# CONFIG
# ============================================================

SPOTDL_VENV = os.path.join(
    os.getcwd(),
    ".spotdl_venv"
)

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

FFMPEG_PATH = os.path.expanduser(
    "~/.config/spotdl/ffmpeg"
)


# ============================================================
# HELPERS
# ============================================================

def run_command(cmd, input_text=None, cwd=None, env=None, timeout=600):

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
            cwd=cwd,
            env=env,
            timeout=timeout
        )

        if result.stdout:
            print(result.stdout)

        if result.stderr:
            print(result.stderr)

        print("Exit code:", result.returncode)

        return result

    except subprocess.TimeoutExpired:

        print("COMMAND TIMEOUT")
        return None

    except Exception as e:

        print("COMMAND ERROR:", repr(e))
        return None


# ============================================================
# CPU INFO
# ============================================================

def cpu_info():

    print()
    print("========== CPU INFO ==========")

    run_command(
        ["nproc"],
        timeout=30
    )

    run_command(
        ["lscpu"],
        timeout=30
    )

    print("======== END CPU INFO ========")


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
            (
                "id; "
                "echo '--- whoami ---'; "
                "whoami; "
                "echo '--- sudo ---'; "
                "command -v sudo || true; "
                "echo '--- sudo id ---'; "
                "sudo -n id 2>&1 || true"
            )
        ],
        timeout=30
    )

    try:

        if os.getuid() == 0:
            print("ROOT STATUS: ROOT")
            return True

        print("ROOT STATUS: NOT ROOT")
        return False

    except Exception:

        return False


# ============================================================
# SPOTDL SETUP
# ============================================================

def setup_spotdl():

    print()
    print("========== SPOTDL SETUP ==========")

    # --------------------------------------------------------
    # Create virtual environment
    # --------------------------------------------------------

    if not os.path.exists(SPOTDL_VENV):

        print(
            "Creating isolated spotDL virtual environment..."
        )

        result = run_command(
            [
                sys.executable,
                "-m",
                "venv",
                SPOTDL_VENV
            ],
            timeout=300
        )

        if result is None or result.returncode != 0:

            raise RuntimeError(
                "Could not create spotDL virtual environment."
            )

    else:

        print(
            "spotDL virtual environment already exists."
        )

    # --------------------------------------------------------
    # Upgrade pip / setuptools
    # --------------------------------------------------------

    print(
        "Upgrading pip/setuptools..."
    )

    result = run_command(
        [
            SPOTDL_PYTHON,
            "-m",
            "pip",
            "install",
            "-U",
            "pip",
            "setuptools",
            "wheel"
        ],
        timeout=600
    )

    if result is None or result.returncode != 0:

        raise RuntimeError(
            "pip/setuptools upgrade failed."
        )

    # --------------------------------------------------------
    # Install spotDL
    # --------------------------------------------------------

    print(
        "Installing spotDL 4.4.11..."
    )

    result = run_command(
        [
            SPOTDL_PYTHON,
            "-m",
            "pip",
            "install",
            "--upgrade",
            SPOTDL_GIT
        ],
        timeout=900
    )

    if result is None or result.returncode != 0:

        raise RuntimeError(
            "spotDL installation failed."
        )

    # --------------------------------------------------------
    # Install yt-dlp
    # --------------------------------------------------------

    print(
        "Installing yt-dlp "
        + YT_DLP_VERSION
        + "..."
    )

    result = run_command(
        [
            SPOTDL_PYTHON,
            "-m",
            "pip",
            "install",
            "--force-reinstall",
            "yt-dlp==" + YT_DLP_VERSION
        ],
        timeout=600
    )

    if result is None or result.returncode != 0:

        raise RuntimeError(
            "yt-dlp installation failed."
        )

    # --------------------------------------------------------
    # Verify spotDL
    # --------------------------------------------------------

    print()
    print("========== SPOTDL VERSION ==========")

    run_command(
        [
            SPOTDL_PYTHON,
            "-m",
            "spotdl",
            "--version"
        ],
        timeout=60
    )

    # --------------------------------------------------------
    # Verify yt-dlp
    # --------------------------------------------------------

    print()
    print("========== YT-DLP VERSION ==========")

    run_command(
        [
            SPOTDL_PYTHON,
            "-m",
            "yt_dlp",
            "--version"
        ],
        timeout=60
    )

    print()
    print("spotDL isolated environment ready.")


# ============================================================
# FFMPEG
# ============================================================

def setup_ffmpeg():

    print()
    print("========== FFMPEG ==========")

    # --------------------------------------------------------
    # System FFmpeg
    # --------------------------------------------------------

    system_ffmpeg = shutil.which("ffmpeg")

    if system_ffmpeg:

        print(
            "System FFmpeg found:"
        )

        print(system_ffmpeg)

        ffmpeg_dir = os.path.dirname(
            system_ffmpeg
        )

        os.environ["PATH"] = (
            ffmpeg_dir
            + os.pathsep
            + os.environ.get("PATH", "")
        )

    # --------------------------------------------------------
    # spotDL FFmpeg
    # --------------------------------------------------------

    elif os.path.exists(FFMPEG_PATH):

        print(
            "spotDL FFmpeg found:"
        )

        print(FFMPEG_PATH)

        ffmpeg_dir = os.path.dirname(
            FFMPEG_PATH
        )

        os.environ["PATH"] = (
            ffmpeg_dir
            + os.pathsep
            + os.environ.get("PATH", "")
        )

    # --------------------------------------------------------
    # Download FFmpeg
    # --------------------------------------------------------

    else:

        print("FFmpeg not found.")
        print(
            "Asking spotDL to download FFmpeg..."
        )

        result = run_command(
            [
                SPOTDL_PYTHON,
                "-m",
                "spotdl",
                "--download-ffmpeg"
            ],
            timeout=900
        )

        if result is None:

            print(
                "FFmpeg download command failed."
            )

    # --------------------------------------------------------
    # Re-check
    # --------------------------------------------------------

    if os.path.exists(FFMPEG_PATH):

        print(
            "FFmpeg available at:"
        )

        print(FFMPEG_PATH)

        ffmpeg_dir = os.path.dirname(
            FFMPEG_PATH
        )

        os.environ["PATH"] = (
            ffmpeg_dir
            + os.pathsep
            + os.environ.get("PATH", "")
        )

    # --------------------------------------------------------
    # Final test
    # --------------------------------------------------------

    final_ffmpeg = shutil.which("ffmpeg")

    if final_ffmpeg:

        print(
            "FFmpeg executable:"
        )

        print(final_ffmpeg)

        run_command(
            [
                final_ffmpeg,
                "-version"
            ],
            timeout=30
        )

    else:

        print(
            "WARNING: FFmpeg executable was not found in PATH."
        )

    print("======== END FFMPEG ========")


# ============================================================
# DIRECT YOUTUBE / YT-DLP TEST
# ============================================================

def test_youtube():

    print()
    print(
        "========== YOUTUBE / YT-DLP TEST =========="
    )

    test_url = (
        "https://www.youtube.com/watch?v=0loPj-nIG7c"
    )

    print("Testing:")
    print(test_url)

    env = os.environ.copy()

    # Make sure spotDL FFmpeg is visible to yt-dlp
    if os.path.exists(FFMPEG_PATH):

        ffmpeg_dir = os.path.dirname(
            FFMPEG_PATH
        )

        env["PATH"] = (
            ffmpeg_dir
            + os.pathsep
            + env.get("PATH", "")
        )

    # --------------------------------------------------------
    # Test 1: Metadata
    # --------------------------------------------------------

    print()
    print("----- YT-DLP METADATA TEST -----")

    result = run_command(
        [
            SPOTDL_PYTHON,
            "-m",
            "yt_dlp",
            "--no-playlist",
            "--skip-download",
            test_url
        ],
        env=env,
        timeout=180
    )

    if result is not None and result.returncode == 0:

        print()
        print(
            "YT-DLP METADATA TEST: SUCCESS"
        )

    else:

        print()
        print(
            "YT-DLP METADATA TEST: FAILED"
        )

        return False

    # --------------------------------------------------------
    # Test 2: Actual media download
    # --------------------------------------------------------

    print()
    print("----- YT-DLP DOWNLOAD TEST -----")

    test_dir = "/tmp/yt_test"

    os.makedirs(
        test_dir,
        exist_ok=True
    )

    output_template = os.path.join(
        test_dir,
        "%(id)s.%(ext)s"
    )

    result = run_command(
        [
            SPOTDL_PYTHON,
            "-m",
            "yt_dlp",
            "--no-playlist",
            "-f",
            "18",
            "-o",
            output_template,
            test_url
        ],
        env=env,
        timeout=300
    )

    if result is not None and result.returncode == 0:

        print()
        print(
            "YT-DLP DOWNLOAD TEST: SUCCESS"
        )

        # Show downloaded file
        try:

            files = os.listdir(test_dir)

            print(
                "Downloaded files:"
            )

            for filename in files:
                print(
                    os.path.join(
                        test_dir,
                        filename
                    )
                )

        except Exception:
            pass

        return True

    print()
    print(
        "YT-DLP DOWNLOAD TEST: FAILED"
    )

    return False


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
            or st.secrets.get(
                "TELEGRAM_TOKEN",
                ""
            )
        )

        if not token:

            raise RuntimeError(
                "TELEGRAM_TOKEN was not found."
            )

        print(
            "Telegram token found."
        )

        # ----------------------------------------------------
        # Updater
        # ----------------------------------------------------

        updater = Updater(
            token=token,
            use_context=True
        )

        dispatcher = updater.dispatcher

        # ----------------------------------------------------
        # /start
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
        # IMPORTANT
        # ----------------------------------------------------
        # Your existing Spotify handlers should be added here.
        #
        # Do NOT use:
        #
        # updater.idle()
        #
        # because Streamlit owns the process signals.
        # ----------------------------------------------------

        updater.start_polling(
            drop_pending_updates=True
        )

        print()
        print(
            "Bot started successfully."
        )

        print(
            "Telegram polling is active."
        )

        while True:

            time.sleep(3600)

    except Exception as e:

        print()
        print(
            "TELEGRAM BOT ERROR:"
        )

        print(
            repr(e)
        )


# ============================================================
# START BOT ONLY ONCE
# ============================================================

def start_bot_thread():

    if globals().get(
        "_BOT_STARTED",
        False
    ):

        print(
            "Telegram bot already started; "
            "not starting another instance."
        )

        return

    globals()[
        "_BOT_STARTED"
    ] = True

    thread = threading.Thread(
        target=start_bot,
        daemon=True,
        name="telegram-bot"
    )

    thread.start()

    print(
        "Telegram bot thread started."
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print(
        "======================================"
    )

    print(
        "             SPMA START"
    )

    print(
        "======================================"
    )

    # --------------------------------------------------------
    # 1. CPU
    # --------------------------------------------------------

    cpu_info()

    # --------------------------------------------------------
    # 2. ROOT TEST
    # --------------------------------------------------------

    root_test()

    # --------------------------------------------------------
    # 3. NO CFWARP
    # --------------------------------------------------------

    print()
    print(
        "CFwarp: DISABLED"
    )

    # --------------------------------------------------------
    # 4. spotDL
    # --------------------------------------------------------

    setup_spotdl()

    # --------------------------------------------------------
    # 5. FFmpeg
    # --------------------------------------------------------

    setup_ffmpeg()

    # --------------------------------------------------------
    # 6. YouTube / yt-dlp
    # --------------------------------------------------------

    youtube_ok = test_youtube()

    if not youtube_ok:

        print()
        print(
            "WARNING: YouTube download test failed."
        )

        print(
            "Telegram bot will still be started."
        )

    # --------------------------------------------------------
    # 7. Telegram
    # --------------------------------------------------------

    print()
    print(
        "========== TELEGRAM BOT =========="
    )

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


# ============================================================
# INITIALIZE ONLY ONCE
# ============================================================

if not globals().get(
    "_SPMA_INITIALIZED",
    False
):

    globals()[
        "_SPMA_INITIALIZED"
    ] = True

    try:

        main()

    except Exception as e:

        print()
        print(
            "========== FATAL ERROR =========="
        )

        print(
            repr(e)
        )

        print(
            "========== END FATAL ERROR =========="
        )

        st.error(
            "SPMA startup error: "
            + str(e)
        )

else:

    print(
        "SPMA already initialized."
    )
