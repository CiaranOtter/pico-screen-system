import asyncio
import network
import machine
from machine import Pin
import config
import scheduler
import state
import mem
import gif_player
import image_loader
from api import app

WIFI_TIMEOUT_S = config.get('wifi_timeout', 20)

def apply_hostname():
    """Set the network hostname from config."""
    hostname = config.get('hostname', 'picoctrl')
    try:
        network.hostname(hostname)
        print(f"Hostname set: {hostname}")
    except Exception as e:
        print(f"Hostname error: {e}")


async def sync_ntp():
    try:
        import ntptime
        ntptime.host    = 'pool.ntp.org'
        ntptime.timeout = 10
        ntptime.settime()
        import time
        t = time.localtime()
        print(f"NTP: {t[0]}-{t[1]:02d}-{t[2]:02d} {t[3]:02d}:{t[4]:02d}")
    except Exception as e:
        print(f"NTP failed: {e}")


async def connect_wifi():
    # Use config for credentials if set, otherwise fall back to hardcoded
    ssid     = config.get('wifi_ssid')
    password = config.get('wifi_password')

    apply_hostname()

    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(ssid, password)
    step = 0
    for _ in range(WIFI_TIMEOUT_S * 10):
        if wlan.isconnected():
            ip = wlan.ifconfig()[0]
            print(f"WiFi: {ip}")
            await sync_ntp()
            state._draw_status_screen(True)
            await asyncio.sleep(2)
            state.render_state()
            mem.report('after wifi')
            return True
        if step % 3 == 0:
            state._draw_loading_frame(step, "Connecting...")
        step += 1
        await asyncio.sleep(0.1)

    print('WiFi failed')
    state._draw_status_screen(False)
    await asyncio.sleep(5)
    machine.reset()
    return False


button = Pin(13, Pin.IN, Pin.PULL_UP)


async def button_task():
    last_btn = 1
    while True:
        btn = button.value()
        if btn == 0 and last_btn == 1:  # button just pressed
            if state.btn_sequence:
                new_index = (state.btn_index + 1) % len(state.btn_sequence)
                if new_index >= len(state.btn_sequence):
                    last_btn = btn
                    await asyncio.sleep_ms(10)
                    continue
                state.btn_index = new_index
                item = state.btn_sequence[state.btn_index]
                old  = state.current['state']
                new  = item.get('state', 'green')

                if item.get('hasSaved'):
                    try:
                        gif_player.clear()
                        image_loader.image_data = None
                        image_loader.active     = False
                        mem.collect()
                        mem.collect()
                        mem.collect()

                        slot_idx = item.get('index', 0)
                        path     = f'/static/sequence_slots/seq_slot_{slot_idx}.bin'
                        print(f"Loading slot {slot_idx} from {path}, RAM: {mem.free()}")
                        print(f"Item: {item}")  # ← add this to see what the Pico received

                        try:
                            # Stream directly to display in small row chunks
                            # — never allocates more than ROWS * 480 bytes at once
                            ROWS      = 8
                            row_bytes = 240 * 2
                            buf       = bytearray(ROWS * row_bytes)
                            mv        = memoryview(buf)

                            with open(path, 'rb') as f:
                                y = 0
                                while y < 240:
                                    rows  = min(ROWS, 240 - y)
                                    n     = f.readinto(mv[:rows * row_bytes])
                                    if not n:
                                        break
                                    actual = n // row_bytes
                                    state.tft.blit_buffer(mv[:actual * row_bytes], 0, y, 240, actual)
                                    y += actual

                            buf = None
                            mv  = None
                            mem.collect()
                            image_loader.active = True

                        except OSError:
                            print(f"{path} not found")
                            buf = None
                            mem.collect()
                            state.render_state()
                            await asyncio.sleep_ms(50)
                            last_btn = btn
                            continue
                        except MemoryError as e:
                            print(f"Cannot alloc row buffer: {e}")
                            mem.collect()
                            state.render_state()
                            await asyncio.sleep_ms(50)
                            last_btn = btn
                            continue

                    except Exception as e:
                        print(f"Slot error: {e}")
                        mem.collect()
                        state.render_state()
                else:
                    image_loader.image_data             = None
                    image_loader.active                 = False
                    gif_player.clear()
                    mem.collect()
                    state.current['state']              = new
                    state.current['mode']               = item.get('mode', 'solid')
                    state.current['show_middle_finger'] = item.get('type') == 'finger'
                    state.current['message']            = item.get('message')
                    state.finger_no_text                = item.get('type') == 'finger'
                    if old != new:
                        state.start_transition(old, new)
                    else:
                        state.render_state()
            else:
                # no sequence — cycle through states manually
                old = state.current['state']
                idx = list(state.STATES).index(old)
                new = state.STATES[(idx + 1) % len(state.STATES)]
                state.current['state']              = new
                state.current['show_middle_finger'] = False
                state.current['message']            = None
                state.finger_no_text                = False
                image_loader.image_data             = None
                image_loader.active                 = False
                gif_player.clear()
                mem.collect()
                state.start_transition(old, new)
                await asyncio.sleep_ms(50)

        last_btn = btn
        await asyncio.sleep_ms(10)
