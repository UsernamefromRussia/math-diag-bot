# -*- coding: utf-8 -*-
"""
Telegram-бот "Экспресс-диагностика по математике"
Стек: aiogram 3.x, long polling (без вебхуков — проще всего задеплоить).

Как это работает:
  Приветствие -> ОГЭ/ЕГЭ -> Имя -> Класс -> 10 заданий -> Результат ->
  Рекомендация -> Призыв к записи -> Отчёт репетитору в отдельный чат

ГДЕ ВСТАВЛЯТЬ СВОИ ДАННЫЕ:
  1. Переменные окружения BOT_TOKEN и REPORT_CHAT_ID (см. README.md)
  2. Списки TASKS_OGE и TASKS_EGE ниже — сейчас там заглушки (10+10),
     замени текст/ответ/тему на свои задания.
  3. Ссылка для кнопки записи — переменная SIGNUP_URL
"""

import asyncio
import logging
import os
import re
from dataclasses import dataclass

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

try:
    from dotenv import load_dotenv  # только для локального запуска
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ["BOT_TOKEN"]
REPORT_CHAT_ID = int(os.environ["REPORT_CHAT_ID"])  # id чата/канала для отчётов

# Ссылка для кнопки записи — ЗАМЕНИ на свою (аккаунт школы или личный Telegram/сайт записи)
SIGNUP_URL = os.environ.get("SIGNUP_URL", "https://t.me/your_username")


# ---------------------------------------------------------------------------
# ДАННЫЕ ЗАДАНИЙ (ЗАГЛУШКИ — замени на свои)
# ---------------------------------------------------------------------------

@dataclass
class Task:
    topic: str          # тема задания — используется для рекомендаций
    question: str        # текст задания
    answer: str           # правильный ответ (сравнивается как строка после нормализации)
    image: str | None = None  # путь к картинке (опционально), напр. "images/oge_04.png"
    options: list[str] | None = None  # если задан — вместо ввода текста показываются кнопки-варианты


TASKS_OGE: list[Task] = [
    Task(
        "Дроби и вычисления",
        "Найдите значение выражения: (5/6 + 0,3) · 15",
        "17",
    ),
    Task(
        "Степени и корни",
        "Найдите значение выражения: (3√2)² / (2² · 3²)",
        "0.5",
    ),
    Task(
        "Линейные уравнения",
        "Найдите корень уравнения: 3(x + 8) − 2(x − 8) = 8",
        "-32",
    ),
    Task(
        "Теория вероятностей",
        "В фирме такси в данный момент свободно 20 машин: 9 чёрных, 7 жёлтых и 4 белых. "
        "По вызову выехала одна из машин, случайно оказавшаяся ближе всего к заказчику. "
        "Найдите вероятность того, что к нему приедет жёлтое такси.",
        "0.35",
    ),
    Task(
        "Графики функций",
        "Установите соответствие между графиками функций и формулами, которые их задают.\n\n"
        "Выбери число — последовательность цифр АБВ:",
        "132",
        options=["132", "312", "123", "231"],
        image="images/oge_05_graphs.png",
    ),
    Task(
        "Квадратные неравенства",
        "Укажите решение неравенства: x² − 16 ≤ 0",
        "[−4; 4]",
        options=["(−∞; −4] ∪ [4; +∞)", "[−4; 4]", "(−∞; 4]", "[0; 16]"],
    ),
    Task(
        "Прогрессии",
        "В амфитеатре 10 рядов. В первом ряду 12 мест, а в каждом следующем — на 3 места больше, "
        "чем в предыдущем. Сколько всего мест в амфитеатре?",
        "255",
    ),
    Task(
        "Геометрия: треугольники",
        "В прямоугольном треугольнике один из катетов равен 6, а гипотенуза равна 10. "
        "Найдите площадь этого треугольника.",
        "24",
    ),
    Task(
        "Геометрия: четырёхугольники",
        "Четырёхугольник ABCD описан около окружности, AB = 7, BC = 12, CD = 9. Найдите четвёртую сторону AD.",
        "4",
    ),
    Task(
        "Текстовая задача / моделирование",
        "Два велосипедиста одновременно отправляются в 60-километровый пробег. Первый едет со скоростью "
        "на 3 км/ч больше второго и приезжает к финишу на 1 час раньше. Пусть x км/ч — скорость первого "
        "велосипедиста. Укажите уравнение, соответствующее условию задачи:",
        "60/(x−3) − 60/x = 1",
        options=[
            "60/(x−3) − 60/x = 1",
            "60/x − 60/(x−3) = 1",
            "60/(x+3) + 60/x = 1",
            "60(x−3) − 60x = 1",
        ],
    ),
]

