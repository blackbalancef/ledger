# Finance Telegram Bot

Personal finance tracking bot with multi-currency support, built with aiogram 3.

## Features

- 💸 Track expenses with categories
- 💰 Track income
- 📊 Monthly reports with currency conversion
- 📜 Transaction history
- ↩️ Undo transactions
- 💱 Multi-currency support (RSD, EUR, USD, CHF, GBP)
- 🔄 Automatic currency conversion to EUR and USD

## Tech Stack

- **Python 3.12** - Programming language
- **aiogram 3** - Telegram Bot framework
- **PostgreSQL** - Database
- **SQLAlchemy 2.0** - ORM with async support
- **Alembic** - Database migrations
- **Redis** - Caching
- **Docker Compose** - Local development

## Project Structure

```
finance_tg_bot/
├── alembic/              # Database migrations
├── bot/
│   ├── handlers/         # Command and message handlers
│   ├── keyboards/        # Inline keyboards
│   ├── middlewares/      # Middlewares
│   ├── services/         # Business logic
│   └── states.py         # FSM states
├── core/
│   ├── config.py         # Settings
│   ├── db.py            # Database engine
│   └── fx_rates.py      # FX rates service
├── models/              # SQLAlchemy models
├── docker-compose.yml
├── Dockerfile
└── main.py             # Entry point
```

## Setup

### 1. Clone and install dependencies

```bash
# Install dependencies
pip install -e ".[dev]"
```

### 2. Configure environment

Copy `env.example` to `.env` and fill in the values:

```bash
cp env.example .env
```

Required variables:
- `BOT_TOKEN` - Get from [@BotFather](https://t.me/botfather)
- `FX_API_KEY` - Get from [exchangerate-api.io](https://www.exchangerate-api.com/)

### 3. Start services

Using poe:

```bash
# Start all services (PostgreSQL, Redis, Bot)
poe up

# Run migrations
poe migrate

# View logs
poe logs
```

Or manually:

```bash
docker-compose up -d
docker-compose exec bot alembic upgrade head
```

## Available Commands

Using poe the poet:

```bash
poe up          # Start all services
poe down        # Stop all services
poe restart     # Restart services
poe logs        # Show bot logs
poe migrate     # Run database migrations
poe shell       # Open PostgreSQL shell
poe test        # Run tests
poe clean       # Remove volumes and containers
poe dev         # Run bot locally with hot-reload (for development)
poe dev-debug   # Run bot locally without reload (for debugging)
poe format      # Format code with black and ruff
```

## Bot Commands

- `/start` - Start the bot and register
- `/income` - Add income (or send `+5000`)
- `/report` - Get monthly report
- `/history` - View recent transactions
- `/undo` - Reverse last transaction

### Adding Expenses

Simply send a number:
```
1200
```

The bot will ask for:
1. Currency (shows recent + default)
2. Category (Food, Transport, etc.)
3. Optional note

### Adding Income

Send with `+` prefix or use command:
```
+50000
```
or
```
/income
```

## Database Schema

### users
- User profiles with default currency

### categories
- Expense and income categories with icons

### transactions
- All transactions with original currency and EUR/USD conversions
- Stores exchange rates at transaction time

### fx_rates
- Daily exchange rates cache

## Currency Conversion

- All transactions store amounts in original currency
- Converted to EUR and USD at transaction time
- Exchange rates cached in Redis (24h) and PostgreSQL
- API: exchangerate-api.io

## Development

### Local development (without Docker)

1. Start PostgreSQL and Redis:
```bash
docker-compose up -d postgres redis
```

2. Run migrations:
```bash
alembic upgrade head
```

3. Run bot with hot-reload:
```bash
poe dev
# or directly: uv run python dev.py
```

The bot will automatically restart when you change any `.py` files in `bot/`, `core/`, or `models/` directories.

### Debugging

#### Option 1: VS Code / Cursor Debugger (Recommended)

Press `F5` and select one of the configurations:
- **Debug Bot (with hot-reload)** - Full debugging with automatic reload on code changes
- **Debug Bot (no reload)** - Clean debugging without reload (faster breakpoint hits)
- **Debug Current File** - Debug any Python file directly

Set breakpoints in your code and enjoy step-by-step debugging!

#### Option 2: Run without hot-reload

```bash
poe dev-debug
# or directly: uv run python main.py
```

Good for debugging without reload interference.

### Code formatting

```bash
poe format
```

## What's NOT in Phase 1

- Split bill functionality
- Debt tracking
- Scheduled reports (Celery)
- FastAPI health checks

These features are planned for Phase 2.

## License

MIT

