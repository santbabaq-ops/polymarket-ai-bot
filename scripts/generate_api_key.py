#!/usr/bin/env python3
"""
Generate Polymarket CLOB API Key

This script creates an API key for Polymarket CLOB trading.
The API key is derived from your wallet's cryptographic signature.
"""

import os
import sys
import argparse


def generate_api_key(private_key: str) -> str:
    """
    Generate Polymarket CLOB API key from private key.

    The API key is created by signing a message with your wallet.
    This proves ownership of the address without revealing the private key.
    """
    try:
        from py_clob_client.client import ClobClient
        from web3 import Web3

        # Clean up private key
        if private_key.startswith("0x"):
            private_key = private_key[2:]

        # Validate key
        if len(private_key) != 64:
            raise ValueError("Private key must be 64 hex characters (32 bytes)")

        # Create client
        client = ClobClient(
            host="https://clob.polymarket.com",
            key=private_key,
            chain_id=137,  # Polygon mainnet
        )

        # Get wallet address
        w3 = Web3()
        account = w3.eth.account.from_key("0x" + private_key)
        address = account.address

        print(f"\nWallet Address: {address}")
        print("\nGenerating API key...")

        try:
            # Try to get existing API key
            api_key = client.get_api_key()
            print(f"\n✓ Existing API key found!")
            return api_key
        except Exception:
            # Create new API key
            api_key = client.create_api_key()
            print(f"\n✓ New API key created!")
            return api_key

    except ImportError as e:
        print(f"\n✗ Missing dependency: {e}")
        print("\nInstall required packages:")
        print("  pip install py-clob-client web3")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Generate Polymarket CLOB API Key",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Using environment variable
  export POLYGON_WALLET_PRIVATE_KEY=0x...
  python scripts/generate_api_key.py

  # Using command line argument (less secure)
  python scripts/generate_api_key.py --key 0x...

  # Save to .env file
  python scripts/generate_api_key.py --save

Security Notes:
  - Never share your private key
  - Never commit private keys to Git
  - Use .env file and add it to .gitignore
        """
    )

    parser.add_argument(
        "--key",
        help="Private key (64 hex characters). If not provided, uses POLYGON_WALLET_PRIVATE_KEY env var"
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save API key to .env file"
    )
    parser.add_argument(
        "--show-private-key",
        action="store_true",
        help="Show private key warning and confirmation"
    )

    args = parser.parse_args()

    # Security warning
    print("=" * 60)
    print("  Polymarket API Key Generator")
    print("=" * 60)
    print("\n⚠️  SECURITY WARNING:")
    print("   - Your private key grants full access to your wallet")
    print("   - Never share it with anyone")
    print("   - Never commit it to version control")
    print("   - Use .env files for local development")
    print()

    if not args.show_private_key:
        print("To proceed, run with --show-private-key flag")
        print()
        sys.exit(0)

    # Get private key
    if args.key:
        private_key = args.key
        print("⚠️  Using private key from command line (not recommended)")
    else:
        private_key = os.environ.get("POLYGON_WALLET_PRIVATE_KEY", "")
        if not private_key:
            print("✗ Error: Private key not provided")
            print()
            print("Set it via environment variable:")
            print("  export POLYGON_WALLET_PRIVATE_KEY=0x...")
            print()
            print("Or use --key flag (less secure):")
            print("  python scripts/generate_api_key.py --key 0x... --show-private-key")
            sys.exit(1)
        print("✓ Using private key from environment variable")

    print()

    # Generate API key
    api_key = generate_api_key(private_key)

    # Display results
    print("\n" + "=" * 60)
    print("  API Key Generated Successfully")
    print("=" * 60)
    print(f"\nAPI Key: {api_key}")
    print()

    # Save to .env if requested
    if args.save:
        env_path = ".env"

        # Read existing .env
        existing_vars = {}
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and "=" in line and not line.startswith("#"):
                        key, value = line.split("=", 1)
                        existing_vars[key] = value

        # Update with new values
        existing_vars["POLYGON_WALLET_PRIVATE_KEY"] = private_key if not private_key.startswith("0x") else private_key[2:]
        existing_vars["POLYMARKET_API_KEY"] = api_key

        # Write back
        with open(env_path, "w") as f:
            f.write("# Polymarket AI Bot Configuration\n")
            f.write("# Generated automatically - DO NOT COMMIT\n\n")
            f.write("# Wallet (required)\n")
            f.write(f"POLYGON_WALLET_PRIVATE_KEY={existing_vars.get('POLYGON_WALLET_PRIVATE_KEY', '')}\n\n")
            f.write("# Polymarket API (auto-generated)\n")
            f.write(f"POLYMARKET_API_KEY={api_key}\n\n")
            f.write("# Anthropic API (required for AI strategy)\n")
            f.write(f"ANTHROPIC_API_KEY={existing_vars.get('ANTHROPIC_API_KEY', '')}\n\n")
            f.write("# Optional settings\n")
            f.write(f"POLYGON_RPC_URL={existing_vars.get('POLYGON_RPC_URL', 'https://polygon-rpc.com')}\n")

        print(f"✓ Configuration saved to {env_path}")
        print()
        print("Next steps:")
        print("  1. Add ANTHROPIC_API_KEY to .env file")
        print("  2. Run: polybot markets")
        print()
    else:
        print("To save this configuration:")
        print(f"  python scripts/generate_api_key.py --save --show-private-key")
        print()

    print("=" * 60)


if __name__ == "__main__":
    main()
