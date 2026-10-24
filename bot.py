"""
Антикоррупционный квест-бот «Зачёт любой ценой?» / «Зачет һәр бәягәме?»
Конкурс «Казань против коррупции! — Казан коррупциягә каршы!»

Режимы запуска:
  • На Render (есть RENDER_EXTERNAL_URL) — webhook + веб-сервер с /health.
  • Локально (нет внешнего URL)          — long polling.

Переменные окружения:
  BOT_TOKEN        токен от @BotFather (обязательно)
  WEBHOOK_SECRET   секрет вебхука (необязательно; по умолчанию выводится из токена)
  WEBHOOK_BASE_URL внешний адрес сервиса (необязательно; Render задаёт RENDER_EXTERNAL_URL сам)
"""

import asyncio
import hashlib
import html
import logging
import os
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    BufferedInputFile,
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

import game
from certificate import make_certificate
from content import UI

TOKEN = os.getenv("BOT_TOKEN", "")
BASE_URL = (os.getenv("WEBHOOK_BASE_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").rstrip("/")
PORT = int(os.getenv("PORT", "10000"))
SECRET = os.getenv("WEBHOOK_SECRET") or hashlib.sha256(TOKEN.encode()).hexdigest()[:40]
WEBHOOK_PATH = "/webhook"

log = logging.getLogger("antikor-bot")
dp = Dispatcher()

# Имена для сертификата, заданные командой /name (хранятся в памяти; если сервис
# перезапустится, возьмётся имя из профиля Telegram).
custom_names: dict[int, str] = {}


# ----------------------------------------------------------------------------
# Помощники
# ----------------------------------------------------------------------------
def to_markup(screen: game.Screen) -> InlineKeyboardMarkup:
    rows = []
    for row in screen.rows:
        rows.append([
            InlineKeyboardButton(text=b.label, url=b.url) if b.url
            else InlineKeyboardButton(text=b.label, callback_data=b.data)
            for b in row
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def guess_lang(message: Message) -> str:
    code = (message.from_user.language_code or "") if message.from_user else ""
    return "tt" if code.lower().startswith("tt") else "ru"


async def bot_link(bot: Bot) -> str:
    me = await bot.me()
    return f"https://t.me/{me.username}"


# ----------------------------------------------------------------------------
# Команды
# ----------------------------------------------------------------------------
@dp.message(CommandStart())
@dp.message(Command("menu"))
async def cmd_start(message: Message) -> None:
    screen = game.menu_screen(guess_lang(message))
    await message.answer(screen.text, reply_markup=to_markup(screen))


@dp.message(Command("name"))
async def cmd_name(message: Message, command: CommandObject) -> None:
    lang = guess_lang(message)
    name = (command.args or "").strip()[:60]
    if not name:
        await message.answer(UI[lang]["name_usage"])
        return
    custom_names[message.from_user.id] = name
    await message.answer(UI[lang]["name_saved"].format(name=html.escape(name)))


# ----------------------------------------------------------------------------
# Кнопки
# ----------------------------------------------------------------------------
@dp.callback_query(F.data.startswith("c:"))
async def on_certificate(cb: CallbackQuery) -> None:
    """Сертификат отправляется отдельным сообщением-фото."""
    try:
        _, lang, hist = cb.data.split(":")
        lang = game.norm_lang(lang)
        if not game.valid_hist(hist, game.N, "012"):
            raise ValueError
    except ValueError:
        await cb.answer()
        return

    await cb.answer("🎓")
    score = game.quest_score(hist)
    title, _ = game.tier_for(lang, score)
    name = custom_names.get(cb.from_user.id) or cb.from_user.full_name
    date_str = (datetime.now(timezone.utc) + timedelta(hours=3)).strftime("%d.%m.%Y")  # время МСК

    png = await asyncio.to_thread(
        make_certificate, name, score, game.MAX_SCORE, title, UI[lang], date_str
    )
    link = await bot_link(cb.bot)
    share = game.result_screen(lang, hist, link).rows[1]  # кнопка «Поделиться»
    menu_btn = [game.Btn(UI[lang]["btn_menu"], f"m:{lang}")]
    markup = to_markup(game.Screen("", [share, menu_btn]))
    await cb.bot.send_photo(
        cb.from_user.id,
        BufferedInputFile(png, filename="certificate.png"),
        caption=UI[lang]["cert_caption"],
        reply_markup=markup,
    )


@dp.callback_query()
async def on_callback(cb: CallbackQuery) -> None:
    screen = game.route(cb.data or "", await bot_link(cb.bot))
    markup = to_markup(screen)
    try:
        await cb.message.edit_text(screen.text, reply_markup=markup)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            # сообщение нельзя отредактировать (например, это фото) — отправим новое
            await cb.bot.send_message(cb.from_user.id, screen.text, reply_markup=markup)
    except AttributeError:
        # слишком старое сообщение, Telegram не отдаёт его для редактирования
        await cb.bot.send_message(cb.from_user.id, screen.text, reply_markup=markup)
    await cb.answer()


@dp.message()
async def fallback(message: Message) -> None:
    """На любой другой текст показываем меню."""
    screen = game.menu_screen(guess_lang(message))
    await message.answer(screen.text, reply_markup=to_markup(screen))


# ----------------------------------------------------------------------------
# Запуск
# ----------------------------------------------------------------------------
async def set_commands(bot: Bot) -> None:
    await bot.set_my_commands([
        BotCommand(command="start", description="Главное меню / Төп меню"),
        BotCommand(command="name", description="Имя для сертификата / Сертификат өчен исем"),
    ])


async def on_startup(bot: Bot) -> None:
    await set_commands(bot)
    await bot.set_webhook(
        f"{BASE_URL}{WEBHOOK_PATH}",
        secret_token=SECRET,
        allowed_updates=dp.resolve_used_update_types(),
    )
    log.info("Webhook установлен: %s%s", BASE_URL, WEBHOOK_PATH)


async def health(_: web.Request) -> web.Response:
    return web.Response(text="ok")


def run_webhook(bot: Bot) -> None:
    dp.startup.register(on_startup)
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=SECRET).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=PORT)


async def run_polling(bot: Bot) -> None:
    await set_commands(bot)
    await bot.delete_webhook()
    await dp.start_polling(bot)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    if not TOKEN:
        raise SystemExit("Не задана переменная окружения BOT_TOKEN")
    bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    if BASE_URL:
        run_webhook(bot)
    else:
        asyncio.run(run_polling(bot))


if __name__ == "__main__":
    main()
