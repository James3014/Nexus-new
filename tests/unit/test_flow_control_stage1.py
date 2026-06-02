import pytest
from nexus.engine.flow_control import IntentIntakeClassifier, InteractionMode, FlowStateMachine
from nexus.engine.capability_contracts import FlowState

def test_intake_classifier_design_intent():
    classifier = IntentIntakeClassifier()
    task = "Please design a new microservice for user auth."
    receipt = classifier.classify(task)
    
    assert receipt.interaction_mode == InteractionMode.CLARIFY_FIRST
    assert receipt.initial_state == FlowState.CLARIFY
    assert receipt.requires_user_confirmation is True
    assert receipt.can_modify_files is False

def test_intake_classifier_direct_fix():
    classifier = IntentIntakeClassifier()
    task = "Fix a typo in readme.md"
    receipt = classifier.classify(task, risk_score=10)
    
    assert receipt.interaction_mode == InteractionMode.DIRECT
    assert receipt.initial_state == FlowState.PLAN
    assert receipt.requires_user_confirmation is False

def test_flow_state_machine_valid_transition():
    fsm = FlowStateMachine()
    # INTAKE -> PLAN is valid for low risk
    assert fsm.validate_transition(FlowState.INTAKE, FlowState.PLAN) is True
    # EXECUTE -> VERIFY is valid
    assert fsm.validate_transition(FlowState.EXECUTE, FlowState.VERIFY) is True

def test_flow_state_machine_invalid_transition():
    fsm = FlowStateMachine()
    # INTAKE -> EXECUTE is invalid (must go through PLAN)
    assert fsm.validate_transition(FlowState.INTAKE, FlowState.EXECUTE) is False
    # VERIFY -> EXECUTE is invalid (must go through REPLAN if failed)
    assert fsm.validate_transition(FlowState.VERIFY, FlowState.EXECUTE) is False
