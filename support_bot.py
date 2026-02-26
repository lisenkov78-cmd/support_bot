from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from telegram import Update, Message, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# ---------------- НАСТРОЙКИ ----------------
# Вставьте токен или оставьте и задайте переменную окружения BOT_TOKEN
TOKEN = TOKEN = "8294512646:AAEvEWKxe_JerQ_CXFT9-FG7StxD8XbU9eQ"
# ID админ-группы (вида -100...)
ADMIN_GROUP_ID = -1003783796432

# Кто считается админом (их user_id)
ADMIN_IDS = {8514858133, 668474047}
# ------------------------------------------

DATA_FILE = Path("support_map.json")  # файл для сохранения связок "сообщение в админ-группе -> клиент"
MAX_MAP_SIZE = 5000  # чтобы файл не разрастался бесконечно

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
log = logging.getLogger("support_bot")


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def load_map() -> Dict[str, int]:
    if DATA_FILE.exists():
        try:
            data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                # ожидаем {"<admin_message_id>": <client_id>, ...}
                return {str(k): int(v) for k, v in data.items()}
        except Exception:
            log.exception("Не смог прочитать %s", DATA_FILE)
    return {}


def save_map(mapping: Dict[str, int]) -> None:
    # ограничим размер
    if len(mapping) > MAX_MAP_SIZE:
        # оставим только последние ключи
        keys = list(mapping.keys())[-MAX_MAP_SIZE:]
        mapping = {k: mapping[k] for k in keys}
    try:
        DATA_FILE.write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")
    except Exception:
        log.exception("Не смог сохранить %s", DATA_FILE)


