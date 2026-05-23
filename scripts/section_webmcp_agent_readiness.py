#!/usr/bin/env python3
"""
AVR §2.7 Agent Readiness Audit (WebMCP + A2A AgentCard)

Implements the agent-readiness audit signals defined by AVR v1.1.0 per the
codex roll-up node [[webmcp-agent-readiness]] and the split glossary at
~/.claude/build-glossary-outputs/webmcp-agent-readiness-2026-05-22.md.

Three checks, all [VERIFIABLE], all rank-10 (high-stake AI surface signal):

  Check W1: .well-known/webmcp manifest exists + valid JSON
            + tool-list non-empty + per-tool fields present
  Check W2: /.well-known/agent.json AgentCard exists + valid JSON
            + describes skills + JSON-RPC 2.0 endpoint declared
  Check W3: Wire-protocol probe — if endpoint advertised, return shape OK

Verdict bands:
  AGENT-READY      = W1 PASS AND (W2 PASS OR site declares no agent surface)
  AGENT-PARTIAL    = W1 PASS only, OR W2 PASS only
  AGENT-NOT-READY  = neither W1 nor W2 pass

Cost: $0 (HTTP GET + local JSON validation; no API spend).

Output JSON shape: section_webmcp_agent_readiness key, ready to merge into
the existing AVR audit JSON or returned standalone.

References:
  - WebMCP W3C spec: https://webmachinelearning.github.io/webmcp/
  - Chrome 146 Canary: chrome://flags "WebMCP for testing"
  - WellKnownMCP standards map: https://wellknownmcp.org/
  - Codex roll-up: ~/.claude/codex/nodes/webmcp-agent-readiness.md
"""

import argparse
import json
import sys
from typing import Any
from urllib.parse import urlparse

import requests


WEBMCP_PATH = "/.well-known/webmcp"
AGENTCARD_PATH = "/.well-known/agent.json"

USER_AGENT = (
    "AVR-citability/1.1 "
    "(Section-WebMCP agent-readiness audit; https://citability.dev; "
    "contact: chudi@chudi.dev)"
)

REQUEST_TIMEOUT_SEC = 6

# Manifest fields the W3C draft expects per tool entry. Field-name shape may
# evolve before stable Chrome rollout; treat presence-of-keys as the strong
# signal, schema-strict validation as weaker (allow extension keys).
TOOL_REQUIRED_FIELDS = ("name", "description")
TOOL_RECOMMENDED_FIELDS = ("input_schema", "auth", "rate_limit", "endpoint")

# A2A AgentCard fields per agentwiki.org / wellknownmcp.org standards map.
AGENTCARD_REQUIRED_FIELDS = ("name", "skills")
AGENTCARD_RECOMMENDED_FIELDS = ("description", "endpoint", "rpc")


def _site_root(url: str) -> str:
    if not url.startswith("http"):
        url = f"https://{url}"
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def _fetch_json(url: str) -> tuple[Any | None, str | None]:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    try:
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SEC, allow_redirects=True)
        if resp.status_code == 404:
            return None, "not_found"
        if resp.status_code >= 400:
            return None, f"http_{resp.status_code}"
        try:
            return resp.json(), None
        except (ValueError, json.JSONDecodeError):
            return None, "invalid_json"
    except requests.RequestException as e:
        return None, f"network_error:{type(e).__name__}"


def check_webmcp_manifest(site_root: str) -> dict[str, Any]:
    """Check W1: .well-known/webmcp manifest presence + structure."""
    url = f"{site_root}{WEBMCP_PATH}"
    result: dict[str, Any] = {
        "id": "webmcp-manifest-present",
        "label": "VERIFIABLE",
        "passed": False,
        "evidence": [],
        "signal_hierarchy_rank": 10,
        "url_probed": url,
    }

    data, err = _fetch_json(url)
    if err:
        result["evidence"].append({"error": err, "url": url})
        return result
    if not isinstance(data, dict):
        result["evidence"].append({"error": "manifest_not_object", "got_type": type(data).__name__})
        return result

    tools = data.get("tools") or data.get("tool_list") or []
    if not isinstance(tools, list) or len(tools) == 0:
        result["evidence"].append({
            "error": "tool_list_missing_or_empty",
            "manifest_keys": sorted(list(data.keys())),
        })
        return result

    tool_audits = []
    valid_tool_count = 0
    for i, tool in enumerate(tools[:20]):  # cap at 20 tools audited
        if not isinstance(tool, dict):
            tool_audits.append({"index": i, "valid": False, "error": "tool_not_object"})
            continue
        missing_required = [f for f in TOOL_REQUIRED_FIELDS if f not in tool]
        missing_recommended = [f for f in TOOL_RECOMMENDED_FIELDS if f not in tool]
        tool_valid = len(missing_required) == 0
        if tool_valid:
            valid_tool_count += 1
        tool_audits.append({
            "index": i,
            "name": tool.get("name", "<unnamed>"),
            "valid": tool_valid,
            "missing_required": missing_required,
            "missing_recommended": missing_recommended,
        })

    result["evidence"].append({
        "manifest_tool_count": len(tools),
        "valid_tool_count": valid_tool_count,
        "tool_audits": tool_audits,
    })

    # Pass criterion: at least 1 valid tool entry with required fields.
    result["passed"] = valid_tool_count >= 1
    return result


