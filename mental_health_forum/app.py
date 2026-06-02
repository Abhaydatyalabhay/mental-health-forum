import random
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from textblob import TextBlob
import google.generativeai as genai
from itsdangerous import URLSafeTimedSerializer
from flask_mail import Mail, Message
from datetime import datetime
import os

# =========================
# GEMINI API
# =========================
import os

genai.configure(
    api_key=os.environ.get("GEMINI_API_KEY")
)
model = genai.GenerativeModel('gemini-2.5-flash')

# =========================
# APP CONFIG
# =========================
app = Flask(__name__)
app.config['SECRET_KEY'] = 'mentalhealthsecret'
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# =========================
# MAIL CONFIG
# =========================
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = 'YOUR_EMAIL@gmail.com'
mail = Mail(app)

# =========================
# DATABASE
# =========================
DB = SQLAlchemy(app)

# =========================
# LOGIN MANAGER
# =========================
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = ""

# =========================
# TOKEN SERIALIZER
# =========================
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

# =========================
# MODELS
# =========================
class User(UserMixin, DB.Model):
    id = DB.Column(DB.Integer, primary_key=True)
    username = DB.Column(DB.String(100), unique=True)
    email = DB.Column(DB.String(100), unique=True)
    password = DB.Column(DB.String(200))

class Post(DB.Model):
    id = DB.Column(DB.Integer, primary_key=True)
    title = DB.Column(DB.String(200))
    content = DB.Column(DB.Text)
    category = DB.Column(DB.String(100))
    created_at = DB.Column(DB.DateTime, default=datetime.utcnow)
    user_id = DB.Column(DB.Integer, DB.ForeignKey('user.id'))
    
    user = DB.relationship('User', backref='posts')
    comments = DB.relationship('Comment', backref='post', lazy=True, cascade="all, delete")
    support = DB.relationship('Support', backref='post', lazy=True, cascade="all, delete")

class Comment(DB.Model):
    id = DB.Column(DB.Integer, primary_key=True)
    comment = DB.Column(DB.Text, nullable=False)
    created_at = DB.Column(DB.DateTime, default=datetime.utcnow)
    post_id = DB.Column(DB.Integer, DB.ForeignKey('post.id'), nullable=False)
    user_id = DB.Column(DB.Integer, DB.ForeignKey('user.id'), nullable=False)
    
    user = DB.relationship('User', backref='user_comments')

class Support(DB.Model):
    id = DB.Column(DB.Integer, primary_key=True)
    user_id = DB.Column(DB.Integer, DB.ForeignKey('user.id'))
    post_id = DB.Column(DB.Integer, DB.ForeignKey('post.id'))

# =========================
# LOGIN LOADER
# =========================
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# =========================
# HOME
# =========================
@app.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('welcome.html')

# =========================
# REGISTER
# =========================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash("Email already registered")
            return redirect(url_for('register'))

        new_user = User(username=username, email=email, password=password)
        DB.session.add(new_user)
        DB.session.commit()
        flash("Registration Successful")
        return redirect(url_for('login'))

    return render_template('register.html')

# =========================
# LOGIN
# =========================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash("Invalid Email or Password")

    return render_template('login.html')

# =========================
# FORGOT PASSWORD
# =========================
@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        user = User.query.filter_by(email=email).first()

        if user:
            token = serializer.dumps(email, salt='password-reset')
            reset_link = url_for('reset_password', token=token, _external=True)
            msg = Message('Password Reset Request', recipients=[email])
            msg.body = f"Hello {user.username},\n\nClick below to reset password:\n\n{reset_link}"
            mail.send(msg)
            flash("Password reset link sent")
            return redirect(url_for('login'))

        flash("Email not found")
    return render_template('forgot_password.html')

# =========================
# RESET PASSWORD
# =========================
@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        email = serializer.loads(token, salt='password-reset', max_age=300)
    except Exception as e:
        return f"Invalid or expired link: {e}"

    user = User.query.filter_by(email=email).first()
    if not user:
        return "User not found"

    if request.method == 'POST':
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        if password != confirm_password:
            flash("Passwords do not match")
            return redirect(request.url)

        user.password = generate_password_hash(password)
        DB.session.commit()
        flash("Password updated successfully")
        return redirect(url_for('login'))

    return render_template('reset_password.html')

