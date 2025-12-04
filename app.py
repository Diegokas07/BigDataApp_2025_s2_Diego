from flask import Flask, render_template, request, redirect, url_for,jsonify, session, flash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import os
from datetime import datetime
from Helpers import MongoDB, ElasticSearch, Funciones, WebScraping

# Cargar variables de entorno
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'Diego_12345')

# Configuración MongoDB
MONGO_URI = os.getenv('MONGO_URI', '')
MONGO_DB = os.getenv('MONGO_DB', '')
MONGO_COLECCION = os.getenv('MONGO_COLECCION', 'usuario_roles')

# Configuración ElasticSearch Cloud
ELASTIC_CLOUD_URL       = os.getenv('ELASTIC_CLOUD_URL', '')
ELASTIC_API_KEY         = os.getenv('ELASTIC_API_KEY', '')
ELASTIC_INDEX_DEFAULT   = os.getenv('ELASTIC_INDEX_DEFAULT', 'index_cuentos')

# Versión de la aplicación
VERSION_APP = "1.3.0"
CREATOR_APP = "DIEGO_ARMANDO CASTILLO M."

# Inicializar conexiones
mongo = MongoDB(MONGO_URI, MONGO_DB)
elastic = ElasticSearch(ELASTIC_CLOUD_URL, ELASTIC_API_KEY)


# ==================== RUTAS ====================
@app.route('/')
def landing():
    """Landing page pública"""
    return render_template('landing.html', version=VERSION_APP, creador=CREATOR_APP)

@app.route('/about')
def about():
    """Página About"""
    return render_template('about.html', version=VERSION_APP, creador=CREATOR_APP)

#--------------rutas del buscador en elastic-inicio-------------
@app.route('/buscador')
def buscador():
    """Página de búsqueda pública"""
    return render_template('buscador.html', version=VERSION_APP, creador=CREATOR_APP)

@app.route('/buscar-elastic', methods=['POST'])
def buscar_elastic():
    """API para realizar búsqueda en ElasticSearch"""
    try:
        data = request.get_json()
        texto_buscar = data.get('texto', '').strip()
        campo = data.get('campo', '_all')
        
        if not texto_buscar:
            return jsonify({
                'success': False,
                'error': 'Texto de búsqueda es requerido'
            }), 400
        
        # Buscar en TODOS los campos de ambos índices
        if campo == '_all':
            query_base = {
                "query": {
                    "query_string": {
                        "query": f"*{texto_buscar}*",
                        "fields": ["*"],
                        "default_operator": "OR"
                    }
                }
            }
        else:
            query_base = {
                "query": {
                    "match": {
                        campo: texto_buscar
                    }
                }
            }
        
        aggs= {
            "documentos_por_anio": {
                "terms": {
                    "field": "año",
                    "size": 20,
                    "order": {"_key": "desc"}
                }
            },
            "documentos_por_tipo": {
                "terms": {
                    "field": "tipo_documento.keyword",
                    "size": 20
                }
            },
            "documentos_por_indice": {
                "terms": {
                    "field": "_index",
                    "size": 10
                }
            }
        }
        
        # Buscar específicamente en los dos índices de mineducación
        indices_busqueda = "index_mineducacion,index_mineducacion_v2"
        
        resultado = elastic.buscar(
            index=indices_busqueda,
            query=query_base,
            aggs=aggs,            
            size=100
        )
        print(f"📚 Buscando '{texto_buscar}' en índices: {indices_busqueda}")
        print(f"✅ Total encontrado: {resultado.get('total', 0)}")
        if resultado.get('success') and resultado.get('resultados'):
            indices_con_resultados = {}
            for hit in resultado['resultados']:
                idx = hit['_index']
                indices_con_resultados[idx] = indices_con_resultados.get(idx, 0) + 1
            print(f"📊 Distribución por índice: {indices_con_resultados}") 
        
        return jsonify(resultado)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
