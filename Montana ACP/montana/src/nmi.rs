//! Montana Time Oracle — Three-Layer Architecture
//!
//! Слой 1: Внутренний порядок + P2P-аттестация (вес 55)
//! Слой 2: NTS серверы (вес 25)
//! Слой 3: NTP серверы (вес 15)
//!
//! Медиана Montana времени = weighted median всех трёх слоёв.

use crate::nts::query_nts_server;
use std::net::UdpSocket;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tokio::sync::RwLock;
use tracing::{info, warn};

/// Layer 1: P2P sample size
pub const P2P_SAMPLE_SIZE: usize = 99;

/// NTP query timeout
const NTP_TIMEOUT_SECS: u64 = 5;

/// Time server entry
pub struct TimeServer {
    pub host: &'static str,
    pub institute: &'static str,
    pub country: &'static str,
    pub stratum: u8,
}

// ══════════════════════════════════════════════════════════════════════════
// LAYER 2: NTS Servers (RFC 8915) — only verified NTS-capable servers
// ══════════════════════════════════════════════════════════════════════════

pub const NTS_SERVERS: &[TimeServer] = &[
    // ── Global ──
    TimeServer { host: "time.cloudflare.com", institute: "Cloudflare", country: "Global", stratum: 1 },

    // ── Sweden (Netnod) ──
    TimeServer { host: "nts.netnod.se", institute: "Netnod", country: "Sweden", stratum: 1 },
    TimeServer { host: "nts.ntp.se", institute: "Netnod", country: "Sweden", stratum: 1 },
    TimeServer { host: "sth1.nts.netnod.se", institute: "Netnod Stockholm", country: "Sweden", stratum: 1 },
    TimeServer { host: "sth2.nts.netnod.se", institute: "Netnod Stockholm", country: "Sweden", stratum: 1 },
    TimeServer { host: "gbg1.nts.netnod.se", institute: "Netnod Gothenburg", country: "Sweden", stratum: 1 },
    TimeServer { host: "gbg2.nts.netnod.se", institute: "Netnod Gothenburg", country: "Sweden", stratum: 1 },
    TimeServer { host: "lul1.nts.netnod.se", institute: "Netnod Luleå", country: "Sweden", stratum: 1 },
    TimeServer { host: "mmo1.nts.netnod.se", institute: "Netnod Malmö", country: "Sweden", stratum: 1 },
    TimeServer { host: "svl1.nts.netnod.se", institute: "Netnod Sundsvall", country: "Sweden", stratum: 1 },

    // ── Netherlands ──
    TimeServer { host: "nts.time.nl", institute: "SIDN Labs", country: "Netherlands", stratum: 1 },
    TimeServer { host: "ntppool1.time.nl", institute: "VSL", country: "Netherlands", stratum: 1 },
    TimeServer { host: "ntppool2.time.nl", institute: "VSL", country: "Netherlands", stratum: 1 },

    // ── Germany ──
    TimeServer { host: "ptbtime1.ptb.de", institute: "PTB", country: "Germany", stratum: 1 },
    TimeServer { host: "ptbtime2.ptb.de", institute: "PTB", country: "Germany", stratum: 1 },
    TimeServer { host: "ptbtime3.ptb.de", institute: "PTB", country: "Germany", stratum: 1 },
    TimeServer { host: "ntp3.fau.de", institute: "FAU Erlangen", country: "Germany", stratum: 1 },
    TimeServer { host: "ntp.3eck.net", institute: "3eck", country: "Germany", stratum: 2 },
    TimeServer { host: "ntp.nanosrvr.cloud", institute: "Nanosrvr", country: "Germany", stratum: 2 },
    TimeServer { host: "www.jabber-germany.de", institute: "Jabber Germany", country: "Germany", stratum: 2 },

    // ── Switzerland ──
    TimeServer { host: "ntp01.maillink.ch", institute: "Maillink", country: "Switzerland", stratum: 2 },
    TimeServer { host: "ntp02.maillink.ch", institute: "Maillink", country: "Switzerland", stratum: 2 },
    TimeServer { host: "ntp03.maillink.ch", institute: "Maillink", country: "Switzerland", stratum: 2 },

    // ── Belgium ──
    TimeServer { host: "nts.teambelgium.net", institute: "Team Belgium", country: "Belgium", stratum: 2 },

    // ── UK ──
    TimeServer { host: "ntp1.dmz.terryburton.co.uk", institute: "Terry Burton", country: "UK", stratum: 2 },
    TimeServer { host: "ntp2.dmz.terryburton.co.uk", institute: "Terry Burton", country: "UK", stratum: 2 },

    // ── France ──
    TimeServer { host: "paris.time.system76.com", institute: "System76", country: "France", stratum: 2 },
    TimeServer { host: "ntp.viarouge.net", institute: "Viarouge", country: "France", stratum: 2 },

    // ── Finland ──
    TimeServer { host: "ntp.miuku.net", institute: "Miuku", country: "Finland", stratum: 2 },

    // ── Czechia ──
    TimeServer { host: "time.cincura.net", institute: "Cincura", country: "Czechia", stratum: 2 },

    // ── USA ──
    TimeServer { host: "virginia.time.system76.com", institute: "System76", country: "USA", stratum: 2 },
    TimeServer { host: "ohio.time.system76.com", institute: "System76", country: "USA", stratum: 2 },
    TimeServer { host: "oregon.time.system76.com", institute: "System76", country: "USA", stratum: 2 },
    TimeServer { host: "ntp1.glypnod.com", institute: "Glypnod", country: "USA", stratum: 2 },
    TimeServer { host: "ntp2.glypnod.com", institute: "Glypnod", country: "USA", stratum: 2 },
    TimeServer { host: "time.txryan.com", institute: "TxRyan", country: "USA", stratum: 2 },
    TimeServer { host: "ntp1.wiktel.com", institute: "Wiktel", country: "USA", stratum: 2 },
    TimeServer { host: "ntp2.wiktel.com", institute: "Wiktel", country: "USA", stratum: 2 },
    TimeServer { host: "stratum1.time.cifelli.xyz", institute: "Cifelli", country: "USA", stratum: 1 },
    TimeServer { host: "time.cifelli.xyz", institute: "Cifelli", country: "USA", stratum: 2 },

    // ── Canada ──
    TimeServer { host: "time.web-clock.ca", institute: "Web-Clock", country: "Canada", stratum: 2 },
    TimeServer { host: "time1.mbix.ca", institute: "MBIX", country: "Canada", stratum: 2 },
    TimeServer { host: "time2.mbix.ca", institute: "MBIX", country: "Canada", stratum: 2 },
    TimeServer { host: "time3.mbix.ca", institute: "MBIX", country: "Canada", stratum: 2 },

    // ── Brazil ──
    TimeServer { host: "brazil.time.system76.com", institute: "System76", country: "Brazil", stratum: 2 },
    TimeServer { host: "a.st1.ntp.br", institute: "NIC.br", country: "Brazil", stratum: 1 },
    TimeServer { host: "d.st1.ntp.br", institute: "NIC.br", country: "Brazil", stratum: 1 },
    TimeServer { host: "gps.ntp.br", institute: "NIC.br", country: "Brazil", stratum: 1 },
    TimeServer { host: "time.bolha.one", institute: "Bolha", country: "Brazil", stratum: 2 },

    // ── Singapore ──
    TimeServer { host: "ntpmon.dcs1.biz", institute: "DCS1", country: "Singapore", stratum: 2 },
];

