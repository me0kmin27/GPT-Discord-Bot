"""Explicit CLI; --check never logs in or reads credentials."""
import argparse
import asyncio
import os
from pathlib import Path
from .core import Store
from .discord_app import create_client
from .provider import build_provider


def main():
    parser = argparse.ArgumentParser(description="Opt-in Discord helper; local Codex OAuth selectable")
    parser.add_argument('--database', default='.runtime/state.db')
    parser.add_argument('--provider', choices=['disabled-codex', 'codex-oauth'], default='disabled-codex')
    parser.add_argument('--data-dir', type=Path, help='Application data directory used by codex-login')
    parser.add_argument('--codex-executable', type=Path, help='Absolute pinned official native executable')
    parser.add_argument('--check', action='store_true', help='Offline schema and command smoke check, no credentials')
    parser.add_argument('--sync-guild', type=int, help='Restrict command registration to one test guild')
    args = parser.parse_args()
    try:
        provider = build_provider(args.provider, data=args.data_dir, executable=args.codex_executable)
    except ValueError as exc:
        parser.error(str(exc))
    token = None if args.check else os.environ.get('DISCORD_BOT_TOKEN')
    if not args.check and not token:
        parser.error('DISCORD_BOT_TOKEN is required for Discord login; no personal auth is read')
    os.umask(0o077)
    store = Store(args.database)
    client = create_client(store, sync_guild=args.sync_guild, provider=provider)
    try:
        if args.check:
            print(f'Offline check OK: {len(client.tree.get_commands())} commands; provider={args.provider}; no network/login')
            asyncio.run(client.close())
        else:
            client.run(token, log_handler=None)
    finally:
        store.close()


if __name__ == '__main__':
    main()
