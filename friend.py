"""Диагностика сервера и удалённый терминал для /utcp: CPU, RAM, диск, GPU + sshx/tmate.

Порядок поднятия терминала: системный sshx → скачивание sshx (S3, musl-статика,
порт 443) → системный tmate → статический tmate (GitHub). Всё скачивается в
папку данных (на botdepo это /data) и запускается оттуда — установка в систему
и root не нужны: файловая система хостинга вне /data только для чтения.
Каждая неудача попадает в диагностику для админа.
"""
import os
import platform
import shutil
import subprocess
import tarfile
import time
import urllib.parse
import urllib.request

import storage

sshx_binary_url = "https://s3.amazonaws.com/sshx/sshx-{arch}-unknown-linux-musl.tar.gz"
tmate_static_url = "https://github.com/tmate-io/tmate/releases/download/2.4.0/tmate-2.4.0-static-linux-{arch}.tar.xz"
sshx_arches = {"x86_64": "x86_64", "amd64": "x86_64", "aarch64": "aarch64", "arm64": "aarch64"}
tmate_arches = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64v8", "arm64": "arm64v8", "armv7l": "arm32v7", "i686": "i386"}
bin_dir = storage.data_dir / "bin"
session_name = "botfriend"
terminal_manual_hint = (
    "Поднять сессию автоматически не удалось. Выполни на сервере вручную:\n"
    "curl -fsSL https://sshx.io/get | sh -s run\n"
    "curl -fsSL https://get.tmate.io/tmate | sh && tmate"
)


def _run(command: str, timeout: int = 180) -> tuple:
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)
        return result.returncode == 0, (result.stdout + result.stderr).strip()
    except (OSError, subprocess.TimeoutExpired):
        return False, ""


def _cpu_fields() -> list:
    with open("/proc/stat") as stat_file:
        return [int(value) for value in stat_file.readline().split()[1:]]


def cpu_usage() -> float:
    before = _cpu_fields()
    time.sleep(0.3)
    after = _cpu_fields()
    before_idle = before[3] + before[4]
    after_idle = after[3] + after[4]
    total_delta = sum(after) - sum(before)
    if total_delta <= 0:
        return 0.0
    return (1.0 - (after_idle - before_idle) / total_delta) * 100.0


def memory_usage() -> tuple:
    values = {}
    with open("/proc/meminfo") as meminfo_file:
        for line in meminfo_file:
            key, _, rest = line.partition(":")
            values[key] = int(rest.split()[0]) * 1024
    return values["MemTotal"] - values["MemAvailable"], values["MemTotal"]


def disk_usage() -> tuple:
    usage = shutil.disk_usage("/")
    return usage.used, usage.total


def gpu_report() -> str:
    if not shutil.which("nvidia-smi"):
        return "не обнаружен"
    ok, output = _run("nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits", 30)
    if not ok or not output:
        return "не обнаружен"
    cards = []
    for row in output.splitlines():
        name, memory_used, memory_total, load = [part.strip() for part in row.split(",")]
        cards.append(f"{name} • {memory_used}/{memory_total} МБ • {load}%")
    return "\n".join(cards)


def _gib(size_bytes: int) -> float:
    return size_bytes / 1024 ** 3


def _share(used: int, total: int) -> str:
    if total <= 0:
        return "0%"
    return f"{used / total * 100:.0f}%"


def system_report() -> str:
    ram_used, ram_total = memory_usage()
    disk_used, disk_total = disk_usage()
    load1, load5, load15 = os.getloadavg()
    lines = [
        f"🖥 Платформа: {platform.system()} {platform.release()} ({platform.machine()})",
        f"🧠 CPU: {os.cpu_count()} ядер • загрузка {cpu_usage():.1f}% • load {load1:.2f}/{load5:.2f}/{load15:.2f}",
        f"💾 RAM: {_gib(ram_used):.1f} / {_gib(ram_total):.1f} ГБ ({_share(ram_used, ram_total)})",
        f"📦 Диск: {_gib(disk_used):.1f} / {_gib(disk_total):.1f} ГБ ({_share(disk_used, disk_total)})",
        f"🎮 GPU: {gpu_report()}",
    ]
    return "\n".join(lines)


