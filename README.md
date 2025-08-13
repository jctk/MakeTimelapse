# MakeTimelapse

MakeTimelapse は、JSol'Exの画像ファイルからタイムラプス動画を生成するツールです。  
個人的に作成したツールですのでうまくいかない場合もご容赦ください。  
特に生成に使用する画像の形式は限定されています。

## 特徴

- 画像の自動並び替え（タイムスタンプ順）
- 高品質なタイムラプス動画の生成
- シンプルなコマンドライン操作
- カスタマイズ可能なフレームレートと解像度

## 導入条件

- Windows 11
- おそらく Linux でも実行可能

## 導入

以下手順で実行環境を構築する

1. 以下ソフトウェアを導入。環境変数PATHを通すこと。
    - 必須
        - python
        - FFmpeg
    - 任意
        - PowerShell 7

2. pythonのライブラリの導入

    ```PowerShell
    PS> pip install numpy astropy opencv-python SimpleITK
    ```

3. スクリプトの展開
    - スクリプトを clone する。
    - サンプル画像も clone される。

    ```PowerShell
    PS> git clone https://github.com/jctk/MakeTimelapse.git
    PS> cd MakeTimelapse
    ```

## ディレクトリ

- To-Do: *****

## 実行手順

1. Sol'Exで太陽を複数撮影
1. JSol'ExのBatchモードで画像を出力
    - 確認済みの主な条件
        - Process Parameter
            - [x] Autocorrect P angle
            - [x] or [ ] Rescale to full resolution (allow oversampling)
        - Miscellaneous
            - [x] Assume mono imamges
            - [x] Generate FITS files
        - Custom process: Image selection
            - [x] Geometry corrected iamge
            - [x] Geometry corrected iamge (processed)
1. make_timelapse.py を実行、複数の画像の位置合わせと動画の生成
    - JSol'Ex で生成した画像から位置合わせに使用する基準画像を選択する。真円に近い、表面が緻密、歪みが少ない、などの条件に合う画像が望ましい。
    - 画像サイズは一致しているのが望ましい。一致していない場合も処理はできるが、太陽のサイズが均一になるようにトリミングされているのがよい。
    - 位置合わせが合わない場合、位置合わせ後の画像を入力として再度位置合わせを行うことも可
1. （任意）gemerate_movie.py の実行
    - make_timelapse.py が出力した位置合わせ画像を元に動画の作成が可能

## 各コマンドの説明

- To-Do: *****

### make_timelapse.py

```PowerShell
PS MakeTimelapse> python .\make_timelapse.py --help
usage: make_timelapse.py [-h] --ref REF [--input_dir INPUT_DIR] [--aligned_dir ALIGNED_DIR] [--movie MOVIE] [--iterations ITERATIONS] [--stddev STDDEV] [--workers WORKERS] [--fast]
                         [--multiscale] [--crf CRF] [--fps FPS]

Sol'Ex画像の歪み補正タイムラプス作成

options:
  -h, --help            show this help message and exit
  --ref REF             基準となるモノクロ画像（fits, fit, png）のファイルのパス
  --input_dir INPUT_DIR
                        入力画像ファイル（fits, fit, png）のフォルダー
  --aligned_dir ALIGNED_DIR
                        位置合わせ後画像の保存フォルダー
  --movie MOVIE         動画の出力ファイル名
  --iterations ITERATIONS
                        DemonsRegistrationFilterの反復回数
  --stddev STDDEV       DemonsRegistrationFilterの標準偏差
  --workers WORKERS     並列処理のワーカー数（デフォルトはCPUコア数）
  --fast                高速版DemonsRegistrationFilterを使用する
  --multiscale          マルチスケール Demons を使用する(実験的実装)
  --crf CRF             ffmpegの画質設定（デフォルト: 23）
  --fps FPS             動画のフレームレート（デフォルト: 7）
```

### gemerate_movie.py

- To-Do: *****

```PowerShell
PS MakeTimelapse> python .\generate_movie.py --help
usage: generate_movie.py [-h] [--fps FPS] [--crf CRF] [--caption] [--caption_re PATTERN REPLACEMENT] input_dir output_file

画像（PNG, FITS）から FFmpeg を使って動画を生成します。

positional arguments:
  input_dir             画像が含まれる入力ディレクトリ
  output_file           生成する動画ファイル名（例: output.mp4）

options:
  -h, --help            show this help message and exit
  --fps FPS             動画のフレームレート（デフォルト: 10）
  --crf CRF             画質（CRF値 1～50、デフォルト: 23）
  --caption             各フレームの左下にファイル名を表示する
  --caption_re PATTERN REPLACEMENT
                        ファイル名の置換（正規表現）: PATTERN を REPLACEMENT に置換
```

### nomalize_image.py

- To-Do: *****

```PowerShell
PS MakeTimelapse> python .\normalize_images.py --help
usage: normalize_images.py [-h] --ref REF --input_dir INPUT_DIR --output_dir OUTPUT_DIR

Normalize contrast and brightness of 16-bit PNG images using a reference image.

options:
  -h, --help            show this help message and exit
  --ref REF             Path to the reference image
  --input_dir INPUT_DIR
                        Path to the input directory containing PNG images
  --output_dir OUTPUT_DIR
                        Path to the output directory to save processed images
```

## 仕組み

- To-Do: *****