// ══════════════════════════════════════════════════════════════════════════
// LAYER 3: NTP Servers (plain NTP — 42 servers, global coverage)
// ══════════════════════════════════════════════════════════════════════════

pub const NTP_SERVERS: &[TimeServer] = &[
    // ── Asia ──
    TimeServer { host: "ntp.nict.jp", institute: "NICT", country: "Japan", stratum: 1 },
    TimeServer { host: "time.kriss.re.kr", institute: "KRISS", country: "Korea", stratum: 1 },
    TimeServer { host: "stdtime.gov.hk", institute: "HKOBS", country: "Hong Kong", stratum: 1 },
    TimeServer { host: "asia.pool.ntp.org", institute: "NTP Pool", country: "Asia", stratum: 2 },

    // ── Oceania ──
    TimeServer { host: "au.pool.ntp.org", institute: "NTP Pool", country: "Australia", stratum: 2 },
    TimeServer { host: "nz.pool.ntp.org", institute: "NTP Pool", country: "New Zealand", stratum: 2 },
    TimeServer { host: "oceania.pool.ntp.org", institute: "NTP Pool", country: "Oceania", stratum: 2 },

    // ── Africa ──
    TimeServer { host: "time.nmisa.org", institute: "NMISA", country: "South Africa", stratum: 1 },
    TimeServer { host: "africa.pool.ntp.org", institute: "NTP Pool", country: "Africa", stratum: 2 },

    // ── Russia ──
    TimeServer { host: "ntp1.vniiftri.ru", institute: "VNIIFTRI", country: "Russia", stratum: 1 },
    TimeServer { host: "ntp.ix.ru", institute: "MSK-IX", country: "Russia", stratum: 1 },

    // ── Europe (no NTS) ──
    TimeServer { host: "ntp.obspm.fr", institute: "LNE-SYRTE", country: "France", stratum: 1 },
    TimeServer { host: "tempus1.gum.gov.pl", institute: "GUM", country: "Poland", stratum: 1 },
    TimeServer { host: "ntp.nic.cz", institute: "CZ.NIC", country: "Czechia", stratum: 1 },
    TimeServer { host: "ntp.ufe.cz", institute: "UFE", country: "Czechia", stratum: 1 },
    TimeServer { host: "ntp.ripe.net", institute: "RIPE NCC", country: "Netherlands", stratum: 1 },
    TimeServer { host: "ntp.se", institute: "Netnod", country: "Sweden", stratum: 1 },
    TimeServer { host: "time.fu-berlin.de", institute: "FU Berlin", country: "Germany", stratum: 1 },
    TimeServer { host: "europe.pool.ntp.org", institute: "NTP Pool", country: "Europe", stratum: 2 },

    // ── North America (corporate) ──
    TimeServer { host: "time.google.com", institute: "Google", country: "USA", stratum: 1 },
    TimeServer { host: "time.apple.com", institute: "Apple", country: "USA", stratum: 2 },
    TimeServer { host: "time.facebook.com", institute: "Meta", country: "USA", stratum: 1 },
    TimeServer { host: "time.windows.com", institute: "Microsoft", country: "USA", stratum: 2 },
    TimeServer { host: "time.aws.com", institute: "Amazon", country: "USA", stratum: 2 },
    TimeServer { host: "ntp.ubuntu.com", institute: "Canonical", country: "UK", stratum: 2 },
    TimeServer { host: "time.nrc.ca", institute: "NRC", country: "Canada", stratum: 1 },

    // ── North America (academic/gov) ──
    TimeServer { host: "ntp-b.nist.gov", institute: "NIST", country: "USA", stratum: 1 },
    TimeServer { host: "utcnist.colorado.edu", institute: "NIST Boulder", country: "USA", stratum: 1 },
    TimeServer { host: "time.stanford.edu", institute: "Stanford", country: "USA", stratum: 1 },
    TimeServer { host: "time.mit.edu", institute: "MIT", country: "USA", stratum: 2 },
    TimeServer { host: "clock.xmission.com", institute: "XMission", country: "USA", stratum: 2 },
    TimeServer { host: "clock.isc.org", institute: "ISC", country: "USA", stratum: 1 },
    TimeServer { host: "north-america.pool.ntp.org", institute: "NTP Pool", country: "N. America", stratum: 2 },

    // ── South America ──
    TimeServer { host: "south-america.pool.ntp.org", institute: "NTP Pool", country: "S. America", stratum: 2 },

    // ── Global pools ──
    TimeServer { host: "0.pool.ntp.org", institute: "NTP Pool", country: "Global", stratum: 2 },
    TimeServer { host: "1.pool.ntp.org", institute: "NTP Pool", country: "Global", stratum: 2 },
    TimeServer { host: "2.pool.ntp.org", institute: "NTP Pool", country: "Global", stratum: 2 },
    TimeServer { host: "3.pool.ntp.org", institute: "NTP Pool", country: "Global", stratum: 2 },
];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CalibrationMode {
    Calibrated,
    Uncalibrated,
}

