"""Render video affiliate 9:16 dari Google Sheet (tab Affiliate).

Cara pakai di Sheet:
  - Isi bahan di kolom: Video AI, Video saya, Foto produk lain, Voice ElevenLabs (boleh kosong).
  - Isi "Durasi video (detik)" (kosong = ikut panjang suara).
  - Centang kolom "Render". GitHub mengecek tiap jam dan merender baris yang dicentang.
  - Hasil: output/<No>.mp4 + catatan di output/hasil.csv (tampil otomatis di kolom "Hasil render").
Baris yang bahannya tidak berubah tidak dirender ulang (hemat waktu & kredit ElevenLabs).

Urutan video: Video AI -> Video saya -> foto (gambar AI, foto produk, foto lain) bergantian
dengan gerak zoom, sampai durasi terpenuhi. Kalau tidak ada video sama sekali, langsung foto.
"""
import csv, hashlib, io, json, os, re, subprocess, sys, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

W, H, FPS = 1080, 1920, 30
FOTO_DETIK = 3.0
ROOT = Path(__file__).parent
OUT = ROOT / "output"; CACHE = ROOT / ".cache"
OUT.mkdir(exist_ok=True); CACHE.mkdir(exist_ok=True)
HASIL = OUT / "hasil.csv"
FONT = os.getenv("FONT", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
VOICE_ID = os.getenv("VOICE_ID") or "W98P5TTtcHAH6zHkf7ul"  # Raya Fie (ID)
COL = {
    "no": "No", "nama": "Nama produk", "harga": "Harga (Rp)",
    "naskah": "Naskah suara (ElevenLabs, ±15 dtk)",
    "img_ai": "Link gambar AI (Drive publik)",
    "vid_ai": "Video AI (link Drive)",
    "audio": "Voice ElevenLabs (link Drive, kosong = otomatis)",
    "img_produk": "URL foto produk",
    "pendek": "Nama pendek (teks di video)",
    "vid_saya": "Video saya (link Drive)",
    "foto_lain": "Foto produk lain (link, pisah koma)",
    "durasi": "Durasi video (detik)",
    "render": "Render",
}
YA = {"true", "benar", "ya", "1", "x", "v", "✓"}

def g(row, key):
    return (row.get(COL[key]) or "").strip()

def run(cmd):
    r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-600:])

def drive_direct(url):
    m = re.search(r"/d/([\w-]+)|[?&]id=([\w-]+)", url or "")
    if "drive.google.com" in (url or "") and m:
        return f"https://drive.google.com/uc?export=download&id={m.group(1) or m.group(2)}"
    return url

def fetch(url, ext):
    """Unduh sekali, simpan di cache. Path lokal juga boleh."""
    if not url: return None
    if os.path.exists(url): return Path(url)
    p = CACHE / (hashlib.md5(url.encode()).hexdigest() + ext)
    if not p.exists():
        req = urllib.request.Request(drive_direct(url), headers={"User-Agent": "Mozilla/5.0"})
        p.write_bytes(urllib.request.urlopen(req, timeout=120).read())
    return p

def tts(text):
    """ElevenLabs TTS, di-cache per naskah -> kredit tidak terbuang."""
    p = CACHE / ("tts-" + hashlib.md5((VOICE_ID + text).encode()).hexdigest() + ".mp3")
    if p.exists(): return p
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key: raise RuntimeError("Secret ELEVENLABS_API_KEY belum diisi dan kolom voice kosong.")
    body = json.dumps({"text": text, "model_id": os.getenv("TTS_MODEL") or "eleven_multilingual_v2"}).encode()
    req = urllib.request.Request(f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}",
        data=body, headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"})
    p.write_bytes(urllib.request.urlopen(req, timeout=120).read())
    return p

def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout
    try: return float(out.strip())
    except ValueError: return 0.0

