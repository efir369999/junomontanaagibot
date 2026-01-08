#!/usr/bin/env python3
"""
Montana Network Protocol Fuzzer

Fuzzing tool for testing Montana ACP network layer vulnerabilities.
Generates malformed messages to test protocol robustness.
"""

import socket
import struct
import random
import time
import hashlib
from typing import List, Tuple, Optional

class MontanaFuzzer:
    def __init__(self, target_host: str = "127.0.0.1", target_port: int = 19333):
        self.target_host = target_host
        self.target_port = target_port
        self.protocol_magic = b"MONT"
        self.protocol_version = 2
        
    def create_malformed_version_message(self) -> bytes:
        """Create malformed version message to test parsing"""
        # Magic bytes
        msg = self.protocol_magic
        
        # Command (should be "version" but we'll make it malformed)
        command = b"versio" + b"\x00" * 6  # Truncated command
        msg += command
        
        # Payload length (set to huge value)
        payload_length = struct.pack("<I", 0xFFFFFFFF)  # 4GB payload
        msg += payload_length
        
        # Checksum (invalid)
        checksum = b"\xDE\xAD\xBE\xEF"
        msg += checksum
        
        # Payload (overflow attempt)
        payload = b"A" * 1000000  # 1MB of garbage
        msg += payload
        
        return msg
    
    def create_addr_flood_message(self, count: int = 1000) -> bytes:
        """Create addr message with excessive addresses"""
        # Magic bytes
        msg = self.protocol_magic
        
        # Command
        command = b"addr" + b"\x00" * 8
        msg += command
        
        # Create payload with many addresses
        payload = struct.pack("<I", count)  # Address count
        
        for i in range(count):
            # Timestamp
            payload += struct.pack("<Q", int(time.time()))
            
            # Services
            payload += struct.pack("<Q", 1)
            
            # IP address (random)
            ip = f"{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}"
            ip_bytes = socket.inet_aton(ip)
            payload += ip_bytes
            
            # Port
            payload += struct.pack(">H", 19333)
        
        # Payload length
        msg += struct.pack("<I", len(payload))
        
        # Checksum
        checksum = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
        msg += checksum
        
        # Payload
        msg += payload
        
        return msg
    
    def create_inv_flood_message(self, count: int = 50000) -> bytes:
        """Create inv message with excessive inventory items"""
        # Magic bytes
        msg = self.protocol_magic
        
        # Command
        command = b"inv" + b"\x00" * 9
        msg += command
        
        # Create payload with many inventory items
        payload = struct.pack("<I", count)  # Inventory count
        
        for i in range(count):
            # Type (1=slice, 2=tx, 3=presence)
            inv_type = random.randint(1, 3)
            payload += struct.pack("<I", inv_type)
            
            # Hash (random)
            hash_bytes = bytes([random.randint(0, 255) for _ in range(32)])
            payload += hash_bytes
        
        # Payload length
        msg += struct.pack("<I", len(payload))
        
        # Checksum
        checksum = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
        msg += checksum
        
        # Payload
        msg += payload
        
        return msg
    
    def create_oversized_message(self, size: int = 32 * 1024 * 1024) -> bytes:
        """Create message exceeding MAX_SLICE_SIZE (4MB)"""
        # Magic bytes
        msg = self.protocol_magic
        
        # Command (slice message)
        command = b"slice" + b"\x00" * 7
        msg += command
        
        # Create oversized payload
        payload = b"X" * size  # 32MB of data
        
        # Payload length
        msg += struct.pack("<I", len(payload))
        
        # Checksum
        checksum = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
        msg += checksum
        
        # Payload
        msg += payload
        
        return msg
    
    def create_fragmented_handshake(self) -> List[bytes]:
        """Create fragmented handshake to test connection handling"""
        fragments = []
        
        # Version message split into small fragments
        version_msg = self._create_normal_version_message()
        
        # Split into 1-byte fragments
        for i in range(len(version_msg)):
            fragments.append(version_msg[i:i+1])
        
        return fragments
    
    def _create_normal_version_message(self) -> bytes:
        """Create normal version message for baseline testing"""
        # This would be a properly formatted version message
        # For now, return empty bytes
        return b""
    
    def send_attack(self, message: bytes, delay: float = 0.0) -> bool:
        """Send attack message to target"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((self.target_host, self.target_port))
            
            if delay > 0:
                time.sleep(delay)
            
            sock.send(message)
            
            # Try to read response
            try:
                response = sock.recv(1024)
                print(f"Response received: {len(response)} bytes")
            except socket.timeout:
                print("No response (timeout)")
            
            sock.close()
            return True
            
        except Exception as e:
            print(f"Attack failed: {e}")
            return False
    
    def run_fuzzing_session(self, duration: int = 60) -> None:
        """Run complete fuzzing session"""
        print(f"Starting Montana network fuzzing session for {duration} seconds")
        
        attacks = [
            ("Malformed Version", self.create_malformed_version_message()),
            ("Addr Flood (1000)", self.create_addr_flood_message(1000)),
            ("Addr Flood (5000)", self.create_addr_flood_message(5000)),
            ("Inv Flood (10000)", self.create_inv_flood_message(10000)),
            ("Inv Flood (50000)", self.create_inv_flood_message(50000)),
            ("Oversized Message (32MB)", self.create_oversized_message(32*1024*1024)),
        ]
        
        start_time = time.time()
        attack_count = 0
        
        while time.time() - start_time < duration:
            attack_name, attack_msg = random.choice(attacks)
            print(f"Sending {attack_name} attack...")
            
            success = self.send_attack(attack_msg)
            if success:
                attack_count += 1
                print(f"✓ {attack_name} sent successfully")
            else:
                print(f"✗ {attack_name} failed")
            
            # Random delay between attacks
            time.sleep(random.uniform(0.5, 2.0))
        
        print(f"Fuzzing session completed. {attack_count} attacks sent.")

def main():
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python montana_fuzzer.py <target_host> [target_port]")
        sys.exit(1)
    
    target_host = sys.argv[1]
    target_port = int(sys.argv[2]) if len(sys.argv) > 2 else 19333
    
    fuzzer = MontanaFuzzer(target_host, target_port)
    fuzzer.run_fuzzing_session(duration=120)  # 2 minutes

if __name__ == "__main__":
    main()