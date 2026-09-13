import os
import sys
import time
import logging
import subprocess
import tempfile
import urllib.request


# ============================================================
# CPU INFORMATION
# ============================================================

print("\n========== NPROC ==========\n")

try:
    subprocess.run(
        ["nproc"],
        check=False
    )
except Exception as e:
    print(f"nproc error: {e}")


print("\n========== LSCPU ==========\n")

try:
    subprocess.run(
        ["lscpu"],
        check=False
    )
except Exception as e:
    print(f"lscpu error: {e}")


# ============================================================
# CF WARP
# Options: 2 -> 1 -> 3
# ============================================================

print("\n========== CFwarp ==========\n")
print("Starting CFwarp automatically: 2 -> 1 -> 3\n")

cfwarp_url = (
    "https://raw.githubusercontent.com/"
    "yonggekkk/warp-yg/main/CFwarp.sh"
)

cfwarp_script = None

try:

    with tempfile.NamedTemporaryFile(
        mode="wb",
        suffix=".sh",
        delete=False
    ) as f:

        cfwarp_script = f.name

    print("Downloading CFwarp.sh...")

    urllib.request.urlretrieve(
        cfwarp_url,
        cfwarp_script
    )

    os.chmod(
        cfwarp_script,
        0o755
    )

    print("Running CFwarp...")
    print("Automatic input: 2 -> 1 -> 3\n")

    result = subprocess.run(
        ["bash", cfwarp_script],
        input="2\n1\n3\n",
        text=True,
        check=False
    )

    print(
        f"\nCFwarp exit code: {result.returncode}"
    )

except Exception as e:

    print(
        f"CFwarp error: {e}"
    )

finally:

    if (
        cfwarp_script
        and os.path.exists(cfwarp_script)
    ):

        try:
            os.remove(cfwarp_script)
        except Exception:
            pass


print("\n========== CFwarp finished ==========\n")


# ============================================================
# SPOTDL - DOWNLOAD FFMPEG
# ============================================================

print("\n========== spotDL FFmpeg ==========\n")

try:

    subprocess.run(
        [
            sys.executable,
            "-m",
            "spotdl",
            "--download-ffmpeg"
        ],
        check=False
    )

except Exception as e:

    print(
        f"FFmpeg installation error: {e}"
    )


# ============================================================
# TELEGRAM
# ============================================================

from dotenv import dotenv_values

from telegram import Update

from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackContext
)


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    format=(
        "%(asctime)s - "
        "%(name)s - "
        "%(levelname)s - "
        "%(message)s"
    ),
    level=logging.INFO
)

logger = logging.getLogger(__name__)


# ============================================================
# CONFIG
# ============================================================

class Config:

    def __init__(self):

        self.load_config()


    def load_config(self):

        token = None

        try:

            values = dotenv_values(
                ".env"
            )

            token = values.get(
                "TELEGRAM_TOKEN"
            )

        except Exception as e:

            logger.error(
                f"Failed to load .env: {e}"
            )


        if not token:

            token = os.environ.get(
                "TELEGRAM_TOKEN"
            )


        if not token:

            logger.error(
                "Telegram token not found."
            )

            raise ValueError(
                "Telegram token not found."
            )


        self.token = token

        # Authentication
        self.auth_enabled = False

        self.auth_password = "PASS"

        self.auth_users = []


config = Config()


# ============================================================
# AUTHENTICATION
# ============================================================

def authenticate_user(
    update: Update,
    context: CallbackContext
):

    chat_id = update.effective_chat.id

    text = (
        update.effective_message
        .text
        .strip()
    )


    if chat_id not in config.auth_users:

        if text.startswith(
            "/password "
        ):

            provided_password = (
                text.split(
                    " ",
                    1
                )[1]
            )


            if (
                provided_password
                == config.auth_password
            ):

                config.auth_users.append(
                    chat_id
                )

                context.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        "✅ Authentication "
                        "successful! You can now "
                        "use the bot."
                    )
                )

            else:

                context.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        "⚠️ Incorrect password. "
                        "Please try again."
                    )
                )

        else:

            context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "⚠️ You need to authenticate "
                    "first. Use "
                    "/password <your_password>."
                )
            )

        return False


    return True


# ============================================================
# START
# ============================================================

