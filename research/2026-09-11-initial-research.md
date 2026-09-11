# NDYIN / Jiuyin D20 Linux support: initial research

Date: 2026-09-11

## Goal

Make the Zhuhai Jiuyin D20 mini thermal printer usable from a Raspberry Pi and, ultimately, as a normal Linux printer. The first implementation target should be a small command-line program that prints a 1-bit raster image reliably. CUPS integration should come after the wire protocol is proven.

## Facts established from the supplied photos

- Product: Mini Printer, model D20
- Manufacturer: Zhuhai Jiuyin Technology Co., Ltd.
- FCC ID: `2BM2R-D20`
- Canadian certification ID: `34064-D20`
- Paper: 57 mm roll
- Battery: 1300 mAh
- Charging input: 5 V / 2 A
- Companion app: Nada Print
- The printed instructions say to connect from inside Nada Print, not from the phone's Bluetooth Settings screen.
- Manufacturer site: `ndyin.com`; support address printed on the box: `support@ndyin.com`

## High-confidence findings from public records

### Radio and controller

The FCC filing contains two radio test reports for the same product:

- A Bluetooth LE report covering 1M and 2M GFSK operation.
- A Bluetooth Classic/EDR report covering GFSK, pi/4-DQPSK, 8DPSK, 79 hopping channels, and DH1/DH3/DH5 packets.

The filing describes the radio as Bluetooth 5.0, with hardware and software versions both listed as V1.0. This establishes that the hardware is dual-mode: BLE and Bluetooth Classic are both available at the radio/firmware level. It does not by itself prove which transport Nada Print uses for print jobs.

The FCC internal photographs show a JieLi (`JL`) Bluetooth system-on-chip as the main controller and a PCB antenna. The exact part marking is not legible enough in the filing photograph to identify the precise JieLi SKU confidently.

The FCC report groups these model names as using the same circuit and RF module, differing only in name:

`D20, D20A-F, D21, D21A-F, S1-S4, S1Pro, PM230, PM240, PM250, PM260, PM270, PM280, M02, T02`

This family list is especially useful because open-source Linux support already exists for some printers sold as M02 and T02.

### Physical print geometry

The official D20 product page specifies 203 dpi, 15-20 mm/s, and 57 mm paper. Small 57/58 mm pocket printers commonly have a 48 mm printable area, which is 384 dots at 203 dpi. The manufacturer's table appears to swap the media-width and print-width labels, so 384 dots is a working hypothesis, not yet a confirmed D20 parameter.

### Android app

- Google Play package: `com.zhuhaijiuyin.print`
- Developer: Zhuhai Jiuyin Technology / 久印
- The store description says the printer works over Bluetooth and supports offline printing. That strongly suggests the job bytes are generated locally and can be reproduced without a cloud service.

## Protocol hypotheses

These are hypotheses, not findings. We should identify the actual protocol before attempting a full print.

### Hypothesis A: ESC/POS-derived M02/T02 protocol

Why it is plausible:

- Jiuyin's FCC report explicitly includes M02 and T02 in the same circuit/RF family as D20.
- `vivier/phomemo-tools` already supports M02/T02 on Linux over Bluetooth Classic and documents an ESC/POS raster stream.
- Its recognizable job signature includes `1B 40` (initialize), a vendor prefix beginning `1F 11`, and `1D 76 30` raster blocks.

What would confirm it:

- The printer advertises the standard Serial Port Profile UUID `00001101-0000-1000-8000-00805f9b34fb`, and/or
- A Nada Print capture contains the byte sequences above.

### Hypothesis B: common 0x5178 "cat printer" protocol

Why it is plausible:

- This protocol is widely used by inexpensive 384-dot BLE pocket printers.
- It commonly uses BLE service `0000ae30-0000-1000-8000-00805f9b34fb`, TX characteristic `ae01`, RX notification characteristic `ae02`, and frames shaped like `51 78 CMD 00 LEN_LO LEN_HI DATA CRC8 FF`.
- Several known devices in this class use JieLi controllers.

What would confirm it:

- The D20 exposes the `ae30` / `ae01` / `ae02` GATT layout, and/or
- A capture contains the `51 78` header and `FF` terminator.

### Hypothesis C: a Jiuyin-specific protocol

If neither signature appears, the protocol is probably implemented by a proprietary SDK inside Nada Print. The Android APK and one controlled Bluetooth capture should still expose service UUIDs, command framing, raster encoding, checksums, chunking, and status notifications.

## Recommended reverse-engineering sequence

### 1. Inventory the D20 from the Raspberry Pi

Use BlueZ to record:

- Bluetooth advertising name and address
- BLE service and characteristic UUIDs, including flags such as read, notify, write, and write-without-response
- Bluetooth Classic SDP services, especially SPP/RFCOMM channel information
- Whether the USB-C connector exposes a USB data device or is charging-only

This step is read-only. Save raw command output so later firmware or hardware variants can be compared.

