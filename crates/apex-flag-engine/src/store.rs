//! Lock-free snapshot store + generation pinning (Decisions #1, #8;
//! Binding Improvement #7). Reads are `arc_swap.load()` — lock-free and
//! allocation-free, O(100ns). No per-evaluation logging on the hot path.

use crate::model::CompiledFlag;
use arc_swap::{ArcSwap, Guard};
use std::collections::HashMap;
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};

/// A consistent, immutable view of all flags at one generation.
#[derive(Debug, Default)]
pub struct FlagSnapshot {
    pub generation: u64,
    /// When this snapshot was last refreshed from a lower tier.
    pub fetched_at_epoch_ms: u128,
    pub flags: HashMap<String, CompiledFlag>,
}

impl FlagSnapshot {
    pub fn now_epoch_ms() -> u128 {
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_millis())
            .unwrap_or(0)
    }

    pub fn get(&self, key: &str) -> Option<&CompiledFlag> {
        self.flags.get(key)
    }
}

/// The hot-path store. `current` is swapped atomically by the refresher.
/// `baked` holds version-pinned defaults for cold start (Decision #1).
pub struct FlagStore {
    current: ArcSwap<FlagSnapshot>,
    baked: Arc<FlagSnapshot>,
}

/// A snapshot pinned for the duration of one unit of work (Decision #8).
/// Flips applied after the pin do NOT affect this unit of work.
#[derive(Clone)]
pub struct PinnedFlags {
    snapshot: Arc<FlagSnapshot>,
}

impl PinnedFlags {
    pub fn generation(&self) -> u64 {
        self.snapshot.generation
    }

    pub fn get(&self, key: &str) -> Option<&CompiledFlag> {
        self.snapshot.get(key)
    }
}

impl FlagStore {
    pub fn new(baked: FlagSnapshot) -> Self {
        // Cold start: begin on the baked-in defaults.
        let baked = Arc::new(baked);
        Self {
            current: ArcSwap::from(baked.clone()),
            baked,
        }
    }

    /// Lock-free hot-path read. Returns a Guard — no allocation, no lock.
    #[inline]
    pub fn load(&self) -> Guard<Arc<FlagSnapshot>> {
        self.current.load()
    }

    /// Pin the CURRENT snapshot for one unit of work. The returned
    /// PinnedFlags is immune to subsequent flips (transactional isolation).
    #[inline]
    pub fn pin(&self) -> PinnedFlags {
        PinnedFlags {
            snapshot: self.current.load_full(),
        }
    }

    /// Atomic swap performed by the background refresher (slow path).
    pub fn swap(&self, next: FlagSnapshot) {
        self.current.store(Arc::new(next));
    }

    pub fn baked(&self) -> &Arc<FlagSnapshot> {
        &self.baked
    }
}