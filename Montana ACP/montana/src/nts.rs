//! NTS (Network Time Security) implementation per RFC 8915
//!
//! Two-phase protocol:
//! 1. NTS-KE: Key Exchange over TLS (port 4460) with ALPN "ntske/1"
//! 2. NTS-protected NTP queries (port 123)

use aes_siv::aead::{Aead, KeyInit};
use aes_siv::Aes128SivAead;
use openssl::ssl::{SslConnector, SslMethod, SslVerifyMode};
use std::io::{Read, Write};
use std::net::{TcpStream, UdpSocket};
use std::time::Duration;
use tracing::debug;

/// NTS-KE record types (RFC 8915 Section 4)
const NTS_KE_END_OF_MESSAGE: u16 = 0;
const NTS_KE_NEXT_PROTOCOL: u16 = 1;
const NTS_KE_ERROR: u16 = 2;
const NTS_KE_WARNING: u16 = 3;
const NTS_KE_AEAD_ALGORITHM: u16 = 4;
const NTS_KE_NEW_COOKIE: u16 = 5;
const NTS_KE_SERVER: u16 = 6;
const NTS_KE_PORT: u16 = 7;

/// NTP protocol ID for NTS-KE
const NTS_KE_PROTOCOL_NTP: u16 = 0;

/// AEAD algorithm: AEAD_AES_SIV_CMAC_256 (RFC 8915 Section 5.1)
const AEAD_AES_SIV_CMAC_256: u16 = 15;

/// NTS extension field types (RFC 8915 Section 5)
const NTS_EXT_UNIQUE_ID: u16 = 0x0104;
const NTS_EXT_COOKIE: u16 = 0x0204;
const NTS_EXT_AUTH_AND_ENC: u16 = 0x0404;

/// NTS-KE default port
const NTS_KE_PORT_DEFAULT: u16 = 4460;

/// NTS session data from key exchange
#[derive(Clone)]
pub struct NtsSession {
    pub server: String,
    pub port: u16,
    pub cookies: Vec<Vec<u8>>,
    pub c2s_key: [u8; 32],
    pub s2c_key: [u8; 32],
}

/// Query NTS server and get timestamp
pub async fn query_nts_server(server: &str) -> Option<u64> {
    let server = server.to_string();

    // Run blocking OpenSSL in spawn_blocking
    tokio::task::spawn_blocking(move || {
        // Phase 1: NTS-KE
        let session = nts_ke_handshake_sync(&server)?;

        // Phase 2: NTS-protected NTP query
        nts_ntp_query_sync(&session)
    })
    .await
    .ok()?
}

/// NTS-KE handshake (RFC 8915 Section 4) - synchronous
fn nts_ke_handshake_sync(server: &str) -> Option<NtsSession> {
    let ke_server = format!("{}:{}", server, NTS_KE_PORT_DEFAULT);

    // Build SSL connector with ALPN
    let mut builder = SslConnector::builder(SslMethod::tls()).ok()?;
    builder.set_verify(SslVerifyMode::PEER);
    builder.set_alpn_protos(b"\x07ntske/1").ok()?;
    let connector = builder.build();

    // Resolve hostname and connect with timeout
    use std::net::ToSocketAddrs;
    let addr = ke_server.to_socket_addrs().ok()?.next()?;
    let stream = TcpStream::connect_timeout(&addr, Duration::from_secs(10)).ok()?;
    stream.set_read_timeout(Some(Duration::from_secs(10))).ok()?;
    stream.set_write_timeout(Some(Duration::from_secs(10))).ok()?;

    let mut ssl_stream = match connector.connect(server, stream) {
        Ok(s) => s,
        Err(_) => return None,
    };

    // Verify ALPN was negotiated
    let alpn = ssl_stream.ssl().selected_alpn_protocol();
    if alpn != Some(b"ntske/1") {
        return None;
    }

    debug!("NTS-KE TLS ok: {} (ALPN: ntske/1)", server);

    // Build and send NTS-KE request
    let request = build_nts_ke_request();
    if ssl_stream.write_all(&request).is_err() {
        return None;
    }
    let _ = ssl_stream.flush();

    // Read response
    let mut response = vec![0u8; 4096];
    let n = match ssl_stream.read(&mut response) {
        Ok(n) if n > 0 => {
            debug!("NTS-KE got {} bytes from {}", n, server);
            n
        }
        Ok(_) => return None,
        Err(_) => return None,
    };
    response.truncate(n);

    // Export keys using TLS exporter (RFC 8915 Section 4.2)
    let (c2s_key, s2c_key) = export_keys_openssl(&ssl_stream)?;

    // Parse response
    let session = parse_nts_ke_response(&response, server, c2s_key, s2c_key)?;
    debug!("NTS-KE session ok: {} (cookies: {})", server, session.cookies.len());

    Some(session)
}

