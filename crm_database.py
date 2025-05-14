import sqlite3
import os
import time # Para timestamps
import datetime # Para fechas de audiencias

# Nombre del archivo de la base de datos
DATABASE_FILE = 'crm_legal.db'

def connect_db():
    """ Establece una conexión con la base de datos SQLite. Crea el archivo si no existe. """
    try:
        conn = sqlite3.connect(DATABASE_FILE, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES) # Detectar tipos
        # Habilitar soporte para claves foráneas
        conn.execute('PRAGMA foreign_keys = ON;')
        # Configurar el row_factory para acceder a las columnas por nombre
        conn.row_factory = sqlite3.Row
        # print(f"Conectado a la base de datos: {DATABASE_FILE}") # Descomentar para depurar
        return conn
    except sqlite3.Error as e:
        print(f"Error al conectar a la base de datos: {e}")
        return None

def close_db(conn):
    """ Cierra la conexión con la base de datos. """
    if conn:
        conn.close()
        # print("Conexión a la base de datos cerrada.") # Comentado para evitar mucho output

def create_tables():
    """ Crea las tablas en la base de datos si no existen, basado en el esquema. """
    conn = connect_db()
    if conn:
        try:
            cursor = conn.cursor()
            
            # >>> NUEVA TABLA: actividades_caso <<<
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS actividades_caso (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    caso_id INTEGER NOT NULL,
                    fecha_hora TEXT NOT NULL, -- Formato YYYY-MM-DD HH:MM:SS para ordenamiento preciso
                    tipo_actividad TEXT NOT NULL, 
                    descripcion TEXT NOT NULL,
                    creado_por TEXT, -- Podría ser útil si varias personas usaran la app
                    referencia_documento TEXT, -- Opcional: ruta o ID de un documento relacionado
                    FOREIGN KEY (caso_id) REFERENCES casos(id) ON DELETE CASCADE
                );
            ''')
            # Crear un índice para búsquedas rápidas por caso_id y fecha_hora
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_actividades_caso_id_fecha
                ON actividades_caso (caso_id, fecha_hora DESC);
            ''')

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
                    numero_expediente TEXT, -- Permitir NULL temporalmente si se crea caso rápido
                    anio_caratula TEXT,     -- Permitir NULL temporalmente
                    caratula TEXT NOT NULL,
                    juzgado TEXT,
                    jurisdiccion TEXT,
                    etapa_procesal TEXT,
                    notas TEXT,
                    ruta_carpeta TEXT,
                    inactivity_threshold_days INTEGER DEFAULT 30,
                    inactivity_enabled INTEGER DEFAULT 1, -- 1 for True, 0 for False
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
                    fecha TEXT NOT NULL, -- YYYY-MM-DD format
                    hora TEXT,           -- HH:MM format (puede ser NULL)
                    descripcion TEXT NOT NULL,
                    link TEXT,
                    recordatorio_activo INTEGER DEFAULT 0, -- 1 for True, 0 for False
                    recordatorio_minutos INTEGER DEFAULT 15,
                    created_at INTEGER,
                    FOREIGN KEY (caso_id) REFERENCES casos(id) ON DELETE CASCADE
                );
            ''')
            # Crear índices para búsquedas comunes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_audiencias_fecha ON audiencias (fecha);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_audiencias_caso_id ON audiencias (caso_id);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_audiencias_recordatorio ON audiencias (recordatorio_activo);')

            # Tabla partes_intervinientes (sin cambios)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS partes_intervinientes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    caso_id INTEGER NOT NULL,
                    nombre TEXT NOT NULL,
                    tipo TEXT, -- e.g., 'testigo', 'abogado'
                    direccion TEXT,
                    contacto TEXT,
                    created_at INTEGER,
                    FOREIGN KEY (caso_id) REFERENCES casos(id) ON DELETE CASCADE
                );
            ''')

            conn.commit()
            print("Tablas verificadas/creadas con éxito.")
        except sqlite3.Error as e:
            print(f"Error al crear tablas: {e}")
            conn.rollback() # Revertir cambios si hay error
        finally:
            close_db(conn)

# --- Funciones CRUD para Actividades del Caso ---