#--------------rutas del buscador en elastic-fin-------------
#--------------rutas de mongodb (usuarios)-inicio-------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    """Página de login con validación"""
    if request.method == 'POST':
        usuario = request.form.get('usuario')
        password = request.form.get('password')
        
        # Validar que usuario y password no sean None
        if not usuario or not password:
            flash('Usuario y contraseña son requeridos', 'danger')
            return render_template('login.html')
        
        # Validar usuario en MongoDB
        user_data = mongo.validar_usuario(usuario, password, MONGO_COLECCION)
        
        if user_data:
            # Guardar sesión
            session['usuario'] = usuario
            session['permisos'] = user_data.get('permisos', {})
            session['logged_in'] = True
            
            flash('¡Bienvenido! Inicio de sesión exitoso', 'success')
            return redirect(url_for('admin'))
        else:
            flash('Usuario o contraseña incorrectos', 'danger')
    
    return render_template('login.html')

@app.route('/listar-usuarios')
def listar_usuarios():
    try:

        usuarios = mongo.listar_usuarios(MONGO_COLECCION)
        
        # Convertir ObjectId a string para serialización JSON
        for usuario in usuarios:
            usuario['_id'] = str(usuario['_id'])
        
        return jsonify(usuarios)
    except Exception as e:
        return jsonify({'error': str(e)}), 500 

@app.route('/gestor_usuarios')
def gestor_usuarios():
    """Página de gestión de usuarios (protegida requiere login y permiso admin_usuarios) """
    if not session.get('logged_in'):
        flash('Por favor, inicia sesión para acceder a esta página', 'warning')
        return redirect(url_for('login'))
    
    permisos = session.get('permisos', {})
    if not permisos.get('admin_usuarios'):
        flash('No tiene permisos para gestionar usuarios', 'danger')
        return redirect(url_for('admin'))
    
    return render_template('gestor_usuarios.html', usuario=session.get('usuario'), permisos=permisos, version=VERSION_APP, creador=CREATOR_APP)

@app.route('/crear-usuario', methods=['POST'])
def crear_usuario():
    """API para crear un nuevo usuario"""
    try:
        if not session.get('logged_in'):
            return jsonify({'success': False, 'error': 'No autorizado'}), 401
        
        permisos = session.get('permisos', {})
        if not permisos.get('admin_usuarios'):
            return jsonify({'success': False, 'error': 'No tiene permisos para crear usuarios'}), 403
        
        data = request.get_json()
        usuario = data.get('usuario')
        password = data.get('password')
        permisos_usuario = data.get('permisos', {})
        
        if not usuario or not password:
            return jsonify({'success': False, 'error': 'Usuario y password son requeridos'}), 400
        
        # Verificar si el usuario ya existe
        usuario_existente = mongo.obtener_usuario(usuario, MONGO_COLECCION)
        if usuario_existente:
            return jsonify({'success': False, 'error': 'El usuario ya existe'}), 400
        
        # Crear usuario
        resultado = mongo.crear_usuario(usuario, password, permisos_usuario, MONGO_COLECCION)
        
        if resultado:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Error al crear usuario'}), 500
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/actualizar-usuario', methods=['POST'])
def actualizar_usuario():
    """API para actualizar un usuario existente"""
    try:
        if not session.get('logged_in'):
            return jsonify({'success': False, 'error': 'No autorizado'}), 401
        
        permisos = session.get('permisos', {})
        if not permisos.get('admin_usuarios'):
            return jsonify({'success': False, 'error': 'No tiene permisos para actualizar usuarios'}), 403
        
        data = request.get_json()
        usuario_original = data.get('usuario_original')
        datos_usuario = data.get('datos', {})
        
        if not usuario_original:
            return jsonify({'success': False, 'error': 'Usuario original es requerido'}), 400
        
        # Verificar si el usuario existe
        usuario_existente = mongo.obtener_usuario(usuario_original, MONGO_COLECCION)
        if not usuario_existente:
            return jsonify({'success': False, 'error': 'Usuario no encontrado'}), 404
        
        # Si el nombre de usuario cambió, verificar que no exista otro con ese nombre
        nuevo_usuario = datos_usuario.get('usuario')
        if nuevo_usuario and nuevo_usuario != usuario_original:
            usuario_duplicado = mongo.obtener_usuario(nuevo_usuario, MONGO_COLECCION)
            if usuario_duplicado:
                return jsonify({'success': False, 'error': 'Ya existe otro usuario con ese nombre'}), 400
        
        # Actualizar usuario
        resultado = mongo.actualizar_usuario(usuario_original, datos_usuario, MONGO_COLECCION)
        
        if resultado:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Error al actualizar usuario'}), 500
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/eliminar-usuario', methods=['POST'])
def eliminar_usuario():
    """API para eliminar un usuario"""
    try:
        if not session.get('logged_in'):
            return jsonify({'success': False, 'error': 'No autorizado'}), 401
        
        permisos = session.get('permisos', {})
        if not permisos.get('admin_usuarios'):
            return jsonify({'success': False, 'error': 'No tiene permisos para eliminar usuarios'}), 403
        
        data = request.get_json()
        usuario = data.get('usuario')
        
        if not usuario:
            return jsonify({'success': False, 'error': 'Usuario es requerido'}), 400
        
        # Verificar si el usuario existe
        usuario_existente = mongo.obtener_usuario(usuario, MONGO_COLECCION)
        if not usuario_existente:
            return jsonify({'success': False, 'error': 'Usuario no encontrado'}), 404
        
        # No permitir eliminar al usuario actual
        if usuario == session.get('usuario'):
            return jsonify({'success': False, 'error': 'No puede eliminarse a sí mismo'}), 400
        
        # Eliminar usuario
        resultado = mongo.eliminar_usuario(usuario, MONGO_COLECCION)
        
        if resultado:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Error al eliminar usuario'}), 500
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

