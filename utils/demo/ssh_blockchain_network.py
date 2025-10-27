#!/usr/bin/env python3

import sys
import time
import logging
import argparse
from fabric import Connection, Config
from invoke.exceptions import UnexpectedExit

# —— CONFIGURATION —— #
# Each node can have its own sudo password (empty string means no sudo required)
NODES = [
    {
        "host": "10.5.15.55",
        "user": "desire6g",
        "script_dir": "/home/desire6g/d6g-dlt-federation/blockchain-network/geth-poa",
        "network_file": "domain1-geth-network.yml",
        "sudo_password": "desire6g2024;"
    },
    {
        "host": "10.5.99.6",
        "user": "netcom",
        "script_dir": "/home/netcom/d6g-dlt-federation/blockchain-network/geth-poa",
        "network_file": "domain2-geth-network.yml",
        "sudo_password": "netcom;"
    },
    {
        "host": "10.5.99.5",
        "user": "netcom",
        "script_dir": "/home/netcom/d6g-dlt-federation/blockchain-network/geth-poa",
        "network_file": "domain3-geth-network.yml",
        "sudo_password": "netcom;"
    },
]

# —— LOGGER SETUP —— #
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)

# —— ARGPARSE —— #
parser = argparse.ArgumentParser(description="Start or stop the PoA network on all nodes.")
group = parser.add_mutually_exclusive_group(required=True)
group.add_argument("--start", action="store_true", help="Start the network on all nodes")
group.add_argument("--stop", action="store_true", help="Stop the network on all nodes (uses sudo)")
args = parser.parse_args()

ACTION = 'start' if args.start else 'stop'

# —— MAIN EXECUTION —— #
def main():
    for idx, node in enumerate(NODES, start=1):
        host = node["host"]
        user = node["user"]
        script_dir = node["script_dir"]
        netfile = node["network_file"]
        sudo_pw = node.get("sudo_password", "")

        # Build per-node Fabric config
        cfg_params = {}
        if ACTION == 'stop' and sudo_pw:
            cfg_params["sudo"] = {"password": sudo_pw}
        cfg = Config(overrides=cfg_params)

        # Select command
        if ACTION == 'start':
            cmd = f"cd {script_dir} && ./start_geth_net.sh --file {netfile}"
        else:
            # wrap in bash -lc so cd builtin works under sudo
            cmd = f'bash -lc "cd {script_dir} && ./stop_geth_net.sh --file {netfile}"'

        logger.info(f"[{idx}/{len(NODES)}] {ACTION.upper()} on {user}@{host}")
        conn = Connection(host=host, user=user, config=cfg)

        try:
            if ACTION == 'stop':
                result = conn.sudo(cmd, warn=True, hide=False)
            else:
                result = conn.run(cmd, warn=True, hide=False)

            if result.exited == 0:
                logger.info(f"Success on {host}")
            else:
                logger.error(f"Non-zero exit ({result.exited}) on {host}")
        except UnexpectedExit as e:
            logger.error(f"Command failed on {host}: {e}")
        except Exception as e:
            logger.error(f"SSH error connecting to {host}: {e}")

        # Sleep before next node
        if idx < len(NODES):
            time.sleep(5)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("Interrupted by user, exiting")
        sys.exit(1)
