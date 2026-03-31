"""
Centralised memory management for the Pico LCD controller.
Import this everywhere instead of calling gc directly.
"""
import gc
import micropython

def collect():
    """Full GC collect — call between major operations."""
    gc.collect()

def free():
    """Return free RAM in bytes."""
    gc.collect()
    return gc.mem_free()

def check(needed, label='operation'):
    """
    Raise MemoryError if not enough RAM available.
    Tries a collect first in case that frees enough.
    """
    gc.collect()
    available = gc.mem_free()
    if available < needed + 20000:  # always keep 20KB headroom
        raise MemoryError(
            f"{label} needs {needed}B but only {available}B free"
        )
    return available

def report(label=''):
    """Print current RAM usage."""
    gc.collect()
    free_ram  = gc.mem_free()
    alloc_ram = gc.mem_alloc()
    total     = free_ram + alloc_ram
    pct       = int((alloc_ram / total) * 100)
    print(f"RAM [{label}] free={free_ram} alloc={alloc_ram} used={pct}%")
    return free_ram

def release(*args):
    """
    Set any number of variables to None and collect.
    Usage: release(big_bytearray, large_string)
    Returns None so you can do: myvar = release(myvar)
    """
    del args
    gc.collect()
    return None

def defrag():
    """
    Attempt to defragment the heap by forcing multiple GC cycles
    and temporarily allocating/freeing a large block to compact memory.
    Returns free RAM after defrag.
    """
    import gc

    # Multiple collect passes
    for _ in range(5):
        gc.collect()

    free1 = gc.mem_free()
    print(f"Defrag: free={free1}")

    # Try to allocate progressively smaller blocks to find
    # the largest contiguous chunk and force compaction
    for size in (180000, 150000, 130000, 115200):
        try:
            tmp = bytearray(size)
            del tmp
            gc.collect()
            break
        except MemoryError:
            gc.collect()
            continue

    for _ in range(3):
        gc.collect()

    free2 = gc.mem_free()
    print(f"Defrag done: free={free2} (gained {free2-free1})")
    return free2

def emergency_free():
    """
    Nuclear option — collect multiple times and run micropython emergency
    allocator. Use when about to do a large allocation.
    """
    gc.collect()
    gc.collect()
    gc.collect()
    try:
        micropython.mem_info(1)  # prints detailed heap info
    except Exception:
        pass
    return gc.mem_free()