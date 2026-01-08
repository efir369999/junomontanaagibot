//! Montana Network Protocol — Test Implementation
//!
//! ACP Network Layer — Atemporal Coordinate Presence
//!
//! Stripped-down implementation for network protocol testing only.
//! No lottery, no cooldown, no NMI/NTS — pure networking.

mod crypto;
mod db;
mod net;
mod types;

use crate::crypto::Keypair;
use crate::db::Storage;
use crate::net::{
    NetConfig, NetEvent, Network, VerificationClient, NODE_FULL, NODE_PRESENCE,
    verification_type,
};
use crate::types::*;
use clap::Parser;
use std::net::{IpAddr, SocketAddr};
use std::path::PathBuf;
use std::sync::Arc;
use tokio::sync::RwLock;
use tracing::{error, info, warn};

/// Montana version
const VERSION: &str = env!("CARGO_PKG_VERSION");

#[derive(Parser)]
#[command(name = "montana", version, about = "Montana: Network Protocol Test")]
struct Args {
    /// Node type: full, light, client
    #[arg(short, long, default_value = "full")]
    node_type: String,

    /// Listen port
    #[arg(short, long, default_value = "19333")]
    port: u16,

    /// Data directory
    #[arg(short, long, default_value = "./data")]
    data_dir: PathBuf,

    /// Seed nodes (comma-separated)
    #[arg(short, long)]
    seeds: Option<String>,

    /// External IP address (optional, auto-discovered from peers if not set)
    #[arg(short = 'e', long)]
    external_ip: Option<IpAddr>,

    /// Use testnet (different hardcoded seeds)
    #[arg(long)]
    testnet: bool,

    /// Skip bootstrap verification (DANGEROUS - only for testing)
    #[arg(long)]
    skip_verify: bool,
}

/// Minimal node for network testing
struct Node {
    keypair: Keypair,
    node_type: NodeType,
    storage: Arc<Storage>,
    network: Arc<Network>,
    mempool: RwLock<Vec<Transaction>>,
}

