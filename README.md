# Bitnxs Bot

Grok Bot template for Bitnxs, an onchain perpetuals protocol. It sends market briefs and alerts from public Bitnxs data, and can trade on the user's own account through their API key. Every order, cancel, leverage change, and TP/SL waits for the user's explicit confirmation.

## Skills

| Skill | What it does |
| --- | --- |
| `bitnxs-getting-started` | First conversation: choose coins, a brief schedule, alert thresholds, and whether to trade. |
| `bitnxs-market-brief` | Read-only market briefs and alerts from public data (price, funding, open interest, book, candles, trades). No API key. |
| `bitnxs-trading` | Place, modify, or cancel orders, change leverage, and set TP/SL on the user's account. Each action waits for an explicit yes. |

## Start

1. Open the Bitnxs trading page, connect a wallet, and deposit.
2. Optionally create an API key under More > API Keys.
3. Import this Grok Bot template and follow the getting-started conversation. The API key is collected through a masked secret field, never in chat.

[![Bitnxs Trade](https://img.shields.io/badge/Bitnxs-Trade-000000?style=for-the-badge)](https://www.bitnxs.com/trade) [![Import Bitnxs Bot on Grok Bot](https://img.shields.io/badge/Grok%20Bot-Import%20Bitnxs%20Bot-000000?style=for-the-badge)](https://x.ai/bot/HAGDFCFxPlzKEzw1XTyQH) [![Bitnxs API Docs](https://img.shields.io/badge/Bitnxs-API%20Docs-000000?style=for-the-badge)](https://www.bitnxs.com/#/docs)

## Scripts

`scripts/snapshot.py` is a read-only market snapshot and uses only the Python standard library.

`scripts/trade_min.py` needs `pip install "eth-account>=0.13"`. Set `BITNXS_API_KEY` and `BITNXS_USER`. Use `--dry-run` to preview a request and `--yes` to send it. `selftest` runs offline and does not use the network.

## Risk notice

Perpetual futures with leverage carry a high risk of loss, including total loss of margin. Nothing here is investment advice. The service is not available to residents of restricted regions including the United States, Canada, the United Kingdom and mainland China.

## License

[![License: MIT](https://img.shields.io/badge/License-MIT-000000?style=for-the-badge)](LICENSE)
