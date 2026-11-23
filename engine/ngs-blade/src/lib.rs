//! Blade M1 Native Engine for NouGenShards (ngs.h draft 0.3.1, ABI 3001).
//!
//! Architecture:
//! - Single append-only framed log (`ngs.log`) + 64-byte node key (`node.key`).
//! - Every `ngs_remember` / `ngs_remember_many` writes ONE contiguous atomic
//!   Batch Frame (`NGSF` header + length + facts payload + CRC32 + `FEND` tail)
//!   in a single write + `sync_data()` (unless `NGS_WRITE_NO_SYNC`).
//! - Hash-chained, gapless monotonic `seq` per writer; BLAKE3/SHA-256 fact IDs.
//! - Torn tail at EOF is truncated cleanly on reopen; mid-log bit flips are
//!   detected via CRC32 + chain verification and return `NGS_CORRUPT`.
//! - Every returned `ngs_fact*` is a single 16-byte-aligned allocation freed
//!   with `ngs_free()`.

#![allow(non_camel_case_types, clippy::missing_safety_doc)]

use std::alloc::{alloc, dealloc, Layout};
use std::collections::HashMap;
use std::ffi::{CStr, CString};
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Seek, SeekFrom, Write};
use std::os::raw::{c_char, c_int, c_void};
use std::path::{Path, PathBuf};
use std::ptr;
use std::sync::Mutex;
use std::time::{Instant, SystemTime, UNIX_EPOCH};

// ---------- Constants from ngs.h 0.3.1 ----------
pub const NGS_VERSION_NUMBER: c_int = 3001;
pub const NGS_OK: c_int = 0;
pub const NGS_ERROR: c_int = 1;
pub const NGS_NOTFOUND: c_int = 2;
pub const NGS_BUSY: c_int = 3;
pub const NGS_CORRUPT: c_int = 4;
pub const NGS_NOGRANT: c_int = 5;
pub const NGS_MISMATCH: c_int = 6;
pub const NGS_QUARANTINED: c_int = 7;
pub const NGS_NOMEM: c_int = 9;
pub const NGS_IOERR: c_int = 10;
pub const NGS_MISUSE: c_int = 11;
pub const NGS_TOOBIG: c_int = 12;

pub const NGS_TIME_MIN: i64 = i64::MIN;
pub const NGS_TIME_MAX: i64 = i64::MAX;
pub const NGS_TIME_NOW: i64 = i64::MIN + 1;

pub const NGS_EPISODIC: i32 = 1;
pub const NGS_SEMANTIC: i32 = 2;
pub const NGS_PROCEDURAL: i32 = 3;

pub const NGS_OPEN_READONLY: i32 = 0x0001;
pub const NGS_OPEN_READWRITE: i32 = 0x0002;
pub const NGS_OPEN_CREATE: i32 = 0x0004;

pub const NGS_WRITE_NO_SYNC: i32 = 0x0001;

pub const NGS_MAX_NS_LEN: usize = 255;
pub const NGS_MAX_TITLE_LEN: usize = 1024;
pub const NGS_MAX_ATTRS_LEN: usize = 65536;
pub const NGS_MAX_DIM: usize = 8192;
pub const NGS_ALIGN_MAX: usize = 16;

const FRAME_MAGIC: &[u8; 4] = b"NGSF";
const FRAME_TAIL: &[u8; 4] = b"FEND";
const FRAME_VERSION: u16 = 1;

// ---------- C ABI Structs ----------
#[repr(C)]
#[derive(Clone, Copy, PartialEq, Eq, Hash, Default, Debug)]
pub struct ngs_id {
    pub b: [u8; 32],
}

#[repr(C)]
#[derive(Clone, Copy, PartialEq, Eq, Hash, Default, Debug)]
pub struct ngs_pubkey {
    pub b: [u8; 32],
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct ngs_str {
    pub p: *const c_char,
    pub n: usize,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct ngs_vec {
    pub model_id: ngs_str,
    pub dim: u32,
    pub version: u32,
    pub v: *const f32,
}

#[repr(C)]
pub struct ngs_open_opts {
    pub size: u32,
    pub flags: i32,
    pub node_seckey: *const u8,
    pub segment_bytes: u64,
    pub group_commit_ms: u32,
    pub checkpoint_every: u32,
    pub shard_vec_split: u32,
    pub root_pubkey: *const ngs_pubkey,
}

#[repr(C)]
pub struct ngs_fact_in {
    pub size: u32,
    pub ns: ngs_str,
    pub kind: i32,
    pub t_event: i64,
    pub valid_from: i64,
    pub title: ngs_str,
    pub body: ngs_str,
    pub tags: *const ngs_str,
    pub n_tags: usize,
    pub attrs_cbor: *const u8,
    pub attrs_len: usize,
    pub schema: u16,
    pub vecs: *const ngs_vec,
    pub n_vecs: usize,
    pub supersedes: *const ngs_id,
    pub salience0: f32,
    pub tokenizer_ids: *const ngs_str,
    pub token_counts: *const u32,
    pub n_token_counts: usize,
}

#[repr(C)]
pub struct ngs_fact {
    pub size: u32,
    pub id: ngs_id,
    pub ns: ngs_str,
    pub kind: i32,
    pub writer: ngs_pubkey,
    pub seq: u64,
    pub t_event: i64,
    pub t_record: i64,
    pub valid_from: i64,
    pub valid_to: i64,
    pub superseded_by: ngs_id,
    pub title: ngs_str,
    pub body: ngs_str,
    pub tags: *const ngs_str,
    pub n_tags: usize,
    pub attrs_cbor: *const u8,
    pub attrs_len: usize,
    pub schema: u16,
    pub redacted: i32,
}

pub const NGS_ARM_VEC: usize = 0;
pub const NGS_ARM_KW: usize = 1;
pub const NGS_ARM_RECENCY: usize = 2;
pub const NGS_ARM_SALIENCE: usize = 3;
pub const NGS_ARM_LINK: usize = 4;
pub const NGS_N_ARMS: usize = 5;

pub const NGS_RECALL_EXPAND: i32 = 0x0001;
pub const NGS_RECALL_INCLUDE_INVALID: i32 = 0x0002;
pub const NGS_RECALL_NO_BODY: i32 = 0x0004;

#[repr(C)]
pub struct ngs_query {
    pub size: u32,
    pub ns: ngs_str,
    pub kinds: u32,
    pub text: ngs_str,
    pub vec: *const ngs_vec,
    pub since: i64,
    pub until: i64,
    pub tags: *const ngs_str,
    pub n_tags: usize,
    pub k: u32,
    pub deadline_ms: u32,
    pub fusion: i32,
    pub weights: *const f32,
    pub flags: i32,
    pub token_budget: u32,
    pub tokenizer_id: ngs_str,
    pub min_confidence: f32,
}

#[repr(C)]
pub struct ngs_hit {
    pub size: u32,
    pub id: ngs_id,
    pub kind: i32,
    pub ns: ngs_str,
    pub title: ngs_str,
    pub body: ngs_str,
    pub score: f32,
    pub arm: [f32; NGS_N_ARMS],
    pub invalid: i32,
    pub confidence: f32,
    pub tokens: u32,
    pub stub: i32,
    pub tokens_estimated: i32,
}

#[repr(C)]
pub struct ngs_results {
    pub size: u32,
    pub hits: *mut ngs_hit,
    pub n: usize,
    pub arms_complete: u32,
    pub timed_out: i32,
    pub elapsed_us: u32,
    pub abstained: i32,
    pub confidence_calibrated: i32,
    pub best_confidence: f32,
    pub min_confidence: f32,
    pub tokens_used: u32,
    pub tokens_budget: u32,
}

#[repr(C)]
pub struct ngs_scan_opts {
    pub size: u32,
    pub ns: ngs_str,
    pub writer: *const ngs_pubkey,
    pub since: i64,
    pub until: i64,
    pub include_derived: i32,
}

// ---------- Pure-Rust CRC32 (IEEE) & SHA-256 (for deterministic 32-byte IDs) ----------
fn crc32(data: &[u8]) -> u32 {
    let mut crc: u32 = 0xFFFF_FFFF;
    for &b in data {
        crc ^= b as u32;
        for _ in 0..8 {
            let mask = (crc & 1).wrapping_neg();
            crc = (crc >> 1) ^ (0xEDB8_8320 & mask);
        }
    }
    !crc
}

fn sha256(data: &[u8]) -> [u8; 32] {
    const K: [u32; 64] = [
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
        0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
        0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
        0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
        0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
        0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
        0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
        0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
    ];
    let mut h: [u32; 8] = [
        0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
        0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
    ];
    let bit_len = (data.len() as u64).wrapping_mul(8);
    let mut msg = data.to_vec();
    msg.push(0x80);
    while (msg.len() % 64) != 56 {
        msg.push(0);
    }
    msg.extend_from_slice(&bit_len.to_be_bytes());

    for chunk in msg.chunks_exact(64) {
        let mut w = [0u32; 64];
        for i in 0..16 {
            w[i] = u32::from_be_bytes([
                chunk[4 * i],
                chunk[4 * i + 1],
                chunk[4 * i + 2],
                chunk[4 * i + 3],
            ]);
        }
        for i in 16..64 {
            let s0 = w[i - 15].rotate_right(7) ^ w[i - 15].rotate_right(18) ^ (w[i - 15] >> 3);
            let s1 = w[i - 2].rotate_right(17) ^ w[i - 2].rotate_right(19) ^ (w[i - 2] >> 10);
            w[i] = w[i - 16].wrapping_add(s0).wrapping_add(w[i - 7]).wrapping_add(s1);
        }
        let [mut a, mut b, mut c, mut d, mut e, mut f, mut g, mut hh] = h;
        for i in 0..64 {
            let s1 = e.rotate_right(6) ^ e.rotate_right(11) ^ e.rotate_right(25);
            let ch = (e & f) ^ ((!e) & g);
            let t1 = hh.wrapping_add(s1).wrapping_add(ch).wrapping_add(K[i]).wrapping_add(w[i]);
            let s0 = a.rotate_right(2) ^ a.rotate_right(13) ^ a.rotate_right(22);
            let maj = (a & b) ^ (a & c) ^ (b & c);
            let t2 = s0.wrapping_add(maj);
            hh = g;
            g = f;
            f = e;
            e = d.wrapping_add(t1);
            d = c;
            c = b;
            b = a;
            a = t1.wrapping_add(t2);
        }
        h[0] = h[0].wrapping_add(a);
        h[1] = h[1].wrapping_add(b);
        h[2] = h[2].wrapping_add(c);
        h[3] = h[3].wrapping_add(d);
        h[4] = h[4].wrapping_add(e);
        h[5] = h[5].wrapping_add(f);
        h[6] = h[6].wrapping_add(g);
        h[7] = h[7].wrapping_add(hh);
    }
    let mut out = [0u8; 32];
    for (i, val) in h.iter().enumerate() {
        out[4 * i..4 * i + 4].copy_from_slice(&val.to_be_bytes());
    }
    out
}

fn now_us() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_micros() as i64)
        .unwrap_or(0)
}

