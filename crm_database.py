import sqlite3
import os
import time # Para timestamps
import datetime # Para fechas de audiencias

# Nombre del archivo de la base de datos
DATABASE_FILE = 'crm_legal.db'

def connect_db():
    """ Establece una conexión con la base de datos SQLite. Crea el archivo si no existe. """
    try:
        conn = sqlite3.connect(DATABASE_FILE, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
        conn.execute('PRAGMA foreign_keys = ON;')
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        print(f"Error al conectar a la base de datos: {e}")
        return None

def close_db(conn):
    """ Cierra la conexión con la base de datos. """
    if conn:
        conn.close()

def create_tables():
    """ Crea las tablas en la base de datos si no existen, basado en el esquema. """
    conn = connect_db()
    if conn:
        try:
            cursor = conn.cursor()

            # Tabla clientes
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS clientes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT NOT NULL,
                    direccion TEXT,
                    email TEXT,
                    whatsapp TEXT,
                    created_at INTEGER
                );
            ''')

            # Tabla casos
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS casos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cliente_id INTEGER NOT NULL,
                    numero_expediente TEXT,
                    anio_caratula TEXT,
                    caratula TEXT NOT NULL,
                    juzgado TEXT,
                    jurisdiccion TEXT,
                    etapa_procesal TEXT,
                    notas TEXT,
                    ruta_carpeta TEXT,
                    inactivity_threshold_days INTEGER DEFAULT 30,
                    inactivity_enabled INTEGER DEFAULT 1,
                    created_at INTEGER,
                    last_activity_timestamp INTEGER,
                    FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON DELETE CASCADE
                );
            ''')

            # Tabla audiencias
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS audiencias (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    caso_id INTEGER NOT NULL,
                    fecha TEXT NOT NULL, 
                    hora TEXT,           
                    descripcion TEXT NOT NULL,
                    link TEXT,
                    recordatorio_activo INTEGER DEFAULT 0, 
                    recordatorio_minutos INTEGER DEFAULT 15,
                    created_at INTEGER,
                    FOREIGN KEY (caso_id) REFERENCES casos(id) ON DELETE CASCADE
                );
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_audiencias_fecha ON audiencias (fecha);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_audiencias_caso_id ON audiencias (caso_id);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_audiencias_recordatorio ON audiencias (recordatorio_activo);')

            # Tabla actividades_caso
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS actividades_caso (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    caso_id INTEGER NOT NULL,
                    fecha_hora TEXT NOT NULL, 
                    tipo_actividad TEXT NOT NULL, 
                    descripcion TEXT NOT NULL,
                    creado_por TEXT, 
                    referencia_documento TEXT, 
                    FOREIGN KEY (caso_id) REFERENCES casos(id) ON DELETE CASCADE
                );
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_actividades_caso_id_fecha
                ON actividades_caso (caso_id, fecha_hora DESC);
            ''')

            # Tabla partes_intervinientes (MODIFICADA para incluir notas)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS partes_intervinientes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    caso_id INTEGER NOT NULL,
                    nombre TEXT NOT NULL,
                    tipo TEXT, 
                    direccion TEXT,
                    contacto TEXT,
                    notas TEXT,          -- NUEVO CAMPO
                    created_at INTEGER,
                    FOREIGN KEY (caso_id) REFERENCES casos(id) ON DELETE CASCADE
                );
            ''')
            # Crear índice para partes_intervinientes por caso_id
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_partes_caso_id
                ON partes_intervinientes (caso_id);
            ''')

            # Crear tabla para usuario/abogado
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS datos_usuario (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    nombre_abogado TEXT,
                    matricula_nacion TEXT,
                    matricula_pba TEXT,
                    matricula_federal TEXT,
                    domicilio_procesal_caba TEXT,
                    zona_notificacion TEXT,
                    domicilio_procesal_pba TEXT,
                    telefono_estudio TEXT,
                    email_estudio TEXT,
                    cuit TEXT,
                    legajo_prev TEXT,
                    domicilio_electrónico_pba TEXT,
                    otros_datos TEXT
                );
            ''')

            # En crm_database.py, dentro de la función create_tables()

            # ... (después de CREATE TABLE IF NOT EXISTS datos_usuario (...) ...)

            # --- NUEVAS TABLAS PARA ETIQUETAS ---
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS etiquetas (
                    id_etiqueta INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre_etiqueta TEXT NOT NULL UNIQUE COLLATE NOCASE 
                );
            ''')
            # COLLATE NOCASE en UNIQUE para que "Urgente" y "urgente" se consideren la misma etiqueta.

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cliente_etiquetas (
                    cliente_id INTEGER NOT NULL,
                    etiqueta_id INTEGER NOT NULL,
                    FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON DELETE CASCADE,
                    FOREIGN KEY (etiqueta_id) REFERENCES etiquetas(id_etiqueta) ON DELETE CASCADE,
                    PRIMARY KEY (cliente_id, etiqueta_id)
                );
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS caso_etiquetas (
                    caso_id INTEGER NOT NULL,
                    etiqueta_id INTEGER NOT NULL,
                    FOREIGN KEY (caso_id) REFERENCES casos(id) ON DELETE CASCADE,
                    FOREIGN KEY (etiqueta_id) REFERENCES etiquetas(id_etiqueta) ON DELETE CASCADE,
                    PRIMARY KEY (caso_id, etiqueta_id)
                );
            ''')
            print("Tablas de etiquetas verificadas/creadas con éxito.")
            # --- FIN NUEVAS TABLAS PARA ETIQUETAS ---

            # Opcional: Insertar una fila por defecto si la tabla está vacía la primera vez
            # Esto asegura que siempre haya una fila para actualizar, simplificando la lógica de guardado.
            cursor.execute('''
                INSERT OR IGNORE INTO datos_usuario (id) VALUES (1);
            ''')

            # --- NUEVA TABLA: tareas ---
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tareas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    caso_id INTEGER,                     -- Puede ser NULL para tareas generales
                    descripcion TEXT NOT NULL,
                    fecha_creacion TEXT NOT NULL,        -- YYYY-MM-DD HH:MM:SS
                    fecha_vencimiento TEXT,              -- YYYY-MM-DD (la hora es opcional o fin del día)
                    prioridad TEXT DEFAULT 'Media',      -- Ej: 'Alta', 'Media', 'Baja'
                    estado TEXT NOT NULL DEFAULT 'Pendiente', -- Ej: 'Pendiente', 'En Progreso', 'Completada', 'Cancelada'
                    notas TEXT,
                    es_plazo_procesal INTEGER DEFAULT 0, -- 0 para False, 1 para True
                    recordatorio_activo INTEGER DEFAULT 0,
                    recordatorio_dias_antes INTEGER DEFAULT 1,
                    fecha_ultima_notificacion TEXT,      -- Para controlar notificaciones repetitivas
                    FOREIGN KEY (caso_id) REFERENCES casos(id) ON DELETE SET NULL -- O CASCADE si quieres que se borren con el caso
                );
            ''')
            # Índices para búsquedas comunes en tareas
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_tareas_caso_id ON tareas (caso_id);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_tareas_fecha_vencimiento ON tareas (fecha_vencimiento);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_tareas_estado ON tareas (estado);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_tareas_recordatorio_activo ON tareas (recordatorio_activo, fecha_vencimiento);')
            # --- FIN NUEVA TABLA tareas ---

            conn.commit()
            print("Tablas verificadas/creadas con éxito (partes_intervinientes actualizada).")
        except sqlite3.Error as e:
            print(f"Error al crear tablas: {e}")
            conn.rollback()
        finally:
            close_db(conn)

# --- Funciones CRUD para Clientes (sin cambios) ---

def get_datos_usuario():
    conn = connect_db()
    datos = None
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM datos_usuario WHERE id = 1")
            row = cursor.fetchone()
            if row:
                datos = dict(row)
        except sqlite3.Error as e:
            print(f"Error al obtener datos del usuario: {e}")
        finally:
            close_db(conn)
    return datos

def save_datos_usuario(**kwargs):
    conn = connect_db()
    success = False
    if conn:
        try:
            cursor = conn.cursor()
            # Construir la parte SET de la consulta dinámicamente
            # Asegurarse de que 'id' no esté en los campos a actualizar
            campos_a_actualizar = {k: v for k, v in kwargs.items() if k != 'id'}
            
            if not campos_a_actualizar:
                print("Advertencia: No se proporcionaron campos para actualizar en save_datos_usuario.")
                return False # O True, si no hacer nada se considera éxito

            set_clause = ", ".join([f"{key} = ?" for key in campos_a_actualizar.keys()])
            valores = list(campos_a_actualizar.values())
            
            # Siempre actualizamos la fila con id = 1
            sql = f"UPDATE datos_usuario SET {set_clause} WHERE id = 1"
            
            cursor.execute(sql, valores)
            conn.commit()
            if cursor.rowcount > 0:
                print("Datos del usuario guardados con éxito.")
                success = True
            else:
                # Podría ser que no hubo cambios o la fila id=1 no existía (si no se usó INSERT OR IGNORE)
                print("Datos del usuario no necesitaron actualización o no se encontró la fila (id=1).")
                success = True # Considerar éxito si no hay error
        except sqlite3.Error as e:
            print(f"Error al guardar datos del usuario: {e}")
            conn.rollback()
        finally:
            close_db(conn)
    return success

def add_client(nombre, direccion="", email="", whatsapp=""):
    conn = connect_db()
    if conn:
        try:
            cursor = conn.cursor()
            timestamp = int(time.time())
            cursor.execute('''
                INSERT INTO clientes (nombre, direccion, email, whatsapp, created_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (nombre, direccion, email, whatsapp, timestamp))
            conn.commit()
            return cursor.lastrowid
        except sqlite3.Error as e:
            print(f"Error al agregar cliente: {e}")
            conn.rollback()
            return None
        finally:
            close_db(conn)