def start(
    update: Update,
    context: CallbackContext
):

    chat_id = update.effective_chat.id

    context.bot.send_message(
        chat_id=chat_id,
        text=(
            "🎵 Welcome to the Song "
            "Downloader Bot! 🎵"
        )
    )


# ============================================================
# DOWNLOAD SONG
# ============================================================

def get_single_song(
    update: Update,
    context: CallbackContext
):

    if not authenticate_user(
        update,
        context
    ):

        return


    chat_id = update.effective_chat.id

    message_id = (
        update.effective_message.message_id
    )

    username = (
        update.effective_chat.username
    )


    logger.info(
        "Starting song download. "
        f"Chat ID: {chat_id}, "
        f"Message ID: {message_id}, "
        f"Username: {username}"
    )


    url = (
        update.effective_message
        .text
        .strip()
    )


    download_dir = (
        f".temp{message_id}{chat_id}"
    )


    os.makedirs(
        download_dir,
        exist_ok=True
    )


    original_dir = os.getcwd()

    os.chdir(
        download_dir
    )


    try:

        context.bot.send_message(
            chat_id=chat_id,
            text="🔍 Downloading"
        )


        if not url.startswith(
            (
                "http://",
                "https://"
            )
        ):

            context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "❌ Invalid URL. "
                    "Please provide a valid "
                    "song URL."
                )
            )

            return


        logger.info(
            f"Downloading: {url}"
        )


        # ====================================================
        # spotDL command
        # ====================================================

        command = [
            sys.executable,
            "-m",
            "spotdl",

            "download",

            url,

            "--no-cache",

            "--client-id",
            "5844159a9506462fa5fd2d190238c37e",

            "--client-secret",
            "7736ac0c637c45f0958cb7cb6976db61",

            "--threads",
            "8",

            "--format",
            "mp3",

            "--bitrate",
            "320k",

            "--yt-dlp-args",
            '--extractor-args "youtube:player_client=web_embedded"'
        ]


        result = subprocess.run(
            command,
            check=False
        )


        logger.info(
            f"spotDL exit code: "
            f"{result.returncode}"
        )


        # ====================================================
        # Find MP3 files
        # ====================================================

        files = [
            file
            for file in os.listdir(".")
            if file.lower().endswith(".mp3")
        ]


        if not files:

            context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "❌ Unable to find "
                    "the requested song."
                )
            )

            logger.warning(
                "No audio file found "
                "after download."
            )

            return


        # ====================================================
        # Send MP3 files
        # ====================================================

        sent = 0


        for file in files:

            try:

                logger.info(
                    f"Sending: {file}"
                )


                with open(
                    file,
                    "rb"
                ) as audio_file:

                    context.bot.send_audio(
                        chat_id=chat_id,
                        audio=audio_file,
                        timeout=18000
                    )


                sent += 1

                time.sleep(
                    0.3
                )


            except Exception as e:

                logger.error(
                    f"Error sending audio: {e}"
                )


        logger.info(
            f"Sent {sent} audio file(s)"
        )


    except Exception as e:

        logger.exception(
            f"Download error: {e}"
        )


        try:

            context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "❌ Download error."
                )
            )

        except Exception:

            pass


    finally:

        os.chdir(
            original_dir
        )


        try:

            subprocess.run(
                [
                    "rm",
                    "-rf",
                    download_dir
                ],
                check=False
            )

        except Exception:

            pass


# ============================================================
# MAIN
# ============================================================

def main():

    logger.info(
        "Starting Telegram bot..."
    )


    updater = Updater(
        token=config.token,
        use_context=True
    )


    dispatcher = (
        updater.dispatcher
    )


    # /start
    dispatcher.add_handler(
        CommandHandler(
            "start",
            start
        )
    )


    # /password
    dispatcher.add_handler(
        MessageHandler(
            Filters.text
            & Filters.regex(
                r"^/password "
            ),
            authenticate_user
        )
    )


    # Song URL
    dispatcher.add_handler(
        MessageHandler(
            Filters.text
            & (~Filters.command),
            get_single_song
        )
    )


    # ========================================================
    # Start polling
    # ========================================================

    updater.start_polling(
        poll_interval=0.3
    )


    logger.info(
        "Bot started successfully."
    )


    # ========================================================
    # IMPORTANT:
    # Do NOT use updater.idle() in Streamlit.
    # Streamlit's execution environment can reject
    # signal handlers.
    # ========================================================

    while True:

        time.sleep(
            3600
        )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()