// ---------- Single-allocation 16-byte-aligned allocator ----------
#[repr(C, align(16))]
struct AllocHeader {
    total_size: usize,
    _pad: usize,
}

unsafe fn ngs_alloc_block(payload_size: usize) -> *mut u8 {
    let header_size = std::mem::size_of::<AllocHeader>(); // 16
    let total = match header_size.checked_add(payload_size) {
        Some(t) => t,
        None => return ptr::null_mut(),
    };
    let layout = match Layout::from_size_align(total, NGS_ALIGN_MAX) {
        Ok(l) => l,
        Err(_) => return ptr::null_mut(),
    };
    let raw = alloc(layout);
    if raw.is_null() {
        return ptr::null_mut();
    }
    ptr::write(raw as *mut AllocHeader, AllocHeader { total_size: total, _pad: 0 });
    raw.add(header_size)
}

// ---------- Stored Vec & Link ----------
#[derive(Clone)]
struct StoredVec {
    model_id: Vec<u8>,
    dim: u32,
    version: u32,
    v: Vec<f32>,
}

#[derive(Clone)]
struct StoredLink {
    id: ngs_id,
    a: ngs_id,
    b: ngs_id,
    rel: Vec<u8>,
    weight: f32,
    valid: bool,
}

// ---------- Stored Fact ----------
#[derive(Clone)]
struct StoredFact {
    id: ngs_id,
    prev_id: ngs_id,
    writer: ngs_pubkey,
    seq: u64,
    t_event: i64,
    t_record: i64,
    valid_from: i64,
    valid_to: i64,
    kind: i32,
    schema: u16,
    redacted: i32,
    ns: Vec<u8>,
    title: Vec<u8>,
    body: Vec<u8>,
    vecs: Vec<StoredVec>,
}

impl StoredFact {
    fn compute_id(&self) -> ngs_id {
        let mut buf = Vec::with_capacity(128 + self.ns.len() + self.title.len() + self.body.len());
        buf.extend_from_slice(b"NGS-FACT-V1");
        buf.extend_from_slice(&self.prev_id.b);
        buf.extend_from_slice(&self.writer.b);
        buf.extend_from_slice(&self.seq.to_le_bytes());
        buf.extend_from_slice(&self.t_event.to_le_bytes());
        buf.extend_from_slice(&self.t_record.to_le_bytes());
        buf.extend_from_slice(&self.valid_from.to_le_bytes());
        buf.extend_from_slice(&self.valid_to.to_le_bytes());
        buf.extend_from_slice(&self.kind.to_le_bytes());
        buf.extend_from_slice(&self.schema.to_le_bytes());
        buf.extend_from_slice(&(self.ns.len() as u32).to_le_bytes());
        buf.extend_from_slice(&self.ns);
        buf.extend_from_slice(&(self.title.len() as u32).to_le_bytes());
        buf.extend_from_slice(&self.title);
        buf.extend_from_slice(&(self.body.len() as u32).to_le_bytes());
        buf.extend_from_slice(&self.body);
        ngs_id { b: sha256(&buf) }
    }

    fn encode(&self, out: &mut Vec<u8>) {
        out.extend_from_slice(&self.id.b);
        out.extend_from_slice(&self.prev_id.b);
        out.extend_from_slice(&self.writer.b);
        out.extend_from_slice(&self.seq.to_le_bytes());
        out.extend_from_slice(&self.t_event.to_le_bytes());
        out.extend_from_slice(&self.t_record.to_le_bytes());
        out.extend_from_slice(&self.valid_from.to_le_bytes());
        out.extend_from_slice(&self.valid_to.to_le_bytes());
        out.extend_from_slice(&self.kind.to_le_bytes());
        out.extend_from_slice(&self.schema.to_le_bytes());
        out.extend_from_slice(&self.redacted.to_le_bytes());
        out.extend_from_slice(&(self.ns.len() as u32).to_le_bytes());
        out.extend_from_slice(&self.ns);
        out.extend_from_slice(&(self.title.len() as u32).to_le_bytes());
        out.extend_from_slice(&self.title);
        out.extend_from_slice(&(self.body.len() as u32).to_le_bytes());
        out.extend_from_slice(&self.body);
    }

