use std::ffi::CString;
use std::fs::{self, OpenOptions};
use std::io::{Read, Seek, SeekFrom, Write};
use std::os::raw::c_char;
use std::path::PathBuf;
use std::ptr;

use ::ngs::{
    ngs as NgsDb, ngs_as_of, ngs_checkpoint, ngs_close, ngs_fact, ngs_fact_in, ngs_flush, ngs_free,
    ngs_get, ngs_grant, ngs_head, ngs_heads, ngs_id, ngs_iter, ngs_iter_close, ngs_iter_next,
    ngs_link, ngs_mark, ngs_node_pubkey, ngs_open, ngs_open_opts, ngs_pubkey, ngs_query,
    ngs_rebuild, ngs_recall, ngs_redact, ngs_remember, ngs_remember_many, ngs_results, ngs_scan,
    ngs_scan_opts, ngs_stats, ngs_stats_t, ngs_str, ngs_sync_export, ngs_sync_import,
    ngs_sync_report, ngs_vec, ngs_verify, NGS_ARM_KW, NGS_ARM_LINK, NGS_ARM_SALIENCE, NGS_ARM_VEC,
    NGS_CORRUPT, NGS_EPISODIC, NGS_MARK_NOT_USED, NGS_MARK_USED, NGS_MISUSE, NGS_NOTFOUND, NGS_OK,
    NGS_OPEN_CREATE, NGS_OPEN_READONLY, NGS_OPEN_READWRITE, NGS_PROCEDURAL, NGS_QUARANTINED,
    NGS_RECALL_EXPAND, NGS_RECALL_INCLUDE_INVALID, NGS_SEMANTIC, NGS_TIME_MAX, NGS_TIME_MIN,
    NGS_TIME_NOW,
};

fn s(val: &str) -> ngs_str {
    ngs_str { p: val.as_ptr() as *const c_char, n: val.len() }
}

unsafe fn str_eq(a: ngs_str, b: &str) -> bool {
    if a.n != b.len() {
        return false;
    }
    if a.n == 0 {
        return true;
    }
    std::slice::from_raw_parts(a.p as *const u8, a.n) == b.as_bytes()
}

fn id_zero(id: &ngs_id) -> bool {
    id.b.iter().all(|&x| x == 0)
}

fn make_fact_in(ns: &str, kind: i32, title: &str, body: &str) -> ngs_fact_in {
    ngs_fact_in {
        size: std::mem::size_of::<ngs_fact_in>() as u32,
        ns: s(ns),
        kind,
        t_event: NGS_TIME_NOW,
        valid_from: NGS_TIME_NOW,
        title: s(title),
        body: s(body),
        tags: ptr::null(),
        n_tags: 0,
        attrs_cbor: ptr::null(),
        attrs_len: 0,
        schema: 0,
        vecs: ptr::null(),
        n_vecs: 0,
        supersedes: ptr::null(),
        salience0: -1.0,
        tokenizer_ids: ptr::null(),
        token_counts: ptr::null(),
        n_token_counts: 0,
    }
}

fn open_opts(flags: i32) -> ngs_open_opts {
    ngs_open_opts {
        size: std::mem::size_of::<ngs_open_opts>() as u32,
        flags,
        node_seckey: ptr::null(),
        segment_bytes: 0,
        group_commit_ms: 0,
        checkpoint_every: 0,
        shard_vec_split: 0,
        root_pubkey: ptr::null(),
    }
}

fn scratch_dir(name: &str) -> PathBuf {
    let p = std::env::temp_dir().join(format!("ngs_blade_{}_{}", name, std::process::id()));
    let _ = fs::remove_dir_all(&p);
    fs::create_dir_all(&p).unwrap();
    p
}

