use pyo3::prelude::*;

pub mod governance;

use crate::governance::types::FlowState;
use crate::governance::state_machine::TransitionGuard;
use crate::governance::normalizer::IntentNormalizer;

#[pyfunction]
#[pyo3(name = "can_transition")]
fn can_transition_py(from: &str, to: &str) -> PyResult<bool> {
    let from_enum = match_state(from);
    let to_enum = match_state(to);
    Ok(TransitionGuard::can_transition(from_enum, to_enum).is_ok())
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
        _ => FlowState::Unknown,
    }
}

#[pymodule]
fn nexus_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(can_transition_py, m)?)?;
    m.add_function(wrap_pyfunction!(normalize_intent_py, m)?)?;
    Ok(())
}