### 2. Pull and inspect the exact installed Nada Print APK

Use Android wireless debugging and the installed package rather than an APK mirror:

1. Pair/connect ADB over Wi-Fi.
2. Run `adb shell pm path com.zhuhaijiuyin.print`.
3. Pull the base APK and any split APKs returned by `pm path`.
4. Record package version and SHA-256 hashes.
5. Decompile with JADX and unpack resources/native libraries with apktool or unzip.

Search for:

- `D20`, the sibling model names, and printer-width tables
- 16-bit and 128-bit Bluetooth UUID strings
- `BluetoothGatt`, `writeCharacteristic`, `createRfcommSocketToServiceRecord`, and `00001101`
- byte constants `51 78`, `1B 40`, `1D 76 30`, and CRC lookup tables
- print density, energy, feed, status, firmware-query, and OTA commands
- native `.so` libraries if the protocol is hidden behind JNI

Static inspection may fully answer the protocol question without transmitting anything to the printer.

### 3. Capture a minimal known-good Nada Print session

Android officially supports Bluetooth HCI snoop logging. Enable the developer option, restart Bluetooth, then capture only this short sequence:

1. Power on D20.
2. Open Nada Print.
3. Connect to D20.
4. Print one small, sparse, known bitmap.
5. Disconnect/close the app and immediately collect an ADB bug report.

Use a sparse pattern rather than a solid black field to avoid unnecessary print-head load. A good diagnostic image is 384 pixels wide with isolated left/right edge dots, an 8-pixel ruler, alternating `0xAA`/`0x55` rows, and a small asymmetric marker. It reveals width, bit order, row order, padding, and image orientation in one print.

Extract BTSnoop data from the bug report with Android's `btsnooz.py`, then inspect in Wireshark/tshark. During the capture, disconnect unrelated Bluetooth accessories because an HCI log can include traffic metadata or payloads from other active Bluetooth devices.

### 4. Differential captures

If the first capture is not self-explanatory, make small controlled changes and diff the outgoing payloads:

- same bitmap twice
- one black dot moved by one pixel
- height changed by one row
- density changed by one setting
- feed-only operation

This isolates framing, width/height fields, raster bit order, compression, checksum, and acknowledgements much faster than blind command guessing.

### 5. Implement the smallest safe Linux client

Start with a CLI, not CUPS:

- Input: PNG or PBM
- Render: resize/crop to the confirmed dot width, grayscale, threshold/dither, pack 1 bit per pixel
- Transport: BLE via BlueZ/Bleak if Nada Print uses GATT; otherwise a native Linux RFCOMM socket for Classic SPP
- Protocol: explicit job start, configuration, raster rows/blocks, job end, feed, and status handling
- Safety: maximum dimensions, conservative default energy, bounded retries, timeouts, and no firmware/OTA commands
- Diagnostics: `scan`, `info`, `print --dry-run`, packet hex dump, and capture replay against a file before real transmission

### 6. Add Linux printing integration

After direct printing is stable:

- Add a CUPS raster/filter/backend path for normal Linux applications.
- Optionally expose a small local IPP service so other devices can submit jobs to the Pi.
- Keep the protocol/renderer library independent of CUPS so it remains testable.

## Existing work worth testing, not assuming

1. `vivier/phomemo-tools` - strongest shortcut because it already supports M02/T02 with an ESC/POS-derived raster path and a Linux CUPS backend.
2. `rhnvrm/catprinter` and related CatPrinter implementations - useful if the D20 exposes `ae30/ae01/ae02` and `0x5178` framing.
3. BlueZ and Bleak - appropriate Linux BLE client layers if the transport is GATT.

Do not send the existing projects' test-print commands until the service UUIDs or captured job signature match. Some vendor commands control heating energy, calibration, reset, or firmware update.

## Decision gate for the next phase

The next phase should begin with three artifacts:

1. Raspberry Pi Bluetooth/USB inventory
2. Decompiled exact-version Nada Print APK
3. One minimal BTSnoop capture plus the exact bitmap that produced it

Once those exist, selecting or implementing the Linux protocol should be straightforward and evidence-driven.

## Sources

- FCC filing and exhibits: https://fccid.io/2BM2R-D20
- Official D20 product page: https://ndyin.com/products/d20-inkless-mini-thermal-printer
- Nada Print on Google Play: https://play.google.com/store/apps/details?id=com.zhuhaijiuyin.print
- Android Bluetooth HCI logging: https://source.android.com/docs/core/connect/bluetooth/verifying_debugging
- Android wireless debugging: https://developer.android.com/studio/run/device
- BlueZ GATT characteristic API: https://github.com/bluez/bluez/blob/master/doc/org.bluez.GattCharacteristic.rst
- Phomemo Linux/CUPS driver and M02 protocol notes: https://github.com/vivier/phomemo-tools
- Documented 0x5178 protocol example: https://github.com/rhnvrm/catprinter/blob/master/docs/pd01-protocol.md
