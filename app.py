"""
Система управления курсами — Flask + PostgreSQL
Запуск:
    pip install flask psycopg2-binary flask-login werkzeug
    python app.py
"""

from flask import Flask, render_template, redirect, url_for, request, flash, session, jsonify
from functools import wraps
import psycopg2
import psycopg2.extras
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "super-secret-dev-key-change-in-prod")

# ── Jinja2 helpers ────────────────────────────────────────────────────────────

@app.context_processor
def inject_globals():
    return {"now": datetime.now()}

app.jinja_env.globals["enumerate"] = enumerate

# ─── Database connection ─────────────────────────────────────────────────────

DB_CONFIG = {
    "host":     os.environ.get("DB_HOST",     "localhost"),
    "port":     int(os.environ.get("DB_PORT", 5432)),
    "dbname":   os.environ.get("DB_NAME",     "courses_db"),
    "user":     os.environ.get("DB_USER",     "postgres"),
    "password": os.environ.get("DB_PASSWORD", "postgres"),
}

def get_db():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    return conn

def query(sql, params=(), fetchone=False, fetchall=False, commit=False):
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        result = None
        if fetchone:
            result = cur.fetchone()
        elif fetchall:
            result = cur.fetchall()
        if commit:
            conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# ─── Auth helpers ────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if session.get("role") not in roles:
                flash("Недостаточно прав доступа.", "error")
                return redirect(url_for("dashboard"))
            return f(*args, **kwargs)
        return decorated
    return decorator

def current_user():
    if "user_id" not in session:
        return None
    return {
        "id":        session["user_id"],
        "role":      session["role"],
        "full_name": session["full_name"],
        "username":  session["username"],
    }

# ─── Routes: Auth ────────────────────────────────────────────────────────────

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = query("SELECT * FROM users WHERE username=%s", (username,), fetchone=True)
        if user and check_password_hash(user["password"], password):
            session["user_id"]   = user["id"]
            session["role"]      = user["role"]
            session["full_name"] = user["full_name"] or username
            session["username"]  = user["username"]
            return redirect(url_for("dashboard"))
        flash("Неверный логин или пароль.", "error")
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username  = request.form.get("username", "").strip()
        full_name = request.form.get("full_name", "").strip()
        email     = request.form.get("email", "").strip()
        password  = request.form.get("password", "")
        password2 = request.form.get("password2", "")
        role      = request.form.get("role", "student")

        if not username or not password or not full_name:
            flash("Заполните все обязательные поля.", "error")
        elif len(username) < 3:
            flash("Логин должен содержать минимум 3 символа.", "error")
        elif password != password2:
            flash("Пароли не совпадают.", "error")
        elif len(password) < 6:
            flash("Пароль должен быть не менее 6 символов.", "error")
        elif email and "@" not in email:
            flash("Введите корректный email.", "error")
        elif role not in ("student", "teacher"):
            flash("Недопустимая роль.", "error")
        else:
            existing = query("SELECT id FROM users WHERE username=%s", (username,), fetchone=True)
            if existing:
                flash(f"Логин «{username}» уже занят.", "error")
            else:
                hashed = generate_password_hash(password)
                query(
                    "INSERT INTO users (username, password, role, full_name, email) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                    (username, hashed, role, full_name, email),
                    commit=True
                )
                user = query("SELECT id FROM users WHERE username=%s", (username,), fetchone=True)
                uid = user["id"]
                if role == "teacher":
                    query("INSERT INTO teachers (user_id) VALUES (%s)", (uid,), commit=True)
                elif role == "student":
                    query("INSERT INTO students (user_id, enrollment_year) VALUES (%s,%s)",
                          (uid, datetime.now().year), commit=True)
                flash("Аккаунт создан! Войдите в систему.", "success")
                return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ─── Dashboard ───────────────────────────────────────────────────────────────

