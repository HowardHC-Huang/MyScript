"""AT 指令送收與序列執行核心（與 GNSS 腳本相容的 step dict 格式）。"""

import csv
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Union

import serial
from serial import SerialException
from serial.tools import list_ports

Expect = Union[str, Callable[[str], bool]]

TTFF_MAX_SEC = 5.0
TTFF_PATTERN = re.compile(r"TTFF\s*\(sec\)\s*=\s*([\d.]+)", re.IGNORECASE)


@dataclass
class AtStepResult:
    round_idx: int
    step: int
    command: str
    expected: str
    passed: bool
    response: str
    elapsed_ms: int
    test_id: str = ""


class Logger:
    def __init__(self, log_path: str) -> None:
        self.log_path = log_path

    def write(self, message: str) -> None:
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
        print(line)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


class DataRecorder:
    FIELDNAMES = [
        "timestamp",
        "test_id",
        "round",
        "step",
        "command",
        "expected",
        "passed",
        "elapsed_ms",
        "response",
    ]

    def __init__(self, data_path: str) -> None:
        self.data_path = data_path
        with open(self.data_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.FIELDNAMES)
            writer.writeheader()

    def append(self, result: AtStepResult) -> None:
        with open(self.data_path, "a", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.FIELDNAMES)
            writer.writerow(
                {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "test_id": result.test_id,
                    "round": result.round_idx,
                    "step": result.step,
                    "command": result.command,
                    "expected": result.expected,
                    "passed": "PASS" if result.passed else "FAIL",
                    "elapsed_ms": result.elapsed_ms,
                    "response": result.response.replace("\r", " ").replace("\n", " "),
                }
            )


def parse_ttff_sec(response: str) -> Optional[float]:
    match = TTFF_PATTERN.search(response)
    if not match:
        return None
    return float(match.group(1))


def log_ttff_result(logger: Logger, response: str, passed: bool, max_sec: float = TTFF_MAX_SEC) -> None:
    ttff = parse_ttff_sec(response)
    if ttff is None:
        if "No TTFF available" in response:
            logger.write("TTFF FAIL [MARK]: No TTFF available")
        else:
            logger.write("TTFF FAIL [MARK]: 無法解析 TTFF (sec)")
        return
    if ttff >= max_sec:
        logger.write(f"TTFF FAIL [MARK]: TTFF (sec) = {ttff} >= {max_sec} (超過門檻)")
    elif passed:
        logger.write(f"TTFF PASS: TTFF (sec) = {ttff} < {max_sec}")


def connect(port: str, baudrate: int, timeout: float) -> serial.Serial:
    return serial.Serial(
        port=port,
        baudrate=baudrate,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=timeout,
    )


def close_quietly(ser: Optional[serial.Serial]) -> None:
    if ser is None:
        return
    try:
        if ser.is_open:
            ser.close()
    except Exception:
        pass


def _port_realpath(port: str) -> str:
    try:
        return str(Path(port).resolve())
    except OSError:
        return port


def _is_windows_com(port: str) -> bool:
    return port.upper().startswith("COM") and not port.startswith("/")


def _iface_from_location(location: Optional[str]) -> Optional[str]:
    if not location or "." not in location:
        return None
    try:
        return str(int(location.rsplit(".", 1)[-1]))
    except ValueError:
        return None


