import logging
import asyncio
import json
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import BufferedInputFile, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from rembg import remove
from io import BytesIO
from PIL import Image

TOKEN = "Ваш токен " 
ADMIN_ID = 12345678 

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ХРАНИЛИЩА
USER_DATA_FILE = "user_data.json"
user_sessions = {}

def load_user_data():
    if os.path.exists(USER_DATA_FILE):
        with open(USER_DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_user_data(data):
    with open(USER_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def update_user_stats(user_id):
    user_data = load_user_data()
    user_id_str = str(user_id)
    
    if user_id_str not in user_data:
        user_data[user_id_str] = {
            "total_processed": 0,
            "first_use": datetime.now().isoformat(),
            "history": []
        }
    
    user_data[user_id_str]["total_processed"] += 1
    user_data[user_id_str]["history"].append({
        "date": datetime.now().isoformat(),
        "type": "photo_processed"
    })
    
    if len(user_data[user_id_str]["history"]) > 10:
        user_data[user_id_str]["history"] = user_data[user_id_str]["history"][-10:]
    
    save_user_data(user_data)

# КЛАВИАТУРЫ
def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎯 Удалить фон"), KeyboardButton(text="🎨 Изменить фон")],
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="🆘 Помощь")]
        ],
        resize_keyboard=True
    )

def get_bg_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⚪ Белый фон"), KeyboardButton(text="⚫ Черный фон")],
            [KeyboardButton(text="📸 Свое фото"), KeyboardButton(text="🔙 Отмена")]
        ],
        resize_keyboard=True
    )

def get_admin_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👥 Все пользователи"), KeyboardButton(text="📈 Статистика")],
            [KeyboardButton(text="🎯 Топ клиентов"), KeyboardButton(text="🔙 В главное меню")]
        ],
        resize_keyboard=True
    )

# ФУНКЦИИ ДЛЯ СМЕНЫ ФОНА
def create_color_bg(width, height, color_name):
    colors = {
        "white": (255, 255, 255),
        "black": (0, 0, 0),
        "blue": (0, 0, 255),
        "green": (0, 255, 0),
        "red": (255, 0, 0),
    }
    bg = Image.new('RGB', (width, height), colors[color_name])
    bg_bytes = BytesIO()
    bg.save(bg_bytes, format='PNG')
    return bg_bytes.getvalue()

def apply_background(no_bg_bytes, bg_bytes, mask):
    foreground = Image.open(BytesIO(no_bg_bytes))
    background = Image.open(BytesIO(bg_bytes)).resize(foreground.size)
    
    result = background.copy()
    result.paste(foreground, (0, 0), mask)
    
    output_buffer = BytesIO()
    result.save(output_buffer, format='PNG')
    return output_buffer.getvalue()

# ПРОГРЕСС-БАР
def get_progress_bar(percentage, length=10):
    filled = int(length * percentage / 100)
    empty = length - filled
    return f"[{'█' * filled}{'░' * empty}] {percentage}%"

async def show_processing_progress(message, steps):
    """Показывает прогресс обработки"""
    progress_msg = await message.answer("🔄 Подготовка к обработке...")
    
    for step_name, progress in steps:
        await progress_msg.edit_text(f"🔄 {step_name} {get_progress_bar(progress)}")
        await asyncio.sleep(0.8)  # Имитация процесса
    
    await progress_msg.delete()
    return True

# КОМАНДА START
@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = str(message.from_user.id)
    user_data = load_user_data()
    
    if user_id not in user_data:
        welcome_text = (
            "✨ <b>Добро пожаловать в AI Фоторедактор!</b>\n\n"
            "🎯 <b>Что умеет бот:</b>\n"
            "• Мгновенно удалять фон с любых фото\n"
            "• Заменять фон на любой цвет или изображение\n"
            "• Сохранять в HD качестве\n\n"
            "🚀 <b>Как начать:</b> Просто нажмите кнопку ниже!"
        )
    else:
        welcome_text = (
            "✨ <b>С возвращением в AI Фоторедактор!</b>\n\n"
            "🎯 Готовы творить магию с вашими фото?"
        )
    
    await message.answer(welcome_text, parse_mode='HTML', reply_markup=get_main_keyboard())

# УДАЛЕНИЕ ФОНА
@dp.message(F.text == "🎯 Удалить фон")
async def remove_bg_start(message: types.Message):
    await message.answer(
        "📸 <b>Отправьте фото для обработки</b>\n\n"
        "<i>Рекомендуем:</i>\n"
        "• Четкие фото с контрастным фоном\n"
        "• Хорошее освещение\n" 
        "• PNG/JPEG формат",
        parse_mode='HTML',
        reply_markup=types.ReplyKeyboardRemove()
    )