def get_clients():
    conn = connect_db()
    clients = []
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute('SELECT id, nombre, direccion, email, whatsapp, created_at FROM clientes ORDER BY nombre')
            rows = cursor.fetchall()
            clients = [dict(row) for row in rows]
        except sqlite3.Error as e:
            print(f"Error al obtener clientes: {e}")
        finally:
            close_db(conn)
    return clients

def get_client_by_id(client_id):
    conn = connect_db()
    client_data = None
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute('SELECT id, nombre, direccion, email, whatsapp, created_at FROM clientes WHERE id = ?', (client_id,))
            row = cursor.fetchone()
            if row:
                client_data = dict(row)
        except sqlite3.Error as e:
            print(f"Error al obtener cliente por ID {client_id}: {e}")
        finally:
            close_db(conn)
    return client_data

def update_client(client_id, nombre, direccion, email, whatsapp):
    conn = connect_db()
    success = False
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE clientes
                SET nombre = ?, direccion = ?, email = ?, whatsapp = ?
                WHERE id = ?
            ''', (nombre, direccion, email, whatsapp, client_id))
            conn.commit()
            success = True
        except sqlite3.Error as e:
            print(f"Error al actualizar cliente ID {client_id}: {e}")
            conn.rollback()
        finally:
            close_db(conn)
    return success

def delete_client(client_id):
    conn = connect_db()
    success = False
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM clientes WHERE id = ?', (client_id,))
            conn.commit()
            success = True
        except sqlite3.Error as e:
            print(f"Error al eliminar cliente ID {client_id}: {e}")
            conn.rollback()
        finally:
            close_db(conn)
    return success

# --- Funciones CRUD para Casos (sin cambios en su lógica principal) ---
def add_case(cliente_id, caratula, numero_expediente="", anio_caratula="", juzgado="", jurisdiccion="", etapa_procesal="", notas="", ruta_carpeta="", inactivity_threshold_days=30, inactivity_enabled=1):
    conn = connect_db()
    new_id = None
    if conn:
        try:
            cursor = conn.cursor()
            timestamp = int(time.time())
            cursor.execute('''
                INSERT INTO casos (cliente_id, numero_expediente, anio_caratula, caratula, juzgado, jurisdiccion, etapa_procesal, notas, ruta_carpeta, inactivity_threshold_days, inactivity_enabled, created_at, last_activity_timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (cliente_id, numero_expediente, anio_caratula, caratula, juzgado, jurisdiccion, etapa_procesal, notas, ruta_carpeta, inactivity_threshold_days, inactivity_enabled, timestamp, timestamp))
            conn.commit()
            new_id = cursor.lastrowid
        except sqlite3.Error as e:
            print(f"Error al agregar caso: {e}")
            conn.rollback()
        finally:
            close_db(conn)
    return new_id