@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    role = user["role"]
    stats = {}

    if role in ("admin", "teacher"):
        stats["students"]  = query("SELECT COUNT(*) as n FROM students", fetchone=True)["n"]
        stats["courses"]   = query("SELECT COUNT(*) as n FROM courses",  fetchone=True)["n"]
        stats["teachers"]  = query("SELECT COUNT(*) as n FROM teachers", fetchone=True)["n"]
        stats["avg_grade"] = query("SELECT ROUND(AVG(grade)::numeric,1) as n FROM grades", fetchone=True)["n"] or 0
        recent = query("""
            SELECT u.full_name AS student, co.title AS course,
                   e.enrolled_at, e.status
            FROM enrollments e
            JOIN students s ON e.student_id=s.id
            JOIN users u ON s.user_id=u.id
            JOIN courses co ON e.course_id=co.id
            ORDER BY e.enrolled_at DESC LIMIT 10
        """, fetchall=True)
    else:
        sid = query("SELECT id FROM students WHERE user_id=%s", (user["id"],), fetchone=True)
        if sid:
            sid = sid["id"]
            stats["enrolled"]  = query("SELECT COUNT(*) as n FROM enrollments WHERE student_id=%s", (sid,), fetchone=True)["n"]
            stats["completed"] = query("SELECT COUNT(*) as n FROM enrollments WHERE student_id=%s AND status='completed'", (sid,), fetchone=True)["n"]
            stats["avg_grade"] = query("""
                SELECT ROUND(AVG(g.grade)::numeric,1) as n FROM grades g
                JOIN enrollments e ON g.enrollment_id=e.id WHERE e.student_id=%s
            """, (sid,), fetchone=True)["n"] or 0
        recent = query("""
            SELECT co.title AS course, e.enrolled_at, e.status, g.grade
            FROM enrollments e
            JOIN courses co ON e.course_id=co.id
            LEFT JOIN grades g ON g.enrollment_id=e.id
            JOIN students s ON e.student_id=s.id
            WHERE s.user_id=%s ORDER BY e.enrolled_at DESC LIMIT 8
        """, (user["id"],), fetchall=True)

    return render_template("dashboard.html", user=user, stats=stats, recent=recent)

# ─── Users (admin) ──────────────────────────────────────────────────────────

@app.route("/users")
@login_required
@role_required("admin")
def users():
    rows = query("""
        SELECT id, username, full_name, email, role, created_at FROM users ORDER BY id
    """, fetchall=True)
    return render_template("users.html", user=current_user(), rows=rows)

@app.route("/users/delete/<int:uid>", methods=["POST"])
@login_required
@role_required("admin")
def delete_user(uid):
    if uid == session["user_id"]:
        flash("Нельзя удалить себя.", "error")
    else:
        query("DELETE FROM users WHERE id=%s", (uid,), commit=True)
        flash("Пользователь удалён.", "success")
    return redirect(url_for("users"))

@app.route("/users/add", methods=["POST"])
@login_required
@role_required("admin")
def add_user():
    username  = request.form.get("username", "").strip()
    full_name = request.form.get("full_name", "").strip()
    email     = request.form.get("email", "").strip()
    password  = request.form.get("password", "")
    role      = request.form.get("role", "student")

    # Валидация
    if not username or not password or not full_name:
        flash("Логин, имя и пароль обязательны.", "error")
        return redirect(url_for("users"))
    if len(username) < 3:
        flash("Логин должен содержать минимум 3 символа.", "error")
        return redirect(url_for("users"))
    if len(password) < 6:
        flash("Пароль должен содержать минимум 6 символов.", "error")
        return redirect(url_for("users"))
    if email and "@" not in email:
        flash("Введите корректный email.", "error")
        return redirect(url_for("users"))

    # Администратор должен быть только один
    if role == "admin":
        existing_admin = query("SELECT id FROM users WHERE role='admin'", fetchone=True)
        if existing_admin:
            flash("В системе уже есть администратор. Допускается только один администратор.", "error")
            return redirect(url_for("users"))

    existing = query("SELECT id FROM users WHERE username=%s", (username,), fetchone=True)
    if existing:
        flash(f"Логин «{username}» уже занят.", "error")
    else:
        query("INSERT INTO users (username,password,role,full_name,email) VALUES (%s,%s,%s,%s,%s)",
              (username, generate_password_hash(password), role, full_name, email), commit=True)
        uid = query("SELECT id FROM users WHERE username=%s", (username,), fetchone=True)["id"]
        if role == "teacher":
            query("INSERT INTO teachers (user_id) VALUES (%s)", (uid,), commit=True)
        elif role == "student":
            query("INSERT INTO students (user_id, enrollment_year) VALUES (%s,%s)",
                  (uid, datetime.now().year), commit=True)
        flash(f"Пользователь «{full_name}» успешно добавлен.", "success")
    return redirect(url_for("users"))