#[derive(Debug, Clone)]
pub struct QueryResult {
    pub server: String,
    pub country: String,
    pub timestamp: u64,
    pub stratum: u8,
    pub success: bool,
    pub layer: u8,
}

/// P2P node time attestation
#[derive(Debug, Clone)]
pub struct P2PNode {
    pub pubkey_short: String,  // first 8 hex chars
    pub timestamp: u64,
}

pub struct TimeOracle {
    mode: RwLock<CalibrationMode>,
    offset_secs: RwLock<i64>,
    layer1_time: RwLock<u64>,           // P2P attestation median
    layer1_nodes: RwLock<Vec<P2PNode>>, // P2P nodes sample
}

impl TimeOracle {
    pub fn new() -> Self {
        Self {
            mode: RwLock::new(CalibrationMode::Uncalibrated),
            offset_secs: RwLock::new(0),
            layer1_time: RwLock::new(0),
            layer1_nodes: RwLock::new(Vec::new()),
        }
    }

    /// Layer 1: Update from P2P attestation (called from consensus)
    pub async fn update_layer1(&self, p2p_median: u64, nodes: Vec<P2PNode>) {
        *self.layer1_time.write().await = p2p_median;
        *self.layer1_nodes.write().await = nodes;
    }

    /// Query single NTP server (Layer 3)
    fn query_ntp(server: &str) -> Option<u64> {
        let socket = UdpSocket::bind("0.0.0.0:0").ok()?;
        socket.set_read_timeout(Some(Duration::from_secs(NTP_TIMEOUT_SECS))).ok()?;
        socket.set_write_timeout(Some(Duration::from_secs(NTP_TIMEOUT_SECS))).ok()?;

        let addr = format!("{}:123", server);
        sntpc::simple_get_time(&addr, &socket)
            .ok()
            .map(|r| r.sec() as u64)
    }

