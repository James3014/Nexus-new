use serde::{Deserialize, Serialize};
use std::io::{self, Read};

mod ast_analyzer;
mod receipt_verifier;
mod flow_machine;
mod matcher;
mod replay;
mod slice_planner;
mod contamination;

use ast_analyzer::{SinglePassScanner, AstRule};
use receipt_verifier::{ReceiptVerifier, ReceiptVerificationRequest};
use flow_machine::{FlowStateMachine, FlowState};
use matcher::{Matcher, MatchRequest};
use replay::{ReplayEngine, ReplayRequest};
use slice_planner::{VerticalSlicePlanner, SliceValidationRequest};
use contamination::{ContaminationGuard, ContaminationCheckRequest};

#[derive(Serialize, Deserialize, Debug)]
#[serde(tag = "type", content = "payload")]
enum Request {
    ValidateTransition {
        current: FlowState,
        next: FlowState,
    },
    GetLegalTransitions {
        current: FlowState,
    },
    IsTerminal {
        state: FlowState,
    },
    AstScan {
        path: String,
        rules: Vec<AstRule>,
    },
    VerifyReceipt(ReceiptVerificationRequest),
    MatchPattern(MatchRequest),
    VerifyReplay(ReplayRequest),
    ValidateSlice(SliceValidationRequest),
    CheckContamination(ContaminationCheckRequest),
    SmokeTest {
        message: String,
    },
}

#[derive(Serialize, Deserialize, Debug)]
struct Response {
    success: bool,
    payload: serde_json::Value,
    error_message: Option<String>,
}

fn main() {
    let mut buffer = String::new();
    if let Ok(_) = io::stdin().read_to_string(&mut buffer) {
        let request: Result<Request, _> = serde_json::from_str(&buffer);
        
        let response = match request {
            Ok(Request::SmokeTest { message }) => Response {
                success: true,
                payload: serde_json::json!({ "echo": message, "status": "Rust Kernel Active" }),
                error_message: None,
            },
            Ok(Request::AstScan { path, rules }) => {
                let scanner = SinglePassScanner::new(rules);
                let result = scanner.scan(&path);
                Response {
                    success: true,
                    payload: serde_json::to_value(result).unwrap(),
                    error_message: None,
                }
            },
            Ok(Request::VerifyReceipt(req)) => {
                let result = ReceiptVerifier::verify(req);
                Response {
                    success: true,
                    payload: serde_json::to_value(result).unwrap(),
                    error_message: None,
                }
            },
            Ok(Request::ValidateTransition { current, next }) => {
                let is_valid = FlowStateMachine::validate_transition(current, next);
                Response {
                    success: true,
                    payload: serde_json::json!({ "is_valid": is_valid }),
                    error_message: None,
                }
            },
            Ok(Request::MatchPattern(req)) => {
                let result = Matcher::execute(req);
                Response {
                    success: true,
                    payload: serde_json::to_value(result).unwrap(),
                    error_message: None,
                }
            },
            Ok(Request::VerifyReplay(req)) => {
                let result = ReplayEngine::verify(req);
                Response {
                    success: true,
                    payload: serde_json::to_value(result).unwrap(),
                    error_message: None,
                }
            },
            Ok(Request::ValidateSlice(req)) => {
                let result = VerticalSlicePlanner::validate(req);
                Response {
                    success: true,
                    payload: serde_json::to_value(result).unwrap(),
                    error_message: None,
                }
            },
            Ok(Request::CheckContamination(req)) => {
                let result = ContaminationGuard::check(req);
                Response {
                    success: true,
                    payload: serde_json::to_value(result).unwrap(),
                    error_message: None,
                }
            },
            Ok(Request::GetLegalTransitions { current }) => {
                let legal = FlowStateMachine::legal_transitions(current);
                let terminal = FlowStateMachine::is_terminal(current);
                Response {
                    success: true,
                    payload: serde_json::json!({
                        "current_state": format!("{:?}", current),
                        "legal_next_states": legal.iter().map(|s| format!("{:?}", s)).collect::<Vec<_>>(),
                        "is_terminal": terminal,
                        "transition_count": legal.len()
                    }),
                    error_message: None,
                }
            },
            Ok(Request::IsTerminal { state }) => {
                let is_term = FlowStateMachine::is_terminal(state);
                Response {
                    success: true,
                    payload: serde_json::json!({
                        "state": format!("{:?}", state),
                        "is_terminal": is_term
                    }),
                    error_message: None,
                }
            },
            Err(e) => Response {
                success: false,
                payload: serde_json::json!({}),
                error_message: Some(format!("Parse error: {}", e)),
            },
        };

        println!("{}", serde_json::to_string(&response).unwrap());
    }
}
