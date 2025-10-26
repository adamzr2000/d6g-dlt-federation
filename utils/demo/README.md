1. Start Geth net
```bash
python3 ssh_blockchain_network.py --start
```

- [eth-netstats](http://10.5.15.55:3000)
- [blockscout](http://10.5.15.55:26000)

2. Deploy Federation Smart Contract
```bash
ssh desire6g@10.5.15.55 "cd adam/d6g-dlt-federation && ./deploy_smart_contract.sh --network-id 1337 --node-ip 10.5.15.55 --port 8545 --protocol http"
```

3. Start demo workflow
```bash
python3 run_experiments.py
```

4. Stop Geth net
```bash
python3 ssh_blockchain_network.py --stop
```