#[test]
fn m1_behaviour_conformance_full() {
    unsafe {
        let dir = scratch_dir("behaviour");
        let dir_c = CString::new(dir.to_str().unwrap()).unwrap();
        let mut db: *mut NgsDb = ptr::null_mut();

        // open_create
        let o = open_opts(NGS_OPEN_READWRITE | NGS_OPEN_CREATE);
        assert_eq!(ngs_open(dir_c.as_ptr(), &o, &mut db), NGS_OK);
        assert!(!db.is_null());

        // node_pubkey_nonzero
        let mut pk = ngs_pubkey::default();
        assert_eq!(ngs_node_pubkey(db, &mut pk), NGS_OK);
        assert!(pk.b.iter().any(|&b| b != 0));

        // remember_one + get_round_trip + get_valid_to_open
        let mut id1 = ngs_id::default();
        let fin = make_fact_in("bench", NGS_SEMANTIC, "first", "the body, verbatim");
        assert_eq!(ngs_remember(db, &fin, 0, &mut id1), NGS_OK);
        assert!(!id_zero(&id1));

        let mut f: *mut ngs_fact = ptr::null_mut();
        assert_eq!(ngs_get(db, &id1, &mut f), NGS_OK);
        assert!(!f.is_null());
        assert_eq!((*f).id, id1);
        assert!(str_eq((*f).ns, "bench"));
        assert_eq!((*f).kind, NGS_SEMANTIC);
        assert!(str_eq((*f).title, "first"));
        assert!(str_eq((*f).body, "the body, verbatim"));
        assert_eq!((*f).redacted, 0);
        assert_eq!((*f).valid_to, NGS_TIME_MAX);
        ngs_free(f as *mut _);

        // ids_unique_for_same_content
        let mut id1b = ngs_id::default();
        assert_eq!(ngs_remember(db, &fin, 0, &mut id1b), NGS_OK);
        assert_ne!(id1, id1b);

        // get_unknown_notfound
        let probe = ngs_id { b: [0x5a; 32] };
        let mut f2: *mut ngs_fact = ptr::null_mut();
        assert_eq!(ngs_get(db, &probe, &mut f2), NGS_NOTFOUND);

        // input validation: kind=0 -> NGS_MISUSE, bad size -> NGS_MISUSE
        let mut bad = make_fact_in("bench", 0, "", "x");
        let mut dummy = ngs_id::default();
        assert_eq!(ngs_remember(db, &bad, 0, &mut dummy), NGS_MISUSE);
        bad.kind = NGS_EPISODIC;
        bad.size = 4;
        assert_eq!(ngs_remember(db, &bad, 0, &mut dummy), NGS_MISUSE);

        // remember_many (50 facts)
        const N_MANY: usize = 50;
        let titles: Vec<String> = (0..N_MANY).map(|i| format!("many-{:02}", i)).collect();
        let batch: Vec<ngs_fact_in> = titles
            .iter()
            .map(|t| make_fact_in("bench", NGS_EPISODIC, t, t))
            .collect();
        let mut many_ids = vec![ngs_id::default(); N_MANY];
        assert_eq!(ngs_remember_many(db, batch.as_ptr(), N_MANY, 0, many_ids.as_mut_ptr()), NGS_OK);
        for i in 0..N_MANY {
            assert!(!id_zero(&many_ids[i]));
            for j in 0..i {
                assert_ne!(many_ids[i], many_ids[j]);
            }
        }

        // flush
        assert_eq!(ngs_flush(db), NGS_OK);

        // scan: all facts, gapless increasing seq
        let so = ngs_scan_opts {
            size: std::mem::size_of::<ngs_scan_opts>() as u32,
            ns: ngs_str { p: ptr::null(), n: 0 },
            writer: ptr::null(),
            since: NGS_TIME_MIN,
            until: NGS_TIME_MAX,
            include_derived: 0,
        };
        let mut it: *mut ngs_iter = ptr::null_mut();
        assert_eq!(ngs_scan(db, &so, &mut it), NGS_OK);
        let mut seen = 0usize;
        let mut seen_many = 0usize;
        let mut last_seq = 0u64;
        loop {
            let mut sf: *mut ngs_fact = ptr::null_mut();
            let rc = ngs_iter_next(it, &mut sf);
            if rc == NGS_NOTFOUND {
                break;
            }
            assert_eq!(rc, NGS_OK);
            if seen > 0 {
                assert_eq!((*sf).seq, last_seq + 1);
            }
            last_seq = (*sf).seq;
            if (*sf).title.n >= 5 && std::slice::from_raw_parts((*sf).title.p as *const u8, 5) == b"many-" {
                seen_many += 1;
            }
            seen += 1;
            ngs_free(sf as *mut _);
        }
        ngs_iter_close(it);
        assert_eq!(seen, 2 + N_MANY);
        assert_eq!(seen_many, N_MANY);

        // verify_clean
        assert_eq!(ngs_verify(db, ptr::null(), 0), NGS_OK);

        // null query returns NGS_MISUSE
        let mut r: *mut ngs_results = ptr::null_mut();
        assert_eq!(ngs_recall(db, ptr::null(), &mut r), NGS_MISUSE);

        // close & reopen
        assert_eq!(ngs_close(db), NGS_OK);
        db = ptr::null_mut();
        let o_rw = open_opts(NGS_OPEN_READWRITE);
        assert_eq!(ngs_open(dir_c.as_ptr(), &o_rw, &mut db), NGS_OK);
        for i in 0..N_MANY {
            let mut rf: *mut ngs_fact = ptr::null_mut();
            assert_eq!(ngs_get(db, &many_ids[i], &mut rf), NGS_OK);
            assert!(str_eq((*rf).title, &titles[i]));
            ngs_free(rf as *mut _);
        }
        assert_eq!(ngs_close(db), NGS_OK);
        db = ptr::null_mut();

        // readonly_rejects_write
        let o_ro = open_opts(NGS_OPEN_READONLY);
        assert_eq!(ngs_open(dir_c.as_ptr(), &o_ro, &mut db), NGS_OK);
        let ro_in = make_fact_in("bench", NGS_SEMANTIC, "ro", "ro");
        assert_ne!(ngs_remember(db, &ro_in, 0, &mut dummy), NGS_OK);
        assert_eq!(ngs_close(db), NGS_OK);
        db = ptr::null_mut();

        // torn_tail_recovers + write_after_torn_tail + verify_after_torn_tail
        let log_path = dir.join("ngs.log");
        let log_sz_before = fs::metadata(&log_path).unwrap().len();
        {
            let mut lf = OpenOptions::new().append(true).open(&log_path).unwrap();
            let junk: [u8; 37] = [0x00, 0xff, 0x13, 0x37, 0xde, 0xad, 0xbe, 0xef, 0x42,
                                  0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0];
            lf.write_all(&junk).unwrap();
        }
        assert_eq!(ngs_open(dir_c.as_ptr(), &o_rw, &mut db), NGS_OK);
        let mut tf: *mut ngs_fact = ptr::null_mut();
        assert_eq!(ngs_get(db, &many_ids[N_MANY - 1], &mut tf), NGS_OK);
        assert!(str_eq((*tf).title, &titles[N_MANY - 1]));
        ngs_free(tf as *mut _);
        let after = make_fact_in("bench", NGS_SEMANTIC, "after-tear", "after-tear");
        assert_eq!(ngs_remember(db, &after, 0, &mut dummy), NGS_OK);
        assert_eq!(ngs_verify(db, ptr::null(), 0), NGS_OK);
        assert_eq!(ngs_close(db), NGS_OK);
        db = ptr::null_mut();

        // bitflip_detected + bitflip_no_wrong_read
        {
            let mut lf = OpenOptions::new().read(true).write(true).open(&log_path).unwrap();
            let at = log_sz_before / 2;
            lf.seek(SeekFrom::Start(at)).unwrap();
            let mut b = [0u8; 1];
            lf.read_exact(&mut b).unwrap();
            b[0] ^= 0x10;
            lf.seek(SeekFrom::Start(at)).unwrap();
            lf.write_all(&b).unwrap();
        }
        let rc_corrupt = ngs_open(dir_c.as_ptr(), &o_rw, &mut db);
        assert_eq!(rc_corrupt, NGS_CORRUPT);
        assert!(db.is_null());

        let _ = fs::remove_dir_all(&dir);
    }
}

