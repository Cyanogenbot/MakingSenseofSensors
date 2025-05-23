# Copyright (c) 2021 Mathias Funk
# This software is released under the MIT License.
# http://opensource.org/licenses/mit-license.php

import os
import _thread
import time
import json
import socket
import random
import ubinascii

__author__ = 'matsfunk'


class OOCSI:

    def __init__(self, handle=None, host='localhost', port=4444, callback=None):
        if handle is None or len(handle.strip()) == 0:
            handle = "OOCSIClient_####"
        while "#" in handle:
            handle = handle.replace("#", str(random.randrange(10)), 1)
        self.handle = handle

        self.receivers = {self.handle: [callback]}
        self.calls = {}
        self.services = {}
        self.reconnect = True
        self.connected = False

        # Connect the socket to the port where the server is listening
        self.server_address = (host, port)
        self.log('connecting to %s port %s' % self.server_address)

        # start the connection thread
        _thread.start_new_thread(self.runOOCSIThread, ())

        # block till we are connected
        while not self.connected:
            time.sleep(0.2)

    def init(self):
        try:
            # Create a TCP/IP socket
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect(self.server_address)

            try:
                # Send data
                message = self.handle + '(JSON)'
                self.internalSend(message)

                data = self.sock.recv(1024).decode()
                if data.startswith('{'):
                    self.log('connection established')
                    # re-subscribe for channels
                    for channelName in self.receivers:
                        self.internalSend('subscribe {0}'.format(channelName))
                    self.connected = True
                elif data.startswith('error'):
                    self.log(data)
                    self.reconnect = False

                # run loop as long as we are connected
                while self.connected:
                    self.loop()

            finally:
                pass
        except:
            pass


    def runOOCSIThread(self):
        while self.reconnect:
            self.init()
            if self.reconnect:
                self.log('re-connecting to OOCSI')
                time.sleep(5)

        self.log('closing connection to OOCSI')
        _thread.exit()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop()

    def log(self, message):
        print('[{0}]: {1}'.format(self.handle, message))

    def internalSend(self, msg):
        try:
            self.sock.sendall((msg + '\n').encode())
        except:
            self.connected = False

    def loop(self):
        try:
            data = self.sock.recv(2 * 1024).decode()
            lines = data.split("\n")
            for line in lines:
                if len(data) == 0:
                    self.sock.close()
                    self.connected = False
                elif line.startswith('ping') or line.startswith('.'):
                    self.internalSend('.')
                elif line.startswith('{'):
                    self.receive(json.loads(line))
        except:
            pass

    def receive(self, event):
        sender = event['sender']
        recipient = event['recipient']

        # clean up the event
        del event['recipient']
        del event['sender']
        del event['timestamp']
        if 'data' in event:
            del event['data']

        if '_MESSAGE_HANDLE' in event and event['_MESSAGE_HANDLE'] in self.services:
            service = self.services[event['_MESSAGE_HANDLE']]
            del event['_MESSAGE_HANDLE']
            service(event)
            self.send(sender, event)
            self.receiveChannelEvent(sender, recipient, event)

        else:
            if '_MESSAGE_ID' in event:
                myCall = self.calls[event['_MESSAGE_ID']]
                if myCall['expiration'] > time.time():
                    response = self.calls[event['_MESSAGE_ID']]
                    response['response'] = event
                    del response['expiration']
                    del response['_MESSAGE_ID']
                    del response['response']['_MESSAGE_ID']
                else:
                    del self.calls[event['_MESSAGE_ID']]

            else:
                self.receiveChannelEvent(sender, recipient, event)

    def receiveChannelEvent(self, sender, recipient, event):
        if recipient in self.receivers and self.receivers[recipient] is not None:
            for x in self.receivers[recipient]:
                x(sender, recipient, event)

    def send(self, channelName, data):
        self.internalSend('sendraw {0} {1}'.format(channelName, json.dumps(data)))

    def call(self, channelName, callName, data, timeout=1):
        data['_MESSAGE_HANDLE'] = callName
        data['_MESSAGE_ID'] = self.uuid4()
        self.calls[data['_MESSAGE_ID']] = {'_MESSAGE_HANDLE': callName, '_MESSAGE_ID': data['_MESSAGE_ID'], 'expiration': time.time() + timeout}
        self.send(channelName, data)
        return self.calls[data['_MESSAGE_ID']]

    def callAndWait(self, channelName, callName, data, timeout=1):
        call = self.call(channelName, callName, data, timeout)
        expiration = time.time() + timeout
        while time.time() < expiration:
            time.sleep(0.1)
    if 'response' in call:
        break

    return call

    def register(self, channelName, callName, callback):
        self.services[callName] = callback
        self.internalSend('subscribe {0}'.format(channelName))
        self.log('registered responder on {0} for {1}'.format(channelName, callName))

    def subscribe(self, channelName, f):
        if channelName in self.receivers:
            self.receivers[channelName].append(f)
        else:
            self.receivers[channelName] = [f]
        self.internalSend('subscribe {0}'.format(channelName))
        self.log('subscribed to {0}'.format(channelName))

    def unsubscribe(self, channelName):
        del self.receivers[channelName]
        self.internalSend('unsubscribe {0}'.format(channelName))
        self.log('unsubscribed from {0}'.format(channelName))

    def variable(self, channelName, key):
        return OOCSIVariable(self, channelName, key)

    def stop(self):
        self.reconnect = False
        self.internalSend('quit')
        self.sock.close()
        self.connected = False

    def handleEvent(self, sender, receiver, message):
        {}

    def uuid4(self):
        """Generates a random UUID compliant to RFC 4122 pg.14"""
        random = bytearray(os.urandom(16))
        random[6] = (random[6] & 0x0F) | 0x40
        random[8] = (random[8] & 0x3F) | 0x80
        h = ubinascii.hexlify(random).decode()
        return '-'.join((h[0:8], h[8:12], h[12:16], h[16:20], h[20:32]))

    def returnHandle(self):
        return self.handle

    def heyOOCSI(self, custom_name=None):
        if custom_name is None:
            return (OOCSIDevice(self, self.handle))
        else:
            return (OOCSIDevice(self, custom_name))