def add_actividad_caso(caso_id, fecha_hora, tipo_actividad, descripcion, creado_por=None, referencia_documento=None):
    """ Agrega una nueva actividad/log a un caso. """
    conn = connect_db()
    if conn:
        try:
            cursor = conn.cursor()
            # Asegurarse de que la fecha_hora tenga un formato consistente para ordenar
            # Si solo se pasa fecha, se podría añadir hora 00:00:00
            # Por ahora, asumimos que fecha_hora viene formateada (ej. desde datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            cursor.execute('''
                INSERT INTO actividades_caso (caso_id, fecha_hora, tipo_actividad, descripcion, creado_por, referencia_documento)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (caso_id, fecha_hora, tipo_actividad, descripcion, creado_por, referencia_documento))
            conn.commit()
            new_id = cursor.lastrowid
            # Actualizar el last_activity_timestamp del caso
            update_last_activity(caso_id) # Llama a tu función existente
            print(f"Actividad ID {new_id} agregada al caso ID {caso_id}.")
            return new_id
        except sqlite3.Error as e:
            print(f"Error al agregar actividad al caso ID {caso_id}: {e}")
            conn.rollback()
            return None
        finally:
            close_db(conn)

def get_actividades_by_caso_id(caso_id, order_desc=True):
    """ Obtiene todas las actividades para un caso específico, ordenadas por fecha_hora. """
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
                ORDER BY fecha_hora {order_direction}
            '''
            cursor.execute(sql, (caso_id,))
            rows = cursor.fetchall()
            actividades = [dict(row) for row in rows]
        except sqlite3.Error as e:
            print(f"Error al obtener actividades para el caso ID {caso_id}: {e}")
        finally:
            close_db(conn)
    return actividades

def get_audiencias_by_case(caso_id):
    """ Obtiene todas las audiencias para un caso específico (ID), incluyendo info básica. """
    conn = connect_db()
    audiencias = []
    if conn:
        try:
            cursor = conn.cursor()
            # No necesitamos unir con casos aquí, ya sabemos el caso_id
            cursor.execute('''
                SELECT id, fecha, hora, descripcion, link, recordatorio_activo, recordatorio_minutos
                FROM audiencias
                WHERE caso_id = ?
                ORDER BY fecha ASC, hora ASC
            ''', (caso_id,))
            rows = cursor.fetchall()
            audiencias = [dict(row) for row in rows]
        except sqlite3.Error as e:
            print(f"Error al obtener audiencias por caso ID {caso_id}: {e}")
        finally:
            close_db(conn)
    return audiencias

# --- Fin de la nueva función ---

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
            print(f"Cliente '{nombre}' agregado con éxito.")
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
            clients = [dict(row) for row in rows] # Convertir a lista de diccionarios
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
            print(f"Cliente ID {client_id} actualizado con éxito.")
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
            print(f"Cliente ID {client_id} eliminado con éxito (y sus casos/audiencias asociados).")
            success = True
        except sqlite3.Error as e:
            print(f"Error al eliminar cliente ID {client_id}: {e}")
            conn.rollback()
        finally:
            close_db(conn)
    return success


# --- Funciones de Interacción con Casos ---

def add_case(cliente_id, caratula, numero_expediente="", anio_caratula="", juzgado="", jurisdiccion="", etapa_procesal="", notas="", ruta_carpeta="", inactivity_threshold_days=30, inactivity_enabled=1):
    """ Agrega un nuevo caso a la base de datos. """
    conn = connect_db()
    new_id = None
    if conn:
        try:
            cursor = conn.cursor()
            timestamp = int(time.time())
            cursor.execute('''
                INSERT INTO casos (cliente_id, numero_expediente, anio_caratula, caratula, juzgado, jurisdiccion, etapa_procesal, notas, ruta_carpeta, inactivity_threshold_days, inactivity_enabled, created_at, last_activity_timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (cliente_id, numero_expediente, anio_caratula, caratula, juzgado, jurisdiccion, etapa_procesal, notas, ruta_carpeta, inactivity_threshold_days, inactivity_enabled, timestamp, timestamp)) # last_activity_timestamp starts with creation time
            conn.commit()
            new_id = cursor.lastrowid
            print(f"Caso '{caratula}' agregado con éxito para cliente ID {cliente_id}. Nuevo ID: {new_id}")
        except sqlite3.Error as e:
            print(f"Error al agregar caso: {e}")
            conn.rollback()
        finally:
            close_db(conn)
    return new_id

