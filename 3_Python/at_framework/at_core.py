"""AT 指令送收與序列執行核心（與 GNSS 腳本相容的 step dict 格式）。"""

import csv
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, List, Optional, Tuple, Union

import serial
from serial import SerialException

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


def reconnect(
    port: str,
    baudrate: int,
    timeout: float,
    logger: Logger,
    old_ser: Optional[serial.Serial] = None,
    max_wait_sec: float = 60.0,
    retry_interval: float = 1.0,
) -> serial.Serial:
    """關閉舊連線並重試開啟 port（模組重啟後 COM 可能暫時消失）。"""
    close_quietly(old_ser)
    logger.write(f"重新連線 {port}（最多等待 {max_wait_sec} 秒）...")

    deadline = time.perf_counter() + max_wait_sec
    last_exc: Optional[BaseException] = None
    attempt = 0
    while time.perf_counter() < deadline:
        attempt += 1
        try:
            ser = connect(port, baudrate, timeout)
            logger.write(f"重連成功: {ser.port} @ {ser.baudrate} bps（第 {attempt} 次嘗試）")
            time.sleep(0.5)
            return ser
        except SerialException as exc:
            last_exc = exc
            remaining = max(0.0, deadline - time.perf_counter())
            if remaining <= 0:
                break
            time.sleep(min(retry_interval, remaining))

    raise SerialException(f"在 {max_wait_sec} 秒內無法重連 {port}: {last_exc}")


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


def send_at_command(
    ser: serial.Serial,
    command: str,
    expect: Expect,
    timeout: float,
    idle_timeout: Optional[float] = 0.3,
) -> Tuple[bool, str]:
    ser.reset_input_buffer()
    ser.write(f"{command}\r\n".encode("utf-8"))

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
    ser: serial.Serial,
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
) -> Tuple[List[AtStepResult], serial.Serial]:
    results: List[AtStepResult] = []
    total = len(at_steps)

    for idx, step in enumerate(at_steps, start=1):
        command = step["cmd"]
        expect = step["expect"]
        timeout = float(step["timeout"])
        expect_label = _expect_label(step)

        logger.write(f"--- {test_id + ' | ' if test_id else ''}Round {round_idx} | Step {idx}/{total} ---")
        logger.write(f"TX: {command}")
        logger.write(f"Expected: {expect_label}")

        idle_timeout = step["idle_timeout"] if "idle_timeout" in step else 0.3
        start = time.perf_counter()
        passed, response = send_at_command(
            ser, command, expect, timeout, idle_timeout=idle_timeout
        )
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        response_display = response.replace("\r", "\\r").replace("\n", "\\n")
        logger.write(f"RX ({elapsed_ms} ms): {response_display}")

        if step.get("check_ttff"):
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

        if break_after_step:
            break

    return results, ser
