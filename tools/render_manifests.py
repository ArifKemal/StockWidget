#!/usr/bin/env python3
"""Winget ve Scoop şablonlarını release asset bilgileriyle işler.

Örnek (PowerShell, hash değerleri Get-FileHash ile alınabilir):

    python tools/render_manifests.py --version 1.2.3 --output-dir packaging/out `
      --setup-url https://example.invalid/StockWidget-1.2.3-setup.exe `
      --setup-sha256 <64-karakterlik-setup-sha256> `
      --portable-url https://example.invalid/StockWidget-1.2.3-portable.zip `
      --portable-sha256 <64-karakterlik-portable-sha256>

URL'lerin sonunda release ile aynı asset adları bulunmalıdır. Bu betik yalnızca
yerel dosya üretir; winget-pkgs veya Scoop bucket deposuna PR göndermez.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
VERSION_RE = re.compile(r"^[0-9]+(?:\.[0-9]+){0,3}$")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
PLACEHOLDER_RE = re.compile(r"{{[A-Z0-9_]+}}")


def normalize_sha256(value: str, *, upper: bool) -> str:
    """SHA256 değerini doğrular ve hedef manifestin biçimine çevirir."""
    if not SHA256_RE.fullmatch(value):
        raise ValueError("SHA256 tam olarak 64 onaltılık karakter olmalıdır")
    return value.upper() if upper else value.lower()


def validate_asset_url(url: str, filename: str) -> str:
    """HTTPS URL'sinin beklenen release asset'ine işaret ettiğini doğrular."""
    if any(char.isspace() for char in url) or any(
        char in url for char in "\"'\\"
    ):
        raise ValueError(f"URL boşluk, tırnak veya ters eğik çizgi içeremez: {url}")
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"Geçerli bir HTTPS URL'si gerekli: {url}")
    if parsed.path.rsplit("/", 1)[-1] != filename:
        raise ValueError(f"URL şu asset ile bitmelidir: {filename}")
    return url


def replace_placeholders(template: str, values: dict[str, str]) -> str:
    """Bilinen yer tutucuları değiştirir; eksik değer bırakılmasını engeller."""
    for name, value in values.items():
        template = template.replace("{{" + name + "}}", value)
    unresolved = PLACEHOLDER_RE.search(template)
    if unresolved:
        raise ValueError(f"Çözümlenmemiş yer tutucu: {unresolved.group(0)}")
    return template


def write_text(path: Path, content: str) -> None:
    """UTF-8 ve LF kullanarak üst dizinleriyle birlikte dosya yazar."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(content)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", required=True, help="Sürüm; v öneki olmadan")
    parser.add_argument("--setup-url", required=True, help="Setup EXE HTTPS URL'si")
    parser.add_argument("--setup-sha256", required=True, help="Setup EXE SHA256")
    parser.add_argument(
        "--portable-url", required=True, help="Portatif ZIP HTTPS URL'si"
    )
    parser.add_argument("--portable-sha256", required=True, help="Portatif ZIP SHA256")
    parser.add_argument(
        "--output-dir", required=True, type=Path, help="Üretilecek manifestlerin kökü"
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if not VERSION_RE.fullmatch(args.version):
            raise ValueError("Sürüm 1-4 sayısal bölümden oluşmalı ve v öneki olmamalı")
        values = {
            "VERSION": args.version,
            "SETUP_URL": validate_asset_url(
                args.setup_url, f"StockWidget-{args.version}-setup.exe"
            ),
            "SETUP_SHA256": normalize_sha256(args.setup_sha256, upper=True),
            "PORTABLE_URL": validate_asset_url(
                args.portable_url, f"StockWidget-{args.version}-portable.zip"
            ),
            "PORTABLE_SHA256": normalize_sha256(args.portable_sha256, upper=False),
        }

        winget_template = (
            ROOT / "packaging" / "winget" / "ArifKemal.StockWidget.yaml.in"
        ).read_text(encoding="utf-8")
        scoop_template = (
            ROOT / "packaging" / "scoop" / "stockwidget.json.in"
        ).read_text(encoding="utf-8")

        winget = replace_placeholders(winget_template, values)
        scoop = replace_placeholders(scoop_template, values)
        scoop = "\n".join(
            line
            for line in scoop.splitlines()
            if not line.lstrip().startswith("//")
        ) + "\n"
        json.loads(scoop)

        winget_output = (
            args.output_dir / "winget" / "ArifKemal.StockWidget.yaml"
        )
        scoop_output = args.output_dir / "scoop" / "stockwidget.json"
        write_text(winget_output, winget)
        write_text(scoop_output, scoop)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))

    print(winget_output)
    print(scoop_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