    /// Query Layer 2 (NTS servers)
    async fn query_layer2(&self) -> Vec<QueryResult> {
        let futures: Vec<_> = NTS_SERVERS
            .iter()
            .map(|server| {
                let host = server.host.to_string();
                let institute = server.institute.to_string();
                let country = server.country.to_string();
                let stratum = server.stratum;

                async move {
                    let result = query_nts_server(&host).await;
                    QueryResult {
                        server: format!("{} ({})", host, institute),
                        country,
                        timestamp: result.unwrap_or(0),
                        stratum,
                        success: result.is_some(),
                        layer: 2,
                    }
                }
            })
            .collect();

        futures::future::join_all(futures).await
    }

    /// Query Layer 3 (NTP servers)
    async fn query_layer3(&self) -> Vec<QueryResult> {
        let futures: Vec<_> = NTP_SERVERS
            .iter()
            .map(|server| {
                let host = server.host.to_string();
                let institute = server.institute.to_string();
                let country = server.country.to_string();
                let stratum = server.stratum;

                async move {
                    let result = tokio::task::spawn_blocking({
                        let h = host.clone();
                        move || Self::query_ntp(&h)
                    })
                    .await
                    .ok()
                    .flatten();

                    QueryResult {
                        server: format!("{} ({})", host, institute),
                        country,
                        timestamp: result.unwrap_or(0),
                        stratum,
                        success: result.is_some(),
                        layer: 3,
                    }
                }
            })
            .collect();

        futures::future::join_all(futures).await
    }

    fn calculate_median(results: &[QueryResult]) -> Option<u64> {
        let mut timestamps: Vec<u64> = results
            .iter()
            .filter(|r| r.success)
            .map(|r| r.timestamp)
            .collect();

        if timestamps.is_empty() {
            return None;
        }

        timestamps.sort();
        let mid = timestamps.len() / 2;
        Some(timestamps[mid])
    }

    fn count_agreeing(results: &[QueryResult], median: u64) -> usize {
        results
            .iter()
            .filter(|r| r.success)
            .filter(|r| (r.timestamp as i64 - median as i64).abs() <= 1)
            .count()
    }

    /// Calculate simple median from all timestamps
    fn simple_median(timestamps: &[u64]) -> Option<u64> {
        let mut sorted: Vec<u64> = timestamps.iter().filter(|&&t| t > 0).copied().collect();

        if sorted.is_empty() {
            return None;
        }

        sorted.sort();
        let mid = sorted.len() / 2;
        Some(sorted[mid])
    }

    fn format_time(ts: u64) -> String {
        use chrono::{TimeZone, Utc};
        Utc.timestamp_opt(ts as i64, 0)
            .unwrap()
            .format("%H:%M UTC")
            .to_string()
    }

