# -*- coding: utf-8 -*-
"""
Полностью рабочий тренер-бот (aiogram 2.25.1).
Функции:
- /start — главное меню.
- "Тренировки" → выбор тренировки (№1/№2) → список упражнений (только названия).
- Выбор упражнения → показ прошлых весов → ввод новых (5 подходов: "60x8 / 62.5x8 / ...").
- /progress — последние записи.
- "◀️ Назад" и "❌ Отмена" (/cancel) — корректно выходят/возвращают меню (из любого состояния).
Хранение — workouts.json рядом с файлом.
"""

import os
import json
from datetime import datetime
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ======= НАСТРОЙКИ =======
API_TOKEN = "7376516944:AAHzTEhTfMAmxT5u6dxwsnSK1Kn5zojNauI"  # <— ВСТАВЬТЕ ТОКЕН @BotFather
DATA_FILE = "workouts.json"
PROGRAM = "Full Body"
SETS_PER_EXERCISE = 5  # строго 5 подходов как вы просили

# ======= ДАННЫЕ ТРЕНИРОВОК =======
WORKOUTS = [
    {   # index 0 → Тренировка №1
        "name": "Тренировка №1",
        "exercises": [
            "Ноги — Приседания",
            "Спина — Тяга штанги в наклоне обратным хватом",
            "Грудные — Жим штанги лёжа",
            "Ноги — Жим платформы ногами",
            "Спина — Подтягивания / Тяга блока",
            "Плечи — Жим гантелей стоя",
            "Трицепсы — Жим узким хватом",
            "Пресс — Скручивания",
        ]
    },
    {   # index 1 → Тренировка №2
        "name": "Тренировка №2",
        "exercises": [
            "Ноги — Выпады",
            "Спина — Тяга горизонтального блока к поясу",
            "Грудные — Жим гантелей под углом 30°",
            "Ноги — Разгибание ног / Мёртвая тяга",
            "Спина — Тяга вертикального блока узкой рукояткой",
            "Плечи — Разведение через стороны",
            "Трицепсы — Отжимания на брусьях / от скамьи",
            "Бицепс — Подъём штанги стоя",
        ]
    }
]

# ======= FSM =======
class InputState(StatesGroup):
    waiting_for_sets = State()  # ждём строку "весxповторы / ... (5 раз)"

# ======= ХРАНИЛКА =======
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def ensure_structure():
    data = load_data()
    if PROGRAM not in data:
        data[PROGRAM] = {}
    # Инициализируем структуру: PROGRAM → Тренировка → Упражнение → []
    for w in WORKOUTS:
        wname = w["name"]
        if wname not in data[PROGRAM]:
            data[PROGRAM][wname] = {}
        for ex in w["exercises"]:
            data[PROGRAM][wname].setdefault(ex, [])
    save_data(data)

# ======= ПАРСИНГ =======
def parse_sets_line(text):
    """
    Ожидаем 5 подходов в виде: "60x8 / 62.5x8 / 65x6 / 65x6 / 67.5x5"
    Разделитель между подходами — '/', ';' тоже допустимы (преобразуем).
    Дробные веса допускают запятую — превращаем в точку.
    Возврат: список словарей [{"w": float, "r": int}, ...] ровно из 5 элементов.
    """
    work = text.strip().replace(";", "/").replace(",", ".")
    parts = [p.strip() for p in work.split("/") if p.strip()]
    if len(parts) != SETS_PER_EXERCISE:
        raise ValueError(f"Ожидалось {SETS_PER_EXERCISE} подходов, получено {len(parts)}.")
    sets = []
    for p in parts:
        p = p.lower().replace("×", "x")
        if "x" not in p:
            raise ValueError(f"Нет 'x' в '{p}'. Пример: 62.5x8")
        w_str, r_str = p.split("x", 1)
        w = float(w_str)
        r = int(r_str)
        sets.append({"w": w, "r": r})
    return sets

def avg_weight(sets):
    return round(sum(s["w"] for s in sets) / len(sets), 2) if sets else 0.0

