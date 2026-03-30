from machine import Pin, SPI
import gc9a01py.lib.gc9a01py as gc9a01
import framebuf
import math
import mem
import gc9a01py.fonts.romfonts.vga2_8x16  as font_med
import gc9a01py.fonts.romfonts.vga2_16x32 as font_big

def swap16(c):
    """Swap bytes for framebuf RGB565 compatibility."""
    return ((c & 0xFF) << 8) | ((c >> 8) & 0xFF)

def rgb(r, g, b):
    """Convert 8-bit RGB to swapped RGB565 for framebuf."""
    return swap16(((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3))

# Colours — defined using rgb() so byte order is always correct
BLACK   = rgb(0,   0,   0)
WHITE   = rgb(255, 255, 255)
RED     = rgb(255, 0,   0)
GREEN   = rgb(0,   255, 0)
BLUE    = rgb(0,   0,   255)
MAGENTA = rgb(255, 0,   255)
YELLOW  = rgb(255, 255, 0)
CYAN    = rgb(0,   255, 255)

COLOUR_RGB = {
    'red':    (255, 0,   0),
    'green':  (0,   255, 0),
    'purple': (255, 0,   255),
}

STATE_COLOURS = {
    'red':    RED,
    'purple': MAGENTA,
    'green':  GREEN,
}

STATES = ('red', 'purple', 'green')
MODES  = ('solid', 'ring', 'flash')

current = {
    'state':              'green',
    'mode':               'solid',
    'show_middle_finger': False,
    'message':            None,
    'gif_url':            None,
}

btn_sequence = []   # list of screen descriptors from frontend
btn_index    = 0    # current position in sequence
finger_no_text  = False   # when True, skip the text flash

transition = {
    'active':   False,
    'from_rgb': (0, 255, 0),
    'to_rgb':   (0, 255, 0),
    'progress': 1.0,
    'speed':    0.05,
}

# ── Hardware ──
spi = SPI(0, baudrate=62500000, sck=Pin(18), mosi=Pin(19))
tft = gc9a01.GC9A01(
    spi,
    dc=Pin(21, Pin.OUT),
    cs=Pin(17, Pin.OUT),
    reset=Pin(15, Pin.OUT),
    backlight=Pin(14, Pin.OUT),
    rotation=0
)

# ── Framebuffer — allocated once, never freed ──
mem.report('before fb alloc')
mem.check(240 * 240 * 2, 'framebuffer')
buf = bytearray(240 * 240 * 2)
fb  = framebuf.FrameBuffer(buf, 240, 240, framebuf.RGB565)
mem.report('after fb alloc')

_ring_drawn   = False
_static_drawn = False
_rendered_snapshot = None
_msg_text          = None
_msg_colour        = None
_msg_mode          = None


# ════════════════════════════════════
# HELPERS
# ════════════════════════════════════
def _blend_colour(c1, c2, t):
    """
    Blend two RGB565 (swapped) colours by t (0.0=c1, 1.0=c2).
    Uses ease-in-out for smoothness.
    """
    t = _ease(t)
    # Unpack c1
    c1s = swap16(c1)
    r1  = (c1s >> 11) & 0x1F
    g1  = (c1s >> 5)  & 0x3F
    b1  =  c1s        & 0x1F

    # Unpack c2
    c2s = swap16(c2)
    r2  = (c2s >> 11) & 0x1F
    g2  = (c2s >> 5)  & 0x3F
    b2  =  c2s        & 0x1F

    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)

    return swap16((r << 11) | (g << 5) | b)

def _push():
    tft.blit_buffer(buf, 0, 0, 240, 240)


def _fill_circle_fb(x0, y0, r, colour):
    for y in range(-r, r + 1):
        x = int((r * r - y * y) ** 0.5)
        fb.fill_rect(x0 - x, y0 + y, x * 2, 1, colour)


