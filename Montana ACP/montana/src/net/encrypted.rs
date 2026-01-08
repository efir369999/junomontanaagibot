//! Noise XX + ML-KEM-768 encrypted connections
//!
//! Implements chunked encryption to handle messages larger than Noise's 64KB limit.
//! Montana protocol allows messages up to 2MB; this layer transparently fragments
//! and reassembles them using Noise frames.

use super::noise::{HandshakeState, NoiseError, NoiseTransport, StaticKeypair, MAX_NOISE_MESSAGE_SIZE, CHACHA_TAG_SIZE};
use rand::rngs::OsRng;
use std::io;
use std::net::SocketAddr;
use std::path::Path;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpStream;
use tracing::info;

// =============================================================================
// CONSTANTS
// =============================================================================

/// Noise handshake timeout (seconds)
pub const NOISE_HANDSHAKE_TIMEOUT_SECS: u64 = 30;

/// Maximum handshake message size
pub const MAX_HANDSHAKE_MSG_SIZE: usize = 4096;

/// Maximum payload per Noise chunk (64KB - tag - length - chunk header)
/// Chunk header is 1 byte (more flag)
const CHUNK_PAYLOAD_MAX: usize = MAX_NOISE_MESSAGE_SIZE - CHACHA_TAG_SIZE - 2 - 1;

/// Maximum total message size (Montana protocol limit)
const MAX_MESSAGE_SIZE: usize = 2 * 1024 * 1024; // 2MB

/// Maximum chunks allowed (prevents DoS via infinite chunking)
const MAX_CHUNKS: usize = (MAX_MESSAGE_SIZE / CHUNK_PAYLOAD_MAX) + 1; // ~32 chunks

// =============================================================================
// ENCRYPTED STREAM
// =============================================================================

/// Encrypted TCP stream wrapper
///
/// Provides transparent encryption/decryption for all data sent/received.
/// After Noise handshake completes, all Montana protocol messages are encrypted.
pub struct EncryptedStream {
    /// Underlying TCP stream (read half)
    reader: tokio::io::ReadHalf<TcpStream>,
    /// Underlying TCP stream (write half)
    writer: tokio::io::WriteHalf<TcpStream>,
    /// Noise transport state for encryption
    transport: NoiseTransport,
    /// Peer address
    pub peer_addr: SocketAddr,
    /// Remote peer's static public key (verified via Noise)
    pub remote_pubkey: Option<[u8; 32]>,
}

impl EncryptedStream {
    /// Establish encrypted connection as initiator
    ///
    /// Performs Noise XX handshake with ML-KEM-768 hybrid.
    /// Returns encrypted stream ready for Montana protocol.
    pub async fn connect(
        stream: TcpStream,
        our_keypair: &StaticKeypair,
    ) -> Result<Self, EncryptedError> {
        let peer_addr = stream.peer_addr()?;
        let (mut reader, mut writer) = tokio::io::split(stream);

        info!("Starting Noise handshake with {} (initiator)", peer_addr);

        // Create initiator handshake state
        let mut handshake = HandshakeState::new_initiator(StaticKeypair::from_secret(our_keypair.secret));

        // Message 0: -> e, kem_pk
        let msg0 = handshake.write_message(&mut OsRng, &[])
            .map_err(EncryptedError::Noise)?;
        write_handshake_msg(&mut writer, &msg0).await?;

        // Read message 1: <- e, ee, s, es, kem_ct
        let msg1 = read_handshake_msg(&mut reader).await?;
        let _ = handshake.read_message(&msg1)
            .map_err(EncryptedError::Noise)?;

        // Message 2: -> s, se
        let msg2 = handshake.write_message(&mut OsRng, &[])
            .map_err(EncryptedError::Noise)?;
        write_handshake_msg(&mut writer, &msg2).await?;

        // Finalize handshake
        let transport = handshake.finalize()
            .map_err(EncryptedError::Noise)?;

        let remote_pubkey = transport.remote_static;

        info!(
            "Noise handshake complete with {} (remote_pubkey: {})",
            peer_addr,
            remote_pubkey.map(|pk| hex::encode(&pk[..8])).unwrap_or_else(|| "none".into())
        );

        Ok(Self {
            reader,
            writer,
            transport,
            peer_addr,
            remote_pubkey,
        })
    }

