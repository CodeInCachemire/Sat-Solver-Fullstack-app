from contextlib import asynccontextmanager
import logging
import os
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from backend.app.api import health, jobs, sudoku
from backend.app.sync import sync
from backend.app.db.session import init_db_pool
from backend.app.redis.redis_session import init_redis_pool


# Custom colored formatter
class ColoredFormatter(logging.Formatter):
    """Custom formatter with colored output."""
    
    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
    }
    RESET = '\033[0m'
    
    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{log_color}{record.levelname}{self.RESET}"
        return super().format(record)


# Configure logging
def setup_logging():
    """Configure logging with colored output."""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Remove existing handlers
    logger.handlers.clear()
    
    # Console handler with colored formatter
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    
    formatter = ColoredFormatter(
        fmt='%(levelname)s: - %(message)s - %(asctime)s - %(name)s ',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)


# Initialize logging
setup_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger = logging.getLogger(__name__)
    logger.info("Starting application...")
    init_db_pool()
    init_redis_pool()
    logger.info("Connection pools initialized")
    
    yield
    
    # Shutdown
    logger.info("Shutting down application...")
    from backend.app.db.session import close_pool
    from backend.app.redis.redis_session import close_redis_pool
    close_pool()
    close_redis_pool()
    logger.info("Connection pools closed")

app = FastAPI(lifespan=lifespan)

ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost,http://127.0.0.1"
).split(",")
# Configure CORS to allow frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.health_router)
app.include_router(sync.sync_router)
app.include_router(jobs.jobs_router)  # Async job submission endpoints
app.include_router(sudoku.sudoku_router)