def get_cases_by_client(cliente_id):
    conn = connect_db()
    cases = []
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT ca.*, cl.nombre as nombre_cliente
                FROM casos ca
                JOIN clientes cl ON ca.cliente_id = cl.id
                WHERE ca.cliente_id = ?
                ORDER BY ca.anio_caratula DESC, ca.numero_expediente ASC
            ''', (cliente_id,))
            rows = cursor.fetchall()
            cases = [dict(row) for row in rows]
        except sqlite3.Error as e:
            print(f"Error al obtener casos por cliente: {e}")
        finally:
            close_db(conn)
    return cases

def get_case_by_id(case_id):
    conn = connect_db()
    case_data = None
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT ca.*, cl.nombre as nombre_cliente
                FROM casos ca
                JOIN clientes cl ON ca.cliente_id = cl.id
                WHERE ca.id = ?
            ''', (case_id,))
            row = cursor.fetchone()
            if row:
                case_data = dict(row)
        except sqlite3.Error as e:
            print(f"Error al obtener caso por ID {case_id}: {e}")
        finally:
            close_db(conn)
    return case_data

def update_case(case_id, caratula, numero_expediente, anio_caratula, juzgado, jurisdiccion, etapa_procesal, notas, ruta_carpeta, inactivity_threshold_days, inactivity_enabled):
    conn = connect_db()
    success = False
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE casos
                SET caratula = ?, numero_expediente = ?, anio_caratula = ?, juzgado = ?,
                    jurisdiccion = ?, etapa_procesal = ?, notas = ?, ruta_carpeta = ?,
                    inactivity_threshold_days = ?, inactivity_enabled = ? 
                WHERE id = ?
            ''', (caratula, numero_expediente, anio_caratula, juzgado, jurisdiccion, etapa_procesal, notas, ruta_carpeta, inactivity_threshold_days, inactivity_enabled, case_id))
            conn.commit()
            if cursor.rowcount > 0:
                update_last_activity(case_id) # Actualizar si hubo cambios
            success = True
        except sqlite3.Error as e:
            print(f"Error al actualizar caso ID {case_id}: {e}")
            conn.rollback()
        finally:
            close_db(conn)
    return success

def delete_case(case_id):
    conn = connect_db()
    success = False
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM casos WHERE id = ?', (case_id,))
            conn.commit()
            success = True
        except sqlite3.Error as e:
            print(f"Error al eliminar caso ID {case_id}: {e}")
            conn.rollback()
        finally:
            close_db(conn)
    return success

def update_case_folder(case_id, folder_path):
    conn = connect_db()
    success = False
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute('UPDATE casos SET ruta_carpeta = ? WHERE id = ?', (folder_path, case_id))
            conn.commit()
            if cursor.rowcount > 0:
                update_last_activity(case_id)
            success = True
        except sqlite3.Error as e:
            print(f"Error al actualizar ruta de carpeta para caso ID {case_id}: {e}")
            conn.rollback()
        finally:
            close_db(conn)
    return success

def update_last_activity(case_id):
    conn = connect_db()
    success = False
    if conn:
        try:
            cursor = conn.cursor()
            timestamp = int(time.time())
            cursor.execute('UPDATE casos SET last_activity_timestamp = ? WHERE id = ?', (timestamp, case_id))
            conn.commit()
            success = True
        except sqlite3.Error as e:
            print(f"Error al actualizar timestamp de actividad para caso ID {case_id}: {e}")
            conn.rollback()
        finally:
            close_db(conn)
    return success

# --- Funciones CRUD para Actividades del Caso (sin cambios) ---
def add_actividad_caso(caso_id, fecha_hora, tipo_actividad, descripcion, creado_por=None, referencia_documento=None):
    conn = connect_db()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO actividades_caso (caso_id, fecha_hora, tipo_actividad, descripcion, creado_por, referencia_documento)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (caso_id, fecha_hora, tipo_actividad, descripcion, creado_por, referencia_documento))
            conn.commit()
            new_id = cursor.lastrowid
            update_last_activity(caso_id)
            return new_id
        except sqlite3.Error as e:
            print(f"Error al agregar actividad al caso ID {caso_id}: {e}")
            conn.rollback()
            return None
        finally:
            close_db(conn)

def get_actividades_by_caso_id(caso_id, order_desc=True):
    conn = connect_db()
    actividades = []
    if conn:
        try:
            cursor = conn.cursor()
            order_direction = "DESC" if order_desc else "ASC"
            sql = f'''
                SELECT id, caso_id, fecha_hora, tipo_actividad, descripcion, creado_por, referencia_documento 
                FROM actividades_caso 
                WHERE caso_id = ? 
                ORDER BY datetime(fecha_hora) {order_direction}
            ''' # Usar datetime() para asegurar ordenamiento correcto de fechas como texto
            cursor.execute(sql, (caso_id,))
            rows = cursor.fetchall()
            actividades = [dict(row) for row in rows]
        except sqlite3.Error as e:
            print(f"Error al obtener actividades para el caso ID {caso_id}: {e}")
        finally:
            close_db(conn)
    return actividades

def get_actividad_by_id(actividad_id):
    conn = connect_db()
    actividad_data = None
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, caso_id, fecha_hora, tipo_actividad, descripcion, creado_por, referencia_documento 
                FROM actividades_caso 
                WHERE id = ?
            ''', (actividad_id,))
            row = cursor.fetchone()
            if row:
                actividad_data = dict(row)
        except sqlite3.Error as e:
            print(f"Error al obtener actividad por ID {actividad_id}: {e}")
        finally:
            close_db(conn)
    return actividad_data

def update_actividad_caso(actividad_id, tipo_actividad, descripcion, referencia_documento=None):
    conn = connect_db()
    success = False
    if conn:
        try:
            cursor = conn.cursor()
            cursor_check = conn.cursor() # Para obtener caso_id
            cursor_check.execute('SELECT caso_id FROM actividades_caso WHERE id = ?', (actividad_id,))
            row_check = cursor_check.fetchone()

            cursor.execute('''
                UPDATE actividades_caso
                SET tipo_actividad = ?,
                    descripcion = ?,
                    referencia_documento = ? 
                WHERE id = ?
            ''', (tipo_actividad, descripcion, referencia_documento, actividad_id))
            conn.commit()
            if cursor.rowcount > 0 and row_check:
                update_last_activity(row_check['caso_id'])
            success = True
        except sqlite3.Error as e:
            print(f"Error al actualizar actividad ID {actividad_id}: {e}")
            conn.rollback()
        finally:
            close_db(conn)
    return success

