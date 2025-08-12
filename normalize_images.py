import os
import argparse
from PIL import Image
import numpy as np

def match_histogram(source, reference):
    matched = np.zeros_like(source)
    for channel in range(source.shape[2]):
        src_hist, bins = np.histogram(source[:, :, channel].flatten(), 65536, [0, 65536])
        ref_hist, _ = np.histogram(reference[:, :, channel].flatten(), 65536, [0, 65536])

        src_cdf = np.cumsum(src_hist).astype(np.float64)
        src_cdf /= src_cdf[-1]
        ref_cdf = np.cumsum(ref_hist).astype(np.float64)
        ref_cdf /= ref_cdf[-1]

        mapping = np.interp(src_cdf, ref_cdf, bins[:-1])
        matched[:, :, channel] = np.interp(source[:, :, channel].flatten(), bins[:-1], mapping).reshape(source[:, :, channel].shape)

    return matched.astype(np.uint16)

def process_images(ref_path, input_dir, output_dir):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    ref_image = Image.open(ref_path)
    ref_array = np.array(ref_image)

    for filename in os.listdir(input_dir):
        if filename.lower().endswith('.png'):
            input_path = os.path.join(input_dir, filename)
            image = Image.open(input_path)
            image_array = np.array(image)

            # 画像が2次元（モノクロ）の場合、チャンネル次元を追加
            if image_array.ndim == 2:
                image_array = image_array[:, :, np.newaxis]
            if ref_array.ndim == 2:
                ref_array = ref_array[:, :, np.newaxis]

            matched_array = match_histogram(image_array, ref_array)

            # チャンネルが1つならモノクロ画像として保存
            if matched_array.shape[2] == 1:
                matched_array = matched_array[:, :, 0]
                matched_image = Image.fromarray(matched_array, mode='I;16')
            else:
                matched_image = Image.fromarray(matched_array, mode='I;16')

            matched_image.save(os.path.join(output_dir, filename))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Normalize contrast and brightness of 16-bit PNG images using a reference image.")
    parser.add_argument('--ref', required=True, help='Path to the reference image')
    parser.add_argument('--input_dir', required=True, help='Path to the input directory containing PNG images')
    parser.add_argument('--output_dir', required=True, help='Path to the output directory to save processed images')

    args = parser.parse_args()
    process_images(args.ref, args.input_dir, args.output_dir)
