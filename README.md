Python 自動化測試工具集 (Automation Test Toolkit)
本倉庫提供了一套用於硬體通訊與自動化流程執行的 Python 工具，特別針對使用 AT 指令 的模組（如 LTE/Mobile Broadband）進行壓力測試與效能驗證。

📝 核心檔案說明
1. 泛用執行器 (run_file_by_path.py)
這是一個強大的自動化封裝腳本，能夠循環執行多種格式的檔案（.py, .bat, .ps1, .exe 等），並在每回合執行前自動驗證硬體狀態。

自動連線檢查：執行目標檔案前，先透過指定 COM Port 發送 AT 指令進行握手測試。

多格式支援：

.py：使用目前環境的 Python 解譯器執行。

.bat / .cmd / .ps1：執行 Windows 批次檔或 PowerShell 腳本。

.exe：以「非阻塞」模式啟動背景程式。

自動化 UI 互動：內建 PowerShell 邏輯，可在執行後自動聚焦目標視窗並送出 ENTER 鍵，模擬人工確認。

詳細日誌：記錄每一回合的 STDOUT、STDERR、AT 指令回應及成功率統計。

2. AT 指令重置效能測試 (IE13_AtRESET_AutoRetryConn_TimeCount_printToLog.py)
這是一個專門針對 AT^RESET 指令開發的測試工具，用於測量模組重啟後的復歸時間 (Boot-up time)。

重啟耗時測量：精確計算從發送 AT^RESET 到系統重新辨識 COM Port 並成功連線的時間（單位：毫秒）。

異常標註：可設定閾值 (Threshold)，若重啟時間超過標準將自動標註為 MARK (EXCEEDED)。

自動重試機制：若回合執行失敗（如連線超時），支援最多 3 次自動重試，確保測試不因偶發性連線問題中斷。

統計分析：測試結束後自動生成統計報告，包含平均、最大、最小耗時及成功率。

🚀 快速開始
環境需求
Python 3.x

安裝必要套件：

Bash
pip install pyserial
使用方式
方案 A：使用執行器運行多回合測試
若你想循環執行某個測試腳本（例如執行 50 次重置測試）：

執行執行器：

Bash
python run_file_by_path.py
根據提示輸入：

欲執行的檔案路徑

COM Port (如 COM3)

驗證用的 AT 指令 (如 ATi)

回合數

方案 B：直接進行重置效能測量
執行重置測試腳本：

Bash
python IE13_AtRESET_AutoRetryConn_TimeCount_printToLog.py
設定測試參數：

目標 COM Port

總測試回合數

逾時閾值 (ms)

失敗重試間隔秒數

📊 日誌與結果
執行器日誌：檔名格式為 run_[目標名稱]_[時間].log。

重置測試日誌：檔名格式為 AT_Reset_Python_Test_[時間].log。

日誌將詳細記錄時間戳記、AT 指令互動過程以及所有統計數據，便於後續分析模組穩定性。

🛠 技術細節
視窗聚焦技術：透過 Windows API 與 PowerShell 腳本結合，確保自動化操作能準確點擊目標程式視窗。

非阻塞啟動：針對 .exe 檔案使用 DETACHED_PROCESS 旗標，確保主控端腳本不會因目標程式未關閉而卡死。

這是一個專為自動化測試工程師設計的工具箱。
