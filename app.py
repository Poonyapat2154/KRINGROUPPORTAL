import os
from datetime import datetime, date
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'kringroup-secret-key')
db_url = os.environ.get('DATABASE_URL', 'sqlite:///kringroup_portal.db')
if db_url.startswith('postgres://'):
    db_url = db_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), default='employee')
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    department = db.relationship('Department')
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

class Department(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    description = db.Column(db.Text)

class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_name = db.Column(db.String(160), nullable=False)
    company = db.Column(db.String(160))
    contact_person = db.Column(db.String(160))
    email = db.Column(db.String(160))
    phone = db.Column(db.String(80))
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=False)
    client_date = db.Column(db.Date, default=date.today)
    status = db.Column(db.String(40), default='New')
    notes = db.Column(db.Text)
    attachment = db.Column(db.String(255))
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    updated_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    department = db.relationship('Department')
    created_by = db.relationship('User', foreign_keys=[created_by_id])
    updated_by = db.relationship('User', foreign_keys=[updated_by_id])

class Activity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(255), nullable=False)
    details = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User')

class Bulletin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.relationship('User')

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'))
    due_date = db.Column(db.Date)
    status = db.Column(db.String(40), default='Open')
    assigned_to = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    department = db.relationship('Department')

class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(80), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.relationship('User')

@login_manager.user_loader
def load_user(user_id): return db.session.get(User, int(user_id))

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if current_user.role != 'admin':
            flash('Admin access only.', 'warning')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return wrapper

def log(action, details=''):
    db.session.add(Activity(action=action, details=details, user_id=current_user.id if current_user.is_authenticated else None))
    db.session.commit()

def save_file(file):
    if not file or not file.filename: return None
    filename = datetime.now().strftime('%Y%m%d%H%M%S_') + secure_filename(file.filename)
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    return filename

def init_db():
    db.create_all()
    if not Department.query.first():
        for n in ['Sales','Engineering','Procurement','Finance','HR','Logistics','IT','Admin']:
            db.session.add(Department(name=n, description=f'{n} department'))
        db.session.commit()
    if not User.query.filter_by(email='admin@kringroup.com').first():
        admin_dept = Department.query.filter_by(name='Admin').first()
        user = User(name='Admin User', email='admin@kringroup.com', role='admin', department_id=admin_dept.id)
        user.set_password('admin123')
        db.session.add(user)
        db.session.commit()

@app.route('/')
def index():
    return redirect(url_for('dashboard') if current_user.is_authenticated else url_for('login'))

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form.get('email','').lower().strip()).first()
        if user and user.check_password(request.form.get('password','')):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Wrong email or password.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user(); return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    today = date.today()
    return render_template('dashboard.html',
        clients=Client.query.order_by(Client.created_at.desc()).limit(6).all(),
        activities=Activity.query.order_by(Activity.created_at.desc()).limit(7).all(),
        bulletins=Bulletin.query.order_by(Bulletin.created_at.desc()).limit(4).all(),
        tasks=Task.query.order_by(Task.due_date.asc()).limit(5).all(),
        departments=Department.query.all(),
        total_clients=Client.query.count(),
        total_departments=Department.query.count(),
        open_tasks=Task.query.filter(Task.status!='Done').count(),
        today_clients=Client.query.filter(Client.client_date==today).count())

@app.route('/clients')
@login_required
def clients():
    q = request.args.get('q','').strip(); dept = request.args.get('department',''); status = request.args.get('status','')
    query = Client.query
    if q:
        like = f'%{q}%'; query = query.filter(db.or_(Client.client_name.ilike(like), Client.company.ilike(like), Client.contact_person.ilike(like), Client.email.ilike(like)))
    if dept: query = query.filter_by(department_id=int(dept))
    if status: query = query.filter_by(status=status)
    return render_template('clients.html', clients=query.order_by(Client.updated_at.desc()).all(), departments=Department.query.all())

