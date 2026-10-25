"""Buat produk.json (untuk halaman link-bio) langsung dari tab Affiliate.

Kolom dibaca per posisi: A=No, C=Nama, F=Harga, L=Link affiliate, AB=Foto, AC=Nama pendek.
Produk hanya masuk kalau No berupa angka, link Shopee dan foto sudah terisi.
"""
import csv, io, json, os, re, sys, urllib.request

src = os.environ.get("SHEET_CSV_URL", "")
if not src:
    sys.exit("SHEET_CSV_URL belum diisi")
data = urllib.request.urlopen(src, timeout=60).read().decode("utf-8")
produk = []
for r in csv.reader(io.StringIO(data)):
    def c(i):
        return r[i].strip() if len(r) > i else ""
    no, link, foto = c(0), c(11), c(27)
    if not no.isdigit() or not link.startswith("http") or not foto.startswith("http"):
        continue
    harga = re.sub(r"\D", "", c(5))
    produk.append({"kode": int(no), "nama": c(28) or c(2), "harga": int(harga or 0),
                   "link": link, "foto": foto})
if not produk:
    sys.exit("Tidak ada produk valid di sheet; produk.json tidak diubah")
produk.sort(key=lambda p: p["kode"])
with open("produk.json", "w", encoding="utf-8") as f:
    json.dump(produk, f, ensure_ascii=False)
print("produk.json:", len(produk), "produk")
