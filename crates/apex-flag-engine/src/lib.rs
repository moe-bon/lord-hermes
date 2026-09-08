//! ApexQuant Ultra — critical-path feature flag engine.
//!
//! Architecture (Binding Decision #1, #2, #8):
//!   Postgres (truth) -> Redis (shared cache) -> local lock-free snapshot.
//!   A unit of work pins ONE snapshot for its duration; flips apply to new
//!   decisions only. Reads are lock-free and allocation-free.

pub mod determinism;
pub mod model;
pub mod evaluator;
pub mod store;
pub mod provider;

pub use determinism::{bucket_for, select_bucketing_entity, DeterminismSpec};
pub use evaluator::{evaluate, EvaluationOutcome};
pub use model::{
    CompiledFlag, EvaluationContext, FlagClass, FlagStatus, FlagType,
};
pub use provider::{DegradationState, FlagProvider};
pub use store::{FlagSnapshot, FlagStore, PinnedFlags};