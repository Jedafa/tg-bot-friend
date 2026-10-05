"""Курсы Bitcoin, Litecoin и USDT (TRC-20) через публичный API CoinGecko."""
import aiohttp

import config

coin_titles = {
    "bitcoin": "Bitcoin (BTC)",
    "litecoin": "Litecoin (LTC)",
    "tether": "USDT (TRC-20)",
}


async def fetch_prices() -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(
            config.prices_url,
            headers={"User-Agent": "tg-bot-friend"},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as response:
            response.raise_for_status()
            data = await response.json()
    return {coin_titles[name]: float(values["usd"]) for name, values in data.items() if name in coin_titles}


def format_prices(prices: dict) -> str:
    lines = ["💱 Текущие курсы", ""]
    for title in coin_titles.values():
        if title in prices:
            lines.append(f"{title} — {prices[title]:,.2f} $".replace(",", " "))
    return "\n".join(lines)
