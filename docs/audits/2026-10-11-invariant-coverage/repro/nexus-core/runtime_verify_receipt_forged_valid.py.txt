"""POST /v1/receipts/verify (RuntimeCertificationService.verify_receipt) returns
status VALID (scope FULL_RECOMPUTED) for a CERTIFIED receipt minted offline by the
caller for a PR the runtime never acquired/executed: no ledger lookup, no signature,
and the policy facts (authority/approval/signing) are read from the receipt under test
(service.py ~687-708; missing -> True). The runtime pipeline itself hard-codes all
four policy facts True (service.py ~424-432) even with signer=None."""
import asyncio, sys, tempfile
sys.path.insert(0, "/home/user/nexus-core")
from product.evidence import (AcceptanceContract, ChangeSet, VerificationPlan, EvidenceBundle,
                              Observation, ObservationStatus, _hash)
from product.kernel import CertificationInput, certify
from product.runtime.service import RuntimeCertificationService

c = AcceptanceContract(contract_id="ac-forged", requirements_hash=_hash("anything"),
                       required_verifier_ids=("pytest",), allowed_paths=("src/evil.py",), deletion_policy="FORBID")
cs = ChangeSet(change_set_id="pr-1", source_revision="a"*40, target_revision="b"*40,
               diff_hash=_hash("never-acquired"), paths=("src/evil.py",))
p = VerificationPlan(plan_id="plan-x", acceptance_contract_hash=c.hash, change_set_hash=cs.hash,
                     required_verifier_ids=("pytest",))
e = EvidenceBundle(bundle_id="b", acceptance_contract_hash=c.hash, change_set_hash=cs.hash,
                   verification_plan_hash=p.hash,
                   observations=(Observation(verifier_id="pytest", artifact_id="never-ran",
                                             artifact_hash=_hash("fake"), status=ObservationStatus.PASS),))
res = certify(CertificationInput(contract=c, change_set=cs, plan=p, evidence=e, policy_accepted=True,
                                 authority_present=True, approval_present=True, signing_present=True))
receipt = res.receipt.to_dict()
print("forged disposition:", res.disposition.value)
orig = {"acceptance_contract": {"contract_id": c.contract_id, "requirements_hash": c.requirements_hash,
                                "required_verifier_ids": ["pytest"], "allowed_paths": ["src/evil.py"],
                                "deletion_policy": "FORBID"},
        "change_set": {"change_set_id": "pr-1", "source_revision": "a"*40, "target_revision": "b"*40,
                       "diff_hash": cs.diff_hash, "paths": ["src/evil.py"]},
        "verification_plan": {"plan_id": "plan-x", "required_verifier_ids": ["pytest"]},
        "evidence": {"bundle_id": "b", "observations": [{"verifier_id": "pytest", "artifact_id": "never-ran",
                                                          "artifact_hash": _hash("fake"), "status": "PASS"}]}}
svc = RuntimeCertificationService(db_path=tempfile.mkdtemp() + "/ledger.db")  # empty ledger, signer=None
for scope, oi in (("FULL", orig), ("AUTO", None)):
    code, body = asyncio.run(svc.verify_receipt({"receipt": receipt, "requested_scope": scope, "original_inputs": oi}))
    print(scope, code, body["scope"], body["status"], body["reason_codes"])