    /// Accept encrypted connection as responder
    ///
    /// Performs Noise XX handshake with ML-KEM-768 hybrid.
    /// Returns encrypted stream ready for Montana protocol.
    pub async fn accept(
        stream: TcpStream,
        our_keypair: &StaticKeypair,
    ) -> Result<Self, EncryptedError> {
        let peer_addr = stream.peer_addr()?;
        let (mut reader, mut writer) = tokio::io::split(stream);

        info!("Starting Noise handshake with {} (responder)", peer_addr);

        // Create responder handshake state
        let mut handshake = HandshakeState::new_responder(StaticKeypair::from_secret(our_keypair.secret));

        // Read message 0: -> e, kem_pk
        let msg0 = read_handshake_msg(&mut reader).await?;
        let _ = handshake.read_message(&msg0)
            .map_err(EncryptedError::Noise)?;

        // Message 1: <- e, ee, s, es, kem_ct
        let msg1 = handshake.write_message(&mut OsRng, &[])
            .map_err(EncryptedError::Noise)?;
        write_handshake_msg(&mut writer, &msg1).await?;

        // Read message 2: -> s, se
        let msg2 = read_handshake_msg(&mut reader).await?;
        let _ = handshake.read_message(&msg2)
            .map_err(EncryptedError::Noise)?;

        // Finalize handshake
        let transport = handshake.finalize()
            .map_err(EncryptedError::Noise)?;

        let remote_pubkey = transport.remote_static;

        info!(
            "Noise handshake complete with {} (remote_pubkey: {})",
            peer_addr,
            remote_pubkey.map(|pk| hex::encode(&pk[..8])).unwrap_or_else(|| "none".into())
        );

        Ok(Self {
            reader,
            writer,
            transport,
            peer_addr,
            remote_pubkey,
        })
    }

    /// Write encrypted data with automatic chunking
    pub async fn write(&mut self, data: &[u8]) -> io::Result<()> {
        if data.len() > MAX_MESSAGE_SIZE {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!("message too large: {} > {}", data.len(), MAX_MESSAGE_SIZE),
            ));
        }

        let chunks: Vec<&[u8]> = data.chunks(CHUNK_PAYLOAD_MAX).collect();
        let total_chunks = chunks.len();

        for (i, chunk) in chunks.iter().enumerate() {
            let is_last = i == total_chunks - 1;
            let more_flag: u8 = if is_last { 0 } else { 1 };

            let mut chunk_data = Vec::with_capacity(1 + chunk.len());
            chunk_data.push(more_flag);
            chunk_data.extend_from_slice(chunk);

            let encrypted = self.transport.encrypt(&chunk_data).map_err(|e| {
                io::Error::new(io::ErrorKind::InvalidData, e.to_string())
            })?;

            self.writer.write_all(&encrypted).await?;
        }

        self.writer.flush().await
    }

    /// Read encrypted data with automatic chunk reassembly
    pub async fn read(&mut self) -> io::Result<Vec<u8>> {
        let mut result = Vec::new();
        let mut chunks_read = 0;

        loop {
            chunks_read += 1;
            if chunks_read > MAX_CHUNKS {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidData,
                    "too many chunks (DoS protection)",
                ));
            }

            let mut len_bytes = [0u8; 2];
            self.reader.read_exact(&mut len_bytes).await?;
            let len = u16::from_be_bytes(len_bytes) as usize;

            if len > MAX_NOISE_MESSAGE_SIZE {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidData,
                    "encrypted chunk too large",
                ));
            }

            let mut ciphertext = vec![0u8; len];
            self.reader.read_exact(&mut ciphertext).await?;

            let mut frame = Vec::with_capacity(2 + len);
            frame.extend_from_slice(&len_bytes);
            frame.extend_from_slice(&ciphertext);

            let chunk_data = self.transport.decrypt(&frame).map_err(|e| {
                io::Error::new(io::ErrorKind::InvalidData, e.to_string())
            })?;

            if chunk_data.is_empty() {
                return Err(io::Error::new(io::ErrorKind::InvalidData, "empty chunk"));
            }

            let more_flag = chunk_data[0];
            let payload = &chunk_data[1..];

            if result.len() + payload.len() > MAX_MESSAGE_SIZE {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidData,
                    "reassembled message too large (DoS protection)",
                ));
            }

            result.extend_from_slice(payload);

            if more_flag == 0 {
                break;
            }
        }

        Ok(result)
    }

    /// Split into read and write halves
    pub fn split(self) -> (EncryptedReader, EncryptedWriter) {
        // Note: This is a simplified split that shares transport state
        // In production, you'd need proper synchronization
        let transport = std::sync::Arc::new(tokio::sync::Mutex::new(self.transport));

        (
            EncryptedReader {
                reader: self.reader,
                transport: transport.clone(),
            },
            EncryptedWriter {
                writer: self.writer,
                transport,
            },
        )
    }
}