# =========================
# DASHBOARD
# =========================
@app.route('/dashboard')
@login_required
def dashboard():
    my_posts = Post.query.filter_by(user_id=current_user.id).all()
    return render_template('dashboard.html', my_posts=my_posts)

# =========================
# ABOUT US
# =========================
@app.route('/about_us')
@login_required
def about_us():
    return render_template('about_us.html')

# =========================
# CLINICAL RESOURCES (NEW)
# =========================
@app.route('/resources')
@login_required
def resources():
    # Place your premium resource materials template here
    return render_template('resources.html')

# =========================
# STRESS MANAGEMENT
# =========================
@app.route('/stress-management')
@login_required
def stress_management():
    return render_template('stress.html')

# =========================
# ANXIETY SUPPORT
# =========================
@app.route('/anxiety-support')
@login_required
def anxiety_support():
    return render_template('anxiety.html')

# =========================
# SELF CARE
# =========================
@app.route('/self-care')
@login_required
def self_care():
    return render_template('self_care.html')

# =========================
# INTERACTIVE DIAGNOSTIC (NEW)
# =========================
@app.route('/assessment')
@login_required
def assessment():
    # Map psychological baselines, surveys, or tracking quizzes here
    return render_template('assessment.html')

# =========================
# COMMUNITY
# =========================
@app.route('/community')
@login_required
def community():
    posts = Post.query.filter(Post.user_id != current_user.id).all()
    return render_template('community.html', posts=posts)

# =========================
# CHATBOT
# =========================
@app.route('/chatbot', methods=['GET', 'POST'])
@login_required
def chatbot():
    if 'chat_history' not in session:
        session['chat_history'] = []

    bot_response = ""
    user_message = ""

    if request.method == 'POST':
        user_message = request.form['message']
        history = session['chat_history']
        history.append(f"User: {user_message}")
        recent_history = history[-10:]

        prompt = f"""
You are a mental health AI chatbot.

Conversation:
{recent_history}

User: {user_message}

AI:
"""
        try:
            response = model.generate_content(prompt)
            bot_response = response.text.strip()
        except Exception as e:
            bot_response = f"Error: {str(e)}"

        history.append(f"AI: {bot_response}")
        session['chat_history'] = history

    return render_template('chatbot.html', bot_response=bot_response, user_message=user_message)

# =========================
# CREATE POST
# =========================
@app.route('/create_post', methods=['GET', 'POST'])
@login_required
def create_post():
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        category = request.form['category']

        post = Post(title=title, content=content, category=category, user_id=current_user.id)
        DB.session.add(post)
        DB.session.commit()
        flash("Post created successfully")
        return redirect(url_for('dashboard'))

    return render_template('create_post.html')

# =========================
# MY POSTS
# =========================
@app.route('/my_posts')
@login_required
def my_posts():
    posts = Post.query.filter_by(user_id=current_user.id).order_by(Post.created_at.desc()).all()
    return render_template('my_posts.html', my_posts=posts)

# =========================
# SUPPORT POST
# =========================
@app.route('/support/<int:post_id>', methods=['POST'])
@login_required
def support_post(post_id):
    existing = Support.query.filter_by(user_id=current_user.id, post_id=post_id).first()
    if not existing:
        support = Support(user_id=current_user.id, post_id=post_id)
        DB.session.add(support)
        DB.session.commit()

    return redirect(url_for('community'))

# =========================
# ADD COMMENT
# =========================
@app.route('/add_comment/<int:post_id>', methods=['POST'])
@login_required
def add_comment(post_id):
    comment_text = request.form.get('comment')
    if comment_text and comment_text.strip():
        new_comment = Comment(comment=comment_text, post_id=post_id, user_id=current_user.id)
        DB.session.add(new_comment)
        DB.session.commit()

    return redirect(url_for('community'))

# =========================
# Appointment
# =========================

@app.route('/appointment')
def appointment():
    return render_template('appointment.html')

# =========================
# Helpline
# =========================
@app.route('/helpline')
def helpline():
    return render_template('helpline.html')

# =========================
# LOGOUT
# =========================
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

# =========================
# MAIN
# =========================
with app.app_context():
    DB.create_all()

if __name__ == '__main__':
    app.run(debug=True)