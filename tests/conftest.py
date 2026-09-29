import os
import sys
from pathlib import Path

# Корень проекта в sys.path, чтобы импортировать services/, plugins/ и т.д.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# config.get_config() требует ADMIN_ID — задаём заглушку, если .env отсутствует
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("BOT_TOKEN", "test")