def check_agentcard(site_root: str) -> dict[str, Any]:
    """Check W2: /.well-known/agent.json AgentCard presence + structure."""
    url = f"{site_root}{AGENTCARD_PATH}"
    result: dict[str, Any] = {
        "id": "agentcard-present",
        "label": "VERIFIABLE",
        "passed": False,
        "evidence": [],
        "signal_hierarchy_rank": 8,  # adjacent to WebMCP; not all sites are "agents"
        "url_probed": url,
    }

    data, err = _fetch_json(url)
    if err:
        result["evidence"].append({"error": err, "url": url, "note": "AgentCard is optional for non-agent sites; absence is not penalized"})
        result["optional_signal"] = True
        return result
    if not isinstance(data, dict):
        result["evidence"].append({"error": "agentcard_not_object", "got_type": type(data).__name__})
        return result

    missing_required = [f for f in AGENTCARD_REQUIRED_FIELDS if f not in data]
    missing_recommended = [f for f in AGENTCARD_RECOMMENDED_FIELDS if f not in data]

    skills = data.get("skills") or []
    skill_count = len(skills) if isinstance(skills, list) else 0

    result["evidence"].append({
        "agentcard_keys": sorted(list(data.keys())),
        "skill_count": skill_count,
        "missing_required": missing_required,
        "missing_recommended": missing_recommended,
    })
    result["passed"] = len(missing_required) == 0 and skill_count >= 1
    return result


def check_wire_protocol(site_root: str, manifest_data: dict | None, agentcard_data: dict | None) -> dict[str, Any]:
    """Check W3: light wire-protocol probe — endpoint advertised?

    We do NOT execute a tool call (could trigger side effects). We only
    verify that endpoint URLs declared in the manifest/AgentCard resolve to
    something other than a 404.
    """
    result: dict[str, Any] = {
        "id": "wire-protocol-endpoint-resolves",
        "label": "VERIFIABLE",
        "passed": False,
        "evidence": [],
        "signal_hierarchy_rank": 7,
        "optional_signal": True,
    }

    endpoints_to_probe: list[str] = []

    # Endpoints from WebMCP manifest tools
    if manifest_data and isinstance(manifest_data, dict):
        for tool in (manifest_data.get("tools") or manifest_data.get("tool_list") or [])[:5]:
            if isinstance(tool, dict) and tool.get("endpoint"):
                endpoints_to_probe.append(tool["endpoint"])

    # Endpoint from AgentCard
    if agentcard_data and isinstance(agentcard_data, dict):
        endpoint = agentcard_data.get("endpoint") or agentcard_data.get("rpc")
        if isinstance(endpoint, str):
            endpoints_to_probe.append(endpoint)
        elif isinstance(endpoint, dict) and endpoint.get("url"):
            endpoints_to_probe.append(endpoint["url"])

    if not endpoints_to_probe:
        result["evidence"].append({"note": "no endpoints declared in manifest or AgentCard; nothing to probe"})
        return result

    probe_results = []
    pass_count = 0
    for ep in endpoints_to_probe[:5]:  # cap probes
        # Resolve relative URLs against site root
        if ep.startswith("/"):
            ep_url = f"{site_root}{ep}"
        elif not ep.startswith("http"):
            ep_url = f"{site_root}/{ep}"
        else:
            ep_url = ep

        headers = {"User-Agent": USER_AGENT}
        try:
            # OPTIONS first (lighter; many JSON-RPC endpoints respond to it).
            resp = requests.options(ep_url, headers=headers, timeout=REQUEST_TIMEOUT_SEC)
            status = resp.status_code
            if status == 404:
                # Try HEAD as fallback (some servers don't implement OPTIONS).
                resp = requests.head(ep_url, headers=headers, timeout=REQUEST_TIMEOUT_SEC, allow_redirects=True)
                status = resp.status_code
            probe_pass = status != 404 and status < 500
            if probe_pass:
                pass_count += 1
            probe_results.append({"endpoint": ep_url, "status": status, "resolved": probe_pass})
        except requests.RequestException as e:
            probe_results.append({"endpoint": ep_url, "error": type(e).__name__, "resolved": False})

    result["evidence"].append({"probe_results": probe_results, "pass_count": pass_count})
    result["passed"] = pass_count >= 1
    return result


