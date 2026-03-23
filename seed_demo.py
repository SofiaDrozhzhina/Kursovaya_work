"""
Расширенный скрипт демо-данных для PostgreSQL.
Запуск: python seed_demo.py

Создаёт:
  - 1 администратор
  - 6 преподавателей (3 кафедры)
  - 20 студентов (4 группы)
  - 10 курсов
  - ~60 записей на курсы с оценками
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
    "password": "postgres",   # ← измените на свой пароль
}

def seed():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    c = conn.cursor()
    now = datetime.now()

    print("=" * 60)
    print("  Загрузка демо-данных...")
    print("=" * 60)

    # ── Очистка старых демо-данных ───────────────────────────
    print("\n[1/5] Очистка старых данных...")
    c.execute("DELETE FROM grades")
    c.execute("DELETE FROM enrollments")
    c.execute("DELETE FROM courses")
    c.execute("DELETE FROM teachers")
    c.execute("DELETE FROM students")
    c.execute("DELETE FROM users")
    conn.commit()
    print("      Готово.")

    # ── Администратор ────────────────────────────────────────
    print("\n[2/5] Создание пользователей...")
    c.execute("""
        INSERT INTO users (username, password, role, full_name, email, created_at)
        VALUES (%s,%s,'admin',%s,%s,%s) RETURNING id
    """, ('admin', generate_password_hash('admin123'),
          'Администратор Системы', 'admin@courses.ru', now))
    print("  ✓ Администратор: admin / admin123")

    # ── Преподаватели ────────────────────────────────────────
    teachers_data = [
        ("teacher1", "Иванова Мария Сергеевна",      "m.ivanova@uni.ru",   "Кафедра информационных технологий", "Кандидат технических наук"),
        ("teacher2", "Петров Алексей Викторович",    "a.petrov@uni.ru",    "Кафедра математики",                "Доктор физико-математических наук"),
        ("teacher3", "Сидорова Елена Николаевна",    "e.sidorova@uni.ru",  "Кафедра информационных технологий", "Кандидат педагогических наук"),
        ("teacher4", "Козлов Дмитрий Андреевич",     "d.kozlov@uni.ru",    "Кафедра математики",                "Кандидат технических наук"),
        ("teacher5", "Новикова Анна Павловна",        "a.novikova@uni.ru",  "Кафедра экономики и управления",    "Доктор экономических наук"),
        ("teacher6", "Фёдоров Игорь Станиславович",  "i.fedorov@uni.ru",   "Кафедра экономики и управления",    "Кандидат экономических наук"),
    ]
    teacher_ids = []
    for uname, fname, email, dept, degree in teachers_data:
        c.execute("""
            INSERT INTO users (username,password,role,full_name,email,created_at)
            VALUES (%s,%s,'teacher',%s,%s,%s) RETURNING id
        """, (uname, generate_password_hash('pass123'), fname, email,
              now - timedelta(days=random.randint(200, 500))))
        uid = c.fetchone()[0]
        c.execute("INSERT INTO teachers (user_id,department,degree) VALUES (%s,%s,%s) RETURNING id",
                  (uid, dept, degree))
        teacher_ids.append(c.fetchone()[0])
        print(f"  ✓ Преподаватель: {uname} — {fname}")
    conn.commit()

    # ── Студенты ─────────────────────────────────────────────
    students_data = [
        # ИС-21
        ("student1",  "Смирнова Анна Павловна",        "a.smirnova@stud.ru",   "ИС-21", 2021),
        ("student2",  "Козлов Дмитрий Игоревич",       "d.kozlov@stud.ru",     "ИС-21", 2021),
        ("student3",  "Новикова Ольга Степановна",      "o.novikova@stud.ru",   "ИС-21", 2021),
        ("student4",  "Соколова Виктория Денисовна",    "v.sokolova@stud.ru",   "ИС-21", 2021),
        ("student5",  "Лебедев Кирилл Олегович",        "k.lebedev@stud.ru",    "ИС-21", 2021),
        # ИС-22
        ("student6",  "Федоров Иван Андреевич",         "i.fedorov@stud.ru",    "ИС-22", 2022),
        ("student7",  "Морозова Татьяна Юрьевна",       "t.morozova@stud.ru",   "ИС-22", 2022),
        ("student8",  "Волков Сергей Николаевич",        "s.volkov@stud.ru",     "ИС-22", 2022),
        ("student9",  "Алексеева Дарья Михайловна",     "d.alekseeva@stud.ru",  "ИС-22", 2022),
        ("student10", "Тихонов Артём Васильевич",        "a.tikhonov@stud.ru",   "ИС-22", 2022),
        # ПМ-21
        ("student11", "Захарова Екатерина Романовна",   "e.zakharova@stud.ru",  "ПМ-21", 2021),
        ("student12", "Никитин Павел Сергеевич",         "p.nikitin@stud.ru",    "ПМ-21", 2021),
        ("student13", "Орлова Полина Александровна",     "p.orlova@stud.ru",     "ПМ-21", 2021),
        ("student14", "Степанов Максим Евгеньевич",      "m.stepanov@stud.ru",   "ПМ-21", 2021),
        ("student15", "Кузнецова Алина Вадимовна",       "a.kuznetsova@stud.ru", "ПМ-21", 2021),
        # ПМ-22
        ("student16", "Белов Антон Игоревич",            "a.belov@stud.ru",      "ПМ-22", 2022),
        ("student17", "Громова Юлия Константиновна",    "y.gromova@stud.ru",    "ПМ-22", 2022),
        ("student18", "Дмитриев Роман Олегович",         "r.dmitriev@stud.ru",   "ПМ-22", 2022),
        ("student19", "Ефимова Наталья Петровна",        "n.efimova@stud.ru",    "ПМ-22", 2022),
        ("student20", "Жуков Илья Владимирович",         "i.zhukov@stud.ru",     "ПМ-22", 2022),
    ]
    student_ids = []
    for uname, fname, email, group, year in students_data:
        c.execute("""
            INSERT INTO users (username,password,role,full_name,email,created_at)
            VALUES (%s,%s,'student',%s,%s,%s) RETURNING id
        """, (uname, generate_password_hash('pass123'), fname, email,
              now - timedelta(days=random.randint(30, 400))))
        uid = c.fetchone()[0]
        c.execute("INSERT INTO students (user_id,group_name,enrollment_year) VALUES (%s,%s,%s) RETURNING id",
                  (uid, group, year))
        student_ids.append(c.fetchone()[0])
        print(f"  ✓ Студент: {uname} — {fname} ({group})")
    conn.commit()

    # ── Курсы ────────────────────────────────────────────────
    print("\n[3/5] Создание курсов...")
    courses_data = [
        ("Основы Python",
         "Введение в программирование на языке Python. Типы данных, управляющие конструкции, функции, модули.",
         0, 20),
        ("Базы данных и SQL",
         "Реляционные базы данных, язык SQL, проектирование схем, работа с PostgreSQL.",
         0, 18),
        ("Веб-разработка на Flask",
         "Создание веб-приложений на Python: маршрутизация, шаблоны Jinja2, формы, сессии.",
         2, 15),
        ("Математический анализ",
         "Пределы, производные, интегралы, ряды. Практическое применение в информационных технологиях.",
         1, 25),
        ("Линейная алгебра",
         "Матрицы и определители, системы линейных уравнений, векторные пространства, собственные значения.",
         3, 25),
        ("Машинное обучение",
         "Алгоритмы классификации и регрессии, кластеризация, библиотеки scikit-learn и pandas.",
         0, 12),
        ("Экономика предприятия",
         "Основы экономической деятельности, финансовый анализ, бизнес-планирование.",
         4, 30),
        ("Управление проектами",
         "Методологии Agile и Scrum, планирование, управление рисками, работа с командой.",
         5, 20),
        ("Дискретная математика",
         "Теория множеств, комбинаторика, теория графов, булева алгебра.",
         1, 22),
        ("Алгоритмы и структуры данных",
         "Базовые алгоритмы сортировки и поиска, деревья, хеш-таблицы, граф-алгоритмы.",
         2, 18),
    ]
    course_ids = []
    for title, desc, tidx, max_s in courses_data:
        tid = teacher_ids[tidx] if tidx < len(teacher_ids) else None
        c.execute("""
            INSERT INTO courses (title, description, teacher_id, max_students, created_at)
            VALUES (%s,%s,%s,%s,%s) RETURNING id
        """, (title, desc, tid, max_s,
              now - timedelta(days=random.randint(60, 300))))
        course_ids.append(c.fetchone()[0])
        print(f"  ✓ Курс: {title} (макс. {max_s} студентов)")
    conn.commit()

    # ── Записи и оценки ──────────────────────────────────────
    print("\n[4/5] Генерация записей и оценок...")
    comments_good = [
        "Отличная работа, продолжайте в том же духе!",
        "Превосходное выполнение всех заданий.",
        "Глубокое понимание материала.",
        "Работа выполнена на высоком уровне.",
    ]
    comments_avg = [
        "Хорошее выполнение, есть небольшие недочёты.",
        "В целом верно, обратите внимание на детали.",
        "Неплохой результат, но можно лучше.",
        "Задание выполнено, есть возможности для улучшения.",
    ]
    comments_low = [
        "Необходимо доработать ряд разделов.",
        "Пересдача рекомендована.",
        "Слабое владение материалом, требуется повторение.",
        "Работа требует существенной доработки.",
    ]

    enrollment_count = 0
    grade_count = 0

    for sid in student_ids:
        # Каждый студент записан на 3-6 курсов
        chosen = random.sample(course_ids, k=random.randint(3, 6))
        for cid in chosen:
            enroll_date = now - timedelta(days=random.randint(14, 120))
            try:
                c.execute("""
                    INSERT INTO enrollments (student_id, course_id, enrolled_at, status)
                    VALUES (%s,%s,%s,'active') RETURNING id
                """, (sid, cid, enroll_date))
                eid = c.fetchone()[0]
                enrollment_count += 1

                # 80% вероятность получить оценку
                if random.random() < 0.80:
                    # Распределение: 30% отлично, 35% хорошо, 25% удовл., 10% неудовл.
                    r = random.random()
                    if r < 0.30:
                        grade = round(random.uniform(90, 100), 1)
                        comment = random.choice(comments_good)
                    elif r < 0.65:
                        grade = round(random.uniform(75, 89.9), 1)
                        comment = random.choice(comments_avg)
                    elif r < 0.90:
                        grade = round(random.uniform(60, 74.9), 1)
                        comment = random.choice(comments_avg)
                    else:
                        grade = round(random.uniform(20, 59.9), 1)
                        comment = random.choice(comments_low)

                    grade_date = enroll_date + timedelta(days=random.randint(7, 60))
                    c.execute("""
                        INSERT INTO grades (enrollment_id, grade, comment, graded_at)
                        VALUES (%s,%s,%s,%s)
                    """, (eid, grade, comment, grade_date))
                    c.execute("UPDATE enrollments SET status='completed' WHERE id=%s", (eid,))
                    grade_count += 1

            except psycopg2.errors.UniqueViolation:
                conn.rollback()
                continue

    conn.commit()
    print(f"  ✓ Создано записей: {enrollment_count}")
    print(f"  ✓ Выставлено оценок: {grade_count}")

    # ── Итоговая статистика ──────────────────────────────────
    print("\n[5/5] Проверка данных...")
    c.execute("SELECT COUNT(*) FROM users")
    print(f"  Пользователей: {c.fetchone()[0]}")
    c.execute("SELECT COUNT(*) FROM students")
    print(f"  Студентов: {c.fetchone()[0]}")
    c.execute("SELECT COUNT(*) FROM teachers")
    print(f"  Преподавателей: {c.fetchone()[0]}")
    c.execute("SELECT COUNT(*) FROM courses")
    print(f"  Курсов: {c.fetchone()[0]}")
    c.execute("SELECT COUNT(*) FROM enrollments")
    print(f"  Записей на курсы: {c.fetchone()[0]}")
    c.execute("SELECT COUNT(*), ROUND(AVG(grade)::numeric,1) FROM grades")
    row = c.fetchone()
    print(f"  Оценок: {row[0]}, средний балл: {row[1]}")

    conn.close()

    print()
    print("=" * 60)
    print("  ✅  Демо-данные успешно загружены!")
    print("=" * 60)
    print("  👑 Администратор : admin       (пароль: admin123)")
    print("  🎓 Преподаватели : teacher1-6  (пароль: pass123)")
    print("  🎒 Студенты      : student1-20 (пароль: pass123)")
    print("=" * 60)

if __name__ == "__main__":
    seed()
