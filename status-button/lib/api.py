import time
import binascii
import hashlib
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
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
}

# ── Auth ──
# Tokens are deterministic: sha256(password + ':' + role).
# _sessions is rebuilt from config on every boot, so tokens survive Pico reboots.
_sessions     = {}
_PUBLIC_WRITE = {'/login', '/logout'}

def _derive_token(password, role):
    data = '{}:{}'.format(password, role).encode()
    return binascii.hexlify(hashlib.sha256(data).digest()).decode()

def _rebuild_sessions():
    """Rebuild session table from current config passwords."""
    _sessions.clear()
    for role, key, default in [
        ('admin',  'admin_pass',  'hal9000'),
        ('viewer', 'viewer_pass', 'daisy'),
    ]:
        pw  = config.get(key, default)
        tok = _derive_token(pw, role)
        _sessions[tok] = {'role': role, 'name': role}
        print(f"Auth: {role} token ready")

_rebuild_sessions()

def _check_auth(request):
    """Return session dict or None."""
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        return _sessions.get(auth[7:].strip())
    return None

@app.before_request
async def auth_guard(request):
    if request.method in ('OPTIONS', 'GET'):
        return None
    if request.path in _PUBLIC_WRITE:
        return None
    s = _check_auth(request)
    if s is None:
        return {'error': 'Unauthorized'}, 401, CORS_HEADERS
    if s.get('role') != 'admin':
        return {'error': 'Forbidden'}, 403, CORS_HEADERS
    return None

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
_TMP_PATH     = '/tmp_upload.bin'
_BLIT_ROWS    = 8
_upload_file  = None
_upload_pos   = 0
_b64_leftover = ''

def _stream_to_display(path):
    """Stream RGB565 file to display in small row chunks — max RAM = _BLIT_ROWS * 480 bytes."""
    import os
    row_bytes = 240 * 2
    buf = bytearray(_BLIT_ROWS * row_bytes)
    mv  = memoryview(buf)
    with open(path, 'rb') as f:
        y = 0
        while y < 240:
            rows  = min(_BLIT_ROWS, 240 - y)
            n     = f.readinto(mv[:rows * row_bytes])
            if not n:
                break
            actual_rows = n // row_bytes
            state.tft.blit_buffer(mv[:actual_rows * row_bytes], 0, y, 240, actual_rows)
            y += actual_rows
    buf = None
    mv  = None
    mem.collect()
    try:
        os.remove(path)
    except OSError:
        pass

@app.after_request
async def add_cors(request, response):
    response.headers['Access-Control-Allow-Origin']  = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
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
@app.route('/login',                methods=['OPTIONS'])
async def opt_login(request):                return '', 204, CORS_HEADERS
@app.route('/logout',               methods=['OPTIONS'])
async def opt_logout(request):               return '', 204, CORS_HEADERS
@app.route('/config/passwords',     methods=['OPTIONS'])
async def opt_passwords(request):            return '', 204, CORS_HEADERS


# ── HTML Pages ──
@app.get('/')
@app.get('/index.html')
async def index(request):
    return send_file('/static/templates/index.html', content_type='text/html')

@app.get('/local')
@app.get('/local-controller.html')
async def local(request):
    return send_file('/static/templates/local-controller.html', content_type='text/html')

@app.get('/login')
@app.get('/login.html')
async def serve_login(request):
    return send_file('/static/templates/login.html', content_type='text/html')

@app.get('/settings')
@app.get('/config.html')
async def serve_settings(request):
    return send_file('/static/templates/config.html', content_type='text/html')


# ── Auth Endpoints ──
@app.post('/login')
async def do_login(request):
    mem.collect()
    body = request.json
    if body is None:
        return {'error': 'JSON body required'}, 400

    password = body.get('password', '')
    name     = (body.get('name') or 'user').strip() or 'user'
    del body
    mem.collect()

    admin_pass  = config.get('admin_pass',  'hal9000')
    viewer_pass = config.get('viewer_pass', 'daisy')

    if password == admin_pass:
        role = 'admin'
    elif password == viewer_pass:
        role = 'viewer'
    else:
        return {'error': 'Invalid credentials'}, 401, CORS_HEADERS

    # Return the deterministic token for this role (pre-built in _sessions)
    token = _derive_token(password, role)
    # Update the display name for this session
    _sessions[token] = {'role': role, 'name': name}
    return {'token': token, 'role': role, 'name': name}

@app.post('/logout')
async def do_logout(request):
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        _sessions.pop(auth[7:].strip(), None)
    return {'status': 'ok'}

