#!/usr/bin/env python3
"""連線到指定 serial port，依序發送 GNSS/Xtra 相關 AT 指令，支援多回合並寫入 log / 資料檔。"""

import argparse
import csv
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, List, Optional, Tuple, Union

import serial
from serial import SerialException
from serial.tools import list_ports

Expect = Union[str, Callable[[str], bool]]

STEP_WAIT_SEC = 5
STEP6_TO_STEP7_WAIT_SEC = 10
# 回應較慢的 AT 指令：等到逾時或收到預期內容為止（不做 idle 提前結束）
XTRASTATUS_TIMEOUT = 30
XTRAINITDNLD_TIMEOUT = 60
GPSSTATUS_TIMEOUT = 30
TTFF_MAX_SEC = 5
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


class Logger:
    def __init__(self, log_path: str) -> None:
        self.log_path = log_path

    def write(self, message: str) -> None:
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
        print(line)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


class DataRecorder:
    """將每回合、每步驟結果寫入 CSV 資料檔。"""

    FIELDNAMES = [
        "timestamp",
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


def log_ttff_result(logger: Logger, response: str, passed: bool) -> None:
    ttff = parse_ttff_sec(response)
    if ttff is None:
        if "No TTFF available" in response:
            logger.write("TTFF FAIL [MARK]: No TTFF available")
        else:
            logger.write("TTFF FAIL [MARK]: 無法解析 TTFF (sec)")
        return
    if ttff >= TTFF_MAX_SEC:
        logger.write(
            f"TTFF FAIL [MARK]: TTFF (sec) = {ttff} >= {TTFF_MAX_SEC} (超過門檻)"
        )
    elif passed:
        logger.write(f"TTFF PASS: TTFF (sec) = {ttff} < {TTFF_MAX_SEC}")


def build_at_steps() -> List[dict]:
    now = datetime.now()
    year_month_label = f"{now.year} {now.month:02d}"

    def expect_current_year_month(response: str) -> bool:
        return year_month_label in response

    def expect_gps_status(response: str) -> bool:
        if "OK" not in response:
            return False
        ttff = parse_ttff_sec(response)
        if ttff is None:
            return False
        return ttff < TTFF_MAX_SEC

    return [
        {"cmd": 'AT!ENTERCND="A710"', "expect": "OK", "timeout": 5},
        {"cmd": "AT!GPSCLRASSIST=1,1,1,1,1", "expect": "OK", "timeout": 10},
        {
            "cmd": "AT!GPSXTRASTATUS?",
            "expect": "1980",
            "timeout": XTRASTATUS_TIMEOUT,
            "idle_timeout": None,
        },
        {
            "cmd": "AT!GPSXTRAINITDNLD",
            "expect": "Xtra command sent successfully",
            "timeout": XTRAINITDNLD_TIMEOUT,
            "idle_timeout": None,
        },
        {
            "cmd": "AT!GPSXTRASTATUS?",
            "expect": expect_current_year_month,
            "expect_label": year_month_label,
            "timeout": XTRASTATUS_TIMEOUT,
            "idle_timeout": None,
        },
        {"cmd": "AT!GPSFIX=1,255,255", "expect": "OK", "timeout": 30},
        {
            "cmd": "AT!GPSSTATUS?",
            "expect": expect_gps_status,
            "expect_label": f"TTFF (sec) < {TTFF_MAX_SEC}",
            "timeout": GPSSTATUS_TIMEOUT,
            "idle_timeout": None,
            "check_ttff": True,
        },
        {
            "cmd": "AT!GPSEND=0",
            "expect": "OK",
            "timeout": 10,
            "run_on_failure": True,
        },
    ]


def list_available_ports() -> None:
    ports = list_ports.comports()
    if not ports:
        print("找不到任何 serial port。")
        return
    print("可用的 serial port：")
    for p in ports:
        print(f"  {p.device}\t{p.description}")


def connect(port: str, baudrate: int, timeout: float) -> serial.Serial:
    return serial.Serial(
        port=port,
        baudrate=baudrate,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=timeout,
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
    chunks = []  # type: List[bytes]

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
) -> List[AtStepResult]:
    results = []  # type: List[AtStepResult]
    total = len(at_steps)

    for idx, step in enumerate(at_steps, start=1):
        command = step["cmd"]
        expect = step["expect"]
        timeout = float(step["timeout"])
        expect_label = _expect_label(step)

        logger.write(f"--- Round {round_idx} | Step {idx}/{total} ---")
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
        )
        results.append(result)
        data_recorder.append(result)

        if passed:
            logger.write(f"Step {idx} PASS")
        else:
            logger.write(f"Step {idx} FAIL (expected: {expect_label})")
            remaining_steps = at_steps[idx:]
            if any(s.get("run_on_failure") for s in remaining_steps):
                logger.write("偵測到失敗後仍需執行的後續步驟，繼續執行...")
            else:
                break

        if idx < total:
            next_command = at_steps[idx]["cmd"]
            wait_sec = STEP_WAIT_SEC
            if command == "AT!GPSFIX=1,255,255" and next_command == "AT!GPSSTATUS?":
                wait_sec = STEP6_TO_STEP7_WAIT_SEC
            logger.write(f"步驟間等待 {wait_sec} 秒...")
            time.sleep(wait_sec)

    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GNSS Xtra AT 指令序列測試（多回合）")
    parser.add_argument("-p", "--port", help="Serial port 名稱，例如 COM14")
    parser.add_argument("-n", "--rounds", type=int, help="測試回合數")
    parser.add_argument("-b", "--baudrate", type=int, default=115200, help="鮑率 (預設: 115200)")
    parser.add_argument("-t", "--timeout", type=float, default=1.0, help="Serial 讀取逾時秒數 (預設: 1.0)")
    parser.add_argument("-o", "--log", help="Log 檔路徑 (預設: 自動產生時間戳檔名)")
    parser.add_argument("-d", "--data", help="資料檔路徑 (預設: 自動產生 CSV 檔名)")
    parser.add_argument("-l", "--list", action="store_true", help="列出可用 port 後結束")
    return parser.parse_args()


