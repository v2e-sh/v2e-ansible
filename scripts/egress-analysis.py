#!/usr/bin/env python3
"""Classify a bounded egress-tap pcap set by source VLAN and destination.

Consumes the pcap files produced by roles/egress_tap (playbooks/ops/
egress-tap.yml --tags stop fetches them to
~/egress-tap-captures/<router>/). Never touches the network itself unless
--resolve-dns is passed explicitly (off by default).

Usage:
    python3 egress-analysis.py --input ~/egress-tap-captures/vyos01 \
        --report report.md --json report.json

Requires: scapy (pip install scapy). Reads pcap headers only; the tap's
default snaplen (96 bytes) means payloads generally aren't present to begin
with, but this script never inspects payload bytes regardless of snaplen.
"""
import argparse
import json
import socket
import sys
from collections import defaultdict
from pathlib import Path

try:
    from scapy.all import PcapReader, IP, TCP, UDP
except ImportError:
    sys.exit("scapy is required: pip install scapy")

# Mirrors v2e-tf/network.tf's subnet layout (network_prefix + octet).
# Override via --prefix if the lab's network_prefix var differs from 10.1.
DEFAULT_PREFIX = "10.1"
VLAN_OCTETS = {
    0: "mgmt (vyos)",
    1: "control",
    2: "services",
    3: "agent",
}

WELL_KNOWN_PORTS = {
    53: "DNS",
    123: "NTP",
    80: "HTTP",
    443: "HTTPS",
    22: "SSH",
}


def classify_vlan(ip: str, prefix: str) -> str:
    parts = ip.split(".")
    if len(parts) != 4 or ".".join(parts[:2]) != prefix:
        return "external/unknown"
    try:
        octet = int(parts[2])
    except ValueError:
        return "external/unknown"
    return VLAN_OCTETS.get(octet, f"unknown-octet-{octet}")


def classify_port(port: int) -> str:
    return WELL_KNOWN_PORTS.get(port, "other")


def iter_pcaps(input_dir: Path):
    files = sorted(input_dir.glob("*.pcap"))
    if not files:
        sys.exit(f"no .pcap files found under {input_dir}")
    for f in files:
        yield f


def analyze(input_dir: Path, prefix: str, resolve_dns: bool):
    # groups[vlan][dst_ip:port] -> {count, protocol, classification, first_seen, last_seen}
    groups = defaultdict(lambda: defaultdict(lambda: {
        "count": 0, "protocol": set(), "classification": None,
        "first_seen": None, "last_seen": None,
    }))
    total_packets = 0
    dropped_non_ip = 0

    for pcap_file in iter_pcaps(input_dir):
        with PcapReader(str(pcap_file)) as reader:
            for pkt in reader:
                total_packets += 1
                if IP not in pkt:
                    dropped_non_ip += 1
                    continue
                ip = pkt[IP]
                vlan = classify_vlan(ip.src, prefix)
                proto = None
                dport = None
                if TCP in pkt:
                    proto = "tcp"
                    dport = pkt[TCP].dport
                elif UDP in pkt:
                    proto = "udp"
                    dport = pkt[UDP].dport
                else:
                    proto = "other"

                key = f"{ip.dst}:{dport}" if dport is not None else f"{ip.dst}:-"
                entry = groups[vlan][key]
                entry["count"] += 1
                entry["protocol"].add(proto)
                entry["classification"] = classify_port(dport) if dport else "other"
                ts = float(pkt.time)
                if entry["first_seen"] is None or ts < entry["first_seen"]:
                    entry["first_seen"] = ts
                if entry["last_seen"] is None or ts > entry["last_seen"]:
                    entry["last_seen"] = ts

    resolved = {}
    if resolve_dns:
        for vlan, dests in groups.items():
            for key in dests:
                dst_ip = key.rsplit(":", 1)[0]
                if dst_ip in resolved:
                    continue
                try:
                    resolved[dst_ip] = socket.gethostbyaddr(dst_ip)[0]
                except (socket.herror, socket.gaierror, OSError):
                    resolved[dst_ip] = None

    return {
        "total_packets": total_packets,
        "dropped_non_ip": dropped_non_ip,
        "groups": groups,
        "resolved": resolved,
    }


def to_json(result: dict) -> str:
    serializable = {
        "total_packets": result["total_packets"],
        "dropped_non_ip": result["dropped_non_ip"],
        "resolved": result["resolved"],
        "groups": {
            vlan: {
                key: {
                    **entry,
                    "protocol": sorted(entry["protocol"]),
                }
                for key, entry in dests.items()
            }
            for vlan, dests in result["groups"].items()
        },
    }
    return json.dumps(serializable, indent=2, sort_keys=True)


def to_markdown(result: dict) -> str:
    lines = [
        "# Egress analysis report",
        "",
        f"Total packets: {result['total_packets']} "
        f"(non-IP dropped: {result['dropped_non_ip']})",
        "",
    ]
    for vlan in sorted(result["groups"]):
        dests = result["groups"][vlan]
        lines.append(f"## {vlan}")
        lines.append("")
        lines.append("| dst_ip:port | class | protocol | count | first seen | last seen | reverse DNS |")
        lines.append("|---|---|---|---|---|---|---|")
        for key, entry in sorted(dests.items(), key=lambda kv: -kv[1]["count"]):
            dst_ip = key.rsplit(":", 1)[0]
            rdns = result["resolved"].get(dst_ip) or ""
            lines.append(
                f"| {key} | {entry['classification']} | "
                f"{','.join(sorted(entry['protocol']))} | {entry['count']} | "
                f"{entry['first_seen']:.0f} | {entry['last_seen']:.0f} | {rdns} |"
            )
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path,
                         help="directory of .pcap files (egress_tap_fetch_dest)")
    parser.add_argument("--prefix", default=DEFAULT_PREFIX,
                         help="network_prefix from v2e-tf variables.tf (default: 10.1)")
    parser.add_argument("--report", type=Path, help="write Markdown report here")
    parser.add_argument("--json", type=Path, help="write JSON report here")
    parser.add_argument("--resolve-dns", action="store_true",
                         help="reverse-resolve destination IPs (issues real DNS "
                              "queries from wherever this script runs — off by "
                              "default, since this script is otherwise fully "
                              "offline/read-only against the pcap files)")
    args = parser.parse_args()

    result = analyze(args.input, args.prefix, args.resolve_dns)

    md = to_markdown(result)
    if args.report:
        args.report.write_text(md)
    else:
        print(md)

    if args.json:
        args.json.write_text(to_json(result))


if __name__ == "__main__":
    main()
