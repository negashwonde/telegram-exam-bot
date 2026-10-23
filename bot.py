import os
import sqlite3
import pandas as pd
import telebot
from telebot import types

TOKEN = "8305646058:AAGEa3w6KgRk-3yFkBJUwHPDy9vaWH6v5NI"
bot = telebot.TeleBot(TOKEN)


# ---------------------------------------------------------
# 1. DATABASE SETUP (ዳታቤዙን ማስተካከል እና ማዋቀር)
# ---------------------------------------------------------
def init_db():
    conn = sqlite3.connect('exam_bot.db')
    cursor = conn.cursor()

    # የድሮው users ቴብል department ከሌለው በራስ-ሰር አስተካክሎ እንዲፈጥር ማድረግ
    cursor.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cursor.fetchall()]
    if columns and 'department' not in columns:
        cursor.execute("DROP TABLE users")

    # የተማሪዎች ቴብል (departmentን ጨምሮ)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            department TEXT
        )
    ''')

    # የጥያቄዎች ቴብል
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            question_text TEXT,
            option_a TEXT,
            option_b TEXT,
            option_c TEXT,
            option_d TEXT,
            correct_option TEXT,
            explanation TEXT
        )
    ''')

    # የተማሪዎች ውጤት መያዣ ቴብል
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_scores (
            user_id INTEGER,
            category TEXT,
            total_answered INTEGER DEFAULT 0,
            correct_count INTEGER DEFAULT 0,
            wrong_count INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, category)
        )
    ''')

    conn.commit()
    conn.close()


init_db()

user_states = {}
user_quizzes = {}  # የፈተና ጊዜያዊ መያዣ


# ---------------------------------------------------------
# 2. FILE UPLOAD HANDLER (Excel Upload)
# ---------------------------------------------------------
@bot.message_handler(content_types=['document'])
def handle_file_upload(message):
    file_name = message.document.file_name

    if file_name.endswith('.xlsx') or file_name.endswith('.csv'):
        bot.reply_to(message, "⏳ ፋይሉ እየወረደና ወደ ዳታቤዝ እየገባ ነው፣ እባክዎን ትንሽ ይጠብቁ...")

        try:
            file_info = bot.get_file(message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)

            file_path = f"temp_{file_name}"
            with open(file_path, 'wb') as new_file:
                new_file.write(downloaded_file)

            if file_name.endswith('.xlsx'):
                df = pd.read_excel(file_path)
            else:
                df = pd.read_csv(file_path)

            conn = sqlite3.connect('exam_bot.db')
            cursor = conn.cursor()

            inserted_count = 0
            for index, row in df.iterrows():
                cursor.execute('''
                    INSERT INTO questions (category, question_text, option_a, option_b, option_c, option_d, correct_option, explanation)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    str(row['category']).strip(),
                    str(row['question_text']).strip(),
                    str(row['option_a']).strip(),
                    str(row['option_b']).strip(),
                    str(row['option_c']).strip(),
                    str(row['option_d']).strip(),
                    str(row['correct_option']).strip().upper(),
                    str(row['explanation']).strip()
                ))
                inserted_count += 1

            conn.commit()
            conn.close()

            if os.path.exists(file_path):
                os.remove(file_path)

            bot.reply_to(message, f"🎉 በስኬት ተጠናቋል!\nበጠቅላላ **{inserted_count}** ጥያቄዎች ወደ ዳታቤዝ ገብተዋል።")

        except Exception as e:
            bot.reply_to(message, f"❌ ስህተት አጋጥሟል! ፋይሉ ትክክለኛ መሆኑን ያረጋግጡ።\nError: {e}")
    else:
        bot.reply_to(message, "⚠️ እባክዎን የ Excel (`.xlsx`) ወይም የ CSV (`.csv`) ፋይል ብቻ ይላኩ።")


# ---------------------------------------------------------
# 3. START & REGISTRATION
# ---------------------------------------------------------
@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.from_user.id

    conn = sqlite3.connect('exam_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()

    if user:
        show_main_menu(message)
    else:
        user_states[user_id] = {'step': 'AWAITING_NAME'}
        bot.reply_to(message,
                     "👋 ሰላም! እንኳን ወደ አገር አቀፍ የፈተናዎች ዝግጅት ቦት በደህና መጡ።\n\nለመጀመር እባክዎን **ሙሉ ስምዎን (Full Name)** ያስገቡ፡")


@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id, {}).get('step') == 'AWAITING_NAME')
def get_name(message):
    user_id = message.from_user.id
    user_states[user_id]['full_name'] = message.text
    user_states[user_id]['step'] = 'AWAITING_DEPT'

    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(
        types.KeyboardButton('📚 9-12ኛ ክፍል (Natural)'),
        types.KeyboardButton('📚 9-12ኛ ክፍል (Social)'),
        types.KeyboardButton('📖 Remedial (Natural)'),
        types.KeyboardButton('📖 Remedial (Social)'),
        types.KeyboardButton('🎓 Freshman (Natural)'),
        types.KeyboardButton('🎓 Freshman (Social)'),
        types.KeyboardButton('💻 CS Exit Exam')
    )

    bot.send_message(message.chat.id, "✨ በጣም አሪፍ! አሁን ደግሞ ከታች ካሉት የትምህርት ዘርፎች **የእርስዎን ዲፓርትመንት** ይምረጡ፡",
                     reply_markup=markup)


