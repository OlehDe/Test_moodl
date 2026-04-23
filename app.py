import json
import os
import random
from glob import glob
from flask import Flask, render_template, request, session, redirect, url_for, jsonify

app = Flask(__name__)
app.secret_key = 'your-secret-key-here-change-in-production'

# Папки, в яких шукаємо тести
TEST_DIRS = ['tests', 'sort']

def get_all_test_files():
    """Рекурсивно знаходить усі JSON-файли у дозволених папках."""
    tests = []
    for folder in TEST_DIRS:
        if not os.path.isdir(folder):
            continue
        pattern = os.path.join(folder, '**', '*.json')
        for filepath in glob(pattern, recursive=True):
            # Перевіряємо, чи файл дійсно всередині дозволеної папки (захист від Directory Traversal)
            real_path = os.path.abspath(filepath)
            if not any(os.path.abspath(f).startswith(os.path.dirname(real_path)) for f in TEST_DIRS):
                # Спрощена перевірка: чи шлях починається з однієї з дозволених папок
                if not any(real_path.startswith(os.path.abspath(d)) for d in TEST_DIRS):
                    continue
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    title = data.get('title', os.path.basename(filepath))
            except Exception:
                title = os.path.basename(filepath)
            # Зберігаємо відносний шлях (відносно кореня проєкту) для використання в маршрутах
            rel_path = os.path.relpath(filepath)
            tests.append({'path': rel_path, 'title': title})
    return tests

def load_test(rel_path):
    """Завантажує JSON за відносним шляхом."""
    # Додаткова перевірка безпеки: шлях має починатися з однієї з дозволених папок
    if not any(rel_path.startswith(folder + os.sep) or rel_path == folder for folder in TEST_DIRS):
        raise ValueError("Недозволений шлях до тесту")
    full_path = rel_path
    with open(full_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def prepare_test_for_display(test_data):
    """Перемішує питання/варіанти, якщо setting == 'random'."""
    import copy
    test_copy = copy.deepcopy(test_data)
    is_random = test_copy.get('setting') == 'random'
    if is_random:
        random.shuffle(test_copy['questions'])
    for q in test_copy['questions']:
        qtype = q.get('type', 'single_choice')
        if is_random and qtype in ('single_choice', 'multiple_choice'):
            random.shuffle(q['options'])
    return test_copy

@app.route('/')
def index():
    tests = get_all_test_files()
    return render_template('index.html', tests=tests)

@app.route('/test/<path:filename>')
def take_test(filename):
    original_test = load_test(filename)
    session['current_test'] = filename
    display_test = prepare_test_for_display(original_test)
    return render_template('test.html', test=display_test, enumerate=enumerate)

@app.route('/submit/<path:filename>', methods=['POST'])
def submit_test(filename):
    original_test = load_test(filename)
    user_answers = {}
    score = 0
    total = len(original_test['questions'])

    for question in original_test['questions']:
        qid = str(question['id'])
        qtype = question.get('type', 'single_choice')
        correct_value = question['correct']

        if qtype == 'single_choice':
            selected_text = request.form.get(f'q{qid}')
            user_answers[qid] = selected_text
            if selected_text and selected_text.strip() == correct_value.strip():
                score += 1
        elif qtype == 'multiple_choice':
            selected_texts = request.form.getlist(f'q{qid}')
            user_answers[qid] = selected_texts
            if set(s.strip() for s in selected_texts) == set(s.strip() for s in correct_value):
                score += 1
        elif qtype == 'open_text':
            answer_text = request.form.get(f'q{qid}', '').strip()
            user_answers[qid] = answer_text
            if answer_text.lower() == correct_value.strip().lower():
                score += 1

    session.pop('current_test', None)
    return render_template('result.html',
                           test=original_test,
                           user_answers=user_answers,
                           score=score,
                           total=total)

@app.route('/check_answer/<path:filename>/<int:question_id>', methods=['POST'])
def check_answer(filename, question_id):
    original_test = load_test(filename)
    question = next((q for q in original_test['questions'] if q['id'] == question_id), None)
    if not question:
        return jsonify({'error': 'Question not found'}), 404

    qtype = question.get('type', 'single_choice')
    correct_value = question['correct']
    is_correct = False
    user_answer = None

    if qtype == 'single_choice':
        selected = request.form.get('answer')
        user_answer = selected
        if selected and selected.strip() == correct_value.strip():
            is_correct = True
    elif qtype == 'multiple_choice':
        selected_list = request.form.getlist('answer')
        user_answer = selected_list
        if set(s.strip() for s in selected_list) == set(s.strip() for s in correct_value):
            is_correct = True
    elif qtype == 'open_text':
        answer_text = request.form.get('answer', '').strip()
        user_answer = answer_text
        if answer_text.lower() == correct_value.strip().lower():
            is_correct = True

    return jsonify({
        'correct': is_correct,
        'user_answer': user_answer,
        'correct_answer': correct_value
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)