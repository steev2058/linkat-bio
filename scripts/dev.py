import asyncio
import os
import signal
import sys


async def run(cmd):
    return await asyncio.create_subprocess_exec(*cmd)


async def main():
    env = os.environ.copy()
    web = await run([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"])
    bot = await run([sys.executable, "-m", "bot.main"])

    async def shutdown():
        for p in [web, bot]:
            if p.returncode is None:
                p.send_signal(signal.SIGINT)

    try:
        await asyncio.gather(web.wait(), bot.wait())
    except KeyboardInterrupt:
        await shutdown()


if __name__ == "__main__":
    asyncio.run(main())
