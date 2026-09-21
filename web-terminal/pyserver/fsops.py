"""파일 작업 — 탐색기가 쓰는 것들."""
import os
import shutil
import subprocess
import sys

IS_WIN = sys.platform == "win32"
CREATE_NO_WINDOW = 0x08000000 if IS_WIN else 0


def _run_ps(script):
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                   creationflags=CREATE_NO_WINDOW, capture_output=True)


def guard(path, roots):
    """roots 가 비어 있으면 제한 없음. 좁히려면 config.json 의 roots 에 폴더를 넣는다."""
    if not path:
        raise ValueError("경로가 없습니다")
    abs_path = os.path.abspath(os.path.expanduser(path))
    if not roots:
        return abs_path
    for r in roots:
        root = os.path.abspath(r)
        if abs_path == root or abs_path.startswith(root + os.sep):
            return abs_path
    raise PermissionError(f"허용되지 않은 경로입니다: {abs_path}")


def drives():
    if not IS_WIN:
        return [{"name": "/", "path": "/"}, {"name": "~", "path": os.path.expanduser("~")}]
    out = []
    for c in range(ord("A"), ord("Z") + 1):
        letter = f"{chr(c)}:\\"
        if os.path.exists(letter):
            out.append({"name": f"{chr(c)}:", "path": letter})
    return out


def listdir(path):
    entries = []
    with os.scandir(path) as it:
        for e in it:
            try:
                st = e.stat(follow_symlinks=False)
                is_dir = e.is_dir()
            except OSError:
                continue                                   # 권한 없는 항목은 건너뛴다
            entries.append({"name": e.name, "dir": is_dir, "size": st.st_size,
                            "mtime": st.st_mtime * 1000, "hidden": e.name.startswith(".")})
    entries.sort(key=lambda r: (not r["dir"], r["name"].lower()))
    parent = os.path.dirname(path)
    return {"path": path, "parent": None if parent == path else parent, "entries": entries}


def mkdir(parent, name):
    target = os.path.join(parent, name or "새 폴더")
    os.mkdir(target)
    return target


def new_file(parent, name):
    target = os.path.join(parent, name or "새 파일.txt")
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(fd)
    return target


def rename(src, new_name):
    dst = os.path.join(os.path.dirname(src), new_name)
    os.rename(src, dst)
    return dst


def remove(path, permanent=False):
    """기본은 휴지통. permanent 를 줘야 진짜 지운다."""
    if permanent or not IS_WIN:
        shutil.rmtree(path) if os.path.isdir(path) else os.remove(path)
        return {"path": path, "permanent": True}
    quoted = path.replace("'", "''")
    _run_ps(
        "Add-Type -AssemblyName Microsoft.VisualBasic; "
        f"$p = '{quoted}'; "
        "if (Test-Path -LiteralPath $p -PathType Container) { "
        "[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory($p,'OnlyErrorDialogs','SendToRecycleBin') } "
        "else { [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile($p,'OnlyErrorDialogs','SendToRecycleBin') }")
    return {"path": path, "permanent": False}


def _unique(dst):
    if not os.path.exists(dst):
        return dst
    base, ext = os.path.splitext(dst)
    for i in range(2, 1000):
        cand = f"{base} ({i}){ext}"
        if not os.path.exists(cand):
            return cand
    return f"{base} ({os.getpid()}){ext}"


def transfer(sources, dest_dir, move=False):
    done = []
    for src in sources:
        dst = _unique(os.path.join(dest_dir, os.path.basename(src)))
        if move:
            shutil.move(src, dst)
        elif os.path.isdir(src):
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        done.append(dst)
    return done


# ── 윈도우 셸 동작 ──────────────────────────────────────────
def open_default(path):
    if IS_WIN:
        os.startfile(path)                                  # noqa: S606 — 사용자가 고른 파일
    else:
        subprocess.Popen(["xdg-open", path])


def reveal(path):
    if IS_WIN:
        subprocess.Popen(["explorer.exe", "/select,", path])
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path)])


def properties(path):
    if not IS_WIN:
        return
    folder = os.path.dirname(path).replace("'", "''")
    leaf = os.path.basename(path).replace("'", "''")
    subprocess.Popen(["powershell.exe", "-NoProfile", "-NonInteractive", "-STA", "-Command",
                      f"$s = New-Object -ComObject Shell.Application; $f = $s.Namespace('{folder}'); "
                      f"$i = $f.ParseName('{leaf}'); if ($i) {{ $i.InvokeVerb('Properties') }}"],
                     creationflags=CREATE_NO_WINDOW)
