from flask import Flask, request, jsonify, abort, send_from_directory
import os
import subprocess

app = Flask(__name__)

# Define the directory where YAML files are stored
YAML_DIR = "./descriptors"

# Ensure the directory exists
if not os.path.exists(YAML_DIR):
    os.makedirs(YAML_DIR)

def serve_yaml_file(descriptor):
    """
    Reusable function to serve YAML files from the YAML directory.
    """
    # Ensure the file is a YAML file
    if not descriptor.endswith(('.yaml', '.yml')):
        abort(400, "Invalid file type. Only YAML files are allowed.")
    
    # Try to serve the requested file if it exists
    try:
        return send_from_directory(YAML_DIR, descriptor)
    except FileNotFoundError:
        abort(404, "File not found.")

def run_script_with_sudo(script_path, args, sudo_password):
    """
    Helper function to run a shell script with sudo and password input.
    """
    command = [
        "sudo", "-S", "bash", script_path
    ] + args
    
    try:
        result = subprocess.run(command, input=sudo_password.encode() + b'\n',
                                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result.stdout.decode(), None
    except subprocess.CalledProcessError as e:
        return None, e.stderr.decode()


@app.route("/configure_router", methods=["POST"])
def configure_router():
    """
    API to execute the vxlan_router_setup.sh script with provided parameters.
    """
    script_path = "./vxlan_router_setup.sh"
    
    if not os.path.exists(script_path):
        return jsonify({"error": "Script not found"}), 500
    
    data = request.json
    required_params = ["sudo_password", "local_ip", "remote_ip", "interface", "vni", "dst_port", "destination_network", "tunnel_ip", "gateway_ip"]
    
    for param in required_params:
        if param not in data:
            return jsonify({"error": "Missing required parameter: {}".format(param)}), 400
    
    args = [
        "-l", data["local_ip"],
        "-r", data["remote_ip"],
        "-i", data["interface"],
        "-v", str(data["vni"]),
        "-p", str(data["dst_port"]),
        "-n", data["destination_network"],
        "-a", data["tunnel_ip"],
        "-g", data["gateway_ip"]
    ]
    
    output, error = run_script_with_sudo(script_path, args, data["sudo_password"])
    if error:
        return jsonify({"error": "Script execution failed", "output": error}), 500
    return jsonify({"message": "Router configured successfully", "output": output})

@app.route("/remove_vxlan", methods=["POST"])
def remove_vxlan():
    """
    API to execute the remove_vxlan.sh script with provided parameters.
    """
    script_path = "./remove_vxlan.sh"
    
    if not os.path.exists(script_path):
        return jsonify({"error": "Script not found"}), 500
    
    data = request.json
    required_params = ["sudo_password", "vni", "destination_network"]
    
    for param in required_params:
        if param not in data:
            return jsonify({"error": "Missing required parameter: {}".format(param)}), 400
    
    args = [
        "-v", str(data["vni"]),
        "-n", data["destination_network"]
    ]
    
    output, error = run_script_with_sudo(script_path, args, data["sudo_password"])
    if error:
        return jsonify({"error": "Script execution failed", "output": error}), 500
    return jsonify({"message": "VXLAN tunnel removed successfully", "output": output})

@app.route("/test_connectivity", methods=["POST"])
def test_connectivity():
    """
    API to perform a simple 3x ping test to a given target.
    """
    data = request.json
    if "target" not in data:
        return jsonify({"error": "Missing required parameter: target"}), 400
    
    target = data["target"]
    try:
        result = subprocess.run(["ping", "-c", "3", target], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode == 0:
            return jsonify({"message": "Ping successful", "output": result.stdout.decode("utf-8")})
        else:
            return jsonify({"error": "Ping failed", "output": result.stderr.decode("utf-8")}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route("/catalog/<path:descriptor>", methods=["GET"])
def get_yaml_from_catalog(descriptor):
    return serve_yaml_file(descriptor)

@app.route("/topology/<path:descriptor>", methods=["GET"])
def get_yaml_from_topology(descriptor):
    return serve_yaml_file(descriptor)

if __name__ == "__main__":
    app.run(debug=True)
