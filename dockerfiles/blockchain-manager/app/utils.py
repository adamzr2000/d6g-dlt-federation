# utils.py

import re
import logging
import csv
import requests
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional
import os
import json
import copy
from yaml.representer import SafeRepresenter

# Get the logger defined in main.py
logger = logging.getLogger(__name__)

def truncate_text(s: str, max_lines=50, max_chars=5000):
    lines = s.splitlines()
    if len(lines) > max_lines:
        s = "\n".join(lines[:max_lines]) + f"\n... (truncated, +{len(lines)-max_lines} lines)"
    if len(s) > max_chars:
        s = s[:max_chars] + f"\n... (truncated to {max_chars} chars)"
    return s

def extract_service_requirements(formatted_requirements: str) -> dict:
    requirements_dict = {}
    
    # Split the string by ';' and process each key-value pair
    for entry in formatted_requirements.split(";"):
        entry = entry.strip()
        if "=" in entry:  # Ensure valid key-value pairs
            key, value = entry.split("=", 1)
            key = key.strip()
            value = value.strip()
            
            # Convert numeric values from string to appropriate type
            if value.isdigit():
                value = int(value)
            elif value.replace(".", "", 1).isdigit():  # Handle float values
                value = float(value)
            elif value.lower() == "none":  # Convert 'None' string to Python None
                value = None
            
            requirements_dict[key] = value
    
    return requirements_dict