def sets_to_text(sets):
    return " / ".join(f"{s['w']}x{s['r']}" for s in sets)

# ======= БОТ =======
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

# ======= КЛАВИАТУРЫ =======
def kb_main():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🏋️ Тренировки", callback_data="menu_workouts"),
        InlineKeyboardButton("📊 Прогресс", callback_data="menu_progress"),
    )
    kb.add(InlineKeyboardButton("❌ Отмена", callback_data="menu_cancel"))
    return kb

def kb_workouts():
    kb = InlineKeyboardMarkup(row_width=1)
    for i, w in enumerate(WORKOUTS):
        kb.add(InlineKeyboardButton(f"💪 {w['name']}", callback_data=f"open::{i}"))  # короткая data
    kb.add(InlineKeyboardButton("◀️ Назад", callback_data="back_main"))
    return kb

def kb_exercises(workout_idx: int):
    kb = InlineKeyboardMarkup(row_width=1)
    for j, ex in enumerate(WORKOUTS[workout_idx]["exercises"]):
        kb.add(InlineKeyboardButton(f"🟡 {ex}", callback_data=f"ex::{workout_idx}::{j}"))  # короткая data
    kb.add(InlineKeyboardButton("◀️ Назад", callback_data="menu_workouts"))
    return kb

# ======= ХЕНДЛЕРЫ =======
@dp.message_handler(commands=["start"])
async def cmd_start(m: types.Message):
    ensure_structure()
    await m.answer("⬛️🟡 <b>FULL BODY</b>\nВыбери действие 👇", parse_mode="HTML", reply_markup=kb_main())

# /cancel — из любого состояния
@dp.message_handler(commands=["cancel"], state="*")
async def cmd_cancel(m: types.Message, state: FSMContext):
    if await state.get_state() is not None:
        await state.finish()
    await m.answer("❌ Отменено. Возврат в меню.", reply_markup=kb_main())

# Кнопка "❌ Отмена" — из любого состояния
@dp.callback_query_handler(lambda c: c.data == "menu_cancel", state="*")
async def cb_cancel(cq: types.CallbackQuery, state: FSMContext):
    if await state.get_state() is not None:
        await state.finish()
    # пробуем редактировать; если нельзя — отправим новое
    try:
        await cq.message.edit_text("❌ Отменено.", reply_markup=kb_main())
    except Exception:
        await cq.message.answer("❌ Отменено.", reply_markup=kb_main())
    await cq.answer("Действие отменено.")

# Назад в главное меню
@dp.callback_query_handler(lambda c: c.data == "back_main")
async def cb_back_main(cq: types.CallbackQuery):
    try:
        await cq.message.edit_text("⬛️🟡 <b>FULL BODY</b>\nВыбери действие 👇", parse_mode="HTML", reply_markup=kb_main())
    except Exception:
        await cq.message.answer("⬛️🟡 <b>FULL BODY</b>\nВыбери действие 👇", parse_mode="HTML", reply_markup=kb_main())
    await cq.answer()

# Переход в «Тренировки»
@dp.callback_query_handler(lambda c: c.data == "menu_workouts")
async def cb_menu_workouts(cq: types.CallbackQuery):
    await cq.message.edit_text("🏋️ Выбери тренировку:", reply_markup=kb_workouts())
    await cq.answer()

# Прогресс (последние записи)
@dp.callback_query_handler(lambda c: c.data == "menu_progress")
async def cb_menu_progress(cq: types.CallbackQuery):
    data = load_data()
    fb = data.get(PROGRAM, {})
    text = "📊 <b>Последние записи</b>\n"
    for wname, ex_dict in fb.items():
        text += f"\n<b>{wname}</b>\n"
        for ex_name, logs in ex_dict.items():
            if not logs:
                continue
            last = logs[-1]
            text += f"• {ex_name}: {last['avg']} кг ({last['date']})\n"
    if text.strip() == "📊 <b>Последние записи</b>":
        text = "Пока нет данных."
    await cq.message.edit_text(text, parse_mode="HTML", reply_markup=kb_main())
    await cq.answer()

