"""Render video fakta pendek (Daily Fact Bites & Pawsome Facts) dari facts_jobs.json.

Dipanggil otomatis oleh render.py (workflow "Render video (cek tiap jam)").
Alur: ElevenLabs (suara) + gambar bebas lisensi (Openverse CC0/public domain,
cadangan Wikimedia Commons) + ffmpeg -> output/<id>.mp4 (mis. output/fact_21.mp4).
Video yang sudah ada tidak dirender ulang. Hasil dicatat di output/facts_hasil.json.
"""
import json, os, subprocess, textwrap, urllib.error, urllib.parse, urllib.request
from pathlib import Path

try:
    import render_remo  # versi Remotion untuk video produk (aktif lewat config.json "remotion_dari")
except Exception as _e:
    print("render_remo tidak aktif:", _e)

ROOT = Path(__file__).parent
OUT = ROOT / "output"
WORK = ROOT / ".cache" / "facts"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
W, H, FPS = 1080, 1920, 30
UA = {"User-Agent": "facts-render/1.0 (github.com/richbrillian)"}
VOICES = [v for v in [os.getenv("FACTS_VOICE_ID"), "EXAVITQu4vr4xnAyxx5Q", os.getenv("VOICE_ID")] if v]


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(" ".join(cmd[:3]) + ": " + r.stderr[-800:])
    return r.stdout


def get(url, timeout=60):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()


def tts(text, out):
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise RuntimeError("Secret ELEVENLABS_API_KEY kosong")
    last = None
    for v in VOICES:
        body = json.dumps({"text": text, "model_id": "eleven_multilingual_v2"}).encode()
        req = urllib.request.Request(f"https://api.elevenlabs.io/v1/text-to-speech/{v}", data=body,
                                     headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"})
        try:
            out.write_bytes(urllib.request.urlopen(req, timeout=120).read())
            return
        except urllib.error.HTTPError as e:
            last = f"ElevenLabs {e.code}: {e.read()[:300]!r}"
            if e.code in (401, 402, 429):
                break
    raise RuntimeError(last)


def image_urls(keyword, n=4):
    urls = []
    try:
        q = urllib.parse.urlencode({"q": keyword, "license": "cc0,pdm", "page_size": 20, "mature": "false"})
        data = json.loads(get(f"https://api.openverse.org/v1/images/?{q}"))
        for r in data.get("results", []):
            if (r.get("width") or 0) >= 800 and (r.get("filetype") or "jpg").lower() in ("jpg", "jpeg", "png"):
                urls.append(r["url"])
    except Exception as e:
        print("openverse gagal:", e)
    if len(urls) < n:
        try:
            q = urllib.parse.urlencode({"action": "query", "format": "json", "generator": "search",
                                        "gsrsearch": f"{keyword} filetype:bitmap", "gsrnamespace": 6, "gsrlimit": 15,
                                        "prop": "imageinfo", "iiprop": "url|extmetadata", "iiurlwidth": 1280})
            data = json.loads(get(f"https://commons.wikimedia.org/w/api.php?{q}"))
            for p in (data.get("query", {}).get("pages", {}) or {}).values():
                ii = (p.get("imageinfo") or [{}])[0]
                lic = (ii.get("extmetadata", {}).get("LicenseShortName", {}) or {}).get("value", "").lower()
                if ("public domain" in lic or "cc0" in lic or lic == "pd") and ii.get("thumburl"):
                    urls.append(ii["thumburl"])
        except Exception as e:
            print("commons gagal:", e)
    return urls


def fetch_images(keyword, folder, n=4):
    got = []
    for u in image_urls(keyword, n * 2):
        if len(got) >= n:
            break
        p = folder / f"img{len(got)}.jpg"
        try:
            p.write_bytes(get(u, 40))
            run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width", "-of", "csv=p=0", str(p)])
            got.append(p)
        except Exception as e:
            print("lewati gambar:", u, e)
    return got


def duration(p):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)]).strip())


def clip(img, secs, out, i):
    frames = int(secs * FPS) + 2
    zoom = "min(zoom+0.0007,1.15)" if i % 2 == 0 else "if(lte(on,1),1.15,max(zoom-0.0007,1.0))"
    vf = (f"[0:v]split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=25:2,eq=brightness=-0.08[bg];"
          f"[b]scale={W}:{int(H*0.62)}:force_original_aspect_ratio=decrease[fg];"
          f"[bg][fg]overlay=(W-w)/2:(H-h)/2,scale={W*2}:{H*2},"
          f"zoompan=z='{zoom}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},format=yuv420p")
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(img), "-filter_complex", vf,
         "-frames:v", str(frames), "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", str(out)])


def plain_bg(secs, out):
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c=0x1b2a41:s={W}x{H}:d={secs}:r={FPS}",
         "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(out)])


def render(job):
    jid = job["id"]
    final = OUT / f"{jid}.mp4"
    if final.exists():
        return "sudah ada"
    d = WORK / jid
    d.mkdir(parents=True, exist_ok=True)
    voice = d / "voice.mp3"
    if not voice.exists():
        tts(job["narasi"], voice)
    dur = duration(voice) + 0.8
    imgs = fetch_images(job["keyword"], d)
    parts = []
    if imgs:
        seg = dur / len(imgs)
        for i, im in enumerate(imgs):
            c = d / f"c{i}.mp4"
            try:
                clip(im, seg, c, i)
                parts.append(c)
            except Exception as e:
                print("clip gagal:", e)
    if not parts:
        c = d / "bg.mp4"
        plain_bg(dur, c)
        parts = [c]
    lst = d / "list.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in parts))
    (d / "q.txt").write_text("\n".join(textwrap.wrap(job["teks"], 22)))
    (d / "tag.txt").write_text(job["label"])
    draw = (f"drawtext=fontfile={FONT}:textfile={d/'q.txt'}:fontsize=66:fontcolor=white:line_spacing=14:"
            f"box=1:boxcolor=black@0.55:boxborderw=28:x=(w-text_w)/2:y=230,"
            f"drawtext=fontfile={FONT}:textfile={d/'tag.txt'}:fontsize=40:fontcolor=white@0.9:"
            f"box=1:boxcolor=0xF2A900@0.9:boxborderw=16:x=(w-text_w)/2:y=h-260")
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(voice),
         "-vf", draw, "-map", "0:v", "-map", "1:a", "-t", f"{dur:.2f}", "-af", "apad",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(final)])
    return "ok"


def main():
    p = ROOT / "facts_jobs.json"
    if not p.exists():
        return
    OUT.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    jobs = json.loads(p.read_text())
    hasil_p = OUT / "facts_hasil.json"
    hasil = json.loads(hasil_p.read_text()) if hasil_p.exists() else {}
    for job in jobs:
        try:
            st = render(job)
            hasil[job["id"]] = {"status": "ok", "file": f"output/{job['id']}.mp4"}
            print("FAKTA", job["id"], st)
        except Exception as e:
            hasil[job["id"]] = {"status": "gagal", "error": str(e)[:500]}
            print("FAKTA", job["id"], "GAGAL", e)
            if "ElevenLabs 401" in str(e) or "ElevenLabs 402" in str(e):
                break
    hasil_p.write_text(json.dumps(hasil, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