#--------------rutas de mongodb (usuarios)-fin-------------
#--------------rutas de elasitcsearch - inicio-------------
@app.route('/gestor_elastic')
def gestor_elastic():
    """Página de gestión de ElasticSearch (protegida requiere login y permiso admin_elastic)"""
    if not session.get('logged_in'):
        flash('Por favor, inicia sesión para acceder a esta página', 'warning')
        return redirect(url_for('login'))
    
    permisos = session.get('permisos', {})
    if not permisos.get('admin_elastic'):
        flash('No tiene permisos para gestionar ElasticSearch', 'danger')
        return redirect(url_for('admin'))
    
    return render_template('gestor_elastic.html', usuario=session.get('usuario'), permisos=permisos, version=VERSION_APP, creador=CREATOR_APP)

@app.route('/listar-indices-elastic')
def listar_indices_elastic():
    """API para listar índices de ElasticSearch"""
    try:
        if not session.get('logged_in'):
            return jsonify({'error': 'No autorizado'}), 401
        
        permisos = session.get('permisos', {})
        if not permisos.get('admin_elastic'):
            return jsonify({'error': 'No tiene permisos para gestionar ElasticSearch'}), 403
        
        indices = elastic.listar_indices()
        return jsonify(indices)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@app.route('/ejecutar-query-elastic', methods=['POST'])
def ejecutar_query_elastic():
    """API para ejecutar una query en ElasticSearch"""
    try:
        if not session.get('logged_in'):
            return jsonify({'success': False, 'error': 'No autorizado'}), 401
        
        permisos = session.get('permisos', {})
        if not permisos.get('admin_elastic'):
            return jsonify({'success': False, 'error': 'No tiene permisos para gestionar ElasticSearch'}), 403
        
        data = request.get_json()
        query_json = data.get('query')
        
        if not query_json:
            return jsonify({'success': False, 'error': 'Query es requerida'}), 400
        
        resultado = elastic.ejecutar_query(query_json)
        return jsonify(resultado)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/cargar_doc_elastic')
def cargar_doc_elastic():
    """Página de carga de documentos a ElasticSearch (protegida requiere login y permiso admin_data_elastic)"""
    if not session.get('logged_in'):
        flash('Por favor, inicia sesión para acceder a esta página', 'warning')
        return redirect(url_for('login'))
    
    permisos = session.get('permisos', {})
    if not permisos.get('admin_data_elastic'):
        flash('No tiene permisos para cargar datos a ElasticSearch', 'danger')
        return redirect(url_for('admin'))
    
    return render_template('documentos_elastic.html', usuario=session.get('usuario'), permisos=permisos, version=VERSION_APP, creador=CREATOR_APP)

# Ruta duplicada eliminada: procesar_webscraping_elastic (se mantiene la definición posterior)