def _iface_from_by_id(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    match = re.search(r"-if(\d+)", Path(path).name)
    if not match:
        return None
    return str(int(match.group(1)))


def find_by_id_symlink(port: str) -> Optional[str]:
    """Linux：找到目前指向此 tty 的 /dev/serial/by-id/ 連結。"""
    by_id_dir = Path("/dev/serial/by-id")
    if not by_id_dir.is_dir():
        return None
    target = _port_realpath(port)
    for link in sorted(by_id_dir.iterdir()):
        try:
            if str(link.resolve()) == target:
                return str(link)
        except OSError:
            continue
    return None


def snapshot_port(port: str) -> Dict[str, Optional[str]]:
    """重連前記下 USB 身分。by-id 檔名可能隨 iProduct 改變，故同時記下 interface。"""
    snap: Dict[str, Optional[str]] = {
        "preferred": port,
        "realpath": _port_realpath(port),
        "by_id": find_by_id_symlink(port),
        "vid": None,
        "pid": None,
        "serial_number": None,
        "location": None,
        "iface": None,
    }
    real = snap["realpath"] or port
    for info in list_ports.comports():
        try:
            same = info.device == port or str(Path(info.device).resolve()) == real
        except OSError:
            same = info.device == port
        if not same:
            continue
        snap["vid"] = None if info.vid is None else str(info.vid)
        snap["pid"] = None if info.pid is None else str(info.pid)
        snap["serial_number"] = info.serial_number
        snap["location"] = info.location
        snap["iface"] = _iface_from_location(info.location) or _iface_from_by_id(snap["by_id"])
        if snap["by_id"] is None:
            snap["by_id"] = find_by_id_symlink(info.device)
            if snap["iface"] is None:
                snap["iface"] = _iface_from_by_id(snap["by_id"])
        break
    if snap["iface"] is None:
        snap["iface"] = _iface_from_by_id(snap["by_id"])
    return snap


def _port_is_live(port: str) -> bool:
    if _is_windows_com(port):
        return True
    real = _port_realpath(port)
    for info in list_ports.comports():
        if info.device == port:
            return True
        try:
            if str(Path(info.device).resolve()) == real:
                return True
        except OSError:
            continue
    return False


def _current_by_id_for_iface(iface: Optional[str]) -> List[str]:
    if not iface:
        return []
    by_id_dir = Path("/dev/serial/by-id")
    if not by_id_dir.is_dir():
        return []
    found: List[str] = []
    for link in sorted(by_id_dir.iterdir()):
        if _iface_from_by_id(str(link)) != iface:
            continue
        try:
            if link.exists():
                found.append(str(link))
        except OSError:
            continue
    return found


def list_reconnect_candidates(preferred: str, snap: Optional[Dict[str, Optional[str]]] = None) -> List[str]:
    """列出目前活著、且最可能是同一條 AT 介面的 port（舊 ttyACM 殘留節點不列入）。"""
    if _is_windows_com(preferred):
        return [preferred]

    scored: List[Tuple[int, str]] = []
    seen = set()

    def add(path: Optional[str], score: int) -> None:
        if not path or path in seen:
            return
        try:
            exists = Path(path).exists()
        except OSError:
            exists = False
        if not exists:
            return
        seen.add(path)
        scored.append((score, path))

    snap = snap or {}
    vid = snap.get("vid")
    pid = snap.get("pid")
    sn = snap.get("serial_number")
    loc = snap.get("location")
    iface = snap.get("iface")

    for info in list_ports.comports():
        score = 0
        if vid is not None:
            if info.vid is None or str(info.vid) != vid:
                continue
            score += 10
            if pid is not None and info.pid is not None and str(info.pid) == pid:
                score += 3
            if sn and info.serial_number == sn:
                score += 20
            if loc and info.location == loc:
                score += 50
            info_iface = _iface_from_location(info.location)
            if iface and info_iface == iface:
                score += 40
        add(info.device, score)

    for link in _current_by_id_for_iface(iface):
        add(link, 80)

    if not scored and vid is None and _port_is_live(preferred):
        add(preferred, 1)

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [path for _score, path in scored]


def reconnect(
    port: str,
    baudrate: int,
    timeout: float,
    logger: Logger,
    old_ser: Optional[serial.Serial] = None,
    max_wait_sec: float = 60.0,
    retry_interval: float = 1.0,
) -> serial.Serial:
    """關閉舊連線並重連。Reset 後 ttyACM 編號、by-id 檔名都可能變，改對 USB 介面並用 AT 確認。"""
    snap_from = old_ser.port if old_ser is not None and old_ser.port else port
    snap = snapshot_port(snap_from)
    old_key = snap.get("realpath") or snap_from
    close_quietly(old_ser)

    logger.write(
        "重新連線 "
        f"vid={snap.get('vid')} pid={snap.get('pid')} "
        f"iface={snap.get('iface')} location={snap.get('location')} "
        f"（最多等待 {max_wait_sec} 秒）..."
    )
    if snap.get("by_id"):
        logger.write(f"Reset 前 by-id: {snap['by_id']}（iProduct 改變後檔名可能不同，僅供參考）")

    deadline = time.perf_counter() + max_wait_sec
    last_exc: Optional[BaseException] = None
    attempt = 0
    last_candidates: Optional[List[str]] = None

    if not _is_windows_com(port):
        drop_deadline = time.perf_counter() + min(15.0, max_wait_sec)
        while time.perf_counter() < drop_deadline:
            if not _port_is_live(old_key) and not _port_is_live(port):
                logger.write("舊 port 已從系統消失，開始尋找新的 tty")
                break
            time.sleep(0.2)
        else:
            if _port_is_live(old_key) or _port_is_live(port):
                logger.write("舊 port 仍在；若接下來連到錯誤的 tty，請加大 wait_after")

    while time.perf_counter() < deadline:
        attempt += 1
        candidates = list_reconnect_candidates(port, snap)
        if candidates != last_candidates:
            logger.write(f"候選 port: {', '.join(candidates) if candidates else '(尚無)'}")
            last_candidates = candidates

        for target in candidates:
            ser: Optional[serial.Serial] = None
            try:
                ser = connect(target, baudrate, timeout)
                passed, _response = send_at_command(ser, "AT", "OK", timeout=2.0, idle_timeout=0.3)
                if not passed:
                    logger.write(f"跳過 {target}：未回應 AT OK（可能不是 AT 埠或模組尚未就緒）")
                    close_quietly(ser)
                    continue
                opened = ser.port or target
                if _port_realpath(opened) != _port_realpath(port) and opened != port:
                    logger.write(f"port 已變更: {port} -> {opened}")
                logger.write(f"重連成功: {opened} @ {ser.baudrate} bps（第 {attempt} 次嘗試）")
                time.sleep(0.5)
                return ser
            except SerialException as exc:
                last_exc = exc
                close_quietly(ser)

        remaining = max(0.0, deadline - time.perf_counter())
        if remaining <= 0:
            break
        time.sleep(min(retry_interval, remaining))

    raise SerialException(
        f"在 {max_wait_sec} 秒內無法重連到可回應 AT 的 port"
        f"（iface={snap.get('iface')}, 最後錯誤: {last_exc}）"
    )


def _expect_label(step: dict) -> str:
    if "expect_label" in step:
        return step["expect_label"]
    expect = step["expect"]
    if isinstance(expect, str):
        return expect
    return getattr(expect, "__name__", "<custom check>")


def _response_matches(response: str, expect: Expect) -> bool:
    if isinstance(expect, str):
        return expect in response
    if hasattr(expect, "search"):
        return bool(expect.search(response))
    return expect(response)


CTRLZ_TOKEN = "{CTRLZ}"


def build_at_tx_bytes(command: str) -> bytes:
    """把 Excel cmd 編成要寫入 serial 的位元組。

    一般 AT 指令結尾加 \\r\\n。
    cmd 含 {CTRLZ} 時改送 Ctrl+Z（0x1A），且不再加 \\r\\n（簡訊本文結束符）。
    """
    if CTRLZ_TOKEN in command:
        return command.replace(CTRLZ_TOKEN, "\x1a").encode("utf-8")
    return f"{command}\r\n".encode("utf-8")


def send_shell_command(
    command: str,
    expect: Expect,
    timeout: float,
) -> Tuple[bool, str]:
    """在本機 shell 執行指令（Ubuntu 用 bash；Windows 用 COMSPEC）。"""
    kwargs = {
        "args": command,
        "shell": True,
        "capture_output": True,
        "stdin": subprocess.DEVNULL,
        "text": True,
        "timeout": timeout,
        "encoding": "utf-8",
        "errors": "replace",
    }
    if sys.platform != "win32":
        kwargs["executable"] = "/bin/bash"

    try:
        completed = subprocess.run(**kwargs)
    except subprocess.TimeoutExpired as exc:
        chunks = []
        for part in (exc.stdout, exc.stderr):
            if not part:
                continue
            chunks.append(part if isinstance(part, str) else part.decode("utf-8", errors="replace"))
        output = "".join(chunks).strip()
        response = f"{output}\n[TIMEOUT]".strip() if output else "[TIMEOUT]"
        return False, response
    except OSError as exc:
        return False, f"[錯誤] {exc}"

    response = (completed.stdout or "") + (completed.stderr or "")
    if completed.returncode != 0:
        response = f"{response.rstrip()}\n[exit={completed.returncode}]"
    return _response_matches(response, expect), response


def send_at_command(
    ser: serial.Serial,
    command: str,
    expect: Expect,
    timeout: float,
    idle_timeout: Optional[float] = 0.3,
) -> Tuple[bool, str]:
    ser.reset_input_buffer()
    ser.write(build_at_tx_bytes(command))

    deadline = time.perf_counter() + timeout
    last_data = time.perf_counter()
    chunks: List[bytes] = []

    while time.perf_counter() < deadline:
        waiting = ser.in_waiting
        if waiting:
            chunks.append(ser.read(waiting))
            last_data = time.perf_counter()
            response = b"".join(chunks).decode("utf-8", errors="ignore")
            if _response_matches(response, expect):
                return True, response
            continue

        if (
            idle_timeout is not None
            and chunks
            and (time.perf_counter() - last_data) >= idle_timeout
        ):
            break
        time.sleep(0.05)

    response = b"".join(chunks).decode("utf-8", errors="ignore")
    return _response_matches(response, expect), response


def run_at_sequence(
    ser: Optional[serial.Serial],
    logger: Logger,
    data_recorder: DataRecorder,
    round_idx: int,
    at_steps: List[dict],
    default_step_wait: float = 0.0,
    test_id: str = "",
    port: Optional[str] = None,
    baudrate: Optional[int] = None,
    serial_timeout: Optional[float] = None,
    reconnect_max_wait: float = 60.0,
) -> Tuple[List[AtStepResult], Optional[serial.Serial]]:
    results: List[AtStepResult] = []
    total = len(at_steps)

    for idx, step in enumerate(at_steps, start=1):
        command = step["cmd"]
        expect = step["expect"]
        timeout = float(step["timeout"])
        expect_label = _expect_label(step)
        cmd_type = step.get("cmd_type", "at")

        logger.write(f"--- {test_id + ' | ' if test_id else ''}Round {round_idx} | Step {idx}/{total} ---")
        if cmd_type == "shell":
            logger.write(f"SH: {command}")
        else:
            logger.write(f"TX: {command}")
        logger.write(f"Expected: {expect_label}")

        idle_timeout = step["idle_timeout"] if "idle_timeout" in step else 0.3
        start = time.perf_counter()
        if cmd_type == "shell":
            passed, response = send_shell_command(command, expect, timeout)
        elif ser is None:
            passed, response = False, "[錯誤] AT 步驟但尚未連線 serial"
        else:
            passed, response = send_at_command(
                ser, command, expect, timeout, idle_timeout=idle_timeout
            )
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        response_display = response.replace("\r", "\\r").replace("\n", "\\n")
        logger.write(f"RX ({elapsed_ms} ms): {response_display}")

        if cmd_type != "shell" and step.get("check_ttff"):
            log_ttff_result(logger, response, passed)

        result = AtStepResult(
            round_idx=round_idx,
            step=idx,
            command=command,
            expected=expect_label,
            passed=passed,
            response=response,
            elapsed_ms=elapsed_ms,
            test_id=test_id,
        )
        results.append(result)
        data_recorder.append(result)

        break_after_step = False
        if passed:
            logger.write(f"Step {idx} PASS")
        else:
            logger.write(f"Step {idx} FAIL (expected: {expect_label})")
            remaining_steps = at_steps[idx:]
            if any(s.get("run_on_failure") for s in remaining_steps):
                logger.write("偵測到失敗後仍需執行的後續步驟，繼續執行...")
            else:
                break_after_step = True

        # wait_after 的語意：本步驟完成後等待秒數
        # 但若是要 break 的步驟且沒有下一個 step，要避免「步驟間」等待只為了延長流程；
        # 只有在 reconnect_after 時，才需要把等待時間用在模組重啟/就緒上。
        wait_sec = float(step.get("wait_after", default_step_wait))

        # 若接著還會執行下一個 step，才做步驟間等待（保留舊行為）
        if idx < total and not break_after_step:
            if wait_sec > 0:
                logger.write(f"步驟間等待 {wait_sec} 秒...")
                time.sleep(wait_sec)

        # reconnect_after：無論是否最後一步/是否 break，都要確保能重連
        if step.get("reconnect_after"):
            if wait_sec > 0 and not (idx < total and not break_after_step):
                logger.write(f"等待 {wait_sec} 秒...")
                time.sleep(wait_sec)

            if not port or baudrate is None or serial_timeout is None:
                raise ValueError(
                    "步驟設了 reconnect_after，但未提供 port/baudrate/serial_timeout"
                )
            ser = reconnect(
                port,
                baudrate,
                serial_timeout,
                logger,
                old_ser=ser,
                max_wait_sec=reconnect_max_wait,
            )
            if ser.port:
                port = ser.port

        if break_after_step:
            break

    return results, ser
