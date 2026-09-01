#!/usr/bin/env python3
"""從 Excel 讀取 AT 測試步驟並執行。"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from serial import SerialException
from serial.tools import list_ports

from at_core import DataRecorder, Logger, close_quietly, connect, run_at_sequence
from excel_loader import ExcelLoadError, load_config_from_excel, load_steps_from_excel, list_test_ids, validate_excel

DEFAULT_EXCEL = Path(__file__).resolve().parent / "testcases" / "AT_Testcases_Template.xlsx"


def list_available_ports() -> None:
    ports = list_ports.comports()
    if not ports:
        print("找不到任何 serial port。")
        return
    print("可用的 serial port：")
    for p in ports:
        print(f"  {p.device}\t{p.description}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="從 Excel 讀取 AT 測試步驟並執行")
    parser.add_argument(
        "-x",
        "--excel",
        default=str(DEFAULT_EXCEL),
        help=f"測項 Excel 路徑（預設: {DEFAULT_EXCEL.name}）",
    )
    parser.add_argument(
        "-t",
        "--test-id",
        action="append",
        help="要執行的 test_id；可重複 -t，或在單一 -t 內以逗號分隔多個",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="執行 Excel 內所有 enabled=V 的 test_id（依 Steps 出現順序）",
    )
    parser.add_argument("-p", "--port", help="Serial port（預設讀 Config sheet 或互動輸入）")
    parser.add_argument("-n", "--rounds", type=int, help="測試回合數（預設讀 Config sheet）")
    parser.add_argument("-b", "--baudrate", type=int, help="鮑率（預設讀 Config sheet）")
    parser.add_argument("--serial-timeout", type=float, help="Serial read timeout（預設讀 Config sheet）")
    parser.add_argument("--default-step-wait", type=float, help="步驟間預設等待秒數")
    parser.add_argument("-o", "--log", help="Log 檔路徑")
    parser.add_argument("-d", "--data", help="結果 CSV 路徑")
    parser.add_argument("--list-ports", action="store_true", help="列出可用 port 後結束")
    parser.add_argument("--list-tests", action="store_true", help="列出 Excel 內 test_id 後結束")
    parser.add_argument("--validate", action="store_true", help="只驗證 Excel 格式後結束")
    return parser.parse_args()


def _config_int(config: dict, key: str, fallback: int) -> int:
    text = config.get(key, "").strip()
    return int(text) if text else fallback


def _config_float(config: dict, key: str, fallback: float) -> float:
    text = config.get(key, "").strip()
    return float(text) if text else fallback


def _flatten_test_id_args(items: Optional[List[str]]) -> List[str]:
    if not items:
        return []
    result: List[str] = []
    for item in items:
        for part in item.split(","):
            part = part.strip()
            if part and part not in result:
                result.append(part)
    return result


def resolve_test_ids(args: argparse.Namespace, config: dict, excel_path: Path) -> List[str]:
    """決定本次要執行的 test_id 清單。

    優先順序：--all > -t > Config.test_ids > Config.test_id > 全部啟用測項（等同 --all）
    """
    if args.all:
        return list_test_ids(excel_path)

    cli_ids = _flatten_test_id_args(args.test_id)
    if cli_ids:
        return cli_ids

    config_ids = config.get("test_ids", "").strip()
    if config_ids:
        ids = [part.strip() for part in config_ids.split(",") if part.strip()]
        return list(dict.fromkeys(ids))

    single = config.get("test_id", "").strip()
    if single:
        return [single]

    return list_test_ids(excel_path)


def _output_paths(
    test_ids: List[str],
    timestamp: str,
    log_arg: Optional[str],
    data_arg: Optional[str],
) -> Tuple[str, str]:
    if log_arg and data_arg:
        return log_arg, data_arg

    if len(test_ids) == 1:
        safe_test_id = test_ids[0].replace(" ", "_")
        log_path = log_arg or f"AT_Excel_{safe_test_id}_{timestamp}.log"
        data_path = data_arg or f"AT_Excel_{safe_test_id}_{timestamp}.csv"
        return log_path, data_path

    log_path = log_arg or f"AT_Excel_Suite_{timestamp}.log"
    data_path = data_arg or f"AT_Excel_Suite_{timestamp}.csv"
    return log_path, data_path


def main() -> int:
    args = parse_args()

    if args.list_ports:
        list_available_ports()
        return 0

    excel_path = Path(args.excel)
    if not excel_path.is_file():
        print(f"找不到 Excel: {excel_path}", file=sys.stderr)
        print("請先執行: python create_template.py", file=sys.stderr)
        return 1

    if args.validate:
        try:
            test_ids = validate_excel(excel_path)
        except ExcelLoadError as exc:
            print(f"[驗證失敗] {exc}", file=sys.stderr)
            return 1
        print(f"Excel 驗證通過，共 {len(test_ids)} 個 test_id: {', '.join(test_ids)}")
        return 0

    if args.list_tests:
        try:
            test_ids = list_test_ids(excel_path)
        except ExcelLoadError as exc:
            print(f"[錯誤] {exc}", file=sys.stderr)
            return 1
        print("Excel 內啟用的 test_id：")
        for test_id in test_ids:
            print(f"  {test_id}")
        return 0

    try:
        config = load_config_from_excel(excel_path)
    except ExcelLoadError as exc:
        print(f"[錯誤] {exc}", file=sys.stderr)
        return 1

    if args.all and args.test_id:
        print("請勿同時使用 --all 與 -t/--test-id。", file=sys.stderr)
        return 1

    try:
        test_ids = resolve_test_ids(args, config, excel_path)
    except ExcelLoadError as exc:
        print(f"[錯誤] {exc}", file=sys.stderr)
        return 1

    if not test_ids:
        print(
            "沒有可執行的 test_id：請在 Steps 將測項 enabled 設為 V，"
            "或在 Config 設定 test_id / test_ids，或使用 -t / --all",
            file=sys.stderr,
        )
        return 1

    steps_by_test: Dict[str, list] = {}
    for test_id in test_ids:
        try:
            steps_by_test[test_id] = load_steps_from_excel(excel_path, test_id=test_id)
        except ExcelLoadError as exc:
            print(f"[錯誤] {exc}", file=sys.stderr)
            return 1

    port = (args.port or config.get("port") or input("請輸入 serial port (例如 COM14): ")).strip().upper()
    if not port:
        print("未指定 port。", file=sys.stderr)
        return 1

    baudrate = args.baudrate if args.baudrate is not None else _config_int(config, "baudrate", 115200)
    serial_timeout = (
        args.serial_timeout
        if args.serial_timeout is not None
        else _config_float(config, "serial_timeout", 1.0)
    )
    rounds = args.rounds if args.rounds is not None else _config_int(config, "rounds", 1)
    default_step_wait = (
        args.default_step_wait
        if args.default_step_wait is not None
        else _config_float(config, "default_step_wait", 0.0)
    )
    reconnect_max_wait = _config_float(config, "reconnect_max_wait", 60.0)

    if rounds < 1:
        print("回合數必須 >= 1。", file=sys.stderr)
        return 1

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path, data_path = _output_paths(test_ids, timestamp, args.log, args.data)

    logger = Logger(log_path)
    data_recorder = DataRecorder(data_path)

    logger.write(f"Excel: {excel_path}")
    logger.write(f"test_ids: {', '.join(test_ids)}")
    logger.write(f"Log file: {log_path}")
    logger.write(f"Data file: {data_path}")
    logger.write(f"Target port: {port}, baudrate: {baudrate}")
    logger.write(f"Total rounds per test_id: {rounds}")
    logger.write(f"default_step_wait: {default_step_wait} sec")
    logger.write(f"reconnect_max_wait: {reconnect_max_wait} sec")

    suite_summaries: List[Tuple[str, int, int]] = []
    ser = None

    try:
        ser = connect(port, baudrate, serial_timeout)
        logger.write(f"已連線: {ser.port} @ {ser.baudrate} bps")
        time.sleep(0.5)

        for i, test_id in enumerate(test_ids):
            if i > 0:
                logger.write("測試 ID 之間等待 2 秒...")
                time.sleep(2)

            at_steps = steps_by_test[test_id]
            logger.write(f"\n########## test_id: {test_id} ({len(at_steps)} steps) ##########")

            success_rounds = 0
            for round_idx in range(1, rounds + 1):
                logger.write(f"\n========== {test_id} | Round {round_idx}/{rounds} ==========")
                results, ser = run_at_sequence(
                    ser,
                    logger,
                    data_recorder,
                    round_idx,
                    at_steps,
                    default_step_wait=default_step_wait,
                    test_id=test_id,
                    port=port,
                    baudrate=baudrate,
                    serial_timeout=serial_timeout,
                    reconnect_max_wait=reconnect_max_wait,
                )
                passed_count = sum(1 for r in results if r.passed)
                round_pass = passed_count == len(at_steps) and len(results) == len(at_steps)
                if round_pass:
                    success_rounds += 1
                logger.write(
                    f"{test_id} Round {round_idx} 結果: "
                    f"{'PASS' if round_pass else 'FAIL'} "
                    f"({passed_count}/{len(at_steps)} 步驟通過)"
                )

            suite_summaries.append((test_id, success_rounds, rounds))

    except SerialException as exc:
        logger.write(f"無法連線到 {port}: {exc}")
        return 1
    finally:
        close_quietly(ser)

    logger.write("\n=== 測試摘要 ===")
    all_pass = True
    for test_id, success_rounds, total_rounds in suite_summaries:
        test_pass = success_rounds == total_rounds
        all_pass = all_pass and test_pass
        at_steps = steps_by_test[test_id]
        logger.write(
            f"{test_id}: {'PASS' if test_pass else 'FAIL'} "
            f"(成功回合 {success_rounds}/{total_rounds}，每回合 {len(at_steps)} 步驟)"
        )
    logger.write(f"Log: {log_path}")
    logger.write(f"Data: {data_path}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
