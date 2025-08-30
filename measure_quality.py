# -*- coding: utf-8 -*-
import argparse
import os
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
matplotlib.rcParams['font.family'] = 'MS Gothic'
import csv
from glob import glob
import re

# FITS画像用
try:
    from astropy.io import fits
except ImportError:
    fits = None
# PNG画像用
try:
    from PIL import Image
except ImportError:
    Image = None
# OpenCV (Laplacian) 必須
try:
    import cv2
except ImportError:
    raise ImportError('OpenCV が必要です: pip install opencv-python')

def measure_quality_fits(filepath, ms_top_percent=10, ms_use_mask=True):
    if fits is None:
        raise ImportError('astropyが必要です: pip install astropy')
    with fits.open(filepath) as hdul:
        data = hdul[0].data.astype(np.float32)
    # 品質指標: コントラスト（最大値-最小値）
    contrast = float(np.max(data) - np.min(data))
    # Laplacian variance（簡易実装：2回の勾配で近似）
    # Laplacian variance: OpenCV の Laplacian を使用
    # cv2 は必須（インポート時に存在確認済み）
    lap = cv2.Laplacian(data, ddepth=cv2.CV_32F)
    lap_var = float(np.var(lap))
    # 返り値: contrast, lap_var, rim_res (rim residual)
    rim_res = compute_rim_residual(data)
    multiscale_sharpness = compute_multiscale_sharpness(data, top_percent=ms_top_percent, use_mask=ms_use_mask)
    return contrast, lap_var, rim_res, multiscale_sharpness

def measure_quality_png(filepath, ms_top_percent=10, ms_use_mask=True):
    if Image is None:
        raise ImportError('Pillowが必要です: pip install pillow')
    img = Image.open(filepath).convert('L')
    data = np.array(img, dtype=np.float32)
    contrast = float(np.max(data) - np.min(data))
    # OpenCV の Laplacian を使用
    lap = cv2.Laplacian(data, ddepth=cv2.CV_32F)
    lap_var = float(np.var(lap))
    # リム残差（輪郭フィッティング残差）を計算
    rim_res = compute_rim_residual(data)
    multiscale_sharpness = compute_multiscale_sharpness(data, top_percent=ms_top_percent, use_mask=ms_use_mask)
    return contrast, lap_var, rim_res, multiscale_sharpness

def compute_rim_residual(data):
    """円フィットに対する輪郭残差のRMSを返す（ピクセル単位）。
    data: 2D numpy array (float32)
    戻り値: float (RMS) または None (失敗時)
    """
    # 正規化して uint8 に変換
    try:
        norm = cv2.normalize(data, None, 0, 255, cv2.NORM_MINMAX)
        img8 = np.uint8(norm)
        # ノイズ除去
        blur = cv2.GaussianBlur(img8, (5, 5), 0)
        # エッジ抽出
        edges = cv2.Canny(blur, 50, 150)
        # 輪郭抽出
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if not contours:
            return None
        # 最大の輪郭を選択（点数ベース）
        contour = max(contours, key=lambda c: c.shape[0])
        pts = contour.reshape(-1, 2).astype(np.float64)
        if pts.shape[0] < 10:
            return None
        x = pts[:, 0]
        y = pts[:, 1]
        # 代数的円フィット: x^2+y^2 + A x + B y + C = 0
        A = np.column_stack([x, y, np.ones_like(x)])
        b = -(x**2 + y**2)
        try:
            p, *_ = np.linalg.lstsq(A, b, rcond=None)
        except Exception:
            return None
        xc = -p[0] / 2.0
        yc = -p[1] / 2.0
        tmp = xc*xc + yc*yc - p[2]
        if tmp <= 0:
            return None
        r = np.sqrt(tmp)
        dists = np.sqrt((x - xc)**2 + (y - yc)**2)
        resid = dists - r
        rms = float(np.sqrt(np.mean(resid**2)))
        return rms
    except Exception:
        return None