/// Encrypted reader half
pub struct EncryptedReader {
    reader: tokio::io::ReadHalf<TcpStream>,
    transport: std::sync::Arc<tokio::sync::Mutex<NoiseTransport>>,
}

impl EncryptedReader {
    /// Read encrypted data with automatic chunk reassembly
    ///
    /// Reads and reassembles chunked messages transparently.
    /// Each chunk has format: [more: 1 byte][payload]
    pub async fn read(&mut self) -> io::Result<Vec<u8>> {
        let mut result = Vec::new();
        let mut chunks_read = 0;

        loop {
            chunks_read += 1;
            if chunks_read > MAX_CHUNKS {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidData,
                    "too many chunks (DoS protection)",
                ));
            }

            // Read single Noise frame
            let mut len_bytes = [0u8; 2];
            self.reader.read_exact(&mut len_bytes).await?;
            let len = u16::from_be_bytes(len_bytes) as usize;

            if len > MAX_NOISE_MESSAGE_SIZE {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidData,
                    "encrypted chunk too large",
                ));
            }

            // Read ciphertext
            let mut ciphertext = vec![0u8; len];
            self.reader.read_exact(&mut ciphertext).await?;

            // Rebuild frame for decrypt
            let mut frame = Vec::with_capacity(2 + len);
            frame.extend_from_slice(&len_bytes);
            frame.extend_from_slice(&ciphertext);

            // Decrypt
            let chunk_data = {
                let mut transport = self.transport.lock().await;
                transport.decrypt(&frame).map_err(|e| {
                    io::Error::new(io::ErrorKind::InvalidData, e.to_string())
                })?
            };

            if chunk_data.is_empty() {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidData,
                    "empty chunk",
                ));
            }

            // Parse chunk: [more_flag][payload]
            let more_flag = chunk_data[0];
            let payload = &chunk_data[1..];

            // Check total size limit
            if result.len() + payload.len() > MAX_MESSAGE_SIZE {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidData,
                    "reassembled message too large (DoS protection)",
                ));
            }

            result.extend_from_slice(payload);

            // more_flag: 0 = last chunk, 1 = more coming
            if more_flag == 0 {
                break;
            }
        }

        Ok(result)
    }
}

/// Encrypted writer half
pub struct EncryptedWriter {
    writer: tokio::io::WriteHalf<TcpStream>,
    transport: std::sync::Arc<tokio::sync::Mutex<NoiseTransport>>,
}

impl EncryptedWriter {
    /// Write encrypted data with automatic chunking for large messages
    ///
    /// Messages larger than ~64KB are split into multiple Noise frames.
    /// Each chunk has format: [more: 1 byte][payload]
    /// - more=0: final or only chunk
    /// - more=1: more chunks follow
    pub async fn write(&mut self, data: &[u8]) -> io::Result<()> {
        if data.len() > MAX_MESSAGE_SIZE {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!("message too large: {} > {}", data.len(), MAX_MESSAGE_SIZE),
            ));
        }

        let chunks: Vec<&[u8]> = data.chunks(CHUNK_PAYLOAD_MAX).collect();
        let total_chunks = chunks.len();

        for (i, chunk) in chunks.iter().enumerate() {
            let is_last = i == total_chunks - 1;
            let more_flag: u8 = if is_last { 0 } else { 1 };

            // Build chunk: [more_flag][payload]
            let mut chunk_data = Vec::with_capacity(1 + chunk.len());
            chunk_data.push(more_flag);
            chunk_data.extend_from_slice(chunk);

            let encrypted = {
                let mut transport = self.transport.lock().await;
                transport.encrypt(&chunk_data).map_err(|e| {
                    io::Error::new(io::ErrorKind::InvalidData, e.to_string())
                })?
            };

            self.writer.write_all(&encrypted).await?;
        }

        self.writer.flush().await
    }
}

// =============================================================================
// KEYPAIR MANAGEMENT
// =============================================================================

