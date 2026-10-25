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
import csv, hashlib, io, json, os, re, subprocess, sys, urllib.error, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

W, H, FPS = 1080, 1920, 30
FOTO_DETIK = 2.0   # ganti foto tiap 2 dtk (lebih dinamis)
def _cfg():
    """Pengaturan kecil di config.json (tanpa ubah kode): tts_model, musik."""
    try: return json.loads((Path(__file__).parent / "config.json").read_text(encoding="utf-8"))
    except Exception: return {}
CFG = _cfg()
# eleven_v4 = suara natural (ada nada ceria/tenang per kalimat); eleven_multilingual_v2 = suara lama, lebih hemat kredit
TTS_MODEL_DEFAULT = CFG.get("tts_model", "eleven_multilingual_v2")
HOOKS = ["STOP SCROLL DULU!", "WAJIB TAHU INI!", "MURAH BANGET, SERIUS!", "JANGAN SAMPAI KETINGGALAN!"]
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

def MODEL_KEY():
    m = os.getenv("TTS_MODEL") or TTS_MODEL_DEFAULT
    return "" if m == "eleven_multilingual_v2" else m   # v2 = kunci lama (cache tetap terpakai)

def tts(text):
    """ElevenLabs TTS, di-cache per naskah -> kredit tidak terbuang."""
    model = os.getenv("TTS_MODEL") or TTS_MODEL_DEFAULT
    p = CACHE / ("tts-" + hashlib.md5((VOICE_ID + MODEL_KEY() + text).encode()).hexdigest() + ".mp3")
    if p.exists(): return p
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key: raise RuntimeError("Secret ELEVENLABS_API_KEY belum diisi dan kolom voice kosong.")
    if model in ("eleven_v3", "eleven_v4"): text = tag_text(text)
    body = json.dumps({"text": text, "model_id": model}).encode()
    req = urllib.request.Request(f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}",
        data=body, headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"})
    p.write_bytes(urllib.request.urlopen(req, timeout=120).read())
    return p

EDIT_VER = "e2"           # versi gaya edit (hook, subtitle, kartu penutup)
MUSIK_VER = "m1"          # ganti angkanya kalau gaya musik diubah -> video dirender ulang
MUSIK_ON = os.getenv("MUSIK", "1" if CFG.get("musik", True) else "0") != "0"   # variabel Actions MUSIK=0 -> tanpa musik

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
    fade = int(0.05 * sr)
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, x / mx * 0.9)) * 32767)) for x in buf))
    return p

def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout
    try: return float(out.strip())
    except ValueError: return 0.0