@app.get('/whoami')
async def whoami(request):
    s = _check_auth(request)
    return s if s else {'role': None, 'name': None}

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
    global _upload_file, _upload_pos, _b64_leftover

    mem.collect()

    body = request.json
    if body is None:
        return {'error': 'JSON body required'}, 400

    chunk = body.get('chunk')
    index = body.get('index')
    total = body.get('total')
    slot  = body.get('slot', None)
    del body
    mem.collect()

    if chunk is None or index is None or total is None:
        return {'error': 'chunk, index, total required'}, 400

    if index == 0:
        # Close any previous incomplete upload
        if _upload_file is not None:
            try:
                _upload_file.close()
            except Exception:
                pass
            _upload_file = None

        _b64_leftover = ''
        _upload_pos   = 0

        # Free any held media RAM
        try:
            image_loader.image_data = None
            image_loader.active     = False
        except Exception:
            pass
        try:
            gif_player.clear()
        except Exception:
            pass
        mem.collect()

        # Open temp file — stream chunks straight to flash, no large RAM buffer
        import os
        try:
            os.remove(_TMP_PATH)
        except OSError:
            pass
        try:
            _upload_file = open(_TMP_PATH, 'wb')
            mem.report('upload started (streaming to flash)')
        except Exception as e:
            return {'error': f'Cannot open tmp file: {e}'}, 500

    if _upload_file is None:
        return {'error': 'Send chunk 0 first'}, 400

    # Decode chunk and write directly to flash
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
            _upload_file.write(decoded)
            _upload_pos += len(decoded)
            decoded   = None
            mem.collect()
        except Exception as e:
            to_decode = None
            mem.collect()
            return {'error': f'Decode: {e}'}, 500
    else:
        to_decode = None

    # Last chunk — flush leftover bytes then finalise
    if index == total - 1:
        if _b64_leftover:
            try:
                pad = len(_b64_leftover) % 4
                if pad:
                    _b64_leftover += '=' * (4 - pad)
                decoded       = binascii.a2b_base64(_b64_leftover)
                _upload_file.write(decoded)
                _upload_pos  += len(decoded)
                decoded       = None
                _b64_leftover = ''
                mem.collect()
            except Exception as e:
                return {'error': f'Final decode: {e}'}, 500

        _upload_file.close()
        _upload_file = None
        mem.collect()

        if slot is not None:
            import os
            slot_path = _slot_path(slot)
            try:
                os.rename(_TMP_PATH, slot_path)
                print(f"Slot {slot} saved to {slot_path} ({_upload_pos} bytes)")
                return {'status': 'ok', 'slot': slot, 'free_ram': mem.free()}
            except Exception as e:
                return {'error': f'Slot save: {e}'}, 500
        else:
            # Stream file to display in 8-row chunks (max ~3840 bytes RAM)
            try:
                _clear_media()
                mem.collect()
                _stream_to_display(_TMP_PATH)
                image_loader.active = True
                return {'status': 'ok', 'bytes': _upload_pos, 'free_ram': mem.free()}
            except Exception as e:
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
    global _upload_file, _b64_leftover
    if _upload_file is not None:
        try:
            _upload_file.close()
        except Exception:
            pass
        _upload_file  = None
    _b64_leftover = ''
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
    state.btn_index    = -1
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

# ── Password management ──
@app.post('/config/passwords')
async def set_passwords(request):
    mem.collect()
    body = request.json
    if body is None:
        return {'error': 'JSON body required'}, 400

    current = body.get('current_admin', '')
    if current != config.get('admin_pass', 'hal9000'):
        del body; mem.collect()
        return {'error': 'Invalid current admin password'}, 401, CORS_HEADERS

    changed       = False
    admin_changed = False

    if 'admin_pass' in body:
        ap = body['admin_pass'].strip()
        if len(ap) < 4:
            return {'error': 'Admin password must be at least 4 characters'}, 400
        config.set('admin_pass', ap)
        changed = admin_changed = True

    if 'viewer_pass' in body:
        vp = body['viewer_pass'].strip()
        if len(vp) < 4:
            return {'error': 'Viewer password must be at least 4 characters'}, 400
        config.set('viewer_pass', vp)
        changed = True

    del body
    mem.collect()

    # Rebuild tokens — old tokens are now invalid, clients must re-login
    _rebuild_sessions()

    return {'status': 'ok', 'changed': changed}


# ── Error handlers ──
@app.errorhandler(404)
async def not_found(request):
    return {'error': 'not found'}, 404, CORS_HEADERS

@app.errorhandler(500)
async def internal_error(request):
    mem.collect()
    return {'error': 'internal error'}, 500, CORS_HEADERS
