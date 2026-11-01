# Validasi proyek

Proyek menggunakan snapshot resmi USAspending.gov yang tersimpan di `data/processed/`: **5.020 transaksi**, **2.043 award** dan **737 vendor** pada NSF dan NRC FY2024–FY2025. Metadata, hasil pemeriksaan kualitas dan checksums tersedia di folder tersebut.

Jalankan pengujian:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Pengujian meliputi kewajiban bersih, identitas vendor dan award, deduplikasi, tahun fiskal, batas klasifikasi ABC, konsistensi filter, integritas snapshot, SQL-versus-pandas, serta rendering Streamlit.

Pada repository sebelum migrasi, pemeriksaan CI atas dataset resmi dan pengujian lima halaman pernah berhasil. Migrasi repository ini tidak otomatis mengulangi pemeriksaan tersebut. [Riwayat hasil pemeriksaan sebelumnya](https://github.com/Granbe1l/USA-Federal-Procurement-Vendor-Dashboard/actions) mungkin tidak lagi tersedia jika repository lama dihapus.

## Batas verifikasi

- Perhitungan menggunakan snapshot historis, bukan data live.
- Pengujian berbasis fixtures tidak menggantikan validasi data resmi.
- Hasil performa di CI tidak dapat dianggap sama dengan performa Streamlit Cloud.
- Perlu memeriksa deployment dan unduhan CSV langsung dari browser setelah menghubungkan repository baru.