def delete_actividad_caso(actividad_id):
    conn = connect_db()
    success = False
    if conn:
        try:
            cursor = conn.cursor()
            cursor_check = conn.cursor() # Para obtener caso_id
            cursor_check.execute('SELECT caso_id FROM actividades_caso WHERE id = ?', (actividad_id,))
            row_check = cursor_check.fetchone()

            cursor.execute('DELETE FROM actividades_caso WHERE id = ?', (actividad_id,))
            conn.commit()
            if cursor.rowcount > 0 and row_check:
                update_last_activity(row_check['caso_id'])
            success = True
        except sqlite3.Error as e:
            print(f"Error al eliminar actividad ID {actividad_id}: {e}")
            conn.rollback()
        finally:
            close_db(conn)
    return success

# --- NUEVAS Funciones CRUD para Tareas ---
def add_tarea(descripcion, caso_id=None, fecha_vencimiento=None, prioridad='Media', estado='Pendiente', notas=None, es_plazo_procesal=0, recordatorio_activo=0, recordatorio_dias_antes=1):
    """ Agrega una nueva tarea. """
    conn = connect_db()
    new_id = None
    if conn:
        try:
            cursor = conn.cursor()
            fecha_creacion = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Asegurarse de que fecha_vencimiento (si se provee) solo sea fecha YYYY-MM-DD
            if fecha_vencimiento:
                try:
                    # Intenta parsear para validar y reformatear si es necesario (ej. si viene con hora)
                    fecha_venc_dt = datetime.datetime.strptime(fecha_vencimiento, "%Y-%m-%d %H:%M:%S") # Si podría venir con hora
                    fecha_vencimiento = fecha_venc_dt.strftime("%Y-%m-%d")
                except ValueError:
                    try:
                        fecha_venc_dt = datetime.datetime.strptime(fecha_vencimiento, "%Y-%m-%d")
                        fecha_vencimiento = fecha_venc_dt.strftime("%Y-%m-%d") # Ya está en formato correcto
                    except ValueError:
                        print(f"Advertencia: Formato de fecha_vencimiento ('{fecha_vencimiento}') no válido. Se guardará como NULL.")
                        fecha_vencimiento = None
            
            cursor.execute('''
                INSERT INTO tareas (caso_id, descripcion, fecha_creacion, fecha_vencimiento, prioridad, estado, notas, es_plazo_procesal, recordatorio_activo, recordatorio_dias_antes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (caso_id, descripcion, fecha_creacion, fecha_vencimiento, prioridad, estado, notas, es_plazo_procesal, recordatorio_activo, recordatorio_dias_antes))
            conn.commit()
            new_id = cursor.lastrowid
            if new_id and caso_id:
                update_last_activity(caso_id) # Actualizar timestamp del caso si la tarea está asociada
            print(f"Tarea ID {new_id} ('{descripcion[:30]}...') agregada.")
        except sqlite3.Error as e:
            print(f"Error al agregar tarea: {e}")
            conn.rollback()
        finally:
            close_db(conn)
    return new_id

def get_tarea_by_id(tarea_id):
    """ Obtiene una tarea específica por su ID. """
    conn = connect_db()
    tarea_data = None
    if conn:
        try:
            cursor = conn.cursor()
            # Podríamos hacer un JOIN con casos si quisiéramos el nombre del caso aquí,
            # pero para la edición directa de la tarea, esto es suficiente.
            cursor.execute("SELECT * FROM tareas WHERE id = ?", (tarea_id,))
            row = cursor.fetchone()
            if row:
                tarea_data = dict(row)
        except sqlite3.Error as e:
            print(f"Error al obtener tarea por ID {tarea_id}: {e}")
        finally:
            close_db(conn)
    return tarea_data

def get_tareas_by_caso_id(caso_id, incluir_completadas=False, orden="fecha_vencimiento_asc"):
    """ Obtiene todas las tareas para un caso específico. """
    conn = connect_db()
    tareas = []
    if conn:
        try:
            cursor = conn.cursor()
            sql = "SELECT * FROM tareas WHERE caso_id = ?"
            params = [caso_id]

            if not incluir_completadas:
                sql += " AND estado NOT IN (?, ?)"
                params.extend(["Completada", "Cancelada"])
            
            if orden == "fecha_vencimiento_asc":
                # Ordenar poniendo NULLs al final, luego por fecha, luego por prioridad
                sql += " ORDER BY CASE WHEN fecha_vencimiento IS NULL THEN 1 ELSE 0 END, fecha_vencimiento ASC, CASE prioridad WHEN 'Alta' THEN 1 WHEN 'Media' THEN 2 WHEN 'Baja' THEN 3 ELSE 4 END ASC"
            elif orden == "prioridad":
                sql += " ORDER BY CASE prioridad WHEN 'Alta' THEN 1 WHEN 'Media' THEN 2 WHEN 'Baja' THEN 3 ELSE 4 END ASC, CASE WHEN fecha_vencimiento IS NULL THEN 1 ELSE 0 END, fecha_vencimiento ASC"
            # Añadir más órdenes si es necesario

            cursor.execute(sql, params)
            rows = cursor.fetchall()
            tareas = [dict(row) for row in rows]
        except sqlite3.Error as e:
            print(f"Error al obtener tareas para el caso ID {caso_id}: {e}")
        finally:
            close_db(conn)
    return tareas

def update_tarea(tarea_id, descripcion, fecha_vencimiento=None, prioridad=None, estado=None, notas=None, es_plazo_procesal=None, recordatorio_activo=None, recordatorio_dias_antes=None):
    """ Actualiza una tarea existente. Solo actualiza los campos que se proporcionan (no son None). """
    conn = connect_db()
    success = False
    if conn:
        try:
            cursor = conn.cursor()
            
            # Obtener datos actuales y caso_id para actualizar last_activity
            current_tarea = get_tarea_by_id(tarea_id)
            if not current_tarea:
                print(f"Error: Tarea ID {tarea_id} no encontrada para actualizar.")
                return False

            # Construir la consulta dinámicamente
            fields_to_update = []
            values = []

            if descripcion is not None:
                fields_to_update.append("descripcion = ?")
                values.append(descripcion)
            
            # Manejo especial para fecha_vencimiento (puede ser None para quitarla)
            if fecha_vencimiento is not None: # Si se pasa algo (incluso cadena vacía)
                if fecha_vencimiento == "": # Si es cadena vacía, interpretamos como quitar fecha
                    fields_to_update.append("fecha_vencimiento = ?")
                    values.append(None)
                else: # Intentar parsear y formatear
                    try:
                        fv_dt = datetime.datetime.strptime(fecha_vencimiento, "%Y-%m-%d")
                        fields_to_update.append("fecha_vencimiento = ?")
                        values.append(fv_dt.strftime("%Y-%m-%d"))
                    except ValueError:
                        print(f"Advertencia: Formato de fecha_vencimiento ('{fecha_vencimiento}') no válido al actualizar. No se cambiará.")
            
            if prioridad is not None:
                fields_to_update.append("prioridad = ?")
                values.append(prioridad)
            if estado is not None:
                fields_to_update.append("estado = ?")
                values.append(estado)
            if notas is not None:
                fields_to_update.append("notas = ?")
                values.append(notas)
            if es_plazo_procesal is not None:
                fields_to_update.append("es_plazo_procesal = ?")
                values.append(int(es_plazo_procesal)) # Asegurar 0 o 1
            if recordatorio_activo is not None:
                fields_to_update.append("recordatorio_activo = ?")
                values.append(int(recordatorio_activo))
            if recordatorio_dias_antes is not None:
                fields_to_update.append("recordatorio_dias_antes = ?")
                values.append(recordatorio_dias_antes)

            if not fields_to_update:
                print(f"Advertencia: No se proporcionaron campos para actualizar en tarea ID {tarea_id}.")
                return True # No es un error, simplemente no hay nada que hacer

            values.append(tarea_id) # Para el WHERE id = ?
            sql = f"UPDATE tareas SET {', '.join(fields_to_update)} WHERE id = ?"
            
            cursor.execute(sql, values)
            conn.commit()

            if cursor.rowcount > 0:
                print(f"Tarea ID {tarea_id} actualizada con éxito.")
                if current_tarea.get('caso_id'):
                    update_last_activity(current_tarea['caso_id'])
                success = True
            else:
                print(f"Tarea ID {tarea_id} no necesitó actualización (datos iguales).")
                success = True # Considerar éxito si no hay error SQL

        except sqlite3.Error as e:
            print(f"Error al actualizar tarea ID {tarea_id}: {e}")
            conn.rollback()
        finally:
            close_db(conn)
    return success

def delete_tarea(tarea_id):
    """ Elimina una tarea. """
    conn = connect_db()
    success = False
    if conn:
        try:
            current_tarea = get_tarea_by_id(tarea_id) # Para obtener caso_id
            cursor = conn.cursor()
            cursor.execute('DELETE FROM tareas WHERE id = ?', (tarea_id,))
            conn.commit()
            if cursor.rowcount > 0:
                print(f"Tarea ID {tarea_id} eliminada con éxito.")
                if current_tarea and current_tarea.get('caso_id'):
                    update_last_activity(current_tarea['caso_id'])
                success = True
            else:
                print(f"Advertencia: No se eliminó ninguna tarea con ID {tarea_id} (quizás ya no existía).")
                success = False # O True si "no existe" es un resultado aceptable de "eliminar"
        except sqlite3.Error as e:
            print(f"Error al eliminar tarea ID {tarea_id}: {e}")
            conn.rollback()
        finally:
            close_db(conn)
    return success

def get_tareas_para_notificacion():
    """ Obtiene tareas con recordatorio activo cuya fecha de vencimiento está próxima o pasada y no han sido notificadas hoy. """
    conn = connect_db()
    tareas_a_notificar = []
    if conn:
        try:
            cursor = conn.cursor()
            hoy_str_db = datetime.date.today().strftime("%Y-%m-%d") # Fecha de hoy para comparar
            # Seleccionar tareas con recordatorio activo, que no estén completadas/canceladas
            # y cuya fecha de recordatorio (vencimiento - dias_antes) sea hoy o anterior
            # y que la fecha de vencimiento no sea muy antigua (ej. más de 30 días pasada) para no notificar indefinidamente.
            # Y que no hayan sido notificadas hoy.
            # Esta consulta puede necesitar ajustes finos.
            cursor.execute("""
                SELECT t.id, t.descripcion, t.fecha_vencimiento, t.prioridad, t.recordatorio_dias_antes, t.caso_id, c.caratula as caso_caratula
                FROM tareas t
                LEFT JOIN casos c ON t.caso_id = c.id
                WHERE t.recordatorio_activo = 1
                    AND t.estado NOT IN ('Completada', 'Cancelada')
                    AND t.fecha_vencimiento IS NOT NULL
                    AND DATE(t.fecha_vencimiento, '-' || t.recordatorio_dias_antes || ' day') <= ? -- Fecha de recordatorio es hoy o antes
                    AND DATE(t.fecha_vencimiento) >= DATE(?, '-30 day') -- No notificar si venció hace más de 30 días
                    AND (t.fecha_ultima_notificacion IS NULL OR DATE(t.fecha_ultima_notificacion) != ?)
                ORDER BY t.fecha_vencimiento ASC, CASE t.prioridad WHEN 'Alta' THEN 1 WHEN 'Media' THEN 2 WHEN 'Baja' THEN 3 ELSE 4 END ASC
            """, (hoy_str_db, hoy_str_db, hoy_str_db))
            rows = cursor.fetchall()
            tareas_a_notificar = [dict(row) for row in rows]
        except sqlite3.Error as e:
            print(f"Error al obtener tareas para notificación: {e}")
        finally:
            close_db(conn)
    return tareas_a_notificar

def update_fecha_ultima_notificacion_tarea(tarea_id):
    """ Actualiza la fecha_ultima_notificacion de una tarea a ahora. """
    conn = connect_db()
    success = False
    if conn:
        try:
            cursor = conn.cursor()
            ahora_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("UPDATE tareas SET fecha_ultima_notificacion = ? WHERE id = ?", (ahora_str, tarea_id))
            conn.commit()
            success = cursor.rowcount > 0
        except sqlite3.Error as e:
            print(f"Error al actualizar fecha_ultima_notificacion para tarea ID {tarea_id}: {e}")
            conn.rollback()
        finally:
            close_db(conn)
    return success

# --- Fin NUEVAS Funciones CRUD para Tareas ---

# --- Funciones CRUD para Audiencias (sin cambios en su lógica principal) ---
def add_audiencia(caso_id, fecha, hora, descripcion, link="", recordatorio_activo=0, recordatorio_minutos=15):
    conn = connect_db()
    new_id = None
    if conn:
        try:
            cursor = conn.cursor()
            timestamp = int(time.time())
            cursor.execute('''
                INSERT INTO audiencias (caso_id, fecha, hora, descripcion, link, recordatorio_activo, recordatorio_minutos, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (caso_id, fecha, hora, descripcion, link, recordatorio_activo, recordatorio_minutos, timestamp))
            conn.commit()
            new_id = cursor.lastrowid
            update_last_activity(caso_id)
        except sqlite3.Error as e:
            print(f"Error al agregar audiencia: {e}")
            conn.rollback()
        finally:
            close_db(conn)
    return new_id

def get_audiencia_by_id(audiencia_id):
    conn = connect_db()
    audiencia_data = None
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT a.*, ca.caratula as caso_caratula, cl.nombre as cliente_nombre
                FROM audiencias a
                JOIN casos ca ON a.caso_id = ca.id
                JOIN clientes cl ON ca.cliente_id = cl.id
                WHERE a.id = ?
            ''', (audiencia_id,))
            row = cursor.fetchone()
            if row:
                audiencia_data = dict(row)
        except sqlite3.Error as e:
            print(f"Error al obtener audiencia por ID {audiencia_id}: {e}")
        finally:
            close_db(conn)
    return audiencia_data

def get_audiencias_by_fecha(fecha):
    conn = connect_db()
    audiencias = []
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT a.*, ca.caratula as caso_caratula
                FROM audiencias a
                JOIN casos ca ON a.caso_id = ca.id
                WHERE a.fecha = ?
                ORDER BY datetime(a.fecha || ' ' || IFNULL(a.hora, '00:00')) ASC
            ''', (fecha,)) # Usar datetime() para asegurar ordenamiento
            rows = cursor.fetchall()
            audiencias = [dict(row) for row in rows]
        except sqlite3.Error as e:
            print(f"Error al obtener audiencias por fecha {fecha}: {e}")
        finally:
            close_db(conn)
    return audiencias
    