    fn decode(slice: &[u8], pos: &mut usize) -> Option<Self> {
        let take = |n: usize, pos: &mut usize| -> Option<&[u8]> {
            let end = pos.checked_add(n)?;
            if end > slice.len() {
                return None;
            }
            let s = &slice[*pos..end];
            *pos = end;
            Some(s)
        };
        let mut id = ngs_id::default();
        id.b.copy_from_slice(take(32, pos)?);
        let mut prev_id = ngs_id::default();
        prev_id.b.copy_from_slice(take(32, pos)?);
        let mut writer = ngs_pubkey::default();
        writer.b.copy_from_slice(take(32, pos)?);
        let seq = u64::from_le_bytes(take(8, pos)?.try_into().ok()?);
        let t_event = i64::from_le_bytes(take(8, pos)?.try_into().ok()?);
        let t_record = i64::from_le_bytes(take(8, pos)?.try_into().ok()?);
        let valid_from = i64::from_le_bytes(take(8, pos)?.try_into().ok()?);
        let valid_to = i64::from_le_bytes(take(8, pos)?.try_into().ok()?);
        let kind = i32::from_le_bytes(take(4, pos)?.try_into().ok()?);
        let schema = u16::from_le_bytes(take(2, pos)?.try_into().ok()?);
        let redacted = i32::from_le_bytes(take(4, pos)?.try_into().ok()?);
        let ns_len = u32::from_le_bytes(take(4, pos)?.try_into().ok()?) as usize;
        let ns = take(ns_len, pos)?.to_vec();
        let title_len = u32::from_le_bytes(take(4, pos)?.try_into().ok()?) as usize;
        let title = take(title_len, pos)?.to_vec();
        let body_len = u32::from_le_bytes(take(4, pos)?.try_into().ok()?) as usize;
        let body = take(body_len, pos)?.to_vec();
        Some(StoredFact {
            id,
            prev_id,
            writer,
            seq,
            t_event,
            t_record,
            valid_from,
            valid_to,
            kind,
            schema,
            redacted,
            ns,
            title,
            body,
            vecs: Vec::new(),
        })
    }

    unsafe fn to_c_fact(&self) -> *mut ngs_fact {
        let struct_sz = std::mem::size_of::<ngs_fact>();
        let total_payload = struct_sz + self.ns.len() + self.title.len() + self.body.len();
        let base = ngs_alloc_block(total_payload);
        if base.is_null() {
            return ptr::null_mut();
        }
        let mut cursor = base.add(struct_sz);

        let ns_ptr = if self.ns.is_empty() {
            ptr::null()
        } else {
            ptr::copy_nonoverlapping(self.ns.as_ptr(), cursor, self.ns.len());
            let p = cursor as *const c_char;
            cursor = cursor.add(self.ns.len());
            p
        };
        let title_ptr = if self.title.is_empty() {
            ptr::null()
        } else {
            ptr::copy_nonoverlapping(self.title.as_ptr(), cursor, self.title.len());
            let p = cursor as *const c_char;
            cursor = cursor.add(self.title.len());
            p
        };
        let body_ptr = if self.body.is_empty() {
            ptr::null()
        } else {
            ptr::copy_nonoverlapping(self.body.as_ptr(), cursor, self.body.len());
            cursor as *const c_char
        };

        let f = ngs_fact {
            size: struct_sz as u32,
            id: self.id,
            ns: ngs_str { p: ns_ptr, n: self.ns.len() },
            kind: self.kind,
            writer: self.writer,
            seq: self.seq,
            t_event: self.t_event,
            t_record: self.t_record,
            valid_from: self.valid_from,
            valid_to: self.valid_to,
            superseded_by: ngs_id::default(),
            title: ngs_str { p: title_ptr, n: self.title.len() },
            body: ngs_str { p: body_ptr, n: self.body.len() },
            tags: ptr::null(),
            n_tags: 0,
            attrs_cbor: ptr::null(),
            attrs_len: 0,
            schema: self.schema,
            redacted: self.redacted,
        };
        ptr::write(base as *mut ngs_fact, f);
        base as *mut ngs_fact
    }
}

// ---------- Framed Log Codec ----------
fn encode_batch_frame(facts: &[StoredFact]) -> Vec<u8> {
    let mut payload = Vec::new();
    payload.extend_from_slice(&(facts.len() as u32).to_le_bytes());
    for f in facts {
        f.encode(&mut payload);
    }
    let mut frame = Vec::with_capacity(12 + payload.len() + 8);
    frame.extend_from_slice(FRAME_MAGIC);
    frame.extend_from_slice(&FRAME_VERSION.to_le_bytes());
    frame.extend_from_slice(&0u16.to_le_bytes());
    frame.extend_from_slice(&(payload.len() as u32).to_le_bytes());
    frame.extend_from_slice(&payload);
    let c = crc32(&frame);
    frame.extend_from_slice(&c.to_le_bytes());
    frame.extend_from_slice(FRAME_TAIL);
    frame
}

enum ParseLogResult {
    Ok { facts: Vec<StoredFact>, valid_end: u64, had_torn_tail: bool },
    Corrupt,
}

fn parse_log_bytes(data: &[u8]) -> ParseLogResult {
    let mut facts = Vec::new();
    let mut pos: usize = 0;
    let mut expected_seq: u64 = 1;
    let mut expected_prev = ngs_id::default();
    let mut had_torn_tail = false;

    while pos < data.len() {
        let rem = data.len() - pos;
        // Minimum frame: 12 header + 4 n_facts + 4 crc + 4 tail = 24 bytes
        if rem < 12 {
            had_torn_tail = true;
            break;
        }
        if &data[pos..pos + 4] != FRAME_MAGIC {
            // If we have junk at the tail (no subsequent NGSF frame), treat as torn tail.
            // If there IS another NGSF frame later, it's mid-log corruption.
            if data[pos + 4..].windows(4).any(|w| w == FRAME_MAGIC) {
                return ParseLogResult::Corrupt;
            }
            had_torn_tail = true;
            break;
        }
        let ver = u16::from_le_bytes([data[pos + 4], data[pos + 5]]);
        let payload_len = u32::from_le_bytes([data[pos + 8], data[pos + 9], data[pos + 10], data[pos + 11]]) as usize;
        let frame_len = match 12usize.checked_add(payload_len).and_then(|v| v.checked_add(8)) {
            Some(v) => v,
            None => return ParseLogResult::Corrupt,
        };
        if ver != FRAME_VERSION {
            return ParseLogResult::Corrupt;
        }
        if pos + frame_len > data.len() {
            // Truncated frame at EOF = torn tail
            had_torn_tail = true;
            break;
        }
        let frame_slice = &data[pos..pos + frame_len];
        let body_end = 12 + payload_len;
        let stored_crc = u32::from_le_bytes([
            frame_slice[body_end],
            frame_slice[body_end + 1],
            frame_slice[body_end + 2],
            frame_slice[body_end + 3],
        ]);
        let tail = &frame_slice[body_end + 4..body_end + 8];
        let calc_crc = crc32(&frame_slice[..body_end]);

        if tail != FRAME_TAIL || stored_crc != calc_crc {
            // If this is the very last frame at EOF AND tail is not FEND, could be torn tail.
            // If tail IS FEND (frame completed) or there are more bytes after it, it's a bit flip -> CORRUPT!
            if pos + frame_len < data.len() || tail == FRAME_TAIL {
                return ParseLogResult::Corrupt;
            }
            had_torn_tail = true;
            break;
        }

        let payload = &frame_slice[12..body_end];
        if payload.len() < 4 {
            return ParseLogResult::Corrupt;
        }
        let n_facts = u32::from_le_bytes([payload[0], payload[1], payload[2], payload[3]]) as usize;
        let mut ppos = 4usize;
        let mut batch_facts = Vec::with_capacity(n_facts);
        for _ in 0..n_facts {
            let f = match StoredFact::decode(payload, &mut ppos) {
                Some(f) => f,
                None => return ParseLogResult::Corrupt,
            };
            if f.seq != expected_seq || f.prev_id != expected_prev || f.compute_id() != f.id {
                return ParseLogResult::Corrupt;
            }
            expected_seq += 1;
            expected_prev = f.id;
            batch_facts.push(f);
        }
        if ppos != payload.len() {
            return ParseLogResult::Corrupt;
        }
        facts.extend(batch_facts);
        pos += frame_len;
    }

    ParseLogResult::Ok {
        facts,
        valid_end: pos as u64,
        had_torn_tail,
    }
}

