import os
import csv
import struct
from dataclasses import dataclass
from typing import List, Tuple, Dict
from PIL import Image

# ayarlar
INPUT_IMAGE_PATH = "resim.jpeg"
OUTPUT_DIR = "rle_hw_output_best"
TARGET_SIZE = (512, 512)
ZIGZAG_BLOCK = 64

MAGIC = b"RLE3"

SCAN_MODE_IDS = {
    "row_row": 1,
    "col_col": 2,
    "zigzag_64x64": 3,
}
SCAN_MODE_NAMES = {v: k for k, v in SCAN_MODE_IDS.items()}

RLE_ALGORITHM_NAME = "Custom Packet-Based RLE on Packed Scan Stream"


# helper funcs
def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def row_stride(width: int, bpp: int) -> int:
    return ((width * bpp + 31) // 32) * 4


# TRUE indeksli BMP 
def write_indexed_bmp(
    out_path: str,
    pixel_matrix: List[List[int]],
    width: int,
    height: int,
    bpp: int,
    palette_rgba: List[Tuple[int, int, int, int]],
):
    if bpp not in (1, 4, 8):
        raise ValueError("Only 1, 4, 8 bpp indexed BMP supported.")

    stride = row_stride(width, bpp)
    pixel_data = bytearray()

    for y in range(height - 1, -1, -1):
        row = pixel_matrix[y]
        packed = bytearray()

        if bpp == 8:
            packed.extend(bytes(v & 0xFF for v in row))

        elif bpp == 4:
            for i in range(0, width, 2):
                p1 = row[i] & 0x0F
                p2 = row[i + 1] & 0x0F if i + 1 < width else 0
                packed.append((p1 << 4) | p2)

        elif bpp == 1:
            current = 0
            bit_count = 0
            for px in row:
                current = (current << 1) | (px & 1)
                bit_count += 1
                if bit_count == 8:
                    packed.append(current)
                    current = 0
                    bit_count = 0
            if bit_count != 0:
                current <<= (8 - bit_count)
                packed.append(current)

        while len(packed) < stride:
            packed.append(0)

        pixel_data.extend(packed)

    palette_bytes = bytearray()
    for r, g, b, a in palette_rgba:
        palette_bytes.extend([b, g, r, 0])

    pixel_offset = 14 + 40 + len(palette_bytes)
    file_size = pixel_offset + len(pixel_data)

    file_header = struct.pack("<2sIHHI", b"BM", file_size, 0, 0, pixel_offset)
    info_header = struct.pack(
        "<IIIHHIIIIII",
        40,
        width,
        height,
        1,
        bpp,
        0,
        len(pixel_data),
        2835,
        2835,
        len(palette_rgba),
        len(palette_rgba),
    )

    with open(out_path, "wb") as f:
        f.write(file_header)
        f.write(info_header)
        f.write(palette_bytes)
        f.write(pixel_data)


# img
def resize_image(path: str, target_size=(512, 512)) -> Image.Image:
    img = Image.open(path).convert("RGB")
    img = img.resize(target_size, Image.LANCZOS)
    return img


def build_bw_1bit_matrix(img: Image.Image) -> List[List[int]]:
    gray = img.convert("L")
    w, h = gray.size
    mat = []
    for y in range(h):
        row = []
        for x in range(w):
            p = gray.getpixel((x, y))
            row.append(1 if p >= 128 else 0)
        mat.append(row)
    return mat


def build_gray_4bit_matrix(img: Image.Image) -> List[List[int]]:
    gray = img.convert("L")
    w, h = gray.size
    mat = []
    for y in range(h):
        row = []
        for x in range(w):
            p = gray.getpixel((x, y))
            q = int(round(p * 15 / 255.0))
            row.append(q)
        mat.append(row)
    return mat


def build_color_8bit_matrix_and_palette(img: Image.Image):
    q = img.quantize(colors=256, method=Image.MEDIANCUT)
    w, h = q.size
    raw_palette = q.getpalette()[:256 * 3]

    palette_rgba = []
    for i in range(256):
        r = raw_palette[i * 3 + 0]
        g = raw_palette[i * 3 + 1]
        b = raw_palette[i * 3 + 2]
        palette_rgba.append((r, g, b, 0))

    mat = []
    for y in range(h):
        row = []
        for x in range(w):
            row.append(q.getpixel((x, y)))
        mat.append(row)

    return mat, palette_rgba


def save_bmp_variants(img_path: str, out_dir: str, target_size=(512, 512)) -> Dict[str, str]:
    ensure_dir(out_dir)
    img = resize_image(img_path, target_size=target_size)
    w, h = img.size

    paths = {}

    bw_mat = build_bw_1bit_matrix(img)
    bw_palette = [(0, 0, 0, 0), (255, 255, 255, 0)]
    bw_path = os.path.join(out_dir, "bw_1bit.bmp")
    write_indexed_bmp(bw_path, bw_mat, w, h, 1, bw_palette)
    paths["bw_1bit"] = bw_path

    gray4_mat = build_gray_4bit_matrix(img)
    gray4_palette = []
    for i in range(16):
        v = int(round(i * 255 / 15.0))
        gray4_palette.append((v, v, v, 0))
    gray4_path = os.path.join(out_dir, "gray_4bit.bmp")
    write_indexed_bmp(gray4_path, gray4_mat, w, h, 4, gray4_palette)
    paths["gray_4bit"] = gray4_path

    color8_mat, color8_palette = build_color_8bit_matrix_and_palette(img)
    color8_path = os.path.join(out_dir, "color_8bit.bmp")
    write_indexed_bmp(color8_path, color8_mat, w, h, 8, color8_palette)
    paths["color_8bit"] = color8_path

    return paths


# BMP read
@dataclass
class BMPInfo:
    width: int
    height: int
    bits_per_pixel: int
    pixel_offset: int
    header_bytes: bytes
    pixel_bytes: bytes
    palette_entries: int


def parse_bmp(path: str) -> BMPInfo:
    with open(path, "rb") as f:
        data = f.read()

    if data[:2] != b"BM":
        raise ValueError(f"{path} is not a BMP file.")

    pixel_offset = struct.unpack_from("<I", data, 10)[0]
    dib_size = struct.unpack_from("<I", data, 14)[0]
    if dib_size < 40:
        raise ValueError("Unsupported BMP DIB header.")

    width = struct.unpack_from("<I", data, 18)[0]
    height = struct.unpack_from("<I", data, 22)[0]
    bpp = struct.unpack_from("<H", data, 28)[0]
    compression = struct.unpack_from("<I", data, 30)[0]
    colors_used = struct.unpack_from("<I", data, 46)[0]

    if compression != 0:
        raise ValueError("Only uncompressed BI_RGB BMP supported.")
    if bpp not in (1, 4, 8):
        raise ValueError(f"Unsupported BMP bpp: {bpp}")

    if colors_used == 0:
        colors_used = 2 ** bpp

    return BMPInfo(
        width=width,
        height=height,
        bits_per_pixel=bpp,
        pixel_offset=pixel_offset,
        header_bytes=data[:pixel_offset],
        pixel_bytes=data[pixel_offset:],
        palette_entries=colors_used,
    )


def unpack_bmp_pixels_to_matrix(info: BMPInfo) -> List[List[int]]:
    width = info.width
    height = info.height
    bpp = info.bits_per_pixel
    stride = row_stride(width, bpp)
    rows_bottom_up = []

    for row_idx in range(height):
        start = row_idx * stride
        row_data = info.pixel_bytes[start:start + stride]
        pixels = []

        if bpp == 8:
            pixels = list(row_data[:width])

        elif bpp == 4:
            needed = (width + 1) // 2
            for b in row_data[:needed]:
                hi = (b >> 4) & 0x0F
                lo = b & 0x0F
                pixels.append(hi)
                if len(pixels) < width:
                    pixels.append(lo)

        elif bpp == 1:
            needed = (width + 7) // 8
            for b in row_data[:needed]:
                for bit in range(7, -1, -1):
                    pixels.append((b >> bit) & 1)
                    if len(pixels) == width:
                        break
                if len(pixels) == width:
                    break

        rows_bottom_up.append(pixels)

    return list(reversed(rows_bottom_up))

# scan orderları
def generate_row_major_coords(width: int, height: int) -> List[Tuple[int, int]]:
    return [(y, x) for y in range(height) for x in range(width)]


def generate_col_major_coords(width: int, height: int) -> List[Tuple[int, int]]:
    return [(y, x) for x in range(width) for y in range(height)]


def zigzag_coords_for_block(block_w: int, block_h: int) -> List[Tuple[int, int]]:
    coords = []
    for s in range(block_w + block_h - 1):
        diag = []
        y_start = max(0, s - (block_w - 1))
        y_end = min(block_h - 1, s)
        for y in range(y_start, y_end + 1):
            x = s - y
            if 0 <= x < block_w:
                diag.append((y, x))
        if s % 2 == 0:
            diag.reverse()
        coords.extend(diag)
    return coords


def generate_zigzag_block_coords(width: int, height: int, block_size: int = 64) -> List[Tuple[int, int]]:
    coords = []
    for by in range(0, height, block_size):
        for bx in range(0, width, block_size):
            bh = min(block_size, height - by)
            bw = min(block_size, width - bx)
            block_coords = zigzag_coords_for_block(bw, bh)
            for yy, xx in block_coords:
                coords.append((by + yy, bx + xx))
    return coords


def get_scan_coords(mode: str, width: int, height: int, block_size: int = 64) -> List[Tuple[int, int]]:
    if mode == "row_row":
        return generate_row_major_coords(width, height)
    elif mode == "col_col":
        return generate_col_major_coords(width, height)
    elif mode == "zigzag_64x64":
        return generate_zigzag_block_coords(width, height, block_size)
    else:
        raise ValueError(f"Unknown scan mode: {mode}")


def flatten_matrix_by_coords(matrix: List[List[int]], coords: List[Tuple[int, int]]) -> List[int]:
    return [matrix[y][x] for y, x in coords]


# pack scan stream
def pack_symbol_stream(data: List[int], bpp: int) -> bytes:
    packed = bytearray()

    if bpp == 8:
        packed.extend(bytes(v & 0xFF for v in data))

    elif bpp == 4:
        for i in range(0, len(data), 2):
            a = data[i] & 0x0F
            b = data[i + 1] & 0x0F if i + 1 < len(data) else 0
            packed.append((a << 4) | b)

    elif bpp == 1:
        current = 0
        bit_count = 0
        for v in data:
            current = (current << 1) | (v & 1)
            bit_count += 1
            if bit_count == 8:
                packed.append(current)
                current = 0
                bit_count = 0
        if bit_count != 0:
            current <<= (8 - bit_count)
            packed.append(current)

    else:
        raise ValueError("Unsupported bpp in pack_symbol_stream.")

    return bytes(packed)


def unpack_symbol_stream(packed: bytes, symbol_count: int, bpp: int) -> List[int]:
    out = []

    if bpp == 8:
        out = list(packed[:symbol_count])

    elif bpp == 4:
        for byte in packed:
            out.append((byte >> 4) & 0x0F)
            if len(out) == symbol_count:
                break
            out.append(byte & 0x0F)
            if len(out) == symbol_count:
                break

    elif bpp == 1:
        for byte in packed:
            for bit in range(7, -1, -1):
                out.append((byte >> bit) & 1)
                if len(out) == symbol_count:
                    break
            if len(out) == symbol_count:
                break

    else:
        raise ValueError("Unsupported bpp in unpack_symbol_stream.")

    return out


def rebuild_matrix_from_scan_stream(symbols: List[int], width: int, height: int, coords: List[Tuple[int, int]]) -> List[List[int]]:
    matrix = [[0 for _ in range(width)] for _ in range(height)]
    for v, (y, x) in zip(symbols, coords):
        matrix[y][x] = v
    return matrix


def pack_matrix_to_bmp_pixel_bytes(matrix: List[List[int]], width: int, height: int, bpp: int) -> bytes:
    stride = row_stride(width, bpp)
    out = bytearray()

    for y in range(height - 1, -1, -1):
        row = matrix[y]
        packed = bytearray(pack_symbol_stream(row, bpp))
        while len(packed) < stride:
            packed.append(0)
        out.extend(packed)

    return bytes(out)


# RLE
def rle_encode_custom(data: bytes) -> bytes:
    out = bytearray()
    i = 0
    n = len(data)

    while i < n:
        run_len = 1
        while i + run_len < n and data[i + run_len] == data[i] and run_len < 128:
            run_len += 1

        if run_len >= 2:
            out.append(0x80 | (run_len - 1))
            out.append(data[i])
            i += run_len
        else:
            lit_start = i
            lit_len = 1
            i += 1

            while i < n and lit_len < 128:
                test_run = 1
                while i + test_run < n and data[i + test_run] == data[i] and test_run < 128:
                    test_run += 1
                if test_run >= 2:
                    break
                lit_len += 1
                i += 1

            out.append(lit_len - 1)
            out.extend(data[lit_start:lit_start + lit_len])

    return bytes(out)


def rle_decode_custom(encoded: bytes, expected_length: int) -> bytes:
    out = bytearray()
    i = 0
    n = len(encoded)

    while i < n and len(out) < expected_length:
        control = encoded[i]
        i += 1

        is_run = (control & 0x80) != 0
        length = (control & 0x7F) + 1

        if is_run:
            if i >= n:
                raise ValueError("Corrupt RLE stream.")
            value = encoded[i]
            i += 1
            out.extend([value] * length)
        else:
            if i + length > n:
                raise ValueError("Corrupt RLE literal stream.")
            out.extend(encoded[i:i + length])
            i += length

    if len(out) != expected_length:
        raise ValueError(f"Decoded byte count mismatch. Expected={expected_length}, got={len(out)}")

    return bytes(out)

# ENCODE / DECODE
def encode_bmp_with_scan(bmp_path: str, out_encoded_path: str, scan_mode: str, block_size: int = 64):
    info = parse_bmp(bmp_path)
    matrix = unpack_bmp_pixels_to_matrix(info)
    coords = get_scan_coords(scan_mode, info.width, info.height, block_size)

    symbol_stream = flatten_matrix_by_coords(matrix, coords)
    packed_scan_stream = pack_symbol_stream(symbol_stream, info.bits_per_pixel)
    payload = rle_encode_custom(packed_scan_stream)

    meta = (
        MAGIC
        + bytes([SCAN_MODE_IDS[scan_mode]])
        + struct.pack("<H", block_size)
        + struct.pack("<I", info.width)
        + struct.pack("<I", info.height)
        + bytes([info.bits_per_pixel])
        + struct.pack("<I", len(symbol_stream))
        + struct.pack("<I", len(packed_scan_stream))
    )

    encoded_bytes = info.header_bytes + meta + payload

    with open(out_encoded_path, "wb") as f:
        f.write(encoded_bytes)

    return {
        "width": info.width,
        "height": info.height,
        "bpp": info.bits_per_pixel,
        "header_size": len(info.header_bytes),
        "raw_pixel_bytes_size": len(info.pixel_bytes),
        "scan_symbol_count": len(symbol_stream),
        "packed_scan_bytes_size": len(packed_scan_stream),
        "payload_size": len(payload),
        "meta_size": len(meta),
        "total_encoded_size": len(encoded_bytes),
    }


def decode_encoded_file_to_bmp(encoded_path: str, out_bmp_path: str):
    with open(encoded_path, "rb") as f:
        data = f.read()

    if data[:2] != b"BM":
        raise ValueError("Encoded file does not start with BMP header.")

    pixel_offset = struct.unpack_from("<I", data, 10)[0]
    header = data[:pixel_offset]

    pos = pixel_offset
    if data[pos:pos + 4] != MAGIC:
        raise ValueError("RLE magic not found.")
    pos += 4

    mode_id = data[pos]
    pos += 1

    block_size = struct.unpack_from("<H", data, pos)[0]
    pos += 2

    width = struct.unpack_from("<I", data, pos)[0]
    pos += 4

    height = struct.unpack_from("<I", data, pos)[0]
    pos += 4

    bpp = data[pos]
    pos += 1

    symbol_count = struct.unpack_from("<I", data, pos)[0]
    pos += 4

    packed_length = struct.unpack_from("<I", data, pos)[0]
    pos += 4

    scan_mode = SCAN_MODE_NAMES.get(mode_id)
    if scan_mode is None:
        raise ValueError("Invalid scan mode.")

    payload = data[pos:]
    packed_scan_stream = rle_decode_custom(payload, packed_length)
    symbols = unpack_symbol_stream(packed_scan_stream, symbol_count, bpp)

    coords = get_scan_coords(scan_mode, width, height, block_size)
    matrix = rebuild_matrix_from_scan_stream(symbols, width, height, coords)
    pixel_bytes = pack_matrix_to_bmp_pixel_bytes(matrix, width, height, bpp)

    with open(out_bmp_path, "wb") as f:
        f.write(header + pixel_bytes)


# metrics
def read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def verify_lossless(original_bmp: str, decoded_bmp: str) -> bool:
    return read_bytes(original_bmp) == read_bytes(decoded_bmp)


def compression_ratio(original_size: int, encoded_size: int) -> float:
    return original_size / encoded_size if encoded_size else 0.0


def space_saving_percent(original_size: int, encoded_size: int) -> float:
    return ((original_size - encoded_size) / original_size) * 100.0 if original_size else 0.0


def overhead_percent(base_size: int, new_size: int) -> float:
    return ((new_size - base_size) / base_size) * 100.0 if base_size else 0.0


# main
def run_pipeline():
    ensure_dir(OUTPUT_DIR)

    bmp_dir = os.path.join(OUTPUT_DIR, "bmp_variants")
    encoded_dir = os.path.join(OUTPUT_DIR, "encoded")
    decoded_dir = os.path.join(OUTPUT_DIR, "decoded")

    ensure_dir(bmp_dir)
    ensure_dir(encoded_dir)
    ensure_dir(decoded_dir)

    print("1) BMP variants are being generated...")
    bmp_paths = save_bmp_variants(INPUT_IMAGE_PATH, bmp_dir, target_size=TARGET_SIZE)

    results = []
    scan_modes = ["row_row", "col_col", "zigzag_64x64"]

    print("2) Encode / Decode process started...")

    for bmp_type, bmp_path in bmp_paths.items():
        info = parse_bmp(bmp_path)
        original_size = os.path.getsize(bmp_path)

        for scan_mode in scan_modes:
            base_name = f"{bmp_type}_{scan_mode}"

            encoded_path = os.path.join(encoded_dir, base_name + ".rle")
            decoded_bmp_path = os.path.join(decoded_dir, base_name + "_decoded.bmp")

            enc_stats = encode_bmp_with_scan(
                bmp_path=bmp_path,
                out_encoded_path=encoded_path,
                scan_mode=scan_mode,
                block_size=ZIGZAG_BLOCK
            )

            decode_encoded_file_to_bmp(encoded_path, decoded_bmp_path)
            encoded_size = os.path.getsize(encoded_path)
            lossless = verify_lossless(bmp_path, decoded_bmp_path)

            results.append({
                "bmp_type": bmp_type,
                "read_mode": scan_mode,
                "rle_algorithm": RLE_ALGORITHM_NAME,
                "width": info.width,
                "height": info.height,
                "bit_depth": info.bits_per_pixel,
                "palette_entries": info.palette_entries,
                "original_bmp_size_bytes": original_size,
                "header_size_bytes": enc_stats["header_size"],
                "raw_pixel_bytes_size": enc_stats["raw_pixel_bytes_size"],
                "scan_symbol_count": enc_stats["scan_symbol_count"],
                "packed_scan_bytes_size": enc_stats["packed_scan_bytes_size"],
                "rle_meta_size": enc_stats["meta_size"],
                "rle_payload_size": enc_stats["payload_size"],
                "encoded_total_size_bytes": encoded_size,
                "compression_ratio": round(compression_ratio(original_size, encoded_size), 4),
                "space_saving_percent": round(space_saving_percent(original_size, encoded_size), 2),
                "payload_overhead_percent_vs_packed_scan": round(
                    overhead_percent(enc_stats["packed_scan_bytes_size"], enc_stats["payload_size"]), 2
                ),
                "lossless": "TRUE" if lossless else "FALSE",
                "original_bmp_path": bmp_path,
                "encoded_file_path": encoded_path,
                "decoded_bmp_path": decoded_bmp_path,
            })

            print(f"   Completed -> {base_name} | lossless={lossless}")

    csv_path = os.path.join(OUTPUT_DIR, "results_detailed.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)

    print("\n3) RESULTS SUMMARY")
    print("-" * 160)
    print(
        f"{'BMP Type':<15} {'Mode':<16} {'BPP':<5} {'Orig Size':<12} "
        f"{'Packed Scan':<12} {'Payload':<12} {'Enc Size':<12} {'Ratio':<10} {'Saving %':<10} {'Lossless':<10}"
    )
    print("-" * 160)

    for r in results:
        print(
            f"{r['bmp_type']:<15} "
            f"{r['read_mode']:<16} "
            f"{r['bit_depth']:<5} "
            f"{r['original_bmp_size_bytes']:<12} "
            f"{r['packed_scan_bytes_size']:<12} "
            f"{r['rle_payload_size']:<12} "
            f"{r['encoded_total_size_bytes']:<12} "
            f"{r['compression_ratio']:<10} "
            f"{r['space_saving_percent']:<10} "
            f"{r['lossless']:<10}"
        )

    print("-" * 160)
    print(f"\nDetailed CSV saved: {csv_path}")
    print(f"All outputs folder: {os.path.abspath(OUTPUT_DIR)}")


if __name__ == "__main__":
    run_pipeline()