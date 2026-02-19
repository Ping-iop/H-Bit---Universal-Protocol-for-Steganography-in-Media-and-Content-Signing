import time
import os
from web3 import Web3
from eth_tester import EthereumTester, PyEVMBackend
import solcx

# Contract source path
CONTRACT_PATH = os.path.join(os.path.dirname(__file__), "..", "contracts", "HBitRegistry.sol")

def compile_contract(solc_version="0.8.20"):
    """Compiles the Solidity smart contract using py-solc-x."""
    print(f"Installing solc {solc_version} (if not already installed)...")
    solcx.install_solc(solc_version)
    solcx.set_solc_version(solc_version)
    
    print(f"Compiling {CONTRACT_PATH}...")
    with open(CONTRACT_PATH, "r") as f:
        source = f.read()

    compiled_sol = solcx.compile_source(
        source,
        output_values=["abi", "bin"]
    )
    
    contract_id, contract_interface = compiled_sol.popitem()
    return contract_interface['abi'], contract_interface['bin']


def main():
    # 1. Compile the contract
    try:
        abi, bytecode = compile_contract()
        print("Contract compiled successfully!")
    except Exception as e:
        print(f"Compilation error: {e}")
        return

    # 2. Setup local Eth-Tester node (in-memory)
    print("Initializing local Ethereum test node...")
    tester = EthereumTester(backend=PyEVMBackend())
    w3 = Web3(Web3.EthereumTesterProvider(tester))

    # Get a funded test account
    test_account = w3.eth.accounts[0]
    print(f"Deploying with account: {test_account}")

    # 3. Deploy the contract
    HBitRegistry = w3.eth.contract(abi=abi, bytecode=bytecode)
    tx_hash = HBitRegistry.constructor().transact({'from': test_account})
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    contract_address = tx_receipt.contractAddress
    
    print(f"Contract deployed to: {contract_address}")
    
    # 4. Interact with the contract
    contract = w3.eth.contract(address=contract_address, abi=abi)

    # Mock Data (SHA-256 hashes are 32 bytes)
    image_hash = Web3.keccak(text="clean_image_content")
    author_hash = Web3.keccak(text="author_identity_pubkey")
    payload_hash = Web3.keccak(text="full_hbit_payload")
    timestamp = int(time.time())

    print("\n--- Testing Registration ---")
    print(f"Registering Image Hash: {image_hash.hex()}...")
    
    tx_hash = contract.functions.register(
        image_hash, 
        author_hash, 
        payload_hash, 
        timestamp
    ).transact({'from': test_account})
    
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    print(f"Registration successful in block {receipt.blockNumber}! Gas used: {receipt.gasUsed}")

    print("\n--- Testing Verification ---")
    print("Calling getRecord()...")
    record = contract.functions.getRecord(image_hash).call()
    
    print(f"Found Record!")
    print(f"  Author Hash:  0x{record[0].hex()}")
    print(f"  Payload Hash: 0x{record[1].hex()}")
    print(f"  Timestamp:    {record[2]}")
    print(f"  Block Number: {record[3]}")
    print(f"  Exists?:      {record[4]}")

    print("\nCalling verify()...")
    is_valid = contract.functions.verify(image_hash, payload_hash).call()
    print(f"Verify matches expected payload check: {is_valid}")
    
    is_invalid = contract.functions.verify(image_hash, Web3.keccak(text="wrong_payload")).call()
    print(f"Verify catches wrong payload check:    {not is_invalid}")
    
    print("\n[SUCCESS] Local Blockchain Simulation Complete.")

if __name__ == "__main__":
    main()
