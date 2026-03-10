-- ============================================================
--  Система управления курсами — PostgreSQL Schema
--  Запуск: psql -U postgres -d courses_db -f init_db.sql
-- ============================================================

-- Пользователи (все роли)
CREATE TABLE IF NOT EXISTS users (
    id         SERIAL PRIMARY KEY,
    username   VARCHAR(80)  UNIQUE NOT NULL,
    password   TEXT         NOT NULL,
    role       VARCHAR(20)  NOT NULL CHECK (role IN ('admin','teacher','student')),
    full_name  VARCHAR(200),
    email      VARCHAR(200),
    created_at TIMESTAMP    DEFAULT NOW()
);

-- Преподаватели (расширение users)
CREATE TABLE IF NOT EXISTS teachers (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    department VARCHAR(200),
    degree     VARCHAR(100)
);

-- Студенты (расширение users)
CREATE TABLE IF NOT EXISTS students (
    id               SERIAL PRIMARY KEY,
    user_id          INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    group_name       VARCHAR(50),
    enrollment_year  INTEGER
);

-- Курсы
CREATE TABLE IF NOT EXISTS courses (
    id           SERIAL PRIMARY KEY,
    title        VARCHAR(200) NOT NULL,
    description  TEXT,
    teacher_id   INTEGER REFERENCES teachers(id) ON DELETE SET NULL,
    max_students INTEGER      DEFAULT 30,
    created_at   TIMESTAMP    DEFAULT NOW()
);

-- Записи на курсы
CREATE TABLE IF NOT EXISTS enrollments (
    id          SERIAL PRIMARY KEY,
    student_id  INTEGER REFERENCES students(id) ON DELETE CASCADE,
    course_id   INTEGER REFERENCES courses(id)  ON DELETE CASCADE,
    enrolled_at TIMESTAMP DEFAULT NOW(),
    status      VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active','completed','dropped')),
    UNIQUE (student_id, course_id)
);

-- Оценки
CREATE TABLE IF NOT EXISTS grades (
    id            SERIAL PRIMARY KEY,
    enrollment_id INTEGER UNIQUE REFERENCES enrollments(id) ON DELETE CASCADE,
    grade         NUMERIC(5,2) CHECK (grade BETWEEN 0 AND 100),
    graded_at     TIMESTAMP DEFAULT NOW(),
    comment       TEXT
);

-- ============================================================
--  Администратор по умолчанию
--  Логин: admin | Пароль: admin123
-- ============================================================
INSERT INTO users (username, password, role, full_name, email)
VALUES (
    'admin',
    'scrypt:32768:8:1$salt$hash',   -- заменится через seed_demo.py
    'admin',
    'Администратор',
    'admin@courses.ru'
)
ON CONFLICT (username) DO NOTHING;
