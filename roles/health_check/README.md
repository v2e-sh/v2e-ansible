# health_check

Fail-fast preflight gate, run first in `01-bootstrap`. Aborts the whole run early
if any node is unreachable (`wait_for_connection`), low on disk/memory (asserts),
or if control can't reach the other nodes across VLANs on SSH. Thresholds and
targets are in `defaults/main.yml`. Pure `ansible.builtin` — no collection deps.