#[test]
fn m2_recall_deadline_budget_supersedes() {
    unsafe {
        let dir = scratch_dir("m2_recall");
        let dir_c = CString::new(dir.to_str().unwrap()).unwrap();
        let o_create = open_opts(NGS_OPEN_READWRITE | NGS_OPEN_CREATE);
        let mut db: *mut NgsDb = ptr::null_mut();
        assert_eq!(ngs_open(dir_c.as_ptr(), &o_create, &mut db), NGS_OK);

        // Remember v1, then supersede with v2
        let mut id_v1 = ngs_id::default();
        let f1 = make_fact_in("arch", NGS_SEMANTIC, "sql successor", "old draft body for sql successor");
        assert_eq!(ngs_remember(db, &f1, 0, &mut id_v1), NGS_OK);

        let mut f2 = make_fact_in("arch", NGS_SEMANTIC, "sql successor", "new native ngs engine with bounded deadline and atomic frames");
        f2.supersedes = &id_v1;
        let mut id_v2 = ngs_id::default();
        assert_eq!(ngs_remember(db, &f2, 0, &mut id_v2), NGS_OK);

        // Default recall: returns ONLY v2 (v1 superseded), non-abstained, arm[KW] > 0
        let mut q = ngs_query {
            size: std::mem::size_of::<ngs_query>() as u32,
            ns: s("arch"),
            kinds: 0,
            text: s("sql successor"),
            vec: ptr::null(),
            since: NGS_TIME_MIN,
            until: NGS_TIME_MAX,
            tags: ptr::null(),
            n_tags: 0,
            k: 5,
            deadline_ms: 50,
            fusion: 0,
            weights: ptr::null(),
            flags: 0,
            token_budget: 0,
            tokenizer_id: ngs_str { p: ptr::null(), n: 0 },
            min_confidence: -1.0,
        };
        let mut res: *mut ngs_results = ptr::null_mut();
        assert_eq!(ngs_recall(db, &q, &mut res), NGS_OK);
        assert!(!res.is_null());
        assert_eq!((*res).n, 1);
        assert_eq!((*res).abstained, 0);
        assert_eq!((*res).timed_out, 0);
        let h0 = &*(*res).hits;
        assert_eq!(h0.id, id_v2);
        assert!(h0.arm[NGS_ARM_KW] > 0.5);
        assert_eq!(h0.invalid, 0);
        ngs_free(res as *mut _);

        // Include invalid: returns BOTH v2 and v1
        q.flags = NGS_RECALL_INCLUDE_INVALID;
        res = ptr::null_mut();
        assert_eq!(ngs_recall(db, &q, &mut res), NGS_OK);
        assert_eq!((*res).n, 2);
        ngs_free(res as *mut _);

        // Tight token budget forces title-only stub (stub == 1, body.n == 0)
        q.flags = 0;
        q.token_budget = 6;
        res = ptr::null_mut();
        assert_eq!(ngs_recall(db, &q, &mut res), NGS_OK);
        assert_eq!((*res).n, 1);
        let hs = &*(*res).hits;
        assert_eq!(hs.stub, 1);
        assert_eq!(hs.body.n, 0);
        ngs_free(res as *mut _);

        // Unmatched query abstains cleanly with NGS_OK
        q.token_budget = 0;
        q.text = s("nonexistent_quantum_banana");
        res = ptr::null_mut();
        assert_eq!(ngs_recall(db, &q, &mut res), NGS_OK);
        assert_eq!((*res).n, 0);
        assert_eq!((*res).abstained, 1);
        ngs_free(res as *mut _);

        assert_eq!(ngs_close(db), NGS_OK);
        let _ = fs::remove_dir_all(&dir);
    }
}

