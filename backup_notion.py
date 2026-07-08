#!/usr/bin/env python3
"""
Notion Backup Script - Exporte les fiches Notion vers Google Drive
Sauvegarde les fiches de JUILLET à OCTOBRE + futurs mois en Markdown + JSON
"""

import os
import json
from datetime import datetime
from notion_client import Client
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from google.api_python_client import discovery
import io

# Configuration
NOTION_TOKEN = os.getenv('NOTION_TOKEN')
GOOGLE_DRIVE_FOLDER_ID = os.getenv('GOOGLE_DRIVE_FOLDER_ID')
GOOGLE_SERVICE_ACCOUNT = os.getenv('GOOGLE_SERVICE_ACCOUNT')

# IDs des pages à sauvegarder (JUILLET à OCTOBRE 2026 + futurs)
PAGES_TO_BACKUP = {
    'JUILLET': [
        '31e8fc81ebf4804d94b4c7f7a6de5069',  # DUOTONE FOIL ASSIST
        '3818fc81ebf4801bb5a0d17641dbc451',  # HOVERAir AQUA DRONE
        '3868fc81ebf4812d895edc1a193f25e1',  # PARAWING ALTIS FOCUS
        '2cd8fc81ebf480e69cbce0255f62900f',  # FOIL GAASTRA MOVE
        '3378fc81ebf480eca045c04a8bbbc912',  # FLITELAB AMP+RAW+FLUX
    ],
    'AOUT': [
        '3578fc81ebf4802cbb23fdf3b412d429',  # ARMSTRONG MIDLENGTH MKII 55L
        '2fb8fc81ebf480409f43eb36bc45dd78',  # FOIL SILK V2 RANGE + TAIL
        '3578fc81ebf48028a5d7fdd20712a7e5',  # ARMSTRONG - WING PERFORMANCE 4.0
        '3378fc81ebf480adbafbeca50f7386f5',  # FOIL TAKOON FLASH
    ],
    'SEPTEMBRE': [
        '3918fc81ebf48182ad25e68bf1740157',  # PARAWING FLYSURFER POW V2
        '3918fc81ebf4812386b4c052ff7511d9',  # PARAWING PPC ORBIT
        '3868fc81ebf481108208fee2f91a6f07',  # TAKOON PUMPSCOOT (EN)
        '2fb8fc81ebf480a4a972f307bec14dee',  # FOIL KPART AROS
        '3868fc81ebf4817db4c8d9c0bbbfd779',  # CABRINHA FOIL RANGE
        '3868fc81ebf481f99069c988c86f21a8',  # KETOS FOIL RANGE (KOBUN)
    ],
    'OCTOBRE': [
        '3918fc81ebf481bcb6a3fd66f6391b2b',  # KT Nouveautés 2026 Mat/foil/boards
    ]
}

def init_notion_client():
    """Initialise le client Notion"""
    return Client(auth=NOTION_TOKEN)

def init_google_drive():
    """Initialise le client Google Drive avec credentials"""
    if GOOGLE_SERVICE_ACCOUNT:
        # Utilise Service Account JSON (recommandé pour GitHub Actions)
        creds_dict = json.loads(GOOGLE_SERVICE_ACCOUNT)
        creds = Credentials.from_service_account_info(
            creds_dict,
            scopes=['https://www.googleapis.com/auth/drive']
        )
    else:
        # Fallback : utilise OAuth2 (local development)
        flow = InstalledAppFlow.from_client_secrets_file(
            'credentials.json',
            scopes=['https://www.googleapis.com/auth/drive']
        )
        creds = flow.run_local_server(port=0)
    
    return discovery.build('drive', 'v3', credentials=creds)

def notion_page_to_markdown(page_data):
    """Convertit une page Notion en Markdown"""
    markdown = f"# {page_data.get('title', 'Untitled')}\n\n"
    markdown += f"**Date de backup :** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    
    # Récupère le contenu brut (Notion retourne du markdown enrichi)
    if 'content' in page_data:
        markdown += page_data['content']
    
    return markdown