impl Node {
    async fn new(
        node_type: NodeType,
        data_dir: &PathBuf,
        port: u16,
        seeds: Vec<String>,
        external_ip: Option<IpAddr>,
        testnet: bool,
        skip_verify: bool,
    ) -> Result<(Self, tokio::sync::mpsc::Receiver<NetEvent>), Box<dyn std::error::Error>> {
        // Initialize storage
        std::fs::create_dir_all(data_dir)?;
        let storage = Storage::open(data_dir)?;

        // Initialize genesis if needed
        if storage.head().is_err() {
            info!("Initializing genesis slice");
            storage.init_genesis()?;
        }

        // Get genesis for verification
        let genesis = storage.get_slice(0)?;

        // =====================================================================
        // BOOTSTRAP VERIFICATION GATE
        // =====================================================================
        //
        // This is the critical security mechanism against Eclipse Attack.
        // Verification MUST complete successfully BEFORE network starts.
        //
        // Security requirements:
        // - 100 peers (20 hardcoded + 80 P2P via gossip)
        // - 25+ unique /16 subnets
        // - Hardcoded nodes must match network median ±1%
        // - Local clock verified against network median
        //
        // Attack cost: control 51+ peers from 25+ /16 subnets AND 15+ hardcoded
        //
        let verify_type = verification_type(&storage);
        let chain_age = storage.chain_age_secs().unwrap_or(u64::MAX);
        let head = storage.head().unwrap_or(0);

        info!("Startup verification: {} (chain_age={} secs, height={})",
            verify_type, chain_age, head);

        if skip_verify {
            // DANGER: Skip verification only for testing
            warn!("════════════════════════════════════════════════════════════");
            warn!("  DANGER: Bootstrap verification SKIPPED (--skip-verify)");
            warn!("  This node is vulnerable to Eclipse Attack!");
            warn!("  DO NOT use in production.");
            warn!("════════════════════════════════════════════════════════════");
        } else {
            // Run bootstrap verification (BLOCKING)
            info!("Running bootstrap verification...");
            info!("Requirements: 100 peers, 25+ /16 subnets, hardcoded consensus");

            let verifier = VerificationClient::new(testnet, port, genesis.clone());

            match verifier.verify().await {
                Ok(result) => {
                    info!("════════════════════════════════════════════════════════════");
                    info!("  Bootstrap verification PASSED");
                    info!("  Height: {} | Weight: {} | Network time: {}",
                        result.height, result.weight, result.network_time);
                    info!("  Peers: {} ({} hardcoded + {} P2P) | Subnets: {}",
                        result.hardcoded_responses + result.p2p_responses,
                        result.hardcoded_responses,
                        result.p2p_responses,
                        result.unique_subnets);
                    info!("════════════════════════════════════════════════════════════");

                    if let Some(warning) = result.time_warning {
                        warn!("Time warning: {}", warning);
                    }
                    if let Some(warning) = result.height_warning {
                        warn!("Height warning: {}", warning);
                    }
                }
                Err(e) => {
                    error!("════════════════════════════════════════════════════════════");
                    error!("  CRITICAL: Bootstrap verification FAILED");
                    error!("  Error: {}", e);
                    error!("════════════════════════════════════════════════════════════");
                    error!("Possible causes:");
                    error!("  1. Network connectivity issues");
                    error!("  2. Hardcoded nodes are down");
                    error!("  3. Local clock is significantly wrong");
                    error!("  4. Network under attack (unlikely but check)");
                    error!("");
                    error!("Node startup ABORTED for security.");
                    error!("Use --skip-verify to bypass (DANGEROUS, testing only).");

                    return Err(format!("Bootstrap verification failed: {}", e).into());
                }
            }
        }

        // Generate keypair
        let keypair = Keypair::generate();
        info!("Node pubkey: {}", hex::encode(&keypair.public[..32]));

        // Create network config
        let net_config = NetConfig {
            listen_port: port,
            data_dir: data_dir.clone(),
            node_type,
            services: NODE_FULL | NODE_PRESENCE,
            seeds,
            external_ip,
            ..Default::default()
        };

        // Create and start network (AFTER verification passed)
        let (network, event_rx) = Network::new(net_config).await?;
        network.start().await?;

        let current_head = storage.head().unwrap_or(0);
        network.set_best_slice(current_head).await;

        Ok((
            Self {
                keypair,
                node_type,
                storage: Arc::new(storage),
                network: Arc::new(network),
                mempool: RwLock::new(Vec::new()),
            },
            event_rx,
        ))
    }

    /// Handle incoming network events
    async fn handle_event(&self, event: NetEvent) {
        match event {
            NetEvent::PeerConnected(addr) => {
                info!("Peer connected: {}", addr);
            }

            NetEvent::PeerDisconnected(addr) => {
                info!("Peer disconnected: {}", addr);
            }

            NetEvent::Slice(addr, slice) => {
                info!("Received slice #{} from {}", slice.header.slice_index, addr);
                if let Err(e) = self.handle_slice(*slice).await {
                    warn!("Failed to process slice: {}", e);
                }
            }

            NetEvent::Tx(addr, tx) => {
                info!("Received tx from {}", addr);
                self.handle_tx(*tx).await;
            }

            NetEvent::Presence(addr, presence) => {
                info!(
                    "Received presence from {} for τ₂ #{}",
                    addr, presence.tau2_index
                );
            }

            NetEvent::NeedSlices(addr, start, count) => {
                info!("Peer {} needs slices {}-{}", addr, start, start + count - 1);
                self.send_slices_to_peer(addr, start, count).await;
            }

            NetEvent::PeerAhead(addr, their_best) => {
                let our_best = self.storage.head().unwrap_or(0);
                if their_best > our_best {
                    info!(
                        "Peer {} has slices up to {} (we have {}), requesting sync",
                        addr, their_best, our_best
                    );
                    self.network
                        .request_slices(&addr, our_best + 1, their_best - our_best)
                        .await;
                }
            }
        }
    }

