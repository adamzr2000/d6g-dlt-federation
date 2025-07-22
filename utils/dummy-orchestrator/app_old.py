from flask import Flask, request, jsonify, abort
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

@app.route("/configure_router", methods=["POST"])
def configure_router():
    """
    API to execute the vxlan_router_setup.sh script with provided parameters.
    """
    script_path = "./vxlan_router_setup.sh"

    # Ensure script exists
    if not os.path.exists(script_path):
        return jsonify({"error": "Script not found"}), 500

    # Get JSON payload
    data = request.json

    required_params = ["local_ip", "remote_ip", "interface", "vni", "dst_port", "destination_network", "tunnel_ip", "gateway_ip"]
    
    # Validate parameters
    for param in required_params:
        if param not in data:
            return jsonify({"error": "Missing required parameter: {}".format(param)}), 400

    # Build the command
    cmd = [
        "sudo", script_path,
        "-l", data["local_ip"],
        "-r", data["remote_ip"],
        "-i", data["interface"],
        "-v", str(data["vni"]),
        "-p", str(data["dst_port"]),
        "-n", data["destination_network"],
        "-a", data["tunnel_ip"],
        "-g", data["gateway_ip"]
    ]

    try:
        # Execute script
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        # Return success or failure response
        if result.returncode == 0:
            return jsonify({"message": "Router configured successfully", "output": result.stdout})
        else:
            return jsonify({"error": "Script execution failed", "output": result.stderr}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/remove_vxlan", methods=["POST"])
def remove_vxlan():
    """
    API to execute the remove_vxlan.sh script with provided parameters.
    """
    script_path = "./remove_vxlan.sh"
    
    if not os.path.exists(script_path):
        return jsonify({"error": "Script not found"}), 500
    
    data = request.json
    required_params = ["vni", "destination_network"]
    
    for param in required_params:
        if param not in data:
            return jsonify({"error": "Missing required parameter: {}".format(param)}), 400
    
    cmd = [
        "sudo", script_path,
        "-v", str(data["vni"]),
        "-n", data["destination_network"]
    ]
    
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            return jsonify({"message": "VXLAN tunnel removed successfully", "output": result.stdout})
        else:
            return jsonify({"error": "Script execution failed", "output": result.stderr}), 500
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
