import time

jobs    = []
_next_id = 1


def add_job(hour, minute, days, state, mode='solid',
            show_middle_finger=False, message=None):
    global _next_id
    job = {
        'id':                 _next_id,
        'hour':               int(hour),
        'minute':             int(minute),
        'days':               [int(d) for d in days],
        'state':              state,
        'mode':               mode,
        'show_middle_finger': bool(show_middle_finger),
        'message':            message,
        'enabled':            True,
    }
    jobs.append(job)
    _next_id += 1
    return job


def remove_job(job_id):
    global jobs
    before = len(jobs)
    jobs   = [j for j in jobs if j['id'] != int(job_id)]
    return len(jobs) < before


def toggle_job(job_id):
    for j in jobs:
        if j['id'] == int(job_id):
            j['enabled'] = not j['enabled']
            return j
    return None


def get_jobs():
    return jobs

_last_fired = {}  # track {job_id: (hour, minute)} to avoid double-firing

def check_jobs(current_state):
    try:
        now     = time.localtime()
        hour    = now[3]
        minute  = now[4]
        weekday = now[6]
    except Exception as e:
        print(f"Scheduler time error: {e}")
        return None

    for job in jobs:
        try:
            if not job['enabled']:
                continue
            if job['hour'] != hour or job['minute'] != minute:
                # reset fired flag when time moves on
                _last_fired.pop(job['id'], None)
                continue
            if job['days'] and weekday not in job['days']:
                continue
            # already fired this minute?
            if _last_fired.get(job['id']) == (hour, minute):
                continue

            print(job, current_state)

            _last_fired[job['id']] = (hour, minute)
            prev = current_state['state']
            current_state['state']              = job['state']
            current_state['mode']               = job['mode']
            current_state['show_middle_finger'] = job['show_middle_finger']
            current_state['message']            = job['message']
            job['_prev_state'] = prev
            print(f"Scheduler fired job {job['id']} at {hour:02d}:{minute:02d}")
            return job
        except Exception as e:
            print(f"Scheduler job {job.get('id','?')} error: {e}")
    return None

def set_time(year, month, day, hour, minute, second, weekday=0):
    """
    Set the Pico's RTC manually since it has no battery.
    weekday: 0=Mon, 6=Sun
    Call this after WiFi connect via NTP or manual set.
    """
    import machine
    rtc = machine.RTC()
    # MicroPython RTC datetime tuple: (year, month, day, weekday, hour, minute, second, subsecond)
    rtc.datetime((year, month, day, weekday, hour, minute, second, 0))
    print(f"RTC set: {year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}")