# ─── Students ───────────────────────────────────────────────────────────────

@app.route("/students")
@login_required
@role_required("admin", "teacher")
def students():
    search = request.args.get("q", "")
    rows = query("""
        SELECT s.id, u.full_name, u.username, u.email,
               s.group_name, s.enrollment_year,
               COUNT(DISTINCT e.id) AS total_courses,
               COUNT(DISTINCT CASE WHEN e.status='completed' THEN e.id END) AS completed,
               ROUND(AVG(g.grade)::numeric,1) AS avg_grade
        FROM students s
        JOIN users u ON s.user_id=u.id
        LEFT JOIN enrollments e ON e.student_id=s.id
        LEFT JOIN grades g ON g.enrollment_id=e.id
        WHERE u.full_name ILIKE %s OR u.username ILIKE %s
        GROUP BY s.id, u.full_name, u.username, u.email, s.group_name, s.enrollment_year
        ORDER BY u.full_name
    """, (f"%{search}%", f"%{search}%"), fetchall=True)
    return render_template("students.html", user=current_user(), rows=rows, search=search)

@app.route("/students/<int:sid>/edit", methods=["POST"])
@login_required
@role_required("admin")
def edit_student(sid):
    full_name = request.form.get("full_name", "").strip()
    email     = request.form.get("email", "").strip()
    group     = request.form.get("group_name", "").strip()
    year_raw  = request.form.get("enrollment_year", "").strip()

    if not full_name:
        flash("Имя студента не может быть пустым.", "error")
        return redirect(url_for("students"))
    if email and "@" not in email:
        flash("Введите корректный email.", "error")
        return redirect(url_for("students"))
    year = None
    if year_raw:
        try:
            year = int(year_raw)
            if year < 2000 or year > datetime.now().year:
                raise ValueError
        except ValueError:
            flash(f"Год поступления должен быть числом от 2000 до {datetime.now().year}.", "error")
            return redirect(url_for("students"))

    query("UPDATE students SET group_name=%s, enrollment_year=%s WHERE id=%s",
          (group or None, year, sid), commit=True)
    query("UPDATE users SET full_name=%s, email=%s WHERE id=(SELECT user_id FROM students WHERE id=%s)",
          (full_name, email or None, sid), commit=True)
    flash("Данные студента успешно обновлены.", "success")
    return redirect(url_for("students"))

# ─── Teachers ───────────────────────────────────────────────────────────────

@app.route("/teachers")
@login_required
@role_required("admin", "teacher")
def teachers():
    rows = query("""
        SELECT t.id, u.full_name, u.username, u.email,
               t.department, t.degree,
               COUNT(DISTINCT c.id) AS courses_count,
               COUNT(DISTINCT e.student_id) AS students_count
        FROM teachers t
        JOIN users u ON t.user_id=u.id
        LEFT JOIN courses c ON c.teacher_id=t.id
        LEFT JOIN enrollments e ON e.course_id=c.id AND e.status='active'
        GROUP BY t.id, u.full_name, u.username, u.email, t.department, t.degree
        ORDER BY u.full_name
    """, fetchall=True)
    return render_template("teachers.html", user=current_user(), rows=rows)

@app.route("/teachers/<int:tid>/edit", methods=["POST"])
@login_required
@role_required("admin")
def edit_teacher(tid):
    query("UPDATE teachers SET department=%s, degree=%s WHERE id=%s",
          (request.form.get("department"), request.form.get("degree"), tid), commit=True)
    flash("Данные преподавателя обновлены.", "success")
    return redirect(url_for("teachers"))

