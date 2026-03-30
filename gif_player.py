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


def load_from_file(path):
    global active, _filepath, _frame_count, _delay_ms

    # Clear everything first
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


def read_frame(index):
    """Read one frame from flash. Caller must set to None after blitting."""
    if not active or not _filepath:
        return None
    offset = HEADER_SIZE + index * (FRAME_HDR + FRAME_BYTES) + FRAME_HDR
    with open(_filepath, 'rb') as f:
        f.seek(offset)
        return f.read(FRAME_BYTES)


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