#[test]
fn m1_crash_batch_atomicity_every_byte_cut() {
    unsafe {
        let dir = scratch_dir("crash_atomic");
        let dir_c = CString::new(dir.to_str().unwrap()).unwrap();
        let o_create = open_opts(NGS_OPEN_READWRITE | NGS_OPEN_CREATE);
        let o_rw = open_opts(NGS_OPEN_READWRITE);
        let mut db: *mut NgsDb = ptr::null_mut();

        // Write 1 acked batch of 5 facts
        assert_eq!(ngs_open(dir_c.as_ptr(), &o_create, &mut db), NGS_OK);
        let t1: Vec<String> = (0..5).map(|j| format!("r0-b0-f{}", j)).collect();
        let b1: Vec<ngs_fact_in> = t1.iter().map(|t| make_fact_in("crash", NGS_EPISODIC, t, t)).collect();
        let mut ids1 = [ngs_id::default(); 5];
        assert_eq!(ngs_remember_many(db, b1.as_ptr(), 5, 0, ids1.as_mut_ptr()), NGS_OK);
        assert_eq!(ngs_close(db), NGS_OK);

        let log_path = dir.join("ngs.log");
        let base_bytes = fs::read(&log_path).unwrap();

        // Write a 2nd batch of 5 facts
        assert_eq!(ngs_open(dir_c.as_ptr(), &o_rw, &mut db), NGS_OK);
        let t2: Vec<String> = (0..5).map(|j| format!("r0-b1-f{}", j)).collect();
        let b2: Vec<ngs_fact_in> = t2.iter().map(|t| make_fact_in("crash", NGS_EPISODIC, t, t)).collect();
        let mut ids2 = [ngs_id::default(); 5];
        assert_eq!(ngs_remember_many(db, b2.as_ptr(), 5, 0, ids2.as_mut_ptr()), NGS_OK);
        assert_eq!(ngs_close(db), NGS_OK);
        let full_bytes = fs::read(&log_path).unwrap();

        // Simulate SIGKILL cutting the 2nd batch at 20 different byte offsets!
        // Every cut must recover with EXACTLY 5 facts (batch 0 only), NEVER 6..9!
        let frame2_len = full_bytes.len() - base_bytes.len();
        for step in 1..20 {
            let cut = base_bytes.len() + (frame2_len * step) / 20;
            fs::write(&log_path, &full_bytes[..cut]).unwrap();
            let mut rdb: *mut NgsDb = ptr::null_mut();
            assert_eq!(ngs_open(dir_c.as_ptr(), &o_rw, &mut rdb), NGS_OK);
            assert_eq!(ngs_verify(rdb, ptr::null(), 0), NGS_OK);
            // Count facts via scan
            let so = ngs_scan_opts {
                size: std::mem::size_of::<ngs_scan_opts>() as u32,
                ns: s("crash"),
                writer: ptr::null(),
                since: NGS_TIME_MIN,
                until: NGS_TIME_MAX,
                include_derived: 0,
            };
            let mut it: *mut ngs_iter = ptr::null_mut();
            assert_eq!(ngs_scan(rdb, &so, &mut it), NGS_OK);
            let mut count = 0usize;
            let mut sf: *mut ngs_fact = ptr::null_mut();
            while ngs_iter_next(it, &mut sf) == NGS_OK {
                count += 1;
                ngs_free(sf as *mut _);
            }
            ngs_iter_close(it);
            assert_eq!(count, 5, "partial batch leaked at cut={}", cut);
            assert_eq!(ngs_close(rdb), NGS_OK);
        }
        let _ = fs::remove_dir_all(&dir);
    }
}

