# -*- coding: utf-8 -*-
"""
Created on Thu Oct 17 16:36:17 2024

@author: OLYMPUS-4313
"""

import cv2
import numpy as np
import pyautogui
from pathlib import Path


def locate_on_screen(template_path, threshold=0.8):
    screenshot = pyautogui.screenshot()
    screen = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
    template = cv2.imread(str(template_path))
    if template is None:
        raise FileNotFoundError(f"找不到模板圖片: {template_path}")

    result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    if max_val < threshold:
        raise RuntimeError(f"找不到圖片 (相似度={max_val:.2f}, 門檻={threshold})")

    h, w = template.shape[:2]
    x = max_loc[0] + w // 2
    y = max_loc[1] + h // 2
    return x, y, max_val


# 1 Identify "a" picture (picture= Single)
chrome_shortcut = Path(__file__).resolve().parent / "pyAutoGuiPic" / "chromeShortCut.png"
x, y, confidence = locate_on_screen(chrome_shortcut, threshold=0.7)
print(f"找到圖片，位置=({x}, {y})，相似度={confidence:.2f}")
pyautogui.rightClick(x, y)
