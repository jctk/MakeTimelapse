<#
    This script processes FITS files to create timelapse videos.

    入力ファイル:モノクロ形式のみ
    出力ファイル:動画形式 mp4
#>

# DemonsRegistration の繰返し回数を指定
# $iterations_list = @(800, 1200, 1600, 2000)
$iterations_list = @(800)

# 処理タイプのリスト
# $proc_type_list = @("", "_fftregi", "_imppg")
$proc_type_list = @("")

# 平準化と平準化後の動画生成を行うかどうか
$normalize = $false

# 参照画像のベース名
#$ref_basename = "14_34_55_2025-08-12T014716_autostretch_0_00"
$ref_basename = "14_34_55_2025-07-29T205504_disk_0_00"

# サンプルフォルダ
$sample_dir = "samples/40_sun_full_disk"

# input ディレクトリのベース名
$input_dir_basename = "$sample_dir/input"

$proc_type_list | ForEach-Object {
    $proc_type = $_
    $input_dir = "$input_dir_basename$proc_type"
    $ref = "$input_dir/$ref_basename.fits"

    if (-Not (Test-Path $input_dir)) {
        Write-Host "ディレクトリが存在しません: $input_dir"
        return
    }

    if (-Not (Test-Path $ref)) {
        Write-Host "参照ファイルが存在しません: $ref"
        return
    }

    Write-Host "処理タイプ: $_, input_dir: $input_dir, ref: $ref"

    $iterations_list | ForEach-Object {
        #
        # 歪み補正
        #
        $iters = $_
        $aligned_dir = "$sample_dir/aligned_$iters$proc_type"
        
        $movie = "$sample_dir/timelapse_$iters$proc_type.mp4"
        $align_cmd = @(
            "python", "make_timelapse.py",
            "--ref", $ref,
            "--input_dir", $input_dir,
            "--aligned_dir", $aligned_dir,
            "--movie", $movie,
            "--iterations", "$iters",
            "--stddev", "4.0",
            "--workers", "8"
        )

        Write-Host "歪み補正 実行: $($align_cmd -join ' ')"

        $startTime = Get-Date
        Write-Host "歪み補正 開始時刻: $startTime"

        & $align_cmd[0] $align_cmd[1..($align_cmd.Length - 1)]
        
        $endTime = Get-Date
        Write-Host "歪み補正 終了時刻: $endTime"

        $duration = New-TimeSpan -Start $startTime -End $endTime
        Write-Host "歪み補正 実行時間: $($duration.ToString())"

        if ($normalize) {
            #
            # 平準化
            #
            $normalized_dir = "$($aligned_dir)_normalized"
            $normalize_cmd = @(
                "python", "../normalize_images.py",
                "--ref", "./$aligned_dir/aligned_$ref_basename.png",
                "--input_dir", $aligned_dir,
                "--output_dir", $normalized_dir
            )

            Write-Host "平準化 実行: $($normalize_cmd -join ' ')"

            $startTime = Get-Date
            Write-Host "平準化 開始時刻: $startTime"

            & $normalize_cmd[0] $normalize_cmd[1..($normalize_cmd.Length - 1)]
            
            $endTime = Get-Date
            Write-Host "平準化 終了時刻: $endTime"

            $duration = New-TimeSpan -Start $startTime -End $endTime
            Write-Host "平準化 実行時間: $($duration.ToString())"

            #
            # 動画作成
            #
            $genmovie_cmd = @(
                "python", "generate_movie.py",
                $normalized_dir,
                "movie/timelapse_$normalized_dir.mp4"
            )

            Write-Host "動画作成 実行: $($genmovie_cmd -join ' ')"

            $startTime = Get-Date
            Write-Host "動画作成 開始時刻: $startTime"

            & $genmovie_cmd[0] $genmovie_cmd[1..($genmovie_cmd.Length - 1)]
            
            $endTime = Get-Date
            Write-Host "動画作成 終了時刻: $endTime"

            $duration = New-TimeSpan -Start $startTime -End $endTime
            Write-Host "動画作成 実行時間: $($duration.ToString())"
        }
    }
}