TASKS_EGE: list[Task] = [
    Task(
        "Планиметрия",
        "В треугольнике ABC угол C равен 54°, AD — биссектриса, угол BAD равен 23°. "
        "Найдите величину угла ADB. Ответ дайте в градусах.",
        "77",
        image="images/ege_01_triangle.png",
    ),
    Task(
        "Векторы",
        "Даны векторы a(2;2) и b(2;−2). Найдите длину вектора 7a + b.",
        "20",
    ),
    Task(
        "Стереометрия",
        "Цилиндр, объём которого равен 18, описан около шара. Найдите объём шара.",
        "12",
    ),
    Task(
        "Вероятность",
        "Из районного центра в деревню ежедневно ходит автобус. Вероятность того, что в понедельник "
        "в автобусе окажется меньше 20 пассажиров, равна 0,94. Вероятность того, что окажется меньше "
        "15 пассажиров, равна 0,56. Найдите вероятность того, что число пассажиров будет от 15 до 19 включительно.",
        "0.38",
    ),
    Task(
        "Вероятность",
        "Автоматическая линия изготавливает батарейки. Вероятность того, что готовая батарейка неисправна, "
        "равна 0,2. Перед упаковкой каждая батарейка проходит систему контроля качества. Вероятность того, что "
        "система забракует неисправную батарейку, равна 0,95. Вероятность того, что система по ошибке забракует "
        "исправную батарейку, равна 0,05. Найдите вероятность того, что случайно выбранная изготовленная "
        "батарейка будет забракована системой контроля.",
        "0.23",
    ),
    Task(
        "Логарифмические уравнения",
        "Найдите корень уравнения log₈(5x + 47) = 3.",
        "93",
    ),
    Task(
        "Тригонометрия",
        "Найдите значение выражения: 3·sin164° / (sin82° · sin8°).",
        "6",
    ),
    Task(
        "Производная и графики",
        "На рисунке изображены график функции y = f(x) и касательная к нему в точке с абсциссой x0. "
        "Найдите значение производной функции f(x) в точке x0.",
        "0.2",
        image="images/ege_08_derivative.png",
    ),
    Task(
        "Текстовая задача (смеси)",
        "Смешав 45%-й и 97%-й растворы кислоты и добавив 10 кг чистой воды, получили 62%-й раствор кислоты. "
        "Если бы вместо 10 кг воды добавили 10 кг 50%-го раствора той же кислоты, то получили бы 72%-й раствор "
        "кислоты. Сколько килограммов 45%-го раствора использовали для получения смеси?",
        "15",
    ),
    Task(
        "Показательные функции и графики",
        "На рисунке изображён график функции вида f(x) = aˣ. Найдите значение f(−3).",
        "64",
        image="images/ege_10_exponent.png",
    ),
]


# ---------------------------------------------------------------------------
# ТЕКСТЫ ЭКРАНОВ
# ---------------------------------------------------------------------------

WELCOME_TEXT = (
    "👋 Привет!\n\n"
    "Это небольшая экспресс-диагностика по математике. Она поможет понять, "
    "какие темы у тебя уже хорошо получаются, а какие стоит повторить.\n\n"
    "Впереди 10 заданий — это займёт примерно 15–20 минут.\n"
    "Решай самостоятельно: так результат будет максимально полезным для тебя.\n\n"
    "Готов? Давай начнём 🚀"
)

EXAM_CHOICE_TEXT = "Отлично! К какому экзамену ты готовишься?"

NAME_PROMPT_TEXT = (
    "Хорошо! Теперь давай познакомимся 🤝\n\n"
    "Как тебя зовут?\n"
    "Это понадобится, чтобы в конце диагностики показать твой персональный результат."
)

GRADE_PROMPT_TEMPLATE = "Приятно познакомиться, {name}! 😊\n\nВ каком ты сейчас классе?\nВыбери свой вариант:"

TASKS_INTRO_TEMPLATE = (
    "Отлично, {name}! Всё готово 🔥\n\n"
    "Тест состоит из 10-ти заданий и займёт примерно 20 минут. "
    "Не торопись и внимательно читай условия. Используй тетрадку и ручку "
    "для выполнения необходимых вычислений. Не забудь указать здесь свой финальный ответ. "
    "Если не знаешь — ничего страшного, просто двигайся дальше.\n\n"
    "Погнали 🚀"
)

RESULT_TEMPLATE = (
    "🏁 Готово, {name}!\n\n"
    "Твой результат: {score}/10 верных ответов.\n"
    "{grade_comment}"
)

RECOMMENDATION_HEADER = "📌 Персональная рекомендация:\n\n"

CTA_TEXT = (
    "Экспресс-диагностика — это только первый шаг. Если хочешь системно подготовиться "
    "к успешной сдаче экзамена, записывайся на занятия!"
)


# ---------------------------------------------------------------------------
# СОСТОЯНИЯ FSM
# ---------------------------------------------------------------------------

