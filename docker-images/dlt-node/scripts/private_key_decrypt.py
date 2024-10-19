from web3.auto import w3
import os

# Define the base directory path
base_dir = "./"  # Change this to your base directory

# Function to read the password from a password file
def read_password(password_file_path):
    with open(password_file_path, "r") as file:
        return file.read().strip()

# Path to the password file
password_file = os.path.join("./scripts", "password.txt")

# Read the password from the password file
password = read_password(password_file)

# Function to decrypt and return private keys from a keystore file
def decrypt_and_get_private_key(keyfile_path):
    with open(keyfile_path) as keyfile:
        encrypted_key = keyfile.read()
        private_key = w3.eth.account.decrypt(encrypted_key, password)

    import binascii
    return binascii.b2a_hex(private_key).decode('utf-8')

# Find and decrypt private keys in all keystore directories and write to env files
for root, dirs, files in os.walk(base_dir):
    for dir in dirs:
        if dir.startswith("node") and os.path.exists(os.path.join(root, dir, "keystore")):
            node_number = dir.replace("node", "")
            keystore_dir = os.path.join(root, dir, "keystore")
            env_file_path = os.path.join(base_dir, f"node{node_number}.env")
            for filename in os.listdir(keystore_dir):
                if filename.startswith("UTC--"):
                    keyfile_path = os.path.join(keystore_dir, filename)
                    private_key_hex = decrypt_and_get_private_key(keyfile_path)
                    with open(env_file_path, "a") as env_file:
                        env_file.write(f"PRIVATE_KEY={private_key_hex}\n")
                    print(f"Private key for {dir} written to {env_file_path}")

print("Private keys have been written to the respective node environment files.")
