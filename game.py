"""
Игровая логика без привязки к Telegram: из callback_data строятся экраны (текст + кнопки).

Бот БЕЗ состояния на сервере: весь прогресс «зашит» в callback_data.
Поэтому перезапуск или «засыпание» бесплатного сервера на Render не ломает прохождение.

Формат callback_data (поля через «:»):
    lg:<lang>                       выбор языка
    lm                              меню выбора языка
    m:<lang>                        главное меню
    q:<lang>   qs:<lang>            квест: вступление / старт
    a:<lang>:<i>:<opt>:<hist>       ответ на ситуацию i, вариант opt
    n:<lang>:<i>:<hist>             следующая ситуация
    r:<lang>:<hist>                 итог квеста
    c:<lang>:<hist>                 сертификат (обрабатывается в bot.py)
    t:<lang>   ts:<lang>            «Правда или миф»: вступление / старт
    y:<lang>:<i>:<ans>:<hist>       ответ на утверждение i (ans: 1 — «правда», 0 — «миф»)
    x:<lang>:<i>:<hist>             следующее утверждение
    z:<lang>:<hist>                 итог «Правда или миф»
hist — строка цифр: результаты уже пройденных шагов (квест: 0/1/2, миф: 2 — верно, 0 — нет).
"""

import random
from dataclasses import dataclass
from urllib.parse import quote

from content import FACTS, MYTHS, SCENARIOS, UI

N = len(SCENARIOS)
MAX_SCORE = N * 2
MN = len(MYTHS)
NUM = ["1️⃣", "2️⃣", "3️⃣"]
BAR_ICONS = {"2": "🟩", "1": "🟨", "0": "🟥"}


@dataclass
class Btn:
    label: str
    data: str | None = None
    url: str | None = None


@dataclass
class Screen:
    text: str
    rows: list[list[Btn]]


# ----------------------------------------------------------------------------
# Утилиты
# ----------------------------------------------------------------------------
def norm_lang(lang: str) -> str:
    return lang if lang in UI else "ru"


def bar(hist: str, total: int) -> str:
    return "".join(BAR_ICONS.get(c, "⬜") for c in hist) + "⬜" * (total - len(hist))


def valid_hist(hist: str, length: int, allowed: str) -> bool:
    return len(hist) == length and all(c in allowed for c in hist)


def tier_for(lang: str, score: int) -> tuple[str, str]:
    for min_score, title, desc in UI[lang]["tiers"]:
        if score >= min_score:
            return title, desc
    return UI[lang]["tiers"][-1][1], UI[lang]["tiers"][-1][2]


def quest_score(hist: str) -> int:
    return sum(int(c) for c in hist)


# ----------------------------------------------------------------------------
# Экраны
# ----------------------------------------------------------------------------
def lang_screen() -> Screen:
    return Screen(UI["ru"]["choose_lang"], [[
        Btn("🇷🇺 Русский", "lg:ru"),
        Btn("Татарча", "lg:tt"),
    ]])


def menu_screen(lang: str) -> Screen:
    u = UI[lang]
    return Screen(u["menu"], [
        [Btn(u["btn_quest"], f"q:{lang}")],
        [Btn(u["btn_myth"], f"t:{lang}")],
        [Btn(u["btn_lang"], "lm")],
    ])


def quest_intro(lang: str) -> Screen:
    u = UI[lang]
    return Screen(u["quest_intro"].format(n=N), [
        [Btn(u["btn_go"], f"qs:{lang}")],
        [Btn(u["btn_menu"], f"m:{lang}")],
    ])


def question_screen(lang: str, i: int, hist: str) -> Screen:
    u, sc = UI[lang], SCENARIOS[i]
    order = list(range(len(sc["options"])))
    random.shuffle(order)  # порядок вариантов каждый раз разный
    lines = [f"{NUM[k]} {sc['options'][o]['text'][lang]}" for k, o in enumerate(order)]
    text = (
        f"<b>{u['scene'].format(i=i + 1, n=N)}</b>\n{bar(hist, N)}\n"
        f"{u['stage'].format(stage=sc['stage'][lang])}\n\n"
        f"{sc['text'][lang]}\n\n" + "\n\n".join(lines)
    )
    rows = [[Btn(NUM[k], f"a:{lang}:{i}:{o}:{hist}") for k, o in enumerate(order)]]
    return Screen(text, rows)


def answer_screen(lang: str, i: int, o: int, hist: str) -> Screen:
    u = UI[lang]
    opt = SCENARIOS[i]["options"][o]
    new = hist + str(opt["score"])
    text = (
        f"<b>{u['scene'].format(i=i + 1, n=N)}</b>\n{bar(new, N)}\n\n"
        f"{u['your_choice']} <i>{opt['text'][lang]}</i>\n\n"
        f"<b>{u['verdict'][opt['score']]}</b>\n{opt['explain'][lang]}\n\n"
        f"{u['points'].format(p=opt['score'])}"
    )
    if i == N - 1:
        btn = Btn(u["btn_result"], f"r:{lang}:{new}")
    else:
        btn = Btn(u["btn_next"], f"n:{lang}:{i + 1}:{new}")
    return Screen(text, [[btn]])


