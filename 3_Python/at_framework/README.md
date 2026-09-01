# AT Framework 操作手冊

本文件供**測試人員**學習與操作 `at_framework`：透過 **Excel 定義 AT 測試步驟**，由 Python 自動連線模組、發送指令、比對回應並產出報告。

---

## 1. 這是什麼？

`at_framework` 是一套 **AT 指令自動測試工具**：

- **測試人員**：在 Excel 裡編輯測項（指令、預期結果、逾時等），不需寫程式。
- **框架程式**：讀取 Excel → 透過 COM Port 與模組通訊 → 逐步執行並記錄 PASS/FAIL。

適用情境：LTE / GNSS 等模組的功能測試、冒煙測試（Smoke Test）、多回合壓力測試。

---

## 2. 目錄結構與各檔案用途

```
at_framework/
├── README.md                 ← 本操作手冊
├── requirements.txt          ← Python 套件清單（安裝用）
│
├── run_from_excel.py         ← 【主程式】測試人員最常執行的入口
├── create_template.py        ← 產生 / 重建 Excel 範本檔
│
├── at_core.py                ← 核心引擎：送 AT、收回應、跑步驟序列、寫 Log/CSV
├── excel_loader.py           ← 讀取 Excel，轉成框架可執行的步驟清單
├── custom_expects.py         ← 進階預期判斷（如 TTFF、年月檢查）；一般由工程師維護
├── __init__.py               ← 套件匯出定義（給其他 Python 腳本 import 用）
│
└── testcases/
    ├── AT_Testcases_Template.xlsx   ← 預設 Excel 範本，複製後編輯使用
    └── IE13_AT_Testcases.xlsx       ← IE13 專案測項檔（範例）
```

### 各檔案說明

| 檔案 | 誰會用到 | 用途 |
|------|----------|------|
| `run_from_excel.py` | 測試人員 | 執行測試的主程式。指定 COM Port、test_id、回合數等。 |
| `testcases/AT_Testcases_Template.xlsx` | 測試人員 | 所有測項定義在此。可複製成新檔（如 `MyProject_Testcases.xlsx`）再修改。 |
| `create_template.py` | 測試 / 工程師 | 若範本遺失或需重置，執行後會重新產生 `AT_Testcases_Template.xlsx`。 |
| `at_core.py` | 工程師 | AT 送收、逾時、步驟序列、Logger、CSV 結果紀錄。通常不需手動修改。 |
| `excel_loader.py` | 工程師 | 解析 Excel 欄位、驗證格式、載入 `test_id` 對應的步驟。 |
| `custom_expects.py` | 工程師 | 定義 Excel 中 `expect_type=custom` 時的判斷邏輯（如 GNSS TTFF）。 |
| `requirements.txt` | 測試人員 | 列出需安裝的套件：`pyserial`、`openpyxl`。 |

### 執行流程（概念）

```
Excel 測項檔
    ↓  excel_loader.py 讀取
步驟清單（cmd、expect、timeout…）
    ↓  at_core.py 執行
COM Port ↔ 模組
    ↓
.log（詳細紀錄）+ .csv（每步驟結果）
```

---

## 3. 環境準備（首次使用）

### 3.1 需求

- Windows 電腦
- Python 3.x（建議 3.8 以上）
- 模組已透過 USB 連接，且裝置管理員中可看到 COM Port（如 `COM14`）
- Microsoft Excel 或相容試算表軟體（用於編輯測項）

### 3.2 安裝套件

開啟 **PowerShell** 或 **命令提示字元**，進入 `at_framework` 資料夾：

```powershell
cd C:\Users\Howard_huang\Desktop\MyScript\3_Python\at_framework
pip install -r requirements.txt
```

### 3.3 確認範本存在

若 `testcases\AT_Testcases_Template.xlsx` 不存在，執行：

```powershell
python create_template.py
```

---

## 4. Excel 測項檔說明

預設檔案：`testcases/AT_Testcases_Template.xlsx`

內含 **3 個工作表**：