# ─── Courses ─────────────────────────────────────────────────────────────────

@app.route("/courses")
@login_required
def courses():
    user = current_user()
    rows = query("""
        SELECT co.id, co.title, co.description, u.full_name AS teacher_name,
               co.max_students,
               COUNT(DISTINCT e.id) AS enrolled,
               COUNT(DISTINCT CASE WHEN e.status='completed' THEN e.id END) AS completed,
               ROUND(AVG(g.grade)::numeric,1) AS avg_grade,
               co.created_at
        FROM courses co
        LEFT JOIN teachers t ON co.teacher_id=t.id
        LEFT JOIN users u ON t.user_id=u.id
        LEFT JOIN enrollments e ON e.course_id=co.id
        LEFT JOIN grades g ON g.enrollment_id=e.id
        GROUP BY co.id, co.title, co.description, u.full_name, co.max_students, co.created_at
        ORDER BY co.title
    """, fetchall=True)
    teacher_list = query("""
        SELECT t.id, u.full_name FROM teachers t JOIN users u ON t.user_id=u.id ORDER BY u.full_name
    """, fetchall=True)
    return render_template("courses.html", user=user, rows=rows, teacher_list=teacher_list)

@app.route("/courses/add", methods=["POST"])
@login_required
@role_required("admin")
def add_course():
    title = request.form.get("title", "").strip()
    if not title:
        flash("Название курса обязательно.", "error")
        return redirect(url_for("courses"))
    if len(title) < 3:
        flash("Название курса должно содержать минимум 3 символа.", "error")
        return redirect(url_for("courses"))
    max_s_raw = request.form.get("max_students", "30")
    try:
        max_s = int(max_s_raw)
        if max_s < 1 or max_s > 500:
            raise ValueError
    except ValueError:
        flash("Максимальное количество студентов должно быть числом от 1 до 500.", "error")
        return redirect(url_for("courses"))

    query("""
        INSERT INTO courses (title, description, teacher_id, max_students)
        VALUES (%s,%s,%s,%s)
    """, (
        title,
        request.form.get("description", "").strip() or None,
        request.form.get("teacher_id") or None,
        max_s
    ), commit=True)
    flash(f"Курс «{title}» успешно добавлен.", "success")
    return redirect(url_for("courses"))

@app.route("/courses/<int:cid>/edit", methods=["POST"])
@login_required
@role_required("admin")
def edit_course(cid):
    query("""
        UPDATE courses SET title=%s, description=%s, teacher_id=%s, max_students=%s WHERE id=%s
    """, (
        request.form.get("title"),
        request.form.get("description"),
        request.form.get("teacher_id") or None,
        request.form.get("max_students") or 30,
        cid
    ), commit=True)
    flash("Курс обновлён.", "success")
    return redirect(url_for("courses"))

@app.route("/courses/<int:cid>/delete", methods=["POST"])
@login_required
@role_required("admin")
def delete_course(cid):
    query("DELETE FROM courses WHERE id=%s", (cid,), commit=True)
    flash("Курс удалён.", "success")
    return redirect(url_for("courses"))

# ─── Grades ──────────────────────────────────────────────────────────────────

@app.route("/grades")
@login_required
@role_required("admin", "teacher")
def grades():
    user = current_user()
    if user["role"] == "teacher":
        tid = query("SELECT id FROM teachers WHERE user_id=%s", (user["id"],), fetchone=True)
        tid = tid["id"] if tid else -1
        rows = query("""
            SELECT e.id, u.full_name AS student, co.title AS course,
                   g.grade, g.graded_at, g.comment, e.status
            FROM enrollments e
            JOIN students s ON e.student_id=s.id
            JOIN users u ON s.user_id=u.id
            JOIN courses co ON e.course_id=co.id
            LEFT JOIN grades g ON g.enrollment_id=e.id
            WHERE co.teacher_id=%s
            ORDER BY u.full_name, co.title
        """, (tid,), fetchall=True)
    else:
        rows = query("""
            SELECT e.id, u.full_name AS student, co.title AS course,
                   g.grade, g.graded_at, g.comment, e.status
            FROM enrollments e
            JOIN students s ON e.student_id=s.id
            JOIN users u ON s.user_id=u.id
            JOIN courses co ON e.course_id=co.id
            LEFT JOIN grades g ON g.enrollment_id=e.id
            ORDER BY u.full_name, co.title
        """, fetchall=True)
    return render_template("grades.html", user=user, rows=rows)

