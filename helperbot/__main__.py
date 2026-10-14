"""Explicit CLI; --check never logs in or reads credentials."""
import argparse
import asyncio
import os
from .core import Store
from .discord_app import create_client


def main():
    parser = argparse.ArgumentParser(description="Opt-in Discord helper; Codex generation disabled")
    parser.add_argument('--database', default='.runtime/state.db')
    parser.add_argument('--provider', choices=['disabled-codex'], default='disabled-codex')
    parser.add_argument('--check', action='store_true', help='Offline schema and command smoke check, no credentials')
    parser.add_argument('--sync-guild', type=int, help='Restrict command registration to one test guild')
    args = parser.parse_args()
    token = None if args.check else os.environ.get('DISCORD_BOT_TOKEN')
    if not args.check and not token:
        parser.error('DISCORD_BOT_TOKEN is required for Discord login; no personal auth is read')
    os.umask(0o077)
    store = Store(args.database)
    client = create_client(store, sync_guild=args.sync_guild)
    try:
        if args.check:
            print(f'Offline check OK: {len(client.tree.get_commands())} commands; provider=disabled-codex; no network/login')
            asyncio.run(client.close())
        else:
            client.run(token, log_handler=None)
    finally:
        store.close()


if __name__ == '__main__':
    main()