def section_verdict(w1_passed: bool, w2_passed: bool, w2_optional: bool, w3_passed: bool) -> str:
    """Map check results to AGENT-READY band.

    AGENT-READY     = W1 PASS AND (W2 PASS OR W2 optional/site-not-agent-flavored)
    AGENT-PARTIAL   = W1 PASS only, OR W2 PASS only
    AGENT-NOT-READY = neither W1 nor W2 pass
    """
    if w1_passed and (w2_passed or w2_optional):
        return "AGENT-READY"
    if w1_passed or w2_passed:
        return "AGENT-PARTIAL"
    return "AGENT-NOT-READY"


def run_section_webmcp_agent_readiness(url: str) -> dict[str, Any]:
    """Run the full §2.7 Agent Readiness section. Returns the section JSON."""
    site_root = _site_root(url)

    w1 = check_webmcp_manifest(site_root)
    # Capture manifest data for W3 probe (if W1 fetched something).
    manifest_data = None
    if w1["passed"]:
        url_probed = w1.get("url_probed")
        if url_probed:
            manifest_data, _ = _fetch_json(url_probed)

    w2 = check_agentcard(site_root)
    agentcard_data = None
    if w2["passed"]:
        url_probed = w2.get("url_probed")
        if url_probed:
            agentcard_data, _ = _fetch_json(url_probed)

    w3 = check_wire_protocol(site_root, manifest_data, agentcard_data)

    verdict = section_verdict(
        w1_passed=w1["passed"],
        w2_passed=w2["passed"],
        w2_optional=w2.get("optional_signal", False) and not w2["passed"],
        w3_passed=w3["passed"],
    )

    recommendations = []
    if not w1["passed"]:
        recommendations.append({
            "id": "rec-publish-webmcp-manifest",
            "priority": 1,
            "action": (
                f"Publish a WebMCP manifest at {site_root}{WEBMCP_PATH}. "
                "Minimum viable: JSON with a 'tools' array containing at least one entry "
                "with 'name' and 'description' fields. See https://webmachinelearning.github.io/webmcp/ for full spec."
            ),
        })
    if not w2["passed"] and not w2.get("optional_signal"):
        recommendations.append({
            "id": "rec-publish-agentcard",
            "priority": 2,
            "action": (
                f"Publish an A2A AgentCard at {site_root}{AGENTCARD_PATH} if your site exposes agent skills. "
                "Required fields: 'name', 'skills' (array). See wellknownmcp.org for the convention."
            ),
        })
    if w1["passed"] and not w3["passed"]:
        recommendations.append({
            "id": "rec-verify-tool-endpoints",
            "priority": 3,
            "action": (
                "Your WebMCP manifest is published but its declared tool endpoints did not resolve. "
                "Verify each tool's 'endpoint' field points to a live URL that accepts JSON-RPC 2.0 requests."
            ),
        })

    return {
        "section_id": "section_webmcp_agent_readiness",
        "section_name": "Agent Readiness (WebMCP + A2A AgentCard)",
        "url_audited": url,
        "site_root": site_root,
        "checks": [w1, w2, w3],
        "section_verdict": verdict,
        "pass_count": sum(1 for c in (w1, w2, w3) if c["passed"]),
        "total_checks": 3,
        "recommendations": recommendations,
        "spec_version": "AVR v1.1.0 §2.7 (WebMCP W3C draft, Chrome 146 Canary)",
        "cost_usd": 0.0,
        "label": "VERIFIABLE",
    }


def main():
    parser = argparse.ArgumentParser(
        description="AVR §2.7 Agent Readiness Audit (WebMCP + A2A AgentCard)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python section_webmcp_agent_readiness.py https://citability.dev
  python section_webmcp_agent_readiness.py example.com -o output.json
  python section_webmcp_agent_readiness.py example.com --quiet

Cost: $0 (HTTP GET only, no API spend).
        """,
    )
    parser.add_argument("url", help="URL to audit")
    parser.add_argument("-o", "--output", help="Write JSON result to this path (otherwise print to stdout)")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-check progress prints")
    args = parser.parse_args()

    if not args.quiet:
        print(f"[section-webmcp] auditing {args.url} ...", file=sys.stderr)
    result = run_section_webmcp_agent_readiness(args.url)
    if not args.quiet:
        print(f"[section-webmcp] verdict: {result['section_verdict']} ({result['pass_count']}/{result['total_checks']} checks pass)", file=sys.stderr)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
        if not args.quiet:
            print(f"[section-webmcp] wrote {args.output}", file=sys.stderr)
    else:
        print(json.dumps(result, indent=2))

    # Exit code reflects verdict: 0 if AGENT-READY, 1 if AGENT-PARTIAL, 2 if AGENT-NOT-READY.
    code_map = {"AGENT-READY": 0, "AGENT-PARTIAL": 1, "AGENT-NOT-READY": 2}
    sys.exit(code_map.get(result["section_verdict"], 2))


if __name__ == "__main__":
    main()