    /// Handle received slice
    async fn handle_slice(&self, slice: Slice) -> Result<(), String> {
        let head = self.storage.head().unwrap_or(0);

        // Check if already have it
        if slice.header.slice_index <= head {
            return Ok(());
        }

        // Check if next expected
        if slice.header.slice_index != head + 1 {
            return Err(format!(
                "Slice gap: expected {}, got {}",
                head + 1,
                slice.header.slice_index
            ));
        }

        // Verify prev_hash
        let prev_slice = self
            .storage
            .get_slice(head)
            .map_err(|e| format!("Failed to get prev slice: {}", e))?;

        if slice.header.prev_hash != prev_slice.hash() {
            return Err("Invalid prev_hash".into());
        }

        // Verify signature
        let header_data = bincode::serialize(&slice.header).map_err(|e| e.to_string())?;
        crypto::verify(&slice.header.winner_pubkey, &header_data, &slice.signature)
            .map_err(|_| "Invalid slice signature")?;

        // Store slice
        self.storage
            .put_slice(&slice)
            .map_err(|e| format!("Failed to store slice: {}", e))?;

        info!("Stored slice #{}", slice.header.slice_index);

        // Update network's best slice
        self.network.set_best_slice(slice.header.slice_index).await;

        Ok(())
    }

    /// Handle received transaction
    async fn handle_tx(&self, tx: Transaction) {
        // Basic validation
        if tx.inputs.is_empty() && !tx.is_coinbase() {
            return;
        }

        // Check UTXOs exist
        for input in &tx.inputs {
            if self
                .storage
                .get_utxo(&input.prev_tx, input.output_index)
                .is_err()
            {
                warn!("UTXO not found for tx input");
                return;
            }
        }

        self.mempool.write().await.push(tx);
    }

    /// Send slices to requesting peer
    async fn send_slices_to_peer(&self, addr: SocketAddr, start: u64, count: u64) {
        for i in start..(start + count) {
            match self.storage.get_slice(i) {
                Ok(slice) => {
                    self.network.send_slice(&addr, slice).await;
                }
                Err(_) => break,
            }
        }
    }
}

#[tokio::main]
async fn main() {
    // Initialize logging
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::from_default_env()
                .add_directive("montana=info".parse().unwrap()),
        )
        .init();

    let args = Args::parse();

    let node_type = match args.node_type.as_str() {
        "full" => NodeType::Full,
        "light" => NodeType::Light,
        "client" => NodeType::Client,
        _ => {
            error!("Invalid node type. Use: full, light, client");
            return;
        }
    };

    // Parse seeds
    let seeds: Vec<String> = args
        .seeds
        .map(|s| s.split(',').map(|s| s.trim().to_string()).collect())
        .unwrap_or_default();

    info!("════════════════════════════════════════════════════════════");
    info!("  Ɉ Montana v{} — Network Protocol Test", VERSION);
    info!("════════════════════════════════════════════════════════════");
    info!("Node type: {:?} | Port: {}", node_type, args.port);
    if !seeds.is_empty() {
        info!("Seeds: {:?}", seeds);
    }
    if let Some(ip) = &args.external_ip {
        info!("External IP: {}", ip);
    }

    // Create node with bootstrap verification
    let (node, mut event_rx) = match Node::new(
        node_type,
        &args.data_dir,
        args.port,
        seeds,
        args.external_ip,
        args.testnet,
        args.skip_verify,
    ).await {
        Ok(n) => n,
        Err(e) => {
            error!("Failed to create node: {}", e);
            return;
        }
    };

    let node = Arc::new(node);

    // Event handler loop
    let node_clone = node.clone();
    tokio::spawn(async move {
        while let Some(event) = event_rx.recv().await {
            node_clone.handle_event(event).await;
        }
    });

    // Status printer
    let node_clone = node.clone();
    tokio::spawn(async move {
        let mut interval = tokio::time::interval(tokio::time::Duration::from_secs(30));
        loop {
            interval.tick().await;
            let peers = node_clone.network.peer_count().await;
            let head = node_clone.storage.head().unwrap_or(0);
            info!("Status: {} peers | chain height: {}", peers, head);
        }
    });

    // Initial status
    let head = node.storage.head().unwrap_or(0);
    info!("Montana running. Chain height: {}", head);
    info!("Waiting for peer connections...");

    // Wait for shutdown
    tokio::signal::ctrl_c().await.ok();
    info!("Shutting down...");
    node.network.shutdown().await;
}