/// Export TLS keys for NTS using OpenSSL (RFC 8915 Section 4.2)
fn export_keys_openssl(ssl_stream: &openssl::ssl::SslStream<TcpStream>) -> Option<([u8; 32], [u8; 32])> {
    let ssl = ssl_stream.ssl();

    // Labels per RFC 8915 (as strings for OpenSSL API)
    let c2s_label = "EXPORTER-network-time-security/1";
    let s2c_label = "EXPORTER-network-time-security/2";

    // Context is AEAD algorithm ID (2 bytes)
    let context = AEAD_AES_SIV_CMAC_256.to_be_bytes();

    let mut c2s_key = [0u8; 32];
    let mut s2c_key = [0u8; 32];

    ssl.export_keying_material(&mut c2s_key, c2s_label, Some(&context)).ok()?;
    ssl.export_keying_material(&mut s2c_key, s2c_label, Some(&context)).ok()?;

    Some((c2s_key, s2c_key))
}

/// Build NTS-KE request message
fn build_nts_ke_request() -> Vec<u8> {
    let mut msg = Vec::new();

    // Next Protocol Negotiation: NTPv4
    append_nts_ke_record(
        &mut msg,
        NTS_KE_NEXT_PROTOCOL,
        &NTS_KE_PROTOCOL_NTP.to_be_bytes(),
    );

    // AEAD Algorithm: AEAD_AES_SIV_CMAC_256
    append_nts_ke_record(
        &mut msg,
        NTS_KE_AEAD_ALGORITHM,
        &AEAD_AES_SIV_CMAC_256.to_be_bytes(),
    );

    // End of Message
    append_nts_ke_record(&mut msg, NTS_KE_END_OF_MESSAGE, &[]);

    msg
}

/// Append NTS-KE record with critical bit set
fn append_nts_ke_record(msg: &mut Vec<u8>, record_type: u16, body: &[u8]) {
    // Critical bit (0x8000) set for all mandatory records
    msg.extend_from_slice(&(0x8000 | record_type).to_be_bytes());
    msg.extend_from_slice(&(body.len() as u16).to_be_bytes());
    msg.extend_from_slice(body);
}