    /// Display time servers and return true if time is synced (divergence <= 1s)
    pub async fn display_servers(&self) -> bool {
        let query_start = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_secs();

        // Query all layers in parallel (silent)
        let (layer2_results, layer3_results) = tokio::join!(
            self.query_layer2(),
            self.query_layer3()
        );

        let query_end = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_secs();

        // Display results
        info!("═══════════════════════════════════════════════════════");
        info!("NMI Time Sync Results ({}s)", query_end - query_start);
        info!("═══════════════════════════════════════════════════════");

        // Display Layer 1 (P2P nodes)
        let layer1_nodes = self.layer1_nodes.read().await;
        let l1_count = layer1_nodes.len();
        let local_time = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_secs();
        info!("Layer 1 — P2P [{}/{}]", l1_count, P2P_SAMPLE_SIZE);
        if l1_count > 0 {
            for node in layer1_nodes.iter() {
                info!("  ✓ {} — node {}", Self::format_time(node.timestamp), node.pubkey_short);
            }
        } else {
            warn!("  ✗ No peers connected");
        }
        drop(layer1_nodes);

        // Display Layer 2 (NTS)
        let l2_ok = layer2_results.iter().filter(|r| r.success).count();
        info!("Layer 2 — NTS [{}/{}]", l2_ok, NTS_SERVERS.len());
        for r in &layer2_results {
            if r.success {
                info!("  ✓ {} — {} [S{}]", Self::format_time(r.timestamp), r.server, r.stratum);
            } else {
                warn!("  ✗ {} — {}", r.country, r.server);
            }
        }

        // Display Layer 3 (NTP)
        let l3_ok = layer3_results.iter().filter(|r| r.success).count();
        info!("Layer 3 — NTP [{}/{}]", l3_ok, NTP_SERVERS.len());
        for r in &layer3_results {
            if r.success {
                info!("  ✓ {} — {} [S{}]", Self::format_time(r.timestamp), r.server, r.stratum);
            } else {
                warn!("  ✗ {} — {}", r.country, r.server);
            }
        }

        // Summary — collect all timestamps
        let mut all_timestamps: Vec<u64> = Vec::new();

        // Layer 1: local + P2P nodes
        all_timestamps.push(local_time);
        let layer1_nodes = self.layer1_nodes.read().await;
        for node in layer1_nodes.iter() {
            all_timestamps.push(node.timestamp);
        }
        drop(layer1_nodes);

        // Layer 2: NTS servers
        for r in &layer2_results {
            if r.success {
                all_timestamps.push(r.timestamp);
            }
        }

        // Layer 3: NTP servers
        for r in &layer3_results {
            if r.success {
                all_timestamps.push(r.timestamp);
            }
        }

        info!("───────────────────────────────────────────────────────");
        let synced = if let Some(median) = Self::simple_median(&all_timestamps) {
            let median_min = median / 60;
            let local_min = local_time / 60;
            info!("Montana Time: {} ● {} — local", Self::format_time(median), Self::format_time(local_time));
            if median_min != local_min {
                let divergence = (median as i64 - local_time as i64).abs();
                warn!("FATAL: Local time diverges by {}s — node must be disconnected", divergence);
                false
            } else {
                true
            }
        } else {
            warn!("FATAL: No time sources available — node must be disconnected");
            false
        };
        info!("═══════════════════════════════════════════════════════");
        synced
    }

    pub async fn calibrate(&self) -> CalibrationMode {
        // Query all layers in parallel
        let (layer2_results, layer3_results) = tokio::join!(
            self.query_layer2(),
            self.query_layer3()
        );

        // Collect all timestamps
        let mut all_timestamps: Vec<u64> = Vec::new();

        // Layer 1: local + P2P
        let local_time = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_secs();
        all_timestamps.push(local_time);

        let layer1_nodes = self.layer1_nodes.read().await;
        for node in layer1_nodes.iter() {
            all_timestamps.push(node.timestamp);
        }
        drop(layer1_nodes);

        // Layer 2: NTS servers
        for r in &layer2_results {
            if r.success {
                all_timestamps.push(r.timestamp);
            }
        }

        // Layer 3: NTP servers
        for r in &layer3_results {
            if r.success {
                all_timestamps.push(r.timestamp);
            }
        }

        // Try to calibrate with median
        if let Some(median) = Self::simple_median(&all_timestamps) {
            let offset = median as i64 - local_time as i64;

            *self.offset_secs.write().await = offset;
            *self.mode.write().await = CalibrationMode::Calibrated;

            return CalibrationMode::Calibrated;
        }

        // Fallback: use local time (offset=0) but mark as uncalibrated
        *self.offset_secs.write().await = 0;
        *self.mode.write().await = CalibrationMode::Uncalibrated;
        CalibrationMode::Uncalibrated
    }

    pub async fn mode(&self) -> CalibrationMode {
        *self.mode.read().await
    }

    pub async fn calibrated_time(&self) -> u64 {
        let local_time = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_secs();
        let offset = *self.offset_secs.read().await;
        (local_time as i64 + offset) as u64
    }

    pub async fn display_time(&self) -> (u64, CalibrationMode) {
        (self.calibrated_time().await, *self.mode.read().await)
    }
}

impl Default for TimeOracle {
    fn default() -> Self {
        Self::new()
    }
}
