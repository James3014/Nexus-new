import json
from pathlib import Path


def generate_inventory():
    repo_root = Path(__file__).resolve().parents[2]
    nexus_dir = repo_root / "nexus"
    tests_dir = repo_root / "tests"

    inventory = []

    for item in sorted(nexus_dir.iterdir()):
        if item.is_dir() and not item.name.startswith("__"):
            pkg_name = item.name
            has_init = (item / "__init__.py").exists()

            # Check for tests
            test_files = list(tests_dir.rglob(f"*test_{pkg_name}*.py"))
            has_tests = len(test_files) > 0

            # Classification logic
            if has_init and has_tests:
                category = "Active & Tested"
                status = "🟢"
            elif has_init:
                category = "Active but Untested"
                status = "🟡"
            else:
                category = "Inert or Placeholder"
                status = "⚪"

            inventory.append({
                "package": pkg_name,
                "status_icon": status,
                "category": category,
                "has_init": has_init,
                "test_count": len(test_files),
                "evidence_basis": "has tests" if has_tests else "no tests detected",
                "path": f"nexus/{pkg_name}/",
            })

    # Write JSON evidence
    output_json = repo_root / "docs/arch/module-inventory.generated.json"
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(inventory, f, indent=2)

    # Generate Markdown Table
    md_lines = [
        "# Nexus Module Inventory (Generated)",
        "",
        "| Status | Package | Category | Evidence | Test Count |",
        "|--------|---------|----------|----------|------------|",
    ]

    for item in inventory:
        md_lines.append(
            f"| {item['status_icon']} | `{item['package']}` | {item['category']} | {item['evidence_basis']} | {item['test_count']} |"
        )

    output_md = repo_root / "docs/arch/module-inventory.md"

    # Read existing content to preserve the Rust part if needed, but the user asked for full inventory
    # I'll just overwrite with the new generated content and re-add the Rust part

    rust_audit = """
## 🦀 Rust Crate Boundary Audit

### Current Split
1. **Root Crate (`/Cargo.toml`)**: retired and deleted 2026-10-14 (#1927); the PyO3 `nexus_core` extension was never on a production path.
2. **`nexus-core-rs` (`/nexus-core-rs/`)**: retired and deleted 2026-10-16 (#2359, Owner decision A) together with policies P-GATE-03 / P-FLOW-01 and the `nexus/bridge` Rust adapters; nothing built or shipped the binary.

Python is the only implementation: receipt verification in `nexus/engine/capability_receipt_adapters.py`, flow transitions in the contract path of `nexus/engine/governance_bridge.py`.
"""

    final_md = "\n".join(md_lines) + "\n" + rust_audit
    with open(output_md, "w", encoding="utf-8") as f:
        f.write(final_md)

    print(f"Generated {output_json}")
    print(f"Updated {output_md}")


if __name__ == "__main__":
    generate_inventory()
