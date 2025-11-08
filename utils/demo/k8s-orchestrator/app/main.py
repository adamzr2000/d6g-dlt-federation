# main.py
import os
import sys
import tempfile
import logging
import uuid
import time
from datetime import datetime
from threading import Lock
from typing import List, Tuple, Dict, Any

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse

from kubernetes import client, config, utils
from kubernetes.client import ApiClient
from kubernetes.client.rest import ApiException

# -------------------------
# Logging
# -------------------------
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("k8s-api")

# -------------------------
# Kubernetes API Initialization (as requested)
# -------------------------
try:
    config.load_kube_config(config_file="/config/k8s-cluster-config.yaml")
    log.info("Successfully loaded kubeconfig from /config/k8s-cluster-config.yaml")
except Exception as e:
    log.error(f"Failed to load kubeconfig: {e}")
    sys.exit(1)

api_client = ApiClient()
core_api = client.CoreV1Api()
version_api = client.VersionApi()
apps_api = client.AppsV1Api() 

# -------------------------
# Simple in-memory registry
# -------------------------
# Structure:
# REGISTRY[deployment_id] = {
#   "filename": str,
#   "applied_at": iso8601 str,
#   "objects": List[Tuple[apiVersion, kind, name]],
#   "yaml_text": str,   # original uploaded YAML text
# }
REGISTRY: Dict[str, Dict[str, Any]] = {}
REGISTRY_LOCK = Lock()

# -------------------------
# FastAPI app
# -------------------------
app = FastAPI(title="K8s Simple Apply/Delete API with Registry")

