"""產生 AT_Testcases_Template.xlsx 範本檔。"""

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

OUTPUT = Path(__file__).resolve().parent / "testcases" / "AT_Testcases_Template.xlsx"

HEADER_FILL = PatternFill("solid", fgColor="4472C4")
HEADER_FONT = Font(color="FFFFFF", bold=True)


def _style_header_row(sheet, col_count: int) -> None:
    for col in range(1, col_count + 1):
        cell = sheet.cell(row=1, column=col)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
    sheet.freeze_panes = "A2"


def _autosize(sheet, col_count: int) -> None:
    for col in range(1, col_count + 1):
        letter = get_column_letter(col)
        max_len = 0
        for cell in sheet[letter]:
            if cell.value is not None:
                max_len = max(max_len, len(str(cell.value)))
        sheet.column_dimensions[letter].width = min(max(max_len + 2, 10), 50)


def _build_config_sheet(wb: Workbook) -> None:
    sheet = wb.create_sheet("Config", 0)
    headers = ["key", "value", "說明"]
    sheet.append(headers)
    rows = [
        ["port", "COM14", "Serial port（Windows: COM14；Ubuntu: /dev/ttyACM0）"],
        ["baudrate", "115200", "鮑率"],
        ["serial_timeout", "1.0", "pyserial read timeout 秒數"],
        ["rounds", "1", "測試回合數"],
        ["default_step_wait", "0", "步驟間預設等待秒數（各步驟 wait_after 可覆寫）"],
        ["reconnect_max_wait", "60", "reconnect_after=V 時，重連最多等待秒數"],
        ["test_id", "", "單一 test_id；留空且 test_ids 也留空時，執行全部 enabled=V 測項"],
        [
            "test_ids",
            "",
            "多個 test_id（逗號分隔）；有值時優先於 test_id",
        ],
    ]
    for row in rows:
        sheet.append(row)
    _style_header_row(sheet, len(headers))
    _autosize(sheet, len(headers))


def _build_steps_sheet(wb: Workbook) -> None:
    sheet = wb.create_sheet("Steps", 1)
    headers = [
        "enabled",
        "GROUP",
        "test_id",
        "step",
        "cmd",
        "cmd_type",
        "expect_type",
        "expect_value",
        "expect_label",
        "timeout",
        "idle_timeout",
        "wait_after",
        "reconnect_after",
        "run_on_failure",
        "note",
        "check_ttff",
    ]
    sheet.append(headers)

    # 與 GNSS_XTRA_ColdStart_STRESS_0001.py build_at_steps() 對應的範例
    rows = [
        [
            "V",
            "GNSS",
            "TC_GNSS_XTRA_ColdStart",
            1,
            'AT!ENTERCND="A710"',
            "at",
            "contains",
            "OK",
            "",
            5,
            "",
            0,
            "N",
            "N",
            "進入 CND 模式",
            "N",
        ],
        [
            "V",
            "GNSS",
            "TC_GNSS_XTRA_ColdStart",
            2,
            "AT!GPSCLRASSIST=1,1,1,1,1",
            "at",
            "contains",
            "OK",
            "",
            10,
            "",
            0,
            "N",
            "N",
            "清除 assist data",
            "N",
        ],
        [
            "V",
            "GNSS",
            "TC_GNSS_XTRA_ColdStart",
            3,
            "AT!GPSXTRASTATUS?",
            "at",
            "contains",
            "1980",
            "",
            30,
            "none",
            0,
            "N",
            "N",
            "XTRA 應為初始狀態",
            "N",
        ],
        [
            "V",
            "GNSS",
            "TC_GNSS_XTRA_ColdStart",
            4,
            "AT!GPSXTRAINITDNLD",
            "at",
            "contains",
            "Xtra command sent successfully",
            "",
            60,
            "none",
            0,
            "N",
            "N",
            "觸發 XTRA 下載",
            "N",
        ],
        [
            "V",
            "GNSS",
            "TC_GNSS_XTRA_ColdStart",
            5,
            "AT!GPSXTRASTATUS?",
            "at",
            "custom",
            "current_year_month",
            "",
            30,
            "none",
            0,
            "N",
            "N",
            "XTRA 日期應為今年今月",
            "N",
        ],
        [
            "V",
            "GNSS",
            "TC_GNSS_XTRA_ColdStart",
            6,
            "AT!GPSFIX=1,255,255",
            "at",
            "contains",
            "OK",
            "",
            30,
            "",
            5,
            "N",
            "N",
            "Cold start fix",
            "N",
        ],
        [
            "V",
            "GNSS",
            "TC_GNSS_XTRA_ColdStart",
            7,
            "AT!GPSSTATUS?",
            "at",
            "custom",
            "gps_status_ttff",
            "",
            30,
            "none",
            0,
            "N",
            "N",
            "檢查 TTFF",
            "V",
        ],
        [
            "V",
            "GNSS",
            "TC_GNSS_XTRA_ColdStart",
            8,
            "AT!GPSEND=0",
            "at",
            "contains",
            "OK",
            "",
            10,
            "",
            0,
            "N",
            "V",
            "收尾；失敗時仍執行",
            "N",
        ],
        [
            "V",
            "Smoke",
            "TC_Smoke_AT",
            1,
            "AT",
            "at",
            "contains",
            "OK",
            "",
            2,
            "",
            0,
            "N",
            "N",
            "基本握手",
            "N",
        ],
        [
            "V",
            "Smoke",
            "TC_Smoke_AT",
            2,
            "ATI",
            "at",
            "regex",
            "OK",
            "",
            2,
            "",
            0,
            "N",
            "N",
            "查詢版本",
            "N",
        ],
        [
            "V",
            "Shell",
            "TC_Shell_Smoke",
            1,
            "echo at_framework_shell_ok",
            "shell",
            "contains",
            "at_framework_shell_ok",
            "",
            5,
            "",
            0,
            "N",
            "N",
            "本機 shell 煙霧測試；可單獨 -t 執行、不必接模組",
            "N",
        ],
    ]
    for row in rows:
        sheet.append(row)
    _style_header_row(sheet, len(headers))
    _autosize(sheet, len(headers))


