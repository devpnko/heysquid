from .channels.telegram_listener import *  # noqa: F401,F403

if __name__ == "__main__":
    import asyncio
    asyncio.run(listen_loop())