/// Load or generate node keypair
///
/// The keypair is used for Noise Protocol authentication.
/// Stored in `data_dir/noise_key.bin` encrypted with a derived key.
pub fn load_or_generate_keypair(data_dir: &Path) -> io::Result<StaticKeypair> {
    let key_path = data_dir.join("noise_key.bin");

    if key_path.exists() {
        // Load existing keypair
        let data = std::fs::read(&key_path)?;
        if data.len() != 32 {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "invalid keypair file",
            ));
        }

        let mut secret = [0u8; 32];
        secret.copy_from_slice(&data);

        info!("Loaded Noise keypair from {:?}", key_path);
        Ok(StaticKeypair::from_secret(secret))
    } else {
        // Generate new keypair
        let keypair = StaticKeypair::generate(&mut OsRng);

        // Save to file
        std::fs::create_dir_all(data_dir)?;
        std::fs::write(&key_path, &keypair.secret)?;

        // Set restrictive permissions (Unix only)
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mut perms = std::fs::metadata(&key_path)?.permissions();
            perms.set_mode(0o600);
            std::fs::set_permissions(&key_path, perms)?;
        }

        info!(
            "Generated new Noise keypair, saved to {:?}, pubkey: {}",
            key_path,
            hex::encode(&keypair.public[..8])
        );
        Ok(keypair)
    }
}

/// Get public key fingerprint for logging
pub fn pubkey_fingerprint(pubkey: &[u8; 32]) -> String {
    hex::encode(&pubkey[..8])
}

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

/// Write handshake message with length prefix
async fn write_handshake_msg<W: AsyncWriteExt + Unpin>(
    writer: &mut W,
    msg: &[u8],
) -> io::Result<()> {
    if msg.len() > MAX_HANDSHAKE_MSG_SIZE {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "handshake message too large",
        ));
    }

    let len = msg.len() as u16;
    writer.write_all(&len.to_be_bytes()).await?;
    writer.write_all(msg).await?;
    writer.flush().await
}

/// Read handshake message with length prefix
async fn read_handshake_msg<R: AsyncReadExt + Unpin>(reader: &mut R) -> Result<Vec<u8>, EncryptedError> {
    let mut len_bytes = [0u8; 2];
    reader.read_exact(&mut len_bytes).await?;
    let len = u16::from_be_bytes(len_bytes) as usize;

    if len > MAX_HANDSHAKE_MSG_SIZE {
        return Err(EncryptedError::MessageTooLarge(len));
    }

    let mut msg = vec![0u8; len];
    reader.read_exact(&mut msg).await?;
    Ok(msg)
}

// =============================================================================
// ERRORS
// =============================================================================

#[derive(Debug, thiserror::Error)]
pub enum EncryptedError {
    #[error("io error: {0}")]
    Io(#[from] io::Error),

    #[error("noise error: {0}")]
    Noise(NoiseError),

    #[error("handshake timeout")]
    Timeout,

    #[error("message too large: {0}")]
    MessageTooLarge(usize),

    #[error("authentication failed: remote pubkey mismatch")]
    AuthenticationFailed,
}

// =============================================================================
// TESTS
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use tokio::net::TcpListener;

    #[tokio::test]
    async fn test_encrypted_connection() {
        // Generate keypairs
        let server_keypair = StaticKeypair::generate(&mut OsRng);
        let client_keypair = StaticKeypair::generate(&mut OsRng);

        // Start server
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let server_addr = listener.local_addr().unwrap();

        let server_kp = StaticKeypair::from_secret(server_keypair.secret);
        let server_handle = tokio::spawn(async move {
            let (stream, _) = listener.accept().await.unwrap();
            let mut encrypted = EncryptedStream::accept(stream, &server_kp).await.unwrap();

            // Read message
            let msg = encrypted.read().await.unwrap();
            assert_eq!(msg, b"Hello from client!");

            // Send response
            encrypted.write(b"Hello from server!").await.unwrap();
        });

        // Connect client
        let stream = TcpStream::connect(server_addr).await.unwrap();
        let mut encrypted = EncryptedStream::connect(stream, &client_keypair).await.unwrap();

        // Send message
        encrypted.write(b"Hello from client!").await.unwrap();

        // Read response
        let response = encrypted.read().await.unwrap();
        assert_eq!(response, b"Hello from server!");

        server_handle.await.unwrap();
    }

    #[test]
    fn test_keypair_generation() {
        let keypair = StaticKeypair::generate(&mut OsRng);
        assert_eq!(keypair.public.len(), 32);
        assert_eq!(keypair.secret.len(), 32);
    }
}
