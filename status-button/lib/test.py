from RPLCD.gpio import CharLCD
import RPi.GPIO as GPIO

lcd = CharLCD(
    numbering_mode=GPIO.BCM,
    cols=16, rows=2,
    pin_rs=25, pin_e=24,
    pins_data=[23, 17, 27, 22],
)

# Each number is a row of 5 pixels expressed as a byte
# e.g. 0b01010 = 10 = pixels at positions 2 and 4

heart = (
    0b01010,
    0b11111,
    0b11111,
    0b01110,
    0b00100,
    0b00000,
    0b00000,
    0b00000,
)

bell = (
    0b00100,
    0b01110,
    0b01110,
    0b11111,
    0b11111,
    0b00100,
    0b00000,
    0b00000,
)

# Full block — useful for progress bars
full_block = (
    0b11111,
    0b11111,
    0b11111,
    0b11111,
    0b11111,
    0b11111,
    0b11111,
    0b11111,
)

# Load characters into slots 0, 1, 2
lcd.create_char(0, heart)
lcd.create_char(1, bell)
lcd.create_char(2, full_block)

# Write them using \x00, \x01, \x02 etc.
lcd.clear()
lcd.write_string('Hello \x00 World!')   # heart in the middle
lcd.cursor_pos = (1, 0)
lcd.write_string('\x01 You have mail')  # bell at the start