# Открыть конкретную тренировку
@dp.callback_query_handler(lambda c: c.data.startswith("open::"))
async def cb_open_workout(cq: types.CallbackQuery):
    _, idx_str = cq.data.split("::", 1)
    w_idx = int(idx_str)
    wname = WORKOUTS[w_idx]["name"]
    plan = "\n".join(f"{i+1}) {ex}" for i, ex in enumerate(WORKOUTS[w_idx]["exercises"]))
    txt = f"🏋️ <b>{wname}</b>\n\n{plan}\n\nВыбери упражнение:"
    await cq.message.edit_text(txt, parse_mode="HTML", reply_markup=kb_exercises(w_idx))
    await cq.answer()

# Открыть упражнение
@dp.callback_query_handler(lambda c: c.data.startswith("ex::"))
async def cb_open_exercise(cq: types.CallbackQuery, state: FSMContext):
    _, w_idx_str, ex_idx_str = cq.data.split("::", 2)
    w_idx = int(w_idx_str)
    ex_idx = int(ex_idx_str)
    wname = WORKOUTS[w_idx]["name"]
    exname = WORKOUTS[w_idx]["exercises"][ex_idx]

    data = load_data()
    logs = data[PROGRAM][wname][exname]
    prev_text = logs[-1]["text"] if logs else "— нет данных —"
    prev_date = logs[-1]["date"] if logs else "—"

    await state.update_data(workout_idx=w_idx, exercise_idx=ex_idx)

    msg = (
        f"🟡 <b>{exname}</b>\n"
        f"📅 Последняя: {prev_date}\n"
        f"🏋️ Было: {prev_text}\n\n"
        f"Введи {SETS_PER_EXERCISE} подходов в формате:\n"
        f"<code>60x8 / 62.5x8 / 65x6 / 65x6 / 67.5x5</code>\n\n"
        f"/cancel — отмена"
    )
    await cq.message.edit_text(msg, parse_mode="HTML")
    await InputState.waiting_for_sets.set()
    await cq.answer()

# Приём 5 подходов
@dp.message_handler(state=InputState.waiting_for_sets, content_types=types.ContentTypes.TEXT)
async def handle_sets_input(m: types.Message, state: FSMContext):
    user = await state.get_data()
    w_idx = user["workout_idx"]
    ex_idx = user["exercise_idx"]
    wname = WORKOUTS[w_idx]["name"]
    exname = WORKOUTS[w_idx]["exercises"][ex_idx]

    try:
        sets = parse_sets_line(m.text)
    except ValueError as e:
        await m.reply(f"⚠️ {e}\nПример: 60x8 / 62.5x8 / 65x6 / 65x6 / 67.5x5")
        return

    data = load_data()
    logs = data[PROGRAM][wname][exname]
    prev_avg = logs[-1]["avg"] if logs else 0.0

    avg = avg_weight(sets)
    delta = round(avg - prev_avg, 2)
    today = datetime.now().strftime("%Y-%m-%d")

    entry = {"date": today, "sets": sets, "avg": avg, "text": m.text}
    data[PROGRAM][wname][exname].append(entry)
    save_data(data)

    report = (
        f"✅ <b>{exname}</b> сохранено\n"
        f"📅 {today}\n"
        f"📈 Средний вес: {avg} кг (было {prev_avg} кг)\n"
        f"Δ Прирост: {delta:+} кг"
    )
    await m.answer(report, parse_mode="HTML", reply_markup=kb_main())
    await state.finish()

# Фоллбек
@dp.message_handler()
async def fallback(m: types.Message):
    await m.answer("Используй /start или кнопки меню.")

# ======= ЗАПУСК =======
if __name__ == "__main__":
    ensure_structure()
    print("✅ Бот запущен. Нажмите Ctrl+C для остановки.")
    executor.start_polling(dp, skip_updates=True)
