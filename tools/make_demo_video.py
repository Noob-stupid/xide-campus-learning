# -*- coding: utf-8 -*-
"""生成演示视频：6 张中文幻灯片（含 1 张大面积红色「重点标记」页）→ mp4。

用法：
    python tools/make_demo_video.py            # 写到 data/media/demo/demo_video.mp4
    python tools/make_demo_video.py 输出路径.mp4

依赖：Pillow（画中文）+ opencv-python（合成 mp4），都是环境里已有的，不引入新依赖。
"""

import os
import shutil
import sys
import tempfile

import numpy as np
import cv2
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import config  # noqa: E402  （路径从 config 推导，禁止硬编码）

FONT_CANDIDATES = (
    'C:/Windows/Fonts/msyh.ttc',
    'C:/Windows/Fonts/msyhbd.ttc',
    'C:/Windows/Fonts/simhei.ttf',
    'C:/Windows/Fonts/simsun.ttc',
    '/System/Library/Fonts/PingFang.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
)

W, H = 960, 540
FPS = 24
SEC_PER_SLIDE = 1.5

INK = (15, 42, 74)          # 主色 #0F2A4A
GOLD = (201, 138, 46)       # 点缀 #C98A2E
TEAL = (14, 124, 107)       # 青绿 #0E7C6B
PAPER = (245, 247, 250)     # 背景 #F5F7FA
RED = (206, 38, 38)         # 重点标记红


def _font(size):
    """优先微软雅黑，找不到就退到 Pillow 默认字体（保证脚本在任何机器都能跑完）。"""
    from PIL import ImageFont

    for cand in FONT_CANDIDATES:
        if os.path.exists(cand):
            for index in (0, 1):
                try:
                    return ImageFont.truetype(cand, size, index=index)
                except Exception:
                    continue
    return ImageFont.load_default()


def _new_slide():
    img = Image.new('RGB', (W, H), PAPER)
    draw = ImageDraw.Draw(img)
    # 顶部细线 + 左侧色条，统一版式
    draw.rectangle([0, 0, W, 6], fill=INK)
    draw.rectangle([56, 88, 64, 148], fill=GOLD)
    draw.text((W - 210, 34), '习得 · 学生交棒', fill=TEAL, font=_font(20))
    draw.line([56, H - 46, W - 56, H - 46], fill=(228, 232, 239), width=2)
    return img, draw


def _wrap(draw, text, font, width):
    """按像素宽度折行（中文按字符切）。"""
    lines, cur = [], ''
    for ch in text:
        trial = cur + ch
        if draw.textlength(trial, font=font) > width and cur:
            lines.append(cur)
            cur = ch
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def slide_title():
    img, draw = _new_slide()
    draw.text((88, 150), '二次函数的图像与性质', fill=INK, font=_font(52))
    draw.text((88, 232), '高一 · 数学 · 必修一 · 第 2 章', fill=(90, 105, 122), font=_font(26))
    draw.rectangle([88, 300, 400, 304], fill=GOLD)
    draw.text((88, 330), '3 分钟看懂 a、b、c 各自管什么', fill=TEAL, font=_font(28))
    draw.text((88, 430), '沧州交通学院 · 智学空间「习得」', fill=(120, 132, 148), font=_font(22))
    return img


def slide_points():
    img, draw = _new_slide()
    draw.text((88, 60), '本节要点', fill=INK, font=_font(40))
    items = [
        '开口方向由 a 的正负决定：a > 0 向上，a < 0 向下',
        '对称轴 x = -b / (2a)，与 b 的符号相反',
        '顶点坐标 (-b/2a, (4ac-b²)/4a) 是最大/最小值所在处',
        '判别式 Δ = b² - 4ac 决定与 x 轴交点个数',
    ]
    y = 140
    for i, text in enumerate(items, 1):
        draw.ellipse([92, y + 6, 120, y + 34], fill=TEAL)
        draw.text((99, y + 9), str(i), fill=(255, 255, 255), font=_font(18))
        for line in _wrap(draw, text, _font(28), W - 240):
            draw.text((136, y), line, fill=(38, 52, 68), font=_font(28))
            y += 42
        y += 26
    return img


def slide_formula():
    img, draw = _new_slide()
    draw.text((88, 60), '把一般式写成顶点式', fill=INK, font=_font(40))
    draw.rectangle([120, 160, W - 120, 330], fill=(255, 255, 255), outline=(228, 232, 239), width=2)
    draw.text((170, 190), 'y = a x² + b x + c', fill=INK, font=_font(44))
    draw.text((170, 258), 'y = a (x - h)² + k', fill=TEAL, font=_font(44))
    draw.text((120, 372), '其中 h = -b/(2a)，k = (4ac - b²)/(4a)；这两个值就是顶点。',
              fill=(90, 105, 122), font=_font(24))
    draw.text((120, 420), '口诀：先定开口，再找对称轴，最后落顶点。', fill=GOLD, font=_font(26))
    return img