def get_fechas_con_audiencias():
    conn = connect_db()
    fechas = []
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute('SELECT DISTINCT fecha FROM audiencias ORDER BY fecha')
            rows = cursor.fetchall()
            fechas = [row['fecha'] for row in rows]
        except sqlite3.Error as e:
            print(f"Error al obtener fechas con audiencias: {e}")
        finally:
            close_db(conn)
    return fechas

def get_audiencias_con_recordatorio_activo():
    conn = connect_db()
    audiencias = []
    if conn:
        try:
            cursor = conn.cursor()
            # Solo seleccionar las necesarias y optimizar la consulta
            # Usamos date('now', '-1 day') para no buscar demasiado atrás, aunque podría ajustarse.
            # Se asume que 'fecha' es YYYY-MM-DD y 'hora' es HH:MM
            cursor.execute('''
                SELECT id, caso_id, fecha, hora, descripcion, link, recordatorio_minutos, recordatorio_activo
                FROM audiencias
                WHERE recordatorio_activo = 1 
                  AND date(fecha) >= date('now', '-1 day') 
                  AND date(fecha) <= date('now', '+30 day') -- Limitar a un futuro razonable también
                ORDER BY datetime(fecha || ' ' || IFNULL(hora, '00:00')) ASC
            ''')
            rows = cursor.fetchall()
            audiencias = [dict(row) for row in rows]
        except sqlite3.Error as e:
            print(f"Error al obtener audiencias con recordatorio activo: {e}")
        finally:
            close_db(conn)
    return audiencias