@app.route("/grades/set", methods=["POST"])
@login_required
@role_required("admin", "teacher")
def set_grade():
    eid_raw   = request.form.get("enrollment_id", "")
    grade_raw = request.form.get("grade", "")
    comment   = request.form.get("comment", "").strip()

    if not eid_raw or not grade_raw:
        flash("Заполните все обязательные поля.", "error")
        return redirect(url_for("grades"))
    try:
        eid   = int(eid_raw)
        grade = float(grade_raw.replace(",", "."))
        if grade < 0 or grade > 100:
            raise ValueError
    except ValueError:
        flash("Оценка должна быть числом от 0 до 100.", "error")
        return redirect(url_for("grades"))

    # Проверяем что запись существует
    enrollment = query("SELECT id FROM enrollments WHERE id=%s", (eid,), fetchone=True)
    if not enrollment:
        flash("Запись на курс не найдена.", "error")
        return redirect(url_for("grades"))

    query("""
        INSERT INTO grades (enrollment_id, grade, comment, graded_at)
        VALUES (%s,%s,%s,NOW())
        ON CONFLICT (enrollment_id) DO UPDATE
        SET grade=EXCLUDED.grade, comment=EXCLUDED.comment, graded_at=NOW()
    """, (eid, grade, comment), commit=True)
    query("UPDATE enrollments SET status='completed' WHERE id=%s", (eid,), commit=True)
    flash(f"Оценка {grade} успешно сохранена.", "success")
    return redirect(url_for("grades"))

# ─── Statistics ──────────────────────────────────────────────────────────────

