from machine import I2C, Pin, SoftI2C
import urtc as uRTC
import os
import urequests
import time
import network
import dht
import neopixel
import secrets

from oocsi import OOCSI

led = neopixel.NeoPixel(Pin(21), 1)

# Variable to check if device is uploading
upload_in_progress = False

# Values to be stored in a secrets.py file
# api_token = "YOUR_API_TOKEN"
# device_id = "YOUR_DEVICE_ID"
# dataset_id = 123456
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
    # Function to start upload on buttonpre
    # Ignore if upload already in progress
    if hasattr(button_pressed, 'upload_in_progress') and button_pressed.upload_in_progress:
        print('*** Upload already in progress, ignoring button press')
        return
    
    # Set indicator light
    led[0] = (0, 20, 20)
    led.write()
    
    # Set upload flag
    upload_in_progress = True
    
    try:
        if wlan.isconnected() and os.stat(csvfilename)[6] > 77:
            # If wifi is connected and file contains at least 2 values, send values
            try:
                # Upload values to DF
                print('*** Starting upload...')
                with open(csvfilename, 'r') as csvfile:
                    csv_content = csvfile.read()
                
                # Set a timeout to prevent hanging
                response = urequests.post(url, headers=headers, data=csv_content)

                print('*** DATAFOUNDRY: Status code:', response.status_code)
                print('*** DATAFOUNDRY: Response:', response.text)
                
                # Only clear the file if upload was successful
                if response.status_code in (200, 201, 202):
                    # Remove values (except header) from CSV
                    with open(csvfilename, "w") as resetfile:
                        resetfile.write("ts,humidity,temperature\n")
                    
                    # Blink green trice
                    blink(3, g=20)
                else:
                    print('*** Upload failed with status code:', response.status_code)
                    blink(2, r=20, g=20)  # Yellow blink for HTTP error
                    
            # If anything goes wrong
            except Exception as e:
                # Print a simple error message and blink red trice
                print('*** Error during upload:', e)
                blink(3, r=20)
                
        elif wlan.isconnected():
            # Blink once if wifi is connected but file is not big enough
            print('*** Error: NOT ENOUGH DATA, PLEASE WAIT')
            blink(1, r=20)
        else:
            # Blink twice if wifi is not connected
            print('*** Error: WIFI NOT CONNECTED')
            blink(2, r=20)
    finally:
        # Always clear the upload flag when done
        upload_in_progress = False


def blink(loop,r=0,g=0,b=0):
    # Simple blink function
    for i in range(loop):
        led[0] = (g, r, b)
        led.write()
        time.sleep(0.2)
        led[0] = (int(g/10), int(r/10), int(b/10))
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
    led.fill((0, 20, 0))  # Indicate trying to connect
    led.write()
    
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    if not wlan.isconnected():
        print('*** WIFI: Connecting to network...')
        # replace these with your WIFI name and password
        wlan.connect(secrets.ssid, secrets.wifipass)
        
        timeout = 10  # Timeout after 10 seconds
        start_time = time.time()
        
        # Check if the Wi-Fi is connected within the timeout period
        while not wlan.isconnected():
            if time.time() - start_time > timeout:
                break  # Exit the loop if the connection attempt times out
            time.sleep(0.1)  # Small delay to prevent hogging the CPU
            
            # Optional: You can add more feedback, like blinking the LED, to show progress

    if wlan.isconnected():
        print("*** WIFI: Connected")
        led.fill((0, 0, 20))  # Change LED to indicate successful connection
    else:
        print("*** WIFI: Couldnt connect in time.")
        led.fill((20, 0, 0))  # Change LED to indicate failure
    
    led.write()

#---------------------------------------------------------------------------

# Connect to wifi
connectWifi()

# Define the upload button and setup interrupt
KEY = Pin(0,Pin.IN,Pin.PULL_UP) 
KEY.irq(trigger=Pin.IRQ_RISING, handler=button_pressed)
time.sleep(2)

# Connect to RTC, Blink pink once if not found
sda_pin=Pin(33)
scl_pin=Pin(34)
i2c = I2C(scl=scl_pin, sda=sda_pin)
try:
    ds = uRTC.DS3231(i2c)
    ds.datetime()
    print("*** RTC Connected")
except Exception as e:
    print('*** RTC Error, type:',e)
    blink(1,r=20, b=20)


# Connect to DHT11 sensor, Blink pink twice if not found
try:
    sensor = dht.DHT11(Pin(6))
    sensor.measure()
    print("*** DHT: Connected")
except Exception as e:
    print("*** DHT: Error, type:",e)
    blink(2,r=20, b=20)


if wlan.isconnected():
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
        print("*** WIFI: Connected")
        led.fill((20, 0, 0))
        led.write()
        
    elif not wlan.isconnected():
        print("*** WIFI: Disconnected")
        led.fill((0, 20, 0))
        led.write()

    # Open CSV file
    with open(csvfilename, "a") as file:

        # Read sensor value
        sensor.measure()
        temperature = sensor.temperature()
        humidity = sensor.humidity()

        # Format and write data to CSV
        timestamp =  "{}-{}-{}T{}:{}:{}" .format(ds.datetime()[0],ds.datetime()[1],ds.datetime()[2],ds.datetime()[4], ds.datetime()[5],ds.datetime()[6])
        data_line = "{},{},{}\n".format(timestamp, humidity, temperature)
        file.write(data_line)
        print("Saved data at: {}, Humidity was {}%, Temperature was {}{}".format(timestamp, humidity, temperature,chr(176)))
        file.close()
        
        # Wait a bit between readings

    # Wait another minute
    time.sleep(60)
