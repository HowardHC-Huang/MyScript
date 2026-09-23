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


def find_by_id_symlink(port: str) -> Optional[str]:
    """Linux：找到指向此 tty 的 /dev/serial/by-id/ 連結（Reset 後編號會變，連結通常不變）。"""
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
    """重連前記下 USB 身分，供 ttyACM 編號改變後對回同一條介面。"""
    snap: Dict[str, Optional[str]] = {
        "preferred": port,
        "by_id": find_by_id_symlink(port),
        "vid": None,
        "pid": None,
        "serial_number": None,
        "location": None,
    }
    real = _port_realpath(port)
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
        if snap["by_id"] is None:
            snap["by_id"] = find_by_id_symlink(info.device)
        break
    return snap


def _is_windows_com(port: str) -> bool:
    return port.upper().startswith("COM") and not port.startswith("/")


def resolve_reconnect_port(preferred: str, snap: Optional[Dict[str, Optional[str]]] = None) -> Optional[str]:
    """原 port 還在就用它；否則改走 by-id 或相同 VID/PID/location 的新 tty。"""
    candidates: List[str] = []

    def add(path: Optional[str]) -> None:
        if not path or path in candidates:
            return
        if _is_windows_com(path):
            candidates.append(path)
            return
        try:
            exists = Path(path).exists()
        except OSError:
            exists = False
        if exists:
            candidates.append(path)

    add(preferred)
    if snap:
        add(snap.get("by_id"))
        vid = snap.get("vid")
        pid = snap.get("pid")
        sn = snap.get("serial_number")
        loc = snap.get("location")
        scored: List[Tuple[int, str]] = []
        if vid is not None:
            for info in list_ports.comports():
                if info.vid is None or str(info.vid) != vid:
                    continue
                if pid is not None and (info.pid is None or str(info.pid) != pid):
                    continue
                score = 0
                if sn and info.serial_number == sn:
                    score += 2
                if loc and info.location == loc:
                    score += 4
                scored.append((score, info.device))
            scored.sort(key=lambda item: (-item[0], item[1]))
            for _score, device in scored:
                add(device)
    return candidates[0] if candidates else None


def reconnect(
    port: str,
    baudrate: int,
    timeout: float,
    logger: Logger,
    old_ser: Optional[serial.Serial] = None,
    max_wait_sec: float = 60.0,
    retry_interval: float = 1.0,
) -> serial.Serial:
    """關閉舊連線並重試開啟 port（模組重啟後路徑可能消失或 ttyACM 編號改變）。"""
    snap_from = old_ser.port if old_ser is not None and old_ser.port else port
    snap = snapshot_port(snap_from)
    close_quietly(old_ser)

    stable = snap.get("by_id") or port
    logger.write(f"重新連線 {stable}（最多等待 {max_wait_sec} 秒）...")
    if snap.get("by_id") and snap["by_id"] != port:
        logger.write(f"穩定路徑: {snap['by_id']}（Reset 後 ttyACM 編號可能改變）")

    deadline = time.perf_counter() + max_wait_sec
    last_exc: Optional[BaseException] = None
    attempt = 0
    while time.perf_counter() < deadline:
        attempt += 1
        target = resolve_reconnect_port(port, snap)
        if target is None:
            remaining = max(0.0, deadline - time.perf_counter())
            if remaining <= 0:
                break
            time.sleep(min(retry_interval, remaining))
            continue
        try:
            ser = connect(target, baudrate, timeout)
            if target != port:
                logger.write(f"port 已變更: {port} -> {ser.port}")
            logger.write(f"重連成功: {ser.port} @ {ser.baudrate} bps（第 {attempt} 次嘗試）")
            time.sleep(0.5)
            return ser
        except SerialException as exc:
            last_exc = exc
            remaining = max(0.0, deadline - time.perf_counter())
            if remaining <= 0:
                break
            time.sleep(min(retry_interval, remaining))

    raise SerialException(f"在 {max_wait_sec} 秒內無法重連 {stable}: {last_exc}")


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
