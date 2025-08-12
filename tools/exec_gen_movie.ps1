$input_dirs = @(
    "aligned_800_normalized",
    "aligned_1200_normalized",
    "aligned_1600_normalized",
    "aligned_2000_normalized",
    "aligned_2400_normalized",
    "fits_tmp_normalized"
)

foreach ($input_dir in $input_dirs) {
    $cmd = @(
        "python", "generate_movie.py",
        $input_dir,
        "movie/timelapse_$input_dir.mp4"
    )

    Write-Host "実行: $($cmd -join ' ')"

    $startTime = Get-Date
    Write-Host "開始時刻: $startTime"

    & $cmd[0] $cmd[1..($cmd.Length - 1)]
    
    $endTime = Get-Date
    Write-Host "終了時刻: $endTime"

    $duration = New-TimeSpan -Start $startTime -End $endTime
    Write-Host "実行時間: $($duration.ToString())"
}
