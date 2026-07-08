"""
Video processing engine for RH-SERIAL-PROMOTION bot.
Handles probing, smart mode selection (fast copy vs smooth re-encode),
and real-time progress reporting straight from ffmpeg's own progress stream.

Credit: RH.RATUL DEPOLOVER
"""

import asyncio
import json
import os
import time
import uuid

import config


class ProbeInfo:
    def __init__(self, duration: float, vcodec: str, acodec: str, width: int, height: int, fps: float):
        self.duration = duration
        self.vcodec = vcodec
        self.acodec = acodec
        self.width = width
        self.height = height
        self.fps = fps


async def _run(cmd):
    """Run a command and wait for completion, raising on failure."""
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed ({proc.returncode}): {stderr.decode(errors='ignore')[-800:]}")
    return stdout, stderr


async def probe(path: str) -> ProbeInfo:
    cmd = [
        "ffprobe", "-v", "error", "-show_format", "-show_streams",
        "-of", "json", path,
    ]
    stdout, _ = await _run(cmd)
    data = json.loads(stdout.decode())

    duration = float(data["format"].get("duration", 0))
    vstream = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    astream = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)

    vcodec = vstream["codec_name"] if vstream else ""
    width = int(vstream["width"]) if vstream else 0
    height = int(vstream["height"]) if vstream else 0
    fps = 0.0
    if vstream and vstream.get("r_frame_rate"):
        num, den = vstream["r_frame_rate"].split("/")
        den = int(den) if int(den) != 0 else 1
        fps = round(int(num) / den, 2)
    acodec = astream["codec_name"] if astream else ""

    return ProbeInfo(duration, vcodec, acodec, width, height, fps)


def _compatible(a: ProbeInfo, b: ProbeInfo) -> bool:
    """Check if two videos can be stream-copy concatenated without re-encoding."""
    return (
        a.vcodec == b.vcodec
        and a.acodec == b.acodec
        and a.width == b.width
        and a.height == b.height
        and abs(a.fps - b.fps) < 0.5
    )


def build_segments(main_duration: float):
    """
    Returns list of (start, end) tuples describing how the ORIGINAL main
    video should be cut, based on PROMO_TIME_1 / PROMO_TIME_2, skipping
    marks that fall beyond the video's actual length.
    """
    t1 = config.PROMO_TIME_1
    t2 = config.PROMO_TIME_2
    marks = [m for m in (t1, t2) if m < main_duration]
    bounds = [0] + marks + [main_duration]
    segments = [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]
    return segments, len(marks)


async def _run_with_progress(cmd, total_duration, on_progress, stage_label):
    """
    Runs an ffmpeg command with `-progress pipe:1` and streams real-time
    percentage / speed / ETA back to on_progress(stage_label, pct, speed, eta_seconds).
    """
    cmd = cmd + ["-progress", "pipe:1", "-nostats"]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )

    start_time = time.time()
    last_report = 0.0
    speed_val = "0x"
    stderr_tail = b""

    async def read_stderr():
        nonlocal stderr_tail
        while True:
            chunk = await proc.stderr.read(4096)
            if not chunk:
                break
            stderr_tail = (stderr_tail + chunk)[-2000:]

    stderr_task = asyncio.create_task(read_stderr())

    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        line = line.decode(errors="ignore").strip()

        if line.startswith("out_time_ms="):
            try:
                current_us = int(line.split("=")[1])
                current_sec = current_us / 1_000_000
            except (ValueError, IndexError):
                continue

            now = time.time()
            if now - last_report < 2 and current_sec < total_duration:
                continue
            last_report = now

            pct = min(current_sec / total_duration * 100, 100) if total_duration else 0
            elapsed = now - start_time
            eta = (elapsed / current_sec * (total_duration - current_sec)) if current_sec > 0 else 0

            if on_progress:
                await on_progress(stage_label, pct, speed_val, eta)

        elif line.startswith("speed="):
            speed_val = line.split("=")[1].strip() or "0x"

        elif line == "progress=end":
            break

    await stderr_task
    await proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed ({proc.returncode}): {stderr_tail.decode(errors='ignore')[-800:]}")


