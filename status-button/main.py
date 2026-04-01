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

                        slot_name = item.get('slotName', str(item.get('index', 0)))
                        path      = f'/static/sequence_slots/seq_slot_{slot_name}.bin'
                        print(f"Loading slot '{slot_name}' from {path}, RAM: {mem.free()}")

                        # Kill transition/flash before streaming so nothing draws over it
                        state.transition['active']          = False
                        state.transition['progress']        = 1.0
                        state.current['mode']               = 'solid'
                        state.current['show_middle_finger'] = False
                        state.current['message']            = None
                        await asyncio.sleep_ms(30)

                        try:
                            ROWS      = 8
                            row_bytes = 240 * 2
                            buf       = bytearray(ROWS * row_bytes)
                            mv        = memoryview(buf)
                            with open(path, 'rb') as f:
                                y = 0
                                while y < 240:
                                    rows   = min(ROWS, 240 - y)
                                    n      = f.readinto(mv[:rows * row_bytes])
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
                # No sequence — cycle states manually on button press
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
                and not image_loader.active
                and not state.transition['active']):

            t0      = time.ticks_ms()
            cur_st  = state.current['state']
            cur_msg = state.current['message']
            colour  = state.STATE_COLOURS[cur_st]

            # Reset pulse on state change
            state_key = (cur_st, cur_msg)
            if state_key != last_state:
                last_state = state_key
                step = 0

            # Sine pulse value 0..1
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

    SPEED        = 0.05
    PAUSE_FRAMES = 15
    FLASH_COUNT  = 3
    FLASH_MS     = 300
    step         = 0
    pause        = 0
    flashed_top  = False

    while True:
        if (state.current['state'] == 'red'
                and state.current['show_middle_finger']
                and state.current['mode'] != 'flash'
                and not state.transition['active']):

            t0           = time.ticks_ms()
            raise_amount = (math.sin(step * SPEED) + 1) / 2
            at_top       = raise_amount > 0.98
            at_bottom    = raise_amount < 0.02

            if at_top:
                if not flashed_top:
                    state._draw_middle_finger_frame(1.0)
                    if not state.finger_no_text:
                        for _ in range(FLASH_COUNT):
                            state._draw_text_centered(
                                "UP YOURS", 170, state.font_med, 8,
                                state.STATE_COLOURS[state.current['state']],
                                state.BLACK
                            )
                            await asyncio.sleep_ms(FLASH_MS)
                            state.tft.fill_rect(0, 165, 240, 20, state.BLACK)
                            await asyncio.sleep_ms(FLASH_MS)
                    flashed_top = True

                if pause < PAUSE_FRAMES:
                    pause += 1
                else:
                    pause = 0; flashed_top = False; step += 1

            elif at_bottom:
                flashed_top = False
                if pause < PAUSE_FRAMES:
                    pause += 1
                else:
                    pause = 0; step += 1
            else:
                pause = 0; step += 1

            state._draw_middle_finger_frame(raise_amount)
            elapsed = time.ticks_diff(time.ticks_ms(), t0)
            await asyncio.sleep_ms(max(0, 50 - elapsed))
        else:
            step = 0; pause = 0; flashed_top = False
            await asyncio.sleep_ms(30)


async def gif_task():
    import time
    frame_idx = 0
    while True:
        if gif_player.active and gif_player._frame_count > 0:
            t0    = time.ticks_ms()
            frame = gif_player.read_frame(frame_idx)
            if frame:
                state.tft.blit_buffer(frame, 0, 0, 240, 240)
                frame = None
                mem.collect()
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
            old   = state.current['state']          # capture BEFORE check_jobs mutates it
            fired = scheduler.check_jobs(state.current)
            if fired:
                # Clear any active media
                gif_player.clear()
                image_loader.image_data = None
                image_loader.active     = False
                mem.collect()
                # Kill any in-progress transition
                state.transition['active']   = False
                state.transition['progress'] = 1.0
                new = state.current['state']         # already updated by check_jobs
                print(f"Scheduler rendering: {old} -> {new}, mode={state.current['mode']}")
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