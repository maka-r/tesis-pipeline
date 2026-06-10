import os
import sys
from pathlib import Path

# Extensiones de texto comunes que Claude puede procesar bien
TEXT_EXTENSIONS = {
    '.py', '.js', '.jsx', '.ts', '.tsx', '.html', '.css', '.json', '.md', 
    '.txt', '.sh', '.yaml', '.yml', '.ini', '.cfg', '.sql', '.go', '.rs',
    '.java', '.c', '.cpp', '.h', '.hpp', '.cs', '.php', '.rb', '.kt'
}

# Directorios y archivos a ignorar por defecto
IGNORE_DIRS = {
    'node_modules', '.git', '.venv', 'venv', 'env', '__pycache__', 
    'dist', 'build', '.next', '.nuxt', 'out', '.idea', '.vscode'
}

IGNORE_FILES = {
    'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', '.DS_Store', 
    'Thumbs.db', 'project_context_claude.txt'
}

def clean_text(content):
    """Remueve caracteres nulos o problemáticos si los hay."""
    return content.replace('\x00', '')

def build_context(root_dir, output_file):
    root_path = Path(root_dir).resolve()
    print(f"[*] Escaneando el directorio: {root_path}")
    print(f"[*] Los archivos se consolidarán en: {output_file}\n")
    
    with open(output_file, 'w', encoding='utf-8') as out:
        out.write(f"===================================================\n")
        out.write(f"CONTEXTO CONSOLIDADO DEL PROYECTO\n")
        out.write(f"Raíz del proyecto: {root_path.name}\n")
        out.write(f"===================================================\n\n")
        
        # Primero, generar un pequeño árbol de archivos para que Claude entienda la estructura
        out.write("### ESTRUCTURA DEL PROYECTO ###\n")
        file_count = 0
        
        for root, dirs, files in os.walk(root_path):
            # Filtrar directorios in situ para evitar que os.walk entre en ellos
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith('.')]
            
            for file in files:
                if file in IGNORE_FILES or file.startswith('.'):
                    continue
                ext = Path(file).suffix.lower()
                if ext in TEXT_EXTENSIONS or file.endswith('rc') or file == 'Dockerfile':
                    rel_path = Path(root).relative_to(root_path) / file
                    out.write(f"- {rel_path}\n")
                    file_count += 1
                    
        out.write(f"Total de archivos indexados: {file_count}\n\n")
        out.write("===================================================\n\n")
        
        # Ahora, leer e inyectar el contenido de cada archivo
        for root, dirs, files in os.walk(root_path):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith('.')]
            
            for file in files:
                if file in IGNORE_FILES or file.startswith('.'):
                    continue
                    
                ext = Path(file).suffix.lower()
                # Procesar solo archivos de texto legibles
                if ext in TEXT_EXTENSIONS or file.endswith('rc') or file == 'Dockerfile':
                    file_path = Path(root) / file
                    rel_path = file_path.relative_to(root_path)
                    
                    print(f"[+] Incluyendo: {rel_path}")
                    
                    out.write(f"--- INICIO ARCHIVO: {rel_path} ---\n")
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                            content = f.read()
                            out.write(clean_text(content))
                    except Exception as e:
                        out.write(f"[ERROR AL LEER ARCHIVO: {str(e)}]")
                    
                    out.write(f"\n--- FIN ARCHIVO: {rel_path} ---\n\n")

    print(f"\n[¡ÉXITO!] Todo tu entorno ha sido consolidado en '{output_file}'.")
    print("Sube este archivo directamente a la sección 'Project Knowledge' de Claude.")

if __name__ == '__main__':
    # Permitir pasar la ruta como argumento, sino usa el directorio actual
    target_directory = sys.argv[1] if len(sys.argv) > 1 else "."
    output_filename = "project_context_claude.txt"
    build_context(target_directory, output_filename)
