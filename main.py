"""
RH-SERIAL-PROMOTION Telegram Bot
Automatically inserts a user's promo video into their main video at fixed
timestamps, and always appends an admin-fixed closing video — with
real-time, professional-style progress reporting at every stage.

Credit: RH.RATUL DEPOLOVER
"""

import logging
import os
import time
import uuid

from pyrogram import Client, filters
from pyrogram.types import Message

import config
import database as db
import video_processor as vp

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("promo-bot")

db.init_db()

app = Client(
    "promo_bot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN,
)

BOT_CREDIT = "🛠 Powered by RH.RATUL DEPOLOVER"


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


def human(n: float) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def human_time(seconds: float) -> str:
    seconds = max(int(seconds), 0)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def bar(pct: float, width: int = 14) -> str:
    pct = max(0, min(pct, 100))
    filled = int(width * pct / 100)
    return "▰" * filled + "▱" * (width - filled)


_last_edit = {}


async def _safe_edit(message: Message, text: str, min_interval: float = 2.5):
    """Edits a status message but throttles to avoid Telegram flood limits."""
    key = message.id
    now = time.time()
    if now - _last_edit.get(key, 0) < min_interval:
        return
    _last_edit[key] = now
    try:
        await message.edit_text(text)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Download / Upload progress (Pyrogram native — real byte-level speed)
# ---------------------------------------------------------------------------

async def transfer_progress(current, total, message: Message, label: str, start_time):
    now = time.time()
    elapsed = max(now - start_time, 0.01)
    speed = current / elapsed
    pct = current * 100 / total if total else 0
    eta = (total - current) / speed if speed > 0 else 0

    text = (
        f"{label}\n\n"
        f"{bar(pct)}  {pct:.1f}%\n"
        f"📦 {human(current)} / {human(total)}\n"
        f"⚡ Speed: {human(speed)}/s\n"
        f"⏳ ETA: {human_time(eta)}\n\n"
        f"{BOT_CREDIT}"
    )
    await _safe_edit(message, text)


# ---------------------------------------------------------------------------
# ffmpeg merge progress (real-time, direct from ffmpeg's own progress stream)
# ---------------------------------------------------------------------------

def make_merge_progress_handler(message: Message):
    async def handler(stage_label: str, pct: float, speed: str, eta_sec: float):
        text = (
            f"{stage_label}\n\n"
            f"{bar(pct)}  {pct:.1f}%\n"
            f"⚡ Encode speed: {speed}\n"
            f"⏳ ETA: {human_time(eta_sec)}\n\n"
            f"{BOT_CREDIT}"
        )
        await _safe_edit(message, text, min_interval=2.0)
    return handler


# ---------------------------------------------------------------------------
# Basic commands
# ---------------------------------------------------------------------------

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client: Client, message: Message):
    text = (
        "✨ **স্বাগতম RH-SERIAL-PROMOTION বটে!** ✨\n\n"
        "এই বট আপনার video তে automatically promotion video বসিয়ে সম্পূর্ণ **episode** তৈরি করে দেয় — "
        "real-time processing status সহ, professional গতিতে।\n\n"
        "**📌 কীভাবে ব্যবহার করবেন:**\n"
        "1️⃣ একটি promo video পাঠিয়ে সেটাতে reply করে `/setpromo` লিখুন — এটা একবার সেট করলেই সবসময় থাকবে।\n"
        "2️⃣ এরপর আপনার main video টি এখানে সেন্ড বা ফরওয়ার্ড করুন।\n"
        "3️⃣ বট automatic ভাবে promo বসিয়ে ও fixed closing video যোগ করে সম্পূর্ণ episode আপনাকে ফেরত দেবে — "
        "সাথে live progress (%, speed, ETA) দেখতে পাবেন।\n\n"
        "**🔧 কমান্ড সমূহ:**\n"
        "`/setpromo` — video তে reply করে নিজের promo video সেট/পরিবর্তন করুন\n"
        "`/mypromo` — বর্তমান promo video স্ট্যাটাস দেখুন\n\n"
        f"{BOT_CREDIT}"
    )
    await message.reply_text(text)


@app.on_message(filters.command("setpromo") & filters.private)
async def set_promo_cmd(client: Client, message: Message):
    if not message.reply_to_message or not (
        message.reply_to_message.video or message.reply_to_message.document
    ):
        await message.reply_text(
            "⚠️ একটি video তে reply করে `/setpromo` লিখুন।\n"
            "যেমন: promo video পাঠান → সেই video তে reply করে `/setpromo` টাইপ করুন।"
        )
        return

    video = message.reply_to_message.video or message.reply_to_message.document
    db.set_user_promo(message.from_user.id, video.file_id, getattr(video, "file_unique_id", ""))
    await message.reply_text(
        "✅ **আপনার promo video সেট/আপডেট হয়ে গেছে!**\n"
        "এখন থেকে আপনার প্রতিটি episode এ automatic এটাই ব্যবহার হবে — বারবার পাঠানোর দরকার নেই।\n\n"
        f"{BOT_CREDIT}"
    )


@app.on_message(filters.command("mypromo") & filters.private)
async def my_promo_cmd(client: Client, message: Message):
    promo = db.get_user_promo(message.from_user.id)
    if promo:
        await message.reply_text("✅ আপনার নিজস্ব promo video সেট করা আছে। পরিবর্তন করতে `/setpromo` ব্যবহার করুন।")
    else:
        default = db.get_default_promo()
        if default:
            await message.reply_text(
                "ℹ️ আপনার নিজস্ব promo video সেট নেই — ডিফল্ট promo video ব্যবহার হবে।\n"
                "নিজের promo সেট করতে video তে reply করে `/setpromo` লিখুন।"
            )
        else:
            await message.reply_text("❌ কোনো promo video সেট নেই। video তে reply করে `/setpromo` লিখুন।")


