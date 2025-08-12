import os
import argparse
import cv2
import numpy as np
import subprocess
import tempfile
from astropy.io import fits

def read_image(image_path):
    ext = os.path.splitext(image_path)[1].lower()
    if ext == '.png':
        frame = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    elif ext in ['.fits', '.fit']:
        data = fits.getdata(image_path)
        if data is None:
            raise ValueError(f"{image_path} に画像データが含まれていません。")
        data = np.nan_to_num(data)
        if data.dtype.byteorder == '>':
            data = data.byteswap().newbyteorder()
        vmin, vmax = (0, 65535)
        data_clipped = np.clip(data, vmin, vmax)
        norm_data = cv2.normalize(data_clipped, None, 0, 255, cv2.NORM_MINMAX)
        frame = norm_data.astype(np.uint8)
    else:
        raise ValueError(f"対応していないファイル形式: {image_path}")
    return frame

# 画像から動画を生成する関数
def create_video_with_ffmpeg(input_dir, output_file, fps=10, crf=23):  # ← crf 引数を追加
    images = sorted([
        img for img in os.listdir(input_dir)
        if img.lower().endswith(('.png', '.fits', '.fit'))
    ])
    if not images:
        raise ValueError("指定されたフォルダに対応する画像が見つかりません。")

    with tempfile.TemporaryDirectory() as temp_dir:
        for i, image_name in enumerate(images):
            image_path = os.path.join(input_dir, image_name)
            try:
                frame = read_image(image_path)
                output_path = os.path.join(temp_dir, f"frame_{i:04d}.png")
                cv2.imwrite(output_path, frame)
            except Exception as e:
                print(f"警告: {image_name} の読み込みに失敗しました。スキップします。理由: {e}")
                continue
        ffmpeg_cmd = [
            'ffmpeg',
            '-y',
            '-framerate', str(fps),
            '-i', os.path.join(temp_dir, 'frame_%04d.png'),
            '-c:v', 'libx264',
            '-crf', str(crf),
            '-pix_fmt', 'yuv420p',
            output_file
        ]
        subprocess.run(ffmpeg_cmd, check=True)
        print(f"動画ファイルが生成されました: {output_file}")

# メイン関数
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="画像（PNG, FITS）から FFmpeg を使って動画を生成します。")
    parser.add_argument("input_dir", help="画像が含まれる入力ディレクトリ")
    parser.add_argument("output_file", help="生成する動画ファイル名（例: output.mp4）")
    parser.add_argument("--fps", type=int, default=10, help="動画のフレームレート（デフォルト: 10）")
    parser.add_argument("--crf", type=int, default=23, help="画質（CRF値 1～50、デフォルト: 23）")
    args = parser.parse_args()

    create_video_with_ffmpeg(args.input_dir, args.output_file, fps=args.fps, crf=args.crf)