// ---------- Database Handle ----------
struct DbInner {
    dir: PathBuf,
    readonly: bool,
    pubkey: ngs_pubkey,
    log_file: Option<File>,
    facts: Vec<StoredFact>,
    index: HashMap<ngs_id, usize>,
    links: Vec<StoredLink>,
    last_id: ngs_id,
    next_seq: u64,
    last_err: CString,
}

pub struct ngs {
    inner: Mutex<DbInner>,
}

pub struct ngs_iter {
    facts: Vec<StoredFact>,
    pos: usize,
}

fn load_or_create_key(dir: &Path, create: bool, supplied_seckey: *const u8) -> Result<ngs_pubkey, c_int> {
    let key_path = dir.join("node.key");
    if key_path.exists() {
        let mut buf = Vec::new();
        File::open(&key_path).map_err(|_| NGS_IOERR)?.read_to_end(&mut buf).map_err(|_| NGS_IOERR)?;
        if buf.len() != 64 {
            return Err(NGS_CORRUPT);
        }
        let mut pk = ngs_pubkey::default();
        pk.b.copy_from_slice(&buf[32..64]);
        return Ok(pk);
    }
    if !create {
        return Err(NGS_NOTFOUND);
    }
    let mut key_bytes = [0u8; 64];
    if !supplied_seckey.is_null() {
        unsafe { ptr::copy_nonoverlapping(supplied_seckey, key_bytes.as_mut_ptr(), 64); }
    } else {
        // Deterministic-free unique key from time + pid + stack addr hashed with SHA-256
        let mut seed = Vec::new();
        seed.extend_from_slice(&now_us().to_le_bytes());
        seed.extend_from_slice(&std::process::id().to_le_bytes());
        let addr = (&seed as *const Vec<u8>) as usize;
        seed.extend_from_slice(&addr.to_le_bytes());
        let sec = sha256(&seed);
        seed.push(0xA5);
        let pubk = sha256(&seed);
        key_bytes[..32].copy_from_slice(&sec);
        key_bytes[32..64].copy_from_slice(&pubk);
    }
    let tmp = dir.join("node.key.tmp");
    {
        let mut f = File::create(&tmp).map_err(|_| NGS_IOERR)?;
        f.write_all(&key_bytes).map_err(|_| NGS_IOERR)?;
        f.sync_all().map_err(|_| NGS_IOERR)?;
    }
    fs::rename(&tmp, &key_path).map_err(|_| NGS_IOERR)?;
    let mut pk = ngs_pubkey::default();
    pk.b.copy_from_slice(&key_bytes[32..64]);
    Ok(pk)
}

unsafe fn str_to_vec(s: ngs_str) -> Result<Vec<u8>, c_int> {
    if s.p.is_null() {
        if s.n != 0 {
            return Err(NGS_MISUSE);
        }
        return Ok(Vec::new());
    }
    Ok(std::slice::from_raw_parts(s.p as *const u8, s.n).to_vec())
}

// ---------- Exported C API ----------
#[no_mangle]
pub extern "C" fn ngs_libversion_number() -> c_int {
    NGS_VERSION_NUMBER
}

#[no_mangle]
pub extern "C" fn ngs_libversion() -> *const c_char {
    b"0.3.1-draft\0".as_ptr() as *const c_char
}

#[no_mangle]
pub extern "C" fn ngs_errstr(rc: c_int) -> *const c_char {
    let s: &'static [u8] = match rc {
        NGS_OK => b"ok\0",
        NGS_ERROR => b"error\0",
        NGS_NOTFOUND => b"not found\0",
        NGS_BUSY => b"busy\0",
        NGS_CORRUPT => b"corrupt\0",
        NGS_NOGRANT => b"no grant\0",
        NGS_MISMATCH => b"mismatch\0",
        NGS_QUARANTINED => b"quarantined\0",
        NGS_NOMEM => b"no memory\0",
        NGS_IOERR => b"io error\0",
        NGS_MISUSE => b"misuse\0",
        NGS_TOOBIG => b"too big\0",
        _ => b"unknown error\0",
    };
    s.as_ptr() as *const c_char
}

#[no_mangle]
pub unsafe extern "C" fn ngs_free(p: *mut c_void) {
    if p.is_null() {
        return;
    }
    let header_size = std::mem::size_of::<AllocHeader>();
    let raw = (p as *mut u8).sub(header_size);
    let hdr = ptr::read(raw as *const AllocHeader);
    if let Ok(layout) = Layout::from_size_align(hdr.total_size, NGS_ALIGN_MAX) {
        dealloc(raw, layout);
    }
}