def slide_red():
    """大面积红色重点页：初筛会把它标成可疑帧（红色占比高）。"""
    img = Image.new('RGB', (W, H), PAPER)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, W, 6], fill=INK)
    # 从 y=120 到 y=420 的通栏红底，占全画面约 56%
    draw.rectangle([0, 120, W, 420], fill=RED)
    draw.text((88, 66), '重点标记', fill=INK, font=_font(40))
    draw.text((88, 158), '高频易错（必考）', fill=(255, 236, 236), font=_font(34))
    for i, line in enumerate(('判别式 Δ = b² - 4ac', 'Δ > 0 两个交点，Δ = 0 一个，Δ < 0 没有'), 0):
        draw.text((88, 226 + i * 62), line, fill=(255, 255, 255), font=_font(40))
    draw.text((88, 356), '考试里 80% 的失分来自符号写错', fill=(255, 224, 224), font=_font(28))
    draw.text((88, H - 90), '看到红色请停下来默写一遍公式', fill=(90, 105, 122), font=_font(22))
    return img


def slide_chart():
    img, draw = _new_slide()
    draw.text((88, 52), '图像对比：a 决定张口', fill=INK, font=_font(40))
    draw.text((88, 106), '张口大小由 |a| 决定：|a| 越大，开口越窄。', fill=(90, 105, 122), font=_font(22))
    ox, oy, k = 600, 350, 52       # 原点像素位置 + 1 个 y 单位 = 52px
    draw.line([150, oy, 900, oy], fill=(170, 178, 190), width=2)
    draw.line([ox, 130, ox, 470], fill=(170, 178, 190), width=2)
    draw.text((906, oy - 14), 'x', fill=(120, 132, 148), font=_font(20))
    draw.text((ox + 10, 112), 'y', fill=(120, 132, 148), font=_font(20))

    def parabola(a, color):
        pts = []
        for px in range(-320, 321, 3):
            x = px / 100.0
            py = oy - a * x * x * k
            if 132 <= py <= 468:        # 越界的点直接丢掉，别画出画布
                pts.append((ox + px, py))
        if len(pts) > 1:
            draw.line(pts, fill=color, width=4, joint='curve')

    parabola(1.0, TEAL)
    parabola(-0.6, GOLD)

    for i, (text, color) in enumerate((('a = 1（开口向上）', TEAL), ('a = -0.6（开口向下）', GOLD))):
        y = 392 + i * 36
        draw.line([150, y + 12, 196, y + 12], fill=color, width=5)
        draw.text((210, y), text, fill=color, font=_font(22))
    return img


def slide_end():
    img, draw = _new_slide()
    draw.text((88, 150), '今晚就练这三步', fill=INK, font=_font(48))
    steps = ['写出 a、b、c', '算对称轴 x = -b/2a', '代回求顶点，画草图']
    x = 88
    for i, text in enumerate(steps, 1):
        draw.rounded_rectangle([x, 240, x + 240, 380], radius=16, fill=(255, 255, 255),
                               outline=(228, 232, 239), width=2)
        draw.text((x + 24, 258), '0%d' % i, fill=GOLD, font=_font(26))
        for j, line in enumerate(_wrap(draw, text, _font(24), 196)):
            draw.text((x + 24, 306 + j * 32), line, fill=(38, 52, 68), font=_font(24))
        x += 266
    draw.text((88, 430), '学完记得回「习得」结束本次学习，系统会推给你下一段。',
              fill=TEAL, font=_font(24))
    return img


SLIDES = (slide_title, slide_points, slide_formula, slide_red, slide_chart, slide_end)


def build_frames(fps=FPS, sec_per_slide=SEC_PER_SLIDE):
    """返回 [(bgr_ndarray, ...)] 顺序帧。"""
    hold = max(1, int(round(fps * sec_per_slide)))
    frames = []
    for maker in SLIDES:
        img = maker().convert('RGB')
        arr = np.array(img)[:, :, ::-1].copy()   # RGB -> BGR
        for _ in range(hold):
            frames.append(arr)
    return frames


def _write_video(path, frames, fps=FPS):
    """cv2.VideoWriter 写视频；个别环境对中文路径不友好，失败就改写到 ASCII 临时目录再拷回。"""
    def _attempt(target):
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(target, fourcc, float(fps), (frames[0].shape[1], frames[0].shape[0]))
        if not writer.isOpened():
            try:
                writer.release()
            except Exception:
                pass
            return False
        try:
            for fr in frames:
                writer.write(fr)
        finally:
            writer.release()
        return os.path.exists(target) and os.path.getsize(target) > 1024

    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    if _attempt(path):
        return path

    tmp_dir = tempfile.mkdtemp(prefix='zx_demo_')
    tmp_path = os.path.join(tmp_dir, 'demo_video.mp4')
    try:
        if not _attempt(tmp_path):
            raise RuntimeError('VideoWriter 无法写出 mp4（缺 mp4v 编码器？）')
        shutil.copyfile(tmp_path, path)
        return path
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def make(path=None, fps=FPS, sec_per_slide=SEC_PER_SLIDE):
    """生成视频，返回绝对路径。"""
    if path is None:
        path = os.path.join(config.MEDIA_DIR, 'demo', 'demo_video.mp4')
    frames = build_frames(fps=fps, sec_per_slide=sec_per_slide)
    _write_video(path, frames, fps=fps)
    return os.path.abspath(path)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    target = argv[0] if argv else None
    path = make(target)
    print(path)
    try:
        cap = cv2.VideoCapture(path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        cap.release()
        print('分辨率 %dx%d，%.2f fps，%d 帧，约 %.1f 秒' % (W, H, fps, total, total / fps if fps else 0))
    except Exception:
        pass
    return path


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(errors='replace')
    except Exception:
        pass
    main()
