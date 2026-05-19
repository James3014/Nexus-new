---
name: github4-sickn33-antigravity-awesome-skills-tdd-workflows-tdd-red
description: Generate failing tests for the TDD red phase to define expected behavior and edge cases. Use only as Nexus SF prompt-only ablation candidate with runtime receipt evidence; do not execute upstream tools, install dependencies, call subagents, or mutate global settings.
metadata: {"source_repo":"https://github.com/sickn33/antigravity-awesome-skills","source_commit":"9e5d4ddefa24be7b50cc83f56a2450401cdf3317","source_path":"skills/tdd-workflows-tdd-red/SKILL.md","source_status":"external_round4_prompt_only_runtime_reviewed","runtime_eligible":true,"ablation_eligible":true}
---

# github4-sickn33-antigravity-awesome-skills-tdd-workflows-tdd-red

Prompt-only Nexus SF candidate adapted from `SKILL.md`.

## Load when
Generate failing tests for the TDD red phase to define expected behavior and edge cases.

## Runtime boundary
- Use only the written workflow principles below.
- Do not execute upstream scripts, install packages, call external services, invoke subagents, or mutate global IDE/agent settings.
- Must produce selected/injected/used/evidence/gate/outcome-backed receipt evidence.

## Safe workflow principles
Write comprehensive failing tests following TDD red phase principles.

[Extended thinking: Generates failing tests that properly define expected behavior using test-automator agent.]

## Use this skill when

- Starting the TDD red phase for new behavior
- You need failing tests that capture expected behavior
- You want edge case coverage before implementation

## Do not use this skill when

- You are in the green or refactor phase
- You only need performance benchmarks
- Tests must run against production systems

## Instructions

1. Identify behaviors, constraints, and edge cases.
2. Generate failing tests that define expected outcomes.
3. Ensure failures are due to missing behavior, not setup errors.
4. Document how to run tests and verify failures.

## Safety

- Keep test data isolated and avoid production environments.
- Avoid flaky external dependencies in the red phase.

## Role

Generate failing tests using Task tool with subagent_type="unit-testing::test-automator".

## Prompt Template

"Generate comprehensive FAILING tests for: $ARGUMENTS

## Core Requirements

1. **Test Structure**
   - Framework-appropriate setup (Jest/pytest/JUnit/Go/RSpec)
   - Arrange-Act-Assert pattern
   - should_X_when_Y naming convention
   - Isolated fixtures with no interdependencies

2. **Behavior Coverage**
   - Happy path scenarios
   - Edge cases (empty, null, boundary values)
   - Error handling and exceptions
   - Concurrent access (if applicable)

3. **Failure Verification**
   - Tests MUST fail when run
   - Failures for RIGHT reasons (not syntax/import errors)
   - Meaningful diagnostic error messages
   - No cascading failures

4. **Test Categories**
   - Unit: Isolated component behavior
   - Integration: Component interaction
   - Contract: API/interface contracts
   - Property: Mathematical invariants

## Framework Patterns

**JavaScript/TypeScript (Jest/Vitest)**
- Mock dependencies with `vi.fn()` or `jest.fn()`
- Use `@testing-library` for React components
- Property tests with `fast-check`

**Python (pytest)**
- Fixtures with appropriate scopes
- Parametrize for multiple test cases
- Hypothesis for property-based tests

**Go**
- Table-driven tests with subtests
- `t.Parallel()` for parallel execution
- Use `testify/assert` for cleaner assertions

**Ruby (RSpec)**
- `let` for lazy loading, `let!` for eager
- Contexts for different scenarios
- Shared examples for common behavior

## Quality Checklist

- Readable test names documenting intent
- One behavior per test
- No implementation leakage
- Meaningful test data (not 'foo'/'bar')
- Tests serve as living documentation

## Anti-Patterns to Avoid

- Tests passing immediately
- Testing implementation vs behavior
- Complex setup code
- Multiple responsibilities per test
- Brittle tests tied to specifics

## Edge Case Categories

- **Null/Empty**: undefined, null, empty string/array/object
- **Boundaries**: min/max values, single element, capacity limits
- **Special Cases**: Unicode, whitespace, special characters
- **State**: Invalid transitions, concurrent modifications
- **Errors**: Network failures, timeouts, permissions

## Output Requirements

- Complete test files with imports
- Documentation of test purpose
- Commands to run and verify failures
- Metrics: test count, coverage areas
- Next steps for green phase"

## Validation

After generation:
1. Run tests - confirm they fail