#[test]
fn m3_vector_and_link_expand() {
    unsafe {
        let dir = scratch_dir("m3_vec_link");
        let dir_c = CString::new(dir.to_str().unwrap()).unwrap();
        let o_create = open_opts(NGS_OPEN_READWRITE | NGS_OPEN_CREATE);
        let mut db: *mut NgsDb = ptr::null_mut();
        assert_eq!(ngs_open(dir_c.as_ptr(), &o_create, &mut db), NGS_OK);

        // Fact A with embedding [1.0, 0.0, 0.0, 0.0]
        let v_a: [f32; 4] = [1.0, 0.0, 0.0, 0.0];
        let vec_a = ngs_vec { model_id: s("nomic-v1"), dim: 4, version: 1, v: v_a.as_ptr() };
        let mut fa = make_fact_in("kg", NGS_SEMANTIC, "anchor node", "vector anchor");
        fa.vecs = &vec_a;
        fa.n_vecs = 1;
        let mut id_a = ngs_id::default();
        assert_eq!(ngs_remember(db, &fa, 0, &mut id_a), NGS_OK);

        // Fact B has NO keyword/vector match, only linked to A (expert knowledge edge)
        let fb = make_fact_in("kg", NGS_PROCEDURAL, "date format rule", "Date column uses YYYYMM integer");
        let mut id_b = ngs_id::default();
        assert_eq!(ngs_remember(db, &fb, 0, &mut id_b), NGS_OK);

        // Link A -> B
        let mut link_id = ngs_id::default();
        assert_eq!(ngs_link(db, &id_a, &id_b, s("governs"), 0.9, &mut link_id), NGS_OK);
        assert!(!id_zero(&link_id));

        // Recall by vector + NGS_RECALL_EXPAND: finds A via VEC arm AND pulls B via 1-hop LINK arm
        let qv_arr: [f32; 4] = [1.0, 0.0, 0.0, 0.0];
        let qv = ngs_vec { model_id: s("nomic-v1"), dim: 4, version: 1, v: qv_arr.as_ptr() };
        let q = ngs_query {
            size: std::mem::size_of::<ngs_query>() as u32,
            ns: s("kg"),
            kinds: 0,
            text: ngs_str { p: ptr::null(), n: 0 },
            vec: &qv,
            since: NGS_TIME_MIN,
            until: NGS_TIME_MAX,
            tags: ptr::null(),
            n_tags: 0,
            k: 5,
            deadline_ms: 50,
            fusion: 0,
            weights: ptr::null(),
            flags: NGS_RECALL_EXPAND,
            token_budget: 0,
            tokenizer_id: ngs_str { p: ptr::null(), n: 0 },
            min_confidence: -1.0,
        };
        let mut res: *mut ngs_results = ptr::null_mut();
        assert_eq!(ngs_recall(db, &q, &mut res), NGS_OK);
        assert_eq!((*res).n, 2);
        assert!(((*res).arms_complete & (1u32 << NGS_ARM_VEC)) != 0);
        assert!(((*res).arms_complete & (1u32 << NGS_ARM_LINK)) != 0);
        let hits = std::slice::from_raw_parts((*res).hits, (*res).n);
        assert_eq!(hits[0].id, id_a);
        assert!(hits[0].arm[NGS_ARM_VEC] > 0.99);
        assert_eq!(hits[1].id, id_b);
        assert!(hits[1].arm[NGS_ARM_LINK] > 0.5);
        ngs_free(res as *mut _);

        assert_eq!(ngs_close(db), NGS_OK);
        let _ = fs::remove_dir_all(&dir);
    }
}