def get_cases_by_client(cliente_id):
    """ Obtiene todos los casos asociados a un cliente específico. """
    conn = connect_db()
    cases = []
    if conn:
        try:
            cursor = conn.cursor()
            # Seleccionar también el nombre del cliente para referencia
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
    """ Obtiene un caso por su ID. """
    conn = connect_db()
    case_data = None
    if conn:
        try:
            cursor = conn.cursor()
            # Seleccionar también el nombre del cliente
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
    """ Actualiza los datos de un caso existente. """
    conn = connect_db()
    success = False
    if conn:
        try:
            cursor = conn.cursor()
            # Actualizar también el last_activity_timestamp podría tener sentido aquí,
            # pero por ahora solo actualizamos los campos provistos.
            cursor.execute('''
                UPDATE casos
                SET caratula = ?, numero_expediente = ?, anio_caratula = ?, juzgado = ?,
                    jurisdiccion = ?, etapa_procesal = ?, notas = ?, ruta_carpeta = ?,
                    inactivity_threshold_days = ?, inactivity_enabled = ?
                WHERE id = ?
            ''', (caratula, numero_expediente, anio_caratula, juzgado, jurisdiccion, etapa_procesal, notas, ruta_carpeta, inactivity_threshold_days, inactivity_enabled, case_id))
            conn.commit()
            print(f"Caso ID {case_id} actualizado con éxito.")
            success = True
        except sqlite3.Error as e:
            print(f"Error al actualizar caso ID {case_id}: {e}")
            conn.rollback()
        finally:
            close_db(conn)
    return success

def delete_case(case_id):
    """ Elimina un caso por su ID (y sus audiencias/partes asociadas). """
    conn = connect_db()
    success = False
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM casos WHERE id = ?', (case_id,))
            conn.commit()
            print(f"Caso ID {case_id} eliminado con éxito (y sus audiencias/partes asociadas).")
            success = True
        except sqlite3.Error as e:
            print(f"Error al eliminar caso ID {case_id}: {e}")
            conn.rollback()
        finally:
            close_db(conn)
    return success

def update_case_folder(case_id, folder_path):
    """ Actualiza solo la ruta de la carpeta de un caso. """
    conn = connect_db()
    success = False
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute('UPDATE casos SET ruta_carpeta = ? WHERE id = ?', (folder_path, case_id))
            conn.commit()
            print(f"Ruta de carpeta actualizada para caso ID {case_id}.")
            success = True
        except sqlite3.Error as e:
            print(f"Error al actualizar ruta de carpeta para caso ID {case_id}: {e}")
            conn.rollback()
        finally:
            close_db(conn)
    return success

def update_last_activity(case_id):
    """ Actualiza el timestamp de última actividad de un caso. """
    conn = connect_db()
    success = False
    if conn:
        try:
            cursor = conn.cursor()
            timestamp = int(time.time())
            cursor.execute('UPDATE casos SET last_activity_timestamp = ? WHERE id = ?', (timestamp, case_id))
            conn.commit()
            print(f"Timestamp de actividad actualizado para caso ID {case_id}.") # Puede ser muy verboso
            success = True
        except sqlite3.Error as e:
            print(f"Error al actualizar timestamp de actividad para caso ID {case_id}: {e}")
            conn.rollback()
        finally:
            close_db(conn)
    return success

# --- Funciones de Interacción con Audiencias ---

def add_audiencia(caso_id, fecha, hora, descripcion, link="", recordatorio_activo=0, recordatorio_minutos=15):
    """ Agrega una nueva audiencia a la base de datos. """
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
            print(f"Audiencia agregada con éxito para caso ID {caso_id}. Nuevo ID: {new_id}")
            # Actualizar actividad del caso asociado
            update_last_activity(caso_id)
        except sqlite3.Error as e:
            print(f"Error al agregar audiencia: {e}")
            conn.rollback()
        finally:
            close_db(conn)
    return new_id

def get_audiencia_by_id(audiencia_id):
    """ Obtiene una audiencia por su ID, incluyendo info del caso y cliente. """
    conn = connect_db()
    audiencia_data = None
    if conn:
        try:
            cursor = conn.cursor()
            # Unir con casos y clientes para obtener más contexto
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
    """ Obtiene todas las audiencias para una fecha específica (YYYY-MM-DD), incluyendo info del caso. """
    conn = connect_db()
    audiencias = []
    if conn:
        try:
            cursor = conn.cursor()
            # Unir con casos para obtener carátula
            cursor.execute('''
                SELECT a.*, ca.caratula as caso_caratula
                FROM audiencias a
                JOIN casos ca ON a.caso_id = ca.id
                WHERE a.fecha = ?
                ORDER BY a.hora ASC
            ''', (fecha,))
            rows = cursor.fetchall()
            audiencias = [dict(row) for row in rows]
        except sqlite3.Error as e:
            print(f"Error al obtener audiencias por fecha {fecha}: {e}")
        finally:
            close_db(conn)
    return audiencias

