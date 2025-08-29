# -*- coding: utf-8 -*-
import argparse
import os
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
matplotlib.rcParams['font.family'] = 'MS Gothic'
import csv
from glob import glob

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

def measure_quality_fits(filepath):
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
    return contrast, lap_var, rim_res

def measure_quality_png(filepath):
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
    return contrast, lap_var, rim_res

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

def main():
    parser = argparse.ArgumentParser(description='太陽画像の品質計測スクリプト')
    parser.add_argument('dir', help='画像ディレクトリ')
    parser.add_argument('--type', choices=['fits', 'png'], required=True, help='画像形式')
    parser.add_argument('--csv', help='品質数値をCSV出力する場合はファイル名を指定')
    args = parser.parse_args()

    if args.type == 'fits':
        ext = '*.fits'
        measure_func = measure_quality_fits
    else:
        ext = '*.png'
        measure_func = measure_quality_png

    files = sorted(glob(os.path.join(args.dir, ext)))
    if not files:
        print('画像が見つかりません')
        return

    qualities = []
    for f in files:
        print(f'評価中: {os.path.basename(f)}', flush=True)
        try:
            q = measure_func(f)
            # q は (contrast, lap_var)
        except Exception as e:
            print(f'{f} の品質計算失敗: {e}')
            q = (None, None)
        qualities.append((os.path.basename(f), q))

    # 横棒グラフ + 並べ替えコントロール
    import matplotlib.widgets as mwidgets

    # データ抽出
    # qualities の各要素: (filename, (contrast, lap_var, rim_res))
    valid_data = [(x[0], x[1][0], x[1][1], x[1][2]) for x in qualities if x[1][0] is not None]
    if not valid_data:
        print('有効な品質データがありません')
        return

    def sort_data(mode, metric_index=1):
        # valid_data: (filename, contrast, lap_var)
        if mode == 'filename':
            return sorted(valid_data, key=lambda x: x[0])
        elif mode == 'quality':
            # None を比較可能にするため、None を -inf に置換してソートする。
            def key_fn(x):
                v = x[metric_index]
                return v if v is not None else float('-inf')
            return sorted(valid_data, key=key_fn, reverse=True)
        else:
            return valid_data

    # 初期表示はファイル名順
    sort_mode = 'filename'
    # metric_index: 1=contrast, 2=lap_var, 3=rim_res
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
            writer.writerow(['filename', 'contrast', 'laplacian_variance', 'rim_residual'])
            for name, val in qualities:
                if val is None:
                    writer.writerow([name, 'error', 'error', 'error'])
                else:
                    # val は (contrast, lap_var, rim_res)
                    writer.writerow([name, val[0], val[1], val[2]])
        print(f'CSV出力: {args.csv}')

    # 1目盛りの高さを文字の高さの120%にする
    font_size_pt = plt.rcParams['font.size'] if 'font.size' in plt.rcParams else 12
    # pt→inch換算（1inch=72pt）
    bar_height_inch = font_size_pt * 1.2 / 72
    fig_height = len(names) * bar_height_inch
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
    bars = ax.barh(names, values)
    ax.set_xlabel('品質（コントラスト）', loc='left')
    ax.set_ylabel('ファイル名')
    ax.set_title('画像品質 横棒グラフ')
    ax.xaxis.set_label_position('top')
    ax.xaxis.tick_top()
    ax.spines['right'].set_visible(False)  # 右端の縦線を非表示
    # 各横棒の右端に品質数値を描画
    pad = max(values)*0.01 if values else 1.0
    for i, (bar, val) in enumerate(zip(bars, values)):
        ax.text(val + pad, bar.get_y() + bar.get_height()/2, f'{val:.1f}', va='center', ha='left', fontsize=10)
    plt.tight_layout()

    # 並べ替え/指標選択コントロール
    control_frame = tk.Frame(root)
    control_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=8)
    # --- ファイル順 / 品質降順 ラジオボタングループ（横並び）
    sort_group = tk.Frame(control_frame)
    sort_group.pack(anchor=tk.N, pady=(10,0))
    sort_var = tk.StringVar(value='ファイル名順')
    radio1 = tk.Radiobutton(sort_group, text='ファイル名順', variable=sort_var, value='ファイル名順')
    radio2 = tk.Radiobutton(sort_group, text='品質降順', variable=sort_var, value='品質降順')
    radio1.pack(side=tk.LEFT, padx=4)
    radio2.pack(side=tk.LEFT, padx=4)
    # --- 指標選択グループ（横並び）
    metric_group = tk.Frame(control_frame)
    metric_group.pack(anchor=tk.N, pady=(20,0))
    metric_var = tk.StringVar(value='contrast')
    m1 = tk.Radiobutton(metric_group, text='コントラスト', variable=metric_var, value='contrast')
    m2 = tk.Radiobutton(metric_group, text='Laplacian variance', variable=metric_var, value='lap')
    m3 = tk.Radiobutton(metric_group, text='リム残差', variable=metric_var, value='rim')
    m1.pack(side=tk.LEFT, padx=4)
    m2.pack(side=tk.LEFT, padx=4)
    m3.pack(side=tk.LEFT, padx=4)
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
        else:
            metric_idx = 3
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
        # 軸ラベルを選択した指標に合わせる
        if sel == 'contrast':
            xlabel_label = '品質（コントラスト）'
        elif sel == 'lap':
            xlabel_label = '品質（Laplacian variance）'
        else:
            xlabel_label = '品質（リム残差）'
        ax.set_xlabel(xlabel_label, loc='left')
        ax.set_ylabel('ファイル名')
        ax.set_title('画像品質 横棒グラフ')
        ax.xaxis.set_label_position('top')
        ax.xaxis.tick_top()
        ax.spines['right'].set_visible(False)  # 右端の縦線を非表示
        # 各横棒の右端に品質数値を描画
        pad = max(values)*0.01 if values else 1.0
        for i, (bar, val) in enumerate(zip(bars, values)):
            ax.text(val + pad, bar.get_y() + bar.get_height()/2, f'{val:.1f}', va='center', ha='left', fontsize=10)
        plt.tight_layout()
        fig_canvas.draw()
        fig_widget.update_idletasks()
        canvas.config(scrollregion=canvas.bbox("all"))

    radio1.config(command=update_graph_tk)
    radio2.config(command=update_graph_tk)

    # metric ラジオボタンのコマンドをここで設定（update_graph_tk が定義済み）
    m1.config(command=update_graph_tk)
    m2.config(command=update_graph_tk)
    m3.config(command=update_graph_tk)

    root.mainloop()

if __name__ == '__main__':
    main()
