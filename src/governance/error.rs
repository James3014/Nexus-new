use thiserror::Error;
use super::types::{BlockerCode, FlowState};

#[derive(Debug, Error, PartialEq, Eq)]
pub enum GovernanceError {
    #[error("Illegal phase transition from {from:?} to {to:?}")]
    IllegalTransition { from: FlowState, to: FlowState },

    #[error("State blocked by policy: {code:?}")]
    StateBlocked { code: BlockerCode },

    #[error("Contract validation failed: missing field {field}")]
    MissingField { field: String },

    #[error("Receipt verification failed: {reason}")]
    InvalidReceipt { reason: String },

    #[error("Failed to normalize intent from string: {0}")]
    NormalizationError(String),
}