| 工作表 | 用途 |
|--------|------|
| **Config** | 全域設定：COM Port、鮑率、預設 test_id、回合數等 |
| **Steps** | 測試步驟（**主要編輯區**） |
| **Reference** | 欄位說明與 `custom` 類型對照表（查閱用） |

### 4.1 Config 工作表

| key | 範例值 | 說明 |
|-----|--------|------|
| `port` | `COM14` | Serial port（執行時可用命令列 `-p` 覆寫） |
| `baudrate` | `115200` | 鮑率 |
| `serial_timeout` | `1.0` | 底層 serial 讀取逾時（秒） |
| `rounds` | `1` | 測試回合數（**每個** test_id 都會跑這麼多回合） |
| `default_step_wait` | `0` | 每步完成後預設等待秒數（各步驟 `wait_after` 可覆寫） |
| `reconnect_max_wait` | `60` | 步驟 `reconnect_after=V` 時，重連最多等待秒數 |
| `test_id` | （留空） | 單一 test_id；**留空且 `test_ids` 也留空時，自動執行全部 `enabled=V` 測項** |
| `test_ids` | （留空） | 多個 test_id（逗號分隔）；有值時優先於 `test_id` |

### 4.2 Steps 工作表（一列 = 一個步驟）

同一個 `test_id` 的多列會組成**一組完整測試**；依 `step` 欄位數字由小到大執行。

**布林欄位填寫規則：**

- `V` = 啟用 / 是 / 要執行
- `N` = 停用 / 否 / 不執行
- 適用欄位：`enabled`、`reconnect_after`、`run_on_failure`、`check_ttff`
- 為了相容舊檔，程式目前仍可讀取 `Y`，但**新建或修改時請統一使用 `V`**

| 欄位 | 必填 | 說明 | 範例 |
|------|------|------|------|
| `test_id` | 是 | 測試案例 ID | `TC_Smoke_AT` |
| `step` | 是 | 步驟順序（整數） | `1` |
| `enabled` | 是 | `V` 執行 / `N` 略過 | `V` |
| `cmd` | 是 | AT 指令（**不要**加 `\r\n`）。簡訊本文結尾寫 `{CTRLZ}`，見 4.2.1 | `AT` |
| `expect_type` | 是 | 預期比對方式（見下節） | `contains` |
| `expect_value` | 視類型 | 預期內容或 custom 名稱 | `OK` |
| `expect_label` | 否 | 報告上顯示的預期說明 | `TTFF (sec) < 5` |
| `timeout` | 是 | 此步驟最長等待秒數 | `30` |
| `idle_timeout` | 否 | 空白=0.3 秒；`none`=等到 timeout 為止 | `none` |
| `wait_after` | 否 | 本步驟完成後等待秒數 | `5` |
| `reconnect_after` | 否 | `V`=等待後關閉並重連 COM（指令會觸發模組重啟時使用） | `V` |
| `run_on_failure` | 否 | 前步失敗時是否仍執行此步：`V`/`N` | `N` |
| `check_ttff` | 否 | `V` 時額外寫入 TTFF 判定 log | `V` |
| `note` | 否 | 備註 | `基本握手` |

### 4.2.1 簡訊輸入（`>` prompt 與 `{CTRLZ}`）

`AT+CMGW` / `AT+CMGS` 這類指令是**兩階段**：先送指令等到 `>`，再送本文並以 Ctrl+Z 結束。

Excel `cmd` 寫 `{CTRLZ}` 時，框架會改送 Ctrl+Z（`0x1A`），**且不再自動加 `\r\n`**。標記請全大寫、含大括號，例如 `Test SMS{CTRLZ}`。

**完整寫入草稿範例（`AT+CMGW`）：**

| test_id | step | enabled | cmd | expect_type | expect_value | timeout | idle_timeout | note |
|---------|------|---------|-----|-------------|--------------|---------|--------------|------|
| TC_SMS_CMGW | 1 | V | `AT+CMGF=1` | contains | `OK` | 5 | （空白） | 切文字模式 |
| TC_SMS_CMGW | 2 | V | `AT+CMGW="0939812986",129,"STO UNSENT"` | contains | `>` | 5 | `none` | 出現輸入提示符 |
| TC_SMS_CMGW | 3 | V | `Test SMS{CTRLZ}` | contains | `+CMGW:` | 10 | `none` | 本文 + Ctrl+Z；成功會回 `+CMGW: <index>` 再 `OK` |

