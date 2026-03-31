import struct
import mem
import state

image_data  = None
active      = False
current_url = None


def _rgb565(r, g, b):
    c = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    return ((c & 0xFF) << 8) | ((c >> 8) & 0xFF)


def display():
    global image_data, active
    if active and image_data is not None:
        state.tft.blit_buffer(image_data, 0, 0, 240, 240)


def clear():
    global image_data, active, current_url
    image_data  = None
    active      = False
    current_url = None
    mem.collect()


def _decode_bmp(data):
    if data[0:2] != b'BM':
        raise Exception("Not a BMP")
    pixel_offset = struct.unpack_from('<I', data, 10)[0]
    img_w        = struct.unpack_from('<i', data, 18)[0]
    img_h        = struct.unpack_from('<i', data, 22)[0]
    bit_count    = struct.unpack_from('<H', data, 28)[0]
    compression  = struct.unpack_from('<I', data, 30)[0]
    if compression != 0:
        raise Exception("Compressed BMP not supported")
    if bit_count not in (24, 32):
        raise Exception(f"Only 24/32-bit BMP, got {bit_count}")
    flipped  = img_h > 0
    abs_h    = abs(img_h)
    bytes_pp = bit_count // 8
    row_size = ((img_w * bytes_pp + 3) // 4) * 4
    mem.check(240 * 240 * 2, 'BMP decode')
    frame = bytearray(240 * 240 * 2)
    sx    = img_w  / 240
    sy    = abs_h / 240
    for fy in range(240):
        src_y = min(int(fy * sy), abs_h - 1)
        bmp_y = (abs_h - 1 - src_y) if flipped else src_y
        for fx in range(240):
            src_x = min(int(fx * sx), img_w - 1)
            off   = pixel_offset + bmp_y * row_size + src_x * bytes_pp
            b, g, r = data[off], data[off+1], data[off+2]
            c     = _rgb565(r, g, b)
            i     = (fy * 240 + fx) * 2
            frame[i]     = c & 0xFF
            frame[i + 1] = (c >> 8) & 0xFF
    return frame


def _decode_bin(data):
    if len(data) != 240 * 240 * 2:
        raise Exception(f"Expected {240*240*2} bytes, got {len(data)}")
    return bytearray(data)


def load_from_url(url):
    global image_data, active, current_url
    import urequests
    clear()
    mem.report('img load start')
    resp = urequests.get(url)
    if resp.status_code != 200:
        raise Exception(f"HTTP {resp.status_code}")
    data = resp.content
    resp.close()
    resp = None
    mem.collect()
    print(f"Image: {len(data)} bytes")
    url_lower = url.lower().split('?')[0]
    if url_lower.endswith('.bmp') or data[0:2] == b'BM':
        image_data = _decode_bmp(data)
    elif url_lower.endswith('.bin') and len(data) == 240 * 240 * 2:
        image_data = _decode_bin(data)
    else:
        raise Exception("Unsupported format — use .bmp or .bin")
    data = None
    mem.collect()
    active      = True
    current_url = url
    mem.report('img load done')
    return True