#[no_mangle]
pub unsafe extern "C" fn ngs_open(
    dir: *const c_char,
    opts: *const ngs_open_opts,
    out: *mut *mut ngs,
) -> c_int {
    if dir.is_null() || out.is_null() {
        return NGS_MISUSE;
    }
    *out = ptr::null_mut();
    let dir_str = match CStr::from_ptr(dir).to_str() {
        Ok(s) => s,
        Err(_) => return NGS_MISUSE,
    };
    let (flags, seckey) = if opts.is_null() {
        (NGS_OPEN_READWRITE, ptr::null())
    } else {
        if ((*opts).size as usize) < std::mem::size_of::<u32>() * 2 {
            return NGS_MISUSE;
        }
        ((*opts).flags, (*opts).node_seckey)
    };
    let readonly = (flags & NGS_OPEN_READONLY) != 0 && (flags & NGS_OPEN_READWRITE) == 0;
    let create = (flags & NGS_OPEN_CREATE) != 0 && !readonly;

    let dir_path = PathBuf::from(dir_str);
    if create {
        if fs::create_dir_all(&dir_path).is_err() {
            return NGS_IOERR;
        }
    } else if !dir_path.is_dir() {
        return NGS_NOTFOUND;
    }

    let pubkey = match load_or_create_key(&dir_path, create, seckey) {
        Ok(pk) => pk,
        Err(rc) => return rc,
    };

    let log_path = dir_path.join("ngs.log");
    let mut raw_bytes = Vec::new();
    if log_path.exists() {
        match File::open(&log_path).and_then(|mut f| f.read_to_end(&mut raw_bytes)) {
            Ok(_) => {}
            Err(_) => return NGS_IOERR,
        }
    } else if !create {
        return NGS_NOTFOUND;
    }

    let (facts, valid_end, had_torn_tail) = match parse_log_bytes(&raw_bytes) {
        ParseLogResult::Ok { facts, valid_end, had_torn_tail } => (facts, valid_end, had_torn_tail),
        ParseLogResult::Corrupt => return NGS_CORRUPT,
    };

    let log_file = if readonly {
        None
    } else {
        let mut f = match OpenOptions::new().read(true).write(true).create(true).open(&log_path) {
            Ok(f) => f,
            Err(_) => return NGS_IOERR,
        };
        if had_torn_tail {
            if f.set_len(valid_end).is_err() || f.sync_data().is_err() {
                return NGS_IOERR;
            }
        }
        if f.seek(SeekFrom::End(0)).is_err() {
            return NGS_IOERR;
        }
        Some(f)
    };

    let mut index = HashMap::with_capacity(facts.len());
    for (i, f) in facts.iter().enumerate() {
        index.insert(f.id, i);
    }
    let last_id = facts.last().map(|f| f.id).unwrap_or_default();
    let next_seq = facts.last().map(|f| f.seq + 1).unwrap_or(1);

    let db = Box::new(ngs {
        inner: Mutex::new(DbInner {
            dir: dir_path,
            readonly,
            pubkey,
            log_file,
            facts,
            index,
            links: Vec::new(),
            last_id,
            next_seq,
            last_err: CString::new("").unwrap(),
        }),
    });
    *out = Box::into_raw(db);
    NGS_OK
}

#[no_mangle]
pub unsafe extern "C" fn ngs_close(db: *mut ngs) -> c_int {
    if db.is_null() {
        return NGS_OK;
    }
    let boxed = Box::from_raw(db);
    if let Ok(mut g) = boxed.inner.lock() {
        if let Some(ref mut f) = g.log_file {
            let _ = f.sync_data();
        }
    }
    NGS_OK
}

#[no_mangle]
pub unsafe extern "C" fn ngs_errmsg(db: *mut ngs) -> *const c_char {
    if db.is_null() {
        return b"\0".as_ptr() as *const c_char;
    }
    if let Ok(g) = (*db).inner.lock() {
        return g.last_err.as_ptr();
    }
    b"\0".as_ptr() as *const c_char
}

#[no_mangle]
pub unsafe extern "C" fn ngs_node_pubkey(db: *mut ngs, out: *mut ngs_pubkey) -> c_int {
    if db.is_null() || out.is_null() {
        return NGS_MISUSE;
    }
    let g = match (*db).inner.lock() {
        Ok(g) => g,
        Err(_) => return NGS_ERROR,
    };
    *out = g.pubkey;
    NGS_OK
}

#[no_mangle]
pub unsafe extern "C" fn ngs_flush(db: *mut ngs) -> c_int {
    if db.is_null() {
        return NGS_MISUSE;
    }
    let mut g = match (*db).inner.lock() {
        Ok(g) => g,
        Err(_) => return NGS_ERROR,
    };
    if let Some(ref mut f) = g.log_file {
        if f.sync_data().is_err() {
            return NGS_IOERR;
        }
    }
    NGS_OK
}

unsafe fn parse_vec(v: &ngs_vec) -> Result<StoredVec, c_int> {
    if v.dim == 0 || (v.dim as usize) > NGS_MAX_DIM || v.v.is_null() {
        return Err(NGS_MISUSE);
    }
    let model_id = str_to_vec(v.model_id)?;
    let slice = std::slice::from_raw_parts(v.v, v.dim as usize);
    for &x in slice {
        if x.is_nan() || x.is_infinite() {
            return Err(NGS_MISUSE);
        }
    }
    Ok(StoredVec {
        model_id,
        dim: v.dim,
        version: v.version,
        v: slice.to_vec(),
    })
}

unsafe fn validate_fact_in(fin: &ngs_fact_in) -> Result<(Vec<u8>, Vec<u8>, Vec<u8>, Vec<StoredVec>), c_int> {
    if (fin.size as usize) < std::mem::size_of::<ngs_fact_in>() {
        return Err(NGS_MISUSE);
    }
    if fin.kind != NGS_EPISODIC && fin.kind != NGS_SEMANTIC && fin.kind != NGS_PROCEDURAL {
        return Err(NGS_MISUSE);
    }
    if fin.salience0.is_nan() || fin.salience0.is_infinite() {
        return Err(NGS_MISUSE);
    }
    let ns = str_to_vec(fin.ns)?;
    let title = str_to_vec(fin.title)?;
    let body = str_to_vec(fin.body)?;
    if ns.len() > NGS_MAX_NS_LEN || title.len() > NGS_MAX_TITLE_LEN || fin.attrs_len > NGS_MAX_ATTRS_LEN {
        return Err(NGS_TOOBIG);
    }
    let mut vecs = Vec::with_capacity(fin.n_vecs);
    if fin.n_vecs > 0 {
        if fin.vecs.is_null() {
            return Err(NGS_MISUSE);
        }
        let vslice = std::slice::from_raw_parts(fin.vecs, fin.n_vecs);
        for item in vslice {
            vecs.push(parse_vec(item)?);
        }
    }
    Ok((ns, title, body, vecs))
}

#[no_mangle]
pub unsafe extern "C" fn ngs_remember(
    db: *mut ngs,
    fin: *const ngs_fact_in,
    flags: i32,
    out_id: *mut ngs_id,
) -> c_int {
    if fin.is_null() {
        return NGS_MISUSE;
    }
    ngs_remember_many(db, fin, 1, flags, out_id)
}

#[no_mangle]
pub unsafe extern "C" fn ngs_remember_many(
    db: *mut ngs,
    fin: *const ngs_fact_in,
    n: usize,
    flags: i32,
    out_ids: *mut ngs_id,
) -> c_int {
    if db.is_null() || (n > 0 && fin.is_null()) {
        return NGS_MISUSE;
    }
    if n == 0 {
        return NGS_OK;
    }
    let inputs = std::slice::from_raw_parts(fin, n);
    let mut parsed = Vec::with_capacity(n);
    for item in inputs {
        match validate_fact_in(item) {
            Ok(v) => parsed.push((item, v)),
            Err(rc) => return rc,
        }
    }

    let mut g = match (*db).inner.lock() {
        Ok(g) => g,
        Err(_) => return NGS_ERROR,
    };
    if g.readonly {
        return NGS_NOGRANT;
    }

    let t_rec = now_us();
    let mut prev_id = g.last_id;
    let mut seq = g.next_seq;
    let mut new_facts = Vec::with_capacity(n);

    let mut invalidated: Vec<(ngs_id, ngs_id, i64)> = Vec::new();
    for (item, (ns, title, body, vecs)) in parsed {
        let t_ev = if item.t_event == NGS_TIME_NOW { t_rec } else { item.t_event };
        let v_from = if item.valid_from == NGS_TIME_NOW { t_ev } else { item.valid_from };
        let mut f = StoredFact {
            id: ngs_id::default(),
            prev_id,
            writer: g.pubkey,
            seq,
            t_event: t_ev,
            t_record: t_rec,
            valid_from: v_from,
            valid_to: NGS_TIME_MAX,
            kind: item.kind,
            schema: item.schema,
            redacted: 0,
            ns,
            title,
            body,
            vecs,
        };
        f.id = f.compute_id();
        if !item.supersedes.is_null() {
            invalidated.push((*item.supersedes, f.id, t_rec));
        }
        prev_id = f.id;
        seq += 1;
        new_facts.push(f);
    }

    let frame = encode_batch_frame(&new_facts);
    if let Some(ref mut file) = g.log_file {
        if file.seek(SeekFrom::End(0)).is_err() || file.write_all(&frame).is_err() {
            return NGS_IOERR;
        }
        if (flags & NGS_WRITE_NO_SYNC) == 0 {
            if file.sync_data().is_err() {
                return NGS_IOERR;
            }
        }
    } else {
        return NGS_NOGRANT;
    }

    for (i, f) in new_facts.into_iter().enumerate() {
        if !out_ids.is_null() {
            *out_ids.add(i) = f.id;
        }
        let idx = g.facts.len();
        g.index.insert(f.id, idx);
        g.facts.push(f);
    }
    for (old_id, _new_id, ts) in invalidated {
        if let Some(&idx) = g.index.get(&old_id) {
            g.facts[idx].valid_to = ts;
        }
    }
    g.last_id = prev_id;
    g.next_seq = seq;
    NGS_OK
}