async def flash_task():
    """Smooth sine-wave background pulse with stable text overlay."""
    import math, time
    step       = 0
    SPEED      = 0.08
    last_state = None

    while True:
        if (state.current['mode'] == 'flash'
                and not state.current['show_middle_finger']
                and not gif_player.active
                and not image_loader.active):

            # Wait for any active transition to finish before flashing
            if state.transition['active']:
                await asyncio.sleep_ms(33)
                continue

            t0      = time.ticks_ms()
            cur_st  = state.current['state']
            cur_msg = state.current['message']
            colour  = state.STATE_COLOURS[cur_st]

            # Reset pulse on state change
            state_key = (cur_st, cur_msg)
            if state_key != last_state:
                last_state = state_key
                step = 0

            # Sine pulse value
            t    = (math.sin(step * SPEED) + 1) / 2
            step += 1

            blended = state._blend_colour(state.BLACK, colour, t)
            state.fb.fill(blended)
            if cur_msg:
                state._draw_text_on_buf(cur_msg, colour, 'flash', fg_override=state.WHITE)
            state._push()

            elapsed = time.ticks_diff(time.ticks_ms(), t0)
            await asyncio.sleep_ms(max(0, 33 - elapsed))
        else:
            step       = 0
            last_state = None
            await asyncio.sleep_ms(33)
            
async def transition_task():
    while True:
        if (state.transition['active']
                and state.current['mode'] != 'flash'):  # ← add this guard
            state.render_transition_frame()
            await asyncio.sleep_ms(16)
        else:
            await asyncio.sleep_ms(16)


async def finger_task():
    import math, time
 
    # Animation constants
    RISE_SPEED   = 0.04   # how fast the finger rises (lower = slower)
    HOLD_FRAMES  = 25     # frames to hold at the top
    REST_FRAMES  = 20     # frames to rest at the bottom
    SHAKE_RANGE  = 3      # pixels of horizontal shake at the top
 
    step        = 0
    hold_count  = 0
    rest_count  = 0
    phase       = 'rise'  # 'rise' | 'hold' | 'lower' | 'rest'
    shake_idx   = 0
 
    while True:
        if (state.current['state'] == 'red'
                and state.current['show_middle_finger']
                and state.current['mode'] != 'flash'
                and not state.transition['active']):
 
            t0 = time.ticks_ms()
 
            if phase == 'rise':
                step += 1
                raise_amount = min(1.0, step * RISE_SPEED)
                state._draw_middle_finger_frame(raise_amount, shake_x=0)
                if raise_amount >= 1.0:
                    phase      = 'hold'
                    hold_count = 0
                    shake_idx  = 0
 
            elif phase == 'hold':
                # Subtle left-right shake at the top
                shake_offsets = [0, 1, 2, 1, 0, -1, -2, -1]
                sx = shake_offsets[shake_idx % len(shake_offsets)] * SHAKE_RANGE // 2
                state._draw_middle_finger_frame(1.0, shake_x=sx)
                shake_idx  += 1
                hold_count += 1
                if hold_count >= HOLD_FRAMES:
                    phase = 'lower'
                    step  = int(1.0 / RISE_SPEED)  # start from top
 
            elif phase == 'lower':
                step -= 1
                raise_amount = max(0.0, step * RISE_SPEED)
                state._draw_middle_finger_frame(raise_amount, shake_x=0)
                if raise_amount <= 0.0:
                    phase      = 'rest'
                    rest_count = 0
 
            elif phase == 'rest':
                rest_count += 1
                if rest_count >= REST_FRAMES:
                    phase = 'rise'
                    step  = 0
 
            elapsed = time.ticks_diff(time.ticks_ms(), t0)
            await asyncio.sleep_ms(max(10, 40 - elapsed))
 
        else:
            # Reset when not active
            step       = 0
            hold_count = 0
            rest_count = 0
            phase      = 'rise'
            shake_idx  = 0
            await asyncio.sleep_ms(30)
async def gif_task():
    import time
    frame_idx = 0
    while True:
        if gif_player.active and gif_player._frame_count > 0:
            t0 = time.ticks_ms()
            gif_player.read_frame(frame_idx)  # blits directly, no buffer returned
            delay     = gif_player.get_delay(frame_idx)
            frame_idx = (frame_idx + 1) % gif_player._frame_count
            elapsed   = time.ticks_diff(time.ticks_ms(), t0)
            await asyncio.sleep_ms(max(10, delay - elapsed))
        else:
            frame_idx = 0
            await asyncio.sleep_ms(50)

async def scheduler_task():
    import time
    while True:
        try:
            fired = scheduler.check_jobs(state.current)
            if fired:
                # Clear any active media so the scheduled state actually shows
                gif_player.clear()
                image_loader.image_data = None
                image_loader.active     = False
                mem.collect()

                # Stop any transition in progress
                state.transition['active']   = False
                state.transition['progress'] = 1.0

                old = fired.get('_prev_state', state.current['state'])
                new = fired['state']

                if old != new:
                    state.start_transition(old, new)
                else:
                    state.render_state()
        except Exception as e:
            print(f"Scheduler error: {e}")
        await asyncio.sleep(20)


async def main():
    mem.report('boot')
    await connect_wifi()
    state.render_state()  # ← render once here, after boot
    mem.report('pre-gather')
    await asyncio.gather(
        app.start_server(host='0.0.0.0', port=80, debug=False),
        button_task(),
        flash_task(),
        transition_task(),
        finger_task(),
        gif_task(),
        scheduler_task(),
    )

asyncio.run(main())