- step 2 / 3 的 `idle_timeout` 建議填 `none`，避免提示符或寫入結果還沒到就被當成結束。
- step 3 的 `expect_value` 用 `+CMGW:` 即可（index 每次可能不同）；若要連 `OK` 一起確認，可改 `regex`：`\+CMGW:\s*\d+[\s\S]*OK`。
- `{CTRLZ}` 只能寫在**本文那一步**，不要加在 `AT+CMGW=...` 那一列。
- 若 step 3 失敗，模組可能仍停在 `>`；請勿接著跑其他測項，改送 ESC 或重開模組。

### 4.3 預期比對方式（expect_type）

| expect_type | expect_value 填什麼 | 判定方式 |
|-------------|-------------------|----------|
| `contains` | 任意字串 | 回應中**包含**該字串即 PASS |
| `regex` | 正則表達式 | 回應符合該 pattern 即 PASS |
| `custom` | 預先定義的名稱 | 由 `custom_expects.py` 執行進階邏輯 |

**內建 custom 名稱**（詳見 Excel 的 Reference 工作表）：

| expect_value | 說明 |
|--------------|------|
| `current_year_month` | 回應含「今年 + 空格 + 兩位數月份」（如 `2026 06`） |
| `gps_status_ttff` | 回應含 `OK`，且 TTFF < 5 秒 |
| `gps_status_ttff:3` | 同上，但 TTFF 門檻改為 3 秒 |

> 若需要新的 `custom` 判斷，請洽工程師在 `custom_expects.py` 新增。

### 4.3.1 使用 `regex` 時的跳脫字元

