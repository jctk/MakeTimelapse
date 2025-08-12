import os
import argparse
import cv2

def create_video_from_images(input_dir, output_file):
    # PNGファイルをファイル名昇順で取得
    images = sorted([img for img in os.listdir(input_dir) if img.lower().endswith('.png')])
    if not images:
        raise ValueError("指定されたフォルダにPNG画像が見つかりません。")

    # 最初の画像からサイズを取得
    first_image_path = os.path.join(input_dir, images[0])
    frame = cv2.imread(first_image_path)
    height, width, _ = frame.shape

    # 動画の設定
    fps = 10
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_file, fourcc, fps, (width, height), False)

    for image_name in images:
        image_path = os.path.join(input_dir, image_name)
        frame = cv2.imread(image_path)
        if frame is None:
            print(f"警告: {image_name} を読み込めませんでした。スキップします。")
            continue
        try:
            out.write(frame)
        except Exception as e:
            print(f"Error writing frame: {e}")


    out.release()
    print(f"動画ファイルが生成されました: {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PNG画像からH.264形式の動画を生成します。")
    parser.add_argument("input_dir", help="PNG画像が含まれる入力ディレクトリ")
    parser.add_argument("output_file", help="生成する動画ファイル名（例: output.mp4）")
    args = parser.parse_args()

    create_video_from_images(args.input_dir, args.output_file)
