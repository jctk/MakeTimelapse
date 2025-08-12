import os
import glob
import numpy as np
from astropy.io import fits
import cv2
import argparse
import SimpleITK as sitk
import concurrent.futures

# FITSファイルをSimpleITKのfloat32画像に変換する関数
def fits_to_sitk_float32(path):
    data = fits.getdata(path)
    img = np.nan_to_num(data)
    img = (img - np.min(img)) / (np.max(img) - np.min(img))  # 0-1正規化
    img = img.astype(np.float32)
    return sitk.GetImageFromArray(img)

# 基準画像を読み込む関数
def load_reference_image(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in ['.fits', '.fit']:
        return fits_to_sitk_float32(path)
    elif ext == '.png':
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        img = np.nan_to_num(img.astype(np.float32))
        img = (img - np.min(img)) / (np.max(img) - np.min(img))  # 0-1正規化
        return sitk.GetImageFromArray(img)
    else:
        raise ValueError(f"対応していないファイル形式です: {ext}")

# コマンドライン引数の定義
parser = argparse.ArgumentParser(description='Sol\'Ex画像の歪み補正タイムラプス作成')
parser.add_argument('--ref', type=str, required=True, help='基準となるモノクロ画像（fits, fit, png）のファイルのパス')
parser.add_argument('--input_dir', type=str, default='./input', help='入力画像ファイル（fits, fit, png）のフォルダー')
parser.add_argument('--aligned_dir', type=str, default='./aligned', help='位置合わせ後画像の保存フォルダー')
parser.add_argument('--movie', type=str, default=None, help='動画の出力ファイル名')
parser.add_argument('--iterations', type=int, default=1200, help='DemonsRegistrationFilterの反復回数')
parser.add_argument('--stddev', type=float, default=4.0, help='DemonsRegistrationFilterの標準偏差')
parser.add_argument('--workers', type=int, default=None, help='並列処理のワーカー数（デフォルトはCPUコア数）')

args = parser.parse_args()

# 各フォルダーの絶対パスを取得
input_dir = os.path.abspath(args.input_dir)
aligned_dir = os.path.abspath(args.aligned_dir)
movie_dir = os.path.dirname(os.path.abspath(args.movie)) if args.movie else os.getcwd()
os.makedirs(aligned_dir, exist_ok=True)
os.makedirs(movie_dir, exist_ok=True)

# 基準画像の拡張子を取得して、それに応じたファイルのみを対象にする
ref_ext = os.path.splitext(args.ref)[1].lower()
input_files = glob.glob(os.path.join(input_dir, f"*{ref_ext}"))
input_files = sorted(input_files)




# 基準画像の読み込みとサイズ取得
ref_img_sitk = load_reference_image(args.ref)
ref_img_np = sitk.GetArrayFromImage(ref_img_sitk)
height, width = ref_img_np.shape

# 各画像の位置合わせ処理を行う関数
def process_image(f):
    # マルチスケール Demons 処理関数（FastSymmetricForcesDemonsRegistrationFilter 使用）
    def multi_resolution_demons(fixed, moving, iterations, stddev):
        transform = sitk.DisplacementFieldTransform(sitk.Image(fixed.GetSize(), sitk.sitkVectorFloat64))
        for shrink_factor in [4, 2, 1]:  # 解像度を段階的に上げる
            fixed_resampled = sitk.Shrink(fixed, [shrink_factor]*fixed.GetDimension())
            moving_resampled = sitk.Shrink(moving, [shrink_factor]*moving.GetDimension())

            demons = sitk.FastSymmetricForcesDemonsRegistrationFilter()
            demons.SetNumberOfIterations(iterations)
            demons.SetStandardDeviations(stddev)
            displacement_field = demons.Execute(fixed_resampled, moving_resampled)

            transform.SetDisplacementField(displacement_field)
        return transform

    print(f"処理中: {os.path.basename(f)}", flush=True)

    # 入力画像の読み込み
    ext = os.path.splitext(f)[1].lower()
    if ext in ['.fits', '.fit']:
        moving_image = fits_to_sitk_float32(f)
    elif ext == '.png':
        img = cv2.imread(f, cv2.IMREAD_GRAYSCALE)
        img = np.nan_to_num(img.astype(np.float32))
        img = (img - np.min(img)) / (np.max(img) - np.min(img))  # 0-1正規化
        moving_image = sitk.GetImageFromArray(img)
    else:
        raise ValueError(f"対応していないファイル形式です: {ext}")

    # 初期位置合わせ
    initial_transform = sitk.CenteredTransformInitializer(
        ref_img_sitk,
        moving_image,
        sitk.Euler2DTransform(),
        sitk.CenteredTransformInitializerFilter.GEOMETRY
    )
    moving_resampled = sitk.Resample(
        moving_image,
        ref_img_sitk,
        initial_transform,
        sitk.sitkLinear,
        0.0
    )
    moving_image = moving_resampled

    # サイズが一致しない場合はリサイズ
    if moving_image.GetSize() != ref_img_sitk.GetSize():
        moving_image = sitk.Resample(moving_image, ref_img_sitk)

    # ヒストグラムマッチング（輝度分布を基準画像に合わせる）
    matcher = sitk.HistogramMatchingImageFilter()
    matcher.SetNumberOfHistogramLevels(65536)
    matcher.SetNumberOfMatchPoints(10)
    matcher.ThresholdAtMeanIntensityOn()
    moving_image = matcher.Execute(moving_image, ref_img_sitk)

    # 改善済み：マルチスケール + 高速 Demons フィルター
    transform = multi_resolution_demons(ref_img_sitk, moving_image, args.iterations, args.stddev)
    displacement_field = transform.GetDisplacementField()

    # displacement_field から変位ベクトルの大きさを計算
    disp_np = sitk.GetArrayFromImage(displacement_field)  # shape: (H, W, 2)
    magnitude = np.linalg.norm(disp_np, axis=-1)  # 各ピクセルの変位ベクトルの大きさ

    mean_disp = np.mean(magnitude)
    max_disp = np.max(magnitude)
    std_disp = np.std(magnitude)

    print(f"変位量:{os.path.basename(f)} - 平均: {mean_disp:.4f}, 最大: {max_disp:.4f}, 標準偏差: {std_disp:.4f}")

    # 変位ベクトルを基に画像を位置合わせ
    resampler = sitk.ResampleImageFilter()
    resampler.SetReferenceImage(ref_img_sitk)
    resampler.SetInterpolator(sitk.sitkLinear)
    resampler.SetDefaultPixelValue(0)
    resampler.SetTransform(transform)
    aligned_sitk = resampler.Execute(moving_image)
    aligned_np = sitk.GetArrayFromImage(aligned_sitk)

    #
    # 画像を16bitに変換して保存
    #

    # 画像を16bitに変換
    img_min = np.min(aligned_np)
    img_max = np.max(aligned_np)
    if img_max > img_min:
        img_uint16 = ((aligned_np - img_min) / (img_max - img_min) * 65535).astype(np.uint16)
    else:
        img_uint16 = np.zeros_like(aligned_np, dtype=np.uint16)

    # サイズ確認（通常不要だが安全のため）
    if img_uint16.shape != (height, width):
        img_uint16 = cv2.resize(img_uint16, (width, height), interpolation=cv2.INTER_LINEAR)

    # 保存形式に応じて保存
    ref_ext = os.path.splitext(args.ref)[1].lower()
    base_name = os.path.splitext(os.path.basename(f))[0]
    save_path = os.path.join(aligned_dir, f"{base_name}{ref_ext}")

    if ref_ext == '.png':
        cv2.imwrite(save_path, img_uint16)
    elif ref_ext in ['.fits', '.fit']:
        # FITS形式で保存（uint16形式をfloat32に変換して保存）
        fits_data = img_uint16.astype(np.float32)
        hdu = fits.PrimaryHDU(fits_data)
        hdu.writeto(save_path, overwrite=True)
    else:
        raise ValueError(f"保存形式に対応していません: {ref_ext}")

    return img_uint16

# メイン処理
if __name__ == "__main__":
    # タイムラプス動画のファイル名を自動生成する関数
    def get_next_movie_filename(movie_dir, base='timelapse', ext='.mp4'):
        idx = 1
        while True:
            fname = f"{base}-{idx}{ext}"
            fpath = os.path.join(movie_dir, fname)
            if not os.path.exists(fpath):
                return fpath
            idx += 1

    aligned_imgs = []
    try:
        # 並列処理で画像を位置合わせ
        with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as executor:
            results = list(executor.map(process_image, input_files))
            aligned_imgs.extend(results)
    except KeyboardInterrupt:
        print("処理を中断しました。")
        exit(1)

    # 動画ファイル名の決定
    if args.movie:
        video_path = os.path.abspath(args.movie)
    else:
        video_path = get_next_movie_filename(movie_dir)

    # 動画の作成
    fps = 10
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    # fourcc = cv2.VideoWriter_fourcc(*'X264')  # 高画質なコーデック
    video = cv2.VideoWriter(video_path, fourcc, fps, (width, height), False)

    for img in aligned_imgs:        
        vimg_uint8 = (img / 256).astype(np.uint8)
        video.write(vimg_uint8)

    video.release()
    print(f'動画を保存しました: {video_path}')
