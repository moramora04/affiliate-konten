"""Render video affiliate 9:16 dari Google Sheet (tab Affiliate).

Cara pakai di Sheet:
  - Isi bahan di kolom: Video AI, Video saya, Foto produk lain, Voice ElevenLabs (boleh kosong).
  - Isi "Durasi video (detik)" (kosong = ikut panjang suara).
  - Kolom "Render": isi "Render" (atau kosong) = dirender otomatis; "Tunggu" = jangan dirender dulu.
    GitHub mengecek tiap jam.
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

MUSIK_VER = "m1"          # ganti angkanya kalau gaya musik diubah -> video dirender ulang
MUSIK_ON = os.getenv("MUSIK", "1") != "0"   # variabel Actions MUSIK=0 -> tanpa musik

def make_music():
    """Musik latar ORIGINAL dibuat lewat kode (tanpa lagu orang lain) -> bebas hak cipta.
    Pad akor C-Am-F-G + petikan lembut + ketukan halus, ±100 BPM, loop 38,4 dtk."""
    p = CACHE / f"latar-{MUSIK_VER}.wav"
    if p.exists(): return p
    import math, struct, wave
    sr, bpm = 22050, 100
    beat = 60.0 / bpm
    chords = [(261.63, 329.63, 392.00), (220.00, 261.63, 329.63),
              (174.61, 220.00, 261.63), (196.00, 246.94, 293.66)]   # C, Am, F, G
    bars_per = 2; total_beats = 4 * bars_per * len(chords) * 2      # 2 putaran
    n = int(total_beats * beat * sr)
    buf = [0.0] * n
    def add(start, dur, freq, amp, kind="sine"):
        s0 = int(start * sr); m = int(dur * sr)
        for i in range(m):
            j = s0 + i
            if j >= n: break
            t = i / sr
            env = min(1.0, t / 0.02) * math.exp(-t * (3.0 if kind == "pluck" else 0.0)) \
                  * (min(1.0, (dur - t) / 0.3) if kind == "pad" else 1.0)
            v = math.sin(2 * math.pi * freq * t) + (0.35 * math.sin(4 * math.pi * freq * t) if kind == "pluck" else 0)
            buf[j] += amp * env * v
    for rep in range(2):
        for ci, ch in enumerate(chords):
            t0 = (rep * len(chords) + ci) * bars_per * 4 * beat
            for f in ch: add(t0, bars_per * 4 * beat, f / 2, 0.10, "pad")          # pad
            for b in range(bars_per * 4):                                             # petikan
                add(t0 + b * beat, beat * 1.8, ch[b % 3] * 2, 0.09, "pluck")
                add(t0 + b * beat + beat / 2, beat * 1.2, ch[(b + 1) % 3] * 2, 0.05, "pluck")
            for b in range(bars_per * 4):                                             # kick halus
                k0 = int((t0 + b * beat) * sr)
                for i in range(int(0.12 * sr)):
                    if k0 + i >= n: break
                    t = i / sr
                    buf[k0 + i] += 0.22 * math.exp(-t * 28) * math.sin(2 * math.pi * (110 - 600 * t * 0.2) * t)
    mx = max(abs(x) for x in buf) or 1
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, x / mx * 0.9)) * 32767)) for x in buf))
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
    return hashlib.md5(("|".join(g(row, k) for k in keys) + VOICE_ID + (MUSIK_VER if MUSIK_ON else "")).encode()).hexdigest()[:12]

def render(row):
    no = g(row, "no")
    nama = g(row, "nama")
    harga = re.sub(r"\D", "", g(row, "harga"))
    work = CACHE / f"row{no}"; work.mkdir(exist_ok=True)

    audio = fetch(g(row, "audio"), ".mp3") or voice_for(row)
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
          + f"drawtext=fontfile={FONT}:text='Kode {no} - Cek link di bio':fontsize=56:fontcolor=white:"
            f"box=1:boxcolor=0xEE4D2D@0.95:boxborderw=26:x=(w-tw)/2:y=h-330")
    af = (f"atempo={tempo:.3f}," if tempo > 1.0 else "") + f"apad,afade=t=out:st={max(0, total-0.4):.2f}:d=0.4"
    out = OUT / f"{no}.mp4"
    if MUSIK_ON:
        mus = make_music()
        fc = (f"[1:a]{af}[v];[2:a]volume=0.13,afade=t=in:d=1,afade=t=out:st={max(0, total-1.2):.2f}:d=1.2[m];"
              f"[v][m]amix=inputs=2:duration=first:normalize=0[a]")
        run(["ffmpeg", "-y", "-i", str(joined), "-i", str(audio), "-stream_loop", "-1", "-i", str(mus),
             "-filter_complex", fc, "-vf", vf, "-map", "0:v", "-map", "[a]",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
             "-c:a", "aac", "-b:a", "128k", "-t", f"{total:.2f}", "-movflags", "+faststart", str(out)])
    else:
        run(["ffmpeg", "-y", "-i", str(joined), "-i", str(audio), "-vf", vf, "-af", af,
             "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
             "-c:a", "aac", "-b:a", "128k", "-t", f"{total:.2f}", "-movflags", "+faststart", str(out)])
    catatan = f"Selesai {duration(out):.0f} dtk"
    if tempo > 1.0: catatan += f" (suara dipercepat {tempo:.2f}x)"
    if a_dur / 1.25 > total: catatan += " - suara terpotong, pendekkan naskah"
    return catatan

HASIL_DATA = {}

def voice_for(row):
    """Suara ElevenLabs per baris -> output/suara-<No>.mp4 (bisa didengar & tidak dibuat ulang)."""
    no, text = g(row, "no"), g(row, "naskah")
    if not text: raise RuntimeError("Naskah suara (kolom L) kosong.")
    h = hashlib.md5((VOICE_ID + text).encode()).hexdigest()[:12]
    out = OUT / f"suara-{no}.mp4"
    rec = HASIL_DATA.setdefault(no, {"No": no})
    if rec.get("SuaraHash") == h and out.exists():
        return out
    run(["ffmpeg", "-y", "-i", str(tts(text)), "-vn", "-c:a", "aac", "-b:a", "128k", str(out)])
    rec["SuaraHash"] = h
    rec["Suara"] = f"{duration(out):.0f}"
    return out

def load_hasil():
    if not HASIL.exists(): return {}
    return {r["No"]: r for r in csv.DictReader(HASIL.open(encoding="utf-8"))}

def save_hasil(data):
    with HASIL.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["No", "Hasil", "Hash", "Suara", "SuaraHash"], extrasaction="ignore")
        w.writeheader()
        for k in sorted(data, key=lambda x: int(x) if x.isdigit() else 0):
            w.writerow(data[k])

def main():
    src = os.getenv("SHEET_CSV_URL") or (sys.argv[1] if len(sys.argv) > 1 else "")
    if not src: sys.exit("Isi secret SHEET_CSV_URL (link CSV tab Affiliate) atau beri path CSV.")
    data = Path(src).read_text() if os.path.exists(src) else urllib.request.urlopen(src, timeout=60).read().decode()
    # Judul kolom bisa dobel (mis. "No" dari data hasil yang tersembunyi) -> pakai kemunculan PERTAMA.
    rd = csv.reader(io.StringIO(data)); header = next(rd, [])
    idx = {}
    for i, h in enumerate(header): idx.setdefault(h.strip(), i)
    semua = [{h: (r[i] if i < len(r) else "") for h, i in idx.items()} for r in rd]
    semua = [r for r in semua if g(r, "no")]
    hasil = HASIL_DATA; hasil.update(load_hasil())
    # 1) Suara: dibuat untuk semua baris yang punya naskah & kolom voice kosong (sekali saja per naskah).
    for r in semua:
        if g(r, "naskah") and not g(r, "audio"):
            try: voice_for(r)
            except Exception as e: print("Suara gagal baris", g(r, "no"), "-", e)
    # 2) Video: semua baris KECUALI yang berisi "Tunggu", dan hanya kalau bahannya berubah.
    rows = [r for r in semua if g(r, "render").lower() != "tunggu"]
    todo = [r for r in rows if hasil.get(g(r, "no"), {}).get("Hash") != input_hash(r)]
    wib = timezone(timedelta(hours=7)); gagal = 0
    for r in todo:
        no = g(r, "no"); rec = hasil.setdefault(no, {"No": no})
        try:
            cat = render(r); print("OK  ", no, cat)
            rec.update({"Hasil": f"{cat} - {datetime.now(wib):%d/%m %H:%M}", "Hash": input_hash(r)})
        except Exception as e:
            gagal += 1; print("GAGAL baris", no, "-", e)
            rec.update({"Hasil": f"Gagal: {str(e)[:120]}", "Hash": ""})
    if not todo: print("Tidak ada baris baru yang perlu dirender.")
    save_hasil(hasil)
    if gagal: print(f"{gagal} baris gagal dirender.")

if __name__ == "__main__":
    main()
