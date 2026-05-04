#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
마란 런처 아이콘 생성기
- 다크 그라데이션 배경 + 보라/파란 그라데이션 'M' 글씨
- 멀티 해상도 .ico 출력
"""

from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import os

OUT_PATH = Path(__file__).with_name("icon.ico")
SIZES = [16, 32, 48, 64, 128, 256]

# Catppuccin Mocha 팔레트
BG_TOP = (30, 30, 46, 255)        # #1e1e2e
BG_BOT = (24, 24, 37, 255)        # #181825
RING_OUTER = (137, 180, 250, 255) # #89b4fa
M_TOP = (203, 166, 247, 255)      # #cba6f7 보라
M_BOT = (137, 180, 250, 255)      # #89b4fa 파랑
SHADOW = (0, 0, 0, 80)


def find_font(size):
    """굵은 sans-serif 폰트 찾기"""
    candidates = [
        r"C:\Windows\Fonts\seguibl.ttf",   # Segoe UI Black
        r"C:\Windows\Fonts\segoeuib.ttf",  # Segoe UI Bold
        r"C:\Windows\Fonts\arialbd.ttf",   # Arial Bold
        r"C:\Windows\Fonts\malgunbd.ttf",  # 맑은 고딕 Bold
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def vertical_gradient(size, top_rgba, bot_rgba):
    """수직 그라데이션 이미지"""
    img = Image.new("RGBA", (size, size), top_rgba)
    px = img.load()
    for y in range(size):
        t = y / max(size - 1, 1)
        r = int(top_rgba[0] * (1 - t) + bot_rgba[0] * t)
        g = int(top_rgba[1] * (1 - t) + bot_rgba[1] * t)
        b = int(top_rgba[2] * (1 - t) + bot_rgba[2] * t)
        a = int(top_rgba[3] * (1 - t) + bot_rgba[3] * t)
        for x in range(size):
            px[x, y] = (r, g, b, a)
    return img


def draw_icon(size):
    # 큰 사이즈로 그리고 다운샘플 → 안티앨리어싱 품질 향상
    scale = 4 if size >= 32 else 2
    S = size * scale
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1) 라운드 사각형 배경 (그라데이션)
    bg = vertical_gradient(S, BG_TOP, BG_BOT)
    mask = Image.new("L", (S, S), 0)
    mdraw = ImageDraw.Draw(mask)
    radius = int(S * 0.22)
    mdraw.rounded_rectangle((0, 0, S - 1, S - 1), radius=radius, fill=255)
    img.paste(bg, (0, 0), mask)

    # 2) 외곽 링 (얇은 강조선)
    ring_w = max(1, int(S * 0.025))
    draw.rounded_rectangle(
        (ring_w // 2, ring_w // 2, S - 1 - ring_w // 2, S - 1 - ring_w // 2),
        radius=radius - ring_w // 2,
        outline=RING_OUTER,
        width=ring_w,
    )

    # 3) M 글씨 (그라데이션 채움)
    text = "M"
    # 폰트 크기를 안전 영역(약 65%) 안에 들어가도록 자동 조정
    target = int(S * 0.62)
    font_size = target
    while font_size > 8:
        font = find_font(font_size)
        bbox = draw.textbbox((0, 0), text, font=font, anchor="lt")
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        if tw <= target and th <= target:
            break
        font_size -= 2
    tx = (S - tw) // 2 - bbox[0]
    ty = (S - th) // 2 - bbox[1]

    text_mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(text_mask).text((tx, ty), text, font=font, fill=255)

    # 그림자 (살짝)
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    offset = max(1, int(S * 0.012))
    sd.text((tx + offset, ty + offset), text, font=font, fill=SHADOW)
    img.alpha_composite(shadow)

    # M 그라데이션 채우기
    grad = vertical_gradient(S, M_TOP, M_BOT)
    img.paste(grad, (0, 0), text_mask)

    # 4) 다운샘플
    if scale > 1:
        img = img.resize((size, size), Image.LANCZOS)
    return img


def main():
    images = [draw_icon(s) for s in SIZES]
    # 가장 큰 이미지를 base로 + 나머지를 sizes로 전달 → 멀티 해상도 ico
    images[-1].save(
        OUT_PATH,
        format="ICO",
        sizes=[(s, s) for s in SIZES],
    )
    # 미리보기 png도 같이 저장
    images[-1].save(OUT_PATH.with_suffix(".png"), format="PNG")
    print(f"[OK] icon written: {OUT_PATH}")
    print(f"[OK] preview     : {OUT_PATH.with_suffix('.png')}")


if __name__ == "__main__":
    main()
