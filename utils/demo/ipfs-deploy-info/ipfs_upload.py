import logging
import json
import os
from typing import Dict, Any, Union
import requests

# IPFS_ENDPOINT = "http://localhost:5001/api/v0"
IPFS_ENDPOINT = "http://10.5.15.55:5001/api/v0"

OUTPUT_PATH = "./deployed_cids.json"

def ipfs_add(file_path: str, api_base: str, pin: bool = True, timeout: int = 30) -> Dict[str, Any]:
    url = f"{api_base}/add"
    params = {"pin": "true" if pin else "false"}
    with open(file_path, "rb") as f:
        files = {"file": (file_path, f)}
        r = requests.post(url, params=params, files=files, timeout=timeout)
    r.raise_for_status()
    lines = r.text.strip().splitlines()
    if not lines:
        raise RuntimeError("Empty response from IPFS /add")
    return json.loads(lines[-1])

def ipfs_cat(cid: str, api_base: str, timeout: int = 60, decode: bool = True) -> Union[str, bytes]:
    url = f"{api_base}/cat"
    r = requests.post(url, params={"arg": cid}, timeout=timeout)
    r.raise_for_status()
    if decode:
        try:
            return r.content.decode("utf-8")
        except UnicodeDecodeError:
            return r.content.decode("latin-1", errors="replace")
    return r.content

def _atomic_write_json(path: str, data: Any) -> None:
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp_path, path)

# --- Example trigger (put under your __main__ guard) ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        source_files = ["domain1-deploy-info-service1.json", "domain1-deploy-info-service2.yml"]
        deployed: Dict[str, str] = {}

        for fname in source_files:
            logging.info(f"Adding to IPFS: {fname}")
            res = ipfs_add(file_path=fname, api_base=IPFS_ENDPOINT)
            cid = res["Hash"]
            deployed[fname] = cid
            logging.info(f"Added {fname} → CID {cid}")

            logging.info(f"Cating from IPFS (CID: {cid})")
            text = ipfs_cat(cid=cid, api_base=IPFS_ENDPOINT)
            print(text)

        # Write resulting CIDs
        logging.info(f"Writing CIDs to {OUTPUT_PATH}")
        _atomic_write_json(OUTPUT_PATH, deployed)
        logging.info("Done.")

    except Exception as e:
        logging.error(f"IPFS request failed: {e}")