class Diagnostic(StatesGroup):
    choosing_exam = State()
    entering_name = State()
    choosing_grade = State()
    answering = State()


router = Router()


def normalize(text: str) -> str:
    """Приводит ответ к единому виду для сравнения: убирает пробелы, запятая->точка, нижний регистр."""
    return re.sub(r"\s+", "", text.strip().lower().replace(",", "."))


def exam_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔵 ОГЭ", callback_data="exam_oge"),
        InlineKeyboardButton(text="🟣 ЕГЭ", callback_data="exam_ege"),
    ]])


def grade_kb(exam: str) -> InlineKeyboardMarkup:
    grades = ["8", "9"] if exam == "oge" else ["10", "11"]
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"{g} класс", callback_data=f"grade_{g}") for g in grades
    ]])


def start_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Начать диагностику", callback_data="start_diag")
    ]])


def begin_tasks_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Начать", callback_data="begin_tasks")
    ]])


def answer_kb(task: Task) -> InlineKeyboardMarkup:
    """Кнопки для задания: варианты ответа (если есть) + всегда 'пропустить'."""
    rows: list[list[InlineKeyboardButton]] = []
    if task.options:
        short = max(len(o) for o in task.options) <= 6
        if short:
            for i in range(0, len(task.options), 2):
                row = [InlineKeyboardButton(text=task.options[i], callback_data=f"opt_{i}")]
                if i + 1 < len(task.options):
                    row.append(InlineKeyboardButton(text=task.options[i + 1], callback_data=f"opt_{i + 1}"))
                rows.append(row)
        else:
            for i, opt in enumerate(task.options):
                rows.append([InlineKeyboardButton(text=opt[:64], callback_data=f"opt_{i}")])
    rows.append([InlineKeyboardButton(text="🤷 Не знаю / пропустить", callback_data="skip")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cta_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Записаться на занятия", url=SIGNUP_URL)
    ]])


def tasks_for(exam: str) -> list[Task]:
    return TASKS_OGE if exam == "oge" else TASKS_EGE


async def clear_kb(message: Message) -> None:
    """Убирает кнопки с уже отправленного сообщения (чтобы старый экран нельзя было нажать повторно)."""
    try:
        await message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


async def clear_kb_by_id(bot: Bot, chat_id: int, message_id: int | None) -> None:
    if message_id is None:
        return
    try:
        await bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=None)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# ХЭНДЛЕРЫ
# ---------------------------------------------------------------------------

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = message.from_user
    await state.update_data(tg_username=user.username, tg_user_id=user.id)
    await message.answer(WELCOME_TEXT, reply_markup=start_kb())


@router.callback_query(F.data == "start_diag")
async def start_diag(call: CallbackQuery, state: FSMContext):
    await state.set_state(Diagnostic.choosing_exam)
    await clear_kb(call.message)
    await call.message.answer(EXAM_CHOICE_TEXT, reply_markup=exam_kb())
    await call.answer()


@router.callback_query(Diagnostic.choosing_exam, F.data.startswith("exam_"))
async def choose_exam(call: CallbackQuery, state: FSMContext):
    exam = call.data.removeprefix("exam_")  # "oge" | "ege"
    await state.update_data(exam=exam)
    await state.set_state(Diagnostic.entering_name)
    await clear_kb(call.message)
    await call.message.answer(NAME_PROMPT_TEXT)
    await call.answer()


@router.message(Diagnostic.entering_name)
async def enter_name(message: Message, state: FSMContext):
    name = message.text.strip()[:50]
    await state.update_data(name=name)
    await state.set_state(Diagnostic.choosing_grade)
    exam = (await state.get_data())["exam"]
    await message.answer(GRADE_PROMPT_TEMPLATE.format(name=name), reply_markup=grade_kb(exam))


@router.callback_query(Diagnostic.choosing_grade, F.data.startswith("grade_"))
async def choose_grade(call: CallbackQuery, state: FSMContext):
    grade = call.data.removeprefix("grade_")
    await state.update_data(grade=grade, task_index=0, results=[])
    data = await state.get_data()
    await clear_kb(call.message)
    await call.message.answer(TASKS_INTRO_TEMPLATE.format(name=data["name"]), reply_markup=begin_tasks_kb())
    await call.answer()


@router.callback_query(F.data == "begin_tasks")
async def begin_tasks(call: CallbackQuery, state: FSMContext):
    await state.set_state(Diagnostic.answering)
    await clear_kb(call.message)
    await call.answer()
    await send_task(call.message, state)


async def send_task(message: Message, state: FSMContext):
    data = await state.get_data()
    idx = data["task_index"]
    task = tasks_for(data["exam"])[idx]
    header = f"Задание {idx + 1}/10\n\n"
    kb = answer_kb(task)
    if task.image:
        sent = await message.answer_photo(FSInputFile(task.image), caption=header + task.question, reply_markup=kb)
    else:
        sent = await message.answer(header + task.question, reply_markup=kb)
    await state.update_data(last_kb_message_id=sent.message_id)


