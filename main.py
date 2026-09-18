"""AgroGestor: sistema de consola para administrar una finca pequena.

Proyecto educativo, sin dependencias externas. Incluye productores, lotes,
cultivos, labores, inventario, cosechas, ventas, gastos y reportes.
Ejecutar: python main.py | python main.py --demo | python main.py --reset --demo
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

APP = "AGROGESTOR"
DB = Path(__file__).with_name("agrogestor.db")


def now() -> str:
	return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today() -> str:
	return date.today().isoformat()


def text(value: str) -> str:
	return " ".join(value.strip().split())


def money(value: float) -> str:
	return f"${value:,.0f}"


def heading(value: str) -> None:
	print("\n" + "=" * 76)
	print(f"  {value}")
	print("=" * 76)


def separator() -> None:
	print("-" * 76)


def pause() -> None:
	input("\nPresiona ENTER para continuar...")


def ask(label: str, default: str = "") -> str:
	suffix = f" [{default}]" if default else ""
	value = input(f"{label}{suffix}: ").strip()
	return value or default


def ask_int(label: str, default: Optional[int] = None) -> Optional[int]:
	while True:
		value = ask(label, "" if default is None else str(default))
		if not value:
			return None
		try:
			return int(value)
		except ValueError:
			print("Escribe un numero entero valido.")


def ask_float(label: str, default: Optional[float] = None) -> Optional[float]:
	while True:
		value = ask(label, "" if default is None else str(default))
		if not value:
			return None
		try:
			return float(value.replace(",", "."))
		except ValueError:
			print("Escribe un numero valido.")


def is_date(value: str) -> bool:
	try:
		datetime.strptime(value, "%Y-%m-%d")
		return True
	except ValueError:
		return False


class Database:
	def __init__(self, path: Path = DB) -> None:
		self.connection = sqlite3.connect(path)
		self.connection.row_factory = sqlite3.Row
		self.connection.execute("PRAGMA foreign_keys = ON")
		self.create_schema()

	def close(self) -> None:
		self.connection.close()

	def execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
		cursor = self.connection.execute(sql, params)
		self.connection.commit()
		return cursor

	def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
		return list(self.connection.execute(sql, params).fetchall())

	def one(self, sql: str, params: tuple[Any, ...] = ()) -> Optional[sqlite3.Row]:
		return self.connection.execute(sql, params).fetchone()

	def count(self, table: str) -> int:
		allowed = {"people", "plots", "crops", "tasks", "supplies", "harvests", "sales", "expenses"}
		if table not in allowed:
			raise ValueError("Tabla no permitida")
		row = self.one(f"SELECT COUNT(*) total FROM {table}")
		return int(row["total"]) if row else 0

	def create_schema(self) -> None:
		self.connection.executescript(
			"""
			CREATE TABLE IF NOT EXISTS people(
			 id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
			 document TEXT UNIQUE NOT NULL, phone TEXT DEFAULT '',
			 email TEXT DEFAULT '', role TEXT DEFAULT 'trabajador', active INTEGER DEFAULT 1,
			 created_at TEXT NOT NULL);
			CREATE TABLE IF NOT EXISTS plots(
			 id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
			 area REAL NOT NULL, location TEXT DEFAULT '', soil TEXT DEFAULT '',
			 water TEXT DEFAULT '', status TEXT DEFAULT 'disponible');
			CREATE TABLE IF NOT EXISTS crops(
			 id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, variety TEXT DEFAULT '',
			 plot_id INTEGER NOT NULL REFERENCES plots(id), person_id INTEGER REFERENCES people(id),
			 planted TEXT NOT NULL, expected TEXT, area REAL NOT NULL,
			 status TEXT DEFAULT 'sembrado', notes TEXT DEFAULT '');
			CREATE TABLE IF NOT EXISTS tasks(
			 id INTEGER PRIMARY KEY AUTOINCREMENT, crop_id INTEGER REFERENCES crops(id),
			 person_id INTEGER REFERENCES people(id), title TEXT NOT NULL,
			 description TEXT DEFAULT '', due TEXT NOT NULL, status TEXT DEFAULT 'pendiente', cost REAL DEFAULT 0);
			CREATE TABLE IF NOT EXISTS supplies(
			 id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, category TEXT NOT NULL,
			 unit TEXT NOT NULL, quantity REAL DEFAULT 0, minimum REAL DEFAULT 0,
			 unit_cost REAL DEFAULT 0, supplier TEXT DEFAULT '');
			CREATE TABLE IF NOT EXISTS movements(
			 id INTEGER PRIMARY KEY AUTOINCREMENT, supply_id INTEGER NOT NULL REFERENCES supplies(id),
			 kind TEXT NOT NULL, quantity REAL NOT NULL, movement_date TEXT NOT NULL, note TEXT DEFAULT '');
			CREATE TABLE IF NOT EXISTS harvests(
			 id INTEGER PRIMARY KEY AUTOINCREMENT, crop_id INTEGER NOT NULL REFERENCES crops(id),
			 harvest_date TEXT NOT NULL, quantity REAL NOT NULL, unit TEXT NOT NULL,
			 quality TEXT DEFAULT 'Primera', unit_price REAL DEFAULT 0, note TEXT DEFAULT '');
			CREATE TABLE IF NOT EXISTS sales(
			 id INTEGER PRIMARY KEY AUTOINCREMENT, harvest_id INTEGER NOT NULL REFERENCES harvests(id),
			 customer TEXT NOT NULL, sale_date TEXT NOT NULL, quantity REAL NOT NULL,
			 unit_price REAL NOT NULL, payment TEXT DEFAULT 'pendiente');
			CREATE TABLE IF NOT EXISTS expenses(
			 id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT NOT NULL,
			 description TEXT NOT NULL, amount REAL NOT NULL, expense_date TEXT NOT NULL);
			CREATE TABLE IF NOT EXISTS activity(
			 id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL,
			 detail TEXT NOT NULL, created_at TEXT NOT NULL);
			"""
		)
		self.connection.commit()

	def log(self, action: str, detail: str) -> None:
		self.execute("INSERT INTO activity(action, detail, created_at) VALUES(?,?,?)", (action, detail, now()))


class People:
	def __init__(self, db: Database) -> None:
		self.db = db

	def get(self, identifier: int) -> Optional[sqlite3.Row]:
		return self.db.one("SELECT * FROM people WHERE id=?", (identifier,))

	def show(self, search: str = "") -> None:
		heading("PRODUCTORES Y TRABAJADORES")
		pattern = f"%{search}%"
		rows = self.db.query("SELECT * FROM people WHERE name LIKE ? OR document LIKE ? ORDER BY name", (pattern, pattern))
		print(f"{'ID':<4} {'NOMBRE':<27} {'DOCUMENTO':<14} {'ROL':<18} {'TELEFONO':<13} ESTADO")
		separator()
		for row in rows:
			state = "Activo" if row["active"] else "Inactivo"
			print(f"{row['id']:<4} {row['name'][:26]:<27} {row['document']:<14} {row['role'][:17]:<18} {row['phone'][:12]:<13} {state}")
		if not rows:
			print("No hay personas registradas.")

	def create(self) -> None:
		heading("NUEVA PERSONA")
		name = text(ask("Nombre completo"))
		document = text(ask("Documento"))
		phone = text(ask("Telefono"))
		email = text(ask("Correo"))
		role = text(ask("Rol", "trabajador"))
		if not name or not document:
			print("Nombre y documento son obligatorios.")
			return
		try:
			self.db.execute("INSERT INTO people(name,document,phone,email,role,created_at) VALUES(?,?,?,?,?,?)", (name, document, phone, email, role, now()))
			self.db.log("PERSONA_CREADA", name)
			print("Persona registrada.")
		except sqlite3.IntegrityError:
			print("El documento ya existe.")

	def toggle(self) -> None:
		self.show()
		identifier = ask_int("ID de la persona")
		person = self.get(identifier) if identifier else None
		if not person:
			print("Persona no encontrada.")
			return
		active = 0 if person["active"] else 1
		self.db.execute("UPDATE people SET active=? WHERE id=?", (active, identifier))
		self.db.log("PERSONA_ESTADO", str(identifier))
		print("Estado actualizado.")


class Plots:
	def __init__(self, db: Database) -> None:
		self.db = db

	def get(self, identifier: int) -> Optional[sqlite3.Row]:
		return self.db.one("SELECT * FROM plots WHERE id=?", (identifier,))

	def show(self) -> None:
		heading("LOTES")
		rows = self.db.query("SELECT p.*, COUNT(c.id) crops FROM plots p LEFT JOIN crops c ON c.plot_id=p.id AND c.status!='finalizado' GROUP BY p.id ORDER BY p.name")
		print(f"{'ID':<4} {'NOMBRE':<18} {'HECTAREAS':<12} {'SUELO':<15} {'AGUA':<15} {'CULTIVOS':<10} ESTADO")
		separator()
		for row in rows:
			print(f"{row['id']:<4} {row['name'][:17]:<18} {row['area']:<12.2f} {row['soil'][:14]:<15} {row['water'][:14]:<15} {row['crops']:<10} {row['status']}")
		if not rows:
			print("No hay lotes registrados.")

	def create(self) -> None:
		heading("NUEVO LOTE")
		name = text(ask("Nombre del lote"))
		area = ask_float("Area en hectareas")
		location = text(ask("Ubicacion"))
		soil = text(ask("Tipo de suelo", "Franco"))
		water = text(ask("Fuente de agua", "Lluvia"))
		if not name or area is None or area <= 0:
			print("Nombre y area positiva son obligatorios.")
			return
		try:
			self.db.execute("INSERT INTO plots(name,area,location,soil,water) VALUES(?,?,?,?,?)", (name, area, location, soil, water))
			self.db.log("LOTE_CREADO", name)
			print("Lote registrado.")
		except sqlite3.IntegrityError:
			print("Ya existe un lote con ese nombre.")


class Crops:
	def __init__(self, db: Database, plots: Plots, people: People) -> None:
		self.db = db
		self.plots = plots
		self.people = people

	def get(self, identifier: int) -> Optional[sqlite3.Row]:
		return self.db.one("SELECT * FROM crops WHERE id=?", (identifier,))

	def show(self, search: str = "") -> None:
		heading("CULTIVOS")
		pattern = f"%{search}%"
		rows = self.db.query("SELECT c.*,p.name plot_name,COALESCE(x.name,'Sin asignar') person_name FROM crops c JOIN plots p ON p.id=c.plot_id LEFT JOIN people x ON x.id=c.person_id WHERE c.name LIKE ? OR c.variety LIKE ? OR p.name LIKE ? ORDER BY c.status,c.expected", (pattern, pattern, pattern))
		print(f"{'ID':<4} {'CULTIVO':<16} {'VARIEDAD':<16} {'LOTE':<15} {'SIEMBRA':<12} {'COSECHA':<12} ESTADO")
		separator()
		for row in rows:
			print(f"{row['id']:<4} {row['name'][:15]:<16} {row['variety'][:15]:<16} {row['plot_name'][:14]:<15} {row['planted']:<12} {row['expected'] or '-':<12} {row['status']}")
		if not rows:
			print("No hay cultivos.")

	def create(self) -> None:
		heading("NUEVO CULTIVO")
		self.plots.show()
		plot_id = ask_int("ID del lote")
		if not plot_id or not self.plots.get(plot_id):
			print("Lote invalido.")
			return
		name = text(ask("Cultivo"))
		variety = text(ask("Variedad"))
		planted = ask("Fecha de siembra", today())
		expected = ask("Fecha esperada", (date.today() + timedelta(days=90)).isoformat())
		area = ask_float("Area sembrada")
		person_id = ask_int("ID del responsable (opcional)")
		notes = text(ask("Notas"))
		if not name or area is None or area <= 0 or not is_date(planted) or not is_date(expected):
			print("Revisa nombre, area y fechas.")
			return
		if person_id and not self.people.get(person_id):
			print("Responsable invalido.")
			return
		self.db.execute("INSERT INTO crops(name,variety,plot_id,person_id,planted,expected,area,notes) VALUES(?,?,?,?,?,?,?,?)", (name, variety, plot_id, person_id, planted, expected, area, notes))
		self.db.execute("UPDATE plots SET status='ocupado' WHERE id=?", (plot_id,))
		self.db.log("CULTIVO_CREADO", name)
		print("Cultivo registrado.")

	def finish(self) -> None:
		self.show()
		identifier = ask_int("ID del cultivo")
		if not identifier or not self.get(identifier):
			print("Cultivo no encontrado.")
			return
		self.db.execute("UPDATE crops SET status='finalizado' WHERE id=?", (identifier,))
		self.db.log("CULTIVO_FINALIZADO", str(identifier))
		print("Cultivo finalizado.")


class Tasks:
	def __init__(self, db: Database, crops: Crops, people: People) -> None:
		self.db = db
		self.crops = crops
		self.people = people

	def show(self, pending: bool = False) -> None:
		heading("AGENDA DE LABORES")
		condition = "WHERE t.status='pendiente'" if pending else ""
		rows = self.db.query(f"SELECT t.*,COALESCE(c.name,'General') crop_name FROM tasks t LEFT JOIN crops c ON c.id=t.crop_id {condition} ORDER BY t.status,t.due")
		print(f"{'ID':<4} {'LABOR':<27} {'CULTIVO':<16} {'FECHA':<12} {'COSTO':<14} ESTADO")
		separator()
		for row in rows:
			print(f"{row['id']:<4} {row['title'][:26]:<27} {row['crop_name'][:15]:<16} {row['due']:<12} {money(row['cost']):<14} {row['status']}")
		if not rows:
			print("No hay labores.")

	def create(self) -> None:
		heading("PROGRAMAR LABOR")
		self.crops.show()
		crop_id = ask_int("ID del cultivo (opcional)")
		if crop_id and not self.crops.get(crop_id):
			print("Cultivo invalido.")
			return
		name = text(ask("Nombre de la labor"))
		description = text(ask("Descripcion"))
		due = ask("Fecha programada", today())
		cost = ask_float("Costo", 0) or 0
		person_id = ask_int("ID del responsable (opcional)")
		if person_id and not self.people.get(person_id):
			print("Responsable invalido.")
			return
		if not name or not is_date(due) or cost < 0:
			print("Labor, fecha y costo valido son obligatorios.")
			return
		self.db.execute("INSERT INTO tasks(crop_id,person_id,title,description,due,cost) VALUES(?,?,?,?,?,?)", (crop_id, person_id, name, description, due, cost))
		self.db.log("LABOR_CREADA", name)
		print("Labor programada.")

	def complete(self) -> None:
		self.show(True)
		identifier = ask_int("ID de la labor")
		row = self.db.one("SELECT * FROM tasks WHERE id=? AND status='pendiente'", (identifier,)) if identifier else None
		if not row:
			print("Labor no encontrada.")
			return
		self.db.execute("UPDATE tasks SET status='realizada' WHERE id=?", (identifier,))
		self.db.log("LABOR_COMPLETADA", str(identifier))
		print("Labor marcada como realizada.")


class Supplies:
	def __init__(self, db: Database) -> None:
		self.db = db

	def get(self, identifier: int) -> Optional[sqlite3.Row]:
		return self.db.one("SELECT * FROM supplies WHERE id=?", (identifier,))

	def show(self, low: bool = False) -> None:
		heading("INVENTARIO DE INSUMOS")
		condition = "WHERE quantity<=minimum" if low else ""
		rows = self.db.query(f"SELECT * FROM supplies {condition} ORDER BY name")
		print(f"{'ID':<4} {'INSUMO':<25} {'CATEGORIA':<16} {'CANTIDAD':<12} {'MINIMO':<10} UNIDAD")
		separator()
		for row in rows:
			mark = " *" if row["quantity"] <= row["minimum"] else ""
			print(f"{row['id']:<4} {row['name'][:24]:<25} {row['category'][:15]:<16} {row['quantity']:<12.2f} {row['minimum']:<10.2f} {row['unit']}{mark}")
		if not rows:
			print("No hay insumos.")

	def create(self) -> None:
		heading("NUEVO INSUMO")
		name = text(ask("Nombre"))
		category = text(ask("Categoria", "Semilla"))
		unit = text(ask("Unidad", "bulto"))
		quantity = ask_float("Cantidad", 0) or 0
		minimum = ask_float("Minimo", 0) or 0
		cost = ask_float("Costo unitario", 0) or 0
		supplier = text(ask("Proveedor"))
		if not name or quantity < 0 or minimum < 0 or cost < 0:
			print("Datos invalidos.")
			return
		cursor = self.db.execute("INSERT INTO supplies(name,category,unit,quantity,minimum,unit_cost,supplier) VALUES(?,?,?,?,?,?,?)", (name, category, unit, quantity, minimum, cost, supplier))
		if quantity:
			self.db.execute("INSERT INTO movements(supply_id,kind,quantity,movement_date,note) VALUES(?,'entrada',?,?,?)", (cursor.lastrowid, quantity, today(), "Inicial"))
		self.db.log("INSUMO_CREADO", name)
		print("Insumo guardado.")

	def move(self) -> None:
		self.show()
		identifier = ask_int("ID del insumo")
		supply = self.get(identifier) if identifier else None
		if not supply:
			print("Insumo no encontrado.")
			return
		kind = ask("Movimiento (entrada/salida)", "entrada").lower()
		quantity = ask_float("Cantidad")
		note = text(ask("Nota"))
		if kind not in {"entrada", "salida"} or quantity is None or quantity <= 0:
			print("Movimiento invalido.")
			return
		new_value = supply["quantity"] + quantity if kind == "entrada" else supply["quantity"] - quantity
		if new_value < 0:
			print("No hay existencias suficientes.")
			return
		self.db.execute("UPDATE supplies SET quantity=? WHERE id=?", (new_value, identifier))
		self.db.execute("INSERT INTO movements(supply_id,kind,quantity,movement_date,note) VALUES(?,?,?,?,?)", (identifier, kind, quantity, today(), note))
		self.db.log("MOVIMIENTO_INSUMO", f"{identifier}:{kind}")
		print("Movimiento guardado.")


class Harvests:
	def __init__(self, db: Database, crops: Crops) -> None:
		self.db = db
		self.crops = crops

	def get(self, identifier: int) -> Optional[sqlite3.Row]:
		return self.db.one("SELECT * FROM harvests WHERE id=?", (identifier,))

	def show(self) -> None:
		heading("COSECHAS")
		rows = self.db.query("SELECT h.*,c.name crop_name FROM harvests h JOIN crops c ON c.id=h.crop_id ORDER BY h.harvest_date DESC")
		print(f"{'ID':<4} {'CULTIVO':<18} {'FECHA':<12} {'CANTIDAD':<12} {'UNIDAD':<10} {'CALIDAD':<12} VALOR")
		separator()
		for row in rows:
			print(f"{row['id']:<4} {row['crop_name'][:17]:<18} {row['harvest_date']:<12} {row['quantity']:<12.2f} {row['unit']:<10} {row['quality']:<12} {money(row['quantity'] * row['unit_price'])}")
		if not rows:
			print("No hay cosechas.")

	def create(self) -> None:
		heading("NUEVA COSECHA")
		self.crops.show()
		crop_id = ask_int("ID del cultivo")
		if not crop_id or not self.crops.get(crop_id):
			print("Cultivo invalido.")
			return
		harvest_date = ask("Fecha", today())
		quantity = ask_float("Cantidad")
		unit = text(ask("Unidad", "kg"))
		quality = text(ask("Calidad", "Primera"))
		price = ask_float("Precio por unidad", 0) or 0
		note = text(ask("Nota"))
		if not is_date(harvest_date) or quantity is None or quantity <= 0 or price < 0:
			print("Datos invalidos.")
			return
		self.db.execute("INSERT INTO harvests(crop_id,harvest_date,quantity,unit,quality,unit_price,note) VALUES(?,?,?,?,?,?,?)", (crop_id, harvest_date, quantity, unit, quality, price, note))
		self.db.log("COSECHA_CREADA", str(crop_id))
		print("Cosecha registrada.")


class Sales:
	def __init__(self, db: Database, harvests: Harvests) -> None:
		self.db = db
		self.harvests = harvests

	def show(self) -> None:
		heading("VENTAS")
		rows = self.db.query("SELECT s.*,c.name crop_name FROM sales s JOIN harvests h ON h.id=s.harvest_id JOIN crops c ON c.id=h.crop_id ORDER BY s.sale_date DESC")
		print(f"{'ID':<4} {'CLIENTE':<24} {'CULTIVO':<16} {'FECHA':<12} {'CANT.':<10} {'TOTAL':<14} PAGO")
		separator()
		for row in rows:
			print(f"{row['id']:<4} {row['customer'][:23]:<24} {row['crop_name'][:15]:<16} {row['sale_date']:<12} {row['quantity']:<10.2f} {money(row['quantity'] * row['unit_price']):<14} {row['payment']}")
		if not rows:
			print("No hay ventas.")

	def create(self) -> None:
		heading("NUEVA VENTA")
		self.harvests.show()
		harvest_id = ask_int("ID de la cosecha")
		harvest = self.harvests.get(harvest_id) if harvest_id else None
		if not harvest:
			print("Cosecha no encontrada.")
			return
		customer = text(ask("Cliente"))
		sale_date = ask("Fecha", today())
		quantity = ask_float("Cantidad vendida")
		price = ask_float("Precio por unidad", harvest["unit_price"])
		payment = ask("Pago (pagado/pendiente)", "pagado")
		if not customer or not is_date(sale_date) or quantity is None or quantity <= 0 or price is None or price < 0:
			print("Datos invalidos.")
			return
		sold = self.db.one("SELECT COALESCE(SUM(quantity),0) total FROM sales WHERE harvest_id=?", (harvest_id,))["total"]
		if sold + quantity > harvest["quantity"]:
			print("La cantidad supera la cosecha disponible.")
			return
		self.db.execute("INSERT INTO sales(harvest_id,customer,sale_date,quantity,unit_price,payment) VALUES(?,?,?,?,?,?)", (harvest_id, customer, sale_date, quantity, price, payment))
		self.db.log("VENTA_CREADA", customer)
		print("Venta registrada por", money(quantity * price))


class Expenses:
	def __init__(self, db: Database) -> None:
		self.db = db

	def show(self) -> None:
		heading("GASTOS")
		rows = self.db.query("SELECT * FROM expenses ORDER BY expense_date DESC")
		print(f"{'ID':<4} {'FECHA':<12} {'CATEGORIA':<17} {'DESCRIPCION':<36} VALOR")
		separator()
		for row in rows:
			print(f"{row['id']:<4} {row['expense_date']:<12} {row['category'][:16]:<17} {row['description'][:35]:<36} {money(row['amount'])}")
		if not rows:
			print("No hay gastos.")

	def create(self) -> None:
		heading("NUEVO GASTO")
		category = text(ask("Categoria", "Insumos"))
		description = text(ask("Descripcion"))
		amount = ask_float("Valor")
		expense_date = ask("Fecha", today())
		if not category or not description or amount is None or amount <= 0 or not is_date(expense_date):
			print("Datos invalidos.")
			return
		self.db.execute("INSERT INTO expenses(category,description,amount,expense_date) VALUES(?,?,?,?)", (category, description, amount, expense_date))
		self.db.log("GASTO_CREADO", description)
		print("Gasto registrado.")


class Reports:
	def __init__(self, db: Database) -> None:
		self.db = db

	def dashboard(self) -> None:
		heading("DASHBOARD DE LA FINCA")
		items = [("Personas activas", self.db.one("SELECT COUNT(*) n FROM people WHERE active=1")["n"]), ("Lotes", self.db.count("plots")), ("Cultivos activos", self.db.one("SELECT COUNT(*) n FROM crops WHERE status!='finalizado'")["n"]), ("Labores pendientes", self.db.one("SELECT COUNT(*) n FROM tasks WHERE status='pendiente'")["n"]), ("Insumos", self.db.count("supplies")), ("Cosechas", self.db.count("harvests"))]
		for label, value in items:
			print(f"  {label:<28} {value}")
		income = self.db.one("SELECT COALESCE(SUM(quantity*unit_price),0) total FROM sales")["total"]
		cost = self.db.one("SELECT COALESCE(SUM(amount),0) total FROM expenses")["total"]
		separator()
		print("Ingresos:", money(income))
		print("Gastos:  ", money(cost))
		print("Balance: ", money(income - cost))
		separator()
		print("PROXIMAS LABORES")
		rows = self.db.query("SELECT title,due,status FROM tasks ORDER BY due LIMIT 5")
		for row in rows:
			print(f"  {row['due']} | {row['title'][:38]:<38} | {row['status']}")
		if not rows:
			print("  No hay labores.")

	def crop_summary(self) -> None:
		heading("RESUMEN POR CULTIVO")
		rows = self.db.query("SELECT c.name,c.variety,p.name plot,COALESCE(SUM(h.quantity),0) quantity,COALESCE(SUM(h.quantity*h.unit_price),0) value FROM crops c JOIN plots p ON p.id=c.plot_id LEFT JOIN harvests h ON h.crop_id=c.id GROUP BY c.id ORDER BY c.name")
		print(f"{'CULTIVO':<18} {'VARIEDAD':<18} {'LOTE':<16} {'CANTIDAD':<12} VALOR")
		separator()
		for row in rows:
			print(f"{row['name'][:17]:<18} {row['variety'][:17]:<18} {row['plot'][:15]:<16} {row['quantity']:<12.2f} {money(row['value'])}")
		if not rows:
			print("No hay cultivos.")

	def low(self) -> None:
		heading("ALERTAS DE INVENTARIO")
		rows = self.db.query("SELECT name,quantity,minimum,unit FROM supplies WHERE quantity<=minimum ORDER BY quantity")
		for row in rows:
			print(f"  {row['name']}: {row['quantity']} {row['unit']} disponibles; minimo {row['minimum']}")
		if not rows:
			print("No hay alertas.")

	def activity(self) -> None:
		heading("ACTIVIDAD RECIENTE")
		rows = self.db.query("SELECT created_at,action,detail FROM activity ORDER BY id DESC LIMIT 15")
		for row in rows:
			print(f"{row['created_at']} | {row['action']:<24} | {row['detail']}")
		if not rows:
			print("No hay actividad.")

	def export(self, name: str) -> Optional[Path]:
		queries = {"cultivos": "SELECT c.name,c.variety,p.name plot,c.planted,c.expected,c.area,c.status FROM crops c JOIN plots p ON p.id=c.plot_id", "cosechas": "SELECT c.name crop,h.harvest_date,h.quantity,h.unit,h.quality,h.unit_price FROM harvests h JOIN crops c ON c.id=h.crop_id", "ventas": "SELECT s.customer,c.name crop,s.sale_date,s.quantity,s.unit_price,s.payment FROM sales s JOIN harvests h ON h.id=s.harvest_id JOIN crops c ON c.id=h.crop_id", "gastos": "SELECT category,description,amount,expense_date FROM expenses"}
		if name not in queries:
			return None
		rows = self.db.query(queries[name])
		path = Path(__file__).with_name(f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
		with path.open("w", newline="", encoding="utf-8") as file:
			writer = csv.writer(file)
			if rows:
				writer.writerow(rows[0].keys())
				writer.writerows([tuple(row) for row in rows])
		return path


class Demo:
	def __init__(self, db: Database) -> None:
		self.db = db

	def load(self) -> None:
		if self.db.count("plots"):
			return
		people = [("Ana Martinez", "1001", "3001112233", "ana@finca.co", "Administradora"), ("Luis Gomez", "1002", "3002223344", "luis@finca.co", "Trabajador"), ("Marta Rojas", "1003", "3003334455", "marta@finca.co", "Tecnica")]
		for person in people:
			self.db.execute("INSERT INTO people(name,document,phone,email,role,created_at) VALUES(?,?,?,?,?,?)", (*person, now()))
		plots = [("La Esperanza", 4.5, "Norte", "Franco", "Nacimiento"), ("El Mirador", 2.0, "Alto", "Arcilloso", "Tanque"), ("La Huerta", .8, "Casa", "Organico", "Goteo")]
		for plot in plots:
			self.db.execute("INSERT INTO plots(name,area,location,soil,water) VALUES(?,?,?,?,?)", plot)
		plot_ids = [r["id"] for r in self.db.query("SELECT id FROM plots")]
		person_ids = [r["id"] for r in self.db.query("SELECT id FROM people")]
		crops = [("Cafe", "Castillo", plot_ids[0], person_ids[0], (date.today()-timedelta(days=160)).isoformat(), (date.today()+timedelta(days=30)).isoformat(), 3.2, "Buen desarrollo"), ("Tomate", "Chonto", plot_ids[1], person_ids[1], (date.today()-timedelta(days=45)).isoformat(), (date.today()+timedelta(days=20)).isoformat(), 1.4, "Vigilar insectos"), ("Lechuga", "Crespa", plot_ids[2], person_ids[2], (date.today()-timedelta(days=25)).isoformat(), (date.today()+timedelta(days=8)).isoformat(), .5, "Venta local")]
		for crop in crops:
			self.db.execute("INSERT INTO crops(name,variety,plot_id,person_id,planted,expected,area,notes) VALUES(?,?,?,?,?,?,?,?)", crop)
		crop_ids = [r["id"] for r in self.db.query("SELECT id FROM crops")]
		for task in [(crop_ids[0], person_ids[1], "Aplicar abono", "Distribuir compost", today(), "pendiente", 85000), (crop_ids[1], person_ids[1], "Revisar riego", "Verificar goteros", (date.today()+timedelta(days=2)).isoformat(), "pendiente", 30000), (crop_ids[2], person_ids[2], "Cosecha de control", "Seleccionar unidades", (date.today()+timedelta(days=5)).isoformat(), "pendiente", 15000)]:
			self.db.execute("INSERT INTO tasks(crop_id,person_id,title,description,due,status,cost) VALUES(?,?,?,?,?,?,?)", task)
		for supply in [("Semilla de lechuga", "Semilla", "sobre", 18, 5, 12000, "Valle"), ("Compost", "Fertilizante", "bulto", 3, 4, 28000, "Granja"), ("Caldo biologico", "Control", "litro", 12, 5, 9500, "BioCampo")]:
			self.db.execute("INSERT INTO supplies(name,category,unit,quantity,minimum,unit_cost,supplier) VALUES(?,?,?,?,?,?,?)", supply)
		self.db.execute("INSERT INTO harvests(crop_id,harvest_date,quantity,unit,quality,unit_price,note) VALUES(?,?,?,?,?,?,?)", (crop_ids[2], today(), 45, "kg", "Primera", 4500, "Prueba"))
		harvest_id = self.db.one("SELECT id FROM harvests ORDER BY id DESC LIMIT 1")["id"]
		self.db.execute("INSERT INTO sales(harvest_id,customer,sale_date,quantity,unit_price,payment) VALUES(?,?,?,?,?,?)", (harvest_id, "Restaurante El Sabor", today(), 30, 5000, "pagado"))
		self.db.execute("INSERT INTO expenses(category,description,amount,expense_date) VALUES(?,?,?,?)", ("Insumos", "Compra de compost", 84000, today()))
		self.db.log("DEMO_CARGADA", "Datos de ejemplo")


class App:
	def __init__(self) -> None:
		self.db = Database()
		self.people = People(self.db)
		self.plots = Plots(self.db)
		self.crops = Crops(self.db, self.plots, self.people)
		self.tasks = Tasks(self.db, self.crops, self.people)
		self.supplies = Supplies(self.db)
		self.harvests = Harvests(self.db, self.crops)
		self.sales = Sales(self.db, self.harvests)
		self.expenses = Expenses(self.db)
		self.reports = Reports(self.db)

	def close(self) -> None:
		self.db.close()

	def run(self) -> None:
		heading(f"{APP} | FINCA Y PRODUCCION")
		print("Control sencillo para organizar el trabajo agropecuario.")
		name = ask("Usuario", "Administrador")
		while True:
			try:
				self.menu(name)
				option = ask("Opcion")
				if option == "0":
					print("Hasta pronto,", name)
					return
				self.handle(option)
			except KeyboardInterrupt:
				print("\nOperacion cancelada.")
			except sqlite3.Error as error:
				print("Error de base de datos:", error)
			pause()

	def menu(self, name: str) -> None:
		heading(f"PANEL PRINCIPAL | {name}")
		print("1. Dashboard")
		print("2. Productores y trabajadores")
		print("3. Lotes y cultivos")
		print("4. Agenda de labores")
		print("5. Inventario de insumos")
		print("6. Cosechas y ventas")
		print("7. Gastos")
		print("8. Reportes y exportacion")
		print("9. Actividad reciente")
		print("0. Salir")

	def handle(self, option: str) -> None:
		actions = {"1": self.reports.dashboard, "2": self.people_menu, "3": self.crops_menu, "4": self.tasks_menu, "5": self.supplies_menu, "6": self.harvest_menu, "7": self.expenses_menu, "8": self.reports_menu, "9": self.reports.activity}
		if option in actions:
			actions[option]()
		else:
			print("Opcion no reconocida.")

	def people_menu(self) -> None:
		while True:
			heading("PERSONAS")
			print("1. Listar  2. Buscar  3. Registrar  4. Cambiar estado  0. Volver")
			option = ask("Opcion")
			if option == "0": return
			if option == "1": self.people.show()
			elif option == "2": self.people.show(ask("Busqueda"))
			elif option == "3": self.people.create()
			elif option == "4": self.people.toggle()
			else: print("Opcion no reconocida.")
			pause()

	def crops_menu(self) -> None:
		while True:
			heading("LOTES Y CULTIVOS")
			print("1. Ver lotes  2. Crear lote  3. Ver cultivos  4. Buscar  5. Crear cultivo  6. Finalizar  0. Volver")
			option = ask("Opcion")
			if option == "0": return
			if option == "1": self.plots.show()
			elif option == "2": self.plots.create()
			elif option == "3": self.crops.show()
			elif option == "4": self.crops.show(ask("Busqueda"))
			elif option == "5": self.crops.create()
			elif option == "6": self.crops.finish()
			else: print("Opcion no reconocida.")
			pause()

	def tasks_menu(self) -> None:
		while True:
			heading("LABORES")
			print("1. Todas  2. Pendientes  3. Programar  4. Completar  0. Volver")
			option = ask("Opcion")
			if option == "0": return
			if option == "1": self.tasks.show()
			elif option == "2": self.tasks.show(True)
			elif option == "3": self.tasks.create()
			elif option == "4": self.tasks.complete()
			else: print("Opcion no reconocida.")
			pause()

	def supplies_menu(self) -> None:
		while True:
			heading("INVENTARIO")
			print("1. Ver  2. Alertas  3. Nuevo insumo  4. Entrada o salida  0. Volver")
			option = ask("Opcion")
			if option == "0": return
			if option == "1": self.supplies.show()
			elif option == "2": self.reports.low()
			elif option == "3": self.supplies.create()
			elif option == "4": self.supplies.move()
			else: print("Opcion no reconocida.")
			pause()

	def harvest_menu(self) -> None:
		while True:
			heading("COSECHAS Y VENTAS")
			print("1. Ver cosechas  2. Registrar cosecha  3. Ver ventas  4. Registrar venta  0. Volver")
			option = ask("Opcion")
			if option == "0": return
			if option == "1": self.harvests.show()
			elif option == "2": self.harvests.create()
			elif option == "3": self.sales.show()
			elif option == "4": self.sales.create()
			else: print("Opcion no reconocida.")
			pause()

	def expenses_menu(self) -> None:
		while True:
			heading("GASTOS")
			print("1. Ver gastos  2. Registrar gasto  0. Volver")
			option = ask("Opcion")
			if option == "0": return
			if option == "1": self.expenses.show()
			elif option == "2": self.expenses.create()
			else: print("Opcion no reconocida.")
			pause()

	def reports_menu(self) -> None:
		while True:
			heading("REPORTES")
			print("1. Resumen por cultivo  2. Alertas  3. CSV cultivos  4. CSV cosechas  5. CSV ventas  6. CSV gastos  0. Volver")
			option = ask("Opcion")
			if option == "0": return
			if option == "1": self.reports.crop_summary()
			elif option == "2": self.reports.low()
			elif option in {"3", "4", "5", "6"}:
				name = {"3": "cultivos", "4": "cosechas", "5": "ventas", "6": "gastos"}[option]
				print("Archivo creado:", self.reports.export(name))
			else: print("Opcion no reconocida.")
			pause()


def demo() -> None:
	db = Database()
	Demo(db).load()
	print(f"{APP}: demo lista")
	print("Personas:", db.count("people"))
	print("Lotes:", db.count("plots"))
	print("Cultivos:", db.count("crops"))
	print("Cosechas:", db.count("harvests"))
	print("Ventas:", db.count("sales"))
	Reports(db).dashboard()
	db.close()


def main() -> None:
	parser = argparse.ArgumentParser(description="Sistema agropecuario sencillo")
	parser.add_argument("--demo", action="store_true", help="cargar datos de ejemplo")
	parser.add_argument("--reset", action="store_true", help="borrar la base local")
	args = parser.parse_args()
	if args.reset and DB.exists():
		DB.unlink()
	if args.demo:
		demo()
		return
	app = App()
	try:
		app.run()
	finally:
		app.close()


if __name__ == "__main__":
	main()