import os
import glob
import numpy as np
from astropy.io import fits
import cv2
import argparse
import SimpleITK as sitk
import concurrent.futures
import datetime
import subprocess

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
parser.add_argument('--fast', action='store_true', help='高速版DemonsRegistrationFilterを使用する')
parser.add_argument('--multiscale', action='store_true', help='マルチスケール Demons を使用する(実験的実装)')
parser.add_argument('--crf', type=int, default=23, help='ffmpegの画質設定（デフォルト: 23）')
parser.add_argument('--fps', type=int, default=7, help='動画のフレームレート（デフォルト: 7）')
parser.add_argument("--caption", action="store_true", help="各フレームの左下にファイル名を表示する")
parser.add_argument("--caption_re", nargs=2, metavar=('PATTERN', 'REPLACEMENT'),
                    help="ファイル名の置換（正規表現）: PATTERN を REPLACEMENT に置換")

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

    # 通常の Demons 処理関数（マルチスケールなし）
    def single_resolution_demons(fixed, moving, iterations, stddev):
        if args.fast:
            demons = sitk.FastSymmetricForcesDemonsRegistrationFilter()
        else:
            demons = sitk.DemonsRegistrationFilter()
        demons.SetNumberOfIterations(iterations)
        demons.SetStandardDeviations(stddev)
        displacement_field = demons.Execute(fixed, moving)
        return sitk.DisplacementFieldTransform(displacement_field)

    # マルチスケール Demons 処理関数（FastSymmetricForcesDemonsRegistrationFilter のみ初期変形フィールドを使用）
    def multi_resolution_demons(fixed, moving, iterations, stddev):
        initial_field = sitk.Image(fixed.GetSize(), sitk.sitkVectorFloat64)
        initial_field.CopyInformation(fixed)

        for shrink_factor, iterations_rate in [(4, 0.25), (2, 0.3), (1, 0.45)]:
            fixed_resampled = sitk.Shrink(fixed, [shrink_factor]*fixed.GetDimension())
            moving_resampled = sitk.Shrink(moving, [shrink_factor]*moving.GetDimension())
            field_resampled = sitk.Resample(initial_field, fixed_resampled)
            demons = sitk.FastSymmetricForcesDemonsRegistrationFilter()
            demons.SetNumberOfIterations(int(iterations * iterations_rate))
            demons.SetStandardDeviations(stddev)
            updated_field = demons.Execute(fixed_resampled, moving_resampled, field_resampled)
            initial_field = sitk.Resample(updated_field, fixed)

        transform = sitk.DisplacementFieldTransform(initial_field)
        return transform

    print(f"処理中: {os.path.basename(f)}", flush=True)

    ext = os.path.splitext(f)[1].lower()
    if ext in ['.fits', '.fit']:
        moving_image = fits_to_sitk_float32(f)
    elif ext == '.png':
        img = cv2.imread(f, cv2.IMREAD_GRAYSCALE)
        img = np.nan_to_num(img.astype(np.float32))
        img = (img - np.min(img)) / (np.max(img) - np.min(img))
        moving_image = sitk.GetImageFromArray(img)
    else:
        raise ValueError(f"対応していないファイル形式です: {ext}")

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

    if moving_image.GetSize() != ref_img_sitk.GetSize():
        moving_image = sitk.Resample(moving_image, ref_img_sitk)

    matcher = sitk.HistogramMatchingImageFilter()
    matcher.SetNumberOfHistogramLevels(65536)
    matcher.SetNumberOfMatchPoints(10)
    matcher.ThresholdAtMeanIntensityOn()
    moving_image = matcher.Execute(moving_image, ref_img_sitk)

    if args.multiscale:
        transform = multi_resolution_demons(ref_img_sitk, moving_image, args.iterations, args.stddev)
    else:
        transform = single_resolution_demons(ref_img_sitk, moving_image, args.iterations, args.stddev)
    displacement_field = transform.GetDisplacementField()

    disp_np = sitk.GetArrayFromImage(displacement_field)
    magnitude = np.linalg.norm(disp_np, axis=-1)

    mean_disp = np.mean(magnitude)
    max_disp = np.max(magnitude)
    std_disp = np.std(magnitude)

    print(f"変位量:{os.path.basename(f)} - 平均: {mean_disp:.4f}, 最大: {max_disp:.4f}, 標準偏差: {std_disp:.4f}")

    resampler = sitk.ResampleImageFilter()
    resampler.SetReferenceImage(ref_img_sitk)
    resampler.SetInterpolator(sitk.sitkLinear)
    resampler.SetDefaultPixelValue(0)
    resampler.SetTransform(transform)
    aligned_sitk = resampler.Execute(moving_image)
    aligned_np = sitk.GetArrayFromImage(aligned_sitk)

    img_min = np.min(aligned_np)
    img_max = np.max(aligned_np)
    if img_max > img_min:
        img_uint16 = ((aligned_np - img_min) / (img_max - img_min) * 65535).astype(np.uint16)
    else:
        img_uint16 = np.zeros_like(aligned_np, dtype=np.uint16)

    if img_uint16.shape != (height, width):
        img_uint16 = cv2.resize(img_uint16, (width, height), interpolation=cv2.INTER_LINEAR)

    base_name = os.path.splitext(os.path.basename(f))[0]
    save_path = os.path.join(aligned_dir, f"{base_name}{ref_ext}")

    if ref_ext == '.png':
        cv2.imwrite(save_path, img_uint16)
    elif ref_ext in ['.fits', '.fit']:
        fits_data = img_uint16.astype(np.float32)
        hdu = fits.PrimaryHDU(fits_data)
        hdu.writeto(save_path, overwrite=True)
    else:
        raise ValueError(f"保存形式に対応していません: {ref_ext}")

    return img_uint16

# メイン処理
if __name__ == "__main__":
    start_time = datetime.datetime.now()
    print(f"実行開始: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    print("指定されたオプション:")
    for arg in vars(args):
        print(f"  {arg}: {getattr(args, arg)}")

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
        with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as executor:
            results = list(executor.map(process_image, input_files))
            aligned_imgs.extend(results)
    except KeyboardInterrupt:
        print("処理を中断しました。")
        exit(1)

    if args.movie:
        video_path = os.path.abspath(args.movie) if args.movie else get_next_movie_filename(movie_dir)

        # generate_movie.py を呼び出して動画生成
        script_dir = os.path.dirname(os.path.abspath(__file__))
        generate_script = os.path.join(script_dir, 'generate_movie.py')

        generate_cmd = [
            'python', generate_script,
            aligned_dir,
            video_path,
            '--fps', str(args.fps),
            '--crf', str(args.crf)
        ]
        if args.caption:
            generate_cmd += ['--caption']
        if args.caption_re:
            generate_cmd += ['--caption_re'] + args.caption_re

        print("generate_movie.py による動画生成を開始します...")
        subprocess.run(generate_cmd, check=True)
        print(f'動画を保存しました: {video_path}')

    end_time = datetime.datetime.now()
    print(f"実行終了: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    elapsed_time = end_time - start_time
    print(f"実行時間: {str(elapsed_time)}")
