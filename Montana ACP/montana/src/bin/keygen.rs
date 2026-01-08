//! ML-DSA-65 Key Generation Tool for Hardcoded Nodes
//!
//! Generates cryptographic keypair for Montana hardcoded bootstrap nodes.
//! This tool creates:
//! - Public key (1952 bytes) - for hardcoded_identity.rs
//! - Secret key (4000 bytes) - for secure storage (HSM recommended)
//!
//! Usage:
//!   cargo run --bin keygen -- --name "timeweb-moscow" --output ./keys/
//!
//! The output includes:
//! - Rust code snippet for public key (copy to hardcoded_identity.rs)
//! - Secret key file (keep secure, load via env var or HSM)

use clap::Parser;
use pqcrypto_dilithium::dilithium3 as mldsa;
use pqcrypto_traits::sign::{PublicKey as PkTrait, SecretKey as SkTrait};
use std::fs;
use std::path::PathBuf;

/// ML-DSA-65 public key size (1952 bytes)
const MLDSA65_PUBKEY_SIZE: usize = 1952;

/// ML-DSA-65 secret key size (4000 bytes)
const MLDSA65_SECRET_SIZE: usize = 4000;

#[derive(Parser)]
#[command(name = "keygen", version, about = "Montana ML-DSA-65 Key Generator")]
struct Args {
    /// Node name (for documentation)
    #[arg(short, long)]
    name: String,

    /// Output directory for keys
    #[arg(short, long, default_value = ".")]
    output: PathBuf,

    /// Region (for documentation)
    #[arg(short, long, default_value = "unknown")]
    region: String,

    /// IP address (for documentation)
    #[arg(short, long)]
    ip: Option<String>,
}

fn main() {
    let args = Args::parse();

    println!("════════════════════════════════════════════════════════════");
    println!("  Montana ML-DSA-65 Keypair Generator");
    println!("════════════════════════════════════════════════════════════");
    println!();
    println!("Generating keypair for: {}", args.name);
    println!("Region: {}", args.region);
    if let Some(ref ip) = args.ip {
        println!("IP: {}", ip);
    }
    println!();

    // Generate keypair
    let (pk, sk) = mldsa::keypair();
    let pubkey_bytes = pk.as_bytes();
    let secret_bytes = sk.as_bytes();

    // Verify sizes (informational - different library versions may differ slightly)
    if pubkey_bytes.len() != MLDSA65_PUBKEY_SIZE {
        eprintln!("Note: Public key size {} differs from expected {}", pubkey_bytes.len(), MLDSA65_PUBKEY_SIZE);
    }
    if secret_bytes.len() != MLDSA65_SECRET_SIZE {
        eprintln!("Note: Secret key size {} differs from expected {}", secret_bytes.len(), MLDSA65_SECRET_SIZE);
    }

    // Create output directory
    fs::create_dir_all(&args.output).expect("Failed to create output directory");

    // Save secret key
    let secret_path = args.output.join(format!("{}_secret.key", args.name));
    fs::write(&secret_path, secret_bytes).expect("Failed to write secret key");
    println!("Secret key saved to: {}", secret_path.display());
    println!("  Size: {} bytes", secret_bytes.len());
    println!();

    // Save public key (binary)
    let pubkey_path = args.output.join(format!("{}_public.key", args.name));
    fs::write(&pubkey_path, pubkey_bytes).expect("Failed to write public key");
    println!("Public key saved to: {}", pubkey_path.display());
    println!("  Size: {} bytes", pubkey_bytes.len());
    println!();

    // Generate Rust code snippet
    let rust_const_name = args.name.to_uppercase().replace("-", "_") + "_PUBKEY";

    println!("════════════════════════════════════════════════════════════");
    println!("  Rust Code (copy to hardcoded_identity.rs)");
    println!("════════════════════════════════════════════════════════════");
    println!();

    // Print as hex chunks for readability
    print!("const {}: MlDsa65PublicKey = *b\"", rust_const_name);
    for byte in pubkey_bytes {
        print!("\\x{:02x}", byte);
    }
    println!("\";");
    println!();

    // Also save the Rust code to a file
    let rust_path = args.output.join(format!("{}_pubkey.rs", args.name));
    let mut rust_code = format!(
        "/// ML-DSA-65 public key for {} ({})\n",
        args.name, args.region
    );
    if let Some(ref ip) = args.ip {
        rust_code.push_str(&format!("/// IP: {}\n", ip));
    }
    rust_code.push_str(&format!(
        "/// Generated: {}\n",
        chrono::Utc::now().format("%Y-%m-%d %H:%M:%S UTC")
    ));
    rust_code.push_str(&format!("const {}: MlDsa65PublicKey = *b\"", rust_const_name));
    for byte in pubkey_bytes {
        rust_code.push_str(&format!("\\x{:02x}", byte));
    }
    rust_code.push_str("\";\n");

    fs::write(&rust_path, &rust_code).expect("Failed to write Rust code");
    println!("Rust code saved to: {}", rust_path.display());
    println!();

    // Hex representation for documentation
    println!("════════════════════════════════════════════════════════════");
    println!("  Public Key (hex, first 64 bytes)");
    println!("════════════════════════════════════════════════════════════");
    println!();
    println!("{}", hex::encode(&pubkey_bytes[..64]));
    println!("... ({} more bytes)", pubkey_bytes.len() - 64);
    println!();

    // Verification test
    println!("════════════════════════════════════════════════════════════");
    println!("  Verification Test");
    println!("════════════════════════════════════════════════════════════");
    println!();

    // Sign test message
    let test_message = b"Montana hardcoded node authentication test";
    let signature = mldsa::detached_sign(test_message, &sk);

    // Verify
    match mldsa::verify_detached_signature(&signature, test_message, &pk) {
        Ok(()) => println!("  Signature verification: PASSED"),
        Err(_) => {
            println!("  Signature verification: FAILED");
            std::process::exit(1);
        }
    }
    println!();

    println!("════════════════════════════════════════════════════════════");
    println!("  SECURITY INSTRUCTIONS");
    println!("════════════════════════════════════════════════════════════");
    println!();
    println!("1. Store {}_secret.key in HSM or encrypted storage", args.name);
    println!("2. Never commit secret key to version control");
    println!("3. Load secret key via environment variable:");
    println!("   export MONTANA_HARDCODED_SECRET=$(cat {}_secret.key | base64)", args.name);
    println!();
    println!("4. Add public key to hardcoded_identity.rs");
    println!("5. Deploy to server and configure NetConfig.hardcoded_secret_key");
    println!();
}
