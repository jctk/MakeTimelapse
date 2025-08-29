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

def measure_quality_fits(filepath):
    if fits is None:
        raise ImportError('astropyが必要です: pip install astropy')
    with fits.open(filepath) as hdul:
        data = hdul[0].data.astype(np.float32)
    # 品質指標: コントラスト（最大値-最小値）
    return float(np.max(data) - np.min(data))

def measure_quality_png(filepath):
    if Image is None:
        raise ImportError('Pillowが必要です: pip install pillow')
    img = Image.open(filepath).convert('L')
    data = np.array(img, dtype=np.float32)
    return float(np.max(data) - np.min(data))

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
        try:
            q = measure_func(f)
        except Exception as e:
            print(f'{f} の品質計算失敗: {e}')
            q = None
        qualities.append((os.path.basename(f), q))

    # 横棒グラフ + 並べ替えコントロール
    import matplotlib.widgets as mwidgets

    # データ抽出
    valid_data = [(x[0], x[1]) for x in qualities if x[1] is not None]
    if not valid_data:
        print('有効な品質データがありません')
        return

    def sort_data(mode):
        if mode == 'filename':
            return sorted(valid_data, key=lambda x: x[0])
        elif mode == 'quality':
            return sorted(valid_data, key=lambda x: x[1], reverse=True)
        else:
            return valid_data

    # 初期表示はファイル名順
    sort_mode = 'filename'
    sorted_data = sort_data(sort_mode)
    # 逆順にする
    sorted_data = list(reversed(sorted_data))
    names = [x[0] for x in sorted_data]
    values = [x[1] for x in sorted_data]

    # CSV出力（必ず保存されるようにグラフ表示前に実行）
    if args.csv:
        with open(args.csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['filename', 'quality'])
            for name, val in qualities:
                writer.writerow([name, val if val is not None else 'error'])
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
    for i, (bar, val) in enumerate(zip(bars, values)):
        ax.text(val + max(values)*0.01, bar.get_y() + bar.get_height()/2, f'{val:.1f}', va='center', ha='left', fontsize=10)
    plt.tight_layout()

    # 並べ替えコントロール（ラジオボタン）
    radio_frame = tk.Frame(root)
    radio_frame.pack(side=tk.RIGHT, fill=tk.Y)
    sort_var = tk.StringVar(value='ファイル名順')
    radio1 = tk.Radiobutton(radio_frame, text='ファイル名順', variable=sort_var, value='ファイル名順')
    radio2 = tk.Radiobutton(radio_frame, text='品質降順', variable=sort_var, value='品質降順')
    radio1.pack(anchor=tk.N)
    radio2.pack(anchor=tk.N)

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
        sorted_data = sort_data(mode)
        sorted_data = list(reversed(sorted_data))
        names = [x[0] for x in sorted_data]
        values = [x[1] for x in sorted_data]
        ax.clear()
        bars = ax.barh(names, values)
        ax.set_xlabel('品質（コントラスト）', loc='left')
        ax.set_ylabel('ファイル名')
        ax.set_title('画像品質 横棒グラフ')
        ax.xaxis.set_label_position('top')
        ax.xaxis.tick_top()
        ax.spines['right'].set_visible(False)  # 右端の縦線を非表示
        # 各横棒の右端に品質数値を描画
        for i, (bar, val) in enumerate(zip(bars, values)):
            ax.text(val + max(values)*0.01, bar.get_y() + bar.get_height()/2, f'{val:.1f}', va='center', ha='left', fontsize=10)
        plt.tight_layout()
        fig_canvas.draw()
        fig_widget.update_idletasks()
        canvas.config(scrollregion=canvas.bbox("all"))

    radio1.config(command=update_graph_tk)
    radio2.config(command=update_graph_tk)

    root.mainloop()

if __name__ == '__main__':
    main()
