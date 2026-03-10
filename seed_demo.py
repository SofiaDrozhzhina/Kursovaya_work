"""
Скрипт заполнения демо-данными (PostgreSQL).
Запуск: python seed_demo.py

Требует: pip install psycopg2-binary werkzeug
Убедитесь, что в app.py настроены переменные окружения БД или дефолтные значения.
"""
import psycopg2
import random
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash

DB_CONFIG = {
    "host":     "localhost",
    "port":     5432,
    "dbname":   "courses_db",
    "user":     "postgres",
    "password": "1234",
}

def seed():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    c = conn.cursor()

    now = datetime.now()

    # ── Таблицы (если ещё не созданы) ──────────────────────
    c.execute(open("init_db.sql").read().split("--  Администратор")[0])  # only DDL part

    # ── Удалить старый дефолтный admin и пересоздать ────────
    c.execute("DELETE FROM users WHERE username='admin'")
    c.execute("""
        INSERT INTO users (username,password,role,full_name,email)
        VALUES (%s,%s,'admin',%s,%s)
    """, ('admin', generate_password_hash('admin123'), 'Администратор', 'admin@courses.ru'))
    conn.commit()
    print("✓ Администратор: admin / admin123")

    # ── Преподаватели ────────────────────────────────────────
    teachers_data = [
        ("teacher1","Иванова Мария Сергеевна","maria@uni.ru","Кафедра ИТ","Кандидат наук"),
        ("teacher2","Петров Алексей Викторович","petrov@uni.ru","Кафедра математики","Доктор наук"),
        ("teacher3","Сидорова Елена Николаевна","sidorova@uni.ru","Кафедра ИТ","Кандидат наук"),
    ]
    teacher_ids = []
    for uname, fname, email, dept, degree in teachers_data:
        c.execute("DELETE FROM users WHERE username=%s", (uname,))
        c.execute("""
            INSERT INTO users (username,password,role,full_name,email)
            VALUES (%s,%s,'teacher',%s,%s) RETURNING id
        """, (uname, generate_password_hash('pass123'), fname, email))
        uid = c.fetchone()[0]
        c.execute("INSERT INTO teachers (user_id,department,degree) VALUES (%s,%s,%s) RETURNING id",
                  (uid, dept, degree))
        teacher_ids.append(c.fetchone()[0])
        print(f"✓ Преподаватель: {fname}")
    conn.commit()

    # ── Студенты ─────────────────────────────────────────────
    students_info = [
        ("student1","Смирнова Анна Павловна","ИС-21"),
        ("student2","Козлов Дмитрий Игоревич","ИС-21"),
        ("student3","Новикова Ольга Степановна","ИС-22"),
        ("student4","Федоров Иван Андреевич","ИС-22"),
        ("student5","Морозов Сергей Николаевич","ПМ-21"),
        ("student6","Волкова Татьяна Юрьевна","ПМ-21"),
        ("student7","Лебедев Кирилл Олегович","ПМ-22"),
        ("student8","Соколова Виктория Денисовна","ИС-21"),
    ]
    student_ids = []
    for uname, fname, group in students_info:
        c.execute("DELETE FROM users WHERE username=%s", (uname,))
        c.execute("""
            INSERT INTO users (username,password,role,full_name,email)
            VALUES (%s,%s,'student',%s,%s) RETURNING id
        """, (uname, generate_password_hash('pass123'), fname, f"{uname}@stud.ru"))
        uid = c.fetchone()[0]
        c.execute("INSERT INTO students (user_id,group_name,enrollment_year) VALUES (%s,%s,%s) RETURNING id",
                  (uid, group, random.choice([2021, 2022, 2023])))
        student_ids.append(c.fetchone()[0])
        print(f"✓ Студент: {fname} ({group})")
    conn.commit()

    # ── Курсы ────────────────────────────────────────────────
    courses_data = [
        ("Основы Python","Введение в программирование на Python с нуля",0,25),
        ("Базы данных","SQL, проектирование БД, PostgreSQL",0,20),
        ("Веб-разработка","HTML, CSS, JavaScript, Flask",1,30),
        ("Математический анализ","Пределы, производные, интегралы",1,35),
        ("Линейная алгебра","Матрицы, векторные пространства",1,30),
        ("Машинное обучение","Алгоритмы ML, scikit-learn, pandas",2,20),
    ]
    course_ids = []
    for title, desc, tidx, max_s in courses_data:
        tid = teacher_ids[tidx] if tidx < len(teacher_ids) else None
        c.execute("""
            INSERT INTO courses (title,description,teacher_id,max_students,created_at)
            VALUES (%s,%s,%s,%s,%s) RETURNING id
        """, (title, desc, tid, max_s, now - timedelta(days=random.randint(30,180))))
        course_ids.append(c.fetchone()[0])
        print(f"✓ Курс: {title}")
    conn.commit()

    # ── Записи и оценки ──────────────────────────────────────
    comments = ["Отличная работа!","Хорошее выполнение","Нужно улучшить",
                "Молодец!","","Хороший прогресс"]
    for sid in student_ids:
        for cid in random.sample(course_ids, k=random.randint(2,4)):
            try:
                enroll_date = now - timedelta(days=random.randint(10,90))
                c.execute("""
                    INSERT INTO enrollments (student_id,course_id,enrolled_at,status)
                    VALUES (%s,%s,%s,'active') RETURNING id
                """, (sid, cid, enroll_date))
                eid = c.fetchone()[0]
                if random.random() < 0.72:
                    grade = round(random.uniform(52,100), 1)
                    c.execute("""
                        INSERT INTO grades (enrollment_id,grade,comment,graded_at)
                        VALUES (%s,%s,%s,%s)
                    """, (eid, grade, random.choice(comments), now - timedelta(days=random.randint(1,30))))
                    c.execute("UPDATE enrollments SET status='completed' WHERE id=%s", (eid,))
            except psycopg2.errors.UniqueViolation:
                conn.rollback()
    conn.commit()
    conn.close()

    print()
    print("=" * 55)
    print("  ✅  Демо-данные успешно загружены!")
    print("=" * 55)
    print("  Администратор : admin      (пароль: admin123)")
    print("  Преподаватели : teacher1-3 (пароль: pass123)")
    print("  Студенты      : student1-8 (пароль: pass123)")
    print("=" * 55)

if __name__ == "__main__":
    seed()
