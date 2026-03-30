import time
import binascii
import mem
from microdot import Microdot, Response, send_file
import state
import gif_player
import image_loader
import scheduler
import config
import network

def _clear_media():
    """Safely clear all media — handles partially loaded modules."""
    try:
        gif_player.clear()
    except Exception as e:
        print(f"gif_player.clear: {e}")
    try:
        image_loader.clear()
    except Exception as e:
        print(f"image_loader.clear: {e}")
    try:
        state.current['gif_url'] = None
    except Exception as e:
        print(f"state gif_url: {e}")
    mem.collect()

app = Microdot()
Response.default_content_type = 'application/json'
app.max_content_length = 1024 * 1024

CORS_HEADERS = {
    'Access-Control-Allow-Origin':  '*',
    'Access-Control-Allow-Methods': 'GET, POST, DELETE, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
}

SLOT_PATH = '/seq_slot_{}.bin'

def _slot_path(slot):
    return SLOT_PATH.format(slot)

def _save_slot_to_flash(slot, data):
    """Write raw RGB565 bytearray to flash."""
    path = _slot_path(slot)
    with open(path, 'wb') as f:
        f.write(data)
    print(f"Slot {slot} saved to {path} ({len(data)} bytes)")

def _load_slot_from_flash(slot):
    """Read raw RGB565 from flash. Returns bytearray or None."""
    path = _slot_path(slot)
    try:
        with open(path, 'rb') as f:
            return f.read()
    except OSError:
        return None

def _clear_all_slots():
    """Delete all slot files from flash."""
    import os
    for i in range(20):
        try:
            os.remove(_slot_path(i))
        except OSError:
            pass
    mem.collect()
_raw_buf      = None
_raw_pos      = 0
_raw_total    = 0
_b64_leftover = ''

@app.after_request
async def add_cors(request, response):
    response.headers['Access-Control-Allow-Origin']  = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response


# ── OPTIONS ──
@app.route('/health',               methods=['OPTIONS'])
async def opt_health(request):               return '', 204, CORS_HEADERS
@app.route('/state',                methods=['OPTIONS'])
async def opt_state(request):                return '', 204, CORS_HEADERS
@app.route('/config',               methods=['OPTIONS'])
async def opt_config(request):               return '', 204, CORS_HEADERS
@app.route('/gif',                  methods=['OPTIONS'])
async def opt_gif(request):                  return '', 204, CORS_HEADERS
@app.route('/gif565',               methods=['OPTIONS'])
async def opt_gif565(request):               return '', 204, CORS_HEADERS
@app.route('/image',                methods=['OPTIONS'])
async def opt_image(request):                return '', 204, CORS_HEADERS
@app.route('/upload_chunk',         methods=['OPTIONS'])
async def opt_upload_chunk(request):         return '', 204, CORS_HEADERS
@app.route('/schedule',             methods=['OPTIONS'])
async def opt_schedule(request):             return '', 204, CORS_HEADERS
@app.route('/schedule/<id>',        methods=['OPTIONS'])
async def opt_schedule_id(request, id):      return '', 204, CORS_HEADERS
@app.route('/schedule/<id>/toggle', methods=['OPTIONS'])
async def opt_schedule_tog(request, id):     return '', 204, CORS_HEADERS


# ── Health ──
@app.get('/')
async def index(request):
    return send_file('index.html', content_type='text/html')

@app.get('/health')
async def health(request):
    mem.collect()
    return {
        'status':    'ok',
        'uptime_ms': time.ticks_ms(),
        'free_ram':  mem.free(),
    }


# ── State ──
@app.get('/state')
async def get_state(request):
    return dict(state.current)

@app.post('/state')
async def set_state(request):
    mem.collect()
    body = request.json
    if body is None:
        return {'error': 'JSON body required'}, 400

    new_state = body.get('state')
    if new_state is None:
        return {'error': 'state field required'}, 400
    if new_state not in state.STATES:
        return {'error': 'invalid state'}, 400

    show_middle_finger = body.get('show_middle_finger', False)
    message            = body.get('message', None)

    if show_middle_finger and message:
        return {'error': 'cannot set both'}, 400

    del body
    mem.collect()

    old_state = state.current['state']
    state.current['state']              = new_state
    state.current['show_middle_finger'] = bool(show_middle_finger)
    state.current['message']            = str(message) if message else None

    _clear_media()
    state.current['gif_url'] = None

    if old_state != new_state:
        state.start_transition(old_state, new_state)
    else:
        state.render_state()

    return dict(state.current)


