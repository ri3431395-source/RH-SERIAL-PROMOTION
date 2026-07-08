import json
import os
import subprocess
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


def probe(path: str) -> ProbeInfo:
    cmd = [
        "ffprobe", "-v", "error", "-show_format", "-show_streams",
        "-of", "json", path,
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(out.stdout)

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
    Returns list of (start, end_or_None) tuples describing how the ORIGINAL
    main video should be cut, based on PROMO_TIME_1 / PROMO_TIME_2, skipping
    marks that fall beyond the video's actual length.
    """
    t1 = config.PROMO_TIME_1
    t2 = config.PROMO_TIME_2
    marks = [m for m in (t1, t2) if m < main_duration]
    bounds = [0] + marks + [main_duration]
    segments = []
    for i in range(len(bounds) - 1):
        segments.append((bounds[i], bounds[i + 1]))
    return segments, len(marks)


def merge_fast_copy(main_path, promo_path, end_path, out_path, segments, promo_count):
    """
    Stream-copy path: no re-encoding. Only usable when main/promo/end all share
    codec+resolution+fps. Uses ffmpeg concat demuxer for max speed.
    """
    work_dir = os.path.dirname(out_path)
    list_file = os.path.join(work_dir, f"concat_{uuid.uuid4().hex}.txt")
    parts = []

    for idx, (start, end) in enumerate(segments):
        part_path = os.path.join(work_dir, f"part_{uuid.uuid4().hex}.mp4")
        cmd = [
            "ffmpeg", "-y", "-ss", str(start), "-to", str(end),
            "-i", main_path, "-c", "copy", "-avoid_negative_ts", "make_zero",
            part_path,
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        parts.append(part_path)
        # insert promo after every segment boundary except the last one
        if idx < len(segments) - 1:
            parts.append(promo_path)

    parts.append(end_path)

    with open(list_file, "w") as f:
        for p in parts:
            f.write(f"file '{os.path.abspath(p)}'\n")

    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", list_file, "-c", "copy", out_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)

    # cleanup temp parts (not promo/end which are shared/reused)
    for p in parts:
        if p not in (promo_path, end_path) and os.path.exists(p):
            os.remove(p)
    if os.path.exists(list_file):
        os.remove(list_file)


def merge_reencode(main_path, promo_path, end_path, out_path, segments):
    """
    Re-encode path: normalizes every clip to the same resolution/fps/codec
    via a single filter_complex pass, so transitions are smooth even when
    inputs differ. Slower than stream-copy but always works.
    """
    w, h, fps = config.TARGET_WIDTH, config.TARGET_HEIGHT, config.TARGET_FPS

    inputs = ["-i", main_path, "-i", promo_path, "-i", end_path]

    filter_parts = []
    concat_labels = []
    label_i = 0

    def vf_label(src_idx, trim=None):
        nonlocal label_i
        label_i += 1
        vlab = f"v{label_i}"
        if trim:
            start, end = trim
            trim_expr = f"trim=start={start}:end={end},setpts=PTS-STARTPTS,"
        else:
            trim_expr = "setpts=PTS-STARTPTS,"
        filter_parts.append(
            f"[{src_idx}:v]{trim_expr}scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}[{vlab}]"
        )
        return vlab

    def af_label(src_idx, trim=None):
        nonlocal label_i
        label_i += 1
        alab = f"a{label_i}"
        if trim:
            start, end = trim
            trim_expr = f"atrim=start={start}:end={end},asetpts=PTS-STARTPTS,"
        else:
            trim_expr = "asetpts=PTS-STARTPTS,"
        filter_parts.append(
            f"[{src_idx}:a]{trim_expr}aformat=sample_rates=44100:channel_layouts=stereo[{alab}]"
        )
        return alab

    for idx, (start, end) in enumerate(segments):
        v = vf_label(0, trim=(start, end))
        a = af_label(0, trim=(start, end))
        concat_labels.append((v, a))
        if idx < len(segments) - 1:
            v = vf_label(1)
            a = af_label(1)
            concat_labels.append((v, a))

    v = vf_label(2)
    a = af_label(2)
    concat_labels.append((v, a))

    concat_inputs = "".join(f"[{v}][{a}]" for v, a in concat_labels)
    filter_parts.append(
        f"{concat_inputs}concat=n={len(concat_labels)}:v=1:a=1[outv][outa]"
    )

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
    subprocess.run(cmd, check=True, capture_output=True)


def merge_video(main_path: str, promo_path: str, end_path: str, out_path: str):
    """
    Main entry point. Decides fast stream-copy vs re-encode automatically,
    and inserts the promo video at every insertion mark that fits the
    main video's real duration, always appending the fixed end video last.
    """
    main_info = probe(main_path)
    promo_info = probe(promo_path)
    end_info = probe(end_path)

    segments, promo_count = build_segments(main_info.duration)

    can_copy = _compatible(main_info, promo_info) and _compatible(main_info, end_info)

    if can_copy:
        merge_fast_copy(main_path, promo_path, end_path, out_path, segments, promo_count)
        mode = "fast_copy"
    else:
        merge_reencode(main_path, promo_path, end_path, out_path, segments)
        mode = "reencode"

    return mode, promo_count