# ИЗМЕНЕНИЕ ФОНА
@dp.message(F.text == "🎨 Изменить фон")
async def change_bg_start(message: types.Message):
    user_id = message.from_user.id
    
    if user_id not in user_sessions:
        await message.answer(
            "❌ <b>Сначала удалите фон с фото!</b>\n\n"
            "📸 Используйте кнопку «🎯 Удалить фон» чтобы подготовить фото",
            parse_mode='HTML'
        )
        return
    
    await message.answer(
        "🎨 <b>Выберите новый фон для вашего фото</b>\n\n"
        "⚪ <b>Белый фон</b> - для соцсетей\n"
        "⚫ <b>Черный фон</b> - стильный контраст\n"
        "📸 <b>Свое фото</b> - любой фон на ваш вкус",
        parse_mode='HTML',
        reply_markup=get_bg_keyboard()
    )

@dp.message(F.text == "⚪ Белый фон")
async def white_bg(message: types.Message):
    await apply_color_bg(message, "white")

@dp.message(F.text == "⚫ Черный фон")
async def black_bg(message: types.Message):
    await apply_color_bg(message, "black")

async def apply_color_bg(message, color):
    user_id = message.from_user.id
    
    if user_id not in user_sessions:
        await message.answer("❌ <b>Сессия устарела</b>\nНачните заново с удаления фона", parse_mode='HTML', reply_markup=get_main_keyboard())
        return
    
    # Показываем прогресс
    steps = [
        ("Создаю фон...", 25),
        ("Накладываю изображение...", 50),
        ("Оптимизирую результат...", 75),
        ("Завершаю обработку...", 100)
    ]
    await show_processing_progress(message, steps)
    
    session = user_sessions[user_id]
    
    # Создаем цветной фон
    bg_bytes = create_color_bg(session["image_size"][0], session["image_size"][1], color)
    
    # Накладываем фон
    result_bytes = apply_background(session["no_bg_bytes"], bg_bytes, session["mask"])
    
    # Отправляем результат
    output_file = BufferedInputFile(result_bytes, filename=f"{color}_bg.png")
    
    color_names = {
        "white": "белый",
        "black": "черный", 
        "blue": "синий",
        "green": "зеленый",
        "red": "красный"
    }
    
    await message.reply_document(
        output_file, 
        caption=f"🎨 <b>{color_names[color].title()} фон успешно применен!</b>\n\n"
               "💎 Хотите еще фото? Используйте кнопки ниже 👇",
        parse_mode='HTML',
        reply_markup=get_main_keyboard()
    )

@dp.message(F.text == "📸 Свое фото")
async def custom_bg(message: types.Message):
    user_id = message.from_user.id
    
    if user_id not in user_sessions:
        await message.answer("❌ <b>Сессия устарела</b>", parse_mode='HTML', reply_markup=get_main_keyboard())
        return
    
    # Переводим в режим ожидания фонового фото
    user_sessions[user_id]["step"] = "waiting_bg_photo"
    
    await message.answer(
        "📸 <b>Отправьте фото которое будет новым фоном</b>\n\n"
        "<i>Рекомендации:</i>\n"
        "• Пейзажи работают лучше всего\n"
        "• Избегайте фото с людьми\n"
        "• Яркие цвета = лучший результат",
        parse_mode='HTML',
        reply_markup=types.ReplyKeyboardRemove()
    )

@dp.message(F.text == "🔙 Отмена")
async def cancel_bg(message: types.Message):
    user_id = message.from_user.id
    if user_id in user_sessions:
        user_sessions[user_id]["step"] = "has_no_bg"
    
    await message.answer("❌ <b>Операция отменена</b>", parse_mode='HTML', reply_markup=get_main_keyboard())