@app.route("/statistics")
@login_required
@role_required("admin", "teacher")
def statistics():
    user = current_user()

    # Students
    st = {}
    st["total"]    = query("SELECT COUNT(*) AS n FROM students", fetchone=True)["n"]
    st["active"]   = query("""SELECT COUNT(DISTINCT s.id) AS n FROM students s
                              JOIN enrollments e ON e.student_id=s.id WHERE e.status='active'""", fetchone=True)["n"]
    st["avg"]      = query("SELECT ROUND(AVG(grade)::numeric,2) AS n FROM grades", fetchone=True)["n"] or 0
    st["max"]      = query("SELECT MAX(grade) AS n FROM grades", fetchone=True)["n"] or 0
    st["min"]      = query("SELECT MIN(grade) AS n FROM grades", fetchone=True)["n"] or 0
    st["no_grade"] = query("""SELECT COUNT(DISTINCT s.id) AS n FROM students s
                              JOIN enrollments e ON e.student_id=s.id
                              LEFT JOIN grades g ON g.enrollment_id=e.id
                              WHERE g.grade IS NULL""", fetchone=True)["n"]
    st["top5"]     = query("""
        SELECT u.full_name, ROUND(AVG(g.grade)::numeric,1) AS avg
        FROM students s JOIN users u ON s.user_id=u.id
        JOIN enrollments e ON e.student_id=s.id
        JOIN grades g ON g.enrollment_id=e.id
        GROUP BY s.id, u.full_name ORDER BY avg DESC LIMIT 5
    """, fetchall=True)

    # Courses
    co = {}
    co["total"]    = query("SELECT COUNT(*) AS n FROM courses", fetchone=True)["n"]
    co["with_t"]   = query("SELECT COUNT(*) AS n FROM courses WHERE teacher_id IS NOT NULL", fetchone=True)["n"]
    co["avg_enr"]  = query("SELECT ROUND(AVG(cnt)::numeric,1) AS n FROM (SELECT COUNT(*) cnt FROM enrollments GROUP BY course_id) t", fetchone=True)["n"] or 0
    co["popular"]  = query("""
        SELECT co.title, COUNT(e.id) AS cnt FROM courses co
        LEFT JOIN enrollments e ON e.course_id=co.id
        GROUP BY co.id ORDER BY cnt DESC LIMIT 1
    """, fetchone=True)
    co["top5"]     = query("""
        SELECT co.title, ROUND(AVG(g.grade)::numeric,1) AS avg
        FROM courses co JOIN enrollments e ON e.course_id=co.id
        JOIN grades g ON g.enrollment_id=e.id
        GROUP BY co.id ORDER BY avg DESC LIMIT 5
    """, fetchall=True)

    # Teachers
    tc = {}
    tc["total"]      = query("SELECT COUNT(*) AS n FROM teachers", fetchone=True)["n"]
    tc["active"]     = query("SELECT COUNT(DISTINCT teacher_id) AS n FROM courses WHERE teacher_id IS NOT NULL", fetchone=True)["n"]
    tc["avg_courses"]= query("SELECT ROUND(AVG(cnt)::numeric,1) AS n FROM (SELECT COUNT(*) cnt FROM courses GROUP BY teacher_id) t", fetchone=True)["n"] or 0
    tc["top5"]       = query("""
        SELECT u.full_name, COUNT(DISTINCT e.student_id) AS students
        FROM teachers t JOIN users u ON t.user_id=u.id
        JOIN courses c ON c.teacher_id=t.id
        JOIN enrollments e ON e.course_id=c.id
        GROUP BY t.id, u.full_name ORDER BY students DESC LIMIT 5
    """, fetchall=True)

    # Grades distribution
    dist = query("""
        SELECT
          COUNT(*) FILTER (WHERE grade>=90) AS excellent,
          COUNT(*) FILTER (WHERE grade>=75 AND grade<90) AS good,
          COUNT(*) FILTER (WHERE grade>=60 AND grade<75) AS satisf,
          COUNT(*) FILTER (WHERE grade<60) AS fail,
          COUNT(*) AS total
        FROM grades WHERE grade IS NOT NULL
    """, fetchone=True)

    return render_template("statistics.html", user=user, st=st, co=co, tc=tc, dist=dist)

# ─── Student: My courses ──────────────────────────────────────────────────────

@app.route("/my-courses")
@login_required
@role_required("student", "teacher")
def my_courses():
    user = current_user()
    if user["role"] == "teacher":
        tid = query("SELECT id FROM teachers WHERE user_id=%s", (user["id"],), fetchone=True)
        rows = []
        if tid:
            rows = query("""
                SELECT co.id, co.title, co.description, co.max_students,
                       COUNT(DISTINCT e.id) AS enrolled,
                       ROUND(AVG(g.grade)::numeric,1) AS avg_grade
                FROM courses co
                LEFT JOIN enrollments e ON e.course_id=co.id
                LEFT JOIN grades g ON g.enrollment_id=e.id
                WHERE co.teacher_id=%s GROUP BY co.id ORDER BY co.title
            """, (tid["id"],), fetchall=True)
    else:
        rows = query("""
            SELECT co.id, co.title, u.full_name AS teacher, e.status, g.grade, e.enrolled_at
            FROM enrollments e
            JOIN courses co ON e.course_id=co.id
            LEFT JOIN teachers t ON co.teacher_id=t.id
            LEFT JOIN users u ON t.user_id=u.id
            LEFT JOIN grades g ON g.enrollment_id=e.id
            JOIN students s ON e.student_id=s.id
            WHERE s.user_id=%s ORDER BY e.enrolled_at DESC
        """, (user["id"],), fetchall=True)
    return render_template("my_courses.html", user=user, rows=rows)

