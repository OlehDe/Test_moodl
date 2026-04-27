import json
import os
import random
from glob import glob
from flask import Flask, render_template, request, session, url_for, jsonify

app = Flask(__name__)
app.secret_key = 'your-secret-key-here-change-in-production'

TEST_DIRS = ['tests', 'sort']

def get_all_test_files():
    tests = []
    for folder in TEST_DIRS:
        if not os.path.isdir(folder):
            continue
        pattern = os.path.join(folder, '**', '*.json')
        for filepath in glob(pattern, recursive=True):
            rel_path = os.path.relpath(filepath)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    title = data.get('title', os.path.basename(filepath))
                    is_random = data.get('setting') == 'random'
            except Exception:
                title = os.path.basename(filepath)
                is_random = False
            tests.append({
                'path': rel_path,
                'title': title,
                'is_random': is_random
            })
    return tests

@app.route('/')
def index():
    all_tests = get_all_test_files()
    normal_tests = [t for t in all_tests if not t['is_random']]
    random_tests = [t for t in all_tests if t['is_random']]
    return render_template('index.html',
                           normal_tests=normal_tests,
                           random_tests=random_tests)

def load_test(rel_path):
    norm_path = os.path.normpath(rel_path)
    abs_path = os.path.abspath(norm_path)
    allowed = False
    for folder in TEST_DIRS:
        abs_folder = os.path.abspath(folder)
        if abs_path.startswith(abs_folder):
            allowed = True
            break
    if not allowed:
        raise ValueError(f"Недозволений шлях: {rel_path}")
    with open(norm_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def prepare_test_for_display(test_data):
    import copy
    test_copy = copy.deepcopy(test_data)
    is_random = test_copy.get('setting') == 'random'
    if is_random:
        random.shuffle(test_copy['questions'])
    for q in test_copy['questions']:
        qtype = q.get('type', 'single_choice')
        if is_random and qtype in ('single_choice', 'multiple_choice'):
            random.shuffle(q['options'])
        if is_random and qtype == 'matching':
            random.shuffle(q['pairs'])
    return test_copy

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
        correct_value = question.get('correct', None)

        if qtype == 'single_choice':
            selected = request.form.get(f'q{qid}')
            user_answers[qid] = selected
            if selected and correct_value and selected.strip() == correct_value.strip():
                score += 1
        elif qtype == 'multiple_choice':
            selected_list = request.form.getlist(f'q{qid}')
            user_answers[qid] = selected_list
            if correct_value and set(s.strip() for s in selected_list) == set(s.strip() for s in correct_value):
                score += 1
        elif qtype == 'open_text':
            answer = request.form.get(f'q{qid}', '').strip()
            user_answers[qid] = answer
            if correct_value and answer.lower() == correct_value.strip().lower():
                score += 1
        elif qtype == 'matching':
            pairs = question['pairs']
            all_correct = True
            user_pairs = {}
            # Збираємо всі відповіді для цього питання з форми
            for pair in pairs:
                left_key = pair['left']
                # name поля в html має вигляд q{id}_{left} – змінимо генерацію нижче
                selected_right = request.form.get(f'q{qid}_{left_key}')
                user_pairs[left_key] = selected_right
                if selected_right != pair['right']:
                    all_correct = False
            user_answers[qid] = user_pairs
            if all_correct:
                score += 1

    current_test_filename = filename
    session.pop('current_test', None)
    return render_template('result.html',
                           test=original_test,
                           user_answers=user_answers,
                           score=score,
                           total=total,
                           filename=current_test_filename)

@app.route('/check_answer/<path:filename>/<int:question_id>', methods=['POST'])
def check_answer(filename, question_id):
    original_test = load_test(filename)
    question = next((q for q in original_test['questions'] if q['id'] == question_id), None)
    if not question:
        return jsonify({'error': 'Question not found'}), 404

    qtype = question.get('type', 'single_choice')
    correct_value = question.get('correct', None)
    is_correct = False
    user_answer = None

    if qtype == 'single_choice':
        selected = request.form.get('answer')
        user_answer = selected
        if selected and correct_value and selected.strip() == correct_value.strip():
            is_correct = True
    elif qtype == 'multiple_choice':
        selected_list = request.form.getlist('answer')
        user_answer = selected_list
        if correct_value and set(s.strip() for s in selected_list) == set(s.strip() for s in correct_value):
            is_correct = True
    elif qtype == 'open_text':
        answer = request.form.get('answer', '').strip()
        user_answer = answer
        if correct_value and answer.lower() == correct_value.strip().lower():
            is_correct = True
    elif qtype == 'matching':
        data = request.get_json()
        if not data or 'answers' not in data:
            return jsonify({'error': 'Invalid data'}), 400
        user_answers = data['answers']  # словник {left: selected_right}
        pairs = question['pairs']
        all_correct = True
        for pair in pairs:
            left = pair['left']
            correct_right = pair['right']
            if left not in user_answers or user_answers[left] != correct_right:
                all_correct = False
                break
        is_correct = all_correct

    return jsonify({
        'correct': is_correct,
        'user_answer': user_answer,
        'correct_answer': correct_value if correct_value else ''
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)