def _draw_text_centered(text, y, font, char_w, fg=WHITE, bg=BLACK):
    x = max(0, (240 - len(text) * char_w) // 2)
    tft.text(font, text, x, y, fg, bg)


def _lerp(a, b, t):
    return int(a + (b - a) * t)


def _ease(t):
    return t * t * (3 - 2 * t)


def _rgb565(r, g, b):
    return swap16(((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3))


def _lerp_colour(from_rgb, to_rgb, t):
    t = _ease(t)
    return _rgb565(
        _lerp(from_rgb[0], to_rgb[0], t),
        _lerp(from_rgb[1], to_rgb[1], t),
        _lerp(from_rgb[2], to_rgb[2], t),
    )


def _snap():
    """Take a snapshot of the current framebuffer state."""
    global _rendered_snapshot
    try:
        _rendered_snapshot = bytearray(buf)
    except MemoryError:
        _rendered_snapshot = None


def _push_blended_snapshot(t):
    """
    Blend _rendered_snapshot with BLACK by t and push.
    t=0 → black, t=1 → full snapshot.
    Operates directly on buf so only one blit needed.
    """
    if _rendered_snapshot is None:
        return
    ease_t = _ease(t)
    # Process in chunks to avoid large temp allocations
    STEP = 480  # 240 pixels worth of RGB565 pairs per iteration
    for start in range(0, len(buf), STEP):
        end = min(start + STEP, len(buf))
        for i in range(start, end, 2):
            # Read pixel from snapshot (big-endian RGB565 swapped)
            hi = _rendered_snapshot[i]
            lo = _rendered_snapshot[i + 1]
            c  = (hi << 8) | lo
            # Unswap, scale, reswap
            cs   = swap16(c)
            r    = int(((cs >> 11) & 0x1F) * ease_t)
            g    = int(((cs >>  5) & 0x3F) * ease_t)
            b    = int(( cs        & 0x1F) * ease_t)
            out  = swap16((r << 11) | (g << 5) | b)
            buf[i]     = (out >> 8) & 0xFF
            buf[i + 1] =  out       & 0xFF
    _push()
    
# ════════════════════════════════════
# LOADING / STATUS
# ════════════════════════════════════
def _draw_loading_frame(step, message="Connecting..."):
    fb.fill(BLACK)
    _fill_circle_fb(120, 120, 118, WHITE)
    _fill_circle_fb(120, 120, 108, BLACK)
    for i in range(8):
        angle = (i / 8) * 2 * math.pi + (step * 0.15)
        x     = int(120 + 80 * math.cos(angle))
        y     = int(120 + 80 * math.sin(angle))
        bri   = int(255 * (i / 8))
        grey  = swap16(((bri >> 3) << 11) | ((bri >> 2) << 5) | (bri >> 3))
        fb.fill_rect(x - 4, y - 4, 8, 8, grey)
    _push()
    _draw_text_centered(message, 108, font_med, 8, WHITE, BLACK)


def _draw_status_screen(success):
    fb.fill(BLACK)
    if success:
        _fill_circle_fb(120, 120, 118, GREEN)
        _fill_circle_fb(120, 120, 88,  BLACK)
        fb.fill_rect(88,  118, 8,  28, GREEN)
        fb.fill_rect(88,  138, 38,  8, GREEN)
        fb.fill_rect(110, 108, 8,  38, GREEN)
        fb.fill_rect(118, 100, 8,  16, GREEN)
        fb.fill_rect(126,  94, 8,  14, GREEN)
        _push()
        _draw_text_centered("CONNECTED", 158, font_med, 8, GREEN, BLACK)
        _draw_text_centered("READY",     178, font_med, 8, WHITE, BLACK)
    else:
        _fill_circle_fb(120, 120, 118, RED)
        _fill_circle_fb(120, 120, 88,  BLACK)
        for i in range(-20, 20):
            fb.fill_rect(120 + i - 2, 120 + i - 2, 5, 5, RED)
            fb.fill_rect(120 - i - 2, 120 + i - 2, 5, 5, RED)
        _push()
        _draw_text_centered("NO WIFI",   158, font_med, 8, RED,   BLACK)
        _draw_text_centered("REBOOTING", 178, font_med, 8, WHITE, BLACK)


# ════════════════════════════════════
# RING + MESSAGE
# ════════════════════════════════════
def _draw_ring(colour):
    fb.fill(BLACK)
    _fill_circle_fb(120, 120, 118, colour)
    _fill_circle_fb(120, 120, 88,  BLACK)
    _push()


# Replace _draw_message with this:
def _draw_message(text, colour, mode):
    global _rendered_snapshot, _msg_text, _msg_colour, _msg_mode
    
    # Store params so flash_task can redraw text each frame
    _msg_text   = text
    _msg_colour = colour
    _msg_mode   = mode

    if mode == 'ring':
        fb.fill(BLACK)
        _fill_circle_fb(120, 120, 118, colour)
        _fill_circle_fb(120, 120, 88,  BLACK)
    else:
        fb.fill(colour)

    # Snapshot background WITHOUT text
    try:
        _rendered_snapshot = bytearray(buf)
    except MemoryError:
        _rendered_snapshot = None

    # Render text into buf then single push — no visible bg box
    _draw_text_on_buf(text, colour, mode)
    _push()



# ── Framebuffer text rendering (write glyphs into buf before _push) ──

def _text8_to_buf(font, text, x0, y0, fg, bg=None):
    """Render 8-wide font glyphs into buf. bg=None skips background pixels."""
    for char in text:
        ch = ord(char)
        if (font.FIRST <= ch < font.LAST
                and x0 + font.WIDTH <= 240
                and y0 + font.HEIGHT <= 240):
            idx = (ch - font.FIRST) * font.HEIGHT
            for row in range(font.HEIGHT):
                byte  = font.FONT[idx + row]
                y_off = (y0 + row) * 480 + x0 * 2
                mask  = 0x80
                for _ in range(8):
                    if byte & mask:
                        buf[y_off]     = fg & 0xFF
                        buf[y_off + 1] = (fg >> 8) & 0xFF
                    elif bg is not None:
                        buf[y_off]     = bg & 0xFF
                        buf[y_off + 1] = (bg >> 8) & 0xFF
                    y_off += 2
                    mask >>= 1
        x0 += font.WIDTH


def _text16_to_buf(font, text, x0, y0, fg, bg=None):
    """Render 16-wide font glyphs into buf. bg=None skips background pixels."""
    passes = 4 if font.HEIGHT == 32 else 2
    size   = 64 if font.HEIGHT == 32 else 32
    for char in text:
        ch = ord(char)
        if (font.FIRST <= ch < font.LAST
                and x0 + font.WIDTH <= 240
                and y0 + font.HEIGHT <= 240):
            for line in range(passes):
                idx    = (ch - font.FIRST) * size + 16 * line
                base_y = y0 + 8 * line
                for row in range(8):
                    byte_hi = font.FONT[idx + row * 2]
                    byte_lo = font.FONT[idx + row * 2 + 1]
                    y_off   = (base_y + row) * 480 + x0 * 2
                    mask = 0x80
                    for _ in range(8):
                        if byte_hi & mask:
                            buf[y_off]     = fg & 0xFF
                            buf[y_off + 1] = (fg >> 8) & 0xFF
                        elif bg is not None:
                            buf[y_off]     = bg & 0xFF
                            buf[y_off + 1] = (bg >> 8) & 0xFF
                        y_off += 2
                        mask >>= 1
                    mask = 0x80
                    for _ in range(8):
                        if byte_lo & mask:
                            buf[y_off]     = fg & 0xFF
                            buf[y_off + 1] = (fg >> 8) & 0xFF
                        elif bg is not None:
                            buf[y_off]     = bg & 0xFF
                            buf[y_off + 1] = (bg >> 8) & 0xFF
                        y_off += 2
                        mask >>= 1
        x0 += font.WIDTH


def _draw_text_centered_to_buf(text, y, font, char_w, fg=WHITE, bg=None):
    x = max(0, (240 - len(text) * char_w) // 2)
    if font.WIDTH == 8:
        _text8_to_buf(font, text, x, y, fg, bg)
    else:
        _text16_to_buf(font, text, x, y, fg, bg)


def _draw_text_on_buf(text, colour, mode, fg_override=None):
    """Render text into buf (framebuffer) — call before _push(). Background pixels
    are transparent (not written), so fb.fill() underneath shows through."""
    words = text.upper().split()
    fg    = fg_override if fg_override is not None else (colour if mode == 'ring' else BLACK)

    if len(text) <= 7:
        _draw_text_centered_to_buf(text.upper(), 104, font_big, 16, fg)
        return

    placed = False
    for i in range(1, len(words)):
        l1 = ' '.join(words[:i])
        l2 = ' '.join(words[i:])
        if len(l1) <= 7 and len(l2) <= 7:
            _draw_text_centered_to_buf(l1, 88,  font_big, 16, fg)
            _draw_text_centered_to_buf(l2, 120, font_big, 16, fg)
            placed = True
            break

    if not placed:
        if len(text) <= 14:
            _draw_text_centered_to_buf(text.upper(), 112, font_med, 8, fg)
        else:
            for i in range(1, len(words)):
                l1 = ' '.join(words[:i])
                l2 = ' '.join(words[i:])
                if len(l1) <= 14 and len(l2) <= 14:
                    _draw_text_centered_to_buf(l1, 100, font_med, 8, fg)
                    _draw_text_centered_to_buf(l2, 120, font_med, 8, fg)
                    break
                
# ════════════════════════════════════
# MIDDLE FINGER
# ════════════════════════════════════
def _draw_ring_background():
    colour = STATE_COLOURS[current['state']]
    fb.fill(BLACK)
    _fill_circle_fb(120, 120, 118, colour)
    _fill_circle_fb(120, 120, 88,  BLACK)
    _push()


def _draw_middle_finger_frame(raise_amount):
    global _ring_drawn, _static_drawn
    colour = STATE_COLOURS[current['state']]

    if not _ring_drawn:
        _draw_ring_background()
        _ring_drawn = True

    if not _static_drawn:
        fb.fill_rect(95,  155, 50, 45, colour)
        fb.fill_rect(75,  135, 18, 30, colour)
        fb.fill_rect(95,  120, 18, 40, colour)
        fb.fill_rect(131, 120, 18, 40, colour)
        fb.fill_rect(151, 135, 18, 30, colour)
        fb.fill_rect(93,  120, 2,  55, BLACK)
        fb.fill_rect(129, 120, 2,  55, BLACK)
        fb.fill_rect(149, 120, 2,  55, BLACK)
        _static_drawn = True

    fb.fill_rect(113, 60, 18, 120, BLACK)
    offset = int((1.0 - raise_amount) * 50)
    fb.fill_rect(113, 85 + offset, 18, 75, colour)
    fb.fill_rect(111, 60, 2, 120, BLACK)
    fb.fill_rect(129, 60, 2, 120, BLACK)
    _push()


# ════════════════════════════════════
# TRANSITIONS
# ════════════════════════════════════
def _draw_finger_with_colour(colour):
    """Draw full static finger in given colour — used during transitions."""
    fb.fill(BLACK)
    _fill_circle_fb(120, 120, 118, colour)
    _fill_circle_fb(120, 120, 88,  BLACK)
    for rect in [
        (95, 155, 50, 45), (75, 135, 18, 30), (95, 120, 18, 40),
        (131, 120, 18, 40), (151, 135, 18, 30), (113, 85, 18, 75),
    ]:
        fb.fill_rect(rect[0], rect[1], rect[2], rect[3], colour)
    for rect in [(93, 120, 2, 55), (129, 120, 2, 55), (149, 120, 2, 55)]:
        fb.fill_rect(rect[0], rect[1], rect[2], rect[3], BLACK)
    _push()


def render_transition_frame():
    t = transition['progress']
    if t >= 1.0:
        transition['active'] = False
        render_state()
        return False

    colour = _lerp_colour(transition['from_rgb'], transition['to_rgb'], t)
    mode   = current['mode']

    if current['show_middle_finger']:
        _draw_finger_with_colour(colour)
    elif current['message']:
        mode = current['mode']
        if mode == 'ring':
            fb.fill(BLACK)
            _fill_circle_fb(120, 120, 118, colour)
            _fill_circle_fb(120, 120, 88,  BLACK)
        else:
            fb.fill(colour)
        _draw_text_on_buf(current['message'], colour, mode)
        _push()
    else:
        if mode in ('solid', 'flash'):
            fb.fill(colour)
            _push()
        elif mode == 'ring':
            fb.fill(colour)
            _fill_circle_fb(120, 120, 90, BLACK)  # ← circle not rect
            _push()

    transition['progress'] = min(1.0, t + transition['speed'])
    return True


def start_transition(from_state, to_state):
    global _ring_drawn, _static_drawn
    _ring_drawn   = False
    _static_drawn = False
    mem.collect()
    transition['active']   = True
    transition['from_rgb'] = COLOUR_RGB[from_state]
    transition['to_rgb']   = COLOUR_RGB[to_state]
    transition['progress'] = 0.0


# ════════════════════════════════════
# MAIN RENDER
# ════════════════════════════════════
def render_state():
    global _ring_drawn, _static_drawn, _rendered_snapshot, _msg_text, _msg_colour, _msg_mode
    _ring_drawn        = False
    _static_drawn      = False
    _rendered_snapshot = None
    _msg_text          = None
    _msg_colour        = None
    _msg_mode          = None
    mem.collect()
    
    try:
        import image_loader
        if image_loader.active:
            image_loader.clear()
    except Exception:
        pass

    colour = STATE_COLOURS[current['state']]
    mode   = current['mode']

    if current['show_middle_finger']:
        _draw_middle_finger_frame(1.0)
    elif current['message']:
        _draw_message(current['message'], colour, mode)   # ← pass mode
    else:
        if mode in ('solid', 'flash'):
            fb.fill(colour)
            _push()
        elif mode == 'ring':
            fb.fill(colour)
            _fill_circle_fb(120, 120, 90, BLACK)
            _push()

render_state()
