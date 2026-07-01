# health_check

Fail-fast preflight gate, run first in `01-bootstrap`. **ANS-1: scaffold only.**
ANS-2 adds mesh `wait_for_connection`, disk/memory asserts, and inter-VLAN
reachability so the rest of the run aborts early on an unhealthy node.
