import os
import subprocess
import logging
from pathlib import Path
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# === LOGGING ===
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# === TOKEN ===
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# === PAPKALAR ===
TEMP_DIR = Path("/tmp/mp3bot")
TEMP_DIR.mkdir(parents=True, exist_ok=True)


def sanitize_filename(name: str) -> str:
    """Bo'sh joylarni '_' bilan almashtiradi."""
    return name.replace(" ", "_")


def convert_mp3(input_path: Path, output_path: Path) -> bool:
    """
    MP3 faylni konvertatsiya qiladi:
    - Rasm va metadatani olib tashlaydi
    - Mono, 44.1kHz, ~128kbps VBR (LAME)
    """
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(input_path),
        "-vn",                    # rasmni olib tashlash
        "-map_metadata", "-1",   # metadatani tozalash
        "-ar", "44100",          # sampling rate
        "-ac", "1",              # mono
        "-codec:a", "libmp3lame",
        "-q:a", "2",             # VBR ~128kbps
        str(output_path),
    ]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
        )
        return result.returncode == 0
    except Exception as e:
        logger.error(f"ffmpeg xatoligi: {e}")
        return False


# === HANDLERS ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Salom! Men MP3 Converter botman.\n\n"
        "🎵 Menga istalgan MP3 fayl yuboring — men uni:\n"
        "  ✅ Tozalayman (rasm va metadatani o'chiraman)\n"
        "  ✅ Mono, 44.1kHz, 128kbps formatiga o'giraman\n"
        "  ✅ Fayl nomidagi bo'shliqlarni '_' ga aylantiraman\n\n"
        "Boshlash uchun MP3 faylingizni yuboring! 🚀"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 Yordam:\n\n"
        "1. MP3 faylingizni menga yuboring\n"
        "2. Men uni qayta ishlayman\n"
        "3. Tayyor faylni sizga qaytaraman\n\n"
        "⚠️ Faqat MP3 formatidagi fayllar qabul qilinadi.\n"
        "📦 Maksimal fayl hajmi: 50 MB (Telegram cheklovi)"
    )


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message

    # Audio yoki document sifatida kelishi mumkin
    audio = message.audio or message.document

    if not audio:
        await message.reply_text("❌ Fayl topilmadi. Iltimos, MP3 fayl yuboring.")
        return

    # Fayl nomini aniqlash
    file_name = getattr(audio, "file_name", None) or "audio.mp3"

    # MP3 ekanligini tekshirish
    if not file_name.lower().endswith(".mp3"):
        await message.reply_text(
            "⚠️ Faqat MP3 formatidagi fayllar qabul qilinadi.\n"
            "Iltimos, .mp3 fayl yuboring."
        )
        return

    # Fayl hajmini tekshirish (50 MB)
    file_size = getattr(audio, "file_size", 0)
    if file_size and file_size > 50 * 1024 * 1024:
        await message.reply_text("❌ Fayl juda katta! Maksimal hajm: 50 MB.")
        return

    processing_msg = await message.reply_text("⏳ Fayl qabul qilindi, konvertatsiya boshlanmoqda...")

    try:
        # Faylni yuklab olish
        tg_file = await context.bot.get_file(audio.file_id)

        clean_name = sanitize_filename(Path(file_name).stem)
        input_path = TEMP_DIR / f"input_{message.message_id}.mp3"
        output_path = TEMP_DIR / f"{clean_name}.mp3"

        await tg_file.download_to_drive(str(input_path))

        await processing_msg.edit_text("🔄 Konvertatsiya qilinmoqda...")

        # Konvertatsiya
        success = convert_mp3(input_path, output_path)

        if not success:
            await processing_msg.edit_text(
                "❌ Konvertatsiya muvaffaqiyatsiz tugadi.\n"
                "Fayl buzilgan bo'lishi mumkin. Boshqa fayl sinab ko'ring."
            )
            return

        await processing_msg.edit_text("📤 Fayl yuborilmoqda...")

        # Tayyor faylni yuborish
        with open(output_path, "rb") as f:
            await message.reply_audio(
                audio=f,
                filename=f"{clean_name}.mp3",
                caption=(
                    f"✅ Tayyor!\n"
                    f"📁 Fayl: `{clean_name}.mp3`\n"
                    f"🎵 Format: Mono | 44.1kHz | 128kbps VBR\n"
                    f"🧹 Rasm va metadata tozalandi"
                ),
                parse_mode="Markdown",
            )

        await processing_msg.delete()

    except Exception as e:
        logger.error(f"Xatolik: {e}")
        await processing_msg.edit_text(
            "❌ Kutilmagan xatolik yuz berdi. Iltimos, qayta urinib ko'ring."
        )

    finally:
        # Vaqtinchalik fayllarni o'chirish
        for path in [input_path, output_path]:
            try:
                if path.exists():
                    path.unlink()
            except Exception:
                pass


async def handle_other(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 Iltimos, faqat MP3 fayl yuboring.\n"
        "Yordam uchun /help ni bosing."
    )


# === MAIN ===

def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN muhit o'zgaruvchisi o'rnatilmagan!")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))

    # Audio va document (fayl sifatida yuborilgan MP3) larni ushlash
    app.add_handler(MessageHandler(filters.AUDIO, handle_audio))
    app.add_handler(MessageHandler(filters.Document.MimeType("audio/mpeg"), handle_audio))
    app.add_handler(MessageHandler(filters.Document.Extension("mp3"), handle_audio))

    # Boshqa xabarlar
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_other))

    logger.info("Bot ishga tushdi...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
