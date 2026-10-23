"""Render video affiliate 9:16 dari Google Sheet (tab Affiliate).

Hemat kredit: semua kerja berat (unduh gambar, suara ElevenLabs, ffmpeg)
jalan di GitHub Actions, bukan di Claude. Suara di-cache, jadi tidak
pernah dibuat dua kali untuk naskah yang sama.

Kolom sheet yang dipakai (judul baris 1 harus sama persis):
  No | Nama produk | Harga (Rp) | Naskah suara (ElevenLabs, ±15 dtk)
  Link gambar AI (Drive publik) | Link video 5 dtk (Drive publik)
  Link audio (Drive publik) | URL foto produk | Status
Baris yang dirender: Status == "Siap render".
"""
import csv, hashlib, io, json, os, re, subprocess, sys, urllib.request
from pathlib import Path

W, H, FPS = 1080, 1920, 30
ROOT = Path(__file__).parent
OUT = ROOT / "output"; CACHE = ROOT / ".cache"
OUT.mkdir(exist_ok=True); CACHE.mkdir(exist_ok=True)
FONT = os.getenv("FONT", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
VOICE_ID = os.getenv("VOICE_ID") or "W98P5TTtcHAH6zHkf7ul"  # Raya Fie (ID)
COL = {
    "no": "No", "nama": "Nama produk", "harga": "Harga (Rp)",
    "naskah": "Naskah suara (ElevenLabs, ±15 dtk)",
    "img_ai": "Link gambar AI (Drive publik)",
    "vid_ai": "Link video 5 dtk (Drive publik)",
    "audio": "Link audio (Drive publik)",
    "img_produk": "URL foto produk", "status": "Status",
}

def run(cmd):
    r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-600:])

def drive_direct(url):
    m = re.search(r"/d/([\w-]+)|id=([\w-]+)", url or "")
    if "drive.google.com" in (url or "") and m:
        return f"https://drive.google.com/uc?export=download&id={m.group(1) or m.group(2)}"
    return url

def fetch(url, ext):
    """Unduh sekali, simpan di cache (hemat kuota & waktu). Path lokal juga boleh."""
    if not url: return None
    if os.path.exists(url): return Path(url)
    p = CACHE / (hashlib.md5(url.encode()).hexdigest() + ext)
    if not p.exists():
        req = urllib.request.Request(drive_direct(url), headers={"User-Agent": "Mozilla/5.0"})
        p.write_bytes(urllib.request.urlopen(req, timeout=60).read())
    return p

def tts(text):
    """ElevenLabs TTS, di-cache per naskah -> kredit tidak terbuang."""
    p = CACHE / ("tts-" + hashlib.md5((VOICE_ID + text).encode()).hexdigest() + ".mp3")
    if p.exists(): return p
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key: raise RuntimeError("Secret ELEVENLABS_API_KEY belum diisi dan kolom audio kosong.")
    body = json.dumps({"text": text, "model_id": os.getenv("TTS_MODEL") or "eleven_multilingual_v2"}).encode()
    req = urllib.request.Request(f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}",
        data=body, headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"})
    p.write_bytes(urllib.request.urlopen(req, timeout=120).read())
    return p

def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout
    return float(out.strip() or 0)