def compute_multiscale_sharpness(data, top_percent=10, use_mask=True):
    """マルチスケールシャープネス指標の実装。
    手法（簡易）:
      - 入力を float に正規化
      - 異なるガウシアン平滑化（複数スケール）で Laplacian 応答を計算
      - 応答の上位 top_percent% を各スケールで抽出し平均化、スケール間で平均化して最終スコアを得る
    戻り値: float スコア、計算失敗時は None
    """
    try:
        a = np.asarray(data, dtype=np.float32)
        if a.size == 0:
            return None
        # マルチスケール: 異なる平滑化強度でスコアを計算し平均化する
        sigmas = [1.0, 2.0, 4.0]
        scores = []
        meanv = np.mean(a)
        if meanv == 0:
            meanv = 1.0
        for sigma in sigmas:
            norm = a / (meanv + 1e-6)
            # カーネルサイズは sigma に合わせる（奇数）
            ksize = max(3, int(2 * round(3 * sigma) + 1))
            blur = cv2.GaussianBlur(norm, (ksize, ksize), sigma)
            lap = cv2.Laplacian(blur, ddepth=cv2.CV_32F)
            resp = np.abs(lap)
            if use_mask:
                h, w = resp.shape[:2]
                yy, xx = np.ogrid[:h, :w]
                cy, cx = h/2.0, w/2.0
                r = min(h, w) * 0.45
                mask = ((yy - cy)**2 + (xx - cx)**2) <= (r*r)
                resp_vals = resp[mask]
            else:
                resp_vals = resp.ravel()
            if resp_vals.size == 0:
                continue
            k = max(1, int(len(resp_vals) * (top_percent/100.0)))
            thresh = np.partition(resp_vals, -k)[-k]
            top_vals = resp_vals[resp_vals >= thresh]
            scores.append(float(np.mean(top_vals)))
        if not scores:
            return None
        # 各スケールの平均を返す
        return float(np.mean(scores))
    except Exception:
        return None