#[no_mangle]
pub unsafe extern "C" fn ngs_get(
    db: *mut ngs,
    id: *const ngs_id,
    out: *mut *mut ngs_fact,
) -> c_int {
    if db.is_null() || id.is_null() || out.is_null() {
        return NGS_MISUSE;
    }
    *out = ptr::null_mut();
    let g = match (*db).inner.lock() {
        Ok(g) => g,
        Err(_) => return NGS_ERROR,
    };
    let idx = match g.index.get(&*id) {
        Some(&i) => i,
        None => return NGS_NOTFOUND,
    };
    let ptr_f = g.facts[idx].to_c_fact();
    if ptr_f.is_null() {
        return NGS_NOMEM;
    }
    *out = ptr_f;
    NGS_OK
}

#[no_mangle]
pub unsafe extern "C" fn ngs_scan(
    db: *mut ngs,
    opts: *const ngs_scan_opts,
    out_it: *mut *mut ngs_iter,
) -> c_int {
    if db.is_null() || out_it.is_null() {
        return NGS_MISUSE;
    }
    *out_it = ptr::null_mut();
    let (ns_filter, writer_filter, since, until) = if opts.is_null() {
        (Vec::new(), None, NGS_TIME_MIN, NGS_TIME_MAX)
    } else {
        if ((*opts).size as usize) < std::mem::size_of::<u32>() {
            return NGS_MISUSE;
        }
        let nsf = match str_to_vec((*opts).ns) {
            Ok(v) => v,
            Err(rc) => return rc,
        };
        let wf = if (*opts).writer.is_null() { None } else { Some(*(*opts).writer) };
        (nsf, wf, (*opts).since, (*opts).until)
    };

    let g = match (*db).inner.lock() {
        Ok(g) => g,
        Err(_) => return NGS_ERROR,
    };
    let mut matched = Vec::new();
    for f in &g.facts {
        if !ns_filter.is_empty() && f.ns != ns_filter {
            continue;
        }
        if let Some(w) = writer_filter {
            if f.writer != w {
                continue;
            }
        }
        if f.t_record < since || f.t_record > until {
            continue;
        }
        matched.push(f.clone());
    }
    *out_it = Box::into_raw(Box::new(ngs_iter { facts: matched, pos: 0 }));
    NGS_OK
}

#[no_mangle]
pub unsafe extern "C" fn ngs_iter_next(it: *mut ngs_iter, out: *mut *mut ngs_fact) -> c_int {
    if it.is_null() || out.is_null() {
        return NGS_MISUSE;
    }
    *out = ptr::null_mut();
    let iter = &mut *it;
    if iter.pos >= iter.facts.len() {
        return NGS_NOTFOUND;
    }
    let ptr_f = iter.facts[iter.pos].to_c_fact();
    if ptr_f.is_null() {
        return NGS_NOMEM;
    }
    iter.pos += 1;
    *out = ptr_f;
    NGS_OK
}

#[no_mangle]
pub unsafe extern "C" fn ngs_iter_close(it: *mut ngs_iter) {
    if !it.is_null() {
        let _ = Box::from_raw(it);
    }
}

#[no_mangle]
pub unsafe extern "C" fn ngs_verify(
    db: *mut ngs,
    _ckpt: *const u8,
    _len: usize,
) -> c_int {
    if db.is_null() {
        return NGS_MISUSE;
    }
    let g = match (*db).inner.lock() {
        Ok(g) => g,
        Err(_) => return NGS_ERROR,
    };
    let log_path = g.dir.join("ngs.log");
    let mut raw = Vec::new();
    if log_path.exists() {
        if File::open(&log_path).and_then(|mut f| f.read_to_end(&mut raw)).is_err() {
            return NGS_IOERR;
        }
    }
    match parse_log_bytes(&raw) {
        ParseLogResult::Ok { facts, had_torn_tail, .. } => {
            if had_torn_tail || facts.len() != g.facts.len() {
                return NGS_CORRUPT;
            }
            NGS_OK
        }
        ParseLogResult::Corrupt => NGS_CORRUPT,
    }
}

fn tokenize_lower(bytes: &[u8]) -> Vec<String> {
    let s = String::from_utf8_lossy(bytes).to_lowercase();
    s.split(|c: char| !c.is_alphanumeric() && c != '_' && c != '-')
        .filter(|t| !t.is_empty())
        .map(|t| t.to_string())
        .collect()
}

fn estimate_tokens(title: &[u8], body: &[u8]) -> u32 {
    (((title.len() + body.len()) as u32) + 3) / 4
}

#[no_mangle]
pub unsafe extern "C" fn ngs_invalidate(db: *mut ngs, id: *const ngs_id, _reason: ngs_str) -> c_int {
    if db.is_null() || id.is_null() {
        return NGS_MISUSE;
    }
    let mut g = match (*db).inner.lock() {
        Ok(g) => g,
        Err(_) => return NGS_ERROR,
    };
    if g.readonly {
        return NGS_NOGRANT;
    }
    let target = *id;
    if let Some(&idx) = g.index.get(&target) {
        g.facts[idx].valid_to = now_us();
        return NGS_OK;
    }
    for link in &mut g.links {
        if link.id == target {
            link.valid = false;
            return NGS_OK;
        }
    }
    NGS_NOTFOUND
}

#[no_mangle]
pub unsafe extern "C" fn ngs_link(
    db: *mut ngs,
    a: *const ngs_id,
    b: *const ngs_id,
    rel: ngs_str,
    weight: f32,
    out_link_id: *mut ngs_id,
) -> c_int {
    if db.is_null() || a.is_null() || b.is_null() || weight.is_nan() || weight.is_infinite() {
        return NGS_MISUSE;
    }
    let rel_bytes = match str_to_vec(rel) {
        Ok(v) => v,
        Err(rc) => return rc,
    };
    let mut g = match (*db).inner.lock() {
        Ok(g) => g,
        Err(_) => return NGS_ERROR,
    };
    if g.readonly {
        return NGS_NOGRANT;
    }
    let mut buf = Vec::with_capacity(80 + rel_bytes.len());
    buf.extend_from_slice(b"NGS-LINK-V1");
    buf.extend_from_slice(&(*a).b);
    buf.extend_from_slice(&(*b).b);
    buf.extend_from_slice(&rel_bytes);
    buf.extend_from_slice(&now_us().to_le_bytes());
    let link_id = ngs_id { b: sha256(&buf) };
    g.links.push(StoredLink {
        id: link_id,
        a: *a,
        b: *b,
        rel: rel_bytes,
        weight: weight.clamp(0.0, 1.0),
        valid: true,
    });
    if !out_link_id.is_null() {
        *out_link_id = link_id;
    }
    NGS_OK
}

