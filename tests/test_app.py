import pytest
from werkzeug.security import generate_password_hash

import app as myapp


@pytest.fixture(autouse=True)
def _setup_app(monkeypatch):
    myapp.app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
    )

    # Чтобы тесты не зависели от HTML-шаблонов
    monkeypatch.setattr(
        myapp,
        "render_template",
        lambda template_name, **context: f"TEMPLATE:{template_name}",
    )


@pytest.fixture
def client():
    return myapp.app.test_client()


def set_session(client, *, user_id=1, role="admin", username="admin", full_name="Admin"):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["role"] = role
        sess["username"] = username
        sess["full_name"] = full_name


def get_flashes(client):
    with client.session_transaction() as sess:
        return sess.get("_flashes", [])


def has_flash(client, text, category=None):
    flashes = get_flashes(client)
    for cat, msg in flashes:
        if text in msg and (category is None or cat == category):
            return True
    return False


def normalize_sql(sql: str) -> str:
    return " ".join(sql.split())


def is_sql(sql: str, fragment: str) -> bool:
    return fragment in normalize_sql(sql)


# ----------------------------
# AUTH
# ----------------------------

def test_login_success_sets_session_and_redirects(client, monkeypatch):
    def fake_query(sql, params=(), fetchone=False, fetchall=False, commit=False):
        if is_sql(sql, "SELECT * FROM users WHERE username=%s"):
            return {
                "id": 7,
                "username": "student1",
                "password": generate_password_hash("pass123"),
                "role": "student",
                "full_name": "Иван Петров",
            }
        raise AssertionError(f"Неожиданный SQL: {sql}")

    monkeypatch.setattr(myapp, "query", fake_query)

    response = client.post(
        "/login",
        data={"username": "student1", "password": "pass123"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/dashboard" in response.headers["Location"]

    with client.session_transaction() as sess:
        assert sess["user_id"] == 7
        assert sess["role"] == "student"
        assert sess["username"] == "student1"
        assert sess["full_name"] == "Иван Петров"


def test_login_invalid_credentials_shows_error(client, monkeypatch):
    def fake_query(sql, params=(), fetchone=False, fetchall=False, commit=False):
        if is_sql(sql, "SELECT * FROM users WHERE username=%s"):
            return None
        raise AssertionError(f"Неожиданный SQL: {sql}")

    monkeypatch.setattr(myapp, "query", fake_query)

    response = client.post(
        "/login",
        data={"username": "wrong", "password": "wrong"},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert has_flash(client, "Неверный логин или пароль.", "error")


def test_register_rejects_invalid_email(client, monkeypatch):
    monkeypatch.setattr(myapp, "query", lambda *args, **kwargs: None)

    response = client.post(
        "/register",
        data={
            "username": "petya",
            "full_name": "Петя Петров",
            "email": "not-an-email",
            "password": "pass123",
            "password2": "pass123",
            "role": "student",
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert has_flash(client, "Введите корректный email.", "error")


def test_register_rejects_duplicate_username(client, monkeypatch):
    def fake_query(sql, params=(), fetchone=False, fetchall=False, commit=False):
        if is_sql(sql, "SELECT id FROM users WHERE username=%s"):
            return {"id": 10}
        raise AssertionError(f"Неожиданный SQL: {sql}")

    monkeypatch.setattr(myapp, "query", fake_query)

    response = client.post(
        "/register",
        data={
            "username": "petya",
            "full_name": "Петя Петров",
            "email": "petya@example.com",
            "password": "pass123",
            "password2": "pass123",
            "role": "student",
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert has_flash(client, "Логин «petya» уже занят.", "error")


def test_register_creates_student_profile_on_success(client, monkeypatch):
    calls = []

    def fake_query(sql, params=(), fetchone=False, fetchall=False, commit=False):
        calls.append((normalize_sql(sql), params, fetchone, fetchall, commit))

        if is_sql(sql, "SELECT id FROM users WHERE username=%s"):
            # Первый вызов — проверка на существование логина
            # Второй вызов — получение id после вставки
            if params == ("newstudent",):
                seen = sum(1 for call in calls if "SELECT id FROM users WHERE username=%s" in call[0])
                if seen == 1:
                    return None
                return {"id": 42}

        if is_sql(sql, "INSERT INTO users (username, password, role, full_name, email) VALUES (%s,%s,%s,%s,%s) RETURNING id"):
            return None

        if is_sql(sql, "INSERT INTO students (user_id, enrollment_year) VALUES (%s,%s)"):
            return None

        raise AssertionError(f"Неожиданный SQL: {sql}")

    monkeypatch.setattr(myapp, "query", fake_query)

    response = client.post(
        "/register",
        data={
            "username": "newstudent",
            "full_name": "Новый Студент",
            "email": "newstudent@example.com",
            "password": "pass123",
            "password2": "pass123",
            "role": "student",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    assert has_flash(client, "Аккаунт создан! Войдите в систему.", "success")

    sql_texts = [c[0] for c in calls]
    assert any("INSERT INTO users" in sql for sql in sql_texts)
    assert any("INSERT INTO students" in sql for sql in sql_texts)


# ----------------------------
# ACCESS / USERS
# ----------------------------

def test_users_requires_admin_role(client, monkeypatch):
    set_session(client, user_id=2, role="teacher", username="teacher1", full_name="Teacher One")
    monkeypatch.setattr(myapp, "query", lambda *args, **kwargs: [])

    response = client.get("/users", follow_redirects=False)

    assert response.status_code == 302
    assert "/dashboard" in response.headers["Location"]
    assert has_flash(client, "Недостаточно прав доступа.", "error")


def test_add_user_rejects_second_admin(client, monkeypatch):
    set_session(client, user_id=1, role="admin", username="admin", full_name="Admin")

    def fake_query(sql, params=(), fetchone=False, fetchall=False, commit=False):
        if is_sql(sql, "SELECT id FROM users WHERE role='admin'"):
            return {"id": 1}
        raise AssertionError(f"Неожиданный SQL: {sql}")

    monkeypatch.setattr(myapp, "query", fake_query)

    response = client.post(
        "/users/add",
        data={
            "username": "admin2",
            "full_name": "Второй Админ",
            "email": "admin2@example.com",
            "password": "pass123",
            "role": "admin",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/users" in response.headers["Location"]
    assert has_flash(
        client,
        "В системе уже есть администратор. Допускается только один администратор.",
        "error",
    )


def test_delete_user_cannot_delete_self(client, monkeypatch):
    set_session(client, user_id=7, role="admin", username="admin", full_name="Admin")
    monkeypatch.setattr(myapp, "query", lambda *args, **kwargs: None)

    response = client.post("/users/delete/7", follow_redirects=False)

    assert response.status_code == 302
    assert "/users" in response.headers["Location"]
    assert has_flash(client, "Нельзя удалить себя.", "error")


# ----------------------------
# ENROLLMENTS
# ----------------------------

def test_enroll_rejects_if_course_is_full(client, monkeypatch):
    set_session(client, user_id=100, role="student", username="student1", full_name="Student One")
    calls = []

    def fake_query(sql, params=(), fetchone=False, fetchall=False, commit=False):
        calls.append((normalize_sql(sql), params, fetchone, fetchall, commit))

        if is_sql(sql, "SELECT id FROM students WHERE user_id=%s"):
            return {"id": 10}
        if is_sql(sql, "SELECT id, title, max_students FROM courses WHERE id=%s"):
            return {"id": 5, "title": "Python", "max_students": 5}
        if is_sql(sql, "SELECT id FROM enrollments WHERE student_id=%s AND course_id=%s"):
            return None
        if is_sql(sql, "SELECT COUNT(*) AS n FROM enrollments WHERE course_id=%s AND status<>'dropped'"):
            return {"n": 5}
        raise AssertionError(f"Неожиданный SQL: {sql}")

    monkeypatch.setattr(myapp, "query", fake_query)

    response = client.post("/enroll", data={"course_id": "5"}, follow_redirects=False)

    assert response.status_code == 302
    assert "/enroll" in response.headers["Location"]
    assert has_flash(client, "уже набрал максимальное количество участников", "error")

    sql_texts = [c[0] for c in calls]
    assert not any("INSERT INTO enrollments" in sql for sql in sql_texts)


def test_enroll_rejects_duplicate_course(client, monkeypatch):
    set_session(client, user_id=100, role="student", username="student1", full_name="Student One")

    def fake_query(sql, params=(), fetchone=False, fetchall=False, commit=False):
        if is_sql(sql, "SELECT id FROM students WHERE user_id=%s"):
            return {"id": 10}
        if is_sql(sql, "SELECT id, title, max_students FROM courses WHERE id=%s"):
            return {"id": 5, "title": "Python", "max_students": 20}
        if is_sql(sql, "SELECT id FROM enrollments WHERE student_id=%s AND course_id=%s"):
            return {"id": 99}
        raise AssertionError(f"Неожиданный SQL: {sql}")

    monkeypatch.setattr(myapp, "query", fake_query)

    response = client.post("/enroll", data={"course_id": "5"}, follow_redirects=False)

    assert response.status_code == 302
    assert "/enroll" in response.headers["Location"]
    assert has_flash(client, "Вы уже записаны на этот курс.", "error")


def test_enroll_success_creates_record(client, monkeypatch):
    set_session(client, user_id=100, role="student", username="student1", full_name="Student One")
    calls = []

    def fake_query(sql, params=(), fetchone=False, fetchall=False, commit=False):
        calls.append((normalize_sql(sql), params, fetchone, fetchall, commit))

        if is_sql(sql, "SELECT id FROM students WHERE user_id=%s"):
            return {"id": 10}
        if is_sql(sql, "SELECT id, title, max_students FROM courses WHERE id=%s"):
            return {"id": 5, "title": "Python", "max_students": 20}
        if is_sql(sql, "SELECT id FROM enrollments WHERE student_id=%s AND course_id=%s"):
            return None
        if is_sql(sql, "SELECT COUNT(*) AS n FROM enrollments WHERE course_id=%s AND status<>'dropped'"):
            return {"n": 4}
        if is_sql(sql, "INSERT INTO enrollments (student_id, course_id) VALUES (%s,%s)"):
            return None
        raise AssertionError(f"Неожиданный SQL: {sql}")

    monkeypatch.setattr(myapp, "query", fake_query)

    response = client.post("/enroll", data={"course_id": "5"}, follow_redirects=False)

    assert response.status_code == 302
    assert "/enroll" in response.headers["Location"]
    assert has_flash(client, "Вы успешно записались на курс «Python»!", "success")

    sql_texts = [c[0] for c in calls]
    assert any("INSERT INTO enrollments" in sql for sql in sql_texts)


# ----------------------------
# GRADES
# ----------------------------

def test_set_grade_rejects_out_of_range_value(client, monkeypatch):
    set_session(client, user_id=2, role="teacher", username="teacher1", full_name="Teacher One")
    monkeypatch.setattr(myapp, "query", lambda *args, **kwargs: None)

    response = client.post(
        "/grades/set",
        data={"enrollment_id": "1", "grade": "101", "comment": "слишком много"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/grades" in response.headers["Location"]
    assert has_flash(client, "Оценка должна быть числом от 0 до 100.", "error")


def test_set_grade_rejects_foreign_teacher_course(client, monkeypatch):
    set_session(client, user_id=20, role="teacher", username="teacher2", full_name="Teacher Two")

    def fake_query(sql, params=(), fetchone=False, fetchall=False, commit=False):
        if is_sql(sql, "SELECT id, course_id FROM enrollments WHERE id=%s"):
            return {"id": 1, "course_id": 5}
        if is_sql(sql, "SELECT id FROM teachers WHERE user_id=%s"):
            return {"id": 9}
        if is_sql(sql, "SELECT id FROM courses WHERE id=%s AND teacher_id=%s"):
            return None
        raise AssertionError(f"Неожиданный SQL: {sql}")

    monkeypatch.setattr(myapp, "query", fake_query)

    response = client.post(
        "/grades/set",
        data={"enrollment_id": "1", "grade": "88", "comment": "ok"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/grades" in response.headers["Location"]
    assert has_flash(client, "Нельзя выставлять оценку по чужому курсу.", "error")


def test_set_grade_success_for_teacher_saves_grade_and_marks_completed(client, monkeypatch):
    set_session(client, user_id=20, role="teacher", username="teacher2", full_name="Teacher Two")
    calls = []

    def fake_query(sql, params=(), fetchone=False, fetchall=False, commit=False):
        calls.append((normalize_sql(sql), params, fetchone, fetchall, commit))

        if is_sql(sql, "SELECT id, course_id FROM enrollments WHERE id=%s"):
            return {"id": 1, "course_id": 5}
        if is_sql(sql, "SELECT id FROM teachers WHERE user_id=%s"):
            return {"id": 9}
        if is_sql(sql, "SELECT id FROM courses WHERE id=%s AND teacher_id=%s"):
            return {"id": 5}
        if is_sql(sql, "INSERT INTO grades (enrollment_id, grade, comment, graded_at) VALUES (%s,%s,%s,NOW()) ON CONFLICT (enrollment_id) DO UPDATE SET grade=EXCLUDED.grade, comment=EXCLUDED.comment, graded_at=NOW()"):
            return None
        if is_sql(sql, "UPDATE enrollments SET status='completed' WHERE id=%s"):
            return None
        raise AssertionError(f"Неожиданный SQL: {sql}")

    monkeypatch.setattr(myapp, "query", fake_query)

    response = client.post(
        "/grades/set",
        data={"enrollment_id": "1", "grade": "91", "comment": "Отлично"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/grades" in response.headers["Location"]
    assert has_flash(client, "Оценка 91.0 успешно сохранена.", "success")

    sql_texts = [c[0] for c in calls]
    assert any("INSERT INTO grades" in sql for sql in sql_texts)
    assert any("UPDATE enrollments SET status='completed'" in sql for sql in sql_texts)


def test_set_grade_success_for_admin_saves_grade_and_marks_completed(client, monkeypatch):
    set_session(client, user_id=1, role="admin", username="admin", full_name="Admin")
    calls = []

    def fake_query(sql, params=(), fetchone=False, fetchall=False, commit=False):
        calls.append((normalize_sql(sql), params, fetchone, fetchall, commit))

        if is_sql(sql, "SELECT id, course_id FROM enrollments WHERE id=%s"):
            return {"id": 1, "course_id": 5}
        if is_sql(sql, "SELECT id FROM enrollments WHERE id=%s"):
            return {"id": 1}
        if is_sql(sql, "INSERT INTO grades (enrollment_id, grade, comment, graded_at) VALUES (%s,%s,%s,NOW()) ON CONFLICT (enrollment_id) DO UPDATE SET grade=EXCLUDED.grade, comment=EXCLUDED.comment, graded_at=NOW()"):
            return None
        if is_sql(sql, "UPDATE enrollments SET status='completed' WHERE id=%s"):
            return None
        raise AssertionError(f"Неожиданный SQL: {sql}")

    monkeypatch.setattr(myapp, "query", fake_query)

    response = client.post(
        "/grades/set",
        data={"enrollment_id": "1", "grade": "77", "comment": "Хорошо"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/grades" in response.headers["Location"]
    assert has_flash(client, "Оценка 77.0 успешно сохранена.", "success")

    sql_texts = [c[0] for c in calls]
    assert any("INSERT INTO grades" in sql for sql in sql_texts)
    assert any("UPDATE enrollments SET status='completed'" in sql for sql in sql_texts)


def test_delete_grade_resets_enrollment_status_to_active(client, monkeypatch):
    set_session(client, user_id=1, role="admin", username="admin", full_name="Admin")
    calls = []

    def fake_query(sql, params=(), fetchone=False, fetchall=False, commit=False):
        calls.append((normalize_sql(sql), params, fetchone, fetchall, commit))

        if is_sql(sql, "SELECT id FROM grades WHERE enrollment_id=%s"):
            return {"id": 50}
        if is_sql(sql, "DELETE FROM grades WHERE enrollment_id=%s"):
            return None
        if is_sql(sql, "UPDATE enrollments SET status='active' WHERE id=%s"):
            return None
        raise AssertionError(f"Неожиданный SQL: {sql}")

    monkeypatch.setattr(myapp, "query", fake_query)

    response = client.post("/grades/delete/12", follow_redirects=False)

    assert response.status_code == 302
    assert "/grades" in response.headers["Location"]
    assert has_flash(client, "Оценка удалена.", "success")

    sql_texts = [c[0] for c in calls]
    assert any("DELETE FROM grades" in sql for sql in sql_texts)
    assert any("UPDATE enrollments SET status='active'" in sql for sql in sql_texts)


def test_delete_grade_shows_error_if_missing(client, monkeypatch):
    set_session(client, user_id=1, role="admin", username="admin", full_name="Admin")

    def fake_query(sql, params=(), fetchone=False, fetchall=False, commit=False):
        if is_sql(sql, "SELECT id FROM grades WHERE enrollment_id=%s"):
            return None
        raise AssertionError(f"Неожиданный SQL: {sql}")

    monkeypatch.setattr(myapp, "query", fake_query)

    response = client.post("/grades/delete/12", follow_redirects=False)

    assert response.status_code == 302
    assert "/grades" in response.headers["Location"]
    assert has_flash(client, "Оценка не найдена.", "error")