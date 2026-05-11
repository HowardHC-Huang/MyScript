import serial
import time
from datetime import datetime

def run_at_reset_test():
    # 1. Initialization & User Input
    port = input("Enter DUT-Modem COM port (e.g. COM9): ").upper()
    try:
        total_rnd = int(input("Enter total TEST ROUNDS: "))
        threshold_ms = int(input("Enter threshold in ms (mark if exceeded): "))
        retry_wait_sec = int(input("Enter retry wait seconds for failed rounds: "))
    except ValueError:
        print("Invalid input. Please enter a number.")
        return

    # 2. Setup Logging with Timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"AT_Reset_Python_Test_{timestamp}.log"
    
    def log_and_print(message):
        print(message)
        with open(log_filename, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")

    log_and_print(f"Starting test on {port} for {total_rnd} rounds.")
    log_and_print(f"Threshold: {threshold_ms} ms (exceeded => MARK)")
    log_and_print(f"Retry wait: {retry_wait_sec} seconds (failed round auto-retry)")
    log_and_print("Max retry per round: 3")
    reset_times_ms = []
    exceed_count = 0
    total_retry_count = 0
    failed_round_count = 0

    # 3. Main Loop
    # Python 邏輯：執行 N 次 reset，並在每次 reset 後等待重新連線
    for i in range(1, total_rnd + 1):
        log_and_print(f"\n--- Round: {i} ---")
        attempt = 1
        round_done = False

        while not round_done:
            try:
                log_and_print(f"Round {i} attempt {attempt} started.")

                # --- A. Connect and Execute Commands ---
                with serial.Serial(port, 115200, timeout=2) as ser:
                    log_and_print(f"Successfully connected to {port}. Starting testing...")

                    # Send ATi
                    time.sleep(0.3)
                    log_and_print("Sending 'ATi...'")
                    ser.write(b"ATi\r\n")
                    response = ser.read_until(b"OK").decode('utf-8', errors='ignore')
                    if "OK" not in response:
                        raise RuntimeError("ATi failed")

                    time.sleep(1)

                    # Send AT^reset and start timing
                    log_and_print("Sending AT^reset...")
                    ser.write(b"AT^reset\r\n")
                    reset_response = ser.read_until(b"OK").decode("utf-8", errors="ignore")
                    if "OK" not in reset_response:
                        raise RuntimeError("AT^reset failed")

                    # 記錄起始時間 (Start time)
                    var_start = time.perf_counter()

                # Serial port closes automatically after 'with' block
                log_and_print("Waiting for device to disconnect...")
                time.sleep(2) # 給予設備斷開反應時間

                # --- B. Reconnect Loop (Wait for Boot-up) ---
                log_and_print("Device disconnected. Re-trying connection...")
                while True:
                    try:
                        # 嘗試重新打開 Port
                        with serial.Serial(port, 115200, timeout=1) as ser:
                            # 重新連線成功，計算結束時間 (End time)
                            var_end = time.perf_counter()
                            t_spent_ms = int((var_end - var_start) * 1000)
                            reset_times_ms.append(t_spent_ms)
                            is_exceeded = t_spent_ms > threshold_ms
                            mark = "MARK (EXCEEDED)" if is_exceeded else "PASS"
                            if is_exceeded:
                                exceed_count += 1

                            log_and_print(
                                f"====--> Round: {i}, AT^RESET time: {t_spent_ms} ms, "
                                f"Threshold: {threshold_ms} ms, Result: {mark} <--===="
                            )
                            round_done = True
                            break # 跳出 reconnect while
                    except (serial.SerialException, PermissionError):
                        # 設備還沒開好或 Port 還沒枚舉完成
                        time.sleep(1)
                        continue
            except (serial.SerialException, PermissionError, RuntimeError) as e:
                if attempt >= 4:
                    failed_round_count += 1
                    log_and_print(
                        f"Round {i} reached max retry limit (3). "
                        f"Last error: {e}. Mark this round as FAILED."
                    )
                    break

                total_retry_count += 1
                log_and_print(
                    f"Round {i} attempt {attempt} failed: {e}. "
                    f"Auto-retry after {retry_wait_sec} seconds."
                )
                time.sleep(retry_wait_sec)
                attempt += 1
                continue

    if reset_times_ms:
        avg_time_ms = sum(reset_times_ms) / len(reset_times_ms)
        max_time_ms = max(reset_times_ms)
        min_time_ms = min(reset_times_ms)
        log_and_print("\n=== AT^RESET Time Statistics ===")
        log_and_print(f"Successful rounds: {len(reset_times_ms)}/{total_rnd}")
        log_and_print(f"Average time: {avg_time_ms:.2f} ms")
        log_and_print(f"Max time: {max_time_ms} ms")
        log_and_print(f"Min time: {min_time_ms} ms")
        log_and_print(f"Exceeded threshold rounds: {exceed_count}")
        log_and_print(f"Total retry count: {total_retry_count}")
        log_and_print(f"Failed rounds: {failed_round_count}")
    else:
        log_and_print("\n=== AT^RESET Time Statistics ===")
        log_and_print("No successful rounds. No statistics available.")
        log_and_print(f"Failed rounds: {failed_round_count}")

    log_and_print("\nTest finished. Log saved to: " + log_filename)

if __name__ == "__main__":
    run_at_reset_test()