`expect_type=regex` 時，框架使用 Python 標準正則（`re.compile`）。  
**不是**整段 pattern 前面都要加 `\`；只有當某字元在 regex 裡有**特殊意義**、而你又想把它當**普通文字**比對時，才在該字元前加 `\`。

#### 需要跳脫（前面加 `\`）的字元

以下字元在 regex 中有特殊用途，要比對「字面意義」時需跳脫：

| 字元 | regex 中的意義 | AT 常見範例 | 寫法 |
|------|---------------|-------------|------|
| `+` | 前一字元重複 1 次以上 | `+CCID:`、`+CSUS:` | `\+CCID:` |
| `?` | 前一字元出現 0 或 1 次 | `AT+CSUS?`、`AT!GPSSTATUS?` | `AT\+CSUS\?` |
| `.` | 任意一個字元 | `Revision: 1.0` | `1\.0` |
| `*` | 前一字元重複 0 次以上 | 較少直接用 | `\*` |
| `^` | 字串開頭 | 較少直接用 | `\^` |
| `$` | 字串結尾 | 較少直接用 | `\$` |
| `\` | 跳脫字元本身 | 極少 | `\\` |
| `( )` | 分組 | 較少直接用 | `\(` `\)` |
| `[ ]` | 字元集合 | 較少直接用 | `\[` `\]` |
| `{ }` | 重複次數 | `\d{19}` 中的 `{}` 是語法，勿亂跳脫 | 見下方說明 |
| `|` | 或 | 較少直接用 | `\|` |

> `{` `}` 在「重複語法」中是有意義的（如 `\d{19,20}`），不要整段都加 `\`；僅在要比對字面大括號時才跳脫。

#### 不需要跳脫的字元（直接寫）

以下在 AT 回應中很常見，**可直接寫入** `expect_value`：

| 類別 | 字元／範例 |
|------|-----------|
| 英文字母、數字 | `OK`、`ATI`、`89886019137837568521` |
| 空白、換行 | 用 regex 語法 `\s`、`\r`、`\n` 描述即可 |
| 標點（多數） | `:` `,` `"` `=` `-` `_` `/` |
| 驚嘆號 | `AT!ENTERCND`、`AT!GPSSTATUS` 中的 `!` **不用**加 `\` |

#### 實用範例（可直接貼到 Excel `expect_value`）

| 欲比對的回應片段 | 建議 `expect_value` |
|-----------------|---------------------|
| `+CCID: "89886019137837568521",""` | `\+CCID:\s*"\d{19,20}",""` |
| `+CSUS: 0` 後接 `OK` | `\+CSUS:\s*0` 或改用 `contains`：`+CSUS: 0` |
| `AT!GPSSTATUS?` 回應含 OK | `OK`（`contains`）或 `TTFF[\s\S]*OK`（`regex`） |
| 固定字串 `Manufacturer: Sierra Wireless` | 建議用 `contains`，不必用 regex |

#### `contains` vs `regex` 怎麼選？

| 情境 | 建議 |
|------|------|
| 只確認回應「包含某段文字」 | `contains`（最簡單，不用管跳脫） |
| 回應以 `+` 開頭的 URC | `contains` 填 `+CCID:`；或 `regex` 用 `\+CCID:` |
| ICCID、電話號碼等長度不固定 | `regex` + `\d+`、`\d{19,20}` |
| 不確定要不要跳脫 | **優先改用 `contains`** |

#### 常見錯誤

| 錯誤寫法 | 原因 |
|----------|------|
| `+CSUS: 0`（regex） | 開頭 `+` 會觸發 `nothing to repeat` 錯誤 |
| 在 Excel 填 `\\r\\n` 想比對換行 | 通常多餘；實際回應是真實換行，用 `\s` 或 `[\s\S]*` 即可 |
| 每個字元都加 `\` | 不必要，且會讓 pattern 難維護 |

驗證 regex 是否正確：改完 Excel 後執行 `python run_from_excel.py -x <你的檔案> --validate`，格式錯誤會在執行前就報錯。

### 4.4 範本內建的測試案例

| test_id | 說明 |
|---------|------|
| `TC_Smoke_AT` | 簡單 `AT`、`ATI` 握手，適合第一次驗證環境 |
| `TC_GNSS_XTRA_ColdStart` | GNSS XTRA 冷開機完整流程（8 步） |

---

## 5. 操作步驟（測試人員日常流程）

### 步驟 1：確認硬體連線

模組接好 USB 後，在裝置管理員確認 COM Port 號碼，或執行：

```powershell
python run_from_excel.py --list-ports
```

### 步驟 2：編輯 Excel

1. 複製 `testcases\AT_Testcases_Template.xlsx` 為自己的檔名（建議保留原範本不動）。
2. 在 **Config** 修改 `port`、`test_id` 等。
3. 在 **Steps** 新增或修改測試步驟。
4. **存檔後關閉 Excel**（避免檔案被鎖定無法讀取）。

### 步驟 3：驗證 Excel 格式（建議每次改完都跑）

```powershell
python run_from_excel.py --validate
python run_from_excel.py --list-tests