def create_csv_file(file_path, header, data):
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)  # ensure /experiments exists

    with open(file_path, 'w', encoding='UTF8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(data)
    logger.info(f"Data saved to {file_path}")

def ipfs_add(file_path: str, api_base: str, pin: bool = True, timeout: int = 30):
    url = f"{api_base}/add"
    params = {"pin": "true" if pin else "false"}

    basename = os.path.basename(file_path)                   # <-- key change
    with open(file_path, "rb") as f:
        files = {"file": (basename, f)}                      # <-- no directories in multipart filename
        r = requests.post(url, params=params, files=files, timeout=timeout)
    r.raise_for_status()

    # If IPFS still returns multiple NDJSON lines, pick the file object by Name
    objs = [json.loads(line) for line in r.text.strip().splitlines() if line.strip()]
    # Prefer the object whose Name == basename; fallback to last
    obj = next((o for o in objs if o.get("Name") == basename), objs[-1])
    return obj  # contains "Hash" (CID), "Name", "Size"

def ipfs_cat(cid: str, api_base: str, timeout: int = 30, decode: bool = True) -> str:
    url = f"{api_base}/cat"
    r = requests.post(url, params={"arg": cid}, timeout=timeout)
    r.raise_for_status()
    if decode:
        try:
            return r.content.decode("utf-8")
        except UnicodeDecodeError:
            return r.content.decode("latin-1", errors="replace")
    return r.content

def load_yaml_file(path: str) -> List[Dict[str, Any]]:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"YAML file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        docs = [doc for doc in yaml.safe_load_all(f) if isinstance(doc, dict)]
    if not docs:
        raise ValueError(f"No YAML documents found in: {path}")
    return docs

class _LiteralStr(str):
    """Marker to dump a Python str using YAML literal block style ('|')."""
    pass

def _literal_str_representer(dumper, data):
    return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')

class _LiteralDumper(yaml.SafeDumper):
    pass

_LiteralDumper.add_representer(_LiteralStr, _literal_str_representer)


def _beautify_multus_nad_config(obj: Dict[str, Any]) -> Dict[str, Any]:
    """
    If obj is a NetworkAttachmentDefinition and spec.config is a JSON string,
    dump it as a YAML literal block (|) and pretty-indent the JSON.
    """
    if not isinstance(obj, dict):
        return obj
    if obj.get("kind") != "NetworkAttachmentDefinition":
        return obj

    spec = obj.get("spec") or {}
    cfg = spec.get("config")
    if isinstance(cfg, str) and cfg.strip():
        pretty = cfg.strip()
        # Try to pretty-print JSON if valid; otherwise keep as-is
        try:
            pretty = json.dumps(json.loads(pretty), indent=2)
        except Exception:
            pass
        # Ensure trailing newline so the block prints cleanly
        spec["config"] = _LiteralStr(pretty + ("\n" if not pretty.endswith("\n") else ""))
        obj["spec"] = spec
    return obj

def get_vxlan_network_config(
    docs: List[Dict[str, Any]],
    overlay_name: Optional[str] = None,
) -> Dict[str, Any]:
    for doc in docs:
        if doc.get("kind") == "NetworkOverlayConfig":
            if overlay_name and doc.get("metadata", {}).get("name") != overlay_name:
                continue
            spec = doc.get("spec", {}) or {}
            net = spec.get("network", {}) or {}
            endpoints = spec.get("endpoints", []) or []
            return {
                "name": doc.get("metadata", {}).get("name"),
                "vni": net.get("vni"),
                "overlaySubnet": net.get("overlaySubnet"),
                "udpPort": net.get("udpPort"),
                "endpoints": [e.get("name") for e in endpoints if isinstance(e, dict)],
            }
    raise ValueError("No NetworkOverlayConfig found"
                     + (f" with name '{overlay_name}'" if overlay_name else ""))

def _find_overlay(
    docs: List[Dict[str, Any]],
    overlay_name: str
) -> Dict[str, Any]:
    for doc in docs:
        if doc.get("kind") == "NetworkOverlayConfig" and doc.get("metadata", {}).get("name") == overlay_name:
            spec = doc.get("spec", {}) or {}
            net = spec.get("network", {}) or {}
            endpoints = spec.get("endpoints", []) or []
            return {
                "name": overlay_name,
                "vni": net.get("vni"),
                "overlaySubnet": net.get("overlaySubnet"),
                "udpPort": net.get("udpPort"),
                "protocol": net.get("protocol"),
                "endpoints": [e.get("name") for e in endpoints if isinstance(e, dict)],
            }
    raise ValueError(f"No NetworkOverlayConfig found with name '{overlay_name}'")

def get_vtep_node_config(
    docs: List[Dict[str, Any]],
    node_name: str,
    overlay_name: Optional[str] = None,
    include_overlay: bool = True,
) -> Dict[str, Any]:
    # First locate the VTEP node
    match: Dict[str, Any] = {}
    for doc in docs:
        if doc.get("kind") == "VtepNodeConfig" and doc.get("metadata", {}).get("name") == node_name:
            spec = doc.get("spec", {}) or {}
            match = {
                "name": node_name,
                "overlayRef": spec.get("overlayRef"),
                "endpointRef": spec.get("endpointRef"),
                "vtepIP": spec.get("vtepIP"),
                "addressPool": spec.get("addressPool"),
            }
            break
    if not match:
        raise ValueError(f"No VtepNodeConfig found for node '{node_name}'")

    # If caller specified an overlay_name, ensure it matches the node's overlayRef
    if overlay_name is not None and match.get("overlayRef") != overlay_name:
        raise ValueError(
            f"VTEP '{node_name}' overlayRef='{match.get('overlayRef')}' "
            f"does not match requested overlay_name='{overlay_name}'"
        )

    # Optionally attach overlay details (resolve either requested overlay_name or node's overlayRef)
    if include_overlay:
        resolved_overlay_name = overlay_name or match.get("overlayRef")
        if resolved_overlay_name:
            match["overlay"] = _find_overlay(docs, resolved_overlay_name)

    return match

def get_k8s_manifest(
    docs: List[Dict[str, Any]],
    include_kinds: Optional[List[str]] = None,
    as_yaml: bool = False,
):
    """
    Collect a unified manifest of selected Kubernetes resource kinds.
    Defaults: Pod, Deployment, Service, NetworkAttachmentDefinition (Multus).
    Returns list[dict], or multi-doc YAML if as_yaml=True.
    """
    default_kinds = {"Pod", "Deployment", "Service", "NetworkAttachmentDefinition"}
    kinds = set(include_kinds) if include_kinds else default_kinds

    selected = [d for d in docs if isinstance(d, dict) and d.get("kind") in kinds]
    if not selected:
        raise ValueError(f"No Kubernetes manifests found for kinds: {sorted(kinds)}")

    # Work on a copy so we don’t mutate the original docs
    selected = [copy.deepcopy(d) for d in selected]
    # Beautify Multus NAD config so it prints as a literal block
    selected = [_beautify_multus_nad_config(d) for d in selected]

    if as_yaml:
        # Use our dumper that knows how to print _LiteralStr with '|'
        return "\n---\n".join(
            yaml.dump(d, Dumper=_LiteralDumper, sort_keys=False).strip() for d in selected
        )

    return selected


def vxlan_create(vni: int, iface: str, port: int, vxlan_ip: str,
                 remote_ips: List[str], base_url: str):
    r = requests.post(f"{base_url}/vxlan",
                      json={"vni": vni, "iface": iface, "port": port,
                            "vxlan_ip": vxlan_ip, "remote_ips": remote_ips},
                      timeout=10)
    r.raise_for_status()
    return r.json()

def vxlan_add_peers(vxlan_iface: str, peers: List[str], base_url: str):
    r = requests.post(f"{base_url}/vxlan/{vxlan_iface}/peers",
                      json={"peers": peers}, timeout=10)
    r.raise_for_status()
    return r.json()

def vxlan_delete(vxlan_iface: str, base_url: str):
    r = requests.delete(f"{base_url}/vxlan/{vxlan_iface}", timeout=10)
    r.raise_for_status()
    return r.json()

def vxlan_ping(dst: str, base_url: str, count: int = 4, interval: float = 1.0, timeout: int = 10) -> Dict[str, Any]:
    """
    Call the REST /ping endpoint and return parsed JSON.
    Returns keys: dest, count, interval, sent, received, loss_pct, times_ms, exit_code
    """
    params = {"dst": dst, "count": count, "interval": interval}
    r = requests.get(f"{base_url}/ping", params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()

def pretty(obj):  # tiny helper
    print(json.dumps(obj, indent=2))