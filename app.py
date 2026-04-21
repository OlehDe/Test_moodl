import json
import os
from glob import glob
from flask import Flask, render_template, request, session, redirect, url_for, jsonify

app = Flask(__name__)
app.secret_key = 'your-secret-key-here-change-in-production'

TESTS_DIR = 'tests'

def load_test(filename):
    path = os.path.join(TESTS_DIR, filename)
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

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
    test_data = load_test(filename)
    session['current_test'] = filename
    # Зберігаємо відповіді користувача (для множинного вибору - списки)
    session['answers'] = {}
    return render_template('test.html', test=test_data, enumerate=enumerate)

@app.route('/submit/<filename>', methods=['POST'])
def submit_test(filename):
    test_data = load_test(filename)
    user_answers = {}
    score = 0
    total = len(test_data['questions'])

    for question in test_data['questions']:
        qid = str(question['id'])
        qtype = question.get('type', 'single_choice')
        if qtype == 'single_choice':
            selected = request.form.get(f'q{qid}')
            user_answers[qid] = int(selected) if selected is not None else None
            if selected is not None and int(selected) == question['correct']:
                score += 1
        elif qtype == 'multiple_choice':
            selected_list = request.form.getlist(f'q{qid}')
            selected_indices = [int(x) for x in selected_list] if selected_list else []
            user_answers[qid] = selected_indices
            correct_set = set(question['correct'])
            if set(selected_indices) == correct_set:
                score += 1
        elif qtype == 'open_text':
            answer_text = request.form.get(f'q{qid}', '').strip()
            user_answers[qid] = answer_text
            correct_answer = question['correct'].strip()
            if answer_text.lower() == correct_answer.lower():
                score += 1

    session.pop('current_test', None)
    session.pop('answers', None)

    return render_template('result.html',
                           test=test_data,
                           user_answers=user_answers,
                           score=score,
                           total=total)

@app.route('/check_answer/<filename>/<int:question_id>', methods=['POST'])
def check_answer(filename, question_id):
    test_data = load_test(filename)
    question = next((q for q in test_data['questions'] if q['id'] == question_id), None)
    if not question:
        return jsonify({'error': 'Question not found'}), 404

    qtype = question.get('type', 'single_choice')
    correct = False
    correct_answer = None
    user_answer = None

    if qtype == 'single_choice':
        selected = request.form.get('answer')
        if selected is not None:
            selected = int(selected)
            user_answer = selected
            correct = (selected == question['correct'])
            correct_answer = question['correct']
    elif qtype == 'multiple_choice':
        selected_list = request.form.getlist('answer')
        selected_indices = [int(x) for x in selected_list] if selected_list else []
        user_answer = selected_indices
        correct_set = set(question['correct'])
        correct = (set(selected_indices) == correct_set)
        correct_answer = question['correct']
    elif qtype == 'open_text':
        answer_text = request.form.get('answer', '').strip()
        user_answer = answer_text
        correct_answer = question['correct'].strip()
        correct = (answer_text.lower() == correct_answer.lower())

    return jsonify({
        'correct': correct,
        'user_answer': user_answer,
        'correct_answer': correct_answer
    })

if __name__ == '__main__':
    app.run(debug=True)