# ── Config ──
@app.get('/config')
async def get_config(request):
    return {'mode': state.current['mode']}

@app.post('/config')
async def set_config(request):
    mem.collect()
    body = request.json
    if body is None:
        return {'error': 'JSON body required'}, 400

    mode = body.get('mode')
    del body
    if mode is None:
        return {'error': 'mode required'}, 400
    if mode not in state.MODES:
        return {'error': 'invalid mode'}, 400

    state.current['mode'] = mode
    state.render_state()
    return {'mode': state.current['mode']}


# ── GIF from URL (legacy — small GIFs only) ──
@app.post('/gif')
async def set_gif(request):
    mem.collect()
    body = request.json
    if body is None:
        return {'error': 'JSON body required'}, 400

    url = body.get('url')
    del body
    mem.collect()

    if not url:
        return {'error': 'url required'}, 400

    if url == 'clear':
        _clear_media()
        state.current['gif_url'] = None
        state.render_state()
        return {'status': 'cleared'}

    return {'error': 'Use gif_converter.py + /gif565 for reliable GIF playback'}, 400


# ── GIF565 from flash ──
@app.post('/gif565')
async def set_gif565(request):
    mem.collect()
    body = request.json
    if body is None:
        return {'error': 'JSON body required'}, 400

    path = body.get('path')
    del body
    mem.collect()

    if not path:
        return {'error': 'path required'}, 400

    if path == 'clear':
        _clear_media()
        state.current['gif_url'] = None
        state.render_state()
        return {'status': 'cleared'}

    try:
        _clear_media()
        mem.collect()
        count, delay = gif_player.load_from_file(path)
        state.current['gif_url']            = path
        state.current['show_middle_finger'] = False
        state.current['message']            = None
        return {'status': 'ok', 'frames': count, 'delay_ms': delay, 'free_ram': mem.free()}
    except Exception as e:
        mem.collect()
        return {'error': str(e)}, 500


# ── Image from URL ──
@app.post('/image')
async def set_image(request):
    mem.collect()
    body = request.json
    if body is None:
        return {'error': 'JSON body required'}, 400

    url = body.get('url')
    del body
    mem.collect()

    if not url:
        return {'error': 'url required'}, 400

    if url == 'clear':
        _clear_media()
        state.current['gif_url'] = None
        state.render_state()
        return {'status': 'cleared'}

    try:
        _clear_media()
        state.current['gif_url']            = None
        state.current['show_middle_finger'] = False
        state.current['message']            = None
        mem.collect()
        image_loader.load_from_url(url)
        image_loader.display()
        return {'status': 'ok', 'free_ram': mem.free()}
    except Exception as e:
        mem.collect()
        return {'error': str(e)}, 500