def main():
    parser = argparse.ArgumentParser(description='太陽画像の品質計測スクリプト')
    parser.add_argument('dir', help='画像ディレクトリ')
    parser.add_argument('--type', choices=['fits', 'png'], required=True, help='画像形式')
    parser.add_argument('--csv', help='品質数値をCSV出力する場合はファイル名を指定')
    parser.add_argument('--input_filter', help='入力ファイルのベースネームに対する正規表現フィルタ（拡張子とディレクトリは除く）')
    parser.add_argument('--ms-top-percent', type=int, default=10, help='multiscale_sharpness の上位パーセンタイル（デフォルト10）')
    parser.add_argument('--ms-no-mask', dest='ms_use_mask', action='store_false', help='multiscale_sharpness で中心マスクを使わない')
    parser.set_defaults(ms_use_mask=True)
    args = parser.parse_args()

    if args.type == 'fits':
        ext = '*.fits'
        measure_func = measure_quality_fits
    else:
        ext = '*.png'
        measure_func = measure_quality_png

    files = sorted(glob(os.path.join(args.dir, ext)))
    # 入力ベースネームに対する正規表現フィルタが指定されていれば適用
    if getattr(args, 'input_filter', None):
        try:
            pattern = re.compile(args.input_filter)
        except re.error as e:
            print(f'--input_filter の正規表現が無効です: {e}')
            return
        filtered = []
        for f in files:
            bn = os.path.splitext(os.path.basename(f))[0]
            if pattern.search(bn):
                filtered.append(f)
        files = filtered
    if not files:
        print('画像が見つかりません')
        return

    qualities = []
    for f in files:
        print(f'評価中: {os.path.basename(f)}', flush=True)
        try:
            q = measure_func(f, ms_top_percent=args.ms_top_percent, ms_use_mask=args.ms_use_mask)
            # q は (contrast, lap_var, rim_res, multiscale_sharpness)
        except Exception as e:
            print(f'{f} の品質計算失敗: {e}')
            q = (None, None, None, None)
        qualities.append((os.path.basename(f), q))

    # 横棒グラフ + 並べ替えコントロール
    import matplotlib.widgets as mwidgets

    # データ抽出
    # qualities の各要素: (filename, (contrast, lap_var, rim_res, multiscale_sharpness))
    valid_data = [(x[0], x[1][0], x[1][1], x[1][2], x[1][3]) for x in qualities if x[1][0] is not None]
    if not valid_data:
        print('有効な品質データがありません')
        return
    # 全ファイルのコントラスト最小値（後で軸開始に使用）
    try:
        global_min_contrast = min(x[1] for x in valid_data if x[1] is not None)
    except ValueError:
        global_min_contrast = None

    def sort_data(mode, metric_index=1):
        # valid_data: (filename, contrast, lap_var)
        if mode == 'filename':
            return sorted(valid_data, key=lambda x: x[0])
        elif mode == 'quality':
            # metric_index に応じて昇順／降順を選ぶ
            # contrast/lap (1/2) は降順（大きいほど良い）、rim (3) は昇順（小さいほど良い）
            if metric_index == 3:
                # None は +inf にして末尾に来るようにする（昇順）
                def key_fn(x):
                    v = x[metric_index]
                    return float('inf') if v is None else v
                return sorted(valid_data, key=key_fn, reverse=False)
            else:
                # None は -inf にして末尾に来るようにする（降順）
                def key_fn(x):
                    v = x[metric_index]
                    return v if v is not None else float('-inf')
                return sorted(valid_data, key=key_fn, reverse=True)
        else:
            return valid_data

    # 初期表示はファイル名順
    sort_mode = 'filename'
    # metric_index: 1=contrast, 2=lap_var, 3=rim_res, 4=autostakkert_like
    metric_index = 1
    sorted_data = sort_data(sort_mode, metric_index)
    # 逆順にする
    sorted_data = list(reversed(sorted_data))
    names = [x[0] for x in sorted_data]
    values = [x[metric_index] for x in sorted_data]

    # CSV出力（必ず保存されるようにグラフ表示前に実行）
    if args.csv:
        with open(args.csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['filename', 'contrast', 'laplacian_variance', 'rim_residual', 'multiscale_sharpness'])
            for name, val in qualities:
                if val is None:
                    # 計算に失敗した場合は空欄（空セル）にする
                    writer.writerow([name, '', '', '', ''])
                else:
                    # val は (contrast, lap_var, rim_res, multiscale_sharpness)
                    # None 値は空欄にする
                    out = [name]
                    for item in val:
                        out.append('' if item is None else item)
                    writer.writerow(out)
        print(f'CSV出力: {args.csv}')

    # 1目盛りの高さを文字の高さの120%にする
    font_size_pt = plt.rcParams['font.size'] if 'font.size' in plt.rcParams else 12
    # pt→inch換算（1inch=72pt）
    bar_height_inch = font_size_pt * 1.2 / 72
    # 行数が少ない場合でも各行の高さを保つため最小行数を確保する
    min_display_rows = 20
    display_rows = max(len(names), min_display_rows)
    fig_height = display_rows * bar_height_inch
    import tkinter as tk
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

    # Tkinterウィンドウ作成
    root = tk.Tk()
    root.title('画像品質 横棒グラフ')
    window_width = 900
    window_height = 600
    root.geometry(f'{window_width}x{window_height}')

    # スクロール用Frame
    frame = tk.Frame(root)
    frame.pack(fill=tk.BOTH, expand=True)

    # Canvas + Scrollbar
    vbar_width = 18  # スクロールバーの幅（px）
    canvas = tk.Canvas(frame)
    vbar = tk.Scrollbar(frame, orient=tk.VERTICAL, command=canvas.yview)
    canvas.configure(yscrollcommand=vbar.set)
    vbar.pack(side=tk.RIGHT, fill=tk.Y)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    # matplotlib Figure作成（目盛り高さ固定）
    fig, ax = plt.subplots(figsize=(max(8, 5), fig_height))
    # 余白を広めにとってファイル名が収まるようにする
    fig.subplots_adjust(left=0.30, right=0.98, top=0.88, bottom=0.02)
    bars = ax.barh(names, values)
    ax.set_xlabel('品質（コントラスト）', loc='left')
    ax.set_ylabel('ファイル名')
    ax.set_title('画像品質 横棒グラフ')
    ax.xaxis.set_label_position('top')
    ax.xaxis.tick_top()
    ax.spines['right'].set_visible(False)  # 右端の縦線を非表示
    # コントラスト指標の場合、横軸開始を全ファイルの最小コントラスト-1000 の下3桁を0にした値に設定
    if metric_index == 1 and global_min_contrast is not None:
        start_num = int(global_min_contrast) - 1000
        start = (start_num // 1000) * 1000
        start = max(start, 0)
        ax.set_xlim(left=start)
    # 各横棒の右端に品質数値を描画（指標に応じて表示桁数を調整）
    pad = max(values)*0.01 if values else 1.0
    # ytick のフォントサイズを明示
    ytick_fs = font_size_pt
    ax.tick_params(axis='y', labelsize=ytick_fs)
    for i, (bar, val) in enumerate(zip(bars, values)):
        if metric_index == 4:
            label_text = f'{val:.4f}'
        elif metric_index == 1:
            label_text = f'{val:.1f}'
        else:
            label_text = f'{val:.3f}' if abs(val) < 1 else f'{val:.1f}'
        ax.text(val + pad, bar.get_y() + bar.get_height()/2, label_text, va='center', ha='left', fontsize=10)
    fig.tight_layout(pad=0.6)

    # 並べ替え/指標選択コントロール
    control_frame = tk.Frame(root)
    control_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=8)
    # --- ファイル順 / 品質降順 ラジオボタングループ（横並び）
    sort_group = tk.Frame(control_frame)
    sort_group.pack(anchor=tk.N, pady=(10,0))
    sort_var = tk.StringVar(value='ファイル名順')
    radio1 = tk.Radiobutton(sort_group, text='ファイル名順', variable=sort_var, value='ファイル名順')
    radio2 = tk.Radiobutton(sort_group, text='品質順', variable=sort_var, value='品質順')
    radio1.pack(side=tk.LEFT, padx=4)
    radio2.pack(side=tk.LEFT, padx=4)
    # --- 指標選択グループ（横並び）
    metric_group = tk.Frame(control_frame)
    metric_group.pack(anchor=tk.N, pady=(20,0))
    metric_var = tk.StringVar(value='contrast')
    m1 = tk.Radiobutton(metric_group, text='コントラスト', variable=metric_var, value='contrast')
    m2 = tk.Radiobutton(metric_group, text='Laplacian variance', variable=metric_var, value='lap')
    m3 = tk.Radiobutton(metric_group, text='リム残差', variable=metric_var, value='rim')
    m4 = tk.Radiobutton(metric_group, text='マルチスケールシャープネス', variable=metric_var, value='ms')
    m1.pack(side=tk.LEFT, padx=4)
    m2.pack(side=tk.LEFT, padx=4)
    m3.pack(side=tk.LEFT, padx=4)
    m4.pack(side=tk.LEFT, padx=4)
    # 指標切替で再描画されるようにコマンドは後で設定（update_graph_tk 定義後）

    # FigureCanvasをCanvasに埋め込む
    fig_canvas = FigureCanvasTkAgg(fig, master=canvas)
    fig_widget = fig_canvas.get_tk_widget()
    fig_canvas.draw()  # 明示的に描画
    fig_widget.update_idletasks()
    # Canvasの幅をframeの幅-スクロールバー幅に調整
    def resize_canvas(event=None, retry_count=0):
        frame_width = frame.winfo_width()
        canvas_width = max(frame_width - vbar_width, 100)
        canvas.config(width=canvas_width)
        canvas.update_idletasks()
        fig_widget.update_idletasks()
        fw = canvas.winfo_width()
        gw = fig_widget.winfo_width()
        if gw == 0 and retry_count < 5:
            # 幅が取得できない場合は再度遅延呼び出し（最大5回）
            root.after(200, lambda: resize_canvas(None, retry_count+1))
            return
        x_center = max((fw - gw) // 2, 0)
        canvas.delete('all')
        canvas.create_window((x_center, 0), window=fig_widget, anchor='nw')
        canvas.config(scrollregion=canvas.bbox("all"))
    frame.bind('<Configure>', resize_canvas)
    root.after(100, resize_canvas)
    root.after(300, lambda: resize_canvas(None, 1))
    root.after(600, lambda: resize_canvas(None, 2))

    # ウィンドウを閉じたときにプログラムを終了
    def on_closing():
        import matplotlib.pyplot as plt
        plt.close('all')
        root.quit()
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_closing)

    def update_graph_tk():
        label = sort_var.get()
        if label == 'ファイル名順':
            mode = 'filename'
        else:
            mode = 'quality'
        # metric選択
        sel = metric_var.get()
        if sel == 'contrast':
            metric_idx = 1
        elif sel == 'lap':
            metric_idx = 2
        elif sel == 'rim':
            metric_idx = 3
        else:
            metric_idx = 4
        sorted_data = sort_data(mode, metric_idx)
        sorted_data = list(reversed(sorted_data))
        # 指標が None の行は除外して描画
        filtered = [r for r in sorted_data if r[metric_idx] is not None]
        ax.clear()
        if not filtered:
            ax.text(0.5, 0.5, '選択した指標に有効なデータがありません', ha='center', va='center', transform=ax.transAxes)
            ax.set_xlabel('')
            fig_canvas.draw()
            fig_widget.update_idletasks()
            canvas.config(scrollregion=canvas.bbox("all"))
            return
        names = [x[0] for x in filtered]
        values = [float(x[metric_idx]) for x in filtered]
        bars = ax.barh(names, values)
        # コントラスト指標の場合、横軸開始を全ファイルの最小コントラスト-1000 の下3桁を0にした値に設定
        if sel == 'contrast' and global_min_contrast is not None:
            start_num = int(global_min_contrast) - 1000
            start = (start_num // 1000) * 1000
            start = max(start, 0)
            ax.set_xlim(left=start)
        # 軸ラベルを選択した指標に合わせる
        if sel == 'contrast':
            xlabel_label = '品質（コントラスト）'
        elif sel == 'lap':
            xlabel_label = '品質（Laplacian variance）'
        elif sel == 'rim':
            xlabel_label = '品質（リム残差）'
        else:
            xlabel_label = '品質（マルチスケールシャープネス）'
        ax.set_xlabel(xlabel_label, loc='left')
        ax.set_ylabel('ファイル名')
        ax.set_title('画像品質 横棒グラフ')
        ax.xaxis.set_label_position('top')
        ax.xaxis.tick_top()
        ax.spines['right'].set_visible(False)  # 右端の縦線を非表示
        # 各横棒の右端に品質数値を描画
        pad = max(values)*0.01 if values else 1.0
        # ytick のフォントサイズを明示
        ax.tick_params(axis='y', labelsize=font_size_pt)
        for i, (bar, val) in enumerate(zip(bars, values)):
            # 選択指標 sel に応じたラベル表示
            if sel == 'ms':
                label_text = f'{val:.4f}'
            elif sel == 'contrast':
                label_text = f'{val:.1f}'
            else:
                label_text = f'{val:.3f}' if abs(val) < 1 else f'{val:.1f}'
            ax.text(val + pad, bar.get_y() + bar.get_height()/2, label_text, va='center', ha='left', fontsize=10)
        fig.tight_layout(pad=0.6)
        fig_canvas.draw()
        fig_widget.update_idletasks()
        canvas.config(scrollregion=canvas.bbox("all"))

    radio1.config(command=update_graph_tk)
    radio2.config(command=update_graph_tk)

    # metric ラジオボタンのコマンドをここで設定（update_graph_tk が定義済み）
    m1.config(command=update_graph_tk)
    m2.config(command=update_graph_tk)
    m3.config(command=update_graph_tk)
    m4.config(command=update_graph_tk)

    root.mainloop()

if __name__ == '__main__':
    main()