def terminal_session() -> str:
    notes = []
    sshx_path, reason = _ensure_sshx()
    if sshx_path:
        link, reason = _sshx_link(sshx_path)
        if link:
            return "🔐 Удалённый терминал (sshx):\n" + link
    if reason:
        notes.append("sshx: " + reason)
    tmate_path, reason = _ensure_tmate()
    if tmate_path:
        link, reason = _tmate_link(tmate_path)
        if link:
            return "🔐 Удалённый терминал (tmate):\n" + link
    if reason:
        notes.append("tmate: " + reason)
    body = "\n".join("• " + note for note in notes)
    return "🌐 Удалённый терминал\n\n" + (body + "\n\n" if body else "") + terminal_manual_hint


def _download(url: str, target) -> bool:
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "tg-bot-friend"})
        with urllib.request.urlopen(request, timeout=30) as response, open(target, "wb") as output:
            output.write(response.read())
        return True
    except OSError:
        return False


def _extract(archive_path, destination, name: str) -> str:
    try:
        with tarfile.open(archive_path) as archive:
            archive.extractall(destination)
    except (OSError, tarfile.TarError):
        return ""
    for candidate in sorted(destination.rglob(name)):
        if candidate.is_file():
            candidate.chmod(0o755)
            return str(candidate)
    return ""


def _fetch_binary(url: str, name: str, archive_name: str) -> tuple:
    host = urllib.parse.urlsplit(url).hostname
    os.makedirs(bin_dir, exist_ok=True)
    archive_path = bin_dir / archive_name
    if not _download(url, archive_path):
        return "", f"не скачался — хостинг, вероятно, не пускает к {host}"
    binary = _extract(archive_path, bin_dir, name)
    if not binary:
        return "", "скачался, но не распаковался"
    return binary, ""


def _ensure_sshx() -> tuple:
    found = shutil.which("sshx")
    if found:
        return found, ""
    arch = sshx_arches.get(platform.machine())
    if not arch:
        return "", f"архитектура {platform.machine()} не поддерживается"
    return _fetch_binary(sshx_binary_url.format(arch=arch), "sshx", "sshx.tar.gz")


def _ensure_tmate() -> tuple:
    found = shutil.which("tmate")
    if found:
        return found, ""
    arch = tmate_arches.get(platform.machine())
    if not arch:
        return "", f"архитектура {platform.machine()} не поддерживается"
    return _fetch_binary(tmate_static_url.format(arch=arch), "tmate", "tmate.tar.xz")


def _tmate_format(binary: str, template: str) -> str:
    try:
        result = subprocess.run([binary, "display", "-p", template], capture_output=True, text=True, timeout=30)
        return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _tmate_link(binary: str) -> tuple:
    try:
        subprocess.run([binary, "new-session", "-d", "-s", session_name], capture_output=True, timeout=60)
    except OSError:
        return "", "бинарник не запустился — возможно, на разделе с данными запрет exec"
    except subprocess.TimeoutExpired:
        return "", "сессия не стартовала"
    for _ in range(40):
        time.sleep(0.5)
        ssh_line = _tmate_format(binary, "#{tmate_ssh}")
        if ssh_line.startswith("ssh "):
            lines = [f"SSH: {ssh_line}"]
            web_line = _tmate_format(binary, "#{tmate_web}")
            if web_line:
                lines.append(f"Веб: {web_line}")
            return "\n".join(lines), ""
    return "", "сессия не поднялась за 20 секунд — похоже, хостинг закрывает исходящий порт 22"


def _sshx_link(binary: str) -> tuple:
    try:
        process = subprocess.Popen(
            [binary],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
    except OSError:
        return "", "бинарник не запустился — возможно, на разделе с данными запрет exec"
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        line = process.stdout.readline()
        if not line:
            time.sleep(0.3)
            continue
        if "https://sshx.io/v1/" in line:
            return line.strip(), ""
    return "", "ссылки не дождался за 30 секунд — проверь, пускает ли хостинг к sshx.io (порт 443)"