python run_from_excel.py -x testcases\IE13_AT_Testcases.xlsx --validate
python run_from_excel.py -x testcases\IE13_AT_Testcases.xlsx --list-tests
```

- `--validate`：檢查欄位、數值、custom 名稱是否正確。
- `--list-tests`：列出所有 `enabled=V` 的 `test_id`。

### 步驟 4：執行測試

**最簡單（使用 Config 裡的設定）：**

```powershell
python run_from_excel.py -p COM14
```

**指定測項與回合數：**

```powershell
python run_from_excel.py -p COM14 -t TC_Smoke_AT -n 3
```

### 步驟 4a：指定要使用的 Excel 檔

用 `-x` 或 `--excel` 指定測項檔路徑。未指定時，預設使用 `testcases\AT_Testcases_Template.xlsx`。

**基本用法：**

```powershell
python run_from_excel.py -x testcases\MyProject_Testcases.xlsx -p COM14
```

**實際範例：執行 `testcases\IE13_AT_Testcases.xlsx`**

先進入 `at_framework` 目錄，再指定該 Excel 與 COM Port（請將 `COM14` 改為實際埠號）：

```powershell
cd C:\Users\Howard_huang\Desktop\MyScript\3_Python\at_framework
python run_from_excel.py -x testcases\IE13_AT_Testcases.xlsx -p COM14
```

指定 test_id 與回合數（此檔目前啟用的測項為 `TC_Smoke_AT`）：

```powershell
python run_from_excel.py -x testcases\IE13_AT_Testcases.xlsx -p COM14 -t TC_Smoke_AT -n 1
```

執行前先驗證或查看測項：

```powershell
python run_from_excel.py -x testcases\IE13_AT_Testcases.xlsx --validate
python run_from_excel.py -x testcases\IE13_AT_Testcases.xlsx --list-tests
```

若 **Config** 已設定好 `port`、`test_id`，可省略 `-p` / `-t`：

```powershell
python run_from_excel.py -x testcases\IE13_AT_Testcases.xlsx
```

> 未在命令列或 Config 指定 `port` 時，程式會提示輸入 COM Port。

**同時指定 test_id 與回合數（通用寫法）：**

```powershell
python run_from_excel.py -x testcases\MyProject_Testcases.xlsx -p COM14 -t TC_Smoke_AT -n 1
```

**指定 Excel 並一次跑多個 test_id：**

```powershell
python run_from_excel.py -x testcases\MyProject_Testcases.xlsx -p COM14 -t TC_Smoke_AT,TC_GNSS_XTRA_ColdStart
```

**路徑寫法：**

| 寫法 | 範例 |
|------|------|
| 相對路徑（相對於 `at_framework` 目錄） | `-x testcases\MyTest.xlsx` |
| 絕對路徑 | `-x D:\TestPlan\AT_Testcases.xlsx` |

**執行前建議：**

```powershell
python run_from_excel.py -x testcases\MyProject_Testcases.xlsx --validate
python run_from_excel.py -x testcases\MyProject_Testcases.xlsx --list-tests
```

**注意事項：**

- 執行時請**關閉**正在開啟該 Excel 的視窗，避免檔案被鎖定。
- Excel 需包含 **Config**、**Steps** 工作表（格式與範本相同）。
- 若未加 `-t`，會依該 Excel **Config** 的 `test_ids` 或 `test_id` 決定跑哪些測項；兩者皆留空時，**等同 `--all`**（跑全部 `enabled=V` 測項）。
- `-p`、`-n`、`-b` 等參數可覆寫 Config 中的對應設定。

### 步驟 4b：一次執行多個 test_id

若要**同一趟連線**依序跑 `TC_Smoke_AT` 和 `TC_GNSS_XTRA_ColdStart`，可用以下任一方式。

**方式 A：命令列指定（最直覺，不需改 Excel）**

```powershell
# 逗號分隔
python run_from_excel.py -p COM14 -t TC_Smoke_AT,TC_GNSS_XTRA_ColdStart

