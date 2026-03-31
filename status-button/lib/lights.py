from machine import Pin, SPI
import gc9a01py as gc9a01
import time

spi = SPI(0, baudrate=20000000, sck=Pin(18), mosi=Pin(19))

tft = gc9a01.GC9A01(
    spi,
    dc=Pin(21, Pin.OUT),
    cs=Pin(17, Pin.OUT),
    reset=Pin(15, Pin.OUT),
    backlight=Pin(14, Pin.OUT),
    rotation=0
)

button = Pin(13, Pin.IN, Pin.PULL_UP)

colours = [
    gc9a01.RED,
    gc9a01.MAGENTA,
    gc9a01.GREEN,
]
index = 0
tft.fill(colours[index])

last_state = 1

while True:
    state = button.value()
    if state == 0 and last_state == 1:
        index = (index + 1) % len(colours)
        tft.fill(colours[index])
        time.sleep_ms(50)
    last_state = state
    time.sleep_ms(10)