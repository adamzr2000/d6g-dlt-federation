#!/usr/bin/env python3
import sys
import time
import logging
import argparse
import shlex
from fabric import Connection
from invoke.exceptions import UnexpectedExit

# —— CONFIGURATION —— #
NODES = [
    {
        "host": "10.5.15.55",
        "user": "desire6g",
        "script_dir": "/home/desire6g/d6g-dlt-federation",
        "config_file": "blockchain-network/geth-poa/domain1.env",
        "domain_function": "consumer",
        "port": 8090,
    },
    {
        "host": "10.5.99.6",
        "user": "netcom",
        "script_dir": "/home/netcom/d6g-dlt-federation",
        "config_file": "blockchain-network/geth-poa/domain2.env",
        "domain_function": "provider",
        "port": 8090,
    },
    {
        "host": "10.5.99.5",
        "user": "netcom",
        "script_dir": "/home/netcom/d6g-dlt-federation",
        "config_file": "blockchain-network/geth-poa/domain3.env",
        "domain_function": "provider",
        "port": 8090,
    },
]

SSH_CONNECT_TIMEOUT = 30  # seconds
SLEEP_BETWEEN_NODES = 1   # seconds

# Wait/poll after starting to allow the container to come up
STARTUP_WAIT_SECONDS = 15
CHECK_INTERVAL_SECONDS = 1
CONTAINER_NAME = "blockchain-manager"

# —— LOGGER SETUP —— #
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# —— ARGPARSE —— #
parser = argparse.ArgumentParser(description="Start or stop the blockchain manager on all nodes.")
group = parser.add_mutually_exclusive_group(required=True)
group.add_argument("--start", action="store_true", help="Start the blockchain manager on all nodes")
group.add_argument("--stop", action="store_true", help="Stop the blockchain manager on all nodes")
args = parser.parse_args()
ACTION = "start" if args.start else "stop"

def build_start_cmd(script_dir, config_file, domain_function, port):
    sd = shlex.quote(script_dir)
    cf = shlex.quote(config_file)
    df = shlex.quote(domain_function)
    pt = shlex.quote(str(port))
    # Ensure script exists and is executable before running
    return (
        f"cd {sd} && test -x ./start_blockchain_manager.sh "
        f"&& ./start_blockchain_manager.sh --config {cf} --domain-function {df} --port {pt}"
    )

def build_stop_cmd():
    # Idempotent stop: only kill if exact-name container exists
    return "docker ps -q -f name=^/blockchain-manager$ | xargs -r docker kill"

def build_is_running_cmd():
    # Exit 0 if a running container with the exact name exists, else non-zero
    return 'test -n "$(docker ps -q -f name=^/blockchain-manager$ -f status=running)"'

def wait_for_container_running(conn):
    """Poll briefly until container is running; return True/False."""
    check_cmd = build_is_running_cmd()
    deadline = time.time() + STARTUP_WAIT_SECONDS
    while time.time() < deadline:
        # warn=True so we don't raise on non-zero; hide=True to keep output quiet
        result = conn.run(check_cmd, warn=True, hide=True, pty=False)
        if result.ok:
            return True
        time.sleep(CHECK_INTERVAL_SECONDS)
    return False

def main():
    failures = 0
    total = len(NODES)

    for idx, node in enumerate(NODES, start=1):
        host = node["host"]
        user = node["user"]
        script_dir = node["script_dir"]
        config_file = node["config_file"]
        domain_function = node["domain_function"]
        port = node["port"]

        cmd = (
            build_start_cmd(script_dir, config_file, domain_function, port)
            if ACTION == "start"
            else build_stop_cmd()
        )

        logger.info(f"[{idx}/{total}] {ACTION.upper()} on {user}@{host}")
        conn = Connection(host=host, user=user, connect_timeout=SSH_CONNECT_TIMEOUT)

        try:
            result = conn.run(cmd, warn=False, hide=False, pty=False)
            logger.info(f"[{idx}/{total}] Command OK on {host} (exit {result.exited})")

            if ACTION == "start":
                # Simple liveness check: container exists and is running
                alive = wait_for_container_running(conn)
                if alive:
                    logger.info(f"[{idx}/{total}] Container '{CONTAINER_NAME}' is RUNNING on {host}.")
                else:
                    logger.error(f"[{idx}/{total}] Container '{CONTAINER_NAME}' is NOT running on {host}.")
                    failures += 1

        except UnexpectedExit as e:
            code = e.result.exited if e.result else 1
            logger.error(f"[{idx}/{total}] Command exited non-zero on {host}: {code}")
            failures += 1
        except Exception as e:
            logger.error(f"[{idx}/{total}] SSH error on {host}: {e}")
            failures += 1

        # Optional small pause between hosts
        # if idx < total:
        #     time.sleep(SLEEP_BETWEEN_NODES)

    if failures:
        logger.error(f"Finished with {failures} failure(s) out of {total} node(s).")
        sys.exit(1)
    logger.info(f"All {total} node(s) completed successfully.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("Interrupted by user, exiting")
        sys.exit(1)
