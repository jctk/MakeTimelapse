import os
import argparse
import cv2
import numpy as np
import subprocess
import tempfile
import re
from astropy.io import fits

# 画像ファイルを読み込む関数（PNG または FITS）
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
# --caption が指定された場合は、各フレームの左下にファイル名（ベースネーム）を描画
# --caption_re が指定された場合は、正規表現でファイル名を置換して描画
def create_video_with_ffmpeg(input_dir, output_file, fps=10, crf=23, caption=False, caption_re=None):
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

                # キャプション表示が有効な場合
                if caption:
                    basename = os.path.basename(image_name)
                    if caption_re:
                        pattern, replacement = caption_re
                        basename = re.sub(pattern, replacement, basename)

                    # テキスト描画設定
                    font = cv2.FONT_HERSHEY_SIMPLEX
                    font_scale = 1
                    thickness = 1
                    color = (255,)  # 白（グレースケール）
                    margin = 100

                    # 文字サイズを取得
                    (text_width, text_height), baseline = cv2.getTextSize(basename, font, font_scale, thickness)

                    # 背景サイズを1.2倍に拡張
                    scale = 1.2
                    bg_width = int(text_width * scale)
                    bg_height = int(text_height * scale)

                    # 背景の左上座標（画面下部に中央配置）
                    bg_x1 = margin
                    bg_y1 = frame.shape[0] - margin - bg_height

                    # 背景の右下座標
                    bg_x2 = bg_x1 + bg_width
                    bg_y2 = bg_y1 + bg_height

                    # 黒い背景を描画
                    cv2.rectangle(frame, (bg_x1, bg_y1), (bg_x2, bg_y2), (0,), thickness=cv2.FILLED)

                    # テキストの描画位置（背景の中央に配置）
                    text_x = bg_x1 + (bg_width - text_width) // 2
                    text_y = bg_y1 + (bg_height + text_height) // 2  # ベースライン調整込み

                    # テキストを描画
                    cv2.putText(frame, basename, (text_x, text_y), font, font_scale, color, thickness, cv2.LINE_AA)

                output_path = os.path.join(temp_dir, f"frame_{i:04d}.png")
                cv2.imwrite(output_path, frame)
            except Exception as e:
                print(f"警告: {image_name} の読み込みに失敗しました。スキップします。理由: {e}", flush=True)
                continue

        # FFmpeg コマンドで動画生成
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
        print(f"動画ファイルが生成されました: {output_file}", flush=True)

# メイン関数
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="画像（PNG, FITS）から FFmpeg を使って動画を生成します。")
    parser.add_argument("input_dir", help="画像が含まれる入力ディレクトリ")
    parser.add_argument("output_file", help="生成する動画ファイル名（例: output.mp4）")
    parser.add_argument("--fps", type=int, default=10, help="動画のフレームレート（デフォルト: 10）")
    parser.add_argument("--crf", type=int, default=23, help="画質（CRF値 1～50、デフォルト: 23）")
    parser.add_argument("--caption", action="store_true", help="各フレームの左下にファイル名を表示する")
    parser.add_argument("--caption_re", nargs=2, metavar=('PATTERN', 'REPLACEMENT'),
                        help="ファイル名の置換（正規表現）: PATTERN を REPLACEMENT に置換")

    args = parser.parse_args()

    print("指定されたオプション:", flush=True)
    for arg in vars(args):
        print(f"  {arg}: {getattr(args, arg)}", flush=True)

    create_video_with_ffmpeg(
        args.input_dir,
        args.output_file,
        fps=args.fps,
        crf=args.crf,
        caption=args.caption,
        caption_re=args.caption_re
    )