async def record_answer(state: FSMContext, task: Task, given_answer: str | None):
    data = await state.get_data()
    results = data["results"]
    correct = given_answer is not None and normalize(given_answer) == normalize(task.answer)
    results.append({"topic": task.topic, "correct": correct})
    await state.update_data(results=results, task_index=data["task_index"] + 1)


@router.message(Diagnostic.answering)
async def receive_answer(message: Message, state: FSMContext):
    data = await state.get_data()
    task = tasks_for(data["exam"])[data["task_index"]]
    await clear_kb_by_id(message.bot, message.chat.id, data.get("last_kb_message_id"))
    await record_answer(state, task, message.text)
    await advance(message, state)


@router.callback_query(Diagnostic.answering, F.data == "skip")
async def skip_answer(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    task = tasks_for(data["exam"])[data["task_index"]]
    await clear_kb(call.message)
    await record_answer(state, task, None)
    await call.answer()
    await advance(call.message, state)


@router.callback_query(Diagnostic.answering, F.data.startswith("opt_"))
async def choose_option(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    task = tasks_for(data["exam"])[data["task_index"]]
    idx = int(call.data.removeprefix("opt_"))
    given = task.options[idx] if task.options and 0 <= idx < len(task.options) else None
    await clear_kb(call.message)
    await record_answer(state, task, given)
    await call.answer()
    await advance(call.message, state)


async def advance(message: Message, state: FSMContext):
    data = await state.get_data()
    if data["task_index"] < 10:
        await send_task(message, state)
    else:
        await finish_diagnostic(message, state)


def grade_comment(score: int) -> str:
    if score >= 8:
        return "Очень сильный результат! Видно хорошую базу — можно сразу переходить к более сложным темам и разбору задач второй части."
    if score >= 5:
        return "Хороший старт: часть тем усвоена уверенно, а часть стоит подтянуть — на занятиях разберём точечно, что именно."
    return "Пока много пробелов, и это нормально на старте — с системной подготовкой результат заметно вырастет."


def build_recommendation(results: list[dict]) -> str:
    wrong_topics = [r["topic"] for r in results if not r["correct"]]
    if not wrong_topics:
        return RECOMMENDATION_HEADER + "Ты справился со всеми заданиями — держим высокий уровень и переходим к более сложным задачам! 💪"
    # берём до 3 самых частых слабых тем, сохраняя порядок появления
    seen = []
    for t in wrong_topics:
        if t not in seen:
            seen.append(t)
    top = seen[:3]
    bullets = "\n".join(f"— {t}" for t in top)
    return RECOMMENDATION_HEADER + f"Стоит в первую очередь повторить:\n{bullets}\n\nЭто именно то, с чего мы начнём на занятиях."


def build_breakdown(results: list[dict]) -> str:
    lines = [f"Задание {i + 1} {'✅' if r['correct'] else '❌'}" for i, r in enumerate(results)]
    return "Разбор по заданиям:\n" + "\n".join(lines)


async def finish_diagnostic(message: Message, state: FSMContext):
    data = await state.get_data()
    results = data["results"]
    score = sum(1 for r in results if r["correct"])
    name = data["name"]

    await message.answer(RESULT_TEMPLATE.format(name=name, score=score, grade_comment=grade_comment(score)))
    await message.answer(build_breakdown(results))
    await message.answer(build_recommendation(results))
    await message.answer(CTA_TEXT, reply_markup=cta_kb())

    await send_report(message.bot, data, score, results)
    await state.clear()


def student_contact_line(data: dict) -> str:
    username = data.get("tg_username")
    user_id = data.get("tg_user_id")
    if username:
        return f"Telegram: @{username} (https://t.me/{username})"
    return f"Telegram: username не указан (id {user_id})"


async def send_report(bot: Bot, data: dict, score: int, results: list[dict]) -> None:
    exam_label = "ОГЭ" if data["exam"] == "oge" else "ЕГЭ"
    wrong = [r["topic"] for r in results if not r["correct"]]
    lines = [
        "📋 Новый результат диагностики",
        f"Имя: {data['name']}",
        f"Класс: {data['grade']}",
        f"Экзамен: {exam_label}",
        student_contact_line(data),
        f"Результат: {score}/10",
        "",
        build_breakdown(results),
    ]
    if wrong:
        lines.append("")
        lines.append("Слабые темы: " + ", ".join(dict.fromkeys(wrong)))
    try:
        await bot.send_message(REPORT_CHAT_ID, "\n".join(lines))
    except Exception:
        logging.exception("Не удалось отправить отчёт в REPORT_CHAT_ID")


async def main():
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