def clip_from_image(img, secs, out, variant=0):
    """4 gaya gerak bergantian: zoom-in, zoom-out, geser kanan, geser kiri."""
    frames = max(1, int(secs * FPS))
    cy = "ih/2-(ih/zoom/2)"
    if variant % 4 == 0:   z, x, y = "min(zoom+0.0016,1.2)", "iw/2-(iw/zoom/2)", cy
    elif variant % 4 == 1: z, x, y = "if(eq(on,0),1.2,max(zoom-0.0016,1))", "iw/2-(iw/zoom/2)", cy
    elif variant % 4 == 2: z, x, y = "1.15", f"(iw-iw/zoom)*on/{frames}", cy
    else:                  z, x, y = "1.15", f"(iw-iw/zoom)*(1-on/{frames})", cy
    vf = (f"scale={W*2}:{H*2}:force_original_aspect_ratio=increase,crop={W*2}:{H*2},"
          f"zoompan=z='{z}':d={frames}:x='{x}':y='{y}':s={W}x{H}:fps={FPS},setsar=1")
    run(["ffmpeg", "-y", "-loop", "1", "-i", str(img), "-vf", vf, "-t", f"{secs:.2f}",
         "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "veryfast", str(out)])

def clip_from_video(vid, secs, out):
    vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1"
    run(["ffmpeg", "-y", "-i", str(vid), "-t", f"{secs:.2f}", "-vf", vf, "-an",
         "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "veryfast", str(out)])

def _t(sec):
    sec = max(0, sec); cs = int(round(sec * 100))
    return f"{cs//360000}:{cs//6000%60:02d}:{cs//100%60:02d}.{cs%100:02d}"

def make_ass(path, no, text, speech_dur, total):
    """Subtitle ala TikTok: 3-4 kata per layar, kata yang sedang diucapkan menyala kuning,
    + teks hook di awal dan kartu penutup. Waktu kata diperkirakan dari panjang huruf."""
    words = text.split()
    start = 0.15; span = max(1.0, min(speech_dur, total - 0.5) - start)
    weights = [len(w) + 2 for w in words]; tw = float(sum(weights)) or 1.0
    t, timed = start, []
    for w, wt in zip(words, weights):
        d = span * wt / tw; timed.append((w, t, d)); t += d
    chunks, cur = [], []
    for item in timed:
        cur.append(item)
        if len(cur) >= 4 or item[0][-1:] in ".?!":
            chunks.append(cur); cur = []
    if cur: chunks.append(cur)
    hook = HOOKS[int(no) % len(HOOKS)] if str(no).isdigit() else HOOKS[0]
    lines = [
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920", "WrapStyle: 0",
        "ScaledBorderAndShadow: yes", "", "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,"
        "Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
        "Style: Sub,DejaVu Sans,68,&H0000F0FF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,7,0,2,70,70,560,1",
        "Style: Hook,DejaVu Sans,84,&H00FFFFFF,&H00FFFFFF,&H002D4DEE,&H00000000,-1,0,0,0,100,100,0,0,3,18,0,8,60,60,1000,1",
        "Style: End,DejaVu Sans,110,&H00FFFFFF,&H00FFFFFF,&H002D4DEE,&H00000000,-1,0,0,0,100,100,0,0,3,26,0,5,60,60,0,1",
        "", "[Events]", "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text"]
    lines.append(f"Dialogue: 0,{_t(0.05)},{_t(2.6)},Hook,,0,0,0,,{{\\fad(150,200)}}{hook}")
    for ch in chunks:
        s, e = ch[0][1], ch[-1][1] + ch[-1][2]
        body = "".join(f"{{\\k{max(1,int(d*100))}}}{w} " for w, _, d in ch).strip()
        lines.append(f"Dialogue: 0,{_t(s)},{_t(e+0.05)},Sub,,0,0,0,,{body}")
    lines.append(f"Dialogue: 1,{_t(total-2.6)},{_t(total)},End,,0,0,0,,{{\\fad(200,0)}}KODE {no}\\NCek link di bio")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")

def tag_text(text):
    """Untuk model v3/v4: sisipkan penanda emosi per kalimat supaya suara tidak datar/robot."""
    out = []
    sent = re.findall(r"[^.!?]+[.!?]*", text)
    for i, s in enumerate(sent):
        s = s.strip()
        if not s: continue
        low = s.lower()
        if i == 0: tag = "[cheerful]"
        elif "link di bio" in low or i == len(sent) - 1: tag = "[cheerful]"
        elif "harga" in low or "rp" in low or "ribu" in low or "promo" in low: tag = "[excited]"
        else: tag = "[calm]"
        out.append(f"{tag} {s}")
    return " ".join(out)

def esc(t):
    return t.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’").replace("%", "\\%")

def input_hash(row):
    keys = ["nama", "harga", "naskah", "img_ai", "vid_ai", "audio", "img_produk", "pendek",
            "vid_saya", "foto_lain", "durasi"]
    return hashlib.md5(("|".join(g(row, k) for k in keys) + VOICE_ID + MODEL_KEY() + EDIT_VER + (MUSIK_VER if MUSIK_ON else "") + ("ai" + str(AI_SECS) if ai_on(g(row, "no")) else "") + ("loop" if g(row, "no") in LOOP_NOS else "") + ("pp" if g(row, "no") in PINGPONG_NOS else "") + ("nt" if g(row, "no") in TANPA_TEKS else "") + ("ar" if artis_on(g(row, "no")) else "")).encode()).hexdigest()[:12]

# ---- Klip video AI (Alibaba Wan, bayar per detik; hanya untuk No yang ada di config.json "ai_klip") ----
AI_NOS = {str(x) for x in CFG.get("ai_klip", [])}
AI_SECS = int(CFG.get("ai_detik", 5))
LOOP_NOS = {str(x) for x in CFG.get("loop_ai", [])}   # No di sini: Video AI diputar 2x (loop mulus)
PINGPONG_NOS = {str(x) for x in CFG.get("pingpong", [])}   # putaran ke-2 dibalik (maju-mundur)
TANPA_TEKS = {str(x) for x in CFG.get("tanpa_teks", [])}   # tanpa tulisan/subtitle di video
AI_PROMPT = ("Product showcase video for online shop. Smooth slow camera push-in, gentle natural movement, "
             "soft studio lighting, the product stays sharp and unchanged, vertical short-video style.")

# ---- Artis otomatis (tanpa Claude): foto artis + foto produk -> gambar gabungan -> klip 5 dtk -> loop 10 dtk ----
# config.json: "artis_foto": "<URL foto artis publik>", "artis_nos": [9, 10], "artis_aksi": {"9": "minum dari tumbler"},
#              "artis_teks": false (default: video tanpa tulisan), "artis_gambar": {"12": "<URL gambar gabungan siap>"}
#              (kalau diisi, pembuatan gambar dilewati). Perlu secret DASHSCOPE_API_KEY. Hasil disimpan
#              di output/artis-<No>.png & .mp4 (tidak dibuat ulang -> hemat kredit).
ARTIS_NOS = {str(x) for x in CFG.get("artis_nos", [])}
ARTIS_FOTO = CFG.get("artis_foto", "")
ARTIS_AKSI = {str(k): v for k, v in CFG.get("artis_aksi", {}).items()}
ARTIS_AKSI_DEFAULT = ("gunakan produk itu secara alami: pakai bajunya, semprotkan parfumnya, makan makanannya, "
                      "minum dari botolnya, atau pakai sabunnya")

def artis_on(no): return str(no) in ARTIS_NOS and bool(ARTIS_FOTO) and bool(os.getenv("DASHSCOPE_API_KEY"))

def _data_uri(path):
    import base64
    ext = "png" if str(path).lower().endswith(".png") else "jpeg"
    return f"data:image/{ext};base64," + base64.b64encode(Path(path).read_bytes()).decode()

def _dash_sync(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={
        "Authorization": "Bearer " + os.environ["DASHSCOPE_API_KEY"], "Content-Type": "application/json"})
    try: return json.loads(urllib.request.urlopen(req, timeout=180).read())
    except urllib.error.HTTPError as e: raise RuntimeError(f"AI {e.code}: {e.read().decode()[:200]}")

def artis_gambar(no, foto_produk):
    """Gambar gabungan: artis yang sama memegang/memakai produk (disimpan output/artis-<No>.png)."""
    dst = OUT / f"artis-{no}.png"
    if dst.exists(): return dst
    siap = CFG.get("artis_gambar", {}).get(str(no))   # gambar gabungan buatan sendiri (URL) -> lewati pembuatan gambar
    if siap:
        dst.write_bytes(fetch(siap, ".png").read_bytes()); return dst
    aksi = ARTIS_AKSI.get(str(no), ARTIS_AKSI_DEFAULT)
    prompt = ("Foto realistis gaya kamera HP, 9:16. Wanita yang sama persis dengan gambar pertama (wajah, rambut, identitas). "
              "Dia tersenyum ceria ke kamera, " + aksi + ", memegang produk dari gambar kedua dengan jelas terlihat, "
              "bentuk dan warna produk persis sama. Cahaya alami, pose natural dan menarik. Tanpa teks, logo, watermark.")
    r, err = None, ""
    for model in CFG.get("artis_model_gambar", ["qwen-image-edit-plus", "qwen-image-edit"]):
        body = {"model": model, "input": {"messages": [{"role": "user", "content": [
            {"image": _data_uri(fetch(ARTIS_FOTO, ".jpg"))}, {"image": _data_uri(fetch(foto_produk, ".jpg"))},
            {"text": prompt}]}]}, "parameters": {"n": 1, "watermark": False}}
        try:
            r = _dash_sync("https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation", body); break
        except RuntimeError as e:
            err = str(e)
            if "Model not exist" not in err: raise
    if r is None: raise RuntimeError(err)
    url = r["output"]["choices"][0]["message"]["content"][0]["image"]
    dst.write_bytes(urllib.request.urlopen(url, timeout=120).read())
    return dst

def artis_klip(no, foto_produk):
    """Klip 5 dtk artis berinteraksi dengan produk, dari gambar gabungan (output/artis-<No>.mp4)."""
    dst = OUT / f"artis-{no}.mp4"
    if dst.exists(): return dst
    img = artis_gambar(no, foto_produk)
    aksi = ARTIS_AKSI.get(str(no), ARTIS_AKSI_DEFAULT)
    prompt = ("Video HP natural dan realistis, wanita yang sama, gembira dan cantik. Dia tersenyum ke kamera, " + aksi +
              ", gerakan halus seperti manusia asli (bukan robot), napas dan kedipan alami, lalu kembali ke pose awal "
              "di detik terakhir. Wajah dan produk tetap sama. Tanpa teks.")
    base = "https://dashscope-intl.aliyuncs.com/api/v1"
    r = _dash(base + "/services/aigc/video-generation/video-synthesis", {
        "model": "wan2.6-i2v-flash", "input": {"prompt": prompt, "img_url": _data_uri(img)},
        "parameters": {"resolution": "720P", "duration": 5, "audio": False, "prompt_extend": False}})
    tid = r["output"]["task_id"]
    import time
    for _ in range(60):
        time.sleep(10)
        o = _dash(f"{base}/tasks/{tid}")["output"]
        if o["task_status"] == "SUCCEEDED":
            dst.write_bytes(urllib.request.urlopen(o["video_url"], timeout=120).read()); return dst
        if o["task_status"] in ("FAILED", "CANCELED", "UNKNOWN"):
            raise RuntimeError("Klip artis gagal: " + str(o.get("message") or o.get("code"))[:150])
    raise RuntimeError("Klip artis kelamaan")

def ai_on(no): return str(no) in AI_NOS and bool(os.getenv("DASHSCOPE_API_KEY"))

def _dash(url, body=None):
    key = os.environ["DASHSCOPE_API_KEY"]
    h = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
    if body is not None: h["X-DashScope-Async"] = "enable"
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, headers=h)
    try: return json.loads(urllib.request.urlopen(req, timeout=60).read())
    except urllib.error.HTTPError as e: raise RuntimeError(f"AI {e.code}: {e.read().decode()[:200]}")

def ai_clip(no, foto_url):
    """Buat klip AI dari foto produk. Sekali saja per produk (disimpan di output/ai-<No>.mp4)."""
    dst = OUT / f"ai-{no}.mp4"
    if dst.exists(): return dst
    base = "https://dashscope-intl.aliyuncs.com/api/v1"
    r = _dash(base + "/services/aigc/video-generation/video-synthesis", {
        "model": "wan2.6-i2v-flash",
        "input": {"prompt": AI_PROMPT, "img_url": foto_url},
        "parameters": {"resolution": "720P", "duration": AI_SECS, "audio": False, "prompt_extend": True}})
    tid = r["output"]["task_id"]
    import time
    for _ in range(60):
        time.sleep(10)
        o = _dash(f"{base}/tasks/{tid}")["output"]
        if o["task_status"] == "SUCCEEDED":
            dst.write_bytes(urllib.request.urlopen(o["video_url"], timeout=120).read()); return dst
        if o["task_status"] in ("FAILED", "CANCELED", "UNKNOWN"):
            raise RuntimeError("AI gagal: " + str(o.get("message") or o.get("code"))[:150])
    raise RuntimeError("AI klip kelamaan")

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
    ai_gagal = ""
    if ai_on(no) and g(row, "img_produk"):
        try:
            v = ai_clip(no, g(row, "img_produk"))
            secs = min(duration(v) or left, left)
            c = work / "c_ai.mp4"; clip_from_video(v, secs, c)
            clips.append(c); left -= secs; k += 1
        except Exception as e:
            ai_gagal = str(e)[:100]; print("Klip AI gagal", no, "-", e)
    artis_v = None
    if artis_on(no) and g(row, "img_produk"):
        try: artis_v = artis_klip(no, g(row, "img_produk"))
        except Exception as e:
            ai_gagal = str(e)[:100]; print("Klip artis gagal", no, "-", e)
    sumber_ai = str(artis_v) if artis_v else g(row, "vid_ai")
    for url in (sumber_ai, g(row, "vid_saya")):
        v = fetch(url, ".mp4")
        ulang = 2 if (url and url == sumber_ai and (artis_v or str(no) in LOOP_NOS)) else 1
        if v and left > 0.3:
            secs = min(duration(v) or left, left)
            c = work / f"c{k}.mp4"; clip_from_video(v, secs, c)
            for n in range(ulang):
                if left > 0.3:
                    if n == 1 and (artis_v or str(no) in PINGPONG_NOS):
                        r = work / f"c{k}_rev.mp4"
                        run(["ffmpeg", "-y", "-i", str(c), "-vf", "reverse", "-an", "-pix_fmt", "yuv420p",
                             "-c:v", "libx264", "-preset", "veryfast", str(r)])
                        clips.append(r)
                    else:
                        clips.append(c)
                    left -= secs; k += 1
    urls = [g(row, "img_ai"), g(row, "img_produk")] + [x.strip() for x in g(row, "foto_lain").split(",")]
    fotos = [fetch(u, ".jpg") for u in urls if u]
    if not fotos and not clips: raise RuntimeError("Tidak ada video/foto sama sekali.")
    i = 0
    while left > 0.3 and fotos:
        secs = min(FOTO_DETIK, left)
        c = work / f"c{k}.mp4"; clip_from_image(fotos[i % len(fotos)], secs, c, variant=i)
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
    ass = work / "sub.ass"
    make_ass(ass, no, g(row, "naskah"), a_dur / tempo, total)
    vf += f",subtitles='{ass.resolve()}':fontsdir={Path(FONT).parent}"
    if str(no) in TANPA_TEKS or (artis_v and not CFG.get("artis_teks", False)):
        vf = "tpad=stop_mode=clone:stop_duration=5"
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
    if ai_on(no) and not ai_gagal: catatan += " + klip AI"
    if ai_gagal: catatan += " (klip AI gagal: " + ai_gagal + ")"
    return catatan

HASIL_DATA = {}

def voice_for(row):
    """Suara ElevenLabs per baris -> output/suara-<No>.mp4 (bisa didengar & tidak dibuat ulang)."""
    no, text = g(row, "no"), g(row, "naskah")
    if not text: raise RuntimeError("Naskah suara (kolom L) kosong.")
    h = hashlib.md5((VOICE_ID + MODEL_KEY() + text).encode()).hexdigest()[:12]
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
            rec.update({"Hasil": f"{cat} - {datetime.now(wib):%d/%m %H:%M}", "Hash": "" if "klip AI gagal" in cat else input_hash(r)})
        except Exception as e:
            gagal += 1; print("GAGAL baris", no, "-", e)
            rec.update({"Hasil": f"Gagal: {str(e)[:120]}", "Hash": ""})
    if not todo: print("Tidak ada baris baru yang dicentang Render.")
    save_hasil(hasil)
    if gagal: print(f"{gagal} baris gagal dirender.")

if __name__ == "__main__":
    main()