/// Parse NTS-KE response
fn parse_nts_ke_response(
    data: &[u8],
    server: &str,
    c2s_key: [u8; 32],
    s2c_key: [u8; 32],
) -> Option<NtsSession> {
    let mut cookies = Vec::new();
    let mut ntp_server = server.to_string();
    let mut ntp_port = 123u16;
    let mut got_protocol = false;
    let mut got_aead = false;

    let mut pos = 0;
    while pos + 4 <= data.len() {
        let type_and_critical = u16::from_be_bytes([data[pos], data[pos + 1]]);
        let record_type = type_and_critical & 0x7FFF;
        let length = u16::from_be_bytes([data[pos + 2], data[pos + 3]]) as usize;
        pos += 4;

        if pos + length > data.len() {
            break;
        }

        let body = &data[pos..pos + length];

        match record_type {
            NTS_KE_END_OF_MESSAGE => break,
            NTS_KE_NEXT_PROTOCOL => {
                if length >= 2 {
                    let protocol = u16::from_be_bytes([body[0], body[1]]);
                    if protocol == NTS_KE_PROTOCOL_NTP {
                        got_protocol = true;
                    }
                }
            }
            NTS_KE_ERROR => return None,
            NTS_KE_WARNING => {
                debug!("NTS-KE warning from {}", server);
            }
            NTS_KE_AEAD_ALGORITHM => {
                if length >= 2 {
                    let algo = u16::from_be_bytes([body[0], body[1]]);
                    if algo == AEAD_AES_SIV_CMAC_256 {
                        got_aead = true;
                    }
                }
            }
            NTS_KE_NEW_COOKIE => {
                cookies.push(body.to_vec());
            }
            NTS_KE_SERVER => {
                if let Ok(s) = std::str::from_utf8(body) {
                    ntp_server = s.to_string();
                }
            }
            NTS_KE_PORT => {
                if length >= 2 {
                    ntp_port = u16::from_be_bytes([body[0], body[1]]);
                }
            }
            _ => {}
        }

        pos += length;
    }

    if !got_protocol || !got_aead || cookies.is_empty() {
        return None;
    }

    Some(NtsSession {
        server: ntp_server,
        port: ntp_port,
        cookies,
        c2s_key,
        s2c_key,
    })
}

/// NTS-protected NTP query (RFC 8915 Section 5) - synchronous
fn nts_ntp_query_sync(session: &NtsSession) -> Option<u64> {
    use std::net::ToSocketAddrs;

    let addr_str = format!("{}:{}", session.server, session.port);

    // Resolve hostname for UDP
    let addr = addr_str.to_socket_addrs().ok()?.next()?;

    let socket = UdpSocket::bind("0.0.0.0:0").ok()?;
    socket.set_read_timeout(Some(Duration::from_secs(5))).ok()?;
    socket.set_write_timeout(Some(Duration::from_secs(5))).ok()?;
    socket.connect(addr).ok()?;

    // Build NTS-protected NTP request
    let cookie = session.cookies.first()?;
    let request = build_nts_ntp_request(cookie, &session.c2s_key)?;
    socket.send(&request).ok()?;

    let mut response = [0u8; 1024];
    let n = socket.recv(&mut response).ok()?;

    debug!("NTS NTP got {} bytes from {}", n, addr);

    // Parse and verify NTS-protected NTP response
    parse_nts_ntp_response(&response[..n], &session.s2c_key)
}

/// Build NTS-protected NTP request
fn build_nts_ntp_request(cookie: &[u8], c2s_key: &[u8; 32]) -> Option<Vec<u8>> {
    let mut packet = Vec::with_capacity(256);

    // NTP header (48 bytes)
    // LI=0, VN=4, Mode=3 (client)
    packet.push(0x23);  // 00 100 011

    // Stratum, Poll, Precision (zeros for client)
    packet.extend_from_slice(&[0, 0, 0]);

    // Root Delay, Root Dispersion (8 bytes)
    packet.extend_from_slice(&[0u8; 8]);

    // Reference ID (4 bytes)
    packet.extend_from_slice(&[0u8; 4]);

    // Reference Timestamp (8 bytes)
    packet.extend_from_slice(&[0u8; 8]);

    // Origin Timestamp (8 bytes)
    packet.extend_from_slice(&[0u8; 8]);

    // Receive Timestamp (8 bytes)
    packet.extend_from_slice(&[0u8; 8]);

    // Transmit Timestamp (8 bytes) - current time
    // NTP timestamp: 32-bit seconds since 1900 + 32-bit fraction
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap();
    let ntp_secs = (now.as_secs() + 2208988800) as u32; // Unix to NTP epoch, 32-bit
    let ntp_frac = ((now.subsec_nanos() as u64) << 32) / 1_000_000_000;
    packet.extend_from_slice(&ntp_secs.to_be_bytes());  // 4 bytes
    packet.extend_from_slice(&(ntp_frac as u32).to_be_bytes());  // 4 bytes

    // Extension fields

    // Unique Identifier (random, for replay protection)
    let mut unique_id = [0u8; 32];
    getrandom::getrandom(&mut unique_id).ok()?;
    add_extension_field(&mut packet, NTS_EXT_UNIQUE_ID, &unique_id);

    // Cookie
    add_extension_field(&mut packet, NTS_EXT_COOKIE, cookie);

    // Authenticator and Encrypted Extension Fields
    let cipher = Aes128SivAead::new_from_slice(&c2s_key[..32]).ok()?;

    // AAD is everything before this extension field
    let aad = packet.clone();

    // Nonce (16 bytes from unique_id)
    let nonce = &unique_id[..16];

    // Encrypt empty plaintext
    let ciphertext = cipher.encrypt(nonce.into(), aes_siv::aead::Payload {
        msg: &[],
        aad: &aad,
    }).ok()?;

    // Build Auth+Enc extension field
    let mut auth_data = Vec::new();
    auth_data.extend_from_slice(&(nonce.len() as u16).to_be_bytes());
    auth_data.extend_from_slice(nonce);
    auth_data.extend_from_slice(&(ciphertext.len() as u16).to_be_bytes());
    auth_data.extend_from_slice(&ciphertext);

    add_extension_field(&mut packet, NTS_EXT_AUTH_AND_ENC, &auth_data);

    Some(packet)
}