@app.route('/procesar-zip-elastic', methods=['POST'])
def procesar_zip_elastic():
    """API para procesar archivo ZIP con archivos JSON"""
    try:
        if not session.get('logged_in'):
            return jsonify({'success': False, 'error': 'No autorizado'}), 401
        
        permisos = session.get('permisos', {})
        if not permisos.get('admin_data_elastic'):
            return jsonify({'success': False, 'error': 'No tiene permisos para cargar datos'}), 403
        
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No se envió ningún archivo'}), 400
        
        file = request.files['file']
        index = request.form.get('index')
        
        if not file.filename:
            return jsonify({'success': False, 'error': 'Archivo no válido'}), 400
        
        if not index:
            return jsonify({'success': False, 'error': 'Índice no especificado'}), 400
        
        # Guardar archivo ZIP temporalmente
        filename = secure_filename(file.filename)
        carpeta_upload = 'static/uploads'
        Funciones.crear_carpeta(carpeta_upload)
        Funciones.borrar_contenido_carpeta(carpeta_upload)
        
        zip_path = os.path.join(carpeta_upload, filename)
        file.save(zip_path)
        print(f"Archivo ZIP guardado en: {zip_path}")
        
        # Descomprimir ZIP
        archivos = Funciones.descomprimir_zip_local(zip_path, carpeta_upload)
        
        # Eliminar archivo ZIP
        os.remove(zip_path)
        
        # Listar archivos JSON
        archivos_json = Funciones.listar_archivos_json(carpeta_upload)
        
        return jsonify({
            'success': True,
            'archivos': archivos_json,
            'mensaje': f'Se encontraron {len(archivos_json)} archivos JSON'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    
@app.route('/cargar-documentos-elastic', methods=['POST'])
def cargar_documentos_elastic():
    """API para cargar documentos a ElasticSearch"""
    try:
        if not session.get('logged_in'):
            return jsonify({'success': False, 'error': 'No autorizado'}), 401
        
        permisos = session.get('permisos', {})
        if not permisos.get('admin_data_elastic'):
            return jsonify({'success': False, 'error': 'No tiene permisos para cargar datos'}), 403
        
        data = request.get_json()
        archivos = data.get('archivos', [])
        index = data.get('index')
        metodo = data.get('metodo', 'zip')
        
        if not archivos or not index:
            return jsonify({'success': False, 'error': 'Archivos e índice son requeridos'}), 400
        
        documentos = []
        
        if metodo == 'zip':
            # Cargar archivos JSON directamente
            for archivo in archivos:
                ruta = archivo.get('ruta')
                print(f"Procesando archivo JSON: {ruta}")
                if ruta and os.path.exists(ruta):
                    doc = Funciones.leer_json(ruta)
                    print(f"Contenido cargado: {type(doc)}")
                    if doc:
                        # Si el JSON es una lista, extender documentos
                        if isinstance(doc, list):
                            documentos.extend(doc)
                        else:
                            # Si es un solo documento, agregarlo
                            documentos.append(doc)
        
        elif metodo == 'webscraping':
            # Procesar archivos con PLN
            #pln = PLN(cargar_modelos=True)
            
            for archivo in archivos:
                ruta = archivo.get('ruta')
                if not ruta or not os.path.exists(ruta):
                    continue
                
                extension = archivo.get('extension', '').lower()
                
                # Extraer texto según tipo de archivo
                texto = ""
                if extension == 'pdf':
                    # Intentar extracción normal
                    texto = Funciones.extraer_texto_pdf(ruta)
                    
                    # Si no se extrajo texto, intentar con OCR
                    if not texto or len(texto.strip()) < 100:
                        try:
                            texto = Funciones.extraer_texto_pdf_ocr(ruta)
                        except:
                            pass
                
                elif extension == 'txt':
                    try:
                        with open(ruta, 'r', encoding='utf-8') as f:
                            texto = f.read()
                    except:
                        try:
                            with open(ruta, 'r', encoding='latin-1') as f:
                                texto = f.read()
                        except:
                            pass
                
                if not texto or len(texto.strip()) < 50:
                    continue
                
                # Procesar con PLN
                try:
                    #resumen = pln.generar_resumen(texto, num_oraciones=3)
                    #entidades = pln.extraer_entidades(texto)
                    #temas = pln.extraer_temas(texto, top_n=10)

                    resumen = ""            #borrar en produccion
                    entidades = ""          #borrar en produccion
                    temas = ""              #borrar en produccion
                    
                    # Crear documento
                    documento = {
                        'texto': texto,
                        'fecha': datetime.now().isoformat(),
                        'ruta': ruta,
                        'nombre_archivo': archivo.get('nombre', ''),
                        'resumen': resumen,
                        'entidades': entidades,
                        'temas': [{'palabra': palabra, 'relevancia': relevancia} for palabra, relevancia in temas]
                    }
                    
                    documentos.append(documento)
                
                except Exception as e:
                    print(f"Error al procesar {archivo.get('nombre')}: {e}")
                    continue
            
            #pln.close()
        
        if not documentos:
            return jsonify({'success': False, 'error': 'No se pudieron procesar documentos'}), 400
        
        # Indexar documentos en Elastic
        resultado = elastic.indexar_bulk(index, documentos)
        
        return jsonify({
            'success': resultado['success'],
            'indexados': resultado['indexados'],
            'errores': resultado['fallidos']
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/procesar-webscraping-elastic', methods=['POST'])
def procesar_webscraping_elastic():
    """API para procesar Web Scraping"""
    try:
        if not session.get('logged_in'):
            return jsonify({'success': False, 'error': 'No autorizado'}), 401
        
        permisos = session.get('permisos', {})
        if not permisos.get('admin_data_elastic'):
            return jsonify({'success': False, 'error': 'No tiene permisos para cargar datos'}), 403
        
        data = request.get_json()
        url = data.get('url')
        extensiones_navegar = data.get('extensiones_navegar', 'aspx')
        tipos_archivos = data.get('tipos_archivos', 'pdf')
        index = data.get('index')
        
        if not url or not index:
            return jsonify({'success': False, 'error': 'URL e índice son requeridos'}), 400
        
        # Procesar listas de extensiones
        lista_ext_navegar = [ext.strip() for ext in extensiones_navegar.split(',')]
        lista_tipos_archivos = [ext.strip() for ext in tipos_archivos.split(',')]
        
        # Combinar ambas listas para extraer todos los enlaces
        todas_extensiones = lista_ext_navegar + lista_tipos_archivos
        
        # Inicializar WebScraping
        scraper = WebScraping(dominio_base=url.rsplit('/', 1)[0] + '/')
        
        # Limpiar carpeta de uploads
        carpeta_upload = 'static/uploads'
        Funciones.crear_carpeta(carpeta_upload)
        Funciones.borrar_contenido_carpeta(carpeta_upload)
        
        # Extraer todos los enlaces
        json_path = os.path.join(carpeta_upload, 'links.json')
        resultado = scraper.extraer_todos_los_links(
            url_inicial=url,
            json_file_path=json_path,
            listado_extensiones=todas_extensiones,
            max_iteraciones=50
        )
        
        if not resultado['success']:
            return jsonify({'success': False, 'error': 'Error al extraer enlaces'}), 500
        
        # Descargar archivos PDF (o los tipos especificados)
        resultado_descarga = scraper.descargar_pdfs(json_path, carpeta_upload)
        
        scraper.close()
        
        # Listar archivos descargados
        archivos = Funciones.listar_archivos_carpeta(carpeta_upload, lista_tipos_archivos)
        
        return jsonify({
            'success': True,
            'archivos': archivos,
            'mensaje': f'Se descargaron {len(archivos)} archivos',
            'stats': {
                'total_enlaces': resultado['total_links'],
                'descargados': resultado_descarga.get('descargados', 0),
                'errores': resultado_descarga.get('errores', 0)
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
#--------------rutas de elasitcsearch - fin-------------
@app.route('/admin')
def admin():
    """Página de administración (protegida requiere login)"""
    if not session.get('logged_in'):
        flash('Por favor, inicia sesión para acceder al área de administración', 'warning')
        return redirect(url_for('login'))
    
    return render_template('admin.html', usuario=session.get('usuario'), permisos=session.get('permisos'))



# ==================== MAIN ====================
if __name__ == '__main__':
    # Crear carpetas necesarias
    Funciones.crear_carpeta('static/uploads')
    
    # Verificar conexiones
    print("\n" + "="*50)
    print("VERIFICANDO CONEXIONES")

    if mongo.test_connection():
        print("✅ MongoDB Atlas: Conectado")
    else:
        print("❌ MongoDB Atlas: Error de conexión")
    
    if elastic.test_connection():
        print("✅ ElasticSearch Cloud: Conectado")
    else:
        print("❌ ElasticSearch Cloud: Error de conexión")

    # Ejecutar la aplicación (localmente para pruebas)
    app.run(debug=True, host='0.0.0.0', port=5000)

