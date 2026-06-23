# -*- coding: utf-8 -*-
"""
Created on Wed Oct 16 18:53:47 2024

@author: OLYMPUS-4313_hoga
"""

# Example_1 Notepad

# 0 pyautogui config
import ctypes
import time
import pyautogui
pyautogui.FAILSAFE = True


def is_notepad_window(title):
    return title.endswith('記事本') or title.endswith(' - Notepad')

def focus_notepad(wait_seconds=5):    #聚焦記事本視窗
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        for window in pyautogui.getAllWindows():
            if is_notepad_window(window.title):
                if window.isMinimized:
                    window.restore()
                window.activate()
                time.sleep(0.5)
                return True
        time.sleep(0.3)
    return False

def close_notepad(wait_seconds=5):    #關閉記事本視窗
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        for window in pyautogui.getAllWindows():
            if is_notepad_window(window.title):
                window.close()
                time.sleep(0.5)
                return True
        time.sleep(0.3)
    return False

def switch_to_english_input():    #切換為英文輸入法 (US)
    user32 = ctypes.windll.user32
    english_layout = user32.LoadKeyboardLayoutW("00000409", 1)
    foreground = user32.GetForegroundWindow()
    user32.PostMessageW(foreground, 0x0050, 0, english_layout)
    time.sleep(0.3)


# 1 Start the APP: notepad
pyautogui.hotkey('win', 'r')
pyautogui.typewrite('notepad', interval=0.25)
pyautogui.press('enter')
time.sleep(2)
if not focus_notepad():
    raise RuntimeError('找不到記事本視窗，無法取得焦點')

# 2 Using the APP
switch_to_english_input()
pyautogui.typewrite('Demo script for python using notepad', interval=0.25)
pyautogui.hotkey('ctrl','s')
# wait for notepad to start the SAVE dialog
time.sleep(2)

# 3 Saving
switch_to_english_input()
pyautogui.typewrite('demo_script_for_python_notepad', interval=0.25)
pyautogui.press('enter')

# 4 Close the APP
if not close_notepad():
    raise RuntimeError('找不到記事本視窗，無法關閉')