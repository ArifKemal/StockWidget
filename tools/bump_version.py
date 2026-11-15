"""Sürüm numarasını kaynak dosyalara yazar (CI ve yerel derleme için).

Kullanım: python tools/bump_version.py 1.2.3
"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    if len(sys.argv) != 2:
        print("usage: python tools/bump_version.py <version>")
        return 2
    version = sys.argv[1].strip().lstrip("v")
    if not re.fullmatch(r"\d+(\.\d+){0,3}", version):
        print("invalid version: %s" % sys.argv[1])
        return 2
    parts = [int(p) for p in version.split(".")]
    while len(parts) < 4:
        parts.append(0)
    tuple_s = "(%s)" % ", ".join(str(p) for p in parts)

    app_path = os.path.join(ROOT, "stock_widget.py")
    with io.open(app_path, encoding="utf-8", newline="") as f:
        src = f.read()
    src, count = re.subn(r'APP_VERSION = "[^"]*"',
                         'APP_VERSION = "%s"' % version, src, count=1)
    if count != 1:
        print("APP_VERSION line not found")
        return 1
    with io.open(app_path, "w", encoding="utf-8", newline="") as f:
        f.write(src)

    vi_path = os.path.join(ROOT, "version_info.txt")
    with io.open(vi_path, encoding="utf-8", newline="") as f:
        vi = f.read()
    vi = re.sub(r"filevers=\([^)]*\)", "filevers=%s" % tuple_s, vi)
    vi = re.sub(r"prodvers=\([^)]*\)", "prodvers=%s" % tuple_s, vi)
    vi = re.sub(r"StringStruct\(u'FileVersion', u'[^']*'\)",
                "StringStruct(u'FileVersion', u'%s')" % version, vi)
    vi = re.sub(r"StringStruct\(u'ProductVersion', u'[^']*'\)",
                "StringStruct(u'ProductVersion', u'%s')" % version, vi)
    with io.open(vi_path, "w", encoding="utf-8", newline="") as f:
        f.write(vi)

    print("version %s written" % version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
