"""
RaporOku Agent — Auto-Updater

- Sadece Windows frozen (PyInstaller .exe) build'de aktif
- GitHub releases API'den en son tag'i okur
- Asset: raporoku-agent.exe + raporoku-agent.exe.sha256 (her ikisi şart)
- Yeni sürüm varsa .exe'yi "<exe>.pending" olarak indirir, SHA doğrular
- Bir sonraki agent başlangıcında atomic swap (pending → current) + relaunch
- Fail-silent: hata agent akışını durdurmaz
"""
import hashlib
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

log = logging.getLogger("raporoku.updater")

GITHUB_REPO = os.environ.get("RAPOROKU_AGENT_REPO", "eqho10/raporoku-agent")
RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
ASSET_NAME = "raporoku-agent.exe"
SHA_ASSET = "raporoku-agent.exe.sha256"
CHECK_INTERVAL_SEC = 6 * 3600  # 6 saat
FIRST_CHECK_DELAY_SEC = 60  # boot'ta 1dk bekle


def _is_frozen_windows() -> bool:
    return sys.platform == "win32" and getattr(sys, "frozen", False)


def _current_exe_path() -> Path:
    return Path(sys.executable)


def _parse_version(tag: str) -> tuple[int, ...]:
    t = tag.lstrip("vV").strip()
    parts = []
    for p in t.split("."):
        num = ""
        for ch in p:
            if ch.isdigit():
                num += ch
            else:
                break
        parts.append(int(num) if num else 0)
    return tuple(parts)


def _is_newer(remote_tag: str, current: str) -> bool:
    try:
        return _parse_version(remote_tag) > _parse_version(current)
    except Exception:
        return False


def _sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest().lower()


def apply_pending_update() -> bool:
    """Agent startup'ta çağrılır. Pending exe varsa swap + relaunch.

    Return: True eğer swap yapıldı (process restart olacak, caller exit etmeli).
    """
    if not _is_frozen_windows():
        return False
    exe = _current_exe_path()
    pending = exe.with_suffix(exe.suffix + ".pending")
    if not pending.exists():
        return False

    old = exe.with_suffix(exe.suffix + ".old")
    try:
        # Eski backup'ı sil (önceki update'ten kalan)
        if old.exists():
            try:
                old.unlink()
            except Exception:
                pass

        # current → .old, pending → current
        shutil.move(str(exe), str(old))
        shutil.move(str(pending), str(exe))

        log.info(f"Update uygulandı: {exe.name} yenilendi, .old backup tutuluyor.")

        # Yeni exe'yi başlat, kendimizi kapat
        # DETACHED_PROCESS = 0x00000008, CREATE_NEW_PROCESS_GROUP = 0x00000200
        flags = 0x00000008 | 0x00000200
        subprocess.Popen(
            [str(exe)] + sys.argv[1:],
            creationflags=flags,
            close_fds=True,
        )
        return True
    except Exception as e:
        log.error(f"Update swap başarısız: {e} — normal çalışmaya devam")
        # Rollback: pending'i eski haline getirme denemesi yok; .old kaldıysa bir sonraki
        # startup'ta elle temizle. Swap başarısızsa eski exe zaten çalışmakta, safe.
        return False


def _download_release_asset(download_url: str, target: Path):
    import requests
    resp = requests.get(download_url, stream=True, timeout=60)
    resp.raise_for_status()
    with open(target, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)


def _fetch_latest_release() -> dict | None:
    try:
        import requests
        resp = requests.get(RELEASE_API, timeout=10,
                            headers={"Accept": "application/vnd.github+json"})
        if resp.status_code != 200:
            log.debug(f"GitHub API {resp.status_code}")
            return None
        return resp.json()
    except Exception as e:
        log.debug(f"Release fetch exception: {e}")
        return None


def _check_and_stage(current_version: str) -> bool:
    """Yeni sürüm varsa pending'e indirir. Return True=staged."""
    if not _is_frozen_windows():
        return False

    data = _fetch_latest_release()
    if not data:
        return False
    tag = data.get("tag_name", "")
    if not tag or not _is_newer(tag, current_version):
        return False

    assets = {a.get("name"): a for a in data.get("assets", []) if a.get("name")}
    if ASSET_NAME not in assets or SHA_ASSET not in assets:
        log.debug(f"Release {tag} {ASSET_NAME} veya {SHA_ASSET} asset'i yok — atlanıyor")
        return False

    exe = _current_exe_path()
    pending = exe.with_suffix(exe.suffix + ".pending")
    pending_sha = exe.with_suffix(exe.suffix + ".pending.sha")

    try:
        log.info(f"Yeni sürüm bulundu: {tag} — indiriliyor...")
        _download_release_asset(assets[ASSET_NAME]["browser_download_url"], pending)
        _download_release_asset(assets[SHA_ASSET]["browser_download_url"], pending_sha)

        expected = pending_sha.read_text(encoding="utf-8", errors="ignore").strip().split()[0].lower()
        actual = _sha256_of_file(pending)
        if expected != actual:
            log.error(f"SHA mismatch (expected={expected}, actual={actual}) — pending silindi")
            try:
                pending.unlink()
                pending_sha.unlink()
            except Exception:
                pass
            return False

        log.info(f"Update {tag} staged: {pending} — bir sonraki başlangıçta uygulanacak")
        return True
    except Exception as e:
        log.warning(f"Update download fail: {e}")
        try:
            if pending.exists():
                pending.unlink()
            if pending_sha.exists():
                pending_sha.unlink()
        except Exception:
            pass
        return False


def start_update_loop(current_version: str, interval_sec: int = CHECK_INTERVAL_SEC) -> threading.Thread | None:
    """Arka planda 6 saatte bir yeni sürüm arar. Sadece Windows frozen'de başlar."""
    if not _is_frozen_windows():
        return None

    def _run():
        time.sleep(FIRST_CHECK_DELAY_SEC)
        while True:
            try:
                _check_and_stage(current_version)
            except Exception as e:
                log.debug(f"Update loop exception: {e}")
            time.sleep(interval_sec)

    t = threading.Thread(target=_run, daemon=True, name="updater")
    t.start()
    log.info(f"Auto-update aktif (repo: {GITHUB_REPO}, interval: {interval_sec}s)")
    return t
