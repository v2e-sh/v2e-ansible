# Docker deployment — run from the control node

Installs Docker (CE + Compose v2 plugin) on the **control** and **services** hosts
using the vendored `docker` role (geerlingguy/ansible-role-docker, pinned to 8.0.0).

## Execution model

Ansible runs **from within the control node**, which already has SSH access to the
internal network. No jump host, ProxyJump, or extra key distribution required.

| Host      | How it's reached                                              |
|-----------|--------------------------------------------------------------|
| `control` | locally — `ansible_connection: local`                        |
| `services`| direct SSH from control via `~/.ssh/config` alias → 10.1.2.10 |

## 1. Get the folder onto control

From your workstation, through the router forward:

```bash
scp -P 2201 -r ansible v2e@192.168.1.2:~/ansible
# or, on control:  git clone <your-repo> ~/ansible
```

## 2. Install Ansible on control (one-time)

```bash
sudo apt update && sudo apt install -y ansible      # or: pipx install ansible
```

> Needs working internet egress. If outbound HTTPS still hangs (the MTU/MSS
> black-hole on the router path), fix that first — otherwise both this step and
> the Docker download below will time out.

## 3. Run it

```bash
cd ~/ansible
ansible all -m ping              # connectivity check (control + services)
ansible-playbook site.yml        # deploy Docker
```

Add `-K` if `v2e` needs a sudo password on any node (control has passwordless sudo;
services is unverified).

## Layout

```
ansible.cfg            # points at inventory/ and roles/, sudo defaults
inventory/hosts.ini    # control (local) + services (direct SSH)
site.yml               # applies the docker role to control:services
requirements.yml       # Galaxy source for the vendored role (optional re-pull)
roles/docker/          # vendored geerlingguy.docker role
```
# v2e-ansible
