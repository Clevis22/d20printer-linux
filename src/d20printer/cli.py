"""Command-line interface for the D20 printer."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path

from .imaging import prepare_image, render_text
from .printer import D20Printer, PrinterStatus
from .protocol import raster_command


def _nonnegative(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return parsed


def _positive(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _add_print_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--density", type=int, choices=range(1, 5), default=2)
    parser.add_argument("--feed", type=_nonnegative, default=64, metavar="ROWS")
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="check cover, paper, temperature, and busy state before printing",
    )
    parser.add_argument(
        "--dry-run",
        type=Path,
        metavar="FILE",
        help="write the raster command to FILE without connecting",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="d20print")
    parser.add_argument(
        "--address",
        default=os.environ.get("D20_ADDRESS"),
        help="Bluetooth MAC address (or set D20_ADDRESS)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    info = subparsers.add_parser("info", help="query printer status")
    info.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    image = subparsers.add_parser("image", help="print an image file")
    image.add_argument("path", type=Path)
    image.add_argument("--threshold", type=int, choices=range(256), default=128)
    image.add_argument("--no-dither", action="store_true")
    image.add_argument(
        "--image-mode",
        choices=("auto", "line-art", "photo", "raw"),
        default="auto",
        help="tone preparation before 1-bit conversion (default: auto)",
    )
    image.add_argument("--max-height", type=_positive, default=8192)
    _add_print_options(image)

    text = subparsers.add_parser("text", help="render and print text")
    text.add_argument("value")
    text.add_argument("--font", type=Path)
    text.add_argument("--font-size", type=_positive, default=28)
    _add_print_options(text)
    return parser


def _required_address(parser: argparse.ArgumentParser, value: str | None) -> str:
    if not value:
        parser.error("--address is required (or set D20_ADDRESS)")
    return value


def _print_status(status: PrinterStatus) -> None:
    for name, value in (
        ("Firmware", status.firmware),
        ("Serial", status.serial),
        ("Battery", f"{status.battery_percent}%" if status.battery_percent is not None else None),
        ("Cover", "open" if status.cover_open else "closed" if status.cover_open is not None else None),
        ("Paper", "present" if status.paper_present else "absent" if status.paper_present is not None else None),
        ("Temperature", "normal" if status.temperature_normal else "overheated" if status.temperature_normal is not None else None),
        ("Busy", status.busy),
    ):
        print(f"{name:12s} {value if value is not None else 'unknown'}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "info":
            address = _required_address(parser, args.address)
            with D20Printer(address) as printer:
                status = printer.status()
            if args.json:
                print(json.dumps(asdict(status), sort_keys=True))
            else:
                _print_status(status)
            return 0

        if args.command == "image":
            raster = prepare_image(
                args.path,
                dither=not args.no_dither,
                threshold=args.threshold,
                max_height=args.max_height,
                image_mode=args.image_mode,
            )
        else:
            raster = render_text(args.value, font=args.font, font_size=args.font_size)

        if args.dry_run:
            args.dry_run.write_bytes(raster_command(raster))
            print(f"wrote {args.dry_run} ({raster.width}x{raster.height})")
            return 0

        address = _required_address(parser, args.address)
        with D20Printer(address) as printer:
            if args.preflight:
                printer.preflight()
            printer.print_raster(raster, density=args.density, feed_rows=args.feed)
        print(f"printed {raster.width}x{raster.height} at density {args.density}")
        return 0
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(1, f"d20print: error: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