async def merge_fast_copy(main_path, promo_path, end_path, out_path, segments, on_progress=None):
    """
    Stream-copy path: no re-encoding. Only usable when main/promo/end all
    share codec+resolution+fps. Very fast since ffmpeg just remuxes.
    """
    work_dir = os.path.dirname(out_path)
    list_file = os.path.join(work_dir, f"concat_{uuid.uuid4().hex}.txt")
    parts = []
    total_steps = len(segments)

    for idx, (start, end) in enumerate(segments):
        if on_progress:
            pct = (idx / total_steps) * 100
            await on_progress(f"✂️ Segment {idx + 1}/{total_steps} কাটা হচ্ছে", pct, "copy", 0)

        part_path = os.path.join(work_dir, f"part_{uuid.uuid4().hex}.mp4")
        cmd = [
            "ffmpeg", "-y", "-ss", str(start), "-to", str(end),
            "-i", main_path, "-c", "copy", "-avoid_negative_ts", "make_zero",
            part_path,
        ]
        await _run(cmd)
        parts.append(part_path)
        if idx < len(segments) - 1:
            parts.append(promo_path)

    parts.append(end_path)

    with open(list_file, "w") as f:
        for p in parts:
            f.write(f"file '{os.path.abspath(p)}'\n")

    if on_progress:
        await on_progress("🔗 সব অংশ জোড়া লাগানো হচ্ছে", 95, "copy", 0)

    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", list_file, "-c", "copy", out_path,
    ]
    await _run(cmd)

    for p in parts:
        if p not in (promo_path, end_path) and os.path.exists(p):
            os.remove(p)
    if os.path.exists(list_file):
        os.remove(list_file)


async def merge_reencode(main_path, promo_path, end_path, out_path, segments, promo_duration,
                          end_duration, main_duration, on_progress=None):
    """
    Re-encode path: normalizes every clip to the same resolution/fps/codec
    via a single filter_complex pass, so transitions stay smooth even when
    inputs differ. Reports true real-time % / speed / ETA from ffmpeg itself.
    """
    w, h, fps = config.TARGET_WIDTH, config.TARGET_HEIGHT, config.TARGET_FPS
    promo_inserts = max(len(segments) - 1, 0)
    total_duration = main_duration + (promo_duration * promo_inserts) + end_duration

    inputs = ["-i", main_path, "-i", promo_path, "-i", end_path]

    filter_parts = []
    concat_labels = []
    label_i = 0

    def vf_label(src_idx, trim=None):
        nonlocal label_i
        label_i += 1
        vlab = f"v{label_i}"
        trim_expr = f"trim=start={trim[0]}:end={trim[1]},setpts=PTS-STARTPTS," if trim else "setpts=PTS-STARTPTS,"
        filter_parts.append(
            f"[{src_idx}:v]{trim_expr}scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}[{vlab}]"
        )
        return vlab

    def af_label(src_idx, trim=None):
        nonlocal label_i
        label_i += 1
        alab = f"a{label_i}"
        trim_expr = f"atrim=start={trim[0]}:end={trim[1]},asetpts=PTS-STARTPTS," if trim else "asetpts=PTS-STARTPTS,"
        filter_parts.append(
            f"[{src_idx}:a]{trim_expr}aformat=sample_rates=44100:channel_layouts=stereo[{alab}]"
        )
        return alab

    for idx, (start, end) in enumerate(segments):
        concat_labels.append((vf_label(0, trim=(start, end)), af_label(0, trim=(start, end))))
        if idx < len(segments) - 1:
            concat_labels.append((vf_label(1), af_label(1)))

    concat_labels.append((vf_label(2), af_label(2)))

    concat_inputs = "".join(f"[{v}][{a}]" for v, a in concat_labels)
    filter_parts.append(f"{concat_inputs}concat=n={len(concat_labels)}:v=1:a=1[outv][outa]")
    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", config.X264_PRESET, "-crf", config.X264_CRF,
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        out_path,
    ]

    await _run_with_progress(cmd, total_duration, on_progress, "🎬 Episode তৈরি হচ্ছে (Smooth mode)")


async def merge_video(main_path: str, promo_path: str, end_path: str, out_path: str, on_progress=None):
    """
    Main entry point. Decides fast stream-copy vs re-encode automatically,
    inserts the promo video at every insertion mark that fits the main
    video's real duration, and always appends the fixed end video last.
    Reports real-time progress via on_progress(stage_label, pct, speed, eta_sec).
    """
    if on_progress:
        await on_progress("🔍 Video গুলো বিশ্লেষণ করা হচ্ছে", 0, "-", 0)

    main_info = await probe(main_path)
    promo_info = await probe(promo_path)
    end_info = await probe(end_path)

    segments, promo_count = build_segments(main_info.duration)
    can_copy = _compatible(main_info, promo_info) and _compatible(main_info, end_info)

    if can_copy:
        await merge_fast_copy(main_path, promo_path, end_path, out_path, segments, on_progress)
        mode = "fast_copy"
    else:
        await merge_reencode(
            main_path, promo_path, end_path, out_path, segments,
            promo_info.duration, end_info.duration, main_info.duration, on_progress,
        )
        mode = "reencode"

    if on_progress:
        await on_progress("✅ Merge সম্পন্ন", 100, "-", 0)

    return mode, promo_count