def clip_from_image(img, secs, out, zoom_in=True):
    frames = max(1, int(secs * FPS))
    z = "min(zoom+0.0009,1.15)" if zoom_in else "if(eq(on,0),1.15,max(zoom-0.0009,1))"
    vf = (f"scale={W*2}:{H*2}:force_original_aspect_ratio=increase,crop={W*2}:{H*2},"
          f"zoompan=z='{z}':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},setsar=1")
    run(["ffmpeg", "-y", "-loop", "1", "-i", str(img), "-vf", vf, "-t", f"{secs:.2f}",
         "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "veryfast", str(out)])

def clip_from_video(vid, secs, out):
    vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1"
    run(["ffmpeg", "-y", "-i", str(vid), "-t", f"{secs:.2f}", "-vf", vf, "-an",
         "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "veryfast", str(out)])

def esc(t):
    return t.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’").replace("%", "\\%")

def input_hash(row):
    keys = ["nama", "harga", "naskah", "img_ai", "vid_ai", "audio", "img_produk", "pendek",
            "vid_saya", "foto_lain", "durasi"]
    return hashlib.md5(("|".join(g(row, k) for k in keys) + VOICE_ID).encode()).hexdigest()[:12]

def render(row):
    no = g(row, "no")
    nama = g(row, "nama")
    harga = re.sub(r"\D", "", g(row, "harga"))
    work = CACHE / f"row{no}"; work.mkdir(exist_ok=True)

    audio = fetch(g(row, "audio"), ".mp3") or tts(g(row, "naskah"))
    a_dur = duration(audio)
    try: total = float(g(row, "durasi").replace(",", "."))
    except ValueError: total = 0
    if total <= 0: total = a_dur + 0.6
    total = max(5.0, min(total, 90.0))
    # Suara lebih panjang dari durasi: percepat sedikit (maks 1,25x), sisanya dipotong.
    tempo = min(1.25, a_dur / (total - 0.3)) if a_dur > total - 0.3 else 1.0

    clips, left, k = [], total, 0
    for url in (g(row, "vid_ai"), g(row, "vid_saya")):
        v = fetch(url, ".mp4")
        if v and left > 0.3:
            secs = min(duration(v) or left, left)
            c = work / f"c{k}.mp4"; clip_from_video(v, secs, c)
            clips.append(c); left -= secs; k += 1
    urls = [g(row, "img_ai"), g(row, "img_produk")] + [x.strip() for x in g(row, "foto_lain").split(",")]
    fotos = [fetch(u, ".jpg") for u in urls if u]
    if not fotos and not clips: raise RuntimeError("Tidak ada video/foto sama sekali.")
    i = 0
    while left > 0.3 and fotos:
        secs = min(FOTO_DETIK, left)
        c = work / f"c{k}.mp4"; clip_from_image(fotos[i % len(fotos)], secs, c, zoom_in=(i % 2 == 0))
        clips.append(c); left -= secs; k += 1; i += 1

    lst = work / "list.txt"
    lst.write_text("".join(f"file '{c.resolve()}'\n" for c in clips))
    joined = work / "joined.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)])

    pendek = g(row, "pendek") or nama
    judul = esc(pendek[:30] + ("…" if len(pendek) > 30 else ""))
    hrg = esc(f"Cuma Rp{int(harga):,}".replace(",", ".")) if harga else ""
    box = "box=1:boxcolor=black@0.55:boxborderw=24"
    vf = (f"tpad=stop_mode=clone:stop_duration=5,"
          f"drawtext=fontfile={FONT}:text='{judul}':fontsize=46:fontcolor=white:{box}:x=(w-tw)/2:y=170,"
          + (f"drawtext=fontfile={FONT}:text='{hrg}':fontsize=72:fontcolor=yellow:{box}:x=(w-tw)/2:y=290," if hrg else "")
          + f"drawtext=fontfile={FONT}:text='Cek link di bio / komentar':fontsize=56:fontcolor=white:"
            f"box=1:boxcolor=0xEE4D2D@0.95:boxborderw=26:x=(w-tw)/2:y=h-330")
    af = (f"atempo={tempo:.3f}," if tempo > 1.0 else "") + f"apad,afade=t=out:st={max(0, total-0.4):.2f}:d=0.4"
    out = OUT / f"{no}.mp4"
    run(["ffmpeg", "-y", "-i", str(joined), "-i", str(audio), "-vf", vf, "-af", af,
         "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
         "-c:a", "aac", "-b:a", "128k", "-t", f"{total:.2f}", "-movflags", "+faststart", str(out)])
    catatan = f"Selesai {duration(out):.0f} dtk"
    if tempo > 1.0: catatan += f" (suara dipercepat {tempo:.2f}x)"
    if a_dur / 1.25 > total: catatan += " - suara terpotong, pendekkan naskah"
    return catatan

def load_hasil():
    if not HASIL.exists(): return {}
    return {r["No"]: r for r in csv.DictReader(HASIL.open(encoding="utf-8"))}

def save_hasil(data):
    with HASIL.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["No", "Hasil", "Hash"])
        w.writeheader()
        for k in sorted(data, key=lambda x: int(x) if x.isdigit() else 0):
            w.writerow(data[k])

def main():
    src = os.getenv("SHEET_CSV_URL") or (sys.argv[1] if len(sys.argv) > 1 else "")
    if not src: sys.exit("Isi secret SHEET_CSV_URL (link CSV tab Affiliate) atau beri path CSV.")
    data = Path(src).read_text() if os.path.exists(src) else urllib.request.urlopen(src, timeout=60).read().decode()
    rows = [r for r in csv.DictReader(io.StringIO(data)) if g(r, "render").lower() in YA and g(r, "no")]
    hasil = load_hasil()
    todo = [r for r in rows if hasil.get(g(r, "no"), {}).get("Hash") != input_hash(r)]
    if not todo: print("Tidak ada baris baru yang dicentang Render."); return
    wib = timezone(timedelta(hours=7)); gagal = 0
    for r in todo:
        no = g(r, "no")
        try:
            cat = render(r); print("OK  ", no, cat)
            hasil[no] = {"No": no, "Hasil": f"{cat} - {datetime.now(wib):%d/%m %H:%M}", "Hash": input_hash(r)}
        except Exception as e:
            gagal += 1; print("GAGAL baris", no, "-", e)
            hasil[no] = {"No": no, "Hasil": f"Gagal: {str(e)[:120]}", "Hash": ""}
    save_hasil(hasil)
    if gagal: print(f"{gagal} baris gagal dirender.")

if __name__ == "__main__":
    main()
