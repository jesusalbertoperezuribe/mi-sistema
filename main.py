"""
AulaFlow - Sistema integral de gestion academica.

Aplicacion de consola sin dependencias externas para administrar estudiantes,
cursos, tareas, biblioteca y reportes de rendimiento. Usa SQLite para que la
informacion sobreviva al cierre del programa.

Ejecutar:
	python main.py

Modo demostracion:
	python main.py --demo
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Optional


APP_NAME = "AULAFLOW"
DB_FILE = Path(__file__).with_name("aulaflow.db")
EXPORT_DIR = Path(__file__).with_name("reportes")


def now_text() -> str:
	return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_text() -> str:
	return date.today().isoformat()


def clean(value: str) -> str:
	return " ".join(value.strip().split())


def money(value: float) -> str:
	return f"${value:,.2f}"


def password_hash(password: str) -> str:
	return hashlib.sha256(password.encode("utf-8")).hexdigest()


def title(text: str) -> None:
	print("\n" + "=" * 76)
	print(f"  {text}")
	print("=" * 76)


def line() -> None:
	print("-" * 76)


def pause() -> None:
	input("\nPresiona ENTER para continuar...")


def ask(prompt: str, default: str = "") -> str:
	suffix = f" [{default}]" if default else ""
	answer = input(f"{prompt}{suffix}: ").strip()
	return answer or default


def ask_int(prompt: str, default: Optional[int] = None) -> Optional[int]:
	while True:
		raw = ask(prompt, "" if default is None else str(default))
		if not raw:
			return None
		try:
			return int(raw)
		except ValueError:
			print("Ingresa un numero entero valido.")


def ask_float(prompt: str, default: Optional[float] = None) -> Optional[float]:
	while True:
		raw = ask(prompt, "" if default is None else str(default))
		if not raw:
			return None
		try:
			return float(raw.replace(",", "."))
		except ValueError:
			print("Ingresa un numero valido.")


@dataclass
class Session:
	user_id: int
	username: str
	full_name: str
	role: str


class Database:
	"""Capa pequena y explicita de persistencia para mantener el sistema claro."""

	def __init__(self, path: Path = DB_FILE) -> None:
		self.path = path
		self.connection = sqlite3.connect(path)
		self.connection.row_factory = sqlite3.Row
		self.connection.execute("PRAGMA foreign_keys = ON")
		self.create_schema()

	def close(self) -> None:
		self.connection.close()

	def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
		cursor = self.connection.execute(sql, tuple(params))
		self.connection.commit()
		return cursor

	def query(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
		return list(self.connection.execute(sql, tuple(params)).fetchall())

	def one(self, sql: str, params: Iterable[Any] = ()) -> Optional[sqlite3.Row]:
		return self.connection.execute(sql, tuple(params)).fetchone()

	def create_schema(self) -> None:
		self.connection.executescript(
			"""
			CREATE TABLE IF NOT EXISTS users (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				username TEXT UNIQUE NOT NULL,
				password TEXT NOT NULL,
				full_name TEXT NOT NULL,
				role TEXT NOT NULL DEFAULT 'teacher',
				active INTEGER NOT NULL DEFAULT 1,
				created_at TEXT NOT NULL
			);
			CREATE TABLE IF NOT EXISTS students (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				code TEXT UNIQUE NOT NULL,
				full_name TEXT NOT NULL,
				email TEXT UNIQUE NOT NULL,
				phone TEXT DEFAULT '',
				program TEXT NOT NULL,
				semester INTEGER NOT NULL DEFAULT 1,
				status TEXT NOT NULL DEFAULT 'active',
				created_at TEXT NOT NULL
			);
			CREATE TABLE IF NOT EXISTS courses (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				code TEXT UNIQUE NOT NULL,
				name TEXT NOT NULL,
				teacher TEXT NOT NULL,
				credits INTEGER NOT NULL DEFAULT 3,
				room TEXT DEFAULT '',
				schedule TEXT DEFAULT '',
				active INTEGER NOT NULL DEFAULT 1
			);
			CREATE TABLE IF NOT EXISTS enrollments (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				student_id INTEGER NOT NULL REFERENCES students(id),
				course_id INTEGER NOT NULL REFERENCES courses(id),
				enrolled_at TEXT NOT NULL,
				UNIQUE(student_id, course_id)
			);
			CREATE TABLE IF NOT EXISTS grades (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				enrollment_id INTEGER NOT NULL REFERENCES enrollments(id),
				label TEXT NOT NULL,
				score REAL NOT NULL CHECK(score >= 0 AND score <= 5),
				weight REAL NOT NULL DEFAULT 1,
				recorded_at TEXT NOT NULL
			);
			CREATE TABLE IF NOT EXISTS assignments (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				course_id INTEGER NOT NULL REFERENCES courses(id),
				title TEXT NOT NULL,
				description TEXT DEFAULT '',
				due_date TEXT NOT NULL,
				max_score REAL NOT NULL DEFAULT 5,
				status TEXT NOT NULL DEFAULT 'open'
			);
			CREATE TABLE IF NOT EXISTS books (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				isbn TEXT UNIQUE NOT NULL,
				title TEXT NOT NULL,
				author TEXT NOT NULL,
				category TEXT NOT NULL,
				total INTEGER NOT NULL DEFAULT 1,
				available INTEGER NOT NULL DEFAULT 1
			);
			CREATE TABLE IF NOT EXISTS loans (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				book_id INTEGER NOT NULL REFERENCES books(id),
				student_id INTEGER NOT NULL REFERENCES students(id),
				loaned_at TEXT NOT NULL,
				due_date TEXT NOT NULL,
				returned_at TEXT,
				fine REAL NOT NULL DEFAULT 0
			);
			CREATE TABLE IF NOT EXISTS activity_log (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				user_id INTEGER REFERENCES users(id),
				action TEXT NOT NULL,
				details TEXT NOT NULL,
				created_at TEXT NOT NULL
			);
			"""
		)
		self.connection.commit()

	def log(self, session: Optional[Session], action: str, details: str) -> None:
		user_id = session.user_id if session else None
		self.execute(
			"INSERT INTO activity_log(user_id, action, details, created_at) VALUES (?, ?, ?, ?)",
			(user_id, action, details, now_text()),
		)

	def count(self, table: str) -> int:
		allowed = {"students", "courses", "books", "assignments", "loans"}
		if table not in allowed:
			raise ValueError("Tabla no permitida")
		row = self.one(f"SELECT COUNT(*) AS total FROM {table}")
		return int(row["total"]) if row else 0


class AuthService:
	def __init__(self, db: Database) -> None:
		self.db = db

	def ensure_admin(self) -> None:
		if self.db.one("SELECT id FROM users LIMIT 1") is None:
			self.db.execute(
				"INSERT INTO users(username, password, full_name, role, created_at) VALUES (?, ?, ?, ?, ?)",
				("admin", password_hash("admin123"), "Administrador AulaFlow", "admin", now_text()),
			)

	def login(self) -> Optional[Session]:
		title("INICIO DE SESION")
		print("Usuario demo: admin | Clave demo: admin123")
		username = ask("Usuario")
		password = ask("Clave")
		user = self.db.one(
			"SELECT * FROM users WHERE username = ? AND password = ? AND active = 1",
			(username, password_hash(password)),
		)
		if not user:
			print("\nCredenciales invalidas.")
			return None
		return Session(user["id"], user["username"], user["full_name"], user["role"])

	def create_user(self, session: Session) -> None:
		title("CREAR USUARIO")
		username = clean(ask("Nombre de usuario"))
		full_name = clean(ask("Nombre completo"))
		role = ask("Rol (admin/teacher)", "teacher")
		password = ask("Clave temporal", "campus123")
		if not username or not full_name:
			print("Los campos principales son obligatorios.")
			return
		try:
			self.db.execute(
				"INSERT INTO users(username, password, full_name, role, created_at) VALUES (?, ?, ?, ?, ?)",
				(username, password_hash(password), full_name, role, now_text()),
			)
			self.db.log(session, "CREATE_USER", username)
			print("Usuario creado correctamente.")
		except sqlite3.IntegrityError:
			print("Ese nombre de usuario ya existe.")


class StudentService:
	def __init__(self, db: Database) -> None:
		self.db = db

	def create(self, session: Session) -> None:
		title("REGISTRAR ESTUDIANTE")
		code = clean(ask("Codigo estudiantil")).upper()
		name = clean(ask("Nombre completo"))
		email = clean(ask("Correo"))
		phone = clean(ask("Telefono"))
		program = clean(ask("Programa academico"))
		semester = ask_int("Semestre", 1) or 1
		if not all((code, name, email, program)):
			print("Codigo, nombre, correo y programa son obligatorios.")
			return
		try:
			self.db.execute(
				"INSERT INTO students(code, full_name, email, phone, program, semester, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
				(code, name, email, phone, program, semester, now_text()),
			)
			self.db.log(session, "CREATE_STUDENT", code)
			print("Estudiante registrado.")
		except sqlite3.IntegrityError:
			print("El codigo o correo ya esta registrado.")

	def list_all(self, search: str = "") -> list[sqlite3.Row]:
		pattern = f"%{search}%"
		return self.db.query(
			"SELECT * FROM students WHERE full_name LIKE ? OR code LIKE ? OR program LIKE ? ORDER BY full_name",
			(pattern, pattern, pattern),
		)

	def show(self, search: str = "") -> None:
		title("ESTUDIANTES")
		rows = self.list_all(search)
		if not rows:
			print("No hay estudiantes que coincidan.")
			return
		print(f"{'ID':<4} {'CODIGO':<12} {'NOMBRE':<28} {'PROGRAMA':<18} {'SEM':<4} {'ESTADO'}")
		line()
		for row in rows:
			print(f"{row['id']:<4} {row['code']:<12} {row['full_name'][:27]:<28} {row['program'][:17]:<18} {row['semester']:<4} {row['status']}")

	def get(self, student_id: int) -> Optional[sqlite3.Row]:
		return self.db.one("SELECT * FROM students WHERE id = ?", (student_id,))

	def profile(self, student_id: int) -> None:
		student = self.get(student_id)
		if not student:
			print("Estudiante no encontrado.")
			return
		title(f"PERFIL: {student['full_name']}")
		print(f"Codigo: {student['code']}   Correo: {student['email']}")
		print(f"Programa: {student['program']}   Semestre: {student['semester']}")
		print(f"Estado: {student['status']}")
		courses = self.db.query(
			"""SELECT c.code, c.name, COALESCE(AVG(g.score), 0) AS average
			   FROM enrollments e JOIN courses c ON c.id=e.course_id
			   LEFT JOIN grades g ON g.enrollment_id=e.id
			   WHERE e.student_id=? GROUP BY e.id ORDER BY c.name""",
			(student_id,),
		)
		line()
		print("CURSOS INSCRITOS")
		for course in courses:
			print(f"  {course['code']:<10} {course['name']:<35} Promedio: {course['average']:.2f}")

	def change_status(self, session: Session) -> None:
		self.show()
		student_id = ask_int("ID del estudiante")
		if not student_id or not self.get(student_id):
			print("ID invalido.")
			return
		status = ask("Estado (active/inactive/graduated)", "active")
		self.db.execute("UPDATE students SET status=? WHERE id=?", (status, student_id))
		self.db.log(session, "UPDATE_STUDENT_STATUS", str(student_id))
		print("Estado actualizado.")


class AcademicService:
	def __init__(self, db: Database, students: StudentService) -> None:
		self.db = db
		self.students = students

	def create_course(self, session: Session) -> None:
		title("CREAR CURSO")
		code = clean(ask("Codigo del curso")).upper()
		name = clean(ask("Nombre del curso"))
		teacher = clean(ask("Docente"))
		credits = ask_int("Creditos", 3) or 3
		room = clean(ask("Aula"))
		schedule = clean(ask("Horario"))
		try:
			self.db.execute(
				"INSERT INTO courses(code, name, teacher, credits, room, schedule) VALUES (?, ?, ?, ?, ?, ?)",
				(code, name, teacher, credits, room, schedule),
			)
			self.db.log(session, "CREATE_COURSE", code)
			print("Curso creado.")
		except sqlite3.IntegrityError:
			print("El codigo del curso ya existe.")

	def list_courses(self) -> list[sqlite3.Row]:
		return self.db.query(
			"SELECT c.*, COUNT(e.id) AS students_count FROM courses c LEFT JOIN enrollments e ON e.course_id=c.id GROUP BY c.id ORDER BY c.name"
		)

	def show_courses(self) -> None:
		title("CATALOGO DE CURSOS")
		rows = self.list_courses()
		if not rows:
			print("No hay cursos creados.")
			return
		print(f"{'ID':<4} {'CODIGO':<10} {'CURSO':<30} {'DOCENTE':<22} {'EST':<4} {'CRED'}")
		line()
		for row in rows:
			print(f"{row['id']:<4} {row['code']:<10} {row['name'][:29]:<30} {row['teacher'][:21]:<22} {row['students_count']:<4} {row['credits']}")

	def enroll(self, session: Session) -> None:
		self.students.show()
		student_id = ask_int("ID estudiante")
		self.show_courses()
		course_id = ask_int("ID curso")
		if not student_id or not course_id:
			print("Datos incompletos.")
			return
		try:
			self.db.execute(
				"INSERT INTO enrollments(student_id, course_id, enrolled_at) VALUES (?, ?, ?)",
				(student_id, course_id, now_text()),
			)
			self.db.log(session, "ENROLLMENT", f"student={student_id}, course={course_id}")
			print("Inscripcion realizada.")
		except sqlite3.IntegrityError:
			print("El estudiante ya esta inscrito o alguno de los IDs no existe.")

	def record_grade(self, session: Session) -> None:
		title("REGISTRAR NOTA")
		student_id = ask_int("ID estudiante")
		if not student_id or not self.students.get(student_id):
			print("Estudiante no encontrado.")
			return
		rows = self.db.query(
			"SELECT e.id, c.code, c.name FROM enrollments e JOIN courses c ON c.id=e.course_id WHERE e.student_id=?",
			(student_id,),
		)
		for row in rows:
			print(f"{row['id']}: {row['code']} - {row['name']}")
		enrollment_id = ask_int("ID de inscripcion")
		label = clean(ask("Actividad (parcial, proyecto, etc.)"))
		score = ask_float("Nota (0 a 5)")
		weight = ask_float("Peso", 1) or 1
		if enrollment_id and label and score is not None and 0 <= score <= 5:
			try:
				self.db.execute(
					"INSERT INTO grades(enrollment_id, label, score, weight, recorded_at) VALUES (?, ?, ?, ?, ?)",
					(enrollment_id, label, score, weight, now_text()),
				)
				self.db.log(session, "RECORD_GRADE", str(enrollment_id))
				print("Nota registrada.")
			except sqlite3.IntegrityError:
				print("La inscripcion indicada no existe.")
		else:
			print("Nota invalida. Debe estar entre 0 y 5.")

	def create_assignment(self, session: Session) -> None:
		self.show_courses()
		course_id = ask_int("ID del curso")
		assignment_title = clean(ask("Titulo de la tarea"))
		description = clean(ask("Descripcion"))
		due_date = ask("Fecha limite (AAAA-MM-DD)", (date.today() + timedelta(days=7)).isoformat())
		max_score = ask_float("Puntaje maximo", 5) or 5
		try:
			datetime.strptime(due_date, "%Y-%m-%d")
			self.db.execute(
				"INSERT INTO assignments(course_id, title, description, due_date, max_score) VALUES (?, ?, ?, ?, ?)",
				(course_id, assignment_title, description, due_date, max_score),
			)
			self.db.log(session, "CREATE_ASSIGNMENT", assignment_title)
			print("Tarea publicada.")
		except (ValueError, sqlite3.IntegrityError):
			print("Fecha o curso invalido.")

	def show_assignments(self) -> None:
		title("TAREAS Y FECHAS")
		rows = self.db.query(
			"SELECT a.*, c.code, c.name FROM assignments a JOIN courses c ON c.id=a.course_id ORDER BY a.due_date"
		)
		for row in rows:
			overdue = " VENCIDA" if row["due_date"] < today_text() and row["status"] == "open" else ""
			print(f"#{row['id']} [{row['code']}] {row['title']} | limite: {row['due_date']} | max: {row['max_score']}{overdue}")
			print(f"    {row['description']}")
		if not rows:
			print("No hay tareas registradas.")


class LibraryService:
	def __init__(self, db: Database, students: StudentService) -> None:
		self.db = db
		self.students = students

	def add_book(self, session: Session) -> None:
		title("AGREGAR LIBRO")
		isbn = clean(ask("ISBN"))
		book_title = clean(ask("Titulo"))
		author = clean(ask("Autor"))
		category = clean(ask("Categoria"))
		total = ask_int("Cantidad", 1) or 1
		try:
			self.db.execute(
				"INSERT INTO books(isbn, title, author, category, total, available) VALUES (?, ?, ?, ?, ?, ?)",
				(isbn, book_title, author, category, total, total),
			)
			self.db.log(session, "ADD_BOOK", isbn)
			print("Libro agregado al catalogo.")
		except sqlite3.IntegrityError:
			print("Ese ISBN ya existe.")

	def show_books(self, search: str = "") -> None:
		title("CATALOGO DE BIBLIOTECA")
		pattern = f"%{search}%"
		rows = self.db.query(
			"SELECT * FROM books WHERE title LIKE ? OR author LIKE ? OR category LIKE ? ORDER BY title",
			(pattern, pattern, pattern),
		)
		print(f"{'ID':<4} {'ISBN':<16} {'TITULO':<30} {'AUTOR':<20} {'DISP/TOT'}")
		line()
		for row in rows:
			print(f"{row['id']:<4} {row['isbn']:<16} {row['title'][:29]:<30} {row['author'][:19]:<20} {row['available']}/{row['total']}")
		if not rows:
			print("No hay libros que coincidan.")

	def loan(self, session: Session) -> None:
		self.show_books()
		book_id = ask_int("ID del libro")
		self.students.show()
		student_id = ask_int("ID del estudiante")
		days = ask_int("Dias de prestamo", 14) or 14
		book = self.db.one("SELECT * FROM books WHERE id=? AND available > 0", (book_id,)) if book_id else None
		student = self.students.get(student_id) if student_id else None
		if not book or not student:
			print("Libro sin disponibilidad o estudiante invalido.")
			return
		due_date = (date.today() + timedelta(days=days)).isoformat()
		self.db.execute(
			"INSERT INTO loans(book_id, student_id, loaned_at, due_date) VALUES (?, ?, ?, ?)",
			(book_id, student_id, today_text(), due_date),
		)
		self.db.execute("UPDATE books SET available=available-1 WHERE id=?", (book_id,))
		self.db.log(session, "BOOK_LOAN", f"book={book_id}, student={student_id}")
		print(f"Prestamo creado. Fecha limite: {due_date}")

	def return_book(self, session: Session) -> None:
		rows = self.db.query(
			"""SELECT l.id, b.title, s.full_name, l.due_date FROM loans l
			   JOIN books b ON b.id=l.book_id JOIN students s ON s.id=l.student_id
			   WHERE l.returned_at IS NULL ORDER BY l.due_date"""
		)
		title("PRESTAMOS ABIERTOS")
		for row in rows:
			print(f"#{row['id']} | {row['title'][:32]} | {row['full_name'][:25]} | limite {row['due_date']}")
		loan_id = ask_int("ID del prestamo")
		loan = self.db.one("SELECT * FROM loans WHERE id=? AND returned_at IS NULL", (loan_id,)) if loan_id else None
		if not loan:
			print("Prestamo no encontrado.")
			return
		overdue_days = max(0, (date.today() - date.fromisoformat(loan["due_date"])).days)
		fine = overdue_days * 0.75
		self.db.execute("UPDATE loans SET returned_at=?, fine=? WHERE id=?", (today_text(), fine, loan_id))
		self.db.execute("UPDATE books SET available=available+1 WHERE id=?", (loan["book_id"],))
		self.db.log(session, "BOOK_RETURN", str(loan_id))
		print(f"Devolucion registrada. Multa: {money(fine)}")

	def active_loans(self) -> list[sqlite3.Row]:
		return self.db.query(
			"""SELECT l.*, b.title, s.full_name FROM loans l JOIN books b ON b.id=l.book_id
			   JOIN students s ON s.id=l.student_id WHERE l.returned_at IS NULL ORDER BY l.due_date"""
		)


class ReportService:
	def __init__(self, db: Database) -> None:
		self.db = db

	def dashboard(self) -> None:
		title("DASHBOARD EJECUTIVO")
		stats = [
			("Estudiantes activos", self.db.one("SELECT COUNT(*) AS n FROM students WHERE status='active'")["n"]),
			("Cursos creados", self.db.count("courses")),
			("Tareas publicadas", self.db.count("assignments")),
			("Libros en catalogo", self.db.count("books")),
			("Prestamos activos", len(self.db.query("SELECT id FROM loans WHERE returned_at IS NULL"))),
		]
		for label, value in stats:
			print(f"  {label:<30} {value}")
		line()
		print("RENDIMIENTO POR CURSO")
		rows = self.db.query(
			"""SELECT c.code, c.name, COUNT(DISTINCT e.student_id) AS enrolled,
					  COALESCE(AVG(g.score), 0) AS average
			   FROM courses c LEFT JOIN enrollments e ON e.course_id=c.id
			   LEFT JOIN grades g ON g.enrollment_id=e.id GROUP BY c.id ORDER BY average DESC"""
		)
		for row in rows:
			bar = "#" * int(float(row["average"]) * 4)
			print(f"  {row['code']:<8} {row['name'][:24]:<25} {row['average']:.2f} [{bar}]")
		if not rows:
			print("  Todavia no hay cursos con datos.")

	def student_ranking(self) -> None:
		title("RANKING DE ESTUDIANTES")
		rows = self.db.query(
			"""SELECT s.code, s.full_name, s.program, COALESCE(AVG(g.score), 0) AS average,
					  COUNT(DISTINCT e.course_id) AS courses
			   FROM students s LEFT JOIN enrollments e ON e.student_id=s.id
			   LEFT JOIN grades g ON g.enrollment_id=e.id
			   GROUP BY s.id ORDER BY average DESC, s.full_name"""
		)
		print(f"{'#':<4} {'CODIGO':<12} {'ESTUDIANTE':<28} {'CURSOS':<8} {'PROMEDIO'}")
		line()
		for index, row in enumerate(rows, 1):
			print(f"{index:<4} {row['code']:<12} {row['full_name'][:27]:<28} {row['courses']:<8} {row['average']:.2f}")

	def attendance_summary(self) -> None:
		title("RESUMEN OPERATIVO")
		overdue = self.db.query(
			"SELECT COUNT(*) AS total FROM loans WHERE returned_at IS NULL AND due_date < ?", (today_text(),)
		)[0]["total"]
		pending = self.db.query("SELECT COUNT(*) AS total FROM assignments WHERE status='open' AND due_date >= ?", (today_text(),))[0]["total"]
		inactive = self.db.query("SELECT COUNT(*) AS total FROM students WHERE status != 'active'")[0]["total"]
		print(f"Prestamos vencidos: {overdue}")
		print(f"Tareas pendientes: {pending}")
		print(f"Estudiantes no activos: {inactive}")
		print(f"Base de datos: {DB_FILE}")

	def export_csv(self, entity: str) -> Optional[Path]:
		queries = {
			"students": "SELECT code, full_name, email, phone, program, semester, status FROM students ORDER BY full_name",
			"courses": "SELECT code, name, teacher, credits, room, schedule FROM courses ORDER BY name",
			"books": "SELECT isbn, title, author, category, total, available FROM books ORDER BY title",
			"loans": "SELECT l.id, b.title, s.full_name, l.loaned_at, l.due_date, l.returned_at, l.fine FROM loans l JOIN books b ON b.id=l.book_id JOIN students s ON s.id=l.student_id",
		}
		if entity not in queries:
			return None
		rows = self.db.query(queries[entity])
		EXPORT_DIR.mkdir(exist_ok=True)
		path = EXPORT_DIR / f"{entity}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
		with path.open("w", newline="", encoding="utf-8") as file:
			writer = csv.writer(file)
			if rows:
				writer.writerow(rows[0].keys())
				writer.writerows([tuple(row) for row in rows])
		return path


class DemoData:
	def __init__(self, db: Database) -> None:
		self.db = db

	def load(self) -> None:
		if self.db.count("students") > 0:
			return
		students = [
			("A001", "Valentina Rojas", "valentina@aulaflow.edu", "3001112233", "Desarrollo de Software", 3),
			("A002", "Mateo Castillo", "mateo@aulaflow.edu", "3002223344", "Desarrollo de Software", 2),
			("A003", "Sofia Mendoza", "sofia@aulaflow.edu", "3003334455", "Analisis de Datos", 4),
			("A004", "Daniel Torres", "daniel@aulaflow.edu", "3004445566", "Ciberseguridad", 5),
		]
		for student in students:
			self.db.execute(
				"INSERT INTO students(code, full_name, email, phone, program, semester, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
				(*student, now_text()),
			)
		courses = [
			("PROG101", "Fundamentos de Programacion", "Laura Gomez", 4, "Lab 1", "Lun-Mie 8:00"),
			("DB202", "Bases de Datos", "Carlos Perez", 3, "Lab 2", "Mar-Jue 10:00"),
			("UX303", "Experiencia de Usuario", "Ana Ruiz", 3, "Aula 4", "Vie 14:00"),
		]
		for course in courses:
			self.db.execute("INSERT INTO courses(code, name, teacher, credits, room, schedule) VALUES (?, ?, ?, ?, ?, ?)", course)
		books = [
			("978-0132350884", "Clean Code", "Robert C. Martin", "Programacion", 3, 3),
			("978-1492051367", "Python Crash Course", "Eric Matthes", "Python", 2, 2),
			("978-0201633610", "Design Patterns", "Erich Gamma", "Arquitectura", 1, 1),
		]
		for book in books:
			self.db.execute("INSERT INTO books(isbn, title, author, category, total, available) VALUES (?, ?, ?, ?, ?, ?)", book)
		student_ids = [row["id"] for row in self.db.query("SELECT id FROM students ORDER BY id")]
		course_ids = [row["id"] for row in self.db.query("SELECT id FROM courses ORDER BY id")]
		for student_id, course_id in zip(student_ids, [course_ids[0], course_ids[0], course_ids[1], course_ids[2]]):
			self.db.execute("INSERT INTO enrollments(student_id, course_id, enrolled_at) VALUES (?, ?, ?)", (student_id, course_id, now_text()))
		enrollment_ids = [row["id"] for row in self.db.query("SELECT id FROM enrollments ORDER BY id")]
		for enrollment_id, label, score, weight in [(enrollment_ids[0], "Parcial", 4.6, 2), (enrollment_ids[0], "Proyecto", 4.8, 3), (enrollment_ids[1], "Parcial", 3.8, 2), (enrollment_ids[2], "Proyecto", 4.2, 3)]:
			self.db.execute("INSERT INTO grades(enrollment_id, label, score, weight, recorded_at) VALUES (?, ?, ?, ?, ?)", (enrollment_id, label, score, weight, now_text()))
		self.db.execute("INSERT INTO assignments(course_id, title, description, due_date, max_score) VALUES (?, ?, ?, ?, ?)", (course_ids[0], "API de biblioteca", "Construir endpoints CRUD con validaciones.", (date.today() + timedelta(days=5)).isoformat(), 5))
		self.db.execute("INSERT INTO assignments(course_id, title, description, due_date, max_score) VALUES (?, ?, ?, ?, ?)", (course_ids[1], "Modelo relacional", "Entregar diagrama normalizado.", (date.today() + timedelta(days=10)).isoformat(), 5))


class AulaFlow:
	def __init__(self) -> None:
		self.db = Database()
		self.auth = AuthService(self.db)
		self.students = StudentService(self.db)
		self.academic = AcademicService(self.db, self.students)
		self.library = LibraryService(self.db, self.students)
		self.reports = ReportService(self.db)
		self.auth.ensure_admin()

	def close(self) -> None:
		self.db.close()

	def run(self) -> None:
		title(f"{APP_NAME} | GESTION ACADEMICA")
		print("Una plataforma local para organizar el trabajo del campus.")
		session = self.auth.login()
		if not session:
			return
		while True:
			try:
				self.menu(session)
				option = ask("Selecciona una opcion")
				if option == "0":
					print("Sesion finalizada. Hasta pronto.")
					return
				self.handle(option, session)
			except KeyboardInterrupt:
				print("\nOperacion cancelada.")
			except sqlite3.Error as error:
				print(f"Error de base de datos: {error}")
			except Exception as error:
				print(f"No se pudo completar la operacion: {error}")
			pause()

	def menu(self, session: Session) -> None:
		title(f"PANEL PRINCIPAL | {session.full_name}")
		print("1. Dashboard ejecutivo")
		print("2. Gestionar estudiantes")
		print("3. Gestionar cursos e inscripciones")
		print("4. Gestionar tareas y notas")
		print("5. Biblioteca y prestamos")
		print("6. Reportes y exportacion")
		if session.role == "admin":
			print("7. Administracion de usuarios")
		print("0. Cerrar sesion")

	def handle(self, option: str, session: Session) -> None:
		actions = {
			"1": self.dashboard_menu,
			"2": self.students_menu,
			"3": self.courses_menu,
			"4": self.assignments_menu,
			"5": self.library_menu,
			"6": self.reports_menu,
		}
		if option in actions:
			actions[option](session)
		elif option == "7" and session.role == "admin":
			self.users_menu(session)
		else:
			print("Opcion no reconocida.")

	def dashboard_menu(self, session: Session) -> None:
		self.reports.dashboard()

	def students_menu(self, session: Session) -> None:
		while True:
			title("GESTION DE ESTUDIANTES")
			print("1. Listar estudiantes")
			print("2. Buscar estudiantes")
			print("3. Registrar estudiante")
			print("4. Ver perfil academico")
			print("5. Cambiar estado")
			print("0. Volver")
			option = ask("Opcion")
			if option == "0":
				return
			if option == "1":
				self.students.show()
			elif option == "2":
				self.students.show(ask("Texto de busqueda"))
			elif option == "3":
				self.students.create(session)
			elif option == "4":
				self.students.show()
				student_id = ask_int("ID")
				if student_id:
					self.students.profile(student_id)
			elif option == "5":
				self.students.change_status(session)
			else:
				print("Opcion no reconocida.")
			pause()

	def courses_menu(self, session: Session) -> None:
		while True:
			title("CURSOS E INSCRIPCIONES")
			print("1. Ver cursos")
			print("2. Crear curso")
			print("3. Inscribir estudiante")
			print("0. Volver")
			option = ask("Opcion")
			if option == "0":
				return
			if option == "1":
				self.academic.show_courses()
			elif option == "2":
				self.academic.create_course(session)
			elif option == "3":
				self.academic.enroll(session)
			else:
				print("Opcion no reconocida.")
			pause()

	def assignments_menu(self, session: Session) -> None:
		while True:
			title("TAREAS Y CALIFICACIONES")
			print("1. Ver tareas")
			print("2. Publicar tarea")
			print("3. Registrar nota")
			print("0. Volver")
			option = ask("Opcion")
			if option == "0":
				return
			if option == "1":
				self.academic.show_assignments()
			elif option == "2":
				self.academic.create_assignment(session)
			elif option == "3":
				self.academic.record_grade(session)
			else:
				print("Opcion no reconocida.")
			pause()

	def library_menu(self, session: Session) -> None:
		while True:
			title("BIBLIOTECA")
			print("1. Ver catalogo")
			print("2. Buscar libro")
			print("3. Agregar libro")
			print("4. Crear prestamo")
			print("5. Registrar devolucion")
			print("0. Volver")
			option = ask("Opcion")
			if option == "0":
				return
			if option == "1":
				self.library.show_books()
			elif option == "2":
				self.library.show_books(ask("Texto de busqueda"))
			elif option == "3":
				self.library.add_book(session)
			elif option == "4":
				self.library.loan(session)
			elif option == "5":
				self.library.return_book(session)
			else:
				print("Opcion no reconocida.")
			pause()

	def reports_menu(self, session: Session) -> None:
		while True:
			title("REPORTES Y EXPORTACION")
			print("1. Ranking de estudiantes")
			print("2. Resumen operativo")
			print("3. Exportar estudiantes CSV")
			print("4. Exportar cursos CSV")
			print("5. Exportar libros CSV")
			print("6. Exportar prestamos CSV")
			print("0. Volver")
			option = ask("Opcion")
			if option == "0":
				return
			if option == "1":
				self.reports.student_ranking()
			elif option == "2":
				self.reports.attendance_summary()
			elif option in {"3", "4", "5", "6"}:
				entity = {"3": "students", "4": "courses", "5": "books", "6": "loans"}[option]
				path = self.reports.export_csv(entity)
				print(f"Archivo creado: {path}")
			else:
				print("Opcion no reconocida.")
			pause()

	def users_menu(self, session: Session) -> None:
		while True:
			title("ADMINISTRACION")
			print("1. Crear usuario")
			print("2. Ver actividad reciente")
			print("0. Volver")
			option = ask("Opcion")
			if option == "0":
				return
			if option == "1":
				self.auth.create_user(session)
			elif option == "2":
				rows = self.db.query("SELECT created_at, action, details FROM activity_log ORDER BY id DESC LIMIT 15")
				for row in rows:
					print(f"{row['created_at']} | {row['action']:<22} | {row['details']}")
			else:
				print("Opcion no reconocida.")
			pause()


def run_demo() -> None:
	"""Ejecuta un recorrido no interactivo para comprobar que el sistema funciona."""
	db = Database()
	AuthService(db).ensure_admin()
	DemoData(db).load()
	print(f"{APP_NAME}: datos de demostracion listos")
	print(f"Estudiantes: {db.count('students')}")
	print(f"Cursos: {db.count('courses')}")
	print(f"Libros: {db.count('books')}")
	print(f"Tareas: {db.count('assignments')}")
	print("Base de datos:", DB_FILE)
	ReportService(db).dashboard()
	db.close()


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="AulaFlow - gestion academica")
	parser.add_argument("--demo", action="store_true", help="carga datos de ejemplo y muestra el dashboard")
	parser.add_argument("--reset-demo", action="store_true", help="borra la base local antes de cargar demo")
	return parser.parse_args()


def main() -> None:
	args = parse_args()
	if args.reset_demo and DB_FILE.exists():
		DB_FILE.unlink()
	if args.demo:
		run_demo()
		return
	app = AulaFlow()
	try:
		app.run()
	finally:
		app.close()


if __name__ == "__main__":
	main()
