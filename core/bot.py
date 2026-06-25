import logging
import random
import time
from threading import Thread

import requests
import telebot
import telebot.apihelper as apihelper

from core.plugin_manager import PluginManager
from core.scheduler import TaskScheduler

logger = logging.getLogger(__name__)

# Параметры переподключения к Telegram API при сетевых сбоях
_TELEGRAM_POLL_TIMEOUT = 30  # timeout для каждого getUpdates
_TELEGRAM_LONG_POLLING_TIMEOUT = 120  # long_polling_timeout
_TELEGRAM_RECONNECT_DELAY_BASE = 5  # базовая задержка перед переподключением
_TELEGRAM_RECONNECT_DELAY_MAX = 60  # максимальная задержка перед переподключением


class SEMDBotCore:
    def __init__(self, config):
        self.config = config
        self._apply_telegram_api_settings(config)
        self.bot = telebot.TeleBot(config.app.bot_token)
        self.plugin_manager = PluginManager(self.bot, config)
        self.scheduler = TaskScheduler(config)
        self._running = True

    @staticmethod
    def _apply_telegram_api_settings(config):
        """Настраивает TeleBot на работу через reverse-proxy или классический прокси."""
        proxy_cfg = config.proxy
        base_url = config.app.telegram_api_base_url

        if base_url:
            base = base_url.rstrip("/")
            apihelper.API_URL = f"{base}/bot{{0}}/{{1}}"
            apihelper.FILE_URL = f"{base}/file/bot{{0}}/{{1}}"
            logger.info(f"Telegram API настроен через reverse-proxy: {base}")
            return

        if proxy_cfg.enabled and proxy_cfg.host and proxy_cfg.port:
            proxy_auth = ""
            if proxy_cfg.user and proxy_cfg.password:
                proxy_auth = f"{proxy_cfg.user}:{proxy_cfg.password}@"
            proxy_url = f"{proxy_cfg.proxy_type}://{proxy_auth}{proxy_cfg.host}:{proxy_cfg.port}"
            apihelper.proxy = {"http": proxy_url, "https": proxy_url}
            logger.info(f"Telegram API настроен через прокси: {proxy_url}")

    def load_plugin(self, plugin_path: str) -> bool:
        result = self.plugin_manager.load_plugin(plugin_path)

        # Special handling for plugins that need plugin_manager reference
        if result:
            if "root_menu" in plugin_path:
                root_menu_plugin = self.plugin_manager.plugins.get("RootMenu")
                if root_menu_plugin:
                    root_menu_plugin.set_plugin_manager(self.plugin_manager)
                    # Re-register handlers after plugin_manager is set
                    self.plugin_manager._register_handlers(root_menu_plugin)
            elif "plugin_manager" in plugin_path:
                plugin_mgr_plugin = self.plugin_manager.plugins.get("PluginManager")
                if plugin_mgr_plugin:
                    plugin_mgr_plugin.set_plugin_manager(self.plugin_manager)
                    # Re-register handlers after plugin_manager is set
                    self.plugin_manager._register_handlers(plugin_mgr_plugin)

        return result

    def start(self):
        # Запускаем планировщик в отдельном потоке
        tasks = self.plugin_manager.get_scheduled_tasks()
        for task in tasks:
            self.scheduler.add_task(**task)

        Thread(target=self.scheduler.start, daemon=True).start()

        # Запускаем бота с защитой от сетевых сбоев.
        # infinity_polling прерывается при необрабатываемых исключениях связи,
        # поэтому перезапускаем его в цикле с нарастающей задержкой.
        reconnect_attempt = 0
        while self._running:
            try:
                logger.info(
                    "Запуск Telegram polling "
                    f"(poll_timeout={_TELEGRAM_POLL_TIMEOUT}s, "
                    f"long_polling_timeout={_TELEGRAM_LONG_POLLING_TIMEOUT}s)"
                )
                self.bot.infinity_polling(
                    timeout=_TELEGRAM_POLL_TIMEOUT,
                    long_polling_timeout=_TELEGRAM_LONG_POLLING_TIMEOUT,
                    non_stop=True,
                )
                reconnect_attempt = 0
            except (requests.exceptions.RequestException, telebot.apihelper.ApiException) as e:
                reconnect_attempt += 1
                delay = min(
                    _TELEGRAM_RECONNECT_DELAY_BASE * (2 ** (reconnect_attempt - 1)),
                    _TELEGRAM_RECONNECT_DELAY_MAX,
                ) + random.uniform(0, 2)
                logger.warning(
                    f"Сбой связи с Telegram API (попытка {reconnect_attempt}): {e}. "
                    f"Переподключение через {delay:.1f} сек..."
                )
                time.sleep(delay)
            except Exception as e:
                logger.error(f"Неожиданная ошибка в polling: {e}", exc_info=True)
                reconnect_attempt += 1
                delay = min(
                    _TELEGRAM_RECONNECT_DELAY_BASE * (2 ** (reconnect_attempt - 1)),
                    _TELEGRAM_RECONNECT_DELAY_MAX,
                ) + random.uniform(0, 2)
                logger.warning(f"Перезапуск polling через {delay:.1f} сек...")
                time.sleep(delay)

    def shutdown(self):
        self._running = False
        self.plugin_manager.shutdown_all()
        self.scheduler.stop()