@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id, {}).get('step') == 'AWAITING_DEPT')
def get_department(message):
    user_id = message.from_user.id
    dept = message.text.replace('📚 ', '').replace('📖 ', '').replace('🎓 ', '').replace('💻 ', '')
    full_name = user_states[user_id]['full_name']

    conn = sqlite3.connect('exam_bot.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO users (user_id, full_name, department) VALUES (?, ?, ?)",
                   (user_id, full_name, dept))
    conn.commit()
    conn.close()

    del user_states[user_id]
    bot.send_message(message.chat.id, f"🎉 ምዝገባው በስኬት ተጠናቋል!\n👤 ስም: **{full_name}**\n🏫 ዲፓርትመንት: **{dept}**")
    show_main_menu(message)


# ---------------------------------------------------------
# 4. MAIN MENU
# ---------------------------------------------------------
def show_main_menu(message):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(
        types.KeyboardButton('📚 9-12ኛ ክፍል (Natural)'),
        types.KeyboardButton('📚 9-12ኛ ክፍል (Social)'),
        types.KeyboardButton('📖 Remedial (Natural)'),
        types.KeyboardButton('📖 Remedial (Social)'),
        types.KeyboardButton('🎓 Freshman (Natural)'),
        types.KeyboardButton('🎓 Freshman (Social)'),
        types.KeyboardButton('💻 CS Exit Exam'),
        types.KeyboardButton('📊 ውጤቶቼን አሳይ (My Results)')
    )
    bot.send_message(message.chat.id, "📌 እባክዎን መስራት የሚፈልጉትን የትምህርት ዘርፍ ወይም አማራጭ ከታች ይምረጡ፡", reply_markup=markup)


# ---------------------------------------------------------
# 5. QUIZ FLOW
# ---------------------------------------------------------
@bot.message_handler(func=lambda msg: msg.text in [
    '📚 9-12ኛ ክፍል (Natural)', '📚 9-12ኛ ክፍል (Social)',
    '📖 Remedial (Natural)', '📖 Remedial (Social)',
    '🎓 Freshman (Natural)', '🎓 Freshman (Social)',
    '💻 CS Exit Exam'
])
def start_category_quiz(message):
    user_id = message.from_user.id
    category = message.text.replace('📚 ', '').replace('📖 ', '').replace('🎓 ', '').replace('💻 ', '')

    conn = sqlite3.connect('exam_bot.db')
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, category, question_text, option_a, option_b, option_c, option_d, correct_option, explanation FROM questions WHERE category = ?",
        (category,))
    questions = cursor.fetchall()
    conn.close()

    if questions:
        user_quizzes[user_id] = {
            'questions': questions,
            'index': 0,
            'correct': 0,
            'wrong': 0,
            'category': category
        }

        conn = sqlite3.connect('exam_bot.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_scores WHERE user_id = ? AND category = ?", (user_id, category))
        conn.commit()
        conn.close()

        bot.send_message(message.chat.id, f"🚀 ፈተናው ተጀምሯል! በጠቅላላ **{len(questions)}** ጥያቄዎች አሉ።")
        send_quiz_question(message.chat.id, user_id)
    else:
        bot.send_message(message.chat.id,
                         f"⚠️ ለ **{category}** እስካሁን የተካተተ ጥያቄ የለም። እባክዎን የ Excel ፋይል በመላክ ጥያቄዎችን ያስገቡ።")


def send_quiz_question(chat_id, user_id):
    quiz = user_quizzes.get(user_id)
    if not quiz:
        return

    index = quiz['index']
    questions = quiz['questions']

    if index < len(questions):
        q = questions[index]
        q_id, cat, q_text, opt_a, opt_b, opt_c, opt_d, correct, exp = q

        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton(f"🇦 {opt_a}", callback_data=f"ans_{q_id}_A"),
            types.InlineKeyboardButton(f"🇧 {opt_b}", callback_data=f"ans_{q_id}_B"),
            types.InlineKeyboardButton(f"🇨 {opt_c}", callback_data=f"ans_{q_id}_C"),
            types.InlineKeyboardButton(f"🇩 {opt_d}", callback_data=f"ans_{q_id}_D")
        )

        bot.send_message(chat_id, f"📌 **ዘርፍ፡ {cat}** (ጥያቄ {index + 1}/{len(questions)})\n\n{q_text}",
                         parse_mode="Markdown", reply_markup=markup)
    else:
        show_final_score(chat_id, user_id)