def _build_reference_sheet(wb: Workbook) -> None:
    sheet = wb.create_sheet("Reference", 2)
    headers = ["欄位", "說明", "範例"]
    sheet.append(headers)
    rows = [
        ["enabled", "A 欄。V=執行 / N=略過", "V"],
        ["GROUP", "B 欄。分類標籤（執行時不影響；可空）", "GNSS"],
        ["test_id", "C 欄。測試案例 ID，同 ID 多列組成一個序列", "TC_GNSS_XTRA_ColdStart"],
        ["step", "D 欄。步驟順序（整數）", "1"],
        ["cmd", "E 欄。AT 或 shell 指令（AT 不含 \\r\\n；簡訊本文結尾寫 {CTRLZ}）", "Test SMS{CTRLZ}"],
        ["cmd_type", "F 欄。空白或 at=經 serial 送 AT；shell=本機（Ubuntu bash）執行", "at / shell"],
        ["expect_type", "G 欄。contains | regex | custom", "contains"],
        ["expect_value", "H 欄。預期內容或 custom 名稱", "OK / current_year_month"],
        ["expect_label", "I 欄。報告顯示用（可空）", "TTFF (sec) < 5"],
        ["timeout", "J 欄。此步驟最長等待秒數", "30"],
        ["idle_timeout", "K 欄。空=0.3；none=等到 timeout", "none"],
        ["wait_after", "L 欄。本步驟完成後等待秒數", "5"],
        ["reconnect_after", "M 欄。V=等待後關閉並重連 serial（模組會重啟時用）", "V"],
        ["run_on_failure", "N 欄。V=前步失敗時仍執行此步", "V"],
        ["note", "O 欄。備註", ""],
        ["check_ttff", "P 欄。V=額外寫 TTFF 判定 log", "V"],
        ["", "", ""],
        ["custom 名稱", "說明", ""],
        ["current_year_month", "回應含今年+空格+兩位數月份", ""],
        ["gps_status_ttff", "OK 且 TTFF < 5", ""],
        ["gps_status_ttff:3", "OK 且 TTFF < 3", ""],
    ]
    for row in rows:
        sheet.append(row)
    _style_header_row(sheet, len(headers))
    _autosize(sheet, len(headers))


def create_template(output: Path = OUTPUT) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    wb.remove(wb.active)
    _build_config_sheet(wb)
    _build_steps_sheet(wb)
    _build_reference_sheet(wb)
    wb.save(output)
    return output


def main() -> None:
    path = create_template()
    print(f"已建立範本: {path}")


if __name__ == "__main__":
    main()
