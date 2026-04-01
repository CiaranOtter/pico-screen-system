import struct
import gc
import mem
import state

active       = False
_filepath    = None
_frame_count = 0
_delay_ms    = 100

FRAME_BYTES  = 240 * 240 * 2
HEADER_SIZE  = 8
FRAME_HDR    = 4

_TMP_GIF_PATH = '/tmp_dl.gif565'


def load_from_file(path):
    global active, _filepath, _frame_count, _delay_ms

    clear()
    mem.report('gif load start')

    with open(path, 'rb') as f:
        header = f.read(HEADER_SIZE)

    if header[:2] != b'G5':
        raise Exception("Not a .gif565 file — convert with gif_converter.py")

    _frame_count = struct.unpack_from('<H', header, 2)[0]

    with open(path, 'rb') as f:
        f.seek(HEADER_SIZE)
        fhdr = f.read(FRAME_HDR)
    _delay_ms = struct.unpack_from('<H', fhdr, 0)[0]

    _filepath = path
    active    = True
    mem.report('gif load done')
    print(f"GIF: {_frame_count} frames, {_delay_ms}ms, file={path}")
    return _frame_count, _delay_ms


def load_from_url(url, dest_path=None):
    """
    Download a .gif565 file from a URL, save to flash, then load it.
    The file must already be in .gif565 format (converted on your Mac
    with gif_converter.py). Raw .gif files are not supported on the Pico
    as GIF decoding is too memory-intensive.

    dest_path: where to save on the Pico (default: /tmp_dl.gif565)
    """
    global active, _filepath, _frame_count, _delay_ms
    import urequests, os

    clear()
    save_path = dest_path or _TMP_GIF_PATH

    # Remove old file
    try:
        os.remove(save_path)
    except OSError:
        pass

    mem.collect()
    mem.report('gif url download start')
    print(f"Downloading GIF565 from {url}")

    # Stream download directly to flash
    resp = urequests.get(url)
    if resp.status_code != 200:
        resp.close()
        raise Exception(f"HTTP {resp.status_code}")

    total = 0
    first = None
    with open(save_path, 'wb') as f:
        while True:
            chunk = resp.raw.read(4096)
            if not chunk:
                break
            if first is None:
                first = bytes(chunk[:2])
            f.write(chunk)
            total += len(chunk)
            chunk  = None

    resp.close()
    mem.collect()
    print(f"Downloaded {total} bytes")

    if first != b'G5':
        try:
            os.remove(save_path)
        except OSError:
            pass
        raise Exception(
            "Not a .gif565 file. Convert on your Mac first:\n"
            "  python3 gif_converter.py animation.gif output.gif565\n"
            "Then serve output.gif565 from a URL."
        )

    # Load from the saved file
    return load_from_file(save_path)


def read_frame(index):
    """Read one frame from flash in row chunks to save RAM."""
    if not active or not _filepath:
        return None

    ROWS      = 8
    row_bytes = 240 * 2
    buf       = bytearray(ROWS * row_bytes)
    mv        = memoryview(buf)
    frame_off = HEADER_SIZE + index * (FRAME_HDR + FRAME_BYTES) + FRAME_HDR

    with open(_filepath, 'rb') as f:
        f.seek(frame_off)
        y = 0
        while y < 240:
            rows = min(ROWS, 240 - y)
            n    = f.readinto(mv[:rows * row_bytes])
            if not n:
                break
            state.tft.blit_buffer(mv[:n], 0, y, 240, n // row_bytes)
            y += rows

    buf = None
    mv  = None
    mem.collect()
    return True  # signals success without holding frame in RAM


def get_delay(index):
    if not active or not _filepath:
        return _delay_ms
    offset = HEADER_SIZE + index * (FRAME_HDR + FRAME_BYTES)
    with open(_filepath, 'rb') as f:
        f.seek(offset)
        hdr = f.read(FRAME_HDR)
    return struct.unpack_from('<H', hdr, 0)[0]


def clear():
    global active, _filepath, _frame_count, _delay_ms
    active       = False
    _filepath    = None
    _frame_count = 0
    _delay_ms    = 100
    mem.collect()