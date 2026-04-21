import json
import os
import random
from glob import glob
from flask import Flask, render_template, request, session, redirect, url_for, jsonify

app = Flask(__name__)
app.secret_key = 'your-secret-key-here-change-in-production'

TESTS_DIR = 'tests'

def load_test(filename):
    """Завантажує оригінальний JSON тесту."""
    path = os.path.join(TESTS_DIR, filename)
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def prepare_test_for_display(test_data):
    """
    Створює глибоку копію тесту.
    Якщо 'setting' == 'random', то перемішує порядок питань
    і варіанти відповідей для типів single_choice / multiple_choice.
    В іншому випадку порядок залишається незмінним.
    """
    import copy
    test_copy = copy.deepcopy(test_data)

    # Перевіряємо, чи ввімкнено випадкове перемішування
    is_random = test_copy.get('setting') == 'random'

    if is_random:
        # Перемішуємо порядок питань
        random.shuffle(test_copy['questions'])

    # Обробляємо кожне питання
    for q in test_copy['questions']:
        qtype = q.get('type', 'single_choice')
        # Перемішуємо варіанти лише для запитань із вибором і тільки якщо is_random = True
        if is_random and qtype in ('single_choice', 'multiple_choice'):
            random.shuffle(q['options'])

    return test_copy

def get_available_tests():
    tests = []
    for filepath in glob(os.path.join(TESTS_DIR, '*.json')):
        filename = os.path.basename(filepath)
        try:
            data = load_test(filename)
            title = data.get('title', filename)
        except:
            title = filename
        tests.append({'filename': filename, 'title': title})
    return tests

@app.route('/')
def index():
    tests = get_available_tests()
    return render_template('index.html', tests=tests)

@app.route('/test/<filename>')
def take_test(filename):
    original_test = load_test(filename)
    session['current_test'] = filename
    # Готуємо тест для відображення (перемішуємо опції)
    display_test = prepare_test_for_display(original_test)
    return render_template('test.html', test=display_test, enumerate=enumerate)

@app.route('/submit/<filename>', methods=['POST'])
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

@app.route('/check_answer/<filename>/<int:question_id>', methods=['POST'])
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
    app.run(debug=True)