def clip_from_image(img, secs, out, zoom_in=True):
    """Gambar diam -> klip bergerak (zoom pelan). Pengganti video AI berbayar."""
    frames = int(secs * FPS)
    z = "min(zoom+0.0009,1.15)" if zoom_in else "if(eq(on,0),1.15,max(zoom-0.0009,1))"
    vf = (f"scale={W*2}:{H*2}:force_original_aspect_ratio=increase,crop={W*2}:{H*2},"
          f"zoompan=z='{z}':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},setsar=1")
    run(["ffmpeg", "-y", "-loop", "1", "-i", str(img), "-vf", vf, "-t", str(secs),
         "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "veryfast", str(out)])

def clip_from_video(vid, secs, out):
    vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1"
    run(["ffmpeg", "-y", "-i", str(vid), "-t", str(secs), "-vf", vf, "-an",
         "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "veryfast", str(out)])

def esc(t):
    return t.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’").replace("%", "\\%")

def render(row):
    no = row[COL["no"]].strip()
    nama = row[COL["nama"]].strip()
    harga = re.sub(r"\D", "", row.get(COL["harga"], "")) or ""
    work = CACHE / f"row{no}"; work.mkdir(exist_ok=True)

    audio = fetch(row.get(COL["audio"], "").strip(), ".mp3") or tts(row[COL["naskah"]].strip())
    total = max(duration(audio) + 0.6, 6)

    # 1) Pembuka 5 detik: video AI kalau ada, kalau tidak gambar AI yang di-zoom.
    clips = []
    vid_ai = fetch(row.get(COL["vid_ai"], "").strip(), ".mp4")
    img_ai = fetch(row.get(COL["img_ai"], "").strip(), ".jpg")
    img_p = fetch(row.get(COL["img_produk"], "").strip(), ".jpg")
    first = work / "c0.mp4"
    if vid_ai: clip_from_video(vid_ai, 5, first)
    else: clip_from_image(img_ai or img_p, 5, first)
    clips.append(first)
    # 2) Sisa durasi: gantian foto produk asli & gambar AI.
    others = [i for i in (img_p, img_ai) if i] or [img_ai or img_p]
    left, k = total - 5, 0
    while left > 0.3:
        secs = min(4, left); c = work / f"c{k+1}.mp4"
        clip_from_image(others[k % len(others)], secs, c, zoom_in=(k % 2 == 1))
        clips.append(c); left -= secs; k += 1

    lst = work / "list.txt"
    lst.write_text("".join(f"file '{c.resolve()}'\n" for c in clips))
    joined = work / "joined.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)])

    judul = esc(nama[:30] + ("…" if len(nama) > 30 else ""))
    hrg = esc(f"Cuma Rp{int(harga):,}".replace(",", ".")) if harga else ""
    box = "box=1:boxcolor=black@0.55:boxborderw=24"
    vf = (f"drawtext=fontfile={FONT}:text='{judul}':fontsize=46:fontcolor=white:{box}:x=(w-tw)/2:y=170,"
          + (f"drawtext=fontfile={FONT}:text='{hrg}':fontsize=72:fontcolor=yellow:{box}:x=(w-tw)/2:y=290," if hrg else "")
          + f"drawtext=fontfile={FONT}:text='Cek link di bio / komentar':fontsize=56:fontcolor=white:"
            f"box=1:boxcolor=0xEE4D2D@0.95:boxborderw=26:x=(w-tw)/2:y=h-330")
    slug = re.sub(r"[^a-z0-9]+", "-", nama.lower())[:40].strip("-")
    out = OUT / f"{no}-{slug}.mp4"
    run(["ffmpeg", "-y", "-i", str(joined), "-i", str(audio), "-vf", vf, "-map", "0:v", "-map", "1:a",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac", "-b:a", "128k",
         "-t", f"{total:.2f}", "-movflags", "+faststart", str(out)])
    return out

def main():
    src = os.getenv("SHEET_CSV_URL") or (sys.argv[1] if len(sys.argv) > 1 else "")
    if not src: sys.exit("Isi secret SHEET_CSV_URL (link CSV tab Affiliate) atau beri path CSV.")
    data = Path(src).read_text() if os.path.exists(src) else urllib.request.urlopen(src, timeout=60).read().decode()
    rows = [r for r in csv.DictReader(io.StringIO(data)) if r.get(COL["status"], "").strip() == "Siap render"]
    if not rows: print("Tidak ada baris berstatus 'Siap render'."); return
    gagal = 0
    for r in rows:
        try: print("OK  ", render(r))
        except Exception as e: gagal += 1; print("GAGAL baris", r.get(COL["no"]), "-", e)
    if gagal: sys.exit(f"{gagal} baris gagal dirender.")

if __name__ == "__main__":
    main()
