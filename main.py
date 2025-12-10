import logging
import json
import os
import requests
import html
from typing import Optional, Tuple, List

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)


BOT_TOKEN = "8401727674:AAFGRTZ1ZxkX7ywqTVPUuSm-1z8sWuGqwJs"
RESTCOUNTRIES_BASE = "https://restcountries.com/v3.1"
USER_SETTINGS_FILE = "user_settings.json"


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def load_user_settings() -> dict:
    """
    Загружает настройки пользователей из JSON-файла.
    Возвращает словарь с настройками.
    """
    if os.path.exists(USER_SETTINGS_FILE):
        with open(USER_SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_user_settings(settings: dict):
    """
    Сохраняет настройки пользователей в JSON-файл.
    """
    with open(USER_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def get_display_name(user) -> Optional[str]:
    """
    Получает отображаемое имя пользователя Telegram.
    Использует username, если есть, иначе сочетание first_name + last_name.
    """
    if not user:
        return None
    if getattr(user, "username", None):
        return user.username
    first = getattr(user, "first_name", "") or ""
    last = getattr(user, "last_name", "") or ""
    full = (first + " " + last).strip()
    return full if full else None


def set_home_country(user_id: int, country_name: str, username: Optional[str] = None):
    """
    Сохраняет домашнюю страну пользователя с его username.
    """
    settings = load_user_settings()
    settings[str(user_id)] = {
        "country": country_name,
        "username": username
    }
    save_user_settings(settings)


def get_home_country(user_id: int) -> Optional[str]:
    """
    Получает домашнюю страну пользователя по его ID.
    """
    settings = load_user_settings()
    entry = settings.get(str(user_id))
    if entry and isinstance(entry, dict):
        return entry.get("country")
    return None


def country_search_by_name(name: str) -> List[dict]:
    """
    Ищет страну по названию через API restcountries.com.
    Возвращает список словарей с информацией о странах.
    """
    url = f"{RESTCOUNTRIES_BASE}/name/{requests.utils.quote(name)}"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()


def countries_by_region(region: str) -> List[dict]:
    """
    Возвращает список стран по указанному региону.
    """
    url = f"{RESTCOUNTRIES_BASE}/region/{requests.utils.quote(region)}"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()


def all_countries() -> List[dict]:
    """
    Возвращает список всех стран.
    """
    url = f"{RESTCOUNTRIES_BASE}/all"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json()


def format_country_brief(c: dict) -> str:
    """
    Форматирует краткую информацию о стране в виде текста с HTML-разметкой.
    """
    name = c.get("name", {}).get("common", "Unknown")
    capital = ", ".join(c.get("capital", [])) or "—"
    region = c.get("region", "—")
    subregion = c.get("subregion", "—")
    population = c.get("population", "—")
    area = c.get("area", "—")
    currencies = c.get("currencies", {})
    currencies_str = ", ".join(
        f"{currencies[k].get('name', '')}" for k in currencies) if currencies else "—"
    languages = c.get("languages", {})
    languages_str = ", ".join(languages.values()) if languages else "—"
    return (
        f"<b>{html.escape(name)}</b>\n"
        f"Столица: {html.escape(capital)}\n"
        f"Регион: {html.escape(region)} / {html.escape(subregion)}\n"
        f"Население: {population:,}\n"
        f"Площадь: {area:,} км²\n"
        f"Валюта(ы): {html.escape(currencies_str)}\n"
        f"Языки: {html.escape(languages_str)}\n"
    )


def choose_main_menu_keyboard():
    """
    Создает клавиатуру главного меню.
    """
    buttons = [
        [KeyboardButton("Инфо о стране"), KeyboardButton("Выбрать страну")],
        [KeyboardButton("Сохранить домашнюю страну"),
         KeyboardButton("Сравнить страны")],
        [KeyboardButton("Мои настройки"), KeyboardButton("Команды")],
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик команды /start.
    Отправляет приветственное сообщение и главное меню.
    """
    msg = update.effective_message
    user = update.effective_user

    text = (
        f"Привет, {user.first_name or 'пользователь'}! Я бот-справочник по странам.\n\n"
        "Что я умею:\n"
        "/info <страна> — информация о стране\n"
        "/pickcountry — выбрать страну вручную\n"
        "/sethome <страна> — сохранить домашнюю страну\n"
        "/home — показать домашнюю страну\n"
        "/compare <страна1;страна2> — сравнить две страны\n"
        "/help — список команд"
    )
    await msg.reply_text(text, reply_markup=choose_main_menu_keyboard())


async def info_command_logic(update_or_query, context: ContextTypes.DEFAULT_TYPE, country_name: str):
    """
    Основная логика получения информации о стране.
    Работает как для сообщений, так и для CallbackQuery.
    """
    try:
        results = country_search_by_name(country_name)
        if not results:
            raise ValueError("not found")
    except Exception:
        txt = "Не удалось найти страну. Проверьте название."
        if hasattr(update_or_query, 'message') and not hasattr(update_or_query, 'data'):
            await update_or_query.message.reply_text(txt, reply_markup=choose_main_menu_keyboard())
        else:
            try:
                await update_or_query.edit_message_text(txt)
            except Exception:
                await update_or_query.message.reply_text(txt, reply_markup=choose_main_menu_keyboard())
        return

    country = results[0]
    text_out = format_country_brief(country)
    flag_url = country.get("flags", {}).get("png")
    if flag_url:
        text_out += f"\nФлаг: {flag_url}"

    if hasattr(update_or_query, 'message') and not hasattr(update_or_query, 'data'):
        await update_or_query.message.reply_html(text_out, reply_markup=choose_main_menu_keyboard())
    else:
        try:
            await update_or_query.edit_message_text(text_out, parse_mode='HTML')
            await update_or_query.message.reply_text(reply_markup=choose_main_menu_keyboard())
        except Exception:
            await update_or_query.message.reply_html(text_out, reply_markup=choose_main_menu_keyboard())


async def info_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик команды /info.
    Запрашивает у пользователя название страны.
    """
    context.user_data["awaiting_info_country"] = True
    await update.effective_message.reply_text("Напиши название страны:")


async def sethome_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик команды /sethome.
    Сохраняет домашнюю страну пользователя.
    """
    args = context.args
    user_id = update.effective_user.id

    if args:
        country_name = " ".join(args).strip()
        try:
            results = country_search_by_name(country_name)
            proper_name = results[0].get(
                "name", {}).get("common", country_name)
            username = get_display_name(update.effective_user)
            set_home_country(user_id, proper_name, username)
            await update.effective_message.reply_text(
                f"Домашняя страна сохранена: {proper_name}",
                reply_markup=choose_main_menu_keyboard()
            )
        except Exception:
            await update.effective_message.reply_text(
                "Не удалось найти страну.",
                reply_markup=choose_main_menu_keyboard()
            )
        return

    context.user_data["awaiting_sethome"] = True
    await update.effective_message.reply_text("Напиши название страны:")


async def compare_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик команды /compare.
    Запрашивает у пользователя две страны для сравнения.
    """
    args = context.args
    if args:
        pair = split_two_countries(" ".join(args))
        if pair:
            await do_compare_and_send(update, pair[0], pair[1])
        else:
            await update.effective_message.reply_text(
                "Нужно два названия через ';' или ','.",
                reply_markup=choose_main_menu_keyboard()
            )
        return

    context.user_data["awaiting_compare"] = True
    await update.effective_message.reply_text(
        "Отправь два названия через ';' или ','."
    )


async def home_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик команды /home.
    Показывает домашнюю страну пользователя и её подробную информацию.
    """
    user_id = update.effective_user.id
    settings = load_user_settings().get(str(user_id))

    if not settings:
        await update.effective_message.reply_text(
            "Домашняя страна ещё не установлена.",
            reply_markup=choose_main_menu_keyboard()
        )
        return

    country = settings.get("country")
    username = settings.get("username") or get_display_name(
        update.effective_user) or "—"

    await update.effective_message.reply_text(
        f"Домашняя страна: {country}\n",
        reply_markup=choose_main_menu_keyboard()
    )

    try:
        results = country_search_by_name(country)
        detailed_text = format_country_brief(results[0])
        flag_url = results[0].get("flags", {}).get("png")
        if flag_url:
            detailed_text += f"\nФлаг: {flag_url}"

        await update.effective_message.reply_html(detailed_text)
    except Exception:
        await update.effective_message.reply_text("Не удалось загрузить данные о домашней стране.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик команды /help.
    Отправляет список доступных команд.
    """
    msg = update.effective_message
    text = (
        "Список доступных команд:\n\n"
        "/info <страна> — показать информацию о стране\n"
        "/pickcountry — выбрать страну через меню\n"
        "/sethome <страна> — сохранить домашнюю страну\n"
        "/home — показать вашу домашнюю страну\n"
        "/compare <страна1;страна2> — сравнение двух стран\n"
        "/help — подсказка по командам\n\n"
        "Также можно просто написать название страны."
    )
    await msg.reply_text(text)
    await msg.reply_text(reply_markup=choose_main_menu_keyboard())


async def pickcountry_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик команды /pickcountry.
    Позволяет выбрать страну через inline-кнопки по регионам.
    """
    regions = ["Africa", "Americas", "Asia", "Europe", "Oceania", "Polar"]
    kb = [[InlineKeyboardButton(
        r, callback_data=f"region__{r}")] for r in regions]
    await update.effective_message.reply_text("Выберите регион:", reply_markup=InlineKeyboardMarkup(kb))


def split_two_countries(text: str) -> Optional[Tuple[str, str]]:
    """
    Разделяет строку на два названия стран.
    Поддерживает разделители ';' или ','.
    """
    if ";" in text:
        parts = [p.strip() for p in text.split(";") if p.strip()]
    elif "," in text:
        parts = [p.strip() for p in text.split(",") if p.strip()]
    else:
        parts = text.split()
    if len(parts) >= 2:
        return parts[0], parts[1]
    return None


async def do_compare_and_send(update: Update, name_a: str, name_b: str):
    """
    Сравнивает две страны по населению, площади и плотности населения.
    Отправляет результат пользователю с пояснениями.
    """
    try:
        res_a = country_search_by_name(name_a)
        res_b = country_search_by_name(name_b)
    except Exception:
        await update.effective_message.reply_text(
            "Ошибка поиска. Проверьте названия или попробуйте позже.",
            reply_markup=choose_main_menu_keyboard()
        )
        return

    if not res_a or not res_b:
        await update.effective_message.reply_text(
            "Одна из стран не найдена.",
            reply_markup=choose_main_menu_keyboard()
        )
        return

    a = res_a[0]
    b = res_b[0]

    na = a.get("name", {}).get("common", name_a)
    nb = b.get("name", {}).get("common", name_b)

    pa = a.get("population") or 0
    pb = b.get("population") or 0

    aa = a.get("area") or 0
    ab = b.get("area") or 0

    den_a = (pa / aa) if aa and aa > 0 else None
    den_b = (pb / ab) if ab and ab > 0 else None

    lines = [
        f"<b>Сравнение: {html.escape(na)} vs {html.escape(nb)}</b>",
        "",
        f"Население: {pa:,} — {html.escape(na)}",
        f"Население: {pb:,} — {html.escape(nb)}",
        "",
        f"Площадь: {aa:,} км² — {html.escape(na)}",
        f"Площадь: {ab:,} км² — {html.escape(nb)}",
    ]

    if pa > pb:
        lines.append(
            f"\nПо числу жителей лидирует <b>{html.escape(na)}</b> ({pa:,} > {pb:,}).")
    elif pa < pb:
        lines.append(
            f"\nПо числу жителей лидирует <b>{html.escape(nb)}</b> ({pb:,} > {pa:,}).")
    else:
        lines.append("\nПо числу жителей страны имеют одинаковое население.")

    if aa > ab:
        lines.append(
            f"По площади больше <b>{html.escape(na)}</b> ({aa:,} > {ab:,} км²).")
    elif aa < ab:
        lines.append(
            f"По площади больше <b>{html.escape(nb)}</b> ({ab:,} > {aa:,} км²).")
    else:
        lines.append("Площади стран примерно равны.")

    if den_a is not None and den_b is not None:
        da = round(den_a, 1)
        db = round(den_b, 1)
        lines.append(
            f"Плотность населения: {da} чел./км² — {html.escape(na)}, {db} чел./км² — {html.escape(nb)}.")
        if da > db:
            lines.append(
                f"По плотности населения плотнее <b>{html.escape(na)}</b>.")
        elif da < db:
            lines.append(
                f"По плотности населения плотнее <b>{html.escape(nb)}</b>.")
        else:
            lines.append("Плотность населения примерно одинакова.")
    else:
        lines.append(
            "Недостаточно данных для расчёта плотности населения (нет информации о площади).")

    message_text = "\n".join(lines)
    await update.effective_message.reply_html(message_text, reply_markup=choose_main_menu_keyboard())


async def message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик всех текстовых сообщений.
    Определяет действия по состоянию пользователя или тексту сообщения.
    """
    text = (update.message.text or "").strip()
    user_data = context.user_data
    lower = text.lower()

    if user_data.get("awaiting_info_country"):
        user_data.pop("awaiting_info_country")
        await info_command_logic(update, context, text)
        return

    if user_data.get("awaiting_sethome"):
        user_data.pop("awaiting_sethome")
        try:
            results = country_search_by_name(text)
            proper_name = results[0].get("name", {}).get("common", text)
            username = get_display_name(update.effective_user)
            set_home_country(update.effective_user.id, proper_name, username)
            await update.effective_message.reply_text(
                f"Домашняя страна сохранена: {proper_name}",
                reply_markup=choose_main_menu_keyboard()
            )
        except Exception:
            await update.effective_message.reply_text(
                "Не удалось найти страну.",
                reply_markup=choose_main_menu_keyboard()
            )
        return

    if user_data.get("awaiting_compare"):
        user_data.pop("awaiting_compare")
        pair = split_two_countries(text)
        if pair:
            await do_compare_and_send(update, pair[0], pair[1])
        else:
            await update.effective_message.reply_text(
                "Формат: страна1; страна2",
                reply_markup=choose_main_menu_keyboard()
            )
        return

    # Обработка кнопок главного меню
    if "инфо" in lower:
        await info_request(update, context)
        return
    if "выбрать страну" in lower:
        await pickcountry_command(update, context)
        return
    if "сохранить домашнюю страну" in lower:
        await sethome_request(update, context)
        return
    if "сравнить" in lower:
        await compare_request(update, context)
        return
    if "мои настройки" in lower:
        await home_command(update, context)
        return
    if "команд" in lower or "команды" in lower or "commands" in lower:
        await help_command(update, context)
        return
    if "помощь" in lower:
        await help_command(update, context)
        return

    try:
        results = country_search_by_name(text)
        if not results:
            raise ValueError()
    except Exception:
        await update.effective_message.reply_text(
            "Не удалось найти страну.",
            reply_markup=choose_main_menu_keyboard()
        )
        return

    if len(results) > 1:
        kb = [[InlineKeyboardButton(c.get("name", {}).get("common", "Unknown"),
                                    callback_data=f"sel__{c.get('name', {}).get('common', '')}")]
              for c in results[:8]]
        await update.effective_message.reply_text(
            "Найдено несколько совпадений:",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    await info_command_logic(update, context, text)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработка нажатий на inline-кнопки.
    """
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    if data.startswith("sel__"):
        country_name = data.split("__", 1)[1]
        await info_command_logic(query, context, country_name)
        return

    if data.startswith("region__"):
        region = data.split("__", 1)[1]
        try:
            countries = countries_by_region(region)
        except Exception:
            await query.edit_message_text("Ошибка загрузки.")
            return

        kb = [[InlineKeyboardButton(c.get("name", {}).get("common", "Unknown"),
                                    callback_data=f"sel__{c.get('name', {}).get('common', '')}")]
              for c in sorted(countries, key=lambda x: x.get("name", {}).get("common", ""))[:12]]

        await query.edit_message_text(
            f"Страны в регионе {region}:",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    await query.edit_message_text("Неизвестное действие.")


def main():
    """
    Основная точка запуска бота.
    Регистрирует команды, обработчики сообщений и запускает polling.
    """
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("info", info_request))
    app.add_handler(CommandHandler("pickcountry", pickcountry_command))
    app.add_handler(CommandHandler("sethome", sethome_request))
    app.add_handler(CommandHandler("home", home_command))
    app.add_handler(CommandHandler("compare", compare_request))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, message_router))

    logger.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()