@app.post('/upload_chunk')
async def upload_chunk(request):
    global _raw_buf, _raw_pos, _raw_total, _b64_leftover, _seq_slots

    mem.collect()

    body = request.json
    if body is None:
        return {'error': 'JSON body required'}, 400

    chunk = body.get('chunk')
    index = body.get('index')
    total = body.get('total')
    slot  = body.get('slot', None)   # optional — if set, store in _seq_slots[slot]
    del body
    mem.collect()

    if chunk is None or index is None or total is None:
        return {'error': 'chunk, index, total required'}, 400

    if index == 0:
        _raw_buf              = None
        _b64_leftover         = ''

        # Free image and gif data
        try:
            image_loader.image_data = None
            image_loader.active     = False
        except Exception:
            pass
        try:
            gif_player.clear()
        except Exception:
            pass

        # Defragment heap before allocating
        free = mem.defrag()
        mem.report('after defrag')

        NEEDED = 240 * 240 * 2 + 8000
        if free < NEEDED:
            return {
                'error': f'Not enough RAM after defrag: need {NEEDED}B, '
                         f'have {free}B. Try rebooting.'
            }, 500

        try:
            _raw_buf   = bytearray(240 * 240 * 2)
            _raw_pos   = 0
            _raw_total = total
            mem.report('buffer allocated')
        except MemoryError as e:
            _raw_buf = None
            mem.defrag()
            return {'error': f'Alloc failed after defrag: {e} — reboot recommended'}, 500
    if _raw_buf is None:
        return {'error': 'Send chunk 0 first'}, 400

    # Decode chunk directly into buffer
    b64_data      = _b64_leftover + chunk
    chunk         = None
    mem.collect()

    complete      = (len(b64_data) // 4) * 4
    _b64_leftover = b64_data[complete:]
    to_decode     = b64_data[:complete]
    b64_data      = None
    mem.collect()

    if to_decode:
        try:
            decoded   = binascii.a2b_base64(to_decode)
            to_decode = None
            n         = len(decoded)
            _raw_buf[_raw_pos:_raw_pos + n] = decoded
            _raw_pos += n
            decoded   = None
            mem.collect()
        except Exception as e:
            to_decode = None
            mem.collect()
            return {'error': f'Decode: {e}'}, 500
    else:
        to_decode = None

    # Last chunk — decode leftover then either store to slot or display
    if index == total - 1:
        if _b64_leftover:
            try:
                pad = len(_b64_leftover) % 4
                if pad:
                    _b64_leftover += '=' * (4 - pad)
                decoded       = binascii.a2b_base64(_b64_leftover)
                n             = len(decoded)
                _raw_buf[_raw_pos:_raw_pos + n] = decoded
                _raw_pos     += n
                decoded       = None
                _b64_leftover = ''
                mem.collect()
            except Exception as e:
                return {'error': f'Final decode: {e}'}, 500

        if slot is not None:
            # Save to flash — frees RAM immediately
            try:
                _save_slot_to_flash(slot, _raw_buf)
                _raw_buf = None
                mem.collect()
                mem.collect()
                mem.collect()
                print(f"Slot {slot} on flash, RAM: {mem.free()}")
                return {'status': 'ok', 'slot': slot, 'free_ram': mem.free()}
            except Exception as e:
                _raw_buf = None
                mem.collect()
                return {'error': f'Slot save: {e}'}, 500
        else:
            # Normal upload — display immediately
            try:
                _clear_media()
                image_loader.image_data = _raw_buf
                image_loader.active     = True
                _raw_buf                = None
                mem.collect()
                mem.collect()
                mem.collect()
                mem.report('before blit')
                state.tft.blit_buffer(image_loader.image_data, 0, 0, 240, 240)
                return {'status': 'ok', 'bytes': _raw_pos, 'free_ram': mem.free()}
            except Exception as e:
                _raw_buf                = None
                image_loader.image_data = None
                image_loader.active     = False
                mem.collect()
                return {'error': str(e)}, 500

    return {'status': 'chunk_received', 'index': index, 'free_ram': mem.free()}
# ── Scheduler ──
@app.get('/schedule')
async def get_schedule(request):
    return {'jobs': scheduler.get_jobs()}

@app.post('/schedule')
async def create_job(request):
    mem.collect()
    body = request.json
    if body is None:
        return {'error': 'JSON body required'}, 400

    hour    = body.get('hour')
    minute  = body.get('minute')
    days    = body.get('days', [])
    s       = body.get('state')
    mode    = body.get('mode', 'solid')
    finger  = body.get('show_middle_finger', False)
    message = body.get('message', None)
    del body
    mem.collect()

    if hour is None or minute is None:
        return {'error': 'hour and minute required'}, 400
    if not (0 <= hour <= 23):
        return {'error': 'hour 0-23'}, 400
    if not (0 <= minute <= 59):
        return {'error': 'minute 0-59'}, 400
    if s not in state.STATES:
        return {'error': 'invalid state'}, 400
    if mode not in state.MODES:
        return {'error': 'invalid mode'}, 400

    return scheduler.add_job(hour, minute, days, s, mode, finger, message)

@app.post('/schedule/<id>/toggle')
async def toggle_job(request, id):
    job = scheduler.toggle_job(int(id))
    if job is None:
        return {'error': 'not found'}, 404
    return job

@app.delete('/schedule/<id>')
async def delete_job(request, id):
    if not scheduler.remove_job(int(id)):
        return {'error': 'not found'}, 404
    return {'deleted': int(id)}

@app.route('/clear', methods=['OPTIONS'])
async def opt_clear(request):
    return '', 204, CORS_HEADERS

@app.post('/clear')
async def clear_all(request):
    global _raw_buf, _b64_leftover
    _raw_buf              = None
    _b64_leftover         = ''
    try:
        image_loader.image_data = None
        image_loader.active     = False
    except Exception:
        pass
    _clear_media()
    mem.defrag()
    mem.report('after clear')
    return {'status': 'cleared', 'free_ram': mem.free()}

@app.route('/button_sequence', methods=['OPTIONS'])
async def opt_btn_seq(request):
    return '', 204, CORS_HEADERS

@app.post('/button_sequence')
async def set_button_sequence(request):
    mem.collect()
    body = request.json
    if body is None:
        return {'error': 'JSON body required'}, 400
    sequence = body.get('sequence', [])
    del body
    mem.collect()
    state.btn_sequence = sequence
    state.btn_index    = 0
    # No RAM held — slots are on flash
    return {'status': 'ok', 'count': len(sequence), 'free_ram': mem.free()}

@app.route('/reboot', methods=['OPTIONS'])
async def opt_reboot(request):
    return '', 204, CORS_HEADERS

@app.post('/reboot')
async def do_reboot(request):
    import machine
    # Schedule reboot after response is sent
    import asyncio
    async def _reboot():
        await asyncio.sleep_ms(500)
        machine.reset()
    asyncio.create_task(_reboot())
    return {'status': 'rebooting'}

@app.route('/time', methods=['OPTIONS'])
async def opt_time(request):
    return '', 204, CORS_HEADERS

@app.get('/time')
async def get_time(request):
    import time
    t = time.localtime()
    return {
        'year': t[0], 'month': t[1], 'day': t[2],
        'hour': t[3], 'minute': t[4], 'second': t[5],
        'weekday': t[6]
    }

@app.post('/time')
async def set_time(request):
    body = request.json
    if body is None:
        return {'error': 'JSON body required'}, 400
    try:
        import machine
        rtc = machine.RTC()
        rtc.datetime((
            body.get('year',  2025),
            body.get('month', 1),
            body.get('day',   1),
            body.get('weekday', 0),
            body.get('hour',  0),
            body.get('minute', 0),
            body.get('second', 0),
            0
        ))
        import time
        t = time.localtime()
        return {'status': 'ok', 'hour': t[3], 'minute': t[4]}
    except Exception as e:
        return {'error': str(e)}, 500
    
# ── Config / hostname ──
@app.route('/config/device', methods=['OPTIONS'])
async def opt_device_config(request):
    return '', 204, CORS_HEADERS

@app.get('/config/device')
async def get_device_config(request):
    return {
        'hostname':      config.get('hostname'),
        'wifi_ssid':     config.get('wifi_ssid'),
        'has_password':  bool(config.get('wifi_password')),
    }

@app.post('/config/device')
async def set_device_config(request):
    mem.collect()
    body = request.json
    if body is None:
        return {'error': 'JSON body required'}, 400

    changed = False

    if 'hostname' in body:
        hn = body['hostname'].strip().lower()
        # Sanitise — only alphanumeric and hyphens
        VALID = 'abcdefghijklmnopqrstuvwxyz0123456789-'
        hn = ''.join(c for c in hn if c in VALID)
        
        hn = hn[:32] or 'picoctrl'
        config.set('hostname', hn)
        # Apply immediately
        try:
            network.hostname(hn)
        except Exception as e:
            print(f"Hostname apply: {e}")
        changed = True

    if 'wifi_ssid' in body:
        config.set('wifi_ssid', body['wifi_ssid'])
        changed = True

    if 'wifi_password' in body and body['wifi_password']:
        config.set('wifi_password', body['wifi_password'])
        changed = True

    del body
    mem.collect()

    return {
        'status':   'ok',
        'changed':  changed,
        'hostname': config.get('hostname'),
        'note':     'Reboot to apply WiFi changes' if changed else '',
    }

# ── Error handlers ──
@app.errorhandler(404)
async def not_found(request):
    return {'error': 'not found'}, 404, CORS_HEADERS

@app.errorhandler(500)
async def internal_error(request):
    mem.collect()
    return {'error': 'internal error'}, 500, CORS_HEADERS
