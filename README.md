# D20 Printer for Linux

[![Tests](https://github.com/Clevis22/d20printer-linux/actions/workflows/test.yml/badge.svg)](https://github.com/Clevis22/d20printer-linux/actions/workflows/test.yml)

Experimental Linux support for the NDYIN/Jiuyin D20 57 mm Bluetooth thermal printer (`FCC ID 2BM2R-D20`). It prints directly over Bluetooth Classic RFCOMM and does not require the Nada Print Android app.

> [!IMPORTANT]
> This is an independent, reverse-engineered project, not an official NDYIN or
> Jiuyin driver. It has been validated on one D20 hardware/firmware combination.

The protocol was recovered from Nada Print 2.16.1 and validated against a physical D20 from a Raspberry Pi. The printer uses a 384-dot, 203 dpi head; raw images use the ESC/POS `GS v 0` raster command plus short Nada-specific setup and status commands.

## Current status

- Bluetooth pairing and RFCOMM channel 1: working
- Firmware, serial, battery, cover, paper, temperature, and busy queries: working
- Native 1-bit raster printing: working
- PNG/JPEG/PBM conversion and Floyd-Steinberg dithering: implemented
- Text rendering: implemented
- CUPS/IPP integration: planned

## Requirements

- Linux with BlueZ and native Bluetooth RFCOMM socket support
- Python 3.10 or newer
- A paired and trusted D20 printer

## Raspberry Pi setup

Pair and trust the printer once with BlueZ:

```console
bluetoothctl
scan on
pair AA:BB:CC:DD:EE:FF
trust AA:BB:CC:DD:EE:FF
quit
```

Use your printer's address in place of the example. On Debian/Raspberry Pi OS, install Python and Pillow if needed, then install this project:

```console
sudo apt install python3 python3-pil
python3 -m venv --system-site-packages .venv
.venv/bin/pip install .
```

Set the address for the current shell:

```console
export D20_ADDRESS=AA:BB:CC:DD:EE:FF
```

## Usage

Query status:

```console
d20print info
d20print info --json
```

Print an image, scaled to the 384-dot head:

```console
d20print image photo.png
```

Image tone preparation defaults to `auto`: drawings and scans with a dominant
light background are cleaned as line art, while photographs are contrast
normalized before dithering. Override it when needed:

```console
d20print image drawing.png --image-mode line-art
d20print image portrait.jpg --image-mode photo
d20print image already-prepared.png --image-mode raw
```

Print text:

```console
d20print text "Hello from Linux"
```

Check the cover, paper, temperature, and busy state over the same Bluetooth
connection immediately before a print:

```console
d20print text "Hello from Linux" --preflight
```

Density values range from 1 to 4. The default is 2:

```console
d20print image label.png --density 3 --feed 96
```

Render a job without contacting the printer:

```console
d20print image photo.png --dry-run photo.bin
```

## Safety

The CLI defaults to uncompressed raster mode, moderate density, bounded image height, continuous raster jobs, response timeouts, and explicit print-completion checks. Add `--preflight` to refuse a job when the cover is open, paper is absent, the print head is overheated, or the printer reports itself busy. It does not expose calibration, firmware-update, or arbitrary-command operations.

## Troubleshooting

- `Address already in use` or `Device or resource busy`: close the companion app
  and any other process connected to the printer, then retry. The transport also
  retries transient BlueZ busy errors for five seconds.
- `Host is down`: confirm the printer is awake, paired, and trusted with
  `bluetoothctl info AA:BB:CC:DD:EE:FF`.
- Blank or cropped output: confirm the device is a 384-dot D20 variant and start
  with the default density and feed settings.

## Development

Install the package in a virtual environment and run the tests:

```console
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/python -m unittest discover -s tests -v
```

The test suite uses a fake transport and does not contact a printer.

## Research

See `research/2026-09-11-initial-research.md` and `research/2026-09-11-pi-inventory.md` for the hardware identification, protocol byte map, and validation results.

## License

MIT. See `LICENSE`.