# 或重複 -t
python run_from_excel.py -p COM14 -t TC_Smoke_AT -t TC_GNSS_XTRA_ColdStart
```

**方式 B：Excel Config 設定 `test_ids`**

在 **Config** 工作表新增或修改：

| key | value |
|-----|-------|
| `test_ids` | `TC_Smoke_AT,TC_GNSS_XTRA_ColdStart` |

然後執行（不必再加 `-t`）：

```powershell
python run_from_excel.py -p COM14
```

> `test_ids` 有值時會**優先於** `test_id` 單欄設定。若只想跑一個測項，請清空 `test_ids` 或改用 `-t` 覆寫。

**方式 C：跑 Excel 內所有啟用的測項**

```powershell
python run_from_excel.py -p COM14 --all
```

**方式 D：Config 留空（等同方式 C）**

將 Config 的 `test_id` 與 `test_ids` **都留空**，直接執行：

```powershell
python run_from_excel.py -p COM14
```

會自動執行 Steps 中所有 `enabled=V` 的 test_id，效果與 `--all` 相同。

會依 Steps 工作表中 `enabled=V` 的 test_id **出現順序**執行（目前範本順序：`TC_GNSS_XTRA_ColdStart` → `TC_Smoke_AT`）。  
若希望先跑 Smoke 再跑 GNSS，請用方式 A/B **明確指定順序**。

**執行順序與失敗行為**

- 多個 test_id 會在**同一條 COM 連線**內依序執行：先跑完 test A 的所有回合，再跑 test B。
- 某個 test_id 失敗時，**仍會繼續**執行後續 test_id；最後摘要會分別列出各 test_id 的 PASS/FAIL。
- 建議長流程（GNSS）放後面、短流程（Smoke）放前面，方便先確認連線是否正常。

### 步驟 5：查看結果

執行完成後，在 `at_framework` 資料夾會產生：

| 輸出檔 | 內容 |
|--------|------|
| `AT_Excel_<test_id>_<時間>.log` | 單一 test_id 時的完整紀錄 |
| `AT_Excel_<test_id>_<時間>.csv` | 單一 test_id 時的結構化結果 |
| `AT_Excel_Suite_<時間>.log` | **多個** test_id 合併的完整紀錄 |
| `AT_Excel_Suite_<時間>.csv` | **多個** test_id 合併的 CSV（含 `test_id` 欄位） |

也可用 `-o`、`-d` 自訂輸出路徑：

```powershell
python run_from_excel.py -p COM14 -t TC_Smoke_AT -o D:\Logs\test.log -d D:\Logs\test.csv
```

---

## 6. 命令列參數一覽

| 參數 | 說明 |
|------|------|
| `-x`, `--excel` | Excel 測項檔路徑（預設：`testcases/AT_Testcases_Template.xlsx`） |
| `-t`, `--test-id` | 要執行的 test_id；可重複 `-t` 或單一值內逗號分隔多個 |
| `--all` | 執行 Excel 內所有 `enabled=V` 的 test_id（勿與 `-t` 同時使用） |
| `-p`, `--port` | COM Port，如 `COM14` |
| `-n`, `--rounds` | 測試回合數 |
| `-b`, `--baudrate` | 鮑率 |
| `--serial-timeout` | Serial 讀取逾時（秒） |
| `--default-step-wait` | 步驟間預設等待秒數 |
| `-o`, `--log` | Log 檔路徑 |
| `-d`, `--data` | 結果 CSV 路徑 |
| `--list-ports` | 列出可用 COM Port 後結束 |
| `--list-tests` | 列出 Excel 內啟用的 test_id 後結束 |
| `--validate` | 只驗證 Excel 格式，不連硬體 |

> 命令列參數會**覆寫** Excel Config 中的對應設定。  
> test_id 優先順序：`--all` > `-t` > Config `test_ids` > Config `test_id` > **全部啟用測項**（`test_id` 與 `test_ids` 皆留空時，等同 `--all`）。

---

## 7. 如何新增一組測試

以新增 `TC_MyTest` 為例：

1. 在 **Steps** 工作表新增多列，`test_id` 皆填 `TC_MyTest`。
2. `step` 從 `1` 開始遞增。
3. 每列填好 `cmd`、`expect_type`、`expect_value`、`timeout`。
4. 在 **Config** 將 `test_id` 改為 `TC_MyTest`（或執行時用 `-t TC_MyTest`）。
5. 執行 `--validate` 確認無誤後再跑測試。

**範例（兩步握手）：**

| test_id | step | enabled | cmd | expect_type | expect_value | timeout |
|---------|------|---------|-----|-------------|--------------|---------|
| TC_MyTest | 1 | V | AT | contains | OK | 2 |
| TC_MyTest | 2 | V | ATI | contains | OK | 2 |

簡訊寫入請見 **4.2.1**（`>` 與 `{CTRLZ}`）。

---

## 8. 失敗時的行為

- 某步驟 **FAIL**：預設**停止**該回合後續步驟。
- 若後續步驟的 `run_on_failure` 設為 `V`，則前步失敗後**仍會執行**該步（例如收尾指令 `AT!GPSEND=0`）。
- 多回合測試：每回合獨立執行；程式結束時會印出成功回合數摘要。
- 程式結束碼：`0` = 全部回合通過；`1` = 至少一回合失敗或連線錯誤。

---

## 9. 常見問題

### Q1：執行時說找不到 COM Port？

- 確認 USB 已接好、驅動已安裝。
- 用 `--list-ports` 查看實際埠號，可能與 Config 不同（重插 USB 後埠號可能改變）。
- 確認沒有其他程式（PuTTY、Tera Term）佔用該 COM Port。

### Q2：Excel 驗證失敗？

- 對照錯誤訊息中的**列號**檢查 Steps 工作表。
- 確認必填欄位未空白、`enabled`/`reconnect_after`/`run_on_failure`/`check_ttff` 為 V 或 N。
- `expect_type=custom` 時，`expect_value` 必須是 Reference 表中列出的名稱。

### Q3：讀取 Excel 失敗 / 權限錯誤？

- 關閉正在開啟該 Excel 的視窗後再執行。
- 避免 OneDrive / 網路磁碟同步造成檔案鎖定。

### Q4：指令逾時 FAIL？

- 加大該步驟的 `timeout`。
- 慢速指令（如 XTRA 下載）將 `idle_timeout` 設為 `none`。
- 步驟間需要等待時，調整 `wait_after`。
- 指令會導致模組重啟時，設 `reconnect_after=V`（搭配足夠的 `wait_after`）；框架會在等待後關閉並重連 serial，最多等待 Config 的 `reconnect_max_wait` 秒。

### Q5：長時間測試中電腦休眠？

- 筆電長時間測試請關閉休眠/睡眠，或使用公司規範的防休眠方式。
- 參考專案根目錄相關提醒文件。

### Q6：如何暫時跳過某個步驟？

- 將該列 `enabled` 改為 `N`，不必刪除整列。

---

## 10. 測試人員 vs 工程師分工

| 工作 | 測試人員 | 工程師 |
|------|----------|--------|
| 編輯 Excel 測項 | ✓ | |
| 執行 `run_from_excel.py` | ✓ | |
| 解讀 .log / .csv 結果 | ✓ | |
| 新增 `custom` 預期判斷 | | ✓（`custom_expects.py`） |
| 修改送收邏輯、重連、URC | | ✓（`at_core.py`） |
| 整合 pytest / CI | | ✓ |

---

## 11. 快速參考（第一次上手）

```powershell
# 1. 進入目錄並安裝套件（僅首次）
cd C:\Users\Howard_huang\Desktop\MyScript\3_Python\at_framework
pip install -r requirements.txt