class OOCSICall:
    def __init__(self, parent=None):
        self.uuid = parent.uuid4()
        self.expiration = time.time()


class OOCSIVariable:
    def __init__(self, oocsi, channelName, key):
        self.key = key
        self.channel = channelName
        oocsi.subscribe(channelName, self.internalReceiveValue)
        self.oocsi = oocsi
        self.value = None
        self.windowLength = 0
        self.values = []
        self.minvalue = None
        self.maxvalue = None
        self.sigma = None

    def get(self):
        if self.windowLength > 0 and len(self.values) > 0:
            return fsum(self.values)/float(len(self.values))
        else:
            return self.value

    def set(self, value):
        tempvalue = value
        if self.minvalue is not None and tempvalue < self.minvalue:
            tempvalue = self.minvalue
        elif self.maxvalue is not None and tempvalue > self.maxvalue:
            tempvalue = self.maxvalue
        elif self.sigma is not None:
            mean = self.get()
            if mean is not None:
                if abs(mean - tempvalue) > self.sigma:
                    if mean - tempvalue > 0:
                        tempvalue = mean - self.sigma/float(len(self.values))
                    else:
                        tempvalue = mean + self.sigma/float(len(self.values))

        if self.windowLength > 0:
            self.values.append(tempvalue)
            self.values = self.values[-self.windowLength:]
        else:
            self.value = tempvalue
        self.oocsi.send(self.channel, {self.key: value})

    def internalReceiveValue(self, sender, recipient, data):
        if self.key in data:
            tempvalue = data[self.key]
            if self.minvalue is not None and tempvalue < self.minvalue:
                tempvalue = self.minvalue
            elif self.maxvalue is not None and tempvalue > self.maxvalue:
                tempvalue = self.maxvalue
            elif self.sigma is not None:
                mean = self.get()
                if mean is not None:
                    if abs(mean - tempvalue) > self.sigma:
                        if mean - tempvalue > 0:
                            tempvalue = mean - self.sigma/float(len(self.values))
                        else:
                            tempvalue = mean + self.sigma/float(len(self.values))

            if self.windowLength > 0:
                self.values.append(tempvalue)
                self.values = self.values[-self.windowLength:]
            else:
                self.value = tempvalue

    def min(self, minvalue):
        self.minvalue = minvalue
        if self.value < self.minvalue:
            self.value = self.minvalue
        return self

    def max(self, maxvalue):
        self.maxvalue = maxvalue
        if self.value > self.maxvalue:
            self.value = self.maxvalue
        return self

    def smooth(self, windowLength, sigma=None):
        self.windowLength = windowLength
        self.sigma = sigma
        return self