def _prompt_rounds() -> int:
    while True:
        try:
            value = int(input("請輸入測試回合數: "))
            if value < 1:
                print("回合數必須 >= 1。")
                continue
            return value
        except ValueError:
            print("請輸入有效的整數。")


def main() -> int:
    args = parse_args()

    if args.list:
        list_available_ports()
        return 0

    port = (args.port or input("請輸入 serial port (例如 COM14): ")).strip().upper()
    if not port:
        print("未指定 port。", file=sys.stderr)
        return 1

    rounds = args.rounds if args.rounds is not None else _prompt_rounds()
    if rounds < 1:
        print("回合數必須 >= 1。", file=sys.stderr)
        return 1

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = "GNSS_XTRA_ColdStart_STRESS_0001"
    log_path = args.log or f"{base_name}_{timestamp}.log"
    data_path = args.data or f"{base_name}_{timestamp}.csv"
    logger = Logger(log_path)
    data_recorder = DataRecorder(data_path)

    logger.write(f"Log file: {log_path}")
    logger.write(f"Data file: {data_path}")
    logger.write(f"Target port: {port}, baudrate: {args.baudrate}")
    logger.write(f"Total rounds: {rounds}, step interval: {STEP_WAIT_SEC} sec")

    round_summaries = []  # type: List[Tuple[int, bool, int]]
    total_steps = len(build_at_steps())

    try:
        with connect(port, args.baudrate, args.timeout) as ser:
            logger.write(f"已連線: {ser.port} @ {ser.baudrate} bps")
            time.sleep(0.5)

            for round_idx in range(1, rounds + 1):
                logger.write(f"\n========== Round {round_idx}/{rounds} ==========")
                at_steps = build_at_steps()
                results = run_at_sequence(ser, logger, data_recorder, round_idx, at_steps)
                passed_count = sum(1 for r in results if r.passed)
                round_pass = passed_count == len(at_steps)
                round_summaries.append((round_idx, round_pass, passed_count))
                logger.write(
                    f"Round {round_idx} 結果: "
                    f"{'PASS' if round_pass else 'FAIL'} "
                    f"({passed_count}/{len(at_steps)} 步驟通過)"
                )

    except SerialException as exc:
        logger.write(f"無法連線到 {port}: {exc}")
        return 1

    success_rounds = sum(1 for _, passed, _ in round_summaries if passed)
    logger.write(f"\n=== 測試摘要 ===")
    logger.write(f"成功回合: {success_rounds}/{rounds}")
    for round_idx, passed, step_count in round_summaries:
        logger.write(
            f"Round {round_idx}: {'PASS' if passed else 'FAIL'} ({step_count}/{total_steps} 步驟)"
        )
    logger.write(f"Log: {log_path}")
    logger.write(f"Data: {data_path}")

    return 0 if success_rounds == rounds else 1


if __name__ == "__main__":
    raise SystemExit(main())
