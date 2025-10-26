"""Development server with hot-reload capability."""

import asyncio
import signal
import sys
from pathlib import Path
from typing import Optional

from watchfiles import awatch
from loguru import logger


class BotRunner:
    """Manages bot process with hot-reload capability."""

    def __init__(self):
        self.process: Optional[asyncio.subprocess.Process] = None
        self.should_exit = False

    async def start_bot(self) -> asyncio.subprocess.Process:
        """Start the bot process."""
        logger.info("🚀 Starting bot...")
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "main.py",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        # Create tasks to forward output
        asyncio.create_task(self._forward_output(process.stdout, sys.stdout))
        asyncio.create_task(self._forward_output(process.stderr, sys.stderr))
        
        return process

    async def _forward_output(self, stream, target):
        """Forward subprocess output to target stream."""
        if stream is None:
            return
        try:
            async for line in stream:
                target.buffer.write(line)
                target.buffer.flush()
        except asyncio.CancelledError:
            pass

    async def stop_bot(self):
        """Stop the bot process gracefully."""
        if self.process and self.process.returncode is None:
            logger.info("⏹️  Stopping bot...")
            try:
                self.process.send_signal(signal.SIGTERM)
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
                logger.info("✅ Bot stopped gracefully")
            except asyncio.TimeoutError:
                logger.warning("⚠️  Bot didn't stop gracefully, forcing...")
                self.process.kill()
                await self.process.wait()
                logger.info("✅ Bot killed")
            except ProcessLookupError:
                logger.info("✅ Bot already stopped")

    async def restart_bot(self):
        """Restart the bot process."""
        await self.stop_bot()
        if not self.should_exit:
            self.process = await self.start_bot()

    async def run_with_reload(self):
        """Run bot with file watching and auto-reload."""
        # Start the bot initially
        self.process = await self.start_bot()

        # Watch for file changes
        watch_paths = [
            Path("bot"),
            Path("core"),
            Path("models"),
            Path("main.py"),
            Path("config.py"),
        ]

        # Filter to only existing paths
        watch_paths = [p for p in watch_paths if p.exists()]

        logger.info(f"👀 Watching for changes in: {', '.join(str(p) for p in watch_paths)}")
        logger.info("📝 Press Ctrl+C to stop")

        try:
            async for changes in awatch(*watch_paths):
                if self.should_exit:
                    break

                # Filter out non-Python files and __pycache__
                relevant_changes = [
                    (change_type, path)
                    for change_type, path in changes
                    if path.endswith(".py") and "__pycache__" not in path
                ]

                if relevant_changes:
                    logger.info(f"🔄 Detected changes in {len(relevant_changes)} file(s)")
                    for change_type, path in relevant_changes:
                        logger.info(f"   {change_type}: {path}")
                    
                    await self.restart_bot()

        except asyncio.CancelledError:
            logger.info("🛑 Received shutdown signal")
        finally:
            await self.stop_bot()


async def main():
    """Main entry point for development server."""
    runner = BotRunner()

    def signal_handler():
        logger.info("\n🛑 Shutting down...")
        runner.should_exit = True

    # Setup signal handlers
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    try:
        await runner.run_with_reload()
    except KeyboardInterrupt:
        logger.info("🛑 Interrupted by user")
    finally:
        logger.info("👋 Development server stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