def result_screen(lang: str, hist: str, bot_link: str) -> Screen:
    u = UI[lang]
    score = quest_score(hist)
    title, desc = tier_for(lang, score)
    weak = [f"{k + 1}. {SCENARIOS[k]['stage'][lang]}" for k, c in enumerate(hist) if c != "2"]
    review = u["review"].format(items="; ".join(weak)) if weak else u["review_ok"]
    fact = u["fact"].format(fact=random.choice(FACTS)[lang])
    text = (
        f"{u['result'].format(s=score, m=MAX_SCORE)}\n{bar(hist, N)}\n\n"
        f"<b>{title}</b>\n{desc}\n\n{review}\n\n{fact}\n\n{u['report']}"
    )
    share_text = u["share_text"].format(s=score, m=MAX_SCORE)
    share_url = f"https://t.me/share/url?url={quote(bot_link, safe='')}&text={quote(share_text)}"
    return Screen(text, [
        [Btn(u["btn_cert"], f"c:{lang}:{hist}")],
        [Btn(u["btn_share"], url=share_url)],
        [Btn(u["btn_again"], f"qs:{lang}"), Btn(u["btn_menu"], f"m:{lang}")],
    ])


# --- Правда или миф ---------------------------------------------------------
def myth_intro(lang: str) -> Screen:
    u = UI[lang]
    return Screen(u["myth_intro"].format(n=MN), [
        [Btn(u["btn_go"], f"ts:{lang}")],
        [Btn(u["btn_menu"], f"m:{lang}")],
    ])


def myth_question(lang: str, i: int, hist: str) -> Screen:
    u = UI[lang]
    text = (
        f"<b>{u['myth_q'].format(i=i + 1, n=MN)}</b>\n{bar(hist, MN)}\n\n"
        f"{MYTHS[i]['text'][lang]}"
    )
    return Screen(text, [[
        Btn(u["btn_true"], f"y:{lang}:{i}:1:{hist}"),
        Btn(u["btn_false"], f"y:{lang}:{i}:0:{hist}"),
    ]])


def myth_answer(lang: str, i: int, ans: int, hist: str) -> Screen:
    u, m = UI[lang], MYTHS[i]
    correct = (ans == 1) == m["truth"]
    new = hist + ("2" if correct else "0")
    label = u["myth_true_label"] if m["truth"] else u["myth_false_label"]
    text = (
        f"<b>{u['myth_q'].format(i=i + 1, n=MN)}</b>\n{bar(new, MN)}\n\n"
        f"{u['myth_right'] if correct else u['myth_wrong']}\n"
        f"<i>{m['text'][lang]}</i>\n\n<b>{label}</b> {m['explain'][lang]}"
    )
    if i == MN - 1:
        btn = Btn(u["btn_result"], f"z:{lang}:{new}")
    else:
        btn = Btn(u["btn_next"], f"x:{lang}:{i + 1}:{new}")
    return Screen(text, [[btn]])


def myth_result(lang: str, hist: str) -> Screen:
    u = UI[lang]
    score = hist.count("2")
    key = "hi" if score >= MN - 1 else "mid" if score >= MN // 2 else "lo"
    text = (
        f"{u['myth_result'].format(s=score, m=MN)}\n{bar(hist, MN)}\n\n"
        f"{u['myth_comments'][key]}"
    )
    return Screen(text, [
        [Btn(u["btn_quest"], f"q:{lang}")],
        [Btn(u["btn_again"], f"ts:{lang}"), Btn(u["btn_menu"], f"m:{lang}")],
    ])


# ----------------------------------------------------------------------------
# Маршрутизация callback_data → экран
# ----------------------------------------------------------------------------
def route(data: str, bot_link: str) -> Screen:
    """Возвращает экран по callback_data. При любой ошибке/подделке данных — главное меню."""
    parts = data.split(":")
    cmd = parts[0]
    lang = norm_lang(parts[1]) if len(parts) > 1 else "ru"
    try:
        if cmd == "lm":
            return lang_screen()
        if cmd in ("lg", "m"):
            return menu_screen(lang)
        if cmd == "q":
            return quest_intro(lang)
        if cmd == "qs":
            return question_screen(lang, 0, "")
        if cmd == "n":
            i, hist = int(parts[2]), parts[3]
            if 0 < i < N and valid_hist(hist, i, "012"):
                return question_screen(lang, i, hist)
        if cmd == "a":
            i, o, hist = int(parts[2]), int(parts[3]), parts[4]
            if 0 <= i < N and 0 <= o < len(SCENARIOS[i]["options"]) and valid_hist(hist, i, "012"):
                return answer_screen(lang, i, o, hist)
        if cmd == "r":
            hist = parts[2]
            if valid_hist(hist, N, "012"):
                return result_screen(lang, hist, bot_link)
        if cmd == "t":
            return myth_intro(lang)
        if cmd == "ts":
            return myth_question(lang, 0, "")
        if cmd == "x":
            i, hist = int(parts[2]), parts[3]
            if 0 < i < MN and valid_hist(hist, i, "02"):
                return myth_question(lang, i, hist)
        if cmd == "y":
            i, ans, hist = int(parts[2]), int(parts[3]), parts[4]
            if 0 <= i < MN and ans in (0, 1) and valid_hist(hist, i, "02"):
                return myth_answer(lang, i, ans, hist)
        if cmd == "z":
            hist = parts[2]
            if valid_hist(hist, MN, "02"):
                return myth_result(lang, hist)
    except (ValueError, IndexError):
        pass
    return menu_screen(lang)
