"""환경 진단 — 앱을 띄우기 전에 위험 구간만 따로 찍어본다.

실행:  py -3 pyserver\\check.py      (또는 진단.bat 더블클릭)

여기서 통과하면 poshdeck.bat 도 뜰 가능성이 높다.
실패하면 어느 단계에서 막혔는지 그대로 보인다.
"""
import os
import platform
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

OK, NO, WARN = "  [ OK ]", "  [실패]", "  [주의]"
problems = []


def head(t):
    print()
    print(t)
    print("-" * 64)


def fail(msg, hint=""):
    print(NO, msg)
    if hint:
        print("        →", hint)
    problems.append(msg)


def main():
    print("=" * 64)
    print("  PoshDeck 환경 진단")
    print("=" * 64)

    # 1. 파이썬 ────────────────────────────────────────────
    head("1. 파이썬")
    v = sys.version_info
    print(f"  버전: {platform.python_version()}  ({sys.executable})")
    if v < (3, 8):
        fail(f"파이썬 3.8 이상이 필요합니다 (현재 {platform.python_version()})")
    else:
        print(OK, "3.8 이상")

    # 2. 운영체제 ──────────────────────────────────────────
    head("2. 운영체제")
    print(f"  {platform.system()} {platform.release()}  ({platform.version()})")
    is_win = sys.platform == "win32"
    if is_win:
        try:
            build = int(platform.version().split(".")[2])
            if build < 17763:
                fail(f"ConPTY 는 Windows 10 1809(빌드 17763) 이상이 필요합니다 (현재 빌드 {build})",
                     "Node 백엔드 + node-pty 로만 가능합니다")
            else:
                print(OK, f"빌드 {build} — ConPTY 요구사항 충족")
        except (IndexError, ValueError):
            print(WARN, "빌드 번호를 읽지 못했습니다. 그냥 진행합니다")
    else:
        print(WARN, "윈도우가 아닙니다. 개발용 POSIX PTY 로 검사합니다")

    # 3. ConPTY ────────────────────────────────────────────
    head("3. 터미널 엔진")
    if is_win:
        try:
            import ptyconpty  # noqa: F401
            print(OK, "kernel32.CreatePseudoConsole 을 찾았습니다")
        except ImportError as e:
            fail(f"ConPTY 를 쓸 수 없습니다: {e}")
            return report()
        except Exception as e:
            fail(f"ConPTY 준비 중 오류: {type(e).__name__}: {e}")
            return report()
    else:
        import ptyposix  # noqa: F401
        print(OK, "POSIX PTY 사용 가능")

    # 4. 셸 찾기 ───────────────────────────────────────────
    head("4. 셸")
    import sessions
    for kind in (["pwsh", "powershell", "cmd"] if is_win else ["pwsh"]):
        info = sessions.resolve_shell(kind)
        target = info.get("cmdline") or " ".join(info.get("argv", []))
        exe = target.split('"')[1] if target.startswith('"') else target.split()[0]
        exists = os.path.exists(exe) or not os.path.isabs(exe)
        print(f"  {info['label']:<22} {exe}")
        print((OK if exists else WARN), "찾음" if exists else "이 경로에는 없습니다 (PATH 에 있을 수도 있습니다)")

    # 5. 실제로 띄워보기 ───────────────────────────────────
    head("5. 셸을 실제로 띄워 명령 주고받기  ← 가장 중요한 검사")
    shell = "pwsh" if is_win else "pwsh"
    got = []
    try:
        s = sessions.spawn("selfcheck", os.path.expanduser("~"), shell, 80, 24)
        s.attach(lambda m: got.append(m))
        print(f"  {s.shell_label} 세션을 띄웠습니다. 응답을 기다립니다...")
        time.sleep(1.5)
        s.write("echo POSHDECK-SELFCHECK-OK\r")
        for _ in range(60):                                # 최대 6초
            time.sleep(0.1)
            if any(m["t"] == "out" and "POSHDECK-SELFCHECK-OK" in m["d"] for m in got[1:]):
                break
        out = "".join(m["d"] for m in got if m["t"] == "out")
        if "POSHDECK-SELFCHECK-OK" in out.replace("echo POSHDECK-SELFCHECK-OK", "", 1):
            print(OK, "명령을 보내고 결과를 돌려받았습니다")
            print(OK, f"현재 폴더 추적: {s.cwd}")
            if is_win and not any(m["t"] == "state" for m in got):
                print(WARN, "프롬프트 상태 표시가 안 옵니다 — '실행 중' 표시가 정확하지 않을 수 있습니다")
        elif out.strip():
            fail("셸은 떴지만 명령 결과가 돌아오지 않았습니다")
            print("        받은 출력(앞 300자):")
            print("       ", repr(out[:300]))
        else:
            fail("셸에서 아무 출력도 오지 않았습니다")
        sessions.kill("selfcheck")
    except Exception as e:
        import traceback
        fail(f"셸을 띄우지 못했습니다: {type(e).__name__}: {e}")
        print()
        traceback.print_exc()

    # 6. 포트 ──────────────────────────────────────────────
    head("6. 포트")
    for port in (7788, 7789):
        with socket.socket() as sk:
            try:
                sk.bind(("127.0.0.1", port))
                print(OK, f"{port} 사용 가능")
                break
            except OSError:
                print(WARN, f"{port} 은(는) 이미 쓰이고 있습니다")

    # 7. 파일 ──────────────────────────────────────────────
    head("7. 파일")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for rel in ["web/index.html", "web/app.js", "web/vendor/xterm.js", "web/vendor/xterm.css"]:
        p = os.path.join(root, rel.replace("/", os.sep))
        print((OK if os.path.isfile(p) else NO), rel)
        if not os.path.isfile(p):
            problems.append(f"{rel} 없음")
    try:
        d = sessions.data_dir()
        test = os.path.join(d, ".writetest")
        with open(test, "w") as f:
            f.write("x")
        os.remove(test)
        print(OK, f"설정 폴더 쓰기 가능: {d}")
    except OSError as e:
        fail(f"설정 폴더에 쓸 수 없습니다: {e}")

    report()


def report():
    print()
    print("=" * 64)
    if problems:
        print("  결과: 문제가 있습니다")
        for p in problems:
            print("   - " + p)
        print()
        print("  위 내용을 그대로 복사해서 알려주시면 바로 잡겠습니다.")
    else:
        print("  결과: 모두 통과했습니다. poshdeck.bat 을 실행하세요.")
    print("=" * 64)
    print()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        print()
        print("진단 도중 예상치 못한 오류:")
        traceback.print_exc()
    if sys.platform == "win32":
        input("\n엔터를 누르면 닫힙니다...")
