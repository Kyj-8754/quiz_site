from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, RadioField
from wtforms.validators import DataRequired, Length
import pandas as pd
import sqlite3
import os
import random
import re

# print("Starting Flask app...") # Removed for deployment
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here'
app.config['DATABASE'] = 'database.db'
app.config['QUIZ_FILE'] = 'quiz.xlsx'

if not os.path.exists(app.config['QUIZ_FILE']):
    try:
        # Create a dummy quiz.xlsx file if it doesn't exist
        print("Attempting to create dummy quiz.xlsx...")
        dummy_data = {'문제': ['다음 중 파이썬의 자료형이 아닌 것은?', 'Flask의 기본 포트 번호는?', 'HTML에서 제목을 나타내는 태그는?', 'CSS에서 배경색을 지정하는 속성은?', 'Git에서 변경사항을 저장하는 명령어는?'],
                      '보기A': ['List', '5000', '<p>', 'color', 'git pull'],
                      '보기B': ['Tuple', '8000', '<h1>', 'background-color', 'git push'],
                      '보기C': ['Dictionary', '8080', '<a>', 'font-size', 'git commit'],
                      '보기D': ['Array', '3000', '<div>', 'text-align', 'git branch'],
                      '정답': ['D', 'A', 'B', 'B', 'C'],
                      '해설': ['파이썬에는 Array 자료형이 직접적으로 존재하지 않습니다. List가 가장 유사합니다.', 'Flask의 기본 개발 서버 포트는 5000번입니다.', '<h1> 태그는 가장 큰 제목을 나타냅니다.', 'background-color 속성은 요소의 배경색을 지정합니다.', 'git commit은 변경사항을 로컬 저장소에 저장하는 명령어입니다.']}
        pd.DataFrame(dummy_data).to_excel(app.config['QUIZ_FILE'], index=False)
        # print("Dummy quiz.xlsx created successfully.") # Removed for deployment
    except Exception as e:
        # print(f"Error creating dummy quiz.xlsx: {e}") # Removed for deployment
        pass # Consider more robust error handling for production


class LoginForm(FlaskForm):
    username = StringField('이름', validators=[DataRequired()])
    password = PasswordField('비밀번호', validators=[DataRequired()])
    submit = SubmitField('로그인')

class QuizForm(FlaskForm):
    answer = RadioField('정답 선택', validators=[DataRequired()], choices=[('A', 'A'), ('B', 'B'), ('C', 'C'), ('D', 'D')])
    submit = SubmitField('다음 문제')

def get_db():
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with app.app_context():
        db = get_db()
        with open(os.path.join(app.root_path, 'schema.sql'), 'r', encoding='utf-8') as f:
            db.cursor().executescript(f.read())
        db.commit()


@app.route('/')
def index():
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password)).fetchone()
        if user:
            session['logged_in'] = True
            session['username'] = username
            session['quiz_data'] = []
            session['current_question_index'] = 0
            session['score'] = 0
            flash('로그인 성공!', 'success')
            return redirect(url_for('quiz'))
        else:
            flash('이름 또는 비밀번호가 올바르지 않습니다.', 'danger')
    return render_template('login.html', form=form)


@app.route('/quiz', methods=['GET', 'POST'])
def quiz():
    form = QuizForm()
    if 'logged_in' not in session or not session['logged_in']:
        flash('로그인이 필요합니다.', 'danger')
        return redirect(url_for('login'))

    if not session.get('quiz_data'):
        # Load quiz data and shuffle for the first time
        try:
            df = pd.read_excel(app.config['QUIZ_FILE'])
            # print("Columns from quiz.xlsx before standardization:", df.columns) # Removed for deployment

            # Standardize column names to be all uppercase
            df.columns = [col.upper() for col in df.columns]
            # print("Columns from quiz.xlsx before standardization:", df.columns) # Removed for deployment
            # print("Columns from quiz.xlsx after standardization:", df.columns) # Removed for deployment

            # Apply clean_option_text to all option columns
            for col in ['보기A', '보기B', '보기C', '보기D']:
                if col in df.columns:
                    df[col] = df[col].apply(clean_option_text)

            session['quiz_data'] = df.to_dict(orient='records')
            random.shuffle(session['quiz_data'])
            session['quiz_data'] = session['quiz_data'][:5] # Limit to 5 questions
            session['current_question_index'] = 0
            session['score'] = 0
        except Exception as e:
            flash(f'퀴즈 파일을 로드하는 데 실패했습니다: {e}', 'danger')
            return redirect(url_for('login'))

    current_question_index = session.get('current_question_index', 0)
    quiz_data = session.get('quiz_data', [])

    if current_question_index >= len(quiz_data):
        return redirect(url_for('result'))

    current_question = quiz_data[current_question_index]

    if form.validate_on_submit():
        selected_answer = form.answer.data
        correct_answer = current_question['정답'][0].upper() # Extract first character and convert to uppercase for comparison

        # Save the selected answer for the current question
        session['quiz_data'][current_question_index]['selected_answer'] = selected_answer

        if selected_answer == correct_answer:
            session['score'] += 1

        session['current_question_index'] += 1
        return redirect(url_for('quiz'))

    # Dynamically set choices for the radio buttons
    form.answer.choices = [
        ('A', f"A. {clean_option_text(current_question['보기A'])}"),
        ('B', f"B. {clean_option_text(current_question['보기B'])}"),
        ('C', f"C. {clean_option_text(current_question['보기C'])}"),
        ('D', f"D. {clean_option_text(current_question['보기D'])}")
    ]

    return render_template('quiz.html', form=form, question=current_question, question_num=current_question_index + 1, total_questions=len(quiz_data))


@app.route('/result')
def result():
    if 'logged_in' not in session or not session['logged_in']:
        flash('로그인이 필요합니다.', 'danger')
        return redirect(url_for('login'))
    
    quiz_data = session.get('quiz_data', [])
    score = session.get('score', 0)
    total_questions = len(quiz_data)

    # Apply clean_option_text to the '정답' column before passing to template
    for q in quiz_data:
        if '정답' in q and isinstance(q['정답'], str) and q['정답']:
            # Extract only the answer key (A, B, C, D) and convert to uppercase
            cleaned_answer = clean_option_text(q['정답'])
            if cleaned_answer:
                q['정답'] = cleaned_answer[0].upper()
            else:
                q['정답'] = '' # Handle case where answer becomes empty after cleaning
        else:
            q['정답'] = '' # Ensure '정답' key exists and has a default value

    return render_template('result.html', score=score, total_questions=total_questions, quiz_data=quiz_data)


@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('username', None)
    session.pop('quiz_data', None)
    session.pop('current_question_index', None)
    session.pop('score', None)
    flash('로그아웃 되었습니다.', 'info')
    return redirect(url_for('login'))

@app.route('/reset_quiz')
def reset_quiz():
    session['quiz_data'] = []
    session['current_question_index'] = 0
    session['score'] = 0
    flash('새로운 퀴즈를 시작합니다!', 'info')
    return redirect(url_for('quiz'))

def clean_option_text(text):
    if not isinstance(text, str):
        return str(text).strip()
    
    cleaned_text = str(text).strip()
    
    # Remove any leading single letter (case-insensitive) followed by '.' and optional space
    # This handles 'A. text', 'a. text', 'A.a. text' scenarios
    # The '+' after (\.?\s*) ensures it handles multiple prefixes like 'A.a. '
    cleaned_text = re.sub(r"^([a-zA-Z]\.?\s*)+", "", cleaned_text).strip()
    
    return cleaned_text

if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True)
