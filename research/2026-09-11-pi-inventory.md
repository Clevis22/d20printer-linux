# D20 live Raspberry Pi inventory

Date: 2026-09-11

## Host

- OS: Debian GNU/Linux 13.6 (trixie), arm64
- Kernel: `6.18.39+rpt-rpi-2712`
- BlueZ tools: `bluetoothctl`, `btmgmt`, `sdptool`, and `gatttool` present
- BlueZ version reported by `btmgmt`: 5.82
- Bluetooth controller powered with BR/EDR and LE enabled

## D20 identity and pairing state

- Address: public address (value omitted)
- Name/Alias: `D20`
- Device class: `0x00040680`
- BlueZ icon: printer
- Paired: yes
- Bonded: yes
- Trusted: yes
- Live LE RSSI observed: approximately -43 to -49 dBm

The device was initially paired but disconnected. A transport-only Classic connection succeeded. No print bytes were sent.

## Bluetooth Classic

SDP discovery returned:

- Service name: `JL_SPP`
- Service class: Serial Port (`0x1101`)
- RFCOMM channel: 1
- Serial Port Profile version: 1.2

A native Linux RFCOMM socket connected successfully to channel 1. The socket was observed for five seconds without transmitting data; the printer sent no unsolicited banner.

The cached BlueZ service list also contains several audio/telephony profiles, probably defaults inherited from the JieLi Bluetooth firmware rather than useful printer interfaces.

## Bluetooth LE

An LE-only scan found the D20 advertising at the same public address. Direct GATT discovery returned:

| Handle | UUID | Properties | Interpretation |
| --- | --- | --- | --- |
| `0x0001-0x0003` | `1800` | Generic Access | standard service |
| `0x0003` | `2A00` | read | device name value |
| `0x0004-0x0009` | `FF00` | vendor service | BLE data service |
| `0x0006` | `FF01` | read | vendor value; read attempt returned not-readable/empty behavior |
| `0x0008` | `FF02` | write-no-response, write, notify | likely bidirectional print/data characteristic |

The characteristic properties reported for `FF02` were `0x1c`, meaning write-without-response (`0x04`), write (`0x08`), and notify (`0x10`). This layout differs from the common cat-printer `AE30/AE01/AE02` service and is consistent with BLE-UART transports used by several ESC/POS-derived thermal printer families.

Cached advertisement/service metadata also included UUID `AF30`, but it was not present in the GATT database returned by direct discovery. It may be advertisement-only metadata, a separate firmware mode, or a stale cached UUID.

## USB inventory

The Pi currently sees:

- Raspberry Pi root hubs
- Phison USB storage
- Riitek wireless mini keyboard/touchpad

No USB printer-class or USB-serial device corresponding to the D20 was present. The printer appears to be connected by Bluetooth only; the D20's USB-C port is likely charging-only, pending a deliberate cable test.

## Nada Print 2.16.1 static analysis

Wireless ADB connected to an Android 16 test phone. The installed app was:

- Package: `com.zhuhaijiuyin.print`
- Version: `2.16.1` (`versionCode=91`)
- Base APK SHA-256: `1b32070d9a14afd18f8e387a2cff480117b69e924bb708a98cca3d709a00d525`
- arm64 split SHA-256: `97a8d6be9b04b599947b1bf7ab823bde3d6a82d20bedd3e5e5cbe831bdae4aba`
- xhdpi split SHA-256: `1f2e2041c3a56c45fe20a58603a75a01ffe981344fbf9fc256657539dbcdda89`

JADX static analysis confirms that the app's D20 path uses secure Bluetooth Classic RFCOMM with the standard SPP UUID `00001101-0000-1000-8000-00805F9B34FB`. The app opens a `BluetoothSocket`, writes raw byte arrays to its output stream, and parses replies from its input stream. Although the printer also exposes a BLE UART-like service, BLE is not the transport used by this version of Nada Print for the D20.

The app selects its default `NadaProtocol` implementation for `D20`, `D21`, `D80`, `N12`, `N20`, `N80`, and `N12A`. Its model specification gives the D20 a 384-dot / 48 mm print area at 203 dpi.

### Recovered D20 commands

These commands are sent as raw bytes with no wrapper or checksum:

| Purpose | Bytes |
| --- | --- |
| Set density (value clamped to 1-4) | `1F 11 05 02 vv` |
| Set data mode (raw=0, compressed=1) | `1F 11 05 35 vv` |
| Query firmware version | `1F 11 05 07` |
| Query serial number | `1F 11 05 09` |
| Query battery | `1F 11 05 08` |
| Query cover state | `1F 11 05 12` |
| Query paper state | `1F 11 05 11` |
| Query shutdown time | `1F 11 05 0E` |
| Query temperature | `1F 11 05 13` |
| Query busy state | `1F 11 05 2F` |
| Paper calibration | `1F 11 05 16` |
| Set paper type | `1B 4E 06 0A vv` |
| Set power-off time | `1B 4E 06 07 vv` |

Raw raster data uses the standard ESC/POS `GS v 0` form:

`1D 76 30 00 xL xH yL yH <row-major 1bpp pixels>`

