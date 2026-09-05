#!/usr/bin/env python3
"""Independent stdlib validators and bounded exhaustive checks for CP instances.

Input: JSON instance and JSON solver result. Assignment values and edge indices
are zero-based. An optimal/infeasible solver status alone is not a certificate.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
from pathlib import Path


def _int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def check_instance(instance):
    """Raise ValueError on malformed instance data; ignore descriptive metadata."""
    family = instance.get("family")
    n = instance.get("n")
    if not _int(n) or n < 1:
        raise ValueError("n must be a positive integer")
    if family == "scheduling":
        m, durations = instance.get("machines"), instance.get("durations")
        if not _int(m) or m < 1:
            raise ValueError("machines must be a positive integer")
        if not isinstance(durations, list) or len(durations) != n:
            raise ValueError("durations must contain n entries")
        if any(not _int(d) or d < 1 for d in durations):
            raise ValueError("durations must be positive integers")
    elif family in ("coloring", "vertex_cover"):
        edges = instance.get("edges")
        if not isinstance(edges, list):
            raise ValueError("edges must be a list")
        seen = set()
        for edge in edges:
            if not isinstance(edge, (list, tuple)) or len(edge) != 2:
                raise ValueError("every edge must have two endpoints")
            u, v = edge
            if not _int(u) or not _int(v) or not 0 <= u < v < n:
                raise ValueError("edges must use canonical endpoints 0 <= u < v < n")
            if (u, v) in seen:
                raise ValueError("duplicate edge")
            seen.add((u, v))
        if family == "coloring":
            k = instance.get("colors")
            if not _int(k) or k < 1:
                raise ValueError("colors must be a positive integer")
        else:
            weights = instance.get("weights")
            if not isinstance(weights, list) or len(weights) != n:
                raise ValueError("weights must contain n entries")
            if any(not _int(w) or w < 1 for w in weights):
                raise ValueError("weights must be positive integers")
    else:
        raise ValueError("unknown family")


def validate_assignment(instance, assignment):
    """Check original constraints directly, independently of solver code."""
    check_instance(instance)
    if not isinstance(assignment, list) or len(assignment) != instance["n"]:
        return {"valid": False, "error": "assignment must contain exactly n entries"}
    if any(not _int(x) for x in assignment):
        return {"valid": False, "error": "assignment entries must be integers, not booleans"}
    family = instance["family"]
    domain = instance.get("colors", instance.get("machines", 2))
    if any(not 0 <= x < domain for x in assignment):
        return {"valid": False, "error": "assignment entry outside variable domain"}
    if family == "coloring":
        for u, v in instance["edges"]:
            if assignment[u] == assignment[v]:
                return {"valid": False, "error": f"edge ({u},{v}) has equal colors"}
        return {"valid": True, "objective": 0}
    if family == "vertex_cover":
        for u, v in instance["edges"]:
            if not (assignment[u] or assignment[v]):
                return {"valid": False, "error": f"edge ({u},{v}) is uncovered"}
        objective = sum(w * x for w, x in zip(instance["weights"], assignment))
        return {"valid": True, "objective": objective}
    loads = [0] * instance["machines"]
    for machine, duration in zip(assignment, instance["durations"]):
        loads[machine] += duration
    return {"valid": True, "objective": max(loads), "loads": loads}


def exact_solve(instance, max_states=1_000_000):
    """Exhaustively enumerate small instances, or return unknown if too large.

    This deliberately simple independent oracle has no learned policy or CP
    solver dependency. State counts are enumeration counts, not search nodes.
    """
    check_instance(instance)
    family, n = instance["family"], instance["n"]
    domain = instance.get("colors", instance.get("machines", 2))
    states = domain ** n
    if states > max_states:
        return {"status": "unknown", "reason": "state budget", "candidate_states": states}
    best, best_assignment, examined = math.inf, None, 0
    for assignment in itertools.product(range(domain), repeat=n):
        examined += 1
        if family == "coloring":
            if any(assignment[u] == assignment[v] for u, v in instance["edges"]):
                continue
            return {"status": "optimal", "objective": 0, "assignment": list(assignment),
                    "states_examined": examined, "certificate": "feasible satisfaction witness"}
        if family == "vertex_cover":
            if any(not assignment[u] and not assignment[v] for u, v in instance["edges"]):
                continue
            objective = sum(w * x for w, x in zip(instance["weights"], assignment))
        else:
            loads = [0] * instance["machines"]
            for machine, duration in zip(assignment, instance["durations"]):
                loads[machine] += duration
            objective = max(loads)
        if objective < best:
            best, best_assignment = objective, list(assignment)
    if best_assignment is None:
        return {"status": "infeasible", "states_examined": examined,
                "certificate": "exhaustive enumeration"}
    return {"status": "optimal", "objective": best, "assignment": best_assignment,
            "states_examined": examined, "certificate": "exhaustive enumeration"}


def verify_infeasibility_certificate(instance):
    """Check an overlarge clique or an odd wheel requiring four colors."""
    if instance["family"] != "coloring":
        return False
    certificate = instance.get("infeasibility_certificate", {})
    edges = {tuple(e) for e in instance["edges"]}
    if certificate.get("type") == "odd_wheel":
        hub, rim = certificate.get("hub"), certificate.get("rim", [])
        vertices = [hub] + rim
        if (instance["colors"] != 3 or len(rim) < 5 or len(rim) % 2 != 1
                or any(not _int(v) for v in vertices)
                or len(set(vertices)) != len(vertices)
                or any(not 0 <= v < instance["n"] for v in vertices)):
            return False
        required = [(hub, v) for v in rim] + [(rim[i], rim[(i + 1) % len(rim)]) for i in range(len(rim))]
        return all(tuple(sorted(e)) in edges for e in required)
    if certificate.get("type") != "clique":
        return False
    vertices = certificate.get("vertices", [])
    if (len(vertices) <= instance["colors"] or any(not _int(v) for v in vertices)
            or len(set(vertices)) != len(vertices)
            or any(not 0 <= v < instance["n"] for v in vertices)):
        return False
    return all(tuple(sorted((u, v))) in edges for u, v in itertools.combinations(vertices, 2))


def validate_result(instance, result, brute_force=False, max_states=1_000_000):
    check_instance(instance)
    status = result.get("status")
    if status not in ("feasible", "optimal", "infeasible", "unknown"):
        return {"valid": False, "error": "unsupported solver status"}
    reference = exact_solve(instance, max_states) if brute_force else instance.get("reference", {})
    if status == "infeasible":
        if result.get("assignment") not in (None, []):
            return {"valid": False, "error": "infeasible result includes an assignment"}
        if reference.get("status") in ("feasible", "optimal"):
            return {"valid": False, "error": "infeasibility contradicts reference witness"}
        verified = reference.get("status") == "infeasible" or verify_infeasibility_certificate(instance)
        return {"valid": True, "infeasibility_verified": verified,
                "claims_verified": verified, "status": status}
    assignment = result.get("assignment")
    if status == "unknown" and assignment in (None, []):
        return {"valid": True, "claims_verified": True, "status": "unknown",
                "solution_checked": False}
    checked = validate_assignment(instance, assignment)
    if not checked["valid"]:
        return checked
    if reference.get("status") == "infeasible":
        return {"valid": False, "error": "feasible assignment contradicts reference infeasibility"}
    if "objective" in result:
        if not _int(result["objective"]) or result["objective"] != checked["objective"]:
            return {"valid": False, "error": "reported objective differs from recomputed objective",
                    "recomputed_objective": checked["objective"]}
    optimality_verified = instance["family"] == "coloring"
    if reference.get("status") == "optimal":
        if checked["objective"] < reference["objective"]:
            return {"valid": False, "error": "objective beats exact reference; reference or solver mismatch"}
        if status == "optimal" and checked["objective"] != reference["objective"]:
            return {"valid": False, "error": "claimed optimum differs from exact reference"}
        optimality_verified = checked["objective"] == reference["objective"]
    if instance["family"] == "scheduling":
        lower_bound = max(max(instance["durations"]),
                          (sum(instance["durations"]) + instance["machines"] - 1) // instance["machines"])
        checked["lower_bound"] = lower_bound
        optimality_verified = optimality_verified or checked["objective"] == lower_bound
    checked.update(status=status, solution_checked=True, optimality_verified=optimality_verified,
                   claims_verified=status != "optimal" or optimality_verified)
    return checked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("instance", type=Path)
    parser.add_argument("result", type=Path, nargs="?")
    parser.add_argument("--brute-force", action="store_true")
    parser.add_argument("--max-states", type=int, default=1_000_000)
    parser.add_argument("--require-verified-claims", action="store_true")
    args = parser.parse_args()
    try:
        instance = json.loads(args.instance.read_text())
        if args.result:
            result = json.loads(args.result.read_text())
            output = validate_result(instance, result, args.brute_force, args.max_states)
        elif args.brute_force:
            output = exact_solve(instance, args.max_states)
        else:
            check_instance(instance)
            output = {"valid": True, "instance": instance.get("id")}
        print(json.dumps(output, sort_keys=True))
        if not output.get("valid", True):
            return 1
        if args.require_verified_claims and not output.get("claims_verified", False):
            return 2
        return 0
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