def get_todas_audiencias(order_by='fecha_hora'):
    """ Obtiene todas las audiencias, opcionalmente ordenadas. Incluye info del caso. """
    conn = connect_db()
    audiencias = []
    if conn:
        try:
            cursor = conn.cursor()
            query = '''
                SELECT a.*, ca.caratula as caso_caratula
                FROM audiencias a
                JOIN casos ca ON a.caso_id = ca.id
            '''
            if order_by == 'fecha_hora':
                query += ' ORDER BY a.fecha ASC, a.hora ASC'
            elif order_by == 'caso':
                 query += ' ORDER BY ca.caratula ASC, a.fecha ASC, a.hora ASC'
            # Añadir más órdenes si es necesario

            cursor.execute(query)
            rows = cursor.fetchall()
            audiencias = [dict(row) for row in rows]
        except sqlite3.Error as e:
            print(f"Error al obtener todas las audiencias: {e}")
        finally:
            close_db(conn)
    return audiencias


def update_audiencia(audiencia_id, fecha, hora, descripcion, link, recordatorio_activo, recordatorio_minutos):
    """ Actualiza una audiencia existente. No cambia el caso_id. """
    conn = connect_db()
    success = False
    caso_id_afectado = None
    if conn:
        try:
            # Obtener primero el caso_id para actualizar su timestamp
            cursor_check = conn.cursor()
            cursor_check.execute('SELECT caso_id FROM audiencias WHERE id = ?', (audiencia_id,))
            row = cursor_check.fetchone()
            if row:
                caso_id_afectado = row['caso_id']

            cursor = conn.cursor()
            cursor.execute('''
                UPDATE audiencias
                SET fecha = ?, hora = ?, descripcion = ?, link = ?,
                    recordatorio_activo = ?, recordatorio_minutos = ?
                WHERE id = ?
            ''', (fecha, hora, descripcion, link, recordatorio_activo, recordatorio_minutos, audiencia_id))
            conn.commit()
            print(f"Audiencia ID {audiencia_id} actualizada con éxito.")
            success = True
            # Actualizar actividad del caso asociado
            if caso_id_afectado:
                update_last_activity(caso_id_afectado)

        except sqlite3.Error as e:
            print(f"Error al actualizar audiencia ID {audiencia_id}: {e}")
            conn.rollback()
        finally:
            close_db(conn)
    return success

def delete_audiencia(audiencia_id):
    """ Elimina una audiencia por su ID. """
    conn = connect_db()
    success = False
    caso_id_afectado = None
    if conn:
        try:
            # Obtener primero el caso_id para actualizar su timestamp
            cursor_check = conn.cursor()
            cursor_check.execute('SELECT caso_id FROM audiencias WHERE id = ?', (audiencia_id,))
            row = cursor_check.fetchone()
            if row:
                caso_id_afectado = row['caso_id']

            cursor = conn.cursor()
            cursor.execute('DELETE FROM audiencias WHERE id = ?', (audiencia_id,))
            conn.commit()
            print(f"Audiencia ID {audiencia_id} eliminada con éxito.")
            success = True
             # Actualizar actividad del caso asociado
            if caso_id_afectado:
                update_last_activity(caso_id_afectado)

        except sqlite3.Error as e:
            print(f"Error al eliminar audiencia ID {audiencia_id}: {e}")
            conn.rollback()
        finally:
            close_db(conn)
    return success

def get_fechas_con_audiencias():
    """ Obtiene una lista de fechas (YYYY-MM-DD) que tienen al menos una audiencia. """
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
    """ Obtiene todas las audiencias con recordatorio activado. """
    conn = connect_db()
    audiencias = []
    if conn:
        try:
            cursor = conn.cursor()
            # Optimización: Solo seleccionar las necesarias para el recordatorio
            cursor.execute('''
                SELECT id, fecha, hora, descripcion, link, recordatorio_minutos
                FROM audiencias
                WHERE recordatorio_activo = 1 AND fecha >= date('now', '-1 day') -- Optimización: No buscar muy antiguas
                ORDER BY fecha, hora
            ''')
            rows = cursor.fetchall()
            audiencias = [dict(row) for row in rows]
        except sqlite3.Error as e:
            print(f"Error al obtener audiencias con recordatorio activo: {e}")
        finally:
            close_db(conn)
    return audiencias

# --- Funciones de Interacción con Partes Intervinientes (Placeholder) ---
# def add_parte(...): ...
# def get_partes_by_case(...): ...
# def update_parte(...): ...
# def delete_parte(...): ...


# --- Inicializar la base de datos y crear tablas al importar el módulo ---
create_tables()

# --- Ejemplo de uso (Mantenido comentado) ---
# if __name__ == '__main__':
#     # ... (código de ejemplo) ...
#     pass