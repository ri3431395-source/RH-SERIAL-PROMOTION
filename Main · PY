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


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


def human(n: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


async def progress(current, total, message: Message, label: str, start_time):
    now = time.time()
    # throttle edits to ~ every 4 seconds to avoid flood limits
    if not hasattr(progress, "_last"):
        progress._last = {}
    key = message.id
    last = progress._last.get(key, 0)
    if now - last < 4 and current != total:
        return
    progress._last[key] = now
    pct = current * 100 / total if total else 0
    elapsed = max(now - start_time, 0.01)
    speed = current / elapsed
    try:
        await message.edit_text(
            f"{label}\n{pct:.1f}% ({human(current)}/{human(total)})\nSpeed: {human(speed)}/s"
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Basic commands
# ---------------------------------------------------------------------------

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client: Client, message: Message):
    text = (
        "স্বাগতম! 👋\n\n"
        "এই বট আপনার video তে promotion video যোগ করে episode তৈরি করে দেয়।\n\n"
        "**আপনার করণীয়:**\n"
        "1️⃣ প্রথমে `/setpromo` কমান্ড দিয়ে (একটি video তে reply করে) আপনার promo video সেট করুন — এটা একবার সেট করলেই থাকবে।\n"
        "2️⃣ এরপর আপনার main video টি এই বটে ফরওয়ার্ড বা সেন্ড করুন।\n"
        "3️⃣ বট automatic ভাবে promo video বসিয়ে ও শেষে fixed video যোগ করে আপনাকে সম্পূর্ণ episode ফেরত দেবে।\n\n"
        "`/mypromo` — আপনার বর্তমান promo video চেক করতে।"
    )
    await message.reply_text(text)


@app.on_message(filters.command("setpromo") & filters.private)
async def set_promo_cmd(client: Client, message: Message):
    if not message.reply_to_message or not (
        message.reply_to_message.video or message.reply_to_message.document
    ):
        await message.reply_text(
            "একটি video তে reply করে `/setpromo` লিখুন। যেমন: video পাঠান, তারপর সেই video তে reply করে `/setpromo` টাইপ করুন।"
        )
        return

    video = message.reply_to_message.video or message.reply_to_message.document
    db.set_user_promo(message.from_user.id, video.file_id, getattr(video, "file_unique_id", ""))
    await message.reply_text("✅ আপনার promo video সেট/আপডেট হয়ে গেছে। এখন থেকে সব episode এ এটাই ব্যবহার হবে।")


@app.on_message(filters.command("mypromo") & filters.private)
async def my_promo_cmd(client: Client, message: Message):
    promo = db.get_user_promo(message.from_user.id)
    if promo:
        await message.reply_text("✅ আপনার একটি promo video সেট করা আছে। পরিবর্তন করতে `/setpromo` ব্যবহার করুন।")
    else:
        default = db.get_default_promo()
        if default:
            await message.reply_text(
                "আপনার নিজস্ব কোনো promo video সেট করা নেই — ডিফল্ট promo video ব্যবহার হবে। "
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
    await message.reply_text("✅ Fixed end video সেট হয়ে গেছে। এটা সব সময় প্রতিটি episode এর একদম শেষে যোগ হবে এবং user রা এটা পরিবর্তন করতে পারবে না।")


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
    (filters.video | (filters.document & filters.private)) & filters.private & ~filters.command(["setpromo", "setendvideo", "setdefaultpromo"])
)
async def handle_main_video(client: Client, message: Message):
    # ignore if this message is itself being used as a reply-target-setup (handled by command handlers above)
    user_id = message.from_user.id

    end_video_id = db.get_admin_end_video()
    if not end_video_id:
        await message.reply_text("⚠️ Admin এখনো fixed end video সেট করেননি। কিছুক্ষণ পর আবার চেষ্টা করুন।")
        return

    promo_id = db.get_user_promo(user_id) or db.get_default_promo()
    if not promo_id:
        await message.reply_text(
            "⚠️ আপনার কোনো promo video সেট নেই। প্রথমে একটি video তে reply করে `/setpromo` লিখে সেট করুন, তারপর main video পাঠান।"
        )
        return

    video = message.video or message.document
    if video.file_size and video.file_size > config.MAX_FILE_SIZE:
        await message.reply_text(f"⚠️ ফাইল সাইজ অনেক বড় (সর্বোচ্চ {human(config.MAX_FILE_SIZE)})।")
        return

    job_id = uuid.uuid4().hex[:10]
    job_dir = os.path.join(config.WORK_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    status = await message.reply_text("⏳ প্রসেসিং শুরু হচ্ছে...")

    try:
        main_path = os.path.join(job_dir, "main.mp4")
        promo_path = os.path.join(job_dir, "promo.mp4")
        end_path = os.path.join(job_dir, "end.mp4")
        out_path = os.path.join(job_dir, "episode.mp4")

        start_time = time.time()
        await status.edit_text("⬇️ Main video ডাউনলোড হচ্ছে...")
        await client.download_media(
            message, file_name=main_path,
            progress=progress, progress_args=(status, "⬇️ Main video ডাউনলোড হচ্ছে...", start_time),
        )

        await status.edit_text("⬇️ Promo video প্রস্তুত হচ্ছে...")
        await client.download_media(promo_id, file_name=promo_path)

        await status.edit_text("⬇️ End video প্রস্তুত হচ্ছে...")
        await client.download_media(end_video_id, file_name=end_path)

        await status.edit_text("🎬 Video merge করা হচ্ছে... (এতে কিছুটা সময় লাগতে পারে)")
        mode, promo_count = vp.merge_video(main_path, promo_path, end_path, out_path)

        speed_note = "⚡ দ্রুত মোড (re-encode ছাড়াই)" if mode == "fast_copy" else "🎞️ Smooth মোড (re-encoded)"
        await status.edit_text(f"⬆️ Episode আপলোড হচ্ছে...\n{speed_note}")

        upload_start = time.time()
        await client.send_video(
            chat_id=message.chat.id,
            video=out_path,
            caption=f"✅ আপনার episode প্রস্তুত!\n{speed_note}\nPromo inserted: {promo_count}x + fixed end video",
            progress=progress,
            progress_args=(status, "⬆️ Episode আপলোড হচ্ছে...", upload_start),
        )
        await status.delete()

    except Exception as e:
        log.exception("processing failed")
        await status.edit_text(f"❌ প্রসেসিং এ সমস্যা হয়েছে:\n`{e}`")

    finally:
        # cleanup temp job files regardless of outcome
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


if __name__ == "__main__":
    log.info("Starting promo bot...")
    app.run()
