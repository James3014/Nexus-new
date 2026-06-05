use pyo3::prelude::*;

pub mod governance;
pub mod fast_matcher;

use crate::governance::types::FlowState;
use crate::governance::transition_engine::TransitionEngine;
use crate::governance::normalizer::IntentNormalizer;
use crate::fast_matcher::{fast_scan, FileMetadata};

#[pyfunction]
#[pyo3(name = "can_transition")]
fn can_transition_py(from: &str, to: &str) -> PyResult<bool> {
    let from_enum = match_state(from);
    let to_enum = match_state(to);
    Ok(TransitionEngine::can_transition(from_enum, to_enum).is_ok())
}

#[pyfunction]
#[pyo3(name = "normalize_intent")]
fn normalize_intent_py(raw: &str) -> PyResult<Option<(String, String, String, String)>> {
    match IntentNormalizer::normalize(raw) {
        Ok(intent) => Ok(Some((
            format!("{:?}", intent.route).to_uppercase(),
            format!("{:?}", intent.decision).to_uppercase(),
            format!("{:?}", intent.phase).to_uppercase(),
            format!("{:?}", intent.confidence).to_uppercase(),
        ))),
        Err(_) => Ok(None)
    }
}

fn match_state(s: &str) -> FlowState {
    match s.to_uppercase().as_str() {
        "PLAN" | "P" => FlowState::Plan,
        "EXECUTE" | "X" | "D" => FlowState::Execute,
        "VERIFY" | "R" => FlowState::Verify,
        "INTAKE" | "S" => FlowState::Intake,
        "CLOSE" | "A" | "C" => FlowState::Close,
        "ESCALATE" => FlowState::Escalate,
        "STOP" => FlowState::Stop,
        "CLARIFY" => FlowState::Clarify,
        "OUTLINE" => FlowState::Outline,
        "RESEARCH" => FlowState::Research,
        "DESIGN" => FlowState::Design,
        "REPLAN" => FlowState::Replan,
        "HUMAN_REVIEW" => FlowState::HumanReview,
        _ => FlowState::Unknown,
    }
}

#[pymodule]
fn nexus_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(can_transition_py, m)?)?;
    m.add_function(wrap_pyfunction!(normalize_intent_py, m)?)?;
    m.add_function(wrap_pyfunction!(fast_scan, m)?)?;
    m.add_class::<FileMetadata>()?;
    Ok(())
}