/// Add NTP extension field
fn add_extension_field(packet: &mut Vec<u8>, field_type: u16, data: &[u8]) {
    let padded_len = (data.len() + 3) & !3;
    let total_len = 4 + padded_len;

    packet.extend_from_slice(&field_type.to_be_bytes());
    packet.extend_from_slice(&(total_len as u16).to_be_bytes());
    packet.extend_from_slice(data);

    // Padding
    for _ in data.len()..padded_len {
        packet.push(0);
    }
}

/// Parse NTS-protected NTP response
fn parse_nts_ntp_response(data: &[u8], s2c_key: &[u8; 32]) -> Option<u64> {
    if data.len() < 48 {
        return None;
    }

    // Parse extension fields to find and verify authenticator
    let mut pos = 48;
    let mut unique_id: Option<Vec<u8>> = None;
    let mut auth_data: Option<Vec<u8>> = None;

    while pos + 4 <= data.len() {
        let field_type = u16::from_be_bytes([data[pos], data[pos + 1]]);
        let field_len = u16::from_be_bytes([data[pos + 2], data[pos + 3]]) as usize;

        if field_len < 4 || pos + field_len > data.len() {
            break;
        }

        let field_data = &data[pos + 4..pos + field_len];

        match field_type {
            NTS_EXT_UNIQUE_ID => {
                unique_id = Some(field_data.to_vec());
            }
            NTS_EXT_AUTH_AND_ENC => {
                auth_data = Some(field_data.to_vec());
            }
            _ => {}
        }

        pos += field_len;
    }

    // Verify authenticator
    if let (Some(_uid), Some(auth)) = (unique_id, auth_data) {
        if auth.len() < 4 {
            return None;
        }

        let nonce_len = u16::from_be_bytes([auth[0], auth[1]]) as usize;
        if auth.len() < 2 + nonce_len + 2 {
            return None;
        }

        let nonce = &auth[2..2 + nonce_len];
        let ct_len = u16::from_be_bytes([auth[2 + nonce_len], auth[3 + nonce_len]]) as usize;

        if auth.len() < 4 + nonce_len + ct_len {
            return None;
        }

        let ciphertext = &auth[4 + nonce_len..4 + nonce_len + ct_len];

        // AAD is everything before the Auth+Enc field
        let aad_end = data.len() - (auth.len() + 4);
        let aad = &data[..aad_end];

        let cipher = Aes128SivAead::new_from_slice(&s2c_key[..32]).ok()?;

        // Verify and decrypt
        cipher.decrypt(nonce.into(), aes_siv::aead::Payload {
            msg: ciphertext,
            aad,
        }).ok()?;
    }

    // Extract transmit timestamp from NTP header
    let ntp_secs = u32::from_be_bytes([data[40], data[41], data[42], data[43]]) as u64;
    let unix_secs = ntp_secs.saturating_sub(2208988800);

    Some(unix_secs)
}
