import hashlib
import json
import os

from apexquant_auth.rbac import (
    EvaluationStatus,
    authorize,
    evaluate,
    load_matrix,
    matrix_sha256,
    validate_permission,
)


def _repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, "..", "..", "..", ".."))


def test_matrix_matches_canonical_file() -> None:
    path = os.path.join(_repo_root(), "data", "rbac", "forbidden_matrix.yaml")
    with open(path, "rb") as f:
        canonical = hashlib.sha256(f.read()).hexdigest()
    assert matrix_sha256() == canonical, "matrix drift detected"


def test_shared_vectors_match() -> None:
    path = os.path.join(_repo_root(), "data", "rbac", "test_vectors.json")
    with open(path) as f:
        vectors = json.load(f)

    for case in vectors["evaluate"]:
        got = evaluate(case["plane"], case["permissions"], case["has_roles"])
        assert got.value == case["expected_status"], case["name"]

    for case in vectors["authorize"]:
        got = authorize(case["plane"], case["granted"], case["request"])
        assert got == case["expected_allow"], case["name"]


def test_grammar_lock() -> None:
    assert validate_permission("execution:*") is None
    assert validate_permission("execution:modify:OMS-1") is None
    for bad in ("exec*", "execution:sub*", "Execution:submit", "execution"):
        try:
            validate_permission(bad)
            raise AssertionError(f"should have rejected {bad}")
        except Exception:
            pass