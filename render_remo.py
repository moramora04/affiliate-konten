"""Versi Remotion (animasi lebih hidup) untuk video affiliate.

Dipasang otomatis oleh render_facts.py (yang diimpor render.py) tanpa mengubah workflow.
Aktif untuk baris dengan No >= "remotion_dari" di config.json. Baris lain tetap memakai render lama.
Susunan: foto artis (artisDetik) -> 3 foto asli (artis kecil tanpa latar goyang di atasnya) -> foto artis lagi.
Suara ElevenLabs & musik memakai bahan yang sama dengan render lama. Kalau Remotion gagal, pakai render lama
dan baris dicoba lagi pada pengecekan berikutnya.
"""
import hashlib, json, os, re, shutil, subprocess, sys
from pathlib import Path

M = sys.modules["__main__"]          # render.py yang sedang berjalan
ROOT = Path(__file__).parent
REMO = ROOT / "remo"
REMO_VER = "r1"
_asli_render, _asli_hash = M.render, M.input_hash


def aktif(no):
    try:
        return int(no) >= int(M.CFG.get("remotion_dari", 10 ** 9))
    except (TypeError, ValueError):
        return False


def sh(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise RuntimeError((" ".join(map(str, cmd[:3]))) + ": " + (r.stderr or r.stdout)[-700:])
    return r.stdout


_siap = {"ok": False}


def siapkan_alat():
    if _siap["ok"]:
        return
    try:
        import rembg, PIL  # noqa
    except ImportError:
        try:
            sh([sys.executable, "-m", "pip", "install", "-q", "rembg", "onnxruntime", "pillow"])
        except RuntimeError:
            sh([sys.executable, "-m", "pip", "install", "-q", "--break-system-packages", "rembg", "onnxruntime", "pillow"])
        import importlib, site
        importlib.invalidate_caches()
        for d in (site.getusersitepackages(),):
            if os.path.isdir(d) and d not in sys.path:
                sys.path.append(d)
        import rembg, PIL  # noqa  (gagal di sini = pemasangan benar-benar gagal)
    if not (REMO / "node_modules" / "remotion").exists():
        sh(["npm", "install", "--no-audit", "--no-fund", "--loglevel=error"], cwd=REMO, timeout=900)
    if os.getenv("GITHUB_ACTIONS"):
        # pustaka sistem yang dibutuhkan Chrome milik Remotion (diabaikan kalau sudah ada)
        for pk in (["libnss3", "libdbus-1-3", "libatk1.0-0", "libxrandr2", "libxkbcommon0", "libxfixes3",
                    "libxcomposite1", "libxdamage1", "libgbm1", "libcups2", "libatk-bridge2.0-0", "libpango-1.0-0",
                    "libcairo2"]):
            subprocess.run(["sudo", "apt-get", "install", "-y", "-qq", pk], capture_output=True)
        for pk in ("libasound2t64", "libasound2"):
            if subprocess.run(["sudo", "apt-get", "install", "-y", "-qq", pk], capture_output=True).returncode == 0:
                break
    _siap["ok"] = True


def potong_artis(foto, keluar):
    """Hapus latar foto artis -> PNG transparan, dipotong rapat."""
    cache = M.CACHE / ("potong-" + hashlib.md5(Path(foto).read_bytes()).hexdigest()[:12] + ".png")
    if not cache.exists():
        from rembg import new_session, remove
        from PIL import Image
        im = Image.open(foto).convert("RGB")
        out = remove(im, session=new_session("u2net_human_seg"))
        box = out.getchannel("A").point(lambda v: 255 if v > 20 else 0).getbbox()
        if box:
            out = out.crop(box)
        out.thumbnail((700, 1100))
        out.save(cache)
    shutil.copy(cache, keluar)


def kata_waktu(naskah, speech, total):
    words = naskah.split()
    start = 0.15
    span = max(1.0, min(speech, total - 0.5) - start)
    weights = [len(w) + 2 for w in words]
    tw = float(sum(weights)) or 1.0
    t, out = start, []
    for w, wt in zip(words, weights):
        d = span * wt / tw
        out.append({"w": w, "mulai": round(t, 3), "durasi": round(d, 3)})
        t += d
    return out


def remo_render(row):
    g = M.g
    no = g(row, "no")
    siapkan_alat()
    audio = M.fetch(g(row, "audio"), ".mp3") or M.voice_for(row)
    a_dur = M.duration(audio)
    try:
        total = float(g(row, "durasi").replace(",", "."))
    except ValueError:
        total = 0
    if total <= 0:
        total = a_dur + 0.6
    total = max(5.0, min(total, 90.0))
    tempo = min(1.25, a_dur / (total - 0.3)) if a_dur > total - 0.3 else 1.0

    pub = REMO / "public" / f"p{no}"
    shutil.rmtree(pub, ignore_errors=True)
    pub.mkdir(parents=True)
    try:
        # suara (dipercepat bila perlu, dipotong sesuai durasi) & musik
        af = (f"atempo={tempo:.3f}," if tempo > 1.0 else "") + "apad"
        sh(["ffmpeg", "-y", "-loglevel", "error", "-i", str(audio), "-af", af, "-t", f"{total:.2f}",
            "-c:a", "libmp3lame", "-b:a", "128k", str(pub / "suara.mp3")])
        musik = ""
        if M.MUSIK_ON:
            sh(["ffmpeg", "-y", "-loglevel", "error", "-i", str(M.make_music()), "-c:a", "libmp3lame",
                "-b:a", "96k", str(pub / "musik.mp3")])
            musik = f"p{no}/musik.mp3"
        # foto
        artis = ""
        potong = ""
        if g(row, "img_ai"):
            shutil.copy(M.fetch(g(row, "img_ai"), ".jpg"), pub / "artis.jpg")
            artis = f"p{no}/artis.jpg"
            try:
                potong_artis(pub / "artis.jpg", pub / "potong.png")
                potong = f"p{no}/potong.png"
            except Exception as e:
                print("Potong artis gagal (artis kecil dilewati):", str(e)[:200])
        urls = [g(row, "img_produk")] + [x.strip() for x in g(row, "foto_lain").split(",")]
        fotos = []
        for u in [x for x in urls if x][:3]:
            p = M.fetch(u, ".jpg")
            nama = f"f{len(fotos) + 1}.jpg"
            shutil.copy(p, pub / nama)
            fotos.append(f"p{no}/{nama}")
        pendek = g(row, "pendek") or g(row, "nama")
        harga = re.sub(r"\D", "", g(row, "harga"))
        props = {
            "kode": str(no),
            "judul": pendek[:30] + ("…" if len(pendek) > 30 else ""),
            "harga": ("Rp" + f"{int(harga):,}".replace(",", ".")) if harga else "",
            "durasi": total, "artis": artis, "fotos": fotos,
            "audio": f"p{no}/suara.mp3", "musik": musik,
            "artisDetik": float(M.CFG.get("foto_artis_detik", 5)), "fotoDetik": float(M.CFG.get("foto_asli_detik", 2)),
            "kata": kata_waktu(g(row, "naskah"), a_dur / tempo, total),
        }
        if potong:
            props["artisPotong"] = potong
        pj = M.CACHE / f"remo-props-{no}.json"
        pj.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
        out = M.OUT / f"{no}.mp4"
        sh(["node", "render-remo.mjs", str(pj.resolve()), str(out.resolve())], cwd=REMO, timeout=1800)
    finally:
        shutil.rmtree(pub, ignore_errors=True)
    return f"Selesai {M.duration(out):.0f} dtk (Remotion)" + (f" (suara dipercepat {tempo:.2f}x)" if tempo > 1.0 else "")


def render(row):
    if not aktif(M.g(row, "no")):
        return _asli_render(row)
    try:
        return remo_render(row)
    except Exception as e:
        print("Remotion gagal, pakai render lama:", e)
        # kata "klip AI gagal" membuat baris dicoba lagi pada pengecekan berikutnya
        return _asli_render(row) + " (klip AI gagal: Remotion " + str(e)[:60].replace("\n", " ") + ")"


def input_hash(row):
    h = _asli_hash(row)
    if not aktif(M.g(row, "no")):
        return h
    return hashlib.md5((h + REMO_VER + str(M.CFG.get("foto_artis_detik", 5))).encode()).hexdigest()[:12]


M.render = render
M.input_hash = input_hash