def update_audiencia(audiencia_id, fecha, hora, descripcion, link, recordatorio_activo, recordatorio_minutos):
    conn = connect_db()
    success = False
    if conn:
        try:
            cursor = conn.cursor()
            cursor_check = conn.cursor()
            cursor_check.execute('SELECT caso_id FROM audiencias WHERE id = ?', (audiencia_id,))
            row_check = cursor_check.fetchone()

            cursor.execute('''
                UPDATE audiencias
                SET fecha = ?, hora = ?, descripcion = ?, link = ?,
                    recordatorio_activo = ?, recordatorio_minutos = ?
                WHERE id = ?
            ''', (fecha, hora, descripcion, link, recordatorio_activo, recordatorio_minutos, audiencia_id))
            conn.commit()
            if cursor.rowcount > 0 and row_check:
                update_last_activity(row_check['caso_id'])
            success = True
        except sqlite3.Error as e:
            print(f"Error al actualizar audiencia ID {audiencia_id}: {e}")
            conn.rollback()
        finally:
            close_db(conn)
    return success

def delete_audiencia(audiencia_id):
    conn = connect_db()
    success = False
    if conn:
        try:
            cursor = conn.cursor()
            cursor_check = conn.cursor()
            cursor_check.execute('SELECT caso_id FROM audiencias WHERE id = ?', (audiencia_id,))
            row_check = cursor_check.fetchone()

            cursor.execute('DELETE FROM audiencias WHERE id = ?', (audiencia_id,))
            conn.commit()
            if cursor.rowcount > 0 and row_check:
                update_last_activity(row_check['caso_id'])
            success = True
        except sqlite3.Error as e:
            print(f"Error al eliminar audiencia ID {audiencia_id}: {e}")
            conn.rollback()
        finally:
            close_db(conn)
    return success


# --- NUEVAS Funciones CRUD para Partes Intervinientes ---

def add_parte_interviniente(caso_id, nombre, tipo="", direccion="", contacto="", notas=""):
    """ Agrega una nueva parte interviniente a un caso. """
    conn = connect_db()
    new_id = None
    if conn:
        try:
            cursor = conn.cursor()
            timestamp = int(time.time())
            cursor.execute('''
                INSERT INTO partes_intervinientes (caso_id, nombre, tipo, direccion, contacto, notas, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (caso_id, nombre, tipo, direccion, contacto, notas, timestamp))
            conn.commit()
            new_id = cursor.lastrowid
            update_last_activity(caso_id) # Actualizar timestamp del caso
            print(f"Parte ID {new_id} ('{nombre}') agregada al caso ID {caso_id}.")
        except sqlite3.Error as e:
            print(f"Error al agregar parte interviniente al caso ID {caso_id}: {e}")
            conn.rollback()
        finally:
            close_db(conn)
    return new_id

def get_partes_by_caso_id(caso_id):
    """ Obtiene todas las partes intervinientes para un caso específico. """
    conn = connect_db()
    partes = []
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, caso_id, nombre, tipo, direccion, contacto, notas, created_at 
                FROM partes_intervinientes 
                WHERE caso_id = ? 
                ORDER BY nombre ASC
            ''', (caso_id,))
            rows = cursor.fetchall()
            partes = [dict(row) for row in rows]
        except sqlite3.Error as e:
            print(f"Error al obtener partes para el caso ID {caso_id}: {e}")
        finally:
            close_db(conn)
    return partes