def header_for_user(user) -> str:
    return (
        "📩 Сообщение от клиента\n"
        f"👤 {user.first_name} {user.last_name or ''}\n"
        f"🔹 username: @{user.username or 'нет'}\n"
        f"🆔 user_id: {user.id}\n"
        "— — —\n"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Убираем кастомную клавиатуру (кнопки снизу) и оставляем обычный ввод текста
    await update.message.reply_text(
        "Здравствуйте! Напишите ваш вопрос — мы ответим вам здесь ✅",
        reply_markup=ReplyKeyboardRemove(),
    )


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Ваш user_id: {update.effective_user.id}")


async def id_here(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"chat_id: {update.effective_chat.id}")


async def help_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text(
        "Админ-подсказка:\n"
        "• В админ-группе отвечайте РЕПЛАЕМ на сообщение клиента — ответ уйдёт клиенту.\n"
        "• Можно отвечать текстом, фото, видео, документом, голосовым.\n"
        "• /reply <user_id> <текст> — ответить вручную.\n"
        "• /id_here — покажет chat_id группы.\n"
        "• /myid — покажет ваш user_id.\n\n"
        "ВАЖНО: клиент должен хотя бы один раз нажать Start у бота, иначе бот не сможет ему написать."
    )


async def reply_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    if len(context.args) < 2:
        await update.message.reply_text("Формат: /reply <user_id> <текст>")
        return

    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("user_id должен быть числом.")
        return

    text = " ".join(context.args[1:])
    try:
        await context.bot.send_message(chat_id=user_id, text=f"💬 Ответ: {text}")
        await update.message.reply_text("✅ Отправлено клиенту.")
    except Exception as e:
        await update.message.reply_text(f"❗ Не смог отправить клиенту: {e}")


async def send_client_copy_of_message(context: ContextTypes.DEFAULT_TYPE, client_id: int, admin_msg: Message) -> None:
    """Отправляет клиенту копию того, что админ написал в группе (текст/медиа)."""
    caption = admin_msg.caption or ""
    text = admin_msg.text or ""

    # Текст
    if text:
        await context.bot.send_message(chat_id=client_id, text=f"💬 Ответ: {text}")
        return

    # Фото
    if admin_msg.photo:
        file_id = admin_msg.photo[-1].file_id
        cap = f"💬 Ответ: {caption}" if caption else "💬 Ответ"
        await context.bot.send_photo(chat_id=client_id, photo=file_id, caption=cap)
        return

    # Видео
    if admin_msg.video:
        cap = f"💬 Ответ: {caption}" if caption else "💬 Ответ"
        await context.bot.send_video(chat_id=client_id, video=admin_msg.video.file_id, caption=cap)
        return

    # Документ
    if admin_msg.document:
        cap = f"💬 Ответ: {caption}" if caption else "💬 Ответ"
        await context.bot.send_document(chat_id=client_id, document=admin_msg.document.file_id, caption=cap)
        return

    # Голосовое
    if admin_msg.voice:
        cap = f"💬 Ответ: {caption}" if caption else None
        await context.bot.send_voice(chat_id=client_id, voice=admin_msg.voice.file_id, caption=cap)
        return

    # Аудио
    if admin_msg.audio:
        cap = f"💬 Ответ: {caption}" if caption else None
        await context.bot.send_audio(chat_id=client_id, audio=admin_msg.audio.file_id, caption=cap)
        return

    # Стикер (если вдруг)
    if admin_msg.sticker:
        await context.bot.send_sticker(chat_id=client_id, sticker=admin_msg.sticker.file_id)
        return

    # Иначе ничего
    await context.bot.send_message(chat_id=client_id, text="💬 Ответ (неподдерживаемый тип сообщения).")


async def from_client_any(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Клиент пишет в личку -> всё уходит в админ-группу. Поддерживает текст и медиа."""
    user = update.effective_user
    msg = update.message
    mapping = context.application.bot_data.setdefault("map", load_map())

    head = header_for_user(user)

    try:
        # Текст
        if msg.text:
            sent = await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=head + msg.text)
            mapping[str(sent.message_id)] = user.id
            save_map(mapping)
            await msg.reply_text("✅ Принято! Мы ответим вам здесь.", reply_markup=ReplyKeyboardRemove())
            return

        # Фото
        if msg.photo:
            file_id = msg.photo[-1].file_id
            cap = head + (msg.caption or "")
            sent = await context.bot.send_photo(chat_id=ADMIN_GROUP_ID, photo=file_id, caption=cap)
            mapping[str(sent.message_id)] = user.id
            save_map(mapping)
            await msg.reply_text("✅ Принято! Мы ответим вам здесь.", reply_markup=ReplyKeyboardRemove())
            return

        # Видео
        if msg.video:
            cap = head + (msg.caption or "")
            sent = await context.bot.send_video(chat_id=ADMIN_GROUP_ID, video=msg.video.file_id, caption=cap)
            mapping[str(sent.message_id)] = user.id
            save_map(mapping)
            await msg.reply_text("✅ Принято! Мы ответим вам здесь.", reply_markup=ReplyKeyboardRemove())
            return

        # Документ
        if msg.document:
            cap = head + (msg.caption or "")
            sent = await context.bot.send_document(chat_id=ADMIN_GROUP_ID, document=msg.document.file_id, caption=cap)
            mapping[str(sent.message_id)] = user.id
            save_map(mapping)
            await msg.reply_text("✅ Принято! Мы ответим вам здесь.", reply_markup=ReplyKeyboardRemove())
            return

        # Голосовое
        if msg.voice:
            cap = head + (msg.caption or "")
            sent = await context.bot.send_voice(chat_id=ADMIN_GROUP_ID, voice=msg.voice.file_id, caption=cap or None)
            mapping[str(sent.message_id)] = user.id
            save_map(mapping)
            await msg.reply_text("✅ Принято! Мы ответим вам здесь.", reply_markup=ReplyKeyboardRemove())
            return

        # Аудио
        if msg.audio:
            cap = head + (msg.caption or "")
            sent = await context.bot.send_audio(chat_id=ADMIN_GROUP_ID, audio=msg.audio.file_id, caption=cap or None)
            mapping[str(sent.message_id)] = user.id
            save_map(mapping)
            await msg.reply_text("✅ Принято! Мы ответим вам здесь.", reply_markup=ReplyKeyboardRemove())
            return

        # Стикер
        if msg.sticker:
            sent = await context.bot.send_sticker(chat_id=ADMIN_GROUP_ID, sticker=msg.sticker.file_id)
            # отдельно отправим заголовок текстом, чтобы было понятно кто это
            sent2 = await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=head + "(стикер)")
            mapping[str(sent.message_id)] = user.id
            mapping[str(sent2.message_id)] = user.id
            save_map(mapping)
            await msg.reply_text("✅ Принято! Мы ответим вам здесь.", reply_markup=ReplyKeyboardRemove())
            return

        await msg.reply_text("❗ Этот тип сообщения пока не поддерживается. Напишите текстом или отправьте фото/видео/документ/голосовое.")
    except Exception:
        log.exception("Не смог отправить в админ-группу")
        await msg.reply_text(
            "❗ Не получилось отправить сообщение менеджеру.\n"
            "Проверьте: бот добавлен в админ-группу и правильно указан ADMIN_GROUP_ID."
        )


async def admin_reply_in_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админ отвечает в группе реплаем -> бот отправляет клиенту. Поддерживает текст и медиа."""
    user = update.effective_user
    msg = update.message

    if not is_admin(user.id):
        return
    if update.effective_chat.id != ADMIN_GROUP_ID:
        return
    if not msg.reply_to_message:
        return

    mapping = context.application.bot_data.setdefault("map", load_map())
    replied_id = str(msg.reply_to_message.message_id)
    client_id = mapping.get(replied_id)

    if not client_id:
        await msg.reply_text("❗ Не понял, кому отвечать. Ответьте реплаем на сообщение бота с клиентом.")
        return

    try:
        await send_client_copy_of_message(context, client_id, msg)
        await msg.reply_text("✅ Отправлено клиенту.")
    except Exception as e:
        await msg.reply_text(
            "❗ Не смог отправить клиенту.\n"
            "Частая причина: клиент ещё не нажал Start у бота.\n"
            f"Ошибка: {e}"
        )


def main():
    if not TOKEN or TOKEN == "PASTE_YOUR_BOT_TOKEN_HERE":
        print("❗ Вставьте TOKEN в файл или задайте переменную окружения BOT_TOKEN.")
        return

    app = Application.builder().token(TOKEN).build()

    # команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("id_here", id_here))
    app.add_handler(CommandHandler("helpadmin", help_admin))
    app.add_handler(CommandHandler("reply", reply_cmd))

    # Клиенты: любые сообщения (текст + медиа)
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, from_client_any))

    # Админы: ответы реплаем в группе (текст + медиа)
    app.add_handler(MessageHandler(filters.Chat(chat_id=ADMIN_GROUP_ID) & ~filters.COMMAND, admin_reply_in_group))

    print("Support bot v3 запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