def _write_temp(upload: UploadFile) -> str:
    suffix = os.path.splitext(upload.filename or "manifest.yaml")[-1] or ".yaml"
    fd, path = tempfile.mkstemp(prefix="k8s-", suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(upload.file.read())
    return path

def _summarize(results: List) -> List[Tuple[str, str, str]]:
    """Extract (apiVersion, kind, metadata.name) from returned objects."""
    out = []
    for obj in results or []:
        try:
            av = getattr(obj, "api_version", None) or "unknown"
            kd = getattr(obj, "kind", None) or obj.__class__.__name__
            md = getattr(obj, "metadata", None)
            nm = getattr(md, "name", None) if md else None
            out.append((av, kd, nm or "unknown"))
        except Exception:
            try:
                # dict-like
                av = obj.get("apiVersion", "unknown")
                kd = obj.get("kind", "unknown")
                nm = (obj.get("metadata") or {}).get("name", "unknown")
                out.append((av, kd, nm))
            except Exception:
                out.append(("unknown", obj.__class__.__name__, "unknown"))
    return out

def _wait_ready(objects: List[Tuple[str, str, str]], namespace: str = "default", timeout: int = 120):
    """
    Wait for Pods to be Ready and Deployments to be Available.
    'objects' is the (apiVersion, kind, name) list from _summarize().
    """
    deadline = time.time() + timeout

    # Collect names by kind
    pod_names = [n for _, k, n in objects if k == "Pod"]
    dep_names = [n for _, k, n in objects if k == "Deployment"]

    # Wait for Pods → Ready condition True
    for name in pod_names:
        while True:
            if time.time() > deadline:
                raise TimeoutError(f"Pod/{name} not Ready within {timeout}s (ns={namespace})")
            p = core_api.read_namespaced_pod(name=name, namespace=namespace)
            conds = p.status.conditions or []
            if any(c.type == "Ready" and c.status == "True" for c in conds):
                break
            time.sleep(1)

    # Wait for Deployments → Available and observedGeneration up-to-date
    for name in dep_names:
        while True:
            if time.time() > deadline:
                raise TimeoutError(f"Deployment/{name} not Available within {timeout}s (ns={namespace})")
            d = apps_api.read_namespaced_deployment_status(name=name, namespace=namespace)
            spec_repl = d.spec.replicas or 0
            avail = d.status.available_replicas or 0
            gen_ok = (d.status.observed_generation or 0) >= (d.metadata.generation or 0)
            if gen_ok and avail >= spec_repl:
                break
            time.sleep(1)


@app.get("/health")
def health():
    """Very basic health check against the cluster."""
    try:
        ver = version_api.get_code()
        nodes = core_api.list_node()
        return {
            "status": "ok",
            "kubernetes_version": {
                "major": ver.major,
                "minor": ver.minor,
                "gitVersion": ver.git_version,
                "platform": ver.platform,
            },
            "nodes_count": len(nodes.items or []),
        }
    except ApiException as e:
        raise HTTPException(status_code=503, detail=f"Kubernetes API error: {e.reason}")
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Health check failed: {e}")

@app.post("/apply")
def apply_manifest(
    file: UploadFile = File(...),
    wait: bool = Query(False, description="Wait for Pods/Deployments to become Ready/Available"),
    namespace: str = Query("default", description="Namespace to check readiness in"),
    timeout: int = Query(120, ge=1, le=3600, description="Wait timeout in seconds"),
):
    """
    Apply a single YAML file (multi-doc supported) and track it in the registry.
    Returns a deployment_id for later listing/deletion.
    """
    path = None
    try:
        # Read contents once to keep in registry
        raw_bytes = file.file.read()
        yaml_text = raw_bytes.decode("utf-8", errors="replace")
        # Rewind to write into temp file too
        path = tempfile.mkstemp(prefix="k8s-", suffix=".yaml")[1]
        with open(path, "wb") as f:
            f.write(raw_bytes)

        results = utils.create_from_yaml(api_client, path, verbose=False)
        summary = _summarize(results)

        if wait:
            try:
                _wait_ready(summary, namespace=namespace, timeout=timeout)
            except TimeoutError as te:
                raise HTTPException(status_code=504, detail=str(te))

        deployment_id = str(uuid.uuid4())
        with REGISTRY_LOCK:
            REGISTRY[deployment_id] = {
                "filename": file.filename,
                "applied_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "objects": summary,
                "yaml_text": yaml_text,
            }

        return JSONResponse({
            "status": "applied" if not wait else "applied_and_ready",
            "deployment_id": deployment_id,
            "file": file.filename,
            "objects": [{"apiVersion": a, "kind": k, "name": n} for a, k, n in summary],
            "count": len(summary),
            "wait": wait,
            "namespace": namespace,
            "timeout": timeout,
        })
    except ApiException as e:
        raise HTTPException(status_code=400, detail=f"Apply failed: {e.reason}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Apply failed: {e}")
    finally:
        if path:
            try: os.remove(path)
            except Exception: pass

@app.post("/delete")
def delete_manifest(file: UploadFile = File(...)):
    """
    Delete resources described in the uploaded YAML (does NOT touch registry).
    """
    path = None
    try:
        path = _write_temp(file)
        results = utils.delete_from_yaml(api_client, path, verbose=False)
        summary = _summarize(results)
        return JSONResponse({
            "status": "deleted",
            "file": file.filename,
            "objects": [{"apiVersion": a, "kind": k, "name": n} for a, k, n in summary],
            "count": len(summary),
        })
    except ApiException as e:
        raise HTTPException(status_code=400, detail=f"Delete failed: {e.reason}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Delete failed: {e}")
    finally:
        if path:
            try: os.remove(path)
            except Exception: pass

@app.get("/deployments")
def list_deployments():
    """List all deployments applied via /apply (in-memory registry)."""
    with REGISTRY_LOCK:
        data = [
            {
                "deployment_id": dep_id,
                "file": entry["filename"],
                "applied_at": entry["applied_at"],
                "count": len(entry["objects"]),
                "objects": [
                    {"apiVersion": a, "kind": k, "name": n}
                    for (a, k, n) in entry["objects"]
                ],
            }
            for dep_id, entry in REGISTRY.items()
        ]
    return {"deployments": data, "count": len(data)}

@app.post("/deployments/delete_all")
def delete_all_deployments():
    """
    Delete ONLY the resources that were applied via /apply (based on registry),
    then clear the registry.
    """
    deleted: List[Dict[str, Any]] = []
    errors: List[str] = []

    with REGISTRY_LOCK:
        # Work on a snapshot to minimize lock time for delete calls
        snapshot = [(dep_id, entry["filename"], entry["yaml_text"]) for dep_id, entry in REGISTRY.items()]

    for dep_id, filename, yaml_text in snapshot:
        path = None
        try:
            # Write the stored YAML to a temp file and delete from it
            fd, path = tempfile.mkstemp(prefix=f"k8s-del-{dep_id}-", suffix=".yaml")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(yaml_text)
            results = utils.delete_from_yaml(api_client, path, verbose=False)
            summary = _summarize(results)
            deleted.append({
                "deployment_id": dep_id,
                "file": filename,
                "objects": [{"apiVersion": a, "kind": k, "name": n} for a, k, n in summary],
                "count": len(summary),
            })
        except ApiException as e:
            errors.append(f"{dep_id}: {e.reason}")
        except Exception as e:
            errors.append(f"{dep_id}: {e}")
        finally:
            if path:
                try: os.remove(path)
                except Exception: pass

    # If all good, clear the registry
    with REGISTRY_LOCK:
        if not errors:
            REGISTRY.clear()
        else:
            # Remove only successful ones
            for d in deleted:
                REGISTRY.pop(d["deployment_id"], None)

    status = "ok" if not errors else "partial"
    return {
        "status": status,
        "deleted": deleted,
        "deleted_count": len(deleted),
        "errors": errors,
        "remaining_in_registry": len(REGISTRY),
    }
