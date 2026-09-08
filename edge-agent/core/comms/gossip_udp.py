import socket
import json
import threading
import time

class GossipNode:
    """Lightweight broadcast mesh running across local UDP ports."""
    def __init__(self, robot_id: str, port: int, peer_ports: list):
        self.robot_id = robot_id
        self.port = port
        self.peer_ports = peer_ports
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('127.0.0.1', self.port))
        self.running = True
        self.received_messages = []
        self.lock = threading.Lock()

        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()

    def _listen_loop(self):
        while self.running:
            try:
                data, _ = self.sock.recvfrom(4096)
                msg = json.loads(data.decode('utf-8'))
                with self.lock:
                    self.received_messages.append(msg)
                    if len(self.received_messages) > 100:
                        self.received_messages.pop(0)
            except Exception:
                break

    def broadcast(self, payload: dict):
        raw = json.dumps(payload).encode('utf-8')
        for peer in self.peer_ports:
            if peer != self.port:
                try:
                    self.sock.sendto(raw, ('127.0.0.1', peer))
                except Exception:
                    pass

    def get_latest(self):
        with self.lock:
            msgs = list(self.received_messages)
            self.received_messages.clear()
            return msgs

    def stop(self):
        self.running = False
        self.sock.close()