1. Start private ethereum network
```bash
python3 ssh_blockchain_network.py --start
```

- [eth-netstats](http://10.5.15.55:3000)
- [blockscout](http://10.5.15.55:26000)

2. Deploy federation smart contract
```bash
./deploy_smart_contract.sh --network-id 1337 --node-ip 10.5.15.55 --port 8545 --protocol http
```

3. Start blockchain managers
```bash
python3 ssh_blockchain_manager.py --start
```

4. Register domains
```bash
python3 register_domains.py
```

5. Start demo workflow
```bash
python3 run_experiments.py
```

5. Stop blockchain managers
```bash
python3 ssh_blockchain_network.py --stop
```

6. Stop private ethereum network
```bash
python3 ssh_blockchain_network.py --stop
```