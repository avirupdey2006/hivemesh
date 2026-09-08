import paho.mqtt.client as mqtt
import json
import logging

class RobustMQTTClient:
    def __init__(self, client_id: str, host: str = "127.0.0.1", port: int = 1883):
        self.client_id = client_id
        self.host = host
        self.port = port
        self.client = mqtt.Client(client_id=client_id)
        self.is_connected = False
        self.callbacks = {}

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.is_connected = True
            for topic in self.callbacks:
                self.client.subscribe(topic)
        else:
            self.is_connected = False

    def _on_disconnect(self, client, userdata, rc):
        self.is_connected = False

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        try:
            payload = json.loads(msg.payload.decode('utf-8'))
            if topic in self.callbacks:
                self.callbacks[topic](payload)
            elif "#" in self.callbacks:
                self.callbacks["#"](topic, payload)
        except Exception:
            pass

    def subscribe(self, topic: str, cb):
        self.callbacks[topic] = cb
        if self.is_connected:
            self.client.subscribe(topic)

    def publish(self, topic: str, payload: dict):
        if self.is_connected:
            self.client.publish(topic, json.dumps(payload))

    def start(self):
        try:
            self.client.connect(self.host, self.port, keepalive=5)
            self.client.loop_start()
        except Exception:
            self.is_connected = False