class OOCSIDevice:
    def __init__(self, OOCSI, device_name: str) -> None:
        self._device_name = device_name
        self._device = {self._device_name: {}}
        self._device[self._device_name]["properties"] = {}
        self._device[self._device_name]["properties"]["device_id"] = OOCSI.returnHandle()
        self._device[self._device_name]["components"] = {}
        self._device[self._device_name]["location"] = {}
        self._components = self._device[self._device_name]["components"]
        self._oocsi = OOCSI
        self._oocsi.log(f'Created device {self._device_name}.')

    def addProperty(self, properties: str, propertyValue):
        self._device[self._device_name]["properties"][properties] = propertyValue
        self._oocsi.log(f'Added {properties} to the properties list of device {self._device_name}.')
        return self

    def addLocation(self, location_name: str, latitude: float = 0, longitude: float = 0):
        self._device[self._device_name]["location"][location_name] = [latitude, longitude]
        self._oocsi.log(f'Added {location_name} to the locations list of device {self._device_name}.')
        return self

    def addSensor(self, sensor_name: str, sensor_channel: str, sensor_type: str, sensor_unit: str, sensor_default: float, mode: str = "auto", step: float = None, icon: str = None):
        self._components[sensor_name] = {}
        self._components[sensor_name]["channel_name"] = sensor_channel
        self._components[sensor_name]["type"] = "sensor"
        self._components[sensor_name]["sensor_type"] = sensor_type
        self._components[sensor_name]["unit"] = sensor_unit
        self._components[sensor_name]["value"] = sensor_default
        self._components[sensor_name]["mode"] = mode
        self._components[sensor_name]["step"] = step
        self._components[sensor_name]["icon"] = icon
        self._device[self._device_name]["components"][sensor_name] = self._components[sensor_name]
        self._oocsi.log(f'Added {sensor_name} to the components list of device {self._device_name}.')
        return self

    def addNumber(self, number_name: str, number_channel: str, number_min_max, number_unit: str, number_default: float, icon: str = None):
        self._components[number_name] = {}
        self._components[number_name]["channel_name"] = number_channel
        self._components[number_name]["min_max"] = number_min_max
        self._components[number_name]["type"] = "number"
        self._components[number_name]["unit"] = number_unit
        self._components[number_name]["value"] = number_default
        self._components[number_name]["icon"] = icon
        self._device[self._device_name]["components"][number_name] = self._components[number_name]
        self._oocsi.log(f'Added {number_name} to the components list of device {self._device_name}.')
        return self

    def addBinarySensor(self, sensor_name: str, sensor_channel: str, sensor_type: str, sensor_default: bool = False, icon: str = None):
        self._components[sensor_name] = {}
        self._components[sensor_name]["channel_name"] = sensor_channel
        self._components[sensor_name]["type"] = "binary_sensor"
        self._components[sensor_name]["sensor_type"] = sensor_type
        self._components[sensor_name]["state"] = sensor_default
        self._components[sensor_name]["icon"] = icon
        self._device[self._device_name]["components"][sensor_name] = self._components[sensor_name]
        self._oocsi.log(f'Added {sensor_name} to the components list of device {self._device_name}.')
        return self

    def addSwitch(self, switch_name: str, switch_channel: str, switch_default: bool = False, icon: str = None):
        self._components[switch_name] = {}
        self._components[switch_name]["channel_name"] = switch_channel
        self._components[switch_name]["type"] = "switch"
        self._components[switch_name]["state"] = switch_default
        self._components[switch_name]["icon"] = icon
        self._device[self._device_name]["components"][switch_name] = self._components[switch_name]
        self._oocsi.log(f'Added {switch_name} to the components list of device {self._device_name}.')
        return self

    def addLight(self, light_name: str, light_channel: str, led_type: str, spectrum, light_default_state: bool = False, light_default_brightness: int = 0, mired_min_max = None, icon: str = None):
        SPECTRUM = ["WHITE", "CCT", "RGB"]
        LEDTYPE = ["RGB", "RGBW", "RGBWW", "CCT", "DIMMABLE", "ONOFF"]

        self._components[light_name] = {}
        if led_type in LEDTYPE:
            if spectrum in SPECTRUM:
                self._components[light_name]["spectrum"] = spectrum
            else:
                self._oocsi.log(f'error, {light_name} spectrum does not exist.')
                pass
        else:
            self._oocsi.log(f'error, {light_name} ledtype does not exist.')
            pass

        self._components[light_name]["channel_name"] = light_channel
        self._components[light_name]["type"] = "light"
        self._components[light_name]["ledType"] = led_type
        self._components[light_name]["spectrum"] = spectrum
        self._components[light_name]["min_max"] = mired_min_max
        self._components[light_name]["state"] = light_default_state
        self._components[light_name]["brightness"] = light_default_brightness
        self._components[light_name]["icon"] = icon
        self._device[self._device_name]["components"][light_name] = self._components[light_name]
        self._oocsi.log(f'Added {light_name} to the components list of device {self._device_name}.')
        return self

    def submit(self):
        data = self._device
        self._oocsi.internalSend('sendraw {0} {1}'.format("heyOOCSI!", json.dumps(data)))
        self._oocsi.log(f'Sent heyOOCSI! message for device {self._device_name}.')

    def sayHi(self):
        self.submit()