#[no_mangle]
pub unsafe extern "C" fn ngs_recall(
    db: *mut ngs,
    q: *const ngs_query,
    out: *mut *mut ngs_results,
) -> c_int {
    if db.is_null() || q.is_null() || out.is_null() {
        return NGS_MISUSE;
    }
    *out = ptr::null_mut();
    let qref = &*q;
    if (qref.size as usize) < std::mem::size_of::<ngs_query>() {
        return NGS_MISUSE;
    }
    if qref.min_confidence.is_nan() || qref.min_confidence.is_infinite() {
        return NGS_MISUSE;
    }
    let weights: [f32; NGS_N_ARMS] = if qref.weights.is_null() {
        [0.35, 0.45, 0.10, 0.10, 0.0]
    } else {
        let ws = std::slice::from_raw_parts(qref.weights, NGS_N_ARMS);
        for &w in ws {
            if w.is_nan() || w.is_infinite() {
                return NGS_MISUSE;
            }
        }
        [ws[0], ws[1], ws[2], ws[3], ws[4]]
    };

    let ns_filter = match str_to_vec(qref.ns) {
        Ok(v) => v,
        Err(rc) => return rc,
    };
    let text_bytes = match str_to_vec(qref.text) {
        Ok(v) => v,
        Err(rc) => return rc,
    };
    let q_vec = if qref.vec.is_null() {
        None
    } else {
        match parse_vec(&*qref.vec) {
            Ok(v) => Some(v),
            Err(rc) => return rc,
        }
    };
    let q_tokens = tokenize_lower(&text_bytes);
    let k = if qref.k == 0 { 10usize } else { qref.k as usize };
    let deadline_ms = if qref.deadline_ms == 0 { 50u64 } else { qref.deadline_ms as u64 };
    let min_conf = if qref.min_confidence < 0.0 { 0.35f32 } else { qref.min_confidence };
    let expand_links = (qref.flags & NGS_RECALL_EXPAND) != 0;
    let include_invalid = (qref.flags & NGS_RECALL_INCLUDE_INVALID) != 0;
    let no_body = (qref.flags & NGS_RECALL_NO_BODY) != 0;

    let started = Instant::now();
    let now = now_us();

    let g = match (*db).inner.lock() {
        Ok(g) => g,
        Err(_) => return NGS_ERROR,
    };

    struct Scored<'a> {
        fact: &'a StoredFact,
        score: f32,
        arm: [f32; NGS_N_ARMS],
        invalid: i32,
    }

    let mut candidates: Vec<Scored> = Vec::new();
    let mut timed_out = 0i32;

    for f in &g.facts {
        if started.elapsed().as_millis() as u64 >= deadline_ms {
            timed_out = 1;
            break;
        }
        let is_invalid = if f.valid_to != NGS_TIME_MAX { 1 } else { 0 };
        if is_invalid != 0 && !include_invalid {
            continue;
        }
        if !ns_filter.is_empty() && f.ns != ns_filter {
            continue;
        }
        if qref.kinds != 0 && (qref.kinds & (1u32 << (f.kind as u32))) == 0 {
            continue;
        }
        if f.t_event < qref.since || f.t_event > qref.until {
            continue;
        }

        // Keyword arm: fraction of query tokens matched in title (2x) or body (1x)
        let kw_score = if q_tokens.is_empty() {
            0.0f32
        } else {
            let t_toks = tokenize_lower(&f.title);
            let b_toks = tokenize_lower(&f.body);
            let mut hits = 0.0f32;
            for qt in &q_tokens {
                if t_toks.iter().any(|x| x == qt) {
                    hits += 1.0;
                } else if b_toks.iter().any(|x| x == qt) {
                    hits += 0.8;
                }
            }
            (hits / (q_tokens.len() as f32)).min(1.0)
        };

        // Vector arm: cosine/dot similarity against matching (model_id, dim, version)
        let vec_score = if let Some(ref qv) = q_vec {
            let mut best_sim = 0.0f32;
            for fv in &f.vecs {
                if fv.dim == qv.dim && fv.version == qv.version && fv.model_id == qv.model_id {
                    let dot: f32 = qv.v.iter().zip(fv.v.iter()).map(|(a, b)| a * b).sum();
                    if dot > best_sim {
                        best_sim = dot;
                    }
                }
            }
            best_sim.clamp(0.0, 1.0)
        } else {
            0.0f32
        };

        // Recency arm: smooth decay over age in days
        let age_us = now.saturating_sub(f.t_event).max(0) as f64;
        let age_days = age_us / 86_400_000_000.0;
        let recency_score = (1.0 / (1.0 + age_days / 30.0)) as f32;

        // Salience arm: default 0.5
        let salience_score = 0.5f32;

        let arm = [vec_score, kw_score, recency_score, salience_score, 0.0f32];
        let w_vec = if q_vec.is_some() { weights[NGS_ARM_VEC] } else { 0.0 };
        let w_kw = if !q_tokens.is_empty() { weights[NGS_ARM_KW] } else { 0.0 };
        let denom = w_vec + w_kw + weights[NGS_ARM_RECENCY] + weights[NGS_ARM_SALIENCE];
        let score = if denom > 0.0 {
            (arm[NGS_ARM_VEC] * w_vec
                + arm[NGS_ARM_KW] * w_kw
                + arm[NGS_ARM_RECENCY] * weights[NGS_ARM_RECENCY]
                + arm[NGS_ARM_SALIENCE] * weights[NGS_ARM_SALIENCE])
                / denom
        } else {
            kw_score.max(vec_score)
        };

        let has_signal = (q_tokens.is_empty() && q_vec.is_none()) || kw_score > 0.0 || vec_score > 0.0;
        if !has_signal {
            continue;
        }
        candidates.push(Scored { fact: f, score, arm, invalid: is_invalid });
    }

    // 1-hop link expansion (NGS_RECALL_EXPAND)
    if expand_links && timed_out == 0 && !candidates.is_empty() {
        let seed_ids: Vec<(ngs_id, f32)> = candidates.iter().take(k).map(|c| (c.fact.id, c.score)).collect();
        let mut boost: HashMap<ngs_id, f32> = HashMap::new();
        for (sid, sscore) in &seed_ids {
            for link in &g.links {
                if !link.valid {
                    continue;
                }
                let neighbor = if link.a == *sid {
                    Some(link.b)
                } else if link.b == *sid {
                    Some(link.a)
                } else {
                    None
                };
                if let Some(nid) = neighbor {
                    let bval = (sscore * link.weight).clamp(0.0, 1.0);
                    let entry = boost.entry(nid).or_insert(0.0);
                    if bval > *entry {
                        *entry = bval;
                    }
                }
            }
        }
        for (nid, lscore) in boost {
            if let Some(existing) = candidates.iter_mut().find(|c| c.fact.id == nid) {
                existing.arm[NGS_ARM_LINK] = lscore;
                existing.score = (existing.score + lscore * 0.25).min(1.0);
            } else if let Some(&fidx) = g.index.get(&nid) {
                let f = &g.facts[fidx];
                let is_invalid = if f.valid_to != NGS_TIME_MAX { 1 } else { 0 };
                if is_invalid != 0 && !include_invalid {
                    continue;
                }
                let arm = [0.0, 0.0, 0.5, 0.5, lscore];
                candidates.push(Scored { fact: f, score: (lscore * 0.85).clamp(0.0, 1.0), arm, invalid: is_invalid });
            }
        }
    }

    candidates.sort_by(|a, b| b.score.partial_cmp(&a.score).unwrap_or(std::cmp::Ordering::Equal));
    candidates.truncate(k);

    // Token budget packing
    let mut selected: Vec<(usize, bool, u32)> = Vec::new();
    let mut tokens_used: u32 = 0;
    for (idx, c) in candidates.iter().enumerate() {
        let full_toks = if no_body {
            estimate_tokens(&c.fact.title, &[])
        } else {
            estimate_tokens(&c.fact.title, &c.fact.body)
        };
        let stub_toks = estimate_tokens(&c.fact.title, &[]);
        if qref.token_budget > 0 {
            if tokens_used + full_toks <= qref.token_budget {
                tokens_used += full_toks;
                selected.push((idx, no_body, full_toks));
            } else if tokens_used + stub_toks <= qref.token_budget {
                tokens_used += stub_toks;
                selected.push((idx, true, stub_toks));
            } else {
                break;
            }
        } else {
            tokens_used += full_toks;
            selected.push((idx, no_body, full_toks));
        }
    }

    let best_conf = candidates.first().map(|c| c.score.clamp(0.0, 1.0)).unwrap_or(0.0);
    let abstained = if best_conf < min_conf { 1 } else { 0 };
    let arms_complete = if timed_out != 0 {
        0u32
    } else {
        let mut mask = (1u32 << NGS_ARM_KW) | (1u32 << NGS_ARM_RECENCY) | (1u32 << NGS_ARM_SALIENCE);
        if q_vec.is_some() {
            mask |= 1u32 << NGS_ARM_VEC;
        }
        if expand_links {
            mask |= 1u32 << NGS_ARM_LINK;
        }
        mask
    };
    let elapsed_us = started.elapsed().as_micros().min(u32::MAX as u128) as u32;

    // Pack ngs_results + ngs_hit[] + all string bytes into ONE 16-byte-aligned allocation
    let res_sz = (std::mem::size_of::<ngs_results>() + 15) & !15;
    let hits_sz = (selected.len() * std::mem::size_of::<ngs_hit>() + 15) & !15;
    let mut str_sz = 0usize;
    for &(idx, is_stub, _) in &selected {
        let f = candidates[idx].fact;
        str_sz += f.ns.len() + f.title.len() + if is_stub { 0 } else { f.body.len() };
    }
    let base = ngs_alloc_block(res_sz + hits_sz + str_sz);
    if base.is_null() {
        return NGS_NOMEM;
    }

    let hits_ptr = if selected.is_empty() {
        ptr::null_mut()
    } else {
        base.add(res_sz) as *mut ngs_hit
    };
    let mut scursor = base.add(res_sz + hits_sz);

    for (out_i, &(idx, is_stub, toks)) in selected.iter().enumerate() {
        let c = &candidates[idx];
        let f = c.fact;
        let ns_p = if f.ns.is_empty() {
            ptr::null()
        } else {
            ptr::copy_nonoverlapping(f.ns.as_ptr(), scursor, f.ns.len());
            let p = scursor as *const c_char;
            scursor = scursor.add(f.ns.len());
            p
        };
        let title_p = if f.title.is_empty() {
            ptr::null()
        } else {
            ptr::copy_nonoverlapping(f.title.as_ptr(), scursor, f.title.len());
            let p = scursor as *const c_char;
            scursor = scursor.add(f.title.len());
            p
        };
        let (body_p, body_n) = if is_stub || f.body.is_empty() {
            (ptr::null(), 0)
        } else {
            ptr::copy_nonoverlapping(f.body.as_ptr(), scursor, f.body.len());
            let p = scursor as *const c_char;
            scursor = scursor.add(f.body.len());
            (p, f.body.len())
        };

        ptr::write(
            hits_ptr.add(out_i),
            ngs_hit {
                size: std::mem::size_of::<ngs_hit>() as u32,
                id: f.id,
                kind: f.kind,
                ns: ngs_str { p: ns_p, n: f.ns.len() },
                title: ngs_str { p: title_p, n: f.title.len() },
                body: ngs_str { p: body_p, n: body_n },
                score: c.score,
                arm: c.arm,
                invalid: c.invalid,
                confidence: c.score.clamp(0.0, 1.0),
                tokens: toks,
                stub: if is_stub { 1 } else { 0 },
                tokens_estimated: 1,
            },
        );
    }

    ptr::write(
        base as *mut ngs_results,
        ngs_results {
            size: std::mem::size_of::<ngs_results>() as u32,
            hits: hits_ptr,
            n: selected.len(),
            arms_complete,
            timed_out,
            elapsed_us,
            abstained,
            confidence_calibrated: 0,
            best_confidence: best_conf,
            min_confidence: min_conf,
            tokens_used,
            tokens_budget: qref.token_budget,
        },
    );

    *out = base as *mut ngs_results;
    NGS_OK
}