def show_final_score(chat_id, user_id):
    quiz = user_quizzes.get(user_id)
    if not quiz:
        return

    total = len(quiz['questions'])
    correct = quiz['correct']
    wrong = quiz['wrong']
    category = quiz['category']
    percentage = (correct / total) * 100 if total > 0 else 0

    conn = sqlite3.connect('exam_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT full_name, department FROM users WHERE user_id = ?", (user_id,))
    user_info = cursor.fetchone()

    cursor.execute('''
        INSERT OR REPLACE INTO user_scores (user_id, category, total_answered, correct_count, wrong_count)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, category, total, correct, wrong))
    conn.commit()
    conn.close()

    full_name = user_info[0] if user_info else "ተማሪ"

    result_text = (
        f"🎉 **እንኳን ደስ አለዎት {full_name}! ፈተናውን አጠናቀዋል**\n\n"
        f"📊 **የውጤት ማጠቃለያ:**\n"
        f"• የሰራቸው ጥያቄዎች: {total}/{total}\n"
        f"• ትክክለኛ መልሶች: {correct} ✅\n"
        f"• የተሳሳቱ መልሶች: {wrong} ❌\n"
        f"• **አጠቃላይ ውጤት:** `{correct}/{total}` (**{percentage:.1f}%**)\n\n"
        f"ምርጥ ስራ! ከታች ካሉት ሜኑዎች በመምረጥ ሌሎች ፈተናዎችን መስራት ይችላሉ።"
    )

    bot.send_message(chat_id, result_text, parse_mode="Markdown")

    if user_id in user_quizzes:
        del user_quizzes[user_id]


# ---------------------------------------------------------
# 6. ANSWER CHECKING & NEXT QUESTION
# ---------------------------------------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith('ans_'))
def handle_answer(call):
    user_id = call.from_user.id
    quiz = user_quizzes.get(user_id)

    if not quiz:
        bot.answer_callback_query(call.id, "⚠️ እባክዎን በመጀመሪያ ፈተና ይጀምሩ።")
        return

    _, q_id, user_choice = call.data.split('_')
    index = quiz['index']
    q = quiz['questions'][index]
    correct_option = q[7]
    explanation = q[8]

    if user_choice == correct_option:
        quiz['correct'] += 1
        res_text = f"✅ **ትክክል ነው!**\n\n💡 {explanation}"
    else:
        quiz['wrong'] += 1
        res_text = f"❌ **ስህተት ነው!**\nትክክለኛው መልስ፡ **{correct_option}** ነው\n\n💡 {explanation}"

    bot.send_message(call.message.chat.id, res_text, parse_mode="Markdown")

    quiz['index'] += 1
    send_quiz_question(call.message.chat.id, user_id)


# ---------------------------------------------------------
# 7. VIEW RESULTS
# ---------------------------------------------------------
@bot.message_handler(func=lambda msg: msg.text == '📊 ውጤቶቼን አሳይ (My Results)')
def show_user_results(message):
    user_id = message.from_user.id

    conn = sqlite3.connect('exam_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT full_name, department FROM users WHERE user_id = ?", (user_id,))
    user_info = cursor.fetchone()

    cursor.execute("SELECT category, total_answered, correct_count, wrong_count FROM user_scores WHERE user_id = ?",
                   (user_id,))
    scores = cursor.fetchall()
    conn.close()

    if user_info:
        full_name, dept = user_info
        text = f"📊 **የተማሪው ውጤት ማጠቃለያ**\n\n👤 ስም: **{full_name}**\n🏫 ዲፓርትመንት: **{dept}**\n\n--------------------------\n"

        if scores:
            for cat, total, correct, wrong in scores:
                percentage = (correct / total) * 100 if total > 0 else 0
                text += f"📌 **ዘርፍ:** {cat}\n  • የተሰሩ ጥያቄዎች: {total}\n  • ትክክለኛ: {correct} ✅\n  • የተሳሳቱ: {wrong} ❌\n  • **ውጤት:** `{correct}/{total}` (**{percentage:.1f}%**)\n\n"
        else:
            text += "⚠️ እስካሁን የሰሩት ፈተና የለም።"

        bot.send_message(message.chat.id, text, parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "⚠️ እባክዎን በመጀመሪያ `/start` ብለው ይመዝገቡ።")


print("ቦቱ በስኬት ስራ ጀምሯል...")
bot.infinity_polling()