# 2. 查 COM Port
python run_from_excel.py --list-ports

# 3. 驗證 Excel（預設範本）
python run_from_excel.py --validate

# 3b. 驗證 / 查看 IE13 測項檔
python run_from_excel.py -x testcases\IE13_AT_Testcases.xlsx --validate
python run_from_excel.py -x testcases\IE13_AT_Testcases.xlsx --list-tests

# 4. 跑冒煙測試（預設範本，單一 test_id）
python run_from_excel.py -p COM14 -t TC_Smoke_AT -n 1

# 4a. 跑 IE13 測項檔
python run_from_excel.py -x testcases\IE13_AT_Testcases.xlsx -p COM14

# 4b. 一次跑 Smoke + GNSS（預設範本，建議順序：先短後長）
python run_from_excel.py -p COM14 -t TC_Smoke_AT,TC_GNSS_XTRA_ColdStart -n 1

# 5. 查看產生的 .log 與 .csv
```

---

## 12. 相關檔案（專案其他位置）

本框架與以下既有腳本概念相同，可並行使用：

| 路徑 | 說明 |
|------|------|
| `3_Python/GNSS/GNSS_XTRA_ColdStart_STRESS_0001.py` | GNSS 壓力測試（步驟寫在 Python 內） |
| `3_Python/ATReset/IE13_AtRESET_AutoRetryConn_TimeCount_printToLog.py` | AT^RESET 重啟時間測試 |
| `3_Python/Run/run_file_by_path.py` | 多回合執行器，執行前會做 AT 握手檢查 |

`at_framework` 的優勢在於：**測項集中在 Excel，修改測試不必改 Python 程式。**