# ---------------------------------------------------------------------------
# Admin-only commands
# ---------------------------------------------------------------------------

@app.on_message(filters.command("setendvideo") & filters.private)
async def set_end_video_cmd(client: Client, message: Message):
    if not is_admin(message.from_user.id):
        await message.reply_text("❌ এই কমান্ড শুধু admin এর জন্য।")
        return
    if not message.reply_to_message or not (
        message.reply_to_message.video or message.reply_to_message.document
    ):
        await message.reply_text("একটি video তে reply করে `/setendvideo` লিখুন।")
        return

    video = message.reply_to_message.video or message.reply_to_message.document
    db.set_admin_end_video(video.file_id)
    await message.reply_text(
        "✅ **Fixed closing video সেট হয়ে গেছে।**\n"
        "এটা সব সময় প্রতিটি episode এর একদম শেষে যোগ হবে — user রা এটা পরিবর্তন করতে পারবে না।"
    )


@app.on_message(filters.command("setdefaultpromo") & filters.private)
async def set_default_promo_cmd(client: Client, message: Message):
    if not is_admin(message.from_user.id):
        await message.reply_text("❌ এই কমান্ড শুধু admin এর জন্য।")
        return
    if not message.reply_to_message or not (
        message.reply_to_message.video or message.reply_to_message.document
    ):
        await message.reply_text("একটি video তে reply করে `/setdefaultpromo` লিখুন।")
        return

    video = message.reply_to_message.video or message.reply_to_message.document
    db.set_default_promo(video.file_id)
    await message.reply_text("✅ Default promo video সেট হয়ে গেছে (যেসব user নিজের promo সেট করেনি তাদের জন্য)।")


# ---------------------------------------------------------------------------
# Main video processing
# ---------------------------------------------------------------------------

@app.on_message(
    (filters.video | (filters.document & filters.private)) & filters.private
    & ~filters.command(["setpromo", "setendvideo", "setdefaultpromo"])
)
async def handle_main_video(client: Client, message: Message):
    user_id = message.from_user.id

    end_video_id = db.get_admin_end_video()
    if not end_video_id:
        await message.reply_text("⚠️ Admin এখনো fixed closing video সেট করেননি। কিছুক্ষণ পর আবার চেষ্টা করুন।")
        return

    promo_id = db.get_user_promo(user_id) or db.get_default_promo()
    if not promo_id:
        await message.reply_text(
            "⚠️ আপনার কোনো promo video সেট নেই।\n"
            "প্রথমে একটি video তে reply করে `/setpromo` লিখে সেট করুন, তারপর main video পাঠান।"
        )
        return

    video = message.video or message.document
    if video.file_size and video.file_size > config.MAX_FILE_SIZE:
        await message.reply_text(f"⚠️ ফাইল সাইজ অনেক বড় (সর্বোচ্চ {human(config.MAX_FILE_SIZE)})।")
        return

    job_id = uuid.uuid4().hex[:10]
    job_dir = os.path.join(config.WORK_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    status = await message.reply_text(f"⏳ **প্রসেসিং শুরু হচ্ছে...**\n\n{BOT_CREDIT}")

    main_path = os.path.join(job_dir, "main.mp4")
    promo_path = os.path.join(job_dir, "promo.mp4")
    end_path = os.path.join(job_dir, "end.mp4")
    out_path = os.path.join(job_dir, "episode.mp4")

    try:
        t0 = time.time()
        await client.download_media(
            message, file_name=main_path,
            progress=transfer_progress,
            progress_args=(status, "⬇️ **Main video ডাউনলোড হচ্ছে**", t0),
        )

        await _safe_edit(status, f"⬇️ Promo video প্রস্তুত হচ্ছে...\n\n{BOT_CREDIT}", min_interval=0)
        await client.download_media(promo_id, file_name=promo_path)

        await _safe_edit(status, f"⬇️ Closing video প্রস্তুত হচ্ছে...\n\n{BOT_CREDIT}", min_interval=0)
        await client.download_media(end_video_id, file_name=end_path)

        merge_progress = make_merge_progress_handler(status)
        mode, promo_count = await vp.merge_video(main_path, promo_path, end_path, out_path, merge_progress)

        mode_note = "⚡ Fast mode (re-encode ছাড়া)" if mode == "fast_copy" else "🎞️ Smooth mode (re-encoded)"

        t1 = time.time()
        await client.send_video(
            chat_id=message.chat.id,
            video=out_path,
            caption=(
                f"✅ **আপনার episode প্রস্তুত!**\n"
                f"{mode_note}\n"
                f"🎯 Promo inserted: {promo_count}x + fixed closing video\n\n"
                f"{BOT_CREDIT}"
            ),
            progress=transfer_progress,
            progress_args=(status, "⬆️ **Episode আপলোড হচ্ছে**", t1),
        )
        await status.delete()

    except Exception as e:
        log.exception("processing failed")
        await status.edit_text(f"❌ প্রসেসিং এ সমস্যা হয়েছে:\n`{e}`\n\n{BOT_CREDIT}")

    finally:
        for f in (main_path, promo_path, end_path, out_path):
            try:
                if os.path.exists(f):
                    os.remove(f)
            except Exception:
                pass
        try:
            os.rmdir(job_dir)
        except Exception:
            pass
        _last_edit.pop(status.id, None)


if __name__ == "__main__":
    log.info("Starting RH-SERIAL-PROMOTION bot... | Credit: RH.RATUL DEPOLOVER")
    app.run()
