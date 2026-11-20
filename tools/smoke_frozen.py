"""Donmus (onefile) StockWidget icin uc senaryolu duman testi.

Python'un subprocess'unu kullanir: Start-Process'i antivirus/EDR katmanlari
bekletebiliyor; DEVNULL pipe'lar daha ongorulebilir.

Senaryolar:
  A) SW_SMOKE ile acilis: 12 sn sonra kendini kapatir; snapshot.json yazilir,
     %TEMP%'deki 7 gunden eski _MEI klasoru silinir.
  B) Normal acilis + baska surecten `--quit`: calisan kopya temiz kapanir.
  C) Ikinci kopya (argumansiz): sessizce 0 ile cikar, birinci yasar; sonra
     --quit ile birinci kopya kapanir.

Kullanim:
  python -m PyInstaller --noconfirm --clean --distpath build\\test-snap ^
      --workpath build\\work-snap StockWidget-onefile.spec
  python tools/smoke_frozen.py                     # varsayilan exe yolu
  python tools/smoke_frozen.py --exe <yol>         # baska derleme

Not: exe'yi kopyalayip degil oldugu gibi calistirir; TEMP ve SW_DATA_DIR
test basina gecici klasore yonlendirilir, gercek %APPDATA% etkilenmez.
"""
import argparse
import json
import os
import shutil
import subprocess
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build")
DEFAULT_EXE = os.path.join(BUILD, "test-snap", "StockWidget.exe")


def reset(name):
    run = os.path.join(BUILD, name)
    shutil.rmtree(run, ignore_errors=True)
    data = os.path.join(run, "data")
    os.makedirs(data)
    return run, data


def seed(data):
    with open(os.path.join(data, "config.json"), "w", encoding="utf-8") as f:
        json.dump({"symbols": ["AAPL"], "x": 220, "y": 220}, f)


def make_env(run, data, smoke=False):
    env = os.environ.copy()
    env["TEMP"] = run
    env["TMP"] = run
    env["SW_DATA_DIR"] = data
    env["SW_INSTANCE_SUFFIX"] = "smoke"
    env.pop("SW_SMOKE", None)
    if smoke:
        env["SW_SMOKE"] = "1"
    return env


def read_log(data):
    try:
        with open(os.path.join(data, "sw.log"), encoding="utf-8",
                  errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def wait_log(data, marker, seconds):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if marker in read_log(data):
            return True
        time.sleep(0.4)
    return False


def launch(exe, env, args=()):
    return subprocess.Popen(
        [exe] + list(args), env=env, close_fds=True,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL)


def wait_exit(proc, seconds):
    try:
        return proc.wait(timeout=seconds)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)
        return None


def phase_a(exe):
    run, data = reset("tmp-py-a")
    seed(data)
    old = os.path.join(run, "_MEIfake99")
    os.makedirs(old)
    with open(os.path.join(old, "x.txt"), "w", encoding="utf-8") as f:
        f.write("eski")
    past = time.time() - 9 * 24 * 3600
    os.utime(old, (past, past))
    started = time.time()
    proc = launch(exe, make_env(run, data, True))
    rc = wait_exit(proc, 150)
    elapsed = round(time.time() - started, 1)
    assert rc == 0, "A: exit=%r" % (rc,)
    assert not os.path.exists(old), "A: eski _MEI silinmedi"
    snap = os.path.join(data, "snapshot.json")
    assert os.path.exists(snap), "A: snapshot yok"
    with open(snap, encoding="utf-8") as f:
        saved = json.load(f)
    price = saved["quotes"]["AAPL"]["price"]
    bars = len(saved["quotes"]["AAPL"]["spark"])
    assert price > 0 and bars > 1, saved
    print("A OK: exit=0 sure=%ss snapshot=%s bar=%s stale_silindi=True"
          % (elapsed, price, bars))


def phase_b(exe):
    run, data = reset("tmp-py-b")
    seed(data)
    env = make_env(run, data)
    proc = launch(exe, env)
    assert wait_log(data, "pid ", 150), "B: baslangic logu yok"
    time.sleep(2)
    assert proc.poll() is None, "B: ilk kopya erken cikti"
    started = time.time()
    q = launch(exe, env, ["--quit"])
    qrc = wait_exit(q, 150)
    assert qrc == 0, "B: --quit exit=%r" % (qrc,)
    rc = wait_exit(proc, 30)
    elapsed = round(time.time() - started, 1)
    assert rc == 0, "B: calisan kopya --quit ile kapanmadi (exit=%r)" % (rc,)
    assert "\u00e7\u0131k\u0131\u015f" in read_log(data), "B: cikis logu yok"
    print("B OK: --quit exit=0, ilk kopya %ss icinde temiz kapandi" % elapsed)


def phase_c(exe):
    run, data = reset("tmp-py-c")
    seed(data)
    env = make_env(run, data)
    proc = launch(exe, env)
    assert wait_log(data, "pid ", 150), "C: baslangic logu yok"
    time.sleep(2)
    second = launch(exe, env)
    rc2 = wait_exit(second, 150)
    assert rc2 == 0, "C: ikinci kopya exit=%r" % (rc2,)
    time.sleep(2)
    assert proc.poll() is None, "C: birinci kopya da kapandi"
    q = launch(exe, env, ["--quit"])
    assert wait_exit(q, 150) == 0, "C: --quit exit"
    rc1 = wait_exit(proc, 30)
    assert rc1 == 0, "C: birinci kopya kapanmadi (exit=%r)" % (rc1,)
    print("C OK: ikinci kopya sessizce 0 ile cikti, birinci --quit ile kapandi")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--exe", default=DEFAULT_EXE,
                        help="onefile StockWidget.exe yolu")
    args = parser.parse_args()
    exe = os.path.abspath(args.exe)
    assert os.path.exists(exe), "exe yok: %s" % exe
    phase_a(exe)
    phase_b(exe)
    phase_c(exe)
    print("ALL FROZEN SMOKE OK")


if __name__ == "__main__":
    main()