# ОБРАБОТКА ФОТО
@dp.message(F.photo | F.document)
async def handle_photo(message: types.Message):
    user_id = message.from_user.id
    
    # Режим смены фона (свое фото как фон)
    if user_id in user_sessions and user_sessions[user_id]["step"] == "waiting_bg_photo":
        # Показываем прогресс
        steps = [
            ("Анализирую фон...", 20),
            ("Подготавливаю изображение...", 40),
            ("Накладываю композицию...", 60),
            ("Оптимизирую результат...", 80),
            ("Завершаю обработку...", 100)
        ]
        await show_processing_progress(message, steps)
        
        session = user_sessions[user_id]
        
        try:
            # Скачиваем фоновое фото
            if message.photo:
                file_id = message.photo[-1].file_id
            else:
                file_id = message.document.file_id

            file = await bot.get_file(file_id)
            file_bytes = await bot.download_file(file.file_path)
            
            # Накладываем фон
            result_bytes = apply_background(
                session["no_bg_bytes"], 
                file_bytes.getvalue(), 
                session["mask"]
            )
            
            output_file = BufferedInputFile(result_bytes, filename="custom_bg_photo.png")
            await message.reply_document(
                output_file, 
                caption=(
                    "🎨 <b>Фон успешно заменен!</b>\n\n"
                    "✨ Нравится результат? Попробуйте другие варианты!"
                ),
                parse_mode='HTML',
                reply_markup=get_main_keyboard()
            )
            
            update_user_stats(user_id)
            del user_sessions[user_id]
            
        except Exception as e:
            logger.error(f"Ошибка смены фона: {e}")
            await message.reply(
                "❌ <b>Ошибка при смене фона</b>\n\n"
                "Попробуйте другое фоновое фото",
                parse_mode='HTML',
                reply_markup=get_main_keyboard()
            )
        return
    
    # ОБЫЧНОЕ УДАЛЕНИЕ ФОНА
    try:
        # Скачиваем фото
        if message.photo:
            file_id = message.photo[-1].file_id
        else:
            file_id = message.document.file_id

        file = await bot.get_file(file_id)
        file_bytes = await bot.download_file(file.file_path)
        
        # Показываем прогресс удаления фона
        steps = [
            ("Загружаю фото...", 10),
            ("Анализирую изображение...", 30),
            ("Определяю объекты...", 50),
            ("Удаляю фон...", 70),
            ("Оптимизирую результат...", 90),
            ("Завершаю обработку...", 100)
        ]
        await show_processing_progress(message, steps)
        
        no_bg_bytes = remove(file_bytes.getvalue())
        image = Image.open(BytesIO(no_bg_bytes))
        mask = image.getchannel('A')
        
        user_sessions[user_id] = {
            "step": "has_no_bg",
            "no_bg_bytes": no_bg_bytes,
            "mask": mask,
            "image_size": image.size
        }
        
        output_file = BufferedInputFile(no_bg_bytes, filename="no_bg_photo.png")
        await message.reply_document(
            output_file, 
            caption=(
                "✅ <b>Фон успешно удален!</b>\n\n"
                "🎨 <b>Теперь вы можете:</b>\n"
                "• Изменить фон на любой цвет\n"
                "• Использовать свое фото как фон\n"
                "• Скачать результат\n\n"
                "Выберите действие ниже 👇"
            ),
            parse_mode='HTML',
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="🎨 Изменить фон")],
                    [KeyboardButton(text="🎯 Новое фото"), KeyboardButton(text="🔙 Главное меню")]
                ],
                resize_keyboard=True
            )
        )
        
        update_user_stats(user_id)
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await message.reply(
            "❌ <b>Произошла ошибка при обработке</b>\n\n"
            "Попробуйте другое фото или обратитесь в поддержку",
            parse_mode='HTML',
            reply_markup=get_main_keyboard()
        )

# СТАТИСТИКА
@dp.message(F.text == "📊 Статистика")
async def show_stats(message: types.Message):
    user_data = load_user_data()
    user_id = str(message.from_user.id)
    
    if user_id in user_data:
        stats = user_data[user_id]
        first_use = datetime.fromisoformat(stats["first_use"])
        days_used = (datetime.now() - first_use).days
        
        text = (
            "📊 <b>Ваша статистика</b>\n\n"
            f"🎯 <b>Всего обработок:</b> {stats['total_processed']}\n"
            f"📅 <b>Используете:</b> {max(days_used, 1)} дней\n"
            f"📝 <b>Активность:</b> {len(stats['history'])} записей"
        )
    else:
        text = "📊 <b>Статистики пока нет</b>\n\nСделайте первую обработку!"
    
    await message.answer(text, parse_mode='HTML')

@dp.message(F.text == "🎯 Новое фото")
async def new_photo(message: types.Message):
    await remove_bg_start(message)

