# Development Guide

Quick guide for local development with hot-reload and debugging.

## 🚀 Quick Start

### 1. Start Database Services

```bash
docker-compose up -d postgres redis
```

### 2. Run Migrations

```bash
alembic upgrade head
```

### 3. Start Development Server

```bash
uv run python dev.py
# or: poe dev
```

The bot will automatically restart when you save changes to Python files! 🔄

## 🐛 Debugging

### Method 1: VS Code / Cursor (Recommended)

1. Press `F5` (or click Run → Start Debugging)
2. Select configuration:
   - **Debug Bot (with hot-reload)** - Debug + auto-reload ⚡
   - **Debug Bot (no reload)** - Clean debugging without reload 🎯

3. Set breakpoints in your code
4. Edit code and save - debugger will reconnect automatically!

### Method 2: Without Debugger

Run directly without hot-reload:
```bash
uv run python main.py
# or: poe dev-debug
```

## 📁 Watched Directories

Hot-reload monitors these directories for changes:
- `bot/` - Handlers, keyboards, services
- `core/` - Configuration, database, FX rates
- `models/` - SQLAlchemy models
- `main.py`, `config.py` - Entry points and config

Only `.py` files are watched (ignoring `__pycache__`).

## 🎯 Development Workflow

### Normal Development
```bash
# Start services
docker-compose up -d postgres redis

# Run with hot-reload
uv run python dev.py
# or: poe dev

# Edit files, save - bot restarts automatically ✨
```

### Debugging with Breakpoints
```bash
# Option A: Use debugger (F5) - with or without reload
# Option B: Run without reload
uv run python main.py
# or: poe dev-debug
```

### Run Tests
```bash
docker-compose up -d
poe test
```

### Format Code
```bash
poe format
```

## ⚙️ How It Works

`dev.py` uses `watchfiles` to monitor file changes:
1. Starts `main.py` as subprocess
2. Watches for `.py` file changes
3. On change detected:
   - Gracefully stops bot (SIGTERM)
   - Waits up to 5 seconds
   - Restarts bot automatically
4. Forwards all output (stdout/stderr)

## 🛑 Stopping

Press `Ctrl+C` - the bot will shut down gracefully.

## 💡 Tips

- **Fast reload**: Only Python files trigger restart
- **Debug mode**: Use "Debug Bot (no reload)" for cleaner debugging
- **Multiple changes**: Wait for restart to complete before making more changes
- **Database changes**: Run migrations manually: `alembic upgrade head`
- **Redis flush**: `docker-compose exec redis redis-cli FLUSHALL`

## 📝 Available Commands

```bash
# Development
poe dev         # Run with hot-reload
poe dev-debug   # Run without reload

# Docker services
poe up          # Start all services
poe down        # Stop all services
poe logs        # Show bot logs

# Database
poe migrate     # Run migrations
poe shell       # PostgreSQL shell

# Code quality
poe format      # Format code
poe test        # Run tests
```

## 🔥 Common Issues

### Bot doesn't restart after changes
- Check if file is in watched directories
- Ensure file is saved (not just edited)
- Check terminal for error messages

### Debugger not working
- Make sure `debugpy` is installed (comes with VS Code Python extension)
- Try "Debug Bot (no reload)" configuration
- Check `.vscode/launch.json` exists

### Database connection error
- Ensure PostgreSQL is running: `docker-compose ps`
- Check `.env` file has correct DATABASE_URL
- Run migrations: `alembic upgrade head`

---

Happy coding! 🎉

