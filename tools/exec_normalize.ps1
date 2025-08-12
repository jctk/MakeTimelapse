$input_dirs = @(
    ".\aligned_800",
    ".\aligned_1200",
    ".\aligned_1600",
    ".\aligned_2000",
    ".\aligned_2400",
    ".\fits_tmp"
)

foreach ($input_dir in $input_dirs) {
    $normalized_dir = "$($input_dir)_normalized"
    $cmd = @(
        "python", "normalize_images.py",
        "--ref", "./$input_dir/aligned_14_18_32_2025-07-29T205504_disk_0_00.png",
        "--input_dir", $input_dir,
        "--output_dir", $normalized_dir
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
