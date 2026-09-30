# Potentiostat Raspberry Pi

Proyek ini berisi script inti untuk menjalankan IO Rodeo Rodeostat dari Raspberry Pi 4 dan memilih channel SPCE melalui MUX CD4051.

## Fitur

- Pengukuran CV Channel 1, Channel 2, atau keduanya melalui `multi_channel_cv.py`.
- Kontrol CD4051 dua channel memakai GPIO5 sebagai selector S0 dengan penomoran BCM.
- Data mentah dan plot disimpan otomatis ke `data/raw/`.
- Info pengukuran disimpan otomatis ke JSON.
- Analisis peak otomatis disimpan ke CSV.
- GUI layar sentuh tersedia melalui `dashboard.py` dengan Home, status koneksi, WiFi, dan panel pengukuran.
- Analisis ulang file data lama dapat dilakukan melalui `analyze_data.py`.
- Firmware Rodeostat tidak diubah.

## Struktur Folder

```text
Program_Potensiostat_Dual_Kanal/
|-- data/raw/              # Output data, plot, analisis CSV, dan info JSON
|-- src/                   # Modul pengukuran, penyimpanan, analisis, dan plotting
|-- tests/                 # Unit test
|-- dashboard.py           # GUI layar sentuh
|-- multi_channel_cv.py    # Script utama pengukuran CV multi-channel
|-- analyze_data.py        # Analisis ulang data pengukuran yang sudah tersimpan
|-- run_gui.py             # Launcher GUI untuk Raspberry Pi
|-- config.py              # Konfigurasi port, channel, MUX, dan parameter default
`-- requirements.txt       # Dependensi Python
```

Folder `data/raw/` boleh kosong sebelum pengukuran. Folder ini akan diisi otomatis saat pengukuran berjalan.

## Instalasi Raspberry Pi

```bash
python3 -m pip install -r requirements.txt --break-system-packages
```

Untuk GUI layar sentuh:

```bash
sudo apt install python3-tk
```

Jika port serial tidak bisa diakses:

```bash
sudo usermod -a -G dialout $USER
sudo reboot
```

## Menjalankan

Cek konfigurasi:

```bash
python3 main.py
```

CV untuk Channel 1 saja:

```bash
python3 multi_channel_cv.py --port /dev/ttyACM0 --channels 1
```

CV untuk Channel 1 dan Channel 2:

```bash
python3 multi_channel_cv.py --port /dev/ttyACM0 --channels 1,2
```

Gunakan `--no-show` jika hanya ingin menyimpan PNG tanpa membuka window plot.

GUI layar sentuh:

```bash
python3 run_gui.py
```

Override parameter dari command line:

```bash
python3 multi_channel_cv.py --channels 1,2 --param scanRate=0.05 --param currentRange="1000 uA"
```

Analisis ulang file data yang sudah tersimpan:

```bash
python3 analyze_data.py data/raw/nama_file_channel1.txt data/raw/nama_file_channel2.txt
```

Simpan hasil analisis ke file tertentu:

```bash
python3 analyze_data.py data/raw/nama_file_channel1.txt --output data/raw/analysis_manual.csv
```

## Testing

Test dapat dijalankan di laptop/PC tanpa Rodeostat:

```bash
python -m pytest
```

Script yang memakai GPIO dan Rodeostat tetap perlu dijalankan di Raspberry Pi dengan perangkat terhubung.

## File Cache

Folder berikut hanya cache dan aman dihapus:

```text
.pytest_cache/
src/__pycache__/
tests/__pycache__/
```

Cache tersebut bisa muncul lagi otomatis setelah menjalankan Python atau `pytest`.

## Wiring MUX CD4051

```text
Raspberry Pi GPIO5  -> CD4051 S0
Raspberry Pi GND    -> CD4051 S1
Raspberry Pi GND    -> CD4051 S2
Raspberry Pi GND    -> CD4051 GND
Rodeostat WE        -> CD4051 COM/Z
CD4051 Y0           -> WE SPCE 1
CD4051 Y1           -> WE SPCE 2
```

Dengan wiring ini, `Channel 1` aktif saat GPIO5 LOW dan `Channel 2` aktif saat GPIO5 HIGH. Channel lain tidak digunakan dan script hanya menerima channel `1` atau `2`.

RE dan CE masih dapat diparalelkan untuk prototype awal. Pengukuran multi-channel bersifat berurutan, bukan simultan.
