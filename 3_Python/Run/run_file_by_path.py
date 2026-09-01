import argparse
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import serial
from serial import SerialException


def _launch_detached(command: List[str]) -> subprocess.Popen:
    # Windows detached launch: start target and continue script immediately.
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

    return subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
        close_fds=True,
    )


def _create_log_path(target: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_name = f"Stress_MyScript_Python_RunFile_{target.stem}_{ts}.log"
    return Path(__file__).resolve().parent / log_name


def _write_log(
    log_path: Path,
    target: Path,
    command_desc: str,
    return_code: int,
    com_port: str = "",
    com_connection_ok: Optional[bool] = None,
    at_command: str = "",
    at_response: str = "",
    at_pass: Optional[bool] = None,
    stdout: str = "",
    stderr: str = "",
) -> None:
    com_status = (
        "unknown" if com_connection_ok is None else ("success" if com_connection_ok else "failed")
    )
    at_status = "unknown" if at_pass is None else ("pass" if at_pass else "fail")
    content = [
        f"timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"target: {target}",
        f"command: {command_desc}",
        f"return_code: {return_code}",
        f"com_port: {com_port if com_port else '(empty)'}",
        f"com_connection_status: {com_status}",
        f"at_command: {at_command if at_command else '(empty)'}",
        f"at_result: {at_status}",
        "",
        "===== AT RESPONSE =====",
        at_response if at_response else "(empty)",
        "",
        "===== STDOUT =====",
        stdout if stdout else "(empty)",
        "",
        "===== STDERR =====",
        stderr if stderr else "(empty)",
        "",
    ]
    text = "\n".join(content)
    # Important: when running multiple rounds, don't overwrite previous rounds.
    if log_path.exists():
        with log_path.open("a", encoding="utf-8") as f:
            f.write("\n\n" + text)
    else:
        log_path.write_text(text, encoding="utf-8")


def _append_post_action_log(log_path: Path, action_name: str, action_ok: bool, details: str = "") -> None:
    if not log_path.exists():
        return

    section = [
        "",
        "===== POST ACTION =====",
        f"timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"action: {action_name}",
        f"result: {'success' if action_ok else 'failed'}",
        f"details: {details if details else '(empty)'}",
        "",
    ]
    with log_path.open("a", encoding="utf-8") as f:
        f.write("\n".join(section))


def _append_test_summary_log(
    log_path: Path,
    requested_rounds: int,
    executed_rounds: int,
    success_rounds: int,
    failure_rounds: int,
) -> None:
    if not log_path.exists():
        return

    success_rate = 0.0
    if executed_rounds > 0:
        success_rate = success_rounds / executed_rounds * 100.0

    section = [
        "",
        "===== TEST SUMMARY =====",
        f"總回合數（已執行）: {executed_rounds}",
        f"成功回合數: {success_rounds}",
        f"失敗回合數: {failure_rounds}",
        f"成功率: {success_rounds}/{executed_rounds} = {success_rate:.2f}%",
        f"目標回合數（需求）: {requested_rounds}",
    ]
    with log_path.open("a", encoding="utf-8") as f:
        f.write("\n".join(section))


def run_target_file(
    file_path: str,
    log_path: Path,
    com_port: str,
    com_connected: bool,
    at_command: str,
    at_response: str,
    at_pass: bool,
    round_idx: int = 1,
) -> int:
    target = Path(file_path).expanduser().resolve()

    if not target.exists():
        print(f"[錯誤] 找不到檔案：{target}")
        return 1

    if target.is_dir():
        print(f"[錯誤] 你輸入的是資料夾，不是檔案：{target}")
        return 1

    suffix = target.suffix.lower()
    try:
        if suffix == ".py":
            # 使用目前執行這支 script 的 Python 來跑目標 .py
            command = [sys.executable, str(target)]
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            _write_log(
                log_path,
                target,
                f"[round {round_idx}] " + " ".join(command),
                completed.returncode,
                com_port=com_port,
                com_connection_ok=com_connected,
                at_command=at_command,
                at_response=at_response,
                at_pass=at_pass,
                stdout=completed.stdout,
                stderr=completed.stderr,
            )
            print(f"[資訊] 執行完成，log：{log_path}")
            return completed.returncode

        if suffix in {".bat", ".cmd"}:
            command_desc = f"[round {round_idx}] {target}"
            completed = subprocess.run(
                [str(target)],
                shell=True,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            _write_log(
                log_path,
                target,
                command_desc,
                completed.returncode,
                com_port=com_port,
                com_connection_ok=com_connected,
                at_command=at_command,
                at_response=at_response,
                at_pass=at_pass,
                stdout=completed.stdout,
                stderr=completed.stderr,
            )
            print(f"[資訊] 執行完成，log：{log_path}")
            return completed.returncode

        if suffix == ".ps1":
            command = ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(target)]
            command_desc = " ".join(command)
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            _write_log(
                log_path,
                target,
                f"[round {round_idx}] {command_desc}",
                completed.returncode,
                com_port=com_port,
                com_connection_ok=com_connected,
                at_command=at_command,
                at_response=at_response,
                at_pass=at_pass,
                stdout=completed.stdout,
                stderr=completed.stderr,
            )
            print(f"[資訊] 執行完成，log：{log_path}")
            return completed.returncode

        if suffix == ".exe":
            command = [str(target)]
            process = _launch_detached(command)
            _write_log(
                log_path,
                target,
                f"[round {round_idx}] async launch: {' '.join(command)} (pid={process.pid})",
                0,
                com_port=com_port,
                com_connection_ok=com_connected,
                at_command=at_command,
                at_response=at_response,
                at_pass=at_pass,
                stdout="目標程式已啟動（非阻塞模式），script 不等待程式結束。",
                stderr="",
            )
            print(f"[資訊] 已啟動目標程式（非阻塞），log：{log_path}")
            return 0

        # 其他副檔名：用系統預設程式開啟（Windows）
        os.startfile(str(target))  # type: ignore[attr-defined]
        _write_log(
            log_path,
            target,
            f"[round {round_idx}] startfile {target}",
            0,
            com_port=com_port,
            com_connection_ok=com_connected,
            at_command=at_command,
            at_response=at_response,
            at_pass=at_pass,
            stdout="已交給 Windows 預設程式開啟，無法直接擷取該程式輸出。",
            stderr="",
        )
        print(f"[資訊] 已交由系統開啟，log：{log_path}")
        return 0
    except Exception as exc:
        _write_log(
            log_path,
            target,
            "exception",
            1,
            com_port=com_port,
            com_connection_ok=com_connected,
            at_command=at_command,
            at_response=at_response,
            at_pass=at_pass,
            stdout="",
            stderr=str(exc),
        )
        print(f"[資訊] 執行失敗，log：{log_path}")
        print(f"[錯誤] 執行失敗：{exc}")
        return 1


def check_com_connection_and_at(port_name: str, at_command: str) -> Tuple[bool, bool, str, str]:
    try:
        with serial.Serial(port=port_name, baudrate=9600, timeout=2) as ser:
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            ser.write((at_command + "\r\n").encode("utf-8"))
            ser.flush()
            time.sleep(0.5)
            raw = ser.read(ser.in_waiting or 1)

        at_response = raw.decode("utf-8", errors="replace").strip()
        at_pass = "OK" in at_response.upper()
        print(f"[資訊] COM Port 連線成功：{port_name}")
        if at_pass:
            print(f"[資訊] AT 指令 {at_command} 驗證 PASS")
        else:
            print(f"[錯誤] AT 指令 {at_command} 驗證 FAIL，回應：{at_response or '(empty)'}")
        return True, at_pass, at_response, ""
    except SerialException as exc:
        error_msg = f"COM Port 連線失敗：{port_name}，原因：{exc}"
        print(f"[錯誤] {error_msg}")
        return False, False, "", error_msg
    except Exception as exc:
        error_msg = f"無法檢查 COM Port：{port_name}，原因：{exc}"
        print(f"[錯誤] {error_msg}")
        return False, False, "", error_msg


def wait_and_press_enter_on_newest_cmd(
    target_exe_path: str,
    wait_seconds: int = 90,
    root_pid: Optional[int] = None,
) -> Tuple[bool, str]:
    print(
        f"[資訊] 等待 {wait_seconds} 秒後，將嘗試切到目標程式視窗（含子程序視窗），聚焦成功才送 Enter..."
    )
    time.sleep(wait_seconds)

    ps_script = r"""
$targetPath = [System.IO.Path]::GetFullPath($args[0]).ToLowerInvariant()
[int]$rootPid = 0
if ($args.Count -ge 2) { [int]::TryParse($args[1], [ref]$rootPid) | Out-Null }

function Get-DescendantPids([int]$pid) {
    if ($pid -le 0) { return @() }
    $all = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Select-Object ProcessId, ParentProcessId, ExecutablePath
    if (-not $all) { return @($pid) }

    $set = New-Object 'System.Collections.Generic.HashSet[int]'
    $queue = New-Object 'System.Collections.Generic.Queue[int]'
    [void]$set.Add($pid)
    $queue.Enqueue($pid)

    while ($queue.Count -gt 0) {
        $cur = $queue.Dequeue()
        foreach ($child in ($all | Where-Object { $_.ParentProcessId -eq $cur })) {
            $cid = [int]$child.ProcessId
            if ($set.Add($cid)) { $queue.Enqueue($cid) }
        }
    }
    return $set.ToArray()
}

$candidate = $null

if ($rootPid -gt 0) {
    $pids = Get-DescendantPids $rootPid
    if ($pids.Count -gt 0) {
        $candidate = Get-Process -ErrorAction SilentlyContinue |
            Where-Object { $_.MainWindowHandle -ne 0 } |
            Where-Object { $pids -contains $_.Id } |
            Sort-Object StartTime -Descending |
            Select-Object -First 1
    }
}

if (-not $candidate) {
    $candidate = Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.MainWindowHandle -ne 0 } |
        Where-Object {
            $_.Path -and
            ([System.IO.Path]::GetFullPath($_.Path).ToLowerInvariant() -eq $targetPath)
        } |
        Sort-Object StartTime -Descending |
        Select-Object -First 1
}

if (-not $candidate) { exit 1 }

$wshell = New-Object -ComObject WScript.Shell
$ok = $wshell.AppActivate($candidate.Id)
if (-not $ok) { exit 2 }

Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class WinApi {
    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);
}
"@

Start-Sleep -Milliseconds 500
[uint32]$fgPid = 0
$hwnd = [WinApi]::GetForegroundWindow()
if ($hwnd -eq [IntPtr]::Zero) { exit 4 }
[void][WinApi]::GetWindowThreadProcessId($hwnd, [ref]$fgPid)
if ($fgPid -ne [uint32]$candidate.Id) { exit 4 }

$wshell.SendKeys('{ENTER}')
exit 0
""".strip()

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            ps_script,
            str(target_exe_path),
            str(root_pid or 0),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode == 0:
        print("[資訊] 已聚焦目標視窗並送出 Enter")
        return True, "已聚焦目標視窗並送出 Enter"

    if result.returncode == 1:
        msg = "找不到目標 exe 的可見視窗，略過送出 Enter"
        print(f"[警告] {msg}")
        return False, msg
    elif result.returncode == 2:
        msg = "已找到符合條件的視窗，但無法切換到前景"
        print(f"[警告] {msg}")
        return False, msg
    elif result.returncode == 4:
        msg = "目標視窗尚未成功聚焦，已取消送出 Enter"
        print(f"[警告] {msg}")
        return False, msg

    msg = f"切換視窗並送 Enter 失敗，return_code={result.returncode}"
    print(f"[警告] {msg}")
    if result.stderr.strip():
        msg = f"{msg}，stderr={result.stderr.strip()}"
        print(f"[警告] 詳細錯誤：{result.stderr.strip()}")
    return False, msg


def wait_and_press_enter_on_foreground_window(
    wait_seconds: int = 120,
    focus_grace_seconds: int = 10,
) -> Tuple[bool, str]:
    print(
        f"[資訊] 等待 {wait_seconds} 秒後，請先用滑鼠點選你要按 Enter 的目標視窗。"
        f"系統將在 {focus_grace_seconds} 秒後對「目前前景視窗」送出 Enter..."
    )
    time.sleep(wait_seconds)

    # Give user time to focus the right window.
    if focus_grace_seconds > 0:
        time.sleep(focus_grace_seconds)

    ps_script = r"""
$wshell = New-Object -ComObject WScript.Shell

Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class WinApi {
    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();
}
"@

$hwnd = [WinApi]::GetForegroundWindow()
if ($hwnd -eq [IntPtr]::Zero) { exit 1 }

# Send Enter to current foreground window
$wshell.SendKeys('{ENTER}')
exit 0
""".strip()

    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode == 0:
        print("[資訊] 已對目前前景視窗送出 Enter")
        return True, "已對目前前景視窗送出 Enter"

    msg = "無法取得前景視窗，略過送出 Enter"
    print(f"[警告] {msg}")
    if result.stderr.strip():
        msg = f"{msg}，stderr={result.stderr.strip()}"
        print(f"[警告] 詳細錯誤：{result.stderr.strip()}")
    return False, msg


def main() -> int:
    parser = argparse.ArgumentParser(description="執行指定位置的檔案")
    parser.add_argument(
        "path",
        nargs="?",
        help="要執行的檔案路徑（可省略，省略時會進入互動輸入）",
    )
    args = parser.parse_args()

    file_path = args.path
    if not file_path:
        file_path = input("請輸入要執行的檔案完整路徑：").strip().strip('"')

    if not file_path:
        print("[錯誤] 路徑不可為空")
        return 1

    target_for_log = Path(file_path).expanduser().resolve()
    log_path = _create_log_path(target_for_log)

    com_port = input("請輸入要連線的 COM Port（例如 COM3）：").strip().upper()
    if not com_port:
        print("[錯誤] COM Port 不可為空")
        return 1

    at_command = input("請輸入 AT 指令（例如 ATi）：").strip()
    if not at_command:
        print("[錯誤] AT 指令不可為空")
        return 1

    rounds_raw = input("請輸入要重複執行的回合數（預設=1）：").strip()
    if not rounds_raw:
        rounds = 1
    else:
        try:
            rounds = int(rounds_raw)
            if rounds <= 0:
                raise ValueError
        except ValueError:
            print("[錯誤] 回合數必須為正整數")
            return 1

    final_code = 0
    success_rounds = 0
    failure_rounds = 0
    executed_rounds = 0
    for i in range(1, rounds + 1):
        print(f"[資訊] ===== 開始第 {i} 回合，共 {rounds} 回合 =====")
        com_connected, at_pass, at_response, com_error = check_com_connection_and_at(
            com_port, at_command
        )
        if not com_connected:
            _write_log(
                log_path=log_path,
                target=target_for_log,
                command_desc=f"[round {i}] precheck com port",
                return_code=1,
                com_port=com_port,
                com_connection_ok=False,
                at_command=at_command,
                at_response=at_response,
                at_pass=False,
                stdout="",
                stderr=com_error if com_error else "COM Port 連線失敗",
            )
            print(f"[警告] 第 {i} 回合 COM 檢查失敗，log：{log_path}")
            final_code = 1
            executed_rounds = i
            failure_rounds += 1
            time.sleep(1)
            continue

        if not at_pass:
            _write_log(
                log_path=log_path,
                target=target_for_log,
                command_desc=f"[round {i}] precheck at command",
                return_code=1,
                com_port=com_port,
                com_connection_ok=True,
                at_command=at_command,
                at_response=at_response,
                at_pass=False,
                stdout="",
                stderr="AT 指令驗證失敗（未收到 OK）",
            )
            print(f"[警告] 第 {i} 回合 AT 驗證失敗，log：{log_path}")
            final_code = 1
            executed_rounds = i
            failure_rounds += 1
            time.sleep(1)
            continue

        run_code = run_target_file(
            file_path,
            log_path,
            com_port,
            com_connected,
            at_command,
            at_response,
            at_pass,
            round_idx=i,
        )
        final_code = run_code
        executed_rounds = i

        post_ok, post_details = wait_and_press_enter_on_foreground_window(
            wait_seconds=60, focus_grace_seconds=10
        )
        _append_post_action_log(
            log_path,
            f"[round {i}/{rounds}] wait 60 sec, user focus window, then press Enter on foreground",
            post_ok,
            post_details,
        )

        # Round considered success only when both:
        # 1) target launched with return_code == 0
        # 2) we successfully sent Enter (post_ok)
        if run_code == 0 and post_ok:
            success_rounds += 1
        else:
            failure_rounds += 1

        if run_code != 0:
            print(f"[警告] 第 {i} 回合執行失敗（return_code={run_code}），將繼續下一回合")
            time.sleep(1)
            continue

        time.sleep(1)

    _append_test_summary_log(
        log_path=log_path,
        requested_rounds=rounds,
        executed_rounds=executed_rounds,
        success_rounds=success_rounds,
        failure_rounds=failure_rounds,
    )
    return final_code


if __name__ == "__main__":
    raise SystemExit(main())