@app.route("/enroll", methods=["GET", "POST"])
@login_required
@role_required("student")
def enroll():
    user = current_user()
    sid  = query("SELECT id FROM students WHERE user_id=%s", (user["id"],), fetchone=True)
    if not sid:
        flash("Профиль студента не найден.", "error")
        return redirect(url_for("dashboard"))
    sid = sid["id"]

    if request.method == "POST":
        cid = int(request.form.get("course_id"))

        # Проверка: существует ли курс
        course = query("SELECT id, title, max_students FROM courses WHERE id=%s", (cid,), fetchone=True)
        if not course:
            flash("Курс не найден.", "error")
            return redirect(url_for("enroll"))

        # Проверка: уже записан
        existing = query("SELECT id FROM enrollments WHERE student_id=%s AND course_id=%s",
                         (sid, cid), fetchone=True)
        if existing:
            flash("Вы уже записаны на этот курс.", "error")
            return redirect(url_for("enroll"))

        # Проверка: не превышен ли лимит мест
        enrolled_count = query(
            "SELECT COUNT(*) AS n FROM enrollments WHERE course_id=%s", (cid,), fetchone=True
        )["n"]
        if enrolled_count >= course["max_students"]:
            flash(f"К сожалению, курс «{course['title']}» уже набрал максимальное количество участников ({course['max_students']}).", "error")
            return redirect(url_for("enroll"))

        query("INSERT INTO enrollments (student_id, course_id) VALUES (%s,%s)",
              (sid, cid), commit=True)
        flash(f"Вы успешно записались на курс «{course['title']}»!", "success")
        return redirect(url_for("enroll"))

    enrolled_ids = {r["course_id"] for r in query(
        "SELECT course_id FROM enrollments WHERE student_id=%s", (sid,), fetchall=True)}
    courses_list = query("""
        SELECT co.id, co.title, co.description, u.full_name AS teacher,
               COUNT(DISTINCT e.id) AS enrolled, co.max_students
        FROM courses co
        LEFT JOIN teachers t ON co.teacher_id=t.id
        LEFT JOIN users u ON t.user_id=u.id
        LEFT JOIN enrollments e ON e.course_id=co.id
        GROUP BY co.id, co.title, co.description, u.full_name, co.max_students
        ORDER BY co.title
    """, fetchall=True)
    return render_template("enroll.html", user=user, courses=courses_list, enrolled_ids=enrolled_ids)

@app.route("/my-grades")
@login_required
@role_required("student")
def my_grades():
    user = current_user()
    rows = query("""
        SELECT co.title AS course, u.full_name AS teacher,
               g.grade, g.graded_at, g.comment, e.status
        FROM enrollments e
        JOIN courses co ON e.course_id=co.id
        LEFT JOIN teachers t ON co.teacher_id=t.id
        LEFT JOIN users u ON t.user_id=u.id
        LEFT JOIN grades g ON g.enrollment_id=e.id
        JOIN students s ON e.student_id=s.id
        WHERE s.user_id=%s ORDER BY e.enrolled_at DESC
    """, (user["id"],), fetchall=True)
    avg = query("""
        SELECT ROUND(AVG(g.grade)::numeric,2) AS n FROM grades g
        JOIN enrollments e ON g.enrollment_id=e.id
        JOIN students s ON e.student_id=s.id
        WHERE s.user_id=%s
    """, (user["id"],), fetchone=True)["n"]
    return render_template("my_grades.html", user=user, rows=rows, avg=avg)

# ─── API: chart data ─────────────────────────────────────────────────────────

@app.route("/api/chart/grade-dist")
@login_required
def api_grade_dist():
    dist = query("""
        SELECT
          COUNT(*) FILTER (WHERE grade>=90) AS excellent,
          COUNT(*) FILTER (WHERE grade>=75 AND grade<90) AS good,
          COUNT(*) FILTER (WHERE grade>=60 AND grade<75) AS satisf,
          COUNT(*) FILTER (WHERE grade<60) AS fail
        FROM grades WHERE grade IS NOT NULL
    """, fetchone=True)
    return jsonify(dict(dist))

@app.route("/api/chart/enrollments-by-course")
@login_required
def api_enrollments_by_course():
    rows = query("""
        SELECT co.title, COUNT(e.id) AS cnt
        FROM courses co LEFT JOIN enrollments e ON e.course_id=co.id
        GROUP BY co.id ORDER BY cnt DESC LIMIT 8
    """, fetchall=True)
    return jsonify([dict(r) for r in rows])

# ─── Run ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=5000)
