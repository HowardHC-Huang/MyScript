"""開啟瀏覽器前往 Strava，並列出頁面上的活動日期。"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

STRAVA_URL = "https://www.strava.com/athletes/188761095"
REFRESH_INTERVAL_SEC = 180
LOG_FILE = Path(__file__).resolve().parent / "open_strava.log"
logger = logging.getLogger("open_strava")


def setup_logging() -> None:
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter(
        "%(asctime)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)


def extract_activity_dates(html: str) -> list[str]:
    """從頁面 HTML 擷取活動日期文字（去重、保持順序）。"""
    soup = BeautifulSoup(html, "lxml")
    dates: list[str] = []
    seen = set()

    selectors = (
        "time[data-testid='date_at_time']",
        "time[datetime]",
        ".timestamp",
        "[data-testid='date_at_time']",
    )
    for selector in selectors:
        for el in soup.select(selector):
            text = el.get_text(" ", strip=True)
            if not text:
                text = (el.get("datetime") or el.get("title") or "").strip()
            if text and text not in seen:
                seen.add(text)
                dates.append(text)
        if dates:
            break

    return dates


def wait_for_activity_dates(driver: webdriver.Chrome) -> None:
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located(
                (
                    By.CSS_SELECTOR,
                    "time[data-testid='date_at_time'], time[datetime], .timestamp",
                )
            )
        )
    except TimeoutException:
        pass


def list_activity_dates(driver: webdriver.Chrome) -> None:
    wait_for_activity_dates(driver)
    dates = extract_activity_dates(driver.page_source)
    logger.info("重新整理後的活動日期：")
    if not dates:
        logger.info("找不到活動日期。請確認已登入，且頁面有顯示活動。")
        return
    logger.info("共找到 %s 筆：", len(dates))
    for i, date_text in enumerate(dates, 1):
        logger.info("  %s. %s", i, date_text)


def main() -> None:
    setup_logging()
    options = Options()
    options.add_argument("--start-maximized")

    driver = webdriver.Chrome(options=options)
    try:
        logger.info("正在開啟瀏覽器：%s", STRAVA_URL)
        driver.get(STRAVA_URL)

        print("若出現登入畫面，請先在瀏覽器登入；完成後回到此視窗按 Enter…")
        input()

        logger.info(
            "之後每 %s 秒會重新整理並列出活動日期；按 Ctrl+C 結束。",
            REFRESH_INTERVAL_SEC,
        )
        logger.info("Log 檔：%s", LOG_FILE)
        while True:
            list_activity_dates(driver)
            time.sleep(REFRESH_INTERVAL_SEC)
            logger.info("重新整理頁面…")
            driver.refresh()
    except KeyboardInterrupt:
        logger.info("已停止監控。")
    except WebDriverException as exc:
        logger.info("瀏覽器已關閉或發生錯誤：%s", exc)
    finally:
        try:
            driver.quit()
        except WebDriverException:
            pass


if __name__ == "__main__":
    main()
