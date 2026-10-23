# Affiliate Konten – render video otomatis (hemat kredit)

Skrip ini membaca tab **Affiliate** di Google Sheet, lalu untuk setiap baris
berstatus **Siap render** membuat video vertikal 9:16 siap upload
(TikTok, Reels, Shorts, Facebook, Threads):

1. 5 detik pembuka: video AI (kolom P) kalau ada, kalau tidak gambar AI (kolom O) dibuat bergerak (zoom).
2. Sisa durasi: gantian foto produk asli (kolom AA) dan gambar AI, dengan gerak zoom.
3. Suara: file dari kolom Q, atau dibuat otomatis lewat API ElevenLabs dari kolom L.
4. Teks di layar: nama produk, harga, dan "Cek link di bio / komentar".

Semua kerja berat jalan di GitHub Actions (gratis), bukan di Claude.
Suara di-cache: naskah yang sama tidak dibuat dua kali, jadi kredit ElevenLabs tidak terbuang.

## Pasang sekali
1. Google Sheet → File → Bagikan → Publikasikan ke web → pilih tab **Affiliate** → format **CSV** → salin link.
2. Repo → Settings → Secrets and variables → Actions → **New repository secret**:
   - `SHEET_CSV_URL` = link CSV tadi
   - `ELEVENLABS_API_KEY` = API key ElevenLabs (elevenlabs.io → Profile → API Keys)
   - (opsional) tab Variables → `VOICE_ID` untuk ganti suara (default: Raya Fie, Bahasa Indonesia).

## Pemakaian harian
1. Isi baris produk di sheet. Gambar AI / audio / video simpan di Google Drive dengan akses
   "Siapa saja yang memiliki link", tempel link-nya di kolom O/P/Q (boleh kosong).
2. Ubah **Status** jadi `Siap render`.
3. Actions → **Render video affiliate** → Run workflow (atau tunggu jadwal 05.00 WIB).
4. Video muncul di folder `output/`. Link publik:
   `https://raw.githubusercontent.com/moramora04/affiliate-konten/main/output/<file>.mp4`
5. Ubah Status jadi `Video siap`, lalu `Terposting` setelah diunggah.

Uji lokal: `python3 render.py contoh.csv` (butuh ffmpeg).
