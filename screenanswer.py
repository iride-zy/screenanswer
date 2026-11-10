"""点击手机 → 截屏 → 问 LLM → 用 ADBKeyboard 把答案打回手机。"""

import base64
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import mss
import mss.tools
from openai import OpenAI

ADB = os.getenv("ADB", "adb")
MODEL = os.getenv("OPENAI_MODEL", "group/available")
IME = "com.android.adbkeyboard/.AdbIME"
PROMPT = "这是电脑屏幕上的在线笔试题截图。请回答当前题目：先写出关键推理（2~3 句，选择题要逐条验证选项/条件；数字规律题要用每个已知图形验证规律），最后一行输出答案：X。忽略页面水印、计时器和按钮。"
FALLBACK = "无法作答"
NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def first_device() -> str:
    out = subprocess.run(
        [ADB, "devices"], capture_output=True, text=True, creationflags=NO_WINDOW
    ).stdout
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) == 2 and parts[1] == "device":
            return parts[0]
    raise RuntimeError("no device")


def wait_click() -> str:
    while True:
        try:
            serial = first_device()  # 每次都重新 adb devices，断开后能自动连回来
        except RuntimeError:
            time.sleep(1)
            continue
        proc = subprocess.Popen(
            [ADB, "-s", serial, "shell", "getevent", "-lt"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            creationflags=NO_WINDOW,
        )
        try:
            for line in proc.stdout:
                if "BTN_TOUCH" in line or "ABS_MT_POSITION" in line:
                    return serial
        finally:
            proc.kill()
        time.sleep(1)  # getevent 自己退出了（手机断开），不是点击：1 秒后重新探测设备


def screenshot() -> Path:
    path = Path("screenshots") / f"{datetime.now():%Y%m%d_%H%M%S}.png"
    path.parent.mkdir(exist_ok=True)
    with mss.MSS() as sct:
        shot = sct.grab(sct.monitors[1])
        mss.tools.to_png(shot.rgb, shot.size, output=str(path))
    return path


def ask_llm(image: Path) -> str:
    b64 = base64.b64encode(image.read_bytes()).decode()
    client = OpenAI(
        base_url=os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:3425/v1"),
        api_key=os.getenv("OPENAI_API_KEY", "magpie"),
        timeout=None,  # 不设任何超时，等模型把话说完
    )
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        },
                    ],
                }
            ],
            temperature=0.7,
            reasoning_effort="none",
        )
        text = (resp.choices[0].message.content or "").strip()
    except Exception as e:  # 超时、断连、网关错误一律兜底
        print(f"LLM 请求失败: {e}", file=sys.stderr)
        return FALLBACK
    if not text:
        print("LLM 返回空内容，使用兜底文本", file=sys.stderr)
        return FALLBACK
    return text


def push_result(serial: str, text: str) -> None:
    subprocess.run(
        [ADB, "-s", serial, "shell", "ime", "enable", IME], creationflags=NO_WINDOW
    )
    subprocess.run(
        [ADB, "-s", serial, "shell", "ime", "set", IME], creationflags=NO_WINDOW
    )
    msg = base64.b64encode(text.encode()).decode()
    subprocess.run(
        [
            ADB, "-s", serial, "shell", "am", "broadcast",
            "-f", "0x01000020", "-p", "com.android.adbkeyboard",
            "-a", "ADB_INPUT_B64", "--es", "msg", msg,
        ],
        creationflags=NO_WINDOW,
    )


def main() -> None:
    while True:
        push_result(wait_click(), ask_llm(screenshot()))


if __name__ == "__main__":
    main()