def get_parte_by_id(parte_id):
    """ Obtiene una parte interviniente específica por su ID. """
    conn = connect_db()
    parte_data = None
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, caso_id, nombre, tipo, direccion, contacto, notas, created_at 
                FROM partes_intervinientes 
                WHERE id = ?
            ''', (parte_id,))
            row = cursor.fetchone()
            if row:
                parte_data = dict(row)
        except sqlite3.Error as e:
            print(f"Error al obtener parte por ID {parte_id}: {e}")
        finally:
            close_db(conn)
    return parte_data

def update_parte_interviniente(parte_id, nombre, tipo, direccion, contacto, notas):
    """ Actualiza una parte interviniente existente. """
    conn = connect_db()
    success = False
    if conn:
        try:
            cursor = conn.cursor()
            cursor_check = conn.cursor() # Para obtener caso_id
            cursor_check.execute('SELECT caso_id FROM partes_intervinientes WHERE id = ?', (parte_id,))
            row_check = cursor_check.fetchone()

            cursor.execute('''
                UPDATE partes_intervinientes
                SET nombre = ?,
                    tipo = ?,
                    direccion = ?,
                    contacto = ?,
                    notas = ?
                WHERE id = ?
            ''', (nombre, tipo, direccion, contacto, notas, parte_id))
            conn.commit()
            
            if cursor.rowcount > 0 and row_check:
                update_last_activity(row_check['caso_id']) # Actualizar timestamp del caso
                print(f"Parte ID {parte_id} actualizada con éxito.")
                success = True
            elif cursor.rowcount == 0:
                print(f"Parte ID {parte_id} no necesitó actualización (datos iguales) o no se encontró.")
                success = True # Considerar éxito si no hay error, aunque no haya filas cambiadas
            else:
                success = False

        except sqlite3.Error as e:
            print(f"Error al actualizar parte ID {parte_id}: {e}")
            conn.rollback()
        finally:
            close_db(conn)
    return success

def delete_parte_interviniente(parte_id):
    """ Elimina una parte interviniente. """
    conn = connect_db()
    success = False
    if conn:
        try:
            cursor = conn.cursor()
            cursor_check = conn.cursor() # Para obtener caso_id
            cursor_check.execute('SELECT caso_id FROM partes_intervinientes WHERE id = ?', (parte_id,))
            row_check = cursor_check.fetchone()

            cursor.execute('DELETE FROM partes_intervinientes WHERE id = ?', (parte_id,))
            conn.commit()

            if cursor.rowcount > 0 and row_check:
                update_last_activity(row_check['caso_id']) # Actualizar timestamp del caso
                print(f"Parte ID {parte_id} eliminada con éxito.")
                success = True
            elif row_check is None: # La parte no existía
                print(f"Parte ID {parte_id} no encontrada para eliminar.")
                success = False # O True si consideramos "ya no existe" como éxito
            else: # No se eliminó fila pero existía (raro)
                success = False


        except sqlite3.Error as e:
            print(f"Error al eliminar parte ID {parte_id}: {e}")
            conn.rollback()
        finally:
            close_db(conn)
    return success

# En crm_database.py (fuera de cualquier clase, como las otras funciones CRUD)

# --- Funciones CRUD para Etiquetas ---

def add_etiqueta(nombre_etiqueta):
    """
    Agrega una nueva etiqueta si no existe. Devuelve el ID de la etiqueta (nueva o existente).
    El nombre de la etiqueta se guarda en minúsculas para consistencia, pero se compara sin importar mayúsculas/minúsculas.
    """
    conn = connect_db()
    etiqueta_id = None
    if not nombre_etiqueta or not nombre_etiqueta.strip():
        print("Error: El nombre de la etiqueta no puede estar vacío.")
        return None

    # Normalizar el nombre de la etiqueta (ej. a minúsculas y sin espacios extra)
    nombre_etiqueta_normalizado = nombre_etiqueta.strip().lower()

    if conn:
        try:
            cursor = conn.cursor()
            # Primero, verificar si la etiqueta ya existe (ignorando mayúsculas/minúsculas)
            cursor.execute("SELECT id_etiqueta FROM etiquetas WHERE nombre_etiqueta = ?", (nombre_etiqueta_normalizado,))
            row = cursor.fetchone()
            if row:
                etiqueta_id = row['id_etiqueta']
                print(f"Etiqueta '{nombre_etiqueta_normalizado}' ya existe con ID: {etiqueta_id}.")
            else:
                # Si no existe, insertarla
                cursor.execute("INSERT INTO etiquetas (nombre_etiqueta) VALUES (?)", (nombre_etiqueta_normalizado,))
                conn.commit()
                etiqueta_id = cursor.lastrowid
                print(f"Etiqueta '{nombre_etiqueta_normalizado}' agregada con ID: {etiqueta_id}.")
        except sqlite3.IntegrityError: # Por si acaso, aunque el COLLATE NOCASE debería manejarlo en la búsqueda
            print(f"Error de integridad al intentar agregar etiqueta '{nombre_etiqueta_normalizado}'. Podría ya existir con diferente capitalización si no se usa COLLATE NOCASE en la tabla.")
            # Re-intentar obtenerla si falló la inserción por unicidad
            cursor.execute("SELECT id_etiqueta FROM etiquetas WHERE nombre_etiqueta = ?", (nombre_etiqueta_normalizado,))
            row = cursor.fetchone()
            if row: etiqueta_id = row['id_etiqueta']
        except sqlite3.Error as e:
            print(f"Error al agregar o buscar etiqueta '{nombre_etiqueta_normalizado}': {e}")
            if conn: conn.rollback()
        finally:
            close_db(conn)
    return etiqueta_id

def get_etiqueta_by_id(id_etiqueta):
    conn = connect_db()
    etiqueta = None
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id_etiqueta, nombre_etiqueta FROM etiquetas WHERE id_etiqueta = ?", (id_etiqueta,))
            row = cursor.fetchone()
            if row:
                etiqueta = dict(row)
        except sqlite3.Error as e:
            print(f"Error al obtener etiqueta por ID {id_etiqueta}: {e}")
        finally:
            close_db(conn)
    return etiqueta

def get_todas_las_etiquetas():
    """ Obtiene todas las etiquetas ordenadas alfabéticamente. """
    conn = connect_db()
    etiquetas = []
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id_etiqueta, nombre_etiqueta FROM etiquetas ORDER BY nombre_etiqueta ASC")
            rows = cursor.fetchall()
            etiquetas = [dict(row) for row in rows]
        except sqlite3.Error as e:
            print(f"Error al obtener todas las etiquetas: {e}")
        finally:
            close_db(conn)
    return etiquetas

def delete_etiqueta(id_etiqueta):
    """ Elimina una etiqueta y todas sus asociaciones. ¡Usar con cuidado! """
    conn = connect_db()
    success = False
    if conn:
        try:
            cursor = conn.cursor()
            # ON DELETE CASCADE en las tablas de unión se encargará de borrar las asociaciones.
            cursor.execute("DELETE FROM etiquetas WHERE id_etiqueta = ?", (id_etiqueta,))
            conn.commit()
            if cursor.rowcount > 0:
                print(f"Etiqueta ID {id_etiqueta} y sus asociaciones eliminadas.")
                success = True
            else:
                print(f"No se encontró etiqueta con ID {id_etiqueta} para eliminar.")
        except sqlite3.Error as e:
            print(f"Error al eliminar etiqueta ID {id_etiqueta}: {e}")
            if conn: conn.rollback()
        finally:
            close_db(conn)
    return success

# --- Funciones para Asignar/Quitar Etiquetas a Clientes ---

def asignar_etiqueta_a_cliente(cliente_id, etiqueta_id):
    conn = connect_db()
    success = False
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO cliente_etiquetas (cliente_id, etiqueta_id) VALUES (?, ?)", (cliente_id, etiqueta_id))
            conn.commit()
            # rowcount podría ser 0 si la asignación ya existía (debido a INSERT OR IGNORE),
            # lo cual consideramos un éxito en el sentido de que la asignación está presente.
            success = True 
            print(f"Etiqueta ID {etiqueta_id} asignada (o ya estaba asignada) a cliente ID {cliente_id}.")
        except sqlite3.Error as e: # Podría ser un error de Foreign Key si cliente_id o etiqueta_id no existen
            print(f"Error al asignar etiqueta ID {etiqueta_id} a cliente ID {cliente_id}: {e}")
            if conn: conn.rollback()
        finally:
            close_db(conn)
    return success

def quitar_etiqueta_de_cliente(cliente_id, etiqueta_id):
    conn = connect_db()
    success = False
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM cliente_etiquetas WHERE cliente_id = ? AND etiqueta_id = ?", (cliente_id, etiqueta_id))
            conn.commit()
            if cursor.rowcount > 0:
                print(f"Etiqueta ID {etiqueta_id} quitada del cliente ID {cliente_id}.")
                success = True
            else:
                print(f"No se encontró la asignación de etiqueta ID {etiqueta_id} para cliente ID {cliente_id}.")
                success = True # No es un error si no estaba asignada
        except sqlite3.Error as e:
            print(f"Error al quitar etiqueta ID {etiqueta_id} de cliente ID {cliente_id}: {e}")
            if conn: conn.rollback()
        finally:
            close_db(conn)
    return success

def get_etiquetas_de_cliente(cliente_id):
    """ Obtiene una lista de objetos etiqueta (dict) asignados a un cliente. """
    conn = connect_db()
    etiquetas_cliente = []
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT e.id_etiqueta, e.nombre_etiqueta 
                FROM etiquetas e
                JOIN cliente_etiquetas ce ON e.id_etiqueta = ce.etiqueta_id
                WHERE ce.cliente_id = ?
                ORDER BY e.nombre_etiqueta ASC
            ''', (cliente_id,))
            rows = cursor.fetchall()
            etiquetas_cliente = [dict(row) for row in rows]
        except sqlite3.Error as e:
            print(f"Error al obtener etiquetas para el cliente ID {cliente_id}: {e}")
        finally:
            close_db(conn)
    return etiquetas_cliente

