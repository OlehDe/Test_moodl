import json
import os
import random
import copy
from glob import glob
from flask import Flask, render_template, request, session, url_for, jsonify
from markupsafe import Markup

app = Flask(__name__)
app.secret_key = 'your-secret-key-here-change-in-production'

# Забороняємо кешування, щоб браузер не зберігав старі відповіді
@app.after_request
def add_no_cache(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response


@app.template_filter('shuffle')
def shuffle_filter(lst):
    if not isinstance(lst, list):
        return lst
    new_lst = lst[:]
    random.shuffle(new_lst)
    return new_lst


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
                    category = data.get('category', 'Без категорії')
                    is_random = data.get('setting') == 'random'
                    if 'sources' in data:
                        questions_count = sum(source.get('count', 0) for source in data['sources'])
                        max_score = sum(source.get('count', 0) * source.get('weight', 1) for source in data['sources'])
                    else:
                        questions_count = len(data.get('questions', []))
                        max_score = None
            except Exception:
                title = os.path.basename(filepath)
                category = 'Без категорії'
                is_random = False
                questions_count = 0
                max_score = None
            tests.append({
                'path': rel_path,
                'title': title,
                'category': category,
                'is_random': is_random,
                'questions_count': questions_count,
                'max_score': max_score
            })
    return tests


@app.route('/')
def index():
    # Очищаємо будь-які залишки попереднього тесту
    session.pop('current_test', None)
    session.pop('current_recipe', None)

    all_tests = get_all_test_files()
    normal_tests = [t for t in all_tests if not t['is_random']]
    random_tests = [t for t in all_tests if t['is_random']]
    return render_template('index.html',
                           normal_tests=normal_tests,
                           random_tests=random_tests)


# ---------------------------------------------------------------------------
# Підтримка картинок (<img ...>) у питаннях і варіантах відповідей
# ---------------------------------------------------------------------------

def _mark_html(value):
    """Рядки, що починаються з <img, позначає як безпечний HTML (Markup),
    щоб Jinja не екранувала теги й картинка відображалась.
    Подвійні лапки міняє на одинарні, щоб рядок можна було вставляти
    і в текст, і в атрибут value="..." без поломки розмітки."""
    if isinstance(value, str) and value.lstrip().startswith('<img'):
        return Markup(value.replace('"', "'"))
    return value


def _mark_questions(data):
    """Проходить по всіх питаннях і позначає HTML-картинки як безпечні."""
    for q in data.get('questions', []):
        if 'text' in q:
            q['text'] = _mark_html(q['text'])
        if isinstance(q.get('options'), list):
            q['options'] = [_mark_html(o) for o in q['options']]
        c = q.get('correct')
        if isinstance(c, list):
            q['correct'] = [_mark_html(x) for x in c]
        else:
            q['correct'] = _mark_html(c)
    return data


def _load_json_file(rel_path):
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
    if not os.path.isfile(norm_path):
        raise FileNotFoundError(f"Файл не знайдено: {norm_path}")
    with open(norm_path, 'r', encoding='utf-8') as f:
        return _mark_questions(json.load(f))


def _is_meta_test(test_data):
    return 'sources' in test_data


def _load_meta_test(meta_data):
    """Генерує тест із джерел і повертає разом з рецептом (recipe)."""
    questions = []
    recipe = []   # збережемо, які питання брали
    for source in meta_data['sources']:
        source_file = source['file']
        required = source['count']
        weight = source.get('weight', 1)
        source_data = _load_json_file(source_file)
        source_questions = source_data.get('questions', [])
        chosen = random.sample(range(len(source_questions)), required)  # індекси
        recipe.append({'file': source_file, 'indices': chosen, 'weight': weight})
        for idx in chosen:
            q = copy.deepcopy(source_questions[idx])
            q['weight'] = weight
            questions.append(q)

    for idx, q in enumerate(questions, start=1):
        q['id'] = idx

    return {
        'title': meta_data.get('title', 'Mixed Test'),
        'questions': questions,
        'setting': meta_data.get('setting', ''),
        'passing_score': meta_data.get('passing_score', None),
        'max_score': sum(source['count'] * source.get('weight', 1) for source in meta_data['sources']),
        'recipe': recipe   # додаємо рецепт у тест
    }


def _rebuild_from_recipe(recipe):
    """Відновлює тест за збереженим рецептом."""
    questions = []
    for entry in recipe:
        source_file = entry['file']
        indices = entry['indices']
        weight = entry['weight']
        source_data = _load_json_file(source_file)
        source_questions = source_data.get('questions', [])
        for idx in indices:
            q = copy.deepcopy(source_questions[idx])
            q['weight'] = weight
            questions.append(q)

    for idx, q in enumerate(questions, start=1):
        q['id'] = idx

    # Для перевірки потрібні лише питання; метадані беруться з meta-файлу
    # у get_current_test().
    return {'questions': questions}


def load_test(rel_path):
    test_data = _load_json_file(rel_path)
    if _is_meta_test(test_data):
        return _load_meta_test(test_data)
    return test_data


def prepare_test_for_display(test_data):
    test_copy = copy.deepcopy(test_data)
    is_random = test_copy.get('setting') == 'random'
    if is_random:
        random.shuffle(test_copy['questions'])
    for q in test_copy['questions']:
        qtype = q.get('type', 'single_choice')
        if is_random and qtype in ('single_choice', 'multiple_choice', 'multi_select'):
            random.shuffle(q['options'])
        if qtype == 'matching':
            random.shuffle(q['pairs'])
            # distractors — зайві праві варіанти без пари (необов'язкове поле)
            rights = list({p['right'] for p in q['pairs']} | set(q.get('distractors', [])))
            random.shuffle(rights)
            q['shuffled_rights'] = rights
    # Не показуємо recipe клієнту
    test_copy.pop('recipe', None)
    return test_copy


def get_current_test():
    """Отримує поточний тест: відновлює з рецепту або завантажує з файлу."""
    filename = session.get('current_test')
    if not filename:
        return None
    recipe = session.get('current_recipe')
    if recipe:
        # Відновлюємо питання за рецептом
        rebuilt = _rebuild_from_recipe(recipe)
        # Метадані (title, passing_score, max_score) беремо з оригінального meta-файлу
        meta_data = _load_json_file(filename)
        full_test = {
            'title': meta_data.get('title', 'Test'),
            'questions': rebuilt['questions'],
            'setting': meta_data.get('setting', ''),
            'passing_score': meta_data.get('passing_score'),
            'max_score': sum(source['count'] * source.get('weight', 1) for source in meta_data.get('sources', []))
        }
        return full_test
    else:
        # Звичайний тест (не meta)
        return load_test(filename)


@app.route('/test/<path:filename>')
def take_test(filename):
    original_test = load_test(filename)
    # Зберігаємо в сесії лише шлях та рецепт (якщо є)
    session['current_test'] = filename
    session['current_recipe'] = original_test.get('recipe')  # для звичайних тестів буде None
    display_test = prepare_test_for_display(original_test)
    return render_template('test.html', test=display_test, enumerate=enumerate)


@app.route('/submit/<path:filename>', methods=['POST'])
def submit_test(filename):
    original_test = get_current_test()
    if not original_test:
        return "Сесію втрачено. Будь ласка, почніть тест заново.", 400

    user_answers = {}
    score = 0
    total = len(original_test['questions'])
    max_score = original_test.get('max_score', total)
    passing_score = original_test.get('passing_score', None)

    for question in original_test['questions']:
        qid = str(question['id'])
        qtype = question.get('type', 'single_choice')
        correct_value = question.get('correct', None)
        weight = question.get('weight', 1)

        if qtype == 'single_choice':
            selected = request.form.get(f'q{qid}')
            # Відповідь з форми — звичайний рядок; позначаємо як HTML,
            # якщо це картинка, щоб у результатах вона теж відобразилась
            user_answers[qid] = _mark_html(selected)
            if selected and correct_value and selected.strip() == correct_value.strip():
                score += weight
        elif qtype == 'multiple_choice':
            selected_list = request.form.getlist(f'q{qid}')
            user_answers[qid] = [_mark_html(s) for s in selected_list]
            if correct_value and set(s.strip() for s in selected_list) == set(s.strip() for s in correct_value):
                score += weight
        elif qtype == 'open_text':
            answer = request.form.get(f'q{qid}', '').strip()
            user_answers[qid] = answer
            if correct_value and answer.lower() == correct_value.strip().lower():
                score += weight
        elif qtype == 'matching':
            pairs = question['pairs']
            all_correct = True
            user_pairs = {}
            for pair in pairs:
                left_key = pair['left']
                selected_right = request.form.get(f'q{qid}_{left_key}')
                user_pairs[left_key] = selected_right
                if selected_right != pair['right']:
                    all_correct = False
            user_answers[qid] = user_pairs
            if all_correct:
                score += weight
        elif qtype == 'multi_select':
            selected_list = request.form.getlist(f'q{qid}')
            user_answers[qid] = [_mark_html(s) for s in selected_list]
            select_count = question.get('select_count', len(correct_value) if correct_value else 0)
            if correct_value and len(selected_list) == select_count \
                    and set(s.strip() for s in selected_list) == set(s.strip() for s in correct_value):
                score += weight

    # Очищення сесії після завершення
    session.pop('current_test', None)
    session.pop('current_recipe', None)

    return render_template('result.html',
                           test=original_test,
                           user_answers=user_answers,
                           score=score,
                           total=total,
                           max_score=max_score,
                           passing_score=passing_score,
                           filename=filename)


@app.route('/check_answer/<path:filename>/<int:question_id>', methods=['POST'])
def check_answer(filename, question_id):
    original_test = get_current_test()
    if not original_test:
        return jsonify({'error': 'Session lost. Please restart the test.'}), 400

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
        user_answers = data['answers']
        pairs = question['pairs']
        all_correct = True
        correct_pairs_list = []
        for pair in pairs:
            left = pair['left']
            correct_right = pair['right']
            correct_pairs_list.append(f"{left} – {correct_right}")
            if left not in user_answers or user_answers[left] != correct_right:
                all_correct = False
        is_correct = all_correct
        user_answer = user_answers
        correct_value = "; ".join(correct_pairs_list)
    elif qtype == 'multi_select':
        selected_list = request.form.getlist('answer')
        user_answer = selected_list
        select_count = question.get('select_count', len(correct_value) if correct_value else 0)
        if correct_value and len(selected_list) == select_count \
                and set(s.strip() for s in selected_list) == set(s.strip() for s in correct_value):
            is_correct = True
        correct_value = ', '.join(correct_value) if correct_value else ''

    # Markup — підклас str, тому jsonify віддає його як звичайний рядок з тегом <img>
    return jsonify({
        'correct': is_correct,
        'user_answer': user_answer,
        'correct_answer': correct_value if correct_value else ''
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)