Here `x` is bytes per row and `y` is the image height. The app packs each row left-to-right, most-significant bit first, and treats luminance below 128 as black. For the D20, a full-width row is 384 dots / 8 = 48 bytes. Nada Print first sends data-mode and paper/density configuration commands, then sends one raster block per page/image. It can optionally compress raster data in 4096-byte source chunks through a native `nCompress` routine, but explicitly supports uncompressed mode, so a Linux implementation does not need to reproduce that compression.

Replies are compact and do not use the outgoing `1F 11 05` prefix. The recovered parser recognizes status selectors including firmware (`07`, followed by three version bytes), serial (`08`, followed by 15 ASCII bytes), battery (`04`), cover (`05`), paper (`06`), temperature (`03`), print completion (`0F`), and busy/idle (`38`). A live query probe is needed to record the exact D20 response values and confirm whether replies arrive individually or coalesced.

### Live query validation

The read-only probe in `tools/d20_probe.py` connected from the Pi to RFCOMM channel 1 and received one terminated response for every command:

| Query | Transmitted | Received | Interpretation |
| --- | --- | --- | --- |
| Firmware | `1F 11 05 07` | `1C 07 01 00 00 0D` | firmware 1.0.0 |
| Serial | `1F 11 05 09` | `1C 08 <15 ASCII bytes> 0D` | device serial (value omitted) |
| Battery | `1F 11 05 08` | `1C 04 46 0D` | 70 percent |
| Cover | `1F 11 05 12` | `1C 05 98 0D` | closed (`99` means open) |
| Paper | `1F 11 05 11` | `1C 06 89 0D` | paper present (`88` means absent) |
| Shutdown | `1F 11 05 0E` | `1C 09 00 0D` | setting value 0 |
| Temperature | `1F 11 05 13` | `1C 03 A8 0D` | normal (`A9` means overheated) |
| Busy | `1F 11 05 2F` | `1C 38 0D` | idle |

This establishes the response frame as `1C <selector> [payload] 0D` for this firmware. Nada Print also tolerates `1A` as a leading marker, probably for sibling models or older firmware.

### Relationship to the existing Phomemo driver

`vivier/phomemo-tools` is useful for its renderer and CUPS integration, and it agrees on 384 dots, 203 dpi, Classic RFCOMM channel 1, and `GS v 0` raster encoding. It is not wire-compatible without changes: its M02 vendor commands omit the D20's `05` byte (for example, M02 density `1F 11 02 04` versus D20 density `1F 11 05 02 04`), and its documented replies begin with `1A` rather than the D20's observed `1C`. A small D20-native CLI sharing the same general raster approach is therefore lower risk than pretending this unit is an M02.

### First native Linux print

`tools/d20_test_print.py` generated a 384 by 96 dot, 1-bit diagnostic pattern with 475 black dots (1.289 percent coverage). It sent:

1. Paper type 0: `1B 4E 06 0A 00`
2. Lowest supported density: `1F 11 05 02 01`
3. Raw/uncompressed mode: `1F 11 05 35 00`
4. A 4,616-byte `GS v 0` raster block
5. A 3,080-byte blank raster block for 64-dot paper feed

The D20 returned `1C 0F 0C 0D` after each raster block. Nada Print's recovered parser defines selector `0F` with value `0C` as successful print completion. Follow-up queries reported paper present (`1C 06 89 0D`), normal temperature (`1C 03 A8 0D`), and idle (`1C 38 0D`). This proves native Linux printing from the Raspberry Pi end to end without Nada Print.

Visual inspection of the physical strip confirmed both full-width edge lines, the intended top-left to bottom-right diagonal, and all three asymmetric registration boxes in their expected positions. The printed aspect ratio also matches 384 by 96 dots. Therefore the confirmed raw raster geometry is:

- 384 dots / 48 bytes per row
- rows transmitted top to bottom
- pixels transmitted left to right
- most-significant bit is the leftmost pixel in each byte
- no rotation or mirroring required
- density 1 is usable for thin diagnostic marks

### Packaged Linux client

The repository now contains an installable Python package and `d20print` command. On the Raspberry Pi it passes ten protocol, print-pipeline, bit-order, scaling, and text-rendering tests. The installed CLI successfully queried the real D20 and printed a 384 by 72 dot text label at density 2. Current commands support printer status, scaled/dithered image printing, text rendering, adjustable density/feed, and a no-hardware dry-run output.

## Updated protocol assessment

The print protocol and primary transport are now identified: ESC/POS raster plus short Nada vendor commands over Classic RFCOMM `JL_SPP`, channel 1.

The discovery evidence lowers the probability of the `0x5178` cat-printer protocol because that family normally exposes service `AE30` and write characteristic `AE01`.

The BLE `FF00`/`FF02` interface remains interesting as a possible alternate transport, but it is no longer required for first Linux support. The common `0x5178` cat-printer hypothesis is ruled out for the app's D20 path.

## Next evidence needed

1. Implement a Linux PNG/PBM-to-D20 command-line client.
2. Add CUPS or driverless IPP integration after the CLI is reliable.
3. Capture Nada Print HCI traffic only if later behavior differs from the recovered static protocol.