# --- Funciones para Asignar/Quitar Etiquetas a Casos ---

def asignar_etiqueta_a_caso(caso_id, etiqueta_id):
    conn = connect_db()
    success = False
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO caso_etiquetas (caso_id, etiqueta_id) VALUES (?, ?)", (caso_id, etiqueta_id))
            conn.commit()
            success = True
            print(f"Etiqueta ID {etiqueta_id} asignada (o ya estaba asignada) a caso ID {caso_id}.")
        except sqlite3.Error as e:
            print(f"Error al asignar etiqueta ID {etiqueta_id} a caso ID {caso_id}: {e}")
            if conn: conn.rollback()
        finally:
            close_db(conn)
    return success

def quitar_etiqueta_de_caso(caso_id, etiqueta_id):
    conn = connect_db()
    success = False
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM caso_etiquetas WHERE caso_id = ? AND etiqueta_id = ?", (caso_id, etiqueta_id))
            conn.commit()
            if cursor.rowcount > 0:
                print(f"Etiqueta ID {etiqueta_id} quitada del caso ID {caso_id}.")
                success = True
            else:
                print(f"No se encontró la asignación de etiqueta ID {etiqueta_id} para caso ID {caso_id}.")
                success = True
        except sqlite3.Error as e:
            print(f"Error al quitar etiqueta ID {etiqueta_id} de caso ID {caso_id}: {e}")
            if conn: conn.rollback()
        finally:
            close_db(conn)
    return success

def get_etiquetas_de_caso(caso_id):
    """ Obtiene una lista de objetos etiqueta (dict) asignados a un caso. """
    conn = connect_db()
    etiquetas_caso = []
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT e.id_etiqueta, e.nombre_etiqueta 
                FROM etiquetas e
                JOIN caso_etiquetas ce ON e.id_etiqueta = ce.etiqueta_id
                WHERE ce.caso_id = ?
                ORDER BY e.nombre_etiqueta ASC
            ''', (caso_id,))
            rows = cursor.fetchall()
            etiquetas_caso = [dict(row) for row in rows]
        except sqlite3.Error as e:
            print(f"Error al obtener etiquetas para el caso ID {caso_id}: {e}")
        finally:
            close_db(conn)
    return etiquetas_caso

# --- Fin Funciones CRUD para Etiquetas ---

# --- Inicializar la base de datos ---
create_tables()