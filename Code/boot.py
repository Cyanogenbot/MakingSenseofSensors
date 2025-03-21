from machine import I2C, Pin, SoftI2C
import uRTC
import os
import urequests
import time
import network
import dht
import neopixel
import secrets

from OOCSI import OOCSI

led = neopixel.NeoPixel(Pin(38), 1)

# Values to be stored in a secrets file
# api_tok en = "YOUR_API_TOKEN"
# device_id = "YOUR_DEVICE_ID"
# dataset_id = 23463
# ssid = 'YOUR_WIFI_SSID'
# wifipass = 'YOUR_WIFI_PASSWORD'

csvfilename = "sensor_data.csv"

# Upload destination and header
url = 'https://data.id.tue.nl/datasets/ts/logFile/{}'.format(secrets.dataset_id)
headers = {
    "Content-Type": "text/plain",
    "api_token": secrets.api_token,
    "device_id": secrets.device_id    # Replace with your actual device ID
}



def button_pressed(pin):
    # Function to start upload on buttonpress
    led[0] = (20, 0, 20)
    led.write()
    if wlan.isconnected() and os.stat(csvfilename)[6] > 77:
        # If wifi is connected and file is contains 2 values, send values
        try:
            # Upload values to DF
            with open(csvfilename, 'r') as csvfile:
                csv_content = csvfile.read()
                response = urequests.post(url, headers=headers,data=csv_content)
                print('Status code:', response.status_code)
                print('Response:', response.text)
                csvfile.close()

                # Remove values (except header) from CSV
            with open(csvfilename, "w") as resetfile:
                resetfile.write("ts,humidity,temperature\n")
                resetfile.close()

            # Blink green trice
            blink(3,g=20)

        # If anything goes wrong
        except Exception as e:
            # Print a simple error message and blink red trice
            print('**** Error:', e)
            blink(3,r=20)

    elif wlan.isconnected():
        # Blink once if wifi is connected but file is not big enough
        blink(1,r=20)

    else:
        # Blink twice if wifi is not connected
        blink(2,r=20)


def blink(loop,r=0,g=0,b=0):
    # Simple blink function
    for i in range(loop):
        led[0] = (r, g, b)
        led.write()
        time.sleep(0.2)
        led[0] = (int(r/10), int(g/10), int(b/10))
        led.write()
        time.sleep(0.2)


def receiveEvent(sender, recipient, event):
    # When OOCSI message is received, update the RTC and disconnect
    print('from ', sender, ' -> ', event)
    if ("datetime") in event:
        print("found")
        OOCSITIME = uRTC.datetime_tuple(year=event["y"], month=event["M"], day=event["d"], hour=event["h"], minute=event["m"], second=event["s"])
        print(event["y"])
        ds.datetime(OOCSITIME)
        if 'timechannel' in o.receivers:
            o.unsubscribe('timechannel')
            o.stop()

# Configure Wifi
wlan = network.WLAN(network.STA_IF)
print("MAC ADDRESS=",wlan.config('mac').hex())

def connectWifi():
    # Wifi Connection function
    led[0] = (20, 0, 0)
    led.write()
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print('connecting to network...')
        # replace these by your WIFI name and password
        wlan.connect(secrets.ssid, secrets.wifipass)
        while not wlan.isconnected():
            led.write()
            pass
    led[0] = (0, 0, 20)
    led.write()
    # print('network config:', wlan.ifconfig())

#---------------------------------------------------------------------------

# Connect to wifi
connectWifi()

# Define the upload button and setup interrupt
button = Pin(0, Pin.IN, Pin.PULL_UP)
button.irq(trigger=Pin.IRQ_FALLING, handler=button_pressed)

# Connect to RTC, Blink pink twice if not found
sda_pin=Pin(41)
scl_pin=Pin(42)
i2c = I2C(scl=scl_pin, sda=sda_pin, freq=200000)
try:
    ds = uRTC.DS1307(i2c)
    ds.datetime()
except Exception as e:
    print('Error type:',e)
    blink(1,r=20, b=20)


# Connect to DHT11 sensor, Blink pink twice if not found
try:
    sensor = dht.DHT11(Pin(6), Pin.INPUT,Pin.PULL_UP)
    sensor.measure()
except Exception as e:
    print('Error type:',e)
    blink(2,r=20, b=20)

# Connect to OOCSI server to sync clock
o = OOCSI('msos/example/MicroPython_receiver_###', 'hello.oocsi.net')
o.subscribe('timechannel', receiveEvent)

# Setup file, and create one if it doesnt exist yet
file_exists = csvfilename in os.listdir()
with open(csvfilename, "a") as file:
    # Write header only if file is new
    if not file_exists:
        file.write("ts,humidity,temperature\n")
        file.close()

# Loop
while True:

    # Turn on the LED when connected to wifi
    if wlan.isconnected():
        led[0] = (0, 10, 0)
        led.write()
    else:
        led[0] = (10, 0, 0)
        led.write()

    # Open CSV file
    with open(csvfilename, "a") as file:

        # Read sensor value
        sensor.measure()
        temperature = sensor.temperature()
        humidity = sensor.humidity()

        # Format and write data to CSV
        timestamp =  "{}-{}-{}T{}:{}:{}" .format(ds.datetime()[2],ds.datetime()[1],ds.datetime()[0],ds.datetime()[4], ds.datetime()[5],ds.datetime()[6])
        data_line = "{},{},{}\n".format(timestamp, humidity, temperature)
        file.write(data_line)
        print("Saved data at: {}, Humidity was {}%, Temperature was {}{}".format(timestamp, humidity, temperature,chr(176)))
        file.close()
        # Wait a bit between readings

    # Wait another minute
    time.sleep(60)