#[test]
fn m4_mark_as_of_and_stats() {
    unsafe {
        let dir = scratch_dir("m4_mark_asof");
        let dir_c = CString::new(dir.to_str().unwrap()).unwrap();
        let o_create = open_opts(NGS_OPEN_READWRITE | NGS_OPEN_CREATE);
        let mut db: *mut NgsDb = ptr::null_mut();
        assert_eq!(ngs_open(dir_c.as_ptr(), &o_create, &mut db), NGS_OK);

        // Two facts with identical text; mark A USED and B NOT_USED -> A outranks B via SALIENCE
        let mut fa = make_fact_in("fb", NGS_SEMANTIC, "policy rule", "production deploy policy");
        fa.t_event = 1_000;
        fa.valid_from = 1_000;
        let mut id_a = ngs_id::default();
        assert_eq!(ngs_remember(db, &fa, 0, &mut id_a), NGS_OK);

        let mut fb = make_fact_in("fb", NGS_SEMANTIC, "policy rule", "production deploy policy");
        fb.t_event = 1_000;
        fb.valid_from = 1_000;
        let mut id_b = ngs_id::default();
        assert_eq!(ngs_remember(db, &fb, 0, &mut id_b), NGS_OK);

        assert_eq!(ngs_mark(db, &id_a, NGS_MARK_USED), NGS_OK);
        assert_eq!(ngs_mark(db, &id_b, NGS_MARK_NOT_USED), NGS_OK);

        // Unknown id returns NGS_NOTFOUND
        let unk = ngs_id { b: [0x99; 32] };
        assert_eq!(ngs_mark(db, &unk, NGS_MARK_USED), NGS_NOTFOUND);

        let q = ngs_query {
            size: std::mem::size_of::<ngs_query>() as u32,
            ns: s("fb"),
            kinds: 0,
            text: s("policy rule"),
            vec: ptr::null(),
            since: NGS_TIME_MIN,
            until: NGS_TIME_MAX,
            tags: ptr::null(),
            n_tags: 0,
            k: 5,
            deadline_ms: 50,
            fusion: 0,
            weights: ptr::null(),
            flags: 0,
            token_budget: 0,
            tokenizer_id: ngs_str { p: ptr::null(), n: 0 },
            min_confidence: -1.0,
        };
        let mut res: *mut ngs_results = ptr::null_mut();
        assert_eq!(ngs_recall(db, &q, &mut res), NGS_OK);
        let hits = std::slice::from_raw_parts((*res).hits, (*res).n);
        assert_eq!(hits[0].id, id_a);
        assert!(hits[0].arm[NGS_ARM_SALIENCE] > hits[1].arm[NGS_ARM_SALIENCE]);
        ngs_free(res as *mut _);

        // Bi-temporal ngs_as_of: at t_valid=500 (before valid_from=1000) -> 0 hits; at t_valid=1500 -> 2 hits
        res = ptr::null_mut();
        assert_eq!(ngs_as_of(db, 500, NGS_TIME_MAX, &q, &mut res), NGS_OK);
        assert_eq!((*res).n, 0);
        ngs_free(res as *mut _);

        res = ptr::null_mut();
        assert_eq!(ngs_as_of(db, 1500, NGS_TIME_MAX, &q, &mut res), NGS_OK);
        assert_eq!((*res).n, 2);
        ngs_free(res as *mut _);

        // ngs_stats reports accurate counters
        let mut st = ngs_stats_t {
            size: std::mem::size_of::<ngs_stats_t>() as u32,
            facts: 0, invalidated: 0, links: 0, redacted: 0, log_bytes: 0,
            derived_bytes: 0, vec_indexes: 0, facts_missing_vec: 0,
            quarantined_segments: 0, recalls: 0, abstentions: 0, timeouts: 0,
        };
        assert_eq!(ngs_stats(db, &mut st), NGS_OK);
        assert_eq!(st.facts, 2);
        assert_eq!(st.recalls, 3);
        assert_eq!(st.abstentions, 1);
        assert!(st.log_bytes > 0);

        assert_eq!(ngs_close(db), NGS_OK);
        let _ = fs::remove_dir_all(&dir);
    }
}

