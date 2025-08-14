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

    ```PowerShell
    PS> git clone https://github.com/jctk/MakeTimelapse.git
    PS> cd MakeTimelapse
    ```

## ディレクトリ

- リポジトリに登録されているフォルダー

```Text
MAKETIMELAPSE       プロジェクトのルートフォルダ。実利用するスクリプトを保存
├─.vscode           vscode用設定
├─samples           各種サンプルデータ用フォルダ
│  ├─10_simple      単純な画像による検証用
│  │  └─input
│  ├─20_sun_half    小さめの太陽の画像による検証用(JSol'Ex Geometory corrected)
│  │  └─input
│  ├─30_sun_full_autostretch    大きい太陽の画像による検証用(JSol'Ex Geometory corrected(processed))
│  │  └─input
│  ├─40_sun_full_disk   大きい太陽の画像による検証用(JSol'Ex Geometory corrected)
│  │  └─input
│  └─90_postprocess 後処理用素材(Shotcutで使用するファイルなど)
└─tools             検証などで使用する一括処理用ツール
```

## 実行手順

1. Sol'Exで太陽を複数撮影
1. JSol'ExのBatchモードで画像を出力
    - 確認済みの主な条件
        - Process Parameter
            - Autocorrect P angle: ON
            - Rescale to full resolution (allow oversampling): ON or OFF
        - Miscellaneous
            - Assume mono imamges: ON
            - Generate FITS files: ON
        - Custom process: Image selection ※以下いずれの画像も可
            - Geometry corrected iamge: ON
            - Geometry corrected iamge (processed): ON
1. make_timelapse.py を実行、複数の画像の位置合わせと動画の生成
    - JSol'Ex で生成した画像から位置合わせに使用する基準画像を選択する。真円に近い、表面が緻密、歪みが少ない、などの条件に合う画像が望ましい。
    - 画像サイズは一致しているのが望ましい。一致していない場合も処理はできるが、太陽のサイズが均一になるようにトリミングされているのがよい。
    - 位置合わせが合わない場合、位置合わせ後の画像を入力として再度位置合わせを行うことも可
    - make_timelapse.py のフロントエンドGUIの make_timelapse_gui.py の利用可
1. （任意）gemerate_movie.py の実行
    - make_timelapse.py が出力した位置合わせ画像を元に動画の作成が可能

## 各コマンドの説明

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
  --caption             各フレームの左下にファイル名を表示する
  --caption_re PATTERN REPLACEMENT
                        ファイル名の置換（正規表現）: PATTERN を REPLACEMENT に置換
```

### make_timelapse_gui.py

- make_timelapse.py のフロントエンドとなる gui

### gemerate_movie.py

- 画像（PNG, FITS）から FFmpeg を使って動画を生成する。
- 通常このスクリプトは使用しない。make_timelapse.py で位置合わせ後に動画の生成も行うため。
- make_timelapse.py で画像を選定しての位置補正を再度行った場合に、再実行なしと再実行したファイルを一つのフォルダーに集めてからこのスクリプトを用いて動画を作成する。

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

- このスクリプトは基本的に使用しない。make_timelapse.py で基準画像に合わせたヒストグラムの調整を行うので必要がない。

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

## 仕組み - マルチスケール位置合わせ

- 以下は make_timelapse.py のオプション --multiscale を実現する `multi_resolution_demons` 関数の仕組み

- `multi_resolution_demons` 関数は、画像の位置合わせ（レジストレーション）を高精度かつ安定的に行うために、**マルチスケール（多段階）処理**を用いた Demons アルゴリズムの実装である。画像の解像度を段階的に変えながら変位場（displacement field）を更新することで、ノイズの影響を抑えつつ、より滑らかで正確な位置合わせを実現する。

### 処理の流れ

1. **初期変位場の作成**  
   基準画像（`fixed`）と同じサイズ・情報を持つ初期の変位場（`initial_field`）を作成する。これは後の各スケールでの変形のベースとなる。

2. **スケールごとの処理**  
   以下の3段階の縮小率（shrink factor）で画像を処理する：

   - 4倍縮小（粗いスケール）
   - 2倍縮小（中間スケール）
   - 元のサイズ（細かいスケール）

   各スケールでは以下の処理を行う：

   - 基準画像と移動画像を指定の縮小率でリサンプリング（`sitk.Shrink`）
   - 変位場も同様にリサンプリング
   - `FastSymmetricForcesDemonsRegistrationFilter` を用いて変位場を更新
   - 更新された変位場を次のスケールにリサンプリングして引き継ぐ

3. **最終変形の適用**  
   最終的に得られた変位場を用いて `DisplacementFieldTransform` を作成し、移動画像に対して位置合わせを行う。

### 特徴と利点

- 粗いスケールから始めることで大きな構造の整合性を確保し、細かいスケールで微細な調整を行うため、**局所的なノイズや誤差の影響を軽減**できる。
- 各スケールでの反復回数は、全体の反復回数に対して割合で指定されており、**効率的な処理**が可能である。
- `FastSymmetricForcesDemonsRegistrationFilter` を使用することで、通常の Demons よりも**高速かつ安定した変形推定**が可能である。
