"""Generate a simple timelapse icon (sun + film strip) and save as PNG and ICO.

Run: python tools\generate_icon.py
Requires: Pillow
"""
from PIL import Image, ImageDraw
import os

def make_icon(path_png, path_ico, size=256):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cx, cy = size // 2, size // 2
    # background radial-ish sun (two concentric circles)
    outer_r = int(size * 0.42)
    inner_r = int(size * 0.30)
    draw.ellipse([cx - outer_r, cy - outer_r, cx + outer_r, cy + outer_r], fill=(255, 150, 0, 255))
    draw.ellipse([cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r], fill=(255, 220, 80, 255))

    # film strip: a dark rounded rectangle across the bottom quarter
    strip_h = int(size * 0.28)
    strip_y0 = int(size * 0.62)
    strip_y1 = strip_y0 + strip_h
    strip_x0 = int(size * 0.08)
    strip_x1 = int(size * 0.92)
    # base
    draw.rectangle([strip_x0, strip_y0, strip_x1, strip_y1], fill=(20, 20, 30, 230))
    # inner lighter band
    ib = 6
    draw.rectangle([strip_x0 + ib, strip_y0 + ib, strip_x1 - ib, strip_y1 - ib], fill=(40, 40, 50, 200))

    # sprocket holes: small rounded rectangles along top and bottom edges of the strip
    hole_w = int(size * 0.06)
    hole_h = int(size * 0.10)
    gap = int(size * 0.04)
    x = strip_x0 + gap
    holes_top = []
    while x + hole_w < strip_x1 - gap:
        holes_top.append((x, strip_y0 + int(size * 0.02), x + hole_w, strip_y0 + int(size * 0.02) + hole_h))
        x += hole_w + gap
    for r in holes_top:
        draw.rectangle(r, fill=(200, 200, 210, 255))

    # central film frames: lighten a few vertical frame separators
    num_frames = 4
    frame_w = int((strip_x1 - strip_x0) / num_frames)
    for i in range(1, num_frames):
        x = strip_x0 + i * frame_w
        draw.line([(x, strip_y0 + ib), (x, strip_y1 - ib)], fill=(80, 80, 90, 255), width=2)

    # optional highlight arc to imply motion/time at upper-right
    arc_box = [cx + int(size * 0.05), cy - int(size * 0.3), cx + int(size * 0.6), cy + int(size * 0.2)]
    draw.arc(arc_box, start=200, end=300, fill=(255, 230, 120, 200), width=6)

    # save
    img.save(path_png, format='PNG')
    # Save ICO; provide multiple sizes for best results
    try:
        img.resize((64, 64), Image.LANCZOS).save(path_ico, sizes=[(256,256),(128,128),(64,64)])
    except Exception:
        # fallback: save only PNG as ICO may fail on some Pillow builds
        img.save(path_ico, format='ICO')

if __name__ == '__main__':
    base = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(base, '..'))
    out_png = os.path.join(project_root, 'make_timelapse_gui.png')
    out_ico = os.path.join(project_root, 'make_timelapse_gui.ico')
    print('Generating', out_png, 'and', out_ico)
    make_icon(out_png, out_ico)
    print('Done')