#[test]
fn m5_federation_checkpoint_redact() {
    unsafe {
        let dir1 = scratch_dir("m5_node1");
        let dir2 = scratch_dir("m5_node2");
        let d1c = CString::new(dir1.to_str().unwrap()).unwrap();
        let d2c = CString::new(dir2.to_str().unwrap()).unwrap();
        let o_create = open_opts(NGS_OPEN_READWRITE | NGS_OPEN_CREATE);

        let mut db1: *mut NgsDb = ptr::null_mut();
        let mut db2: *mut NgsDb = ptr::null_mut();
        assert_eq!(ngs_open(d1c.as_ptr(), &o_create, &mut db1), NGS_OK);
        assert_eq!(ngs_open(d2c.as_ptr(), &o_create, &mut db2), NGS_OK);

        // Write 2 facts on node1 + grant + checkpoint + verify
        let f1 = make_fact_in("fleet", NGS_SEMANTIC, "secret note", "sensitive payload");
        let f2 = make_fact_in("fleet", NGS_SEMANTIC, "public note", "shared knowledge");
        let mut id1 = ngs_id::default();
        let mut id2 = ngs_id::default();
        assert_eq!(ngs_remember(db1, &f1, 0, &mut id1), NGS_OK);
        assert_eq!(ngs_remember(db1, &f2, 0, &mut id2), NGS_OK);

        let mut pk2 = ngs_pubkey::default();
        assert_eq!(ngs_node_pubkey(db2, &mut pk2), NGS_OK);
        let mut gid = ngs_id::default();
        assert_eq!(ngs_grant(db1, s("fleet"), &pk2, &mut gid), NGS_OK);
        assert!(!id_zero(&gid));

        let mut ckpt: *mut u8 = ptr::null_mut();
        let mut ckpt_len: usize = 0;
        assert_eq!(ngs_checkpoint(db1, &mut ckpt, &mut ckpt_len), NGS_OK);
        assert_eq!(ckpt_len, 44);
        assert_eq!(ngs_verify(db1, ckpt, ckpt_len), NGS_OK);
        ngs_free(ckpt as *mut _);
        assert_eq!(ngs_rebuild(db1), NGS_OK);

        // Heads on node1
        let mut heads: *mut ngs_head = ptr::null_mut();
        let mut n_heads: usize = 0;
        assert_eq!(ngs_heads(db1, &mut heads, &mut n_heads), NGS_OK);
        assert_eq!(n_heads, 1);
        assert_eq!((*heads).seq, 2);
        ngs_free(heads as *mut _);

        // Sync export from node1 -> import into node2
        let mut seg: *mut u8 = ptr::null_mut();
        let mut seg_len: usize = 0;
        assert_eq!(ngs_sync_export(db1, ptr::null(), 0, &mut seg, &mut seg_len), NGS_OK);
        assert!(seg_len > 24);

        let mut rep: *mut ngs_sync_report = ptr::null_mut();
        assert_eq!(ngs_sync_import(db2, seg, seg_len, &mut rep), NGS_OK);
        assert_eq!((*rep).applied, 2);
        assert_eq!((*rep).duplicates, 0);
        assert_eq!((*rep).quarantined, 0);
        ngs_free(rep as *mut _);

        // Re-importing same segment reports duplicates=2, applied=0
        rep = ptr::null_mut();
        assert_eq!(ngs_sync_import(db2, seg, seg_len, &mut rep), NGS_OK);
        assert_eq!((*rep).applied, 0);
        assert_eq!((*rep).duplicates, 2);
        ngs_free(rep as *mut _);

        // Tampered segment is quarantined with NGS_QUARANTINED
        let mut bad_seg = std::slice::from_raw_parts(seg, seg_len).to_vec();
        bad_seg[seg_len / 2] ^= 0xFF;
        rep = ptr::null_mut();
        assert_eq!(ngs_sync_import(db2, bad_seg.as_ptr(), bad_seg.len(), &mut rep), NGS_QUARANTINED);
        assert_eq!((*rep).quarantined, 1);
        ngs_free(rep as *mut _);
        ngs_free(seg as *mut _);

        // Redact id1 on node1 -> body empty, redacted == 1
        assert_eq!(ngs_redact(db1, &id1, s("pii")), NGS_OK);
        let mut rf: *mut ngs_fact = ptr::null_mut();
        assert_eq!(ngs_get(db1, &id1, &mut rf), NGS_OK);
        assert_eq!((*rf).redacted, 1);
        assert_eq!((*rf).body.n, 0);
        ngs_free(rf as *mut _);

        assert_eq!(ngs_close(db1), NGS_OK);
        assert_eq!(ngs_close(db2), NGS_OK);
        let _ = fs::remove_dir_all(&dir1);
        let _ = fs::remove_dir_all(&dir2);
    }
}
