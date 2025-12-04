import requests
from bs4 import BeautifulSoup
import json
from urllib.parse import urljoin
import os
from typing import List, Dict, Optional
from Helpers import Funciones


class WebScraping:
    """Clase para realizar web scraping y extracción de enlaces"""
    
    def __init__(self, dominio_base: str = "https://www.minsalud.gov.co/Normativa/"):
        """
        Inicializa la clase WebScraping
        
        Args:
            dominio_base: Dominio base para validar enlaces
        """
        self.dominio_base = dominio_base
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def extract_links(self, url: str, listado_extensiones: Optional[List[str]] = None) -> List[Dict]:
        """
        Extrae links internos según listado de extensiones que puede ser "PDF, ASPX, PHP"
        
        Args:
            url: URL de la página a analizar
            listado_extensiones: Lista de extensiones a filtrar (ej: ['pdf', 'aspx', 'php'])
            
        Returns:
            Lista de diccionarios con 'url' y 'type' de cada enlace encontrado
        """
        if listado_extensiones is None:
            listado_extensiones = ['pdf', 'aspx']
        
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()  # Raise an exception for bad status codes
            
            soup = BeautifulSoup(response.content, 'lxml')
            container_div = soup.find('div', class_='containerblanco')
            
            links = []
            if container_div:
                for link in container_div.find_all('a'):
                    href = link.get('href')
                    if href:
                        # Ensure href is a string
                        href_str = str(href) if not isinstance(href, str) else href
                        full_url = urljoin(url, href_str)
                        
                        # Check if the link is within the specified domain
                        if full_url.startswith(self.dominio_base):
                            # Verificar extensión
                            for ext in listado_extensiones:
                                ext_lower = ext.lower().strip()
                                if full_url.lower().endswith(f'.{ext_lower}'):
                                    links.append({
                                        'url': full_url,
                                        'type': ext_lower
                                    })
                                    break  # Solo agregar una vez
            
            return links
            
        except requests.exceptions.RequestException as e:
            print(f"Error fetching {url}: {e}")
            return []
        except Exception as e:
            print(f"Error procesando {url}: {e}")
            return []
    
    def extraer_todos_los_links(self, url_inicial: str, json_file_path: str, 
                                 listado_extensiones: Optional[List[str]] = None,
                                 max_iteraciones: int = 100) -> Dict:
        """
        Extrae todos los links de forma recursiva desde una URL inicial
        
        Args:
            url_inicial: URL inicial para comenzar la extracción
            json_file_path: Ruta del archivo JSON para guardar/cargar links
            listado_extensiones: Lista de extensiones a filtrar
            max_iteraciones: Número máximo de iteraciones para evitar loops infinitos
            
        Returns:
            Diccionario con el resultado de la extracción
        """
        if listado_extensiones is None:
            listado_extensiones = ['pdf', 'aspx']
        
        # Cargar links existentes del archivo JSON
        all_links = self._cargar_links_desde_json(json_file_path)
        
        # Si no hay links, extraer de la URL inicial
        if not all_links:
            print(f"Extrayendo links de la URL inicial: {url_inicial}")
            all_links = self.extract_links(url_inicial, listado_extensiones)
        
        # Filtrar links para que solo estén en el dominio especificado
        all_links = [link for link in all_links if link['url'].startswith(self.dominio_base)]
        
        # Obtener links ASPX para visitar
        aspx_links_to_visit = [
            link['url'] for link in all_links 
            if link['type'] == 'aspx' and link['url'].startswith(self.dominio_base)
        ]
        
        visited_aspx_links = set()
        iteraciones = 0
        
        # Recorrer links ASPX
        while aspx_links_to_visit and iteraciones < max_iteraciones:
            iteraciones += 1
            current_aspx_url = aspx_links_to_visit.pop(0)
            
            if current_aspx_url not in visited_aspx_links:
                visited_aspx_links.add(current_aspx_url)
                print(f"Iteración {iteraciones}: Visitando: {current_aspx_url}")
                
                new_links = self.extract_links(current_aspx_url, listado_extensiones)
                
                for link in new_links:
                    # Verificar si el link no está ya en la lista
                    if not any(existing_link['url'] == link['url'] for existing_link in all_links):
                        all_links.append(link)
                        
                        # Si es ASPX, agregarlo a la cola de visitas
                        if link['type'] == 'aspx' and link['url'] not in visited_aspx_links:
                            aspx_links_to_visit.append(link['url'])
        
        if iteraciones >= max_iteraciones:
            print(f"Advertencia: Se alcanzó el máximo de {max_iteraciones} iteraciones")
        
        # Filtrar nuevamente para asegurar que todos están en el dominio
        all_links = [link for link in all_links if link['url'].startswith(self.dominio_base)]
        
        # Guardar en JSON
        json_output = {"links": all_links}
        self._guardar_links_en_json(json_file_path, json_output)
        
        print(f"Finalizado: Se encontraron {len(all_links)} links en total")
        
        return {
            'success': True,
            'total_links': len(all_links),
            'links': all_links,
            'iteraciones': iteraciones
        }
    
    def _cargar_links_desde_json(self, json_file_path: str) -> List[Dict]:
        """Carga links desde un archivo JSON"""
        if os.path.exists(json_file_path):
            try:
                with open(json_file_path, 'r', encoding='utf-8') as f:
                    json_data = json.load(f)
                all_links = json_data.get("links", [])
                print(f"Cargados {len(all_links)} links desde {json_file_path}")
                return all_links
            except json.JSONDecodeError:
                print(f"Advertencia: {json_file_path} contiene JSON inválido. Inicializando con lista vacía.")
                return []
        else:
            print(f"{json_file_path} no encontrado. Se creará un nuevo archivo.")
            return []
    
    def _guardar_links_en_json(self, json_file_path: str, data: Dict):
        """Guarda links en un archivo JSON"""
        try:
            # Crear directorio si no existe
            os.makedirs(os.path.dirname(json_file_path), exist_ok=True) if os.path.dirname(json_file_path) else None
            
            with open(json_file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            print(f"Links guardados en {json_file_path}")
        except Exception as e:
            print(f"Error al guardar JSON: {e}")
    
    def descargar_pdfs(self, json_file_path: str, carpeta_destino: str = "static/uploads") -> Dict:
        """
        Recorre el archivo JSON y descarga los archivos PDF en la carpeta especificada
        
        Args:
            json_file_path: Ruta del archivo JSON con los links
            carpeta_destino: Carpeta donde se descargarán los PDFs (default: static/uploads)
            
        Returns:
            Diccionario con el resultado de la descarga
        """
        try:
            # Cargar links desde JSON
            all_links = self._cargar_links_desde_json(json_file_path)
            
            # Filtrar solo links PDF
            pdf_links = [link for link in all_links if link.get('type') == 'pdf']
            
            if not pdf_links:
                return {
                    'success': True,
                    'mensaje': 'No hay archivos PDF para descargar',
                    'descargados': 0,
                    'errores': 0
                }
            
            # Crear carpeta de destino si no existe
            Funciones.crear_carpeta(carpeta_destino)
            
            # Borrar contenido de la carpeta antes de descargar
            print(f"Limpiando contenido de la carpeta: {carpeta_destino}")
            Funciones.borrar_contenido_carpeta(carpeta_destino)
            
            # Descargar PDFs
            descargados = 0
            errores = 0
            archivos_errores = []
            
            print(f"Iniciando descarga de {len(pdf_links)} archivos PDF...")
            
            for i, link in enumerate(pdf_links, 1):
                pdf_url = link['url']
                try:
                    # Obtener nombre del archivo desde la URL
                    nombre_archivo = os.path.basename(pdf_url.split('?')[0])  # Remover query params
                    
                    # Si no tiene extensión .pdf, agregarla
                    if not nombre_archivo.lower().endswith('.pdf'):
                        nombre_archivo += '.pdf'
                    
                    # Limpiar nombre de archivo (remover caracteres especiales)
                    from werkzeug.utils import secure_filename
                    nombre_archivo = secure_filename(nombre_archivo)
                    
                    # Si el nombre está vacío, generar uno
                    if not nombre_archivo or nombre_archivo == '.pdf':
                        nombre_archivo = f"archivo_{i}.pdf"
                    
                    ruta_archivo = os.path.join(carpeta_destino, nombre_archivo)
                    
                    # Descargar archivo
                    print(f"Descargando [{i}/{len(pdf_links)}]: {nombre_archivo}")
                    response = self.session.get(pdf_url, stream=True, timeout=60)
                    response.raise_for_status()
                    
                    # Guardar archivo
                    with open(ruta_archivo, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    
                    descargados += 1
                    
                except Exception as e:
                    errores += 1
                    archivos_errores.append({
                        'url': pdf_url,
                        'error': str(e)
                    })
                    print(f"Error al descargar {pdf_url}: {e}")
            
            resultado = {
                'success': True,
                'total': len(pdf_links),
                'descargados': descargados,
                'errores': errores,
                'carpeta_destino': carpeta_destino
            }
            
            if archivos_errores:
                resultado['archivos_con_error'] = archivos_errores
            
            print(f"\nDescarga completada:")
            print(f"  Total: {len(pdf_links)}")
            print(f"  Descargados: {descargados}")
            print(f"  Errores: {errores}")
            
            return resultado
            
        except Exception as e:
            print(f"Error en descargar_pdfs: {e}")
            return {
                'success': False,
                'error': str(e),
                'descargados': 0,
                'errores': 0
            }
    
    def close(self):
        """Cierra la sesión de requests"""
        self.session.close()

