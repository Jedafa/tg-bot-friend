"""Диагностика сервера и удалённый терминал для /utcp: CPU, RAM, диск, GPU + tmate/sshx.

Порядок поднятия терминала: готовый tmate → apt → скрипт get.tmate.io →
статический бинарник tmate → sshx через sshx.io/get. Результат видит только админ.
"""
import os
import platform
import shutil
import subprocess
import tarfile
import time
import urllib.request
from pathlib import Path

sshx_installer_url = "https://sshx.io/get"
tmate_installer_url = "https://get.tmate.io/tmate"
tmate_static_url = "https://github.com/tmate-io/tmate/releases/download/2.4.0/tmate-2.4.0-static-linux-amd64.tar.xz"
bin_dir = Path(__file__).resolve().parent / "bin"
session_name = "botfriend"
terminal_manual_hint = (
    "Поднять сессию автоматически не удалось. Выполни на сервере вручную:\n"
    "curl -fsSL https://get.tmate.io/tmate | sh && tmate\n"
    "curl -fsSL https://sshx.io/get | sh && sshx"
)


def _run(command: str, timeout: int = 180) -> tuple:
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)
        return result.returncode == 0, (result.stdout + result.stderr).strip()
    except (OSError, subprocess.TimeoutExpired):
        return False, ""


def _sudo_prefix() -> str:
    return "" if os.geteuid() == 0 else "sudo -n "


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
    tmate_path = _ensure_tmate()
    if tmate_path:
        link = _tmate_link(tmate_path)
        if link:
            return "🔐 Удалённый терминал (tmate):\n" + link
    sshx_path = _ensure_sshx()
    if sshx_path:
        link = _sshx_link(sshx_path)
        if link:
            return "🔐 Удалённый терминал (sshx):\n" + link
    return "🌐 Удалённый терминал\n\n" + terminal_manual_hint


def _ensure_tmate() -> str:
    found = shutil.which("tmate")
    if found:
        return found
    if _install_tmate_apt():
        return shutil.which("tmate") or ""
    if _install_tmate_script():
        return shutil.which("tmate") or ""
    return _install_tmate_static()


def _ensure_sshx() -> str:
    found = shutil.which("sshx")
    if found:
        return found
    _install_sshx()
    return shutil.which("sshx") or ""


def _install_tmate_apt() -> bool:
    prefix = _sudo_prefix()
    ok, _ = _run(f"{prefix}apt-get update -qq && {prefix}apt-get install -y tmate", 600)
    return ok and shutil.which("tmate") is not None


def _install_tmate_script() -> bool:
    ok, _ = _run(f"curl -fsSL {tmate_installer_url} | sh", 600)
    return ok and shutil.which("tmate") is not None


def _install_sshx() -> bool:
    ok, _ = _run(f"curl -fsSL {sshx_installer_url} | sh", 600)
    if shutil.which("sshx"):
        return True
    _run(f"curl -fsSL {sshx_installer_url} | {_sudo_prefix()}sh", 600)
    return shutil.which("sshx") is not None


def _install_tmate_static() -> str:
    os.makedirs(bin_dir, exist_ok=True)
    archive_path = bin_dir / "tmate-static.tar.xz"
    try:
        urllib.request.urlretrieve(tmate_static_url, archive_path)
        with tarfile.open(archive_path) as archive:
            archive.extractall(bin_dir)
    except (OSError, tarfile.TarError):
        return ""
    for candidate in sorted(bin_dir.rglob("tmate")):
        if candidate.is_file():
            candidate.chmod(0o755)
            return str(candidate)
    return ""


def _tmate_format(binary: str, template: str) -> str:
    try:
        result = subprocess.run([binary, "display", "-p", template], capture_output=True, text=True, timeout=30)
        return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _tmate_link(binary: str) -> str:
    try:
        subprocess.run([binary, "new-session", "-d", "-s", session_name], capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    for _ in range(30):
        time.sleep(0.5)
        ssh_line = _tmate_format(binary, "#{tmate_ssh}")
        if ssh_line.startswith("ssh "):
            lines = [f"SSH: {ssh_line}"]
            web_line = _tmate_format(binary, "#{tmate_web}")
            if web_line:
                lines.append(f"Веб: {web_line}")
            return "\n".join(lines)
    return ""


def _sshx_link(binary: str) -> str:
    try:
        process = subprocess.Popen(
            [binary],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
    except OSError:
        return ""
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        line = process.stdout.readline()
        if not line:
            time.sleep(0.3)
            continue
        if "https://sshx.io/v1/" in line:
            return line.strip()
    return ""