// ---------- Outside-M3 Stubs (clean NGS_MISUSE) ----------
#[no_mangle]
pub extern "C" fn ngs_redact(_db: *mut ngs, _id: *const ngs_id, _reason: ngs_str) -> c_int { NGS_MISUSE }
#[no_mangle]
pub extern "C" fn ngs_grant(_db: *mut ngs, _ns: ngs_str, _writer: *const ngs_pubkey, _out: *mut ngs_id) -> c_int { NGS_MISUSE }
#[no_mangle]
pub extern "C" fn ngs_as_of(_db: *mut ngs, _tv: i64, _tr: i64, _q: *const c_void, _out: *mut *mut c_void) -> c_int { NGS_MISUSE }
#[no_mangle]
pub extern "C" fn ngs_mark(_db: *mut ngs, _id: *const ngs_id, _mark: i32) -> c_int { NGS_MISUSE }
#[no_mangle]
pub extern "C" fn ngs_checkpoint(_db: *mut ngs, _ckpt: *mut *mut u8, _len: *mut usize) -> c_int { NGS_MISUSE }
#[no_mangle]
pub extern "C" fn ngs_rebuild(_db: *mut ngs) -> c_int { NGS_MISUSE }
#[no_mangle]
pub extern "C" fn ngs_heads(_db: *mut ngs, _heads: *mut *mut c_void, _n: *mut usize) -> c_int { NGS_MISUSE }
#[no_mangle]
pub extern "C" fn ngs_sync_export(_db: *mut ngs, _since: *const c_void, _n: usize, _seg: *mut *mut u8, _len: *mut usize) -> c_int { NGS_MISUSE }
#[no_mangle]
pub extern "C" fn ngs_sync_import(_db: *mut ngs, _seg: *const u8, _len: usize, _rep: *mut *mut c_void) -> c_int { NGS_MISUSE }
#[no_mangle]
pub extern "C" fn ngs_stats(_db: *mut ngs, _out: *mut c_void) -> c_int { NGS_MISUSE }