def fetch_page_content(notion, page_id):
    """Récupère le contenu complet d'une page Notion"""
    try:
        page = notion.pages.retrieve(page_id)
        blocks = notion.blocks.children.list(page_id)
        
        page_data = {
            'id': page_id,
            'title': page.get('properties', {}).get('title', [{}])[0].get('plain_text', 'Untitled'),
            'created': page['created_time'],
            'last_edited': page['last_edited_time'],
            'url': page['public_url'] if page.get('public_url') else f"https://notion.so/{page_id}",
        }
        
        return page_data
    except Exception as e:
        print(f"Erreur lors de la récupération de la page {page_id}: {e}")
        return None

def upload_to_google_drive(drive_service, file_name, file_content, folder_id, mime_type='text/plain'):
    """Upload un fichier vers Google Drive"""
    try:
        file_metadata = {
            'name': file_name,
            'parents': [folder_id],
            'mimeType': mime_type
        }
        
        media = discovery.http.MediaIoBaseUpload(
            io.BytesIO(file_content.encode('utf-8')),
            mimetype=mime_type
        )
        
        file_obj = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        
        print(f"✅ Uploadé: {file_name}")
        return file_obj.get('id')
    except Exception as e:
        print(f"❌ Erreur upload {file_name}: {e}")
        return None

def create_folder_structure(drive_service, parent_folder_id, folder_name):
    """Crée un dossier dans Google Drive s'il n'existe pas"""
    try:
        # Cherche si le dossier existe déjà
        query = f"name='{folder_name}' and parents='{parent_folder_id}' and trashed=false"
        results = drive_service.files().list(q=query, spaces='drive', fields='files(id)').execute()
        
        if results.get('files'):
            return results['files'][0]['id']
        
        # Crée le dossier
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_folder_id]
        }
        
        folder = drive_service.files().create(body=file_metadata, fields='id').execute()
        print(f"📁 Dossier créé: {folder_name}")
        return folder.get('id')
    except Exception as e:
        print(f"Erreur création dossier {folder_name}: {e}")
        return None

def main():
    print(f"\n🚀 Démarrage du backup Notion — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # Initialise les clients
    notion = init_notion_client()
    drive = init_google_drive()
    
    # Crée dossier "Backups Notion" avec date du jour
    today = datetime.now().strftime('%Y-%m-%d')
    backup_folder_name = f"Backup_{today}"
    backup_folder_id = create_folder_structure(drive, GOOGLE_DRIVE_FOLDER_ID, backup_folder_name)
    
    if not backup_folder_id:
        print("❌ Impossible de créer le dossier de backup")
        return
    
    # Traite chaque mois et ses fiches
    total_files = 0
    for month, page_ids in PAGES_TO_BACKUP.items():
        print(f"\n📅 Traitement du mois : {month}")
        
        # Crée un dossier par mois
        month_folder_id = create_folder_structure(drive, backup_folder_id, month)
        
        for page_id in page_ids:
            print(f"  📄 Récupération page {page_id}...")
            
            page_data = fetch_page_content(notion, page_id)
            if not page_data:
                continue
            
            page_title = page_data['title'].replace('/', '-').replace('\\', '-')
            
            # Export en JSON
            json_filename = f"{page_title}_{today}.json"
            json_content = json.dumps(page_data, indent=2, ensure_ascii=False)
            upload_to_google_drive(drive, json_filename, json_content, month_folder_id, 'application/json')
            
            # Export en Markdown
            markdown_content = notion_page_to_markdown(page_data)
            md_filename = f"{page_title}_{today}.md"
            upload_to_google_drive(drive, md_filename, markdown_content, month_folder_id, 'text/markdown')
            
            total_files += 2
    
    print(f"\n✅ Backup terminé ! {total_files} fichiers sauvegardés")
    print(f"📁 Dossier Google Drive : {backup_folder_name}\n")

if __name__ == '__main__':
    main()
