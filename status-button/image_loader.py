import struct
import mem
import state

image_data  = None
active      = False
current_url = None

_TMP_PATH   = '/tmp_img.bin'
_ROWS       = 8
_ROW_BYTES  = 240 * 2
_FRAME_SIZE = 240 * 240 * 2


def _rgb565(r, g, b):
    c = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    return ((c & 0xFF) << 8) | ((c >> 8) & 0xFF)


def display():
    """Re-display from the temp file if active."""
    global active
    if not active:
        return
    try:
        _stream_file_to_display(_TMP_PATH)
    except Exception as e:
        print(f"image_loader.display: {e}")


def clear():
    global image_data, active, current_url
    image_data  = None
    active      = False
    current_url = None
    mem.collect()


def _stream_file_to_display(path):
    """Stream an RGB565 .bin file to the display in small row chunks."""
    import os
    buf = bytearray(_ROWS * _ROW_BYTES)
    mv  = memoryview(buf)
    with open(path, 'rb') as f:
        y = 0
        while y < 240:
            rows  = min(_ROWS, 240 - y)
            n     = f.readinto(mv[:rows * _ROW_BYTES])
            if not n:
                break
            actual = n // _ROW_BYTES
            state.tft.blit_buffer(mv[:actual * _ROW_BYTES], 0, y, 240, actual)
            y += actual
    buf = None
    mv  = None
    mem.collect()


def _download_to_file(url, dest_path):
    """Download a URL and save raw bytes to dest_path. Returns (content_length, first_bytes)."""
    import urequests
    import os

    try:
        os.remove(dest_path)
    except OSError:
        pass

    mem.collect()
    mem.report('download start')

    resp = urequests.get(url)
    if resp.status_code != 200:
        resp.close()
        raise Exception(f"HTTP {resp.status_code}")

    total = 0
    first = None
    with open(dest_path, 'wb') as f:
        while True:
            chunk = resp.raw.read(4096)
            if not chunk:
                break
            if first is None:
                first = bytes(chunk[:4])
            f.write(chunk)
            total += len(chunk)
            chunk = None

    resp.close()
    mem.collect()
    mem.report(f'download done ({total}b)')
    return total, first


def _decode_bmp_to_bin(src_path, dst_path):
    """
    Read a BMP from src_path, convert to raw RGB565, write to dst_path.
    Processes one row at a time to keep RAM usage low.
    """
    with open(src_path, 'rb') as f:
        header = f.read(54)

    if header[0:2] != b'BM':
        raise Exception("Not a BMP")

    pixel_offset = struct.unpack_from('<I', header, 10)[0]
    img_w        = struct.unpack_from('<i', header, 18)[0]
    img_h        = struct.unpack_from('<i', header, 22)[0]
    bit_count    = struct.unpack_from('<H', header, 28)[0]
    compression  = struct.unpack_from('<I', header, 30)[0]

    if compression != 0:
        raise Exception("Compressed BMP not supported")
    if bit_count not in (24, 32):
        raise Exception(f"Only 24/32-bit BMP, got {bit_count}")

    flipped  = img_h > 0
    abs_h    = abs(img_h)
    bytes_pp = bit_count // 8
    row_size = ((img_w * bytes_pp + 3) // 4) * 4
    sx       = img_w  / 240
    sy       = abs_h  / 240

    out_row  = bytearray(240 * 2)

    with open(src_path, 'rb') as src, open(dst_path, 'wb') as dst:
        for fy in range(240):
            src_y = min(int(fy * sy), abs_h - 1)
            bmp_y = (abs_h - 1 - src_y) if flipped else src_y
            row_off = pixel_offset + bmp_y * row_size

            src.seek(row_off)
            row_data = src.read(row_size)

            for fx in range(240):
                src_x = min(int(fx * sx), img_w - 1)
                off   = src_x * bytes_pp
                b_val = row_data[off]
                g_val = row_data[off + 1]
                r_val = row_data[off + 2]
                c     = _rgb565(r_val, g_val, b_val)
                i     = fx * 2
                out_row[i]     = c & 0xFF
                out_row[i + 1] = (c >> 8) & 0xFF

            dst.write(out_row)

    out_row = None
    mem.collect()


def load_from_url(url):
    global active, current_url
    import os

    clear()
    url_lower = url.lower().split('?')[0]
    tmp_raw   = '/tmp_raw_dl'

    # Download raw file
    total, first_bytes = _download_to_file(url, tmp_raw)
    print(f"Downloaded {total} bytes from {url}")

    try:
        if url_lower.endswith('.bin') and total == _FRAME_SIZE:
            # Already raw RGB565 — just rename
            try:
                os.remove(_TMP_PATH)
            except OSError:
                pass
            os.rename(tmp_raw, _TMP_PATH)

        elif url_lower.endswith('.bmp') or (first_bytes and first_bytes[:2] == b'BM'):
            # BMP — convert to RGB565 bin
            print("Converting BMP...")
            _decode_bmp_to_bin(tmp_raw, _TMP_PATH)
            try:
                os.remove(tmp_raw)
            except OSError:
                pass

        else:
            try:
                os.remove(tmp_raw)
            except OSError:
                pass
            raise Exception("Unsupported format — use .bmp or .bin (240x240 RGB565)")

        mem.collect()

        # Stream from flash to display
        _stream_file_to_display(_TMP_PATH)
        active      = True
        current_url = url
        mem.report('img load done')
        return True

    except Exception as e:
        try:
            os.remove(tmp_raw)
        except OSError:
            pass
        raise e