@app.route('/clients/add', methods=['GET','POST'])
@login_required
def add_client():
    if request.method == 'POST':
        c = Client(client_name=request.form['client_name'], company=request.form.get('company'), contact_person=request.form.get('contact_person'),
            email=request.form.get('email'), phone=request.form.get('phone'), department_id=int(request.form['department_id']),
            client_date=datetime.strptime(request.form.get('client_date'), '%Y-%m-%d').date() if request.form.get('client_date') else date.today(),
            status=request.form.get('status','New'), notes=request.form.get('notes'), attachment=save_file(request.files.get('attachment')),
            created_by_id=current_user.id, updated_by_id=current_user.id)
        db.session.add(c); db.session.commit(); log('Added client', c.client_name); flash('Client added.', 'success'); return redirect(url_for('clients'))
    return render_template('client_form.html', client=None, departments=Department.query.all())

@app.route('/clients/<int:id>/edit', methods=['GET','POST'])
@login_required
def edit_client(id):
    c = Client.query.get_or_404(id)
    if request.method == 'POST':
        c.client_name=request.form['client_name']; c.company=request.form.get('company'); c.contact_person=request.form.get('contact_person')
        c.email=request.form.get('email'); c.phone=request.form.get('phone'); c.department_id=int(request.form['department_id'])
        c.client_date=datetime.strptime(request.form.get('client_date'), '%Y-%m-%d').date() if request.form.get('client_date') else c.client_date
        c.status=request.form.get('status','New'); c.notes=request.form.get('notes'); c.updated_by_id=current_user.id
        f = save_file(request.files.get('attachment'))
        if f: c.attachment = f
        db.session.commit(); log('Edited client', c.client_name); flash('Client updated.', 'success'); return redirect(url_for('clients'))
    return render_template('client_form.html', client=c, departments=Department.query.all())

@app.route('/clients/<int:id>/delete', methods=['POST'])
@login_required
def delete_client(id):
    c=Client.query.get_or_404(id); name=c.client_name; db.session.delete(c); db.session.commit(); log('Deleted client', name); flash('Client deleted.', 'info'); return redirect(url_for('clients'))

@app.route('/uploads/<filename>')
@login_required
def uploaded_file(filename): return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/departments')
@login_required
def departments(): return render_template('departments.html', departments=Department.query.all())

@app.route('/bulletin', methods=['GET','POST'])
@login_required
def bulletin():
    if request.method == 'POST':
        db.session.add(Bulletin(title=request.form['title'], message=request.form['message'], created_by_id=current_user.id)); db.session.commit(); log('Posted bulletin', request.form['title']); return redirect(url_for('bulletin'))
    return render_template('bulletin.html', bulletins=Bulletin.query.order_by(Bulletin.created_at.desc()).all())

@app.route('/tasks', methods=['GET','POST'])
@login_required
def tasks():
    if request.method == 'POST':
        d=request.form.get('due_date')
        db.session.add(Task(title=request.form['title'], department_id=int(request.form['department_id']), assigned_to=request.form.get('assigned_to'), status=request.form.get('status','Open'), due_date=datetime.strptime(d,'%Y-%m-%d').date() if d else None)); db.session.commit(); log('Created task', request.form['title']); return redirect(url_for('tasks'))
    return render_template('tasks.html', tasks=Task.query.order_by(Task.created_at.desc()).all(), departments=Department.query.all())

@app.route('/calendar')
@login_required
def calendar(): return render_template('calendar.html', tasks=Task.query.order_by(Task.due_date.asc()).all(), clients=Client.query.order_by(Client.client_date.asc()).all())

@app.route('/feedback', methods=['GET','POST'])
@login_required
def feedback():
    if request.method == 'POST':
        db.session.add(Feedback(category=request.form['category'], message=request.form['message'], created_by_id=current_user.id)); db.session.commit(); log('Submitted feedback', request.form['category']); flash('Feedback sent.', 'success'); return redirect(url_for('feedback'))
    return render_template('feedback.html', feedbacks=Feedback.query.order_by(Feedback.created_at.desc()).all())

@app.route('/activity')
@login_required
def activity(): return render_template('activity.html', activities=Activity.query.order_by(Activity.created_at.desc()).all())

@app.route('/qr')
@login_required
def qr(): return render_template('qr.html')

with app.app_context(): init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