# ПОМОЩЬ
@dp.message(F.text == "🆘 Помощь")
async def help_command(message: types.Message):
    text = (
        "🆘 <b>Помощь и поддержка</b>\n\n"
        "🎯 <b>Как работает бот:</b>\n"
        "1. Нажмите «Удалить фон»\n"
        "2. Отправьте фото\n"
        "3. Получите результат за 5-10 сек\n\n"
        "🎨 <b>Смена фона:</b>\n"
        "• Сначала удалите фон\n"
        "• Затем выберите «Изменить фон»\n"
        "• Можно выбрать цвет или свое фото\n\n"
        "📸 <b>Рекомендации:</b>\n"
        "• Используйте четкие фото\n"
        "• Контрастный фон = лучший результат\n"
        "• PNG формат для прозрачности"
    )
    await message.answer(text, parse_mode='HTML')

# АДМИН ПАНЕЛЬ
@dp.message(Command("admin"))
async def admin_command(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ <b>Доступ запрещен</b>", parse_mode='HTML')
        return
    
    user_data = load_user_data()
    total_users = len(user_data)
    total_processed = sum(user['total_processed'] for user in user_data.values())
    
    text = (
        "👑 <b>Панель администратора</b>\n\n"
        f"👥 <b>Всего пользователей:</b> {total_users}\n"
        f"📊 <b>Всего обработок:</b> {total_processed}\n\n"
        "Выберите действие:"
    )
    
    await message.answer(text, parse_mode='HTML', reply_markup=get_admin_keyboard())

@dp.message(F.text == "👥 Все пользователи")
async def show_all_users(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    user_data = load_user_data()
    if not user_data:
        await message.answer("📭 <b>Пользователей пока нет</b>", parse_mode='HTML')
        return
    
    text = "👥 <b>Все пользователи:</b>\n\n"
    for i, (user_id, data) in enumerate(list(user_data.items())[:50], 1):
        text += f"{i}. ID: {user_id}\n"
        text += f"   📊 Обработок: {data['total_processed']}\n"
        text += f"   📅 Регистрация: {data.get('first_use', 'N/A')[:10]}\n\n"
    
    await message.answer(text, parse_mode='HTML')

@dp.message(F.text == "📈 Статистика")
async def admin_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    user_data = load_user_data()
    total_users = len(user_data)
    total_processed = sum(user['total_processed'] for user in user_data.values())
    
    # Статистика по активности
    today = datetime.now().date()
    weekly_processed = 0
    active_today = 0
    
    for user_id, data in user_data.items():
        # Активность за сегодня
        if 'history' in data and data['history']:
            last_activity = datetime.fromisoformat(data['history'][-1]['date']).date()
            if last_activity == today:
                active_today += 1
        
        # Обработки за неделю
        first_use = datetime.fromisoformat(data.get('first_use', datetime.now().isoformat())).date()
        days_used = (today - first_use).days
        if days_used <= 7:
            weekly_processed += data['total_processed']
    
    text = (
        "📈 <b>Статистика бота</b>\n\n"
        f"👥 <b>Всего пользователей:</b> {total_users}\n"
        f"📊 <b>Всего обработок:</b> {total_processed}\n"
        f"🔥 <b>Активных сегодня:</b> {active_today}\n"
        f"📅 <b>Обработок за неделю:</b> {weekly_processed}\n"
    )
    
    await message.answer(text, parse_mode='HTML')

@dp.message(F.text == "🎯 Топ клиентов")
async def top_clients(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    user_data = load_user_data()
    if not user_data:
        await message.answer("📭 <b>Пользователей пока нет</b>", parse_mode='HTML')
        return
    
    # Сортируем по количеству обработок
    sorted_users = sorted(user_data.items(), key=lambda x: x[1]['total_processed'], reverse=True)
    
    text = "🏆 <b>Топ клиентов по активности:</b>\n\n"
    for i, (user_id, data) in enumerate(sorted_users[:10], 1):
        text += f"{i}. ID: {user_id}\n"
        text += f"   🎯 Обработок: {data['total_processed']}\n"
        text += f"   📅 С: {data.get('first_use', 'N/A')[:10]}\n\n"
    
    await message.answer(text, parse_mode='HTML')

# ВОЗВРАТ В ГЛАВНОЕ МЕНЮ
@dp.message(F.text == "🔙 Главное меню")
async def back_to_main(message: types.Message):
    await message.answer("🔙 <b>Главное меню</b>", parse_mode='HTML', reply_markup=get_main_keyboard())

@dp.message(F.text == "🔙 В главное меню")
async def admin_back_to_main(message: types.Message):
    await message.answer("🔙 <b>Главное меню</b>", parse_mode='HTML', reply_markup=get_main_keyboard())

# ЗАПУСК
async def main():
    logger.info("Запускаем бота...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
