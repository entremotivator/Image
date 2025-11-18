import streamlit as st
import requests
import json
import time
import io
import numpy as np
from datetime import datetime
from typing import Optional, Dict, List
import base64

# -----------------------------
# PIL (Safe Import)
# -----------------------------
try:
    from PIL import Image as PILImage
except Exception:
    PILImage = None
    st.error("Pillow is missing. Add 'Pillow' to requirements.txt")

# -----------------------------
# Google Drive (Safe Import)
# -----------------------------
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
except Exception:
    service_account = None
    build = None
    MediaIoBaseUpload = None
    st.error("Google API packages missing. Add these to requirements.txt: "
             "google-auth, google-auth-oauthlib, google-auth-httplib2, google-api-python-client")

# ============================================================================
# Streamlit Configuration
# ============================================================================

st.set_page_config(
    page_title="AI Image Generator",
    page_icon="🎨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        padding: 0 20px;
    }
    .image-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
        gap: 20px;
        margin: 20px 0;
    }
    .image-card {
        border: 1px solid #e0e0e0;
        border-radius: 12px;
        padding: 12px;
        background: white;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        transition: transform 0.2s, box-shadow 0.2s;
    }
    .image-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 4px 16px rgba(0,0,0,0.12);
    }
    .image-card img {
        border-radius: 8px;
        width: 100%;
    }
    .status-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 600;
    }
    .status-success {
        background-color: #d4edda;
        color: #155724;
    }
    .status-waiting {
        background-color: #fff3cd;
        color: #856404;
    }
    .status-fail {
        background-color: #f8d7da;
        color: #721c24;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# Configuration
# ============================================================================

BASE_URL = "https://api.kie.ai/api/v1/jobs"
SCOPES = ['https://www.googleapis.com/auth/drive.file']

# ============================================================================
# Session State Initialization
# ============================================================================

def init_session_state():
    """Initialize all session state variables."""
    defaults = {
        'api_key': "",
        'task_history': [],
        'current_task': None,
        'authenticated': False,
        'service': None,
        'credentials': None,
        'library_images': [],
        'gdrive_folder_id': None,
        'auto_upload': True,
        'service_account_info': None,
        'stats': {
            'total_tasks': 0,
            'successful_tasks': 0,
            'failed_tasks': 0,
            'uploaded_images': 0
        },
        'current_page': "Generate"
    }
    
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_session_state()

# ============================================================================
# Google Drive Functions
# ============================================================================

def authenticate_with_service_account(service_account_json):
    """Authenticate with Google Drive using service account."""
    try:
        credentials = service_account.Credentials.from_service_account_info(
            service_account_json,
            scopes=SCOPES
        )
        service = build('drive', 'v3', credentials=credentials)
        st.session_state.credentials = credentials
        st.session_state.service = service
        st.session_state.authenticated = True
        return True, "Successfully authenticated with Google Drive"
    except Exception as e:
        return False, f"Authentication failed: {str(e)}"

def create_app_folder():
    """Create or get the app's folder in Google Drive."""
    if not st.session_state.service:
        return None
    
    try:
        # Search for existing folder
        results = st.session_state.service.files().list(
            q="name='AI_Image_Generator' and mimeType='application/vnd.google-apps.folder' and trashed=false",
            spaces='drive',
            fields='files(id, name)',
            pageSize=1
        ).execute()
        
        files = results.get('files', [])
        if files:
            st.session_state.gdrive_folder_id = files[0]['id']
            return files[0]['id']
        
        # Create new folder
        file_metadata = {
            'name': 'AI_Image_Generator',
            'mimeType': 'application/vnd.google-apps.folder'
        }
        folder = st.session_state.service.files().create(
            body=file_metadata,
            fields='id'
        ).execute()
        
        folder_id = folder.get('id')
        st.session_state.gdrive_folder_id = folder_id
        return folder_id
    except Exception as e:
        st.error(f"Error creating folder: {str(e)}")
        return None

def upload_to_gdrive(image_url: str, file_name: str, task_id: str = None):
    """Download image from URL and upload to Google Drive with public access."""
    if not st.session_state.service:
        return None
    
    try:
        folder_id = st.session_state.gdrive_folder_id or create_app_folder()
        if not folder_id:
            return None
        
        # Download image from URL
        response = requests.get(image_url, timeout=30)
        response.raise_for_status()
        image_data = response.content
        
        # Create file metadata
        file_metadata = {
            'name': file_name,
            'parents': [folder_id]
        }
        
        # Upload to Google Drive
        media = MediaIoBaseUpload(
            io.BytesIO(image_data),
            mimetype='image/png',
            resumable=True
        )
        
        file = st.session_state.service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name, webViewLink'
        ).execute()
        
        file_id = file.get('id')
        
        permission = {
            'type': 'anyone',
            'role': 'reader'
        }
        st.session_state.service.permissions().create(
            fileId=file_id,
            body=permission,
            fields='id'
        ).execute()
        
        public_url = f"https://drive.google.com/uc?export=view&id={file_id}"
        
        # Update stats
        st.session_state.stats['uploaded_images'] += 1
        
        return {
            'file_id': file_id,
            'file_name': file.get('name'),
            'web_link': file.get('webViewLink'),
            'public_url': public_url,
            'uploaded_at': datetime.now().isoformat(),
            'task_id': task_id,
            'original_url': image_url
        }
    except Exception as e:
        st.error(f"Error uploading to Google Drive: {str(e)}")
        return None

def list_gdrive_images(folder_id: Optional[str] = None):
    """List all images in Google Drive folder."""
    if not st.session_state.service:
        return []
    
    try:
        if not folder_id:
            folder_id = st.session_state.gdrive_folder_id or create_app_folder()
        
        results = st.session_state.service.files().list(
            q=f"'{folder_id}' in parents and trashed=false and (mimeType='image/png' or mimeType='image/jpeg' or mimeType='image/webp')",
            spaces='drive',
            fields='files(id, name, webViewLink, createdTime)',
            pageSize=100,
            orderBy='createdTime desc'
        ).execute()
        
        files = results.get('files', [])
        for file in files:
            file['public_url'] = f"https://drive.google.com/uc?export=view&id={file['id']}"
        
        return files
    except Exception as e:
        st.error(f"Error listing images: {str(e)}")
        return []

def delete_gdrive_file(file_id: str):
    """Delete a file from Google Drive."""
    if not st.session_state.service:
        return False
    
    try:
        st.session_state.service.files().delete(fileId=file_id).execute()
        return True
    except Exception as e:
        st.error(f"Error deleting file: {str(e)}")
        return False

# ============================================================================
# API Functions
# ============================================================================

def create_task(api_key, model, input_params, callback_url=None):
    """Create a generation task."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "input": input_params
    }
    
    if callback_url:
        payload["callBackUrl"] = callback_url
    
    try:
        response = requests.post(
            f"{BASE_URL}/createTask",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        data = response.json()
        if response.status_code == 200:
            if data.get("code") == 200:
                st.session_state.stats['total_tasks'] += 1
                return {"success": True, "task_id": data["data"]["taskId"]}
            else:
                return {"success": False, "error": data.get('msg', 'Unknown error')}
        else:
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def check_task_status(api_key, task_id):
    """Check task status."""
    headers = {
        "Authorization": f"Bearer {api_key}",
    }
    
    try:
        response = requests.get(
            f"{BASE_URL}/recordInfo",
            headers=headers,
            params={"taskId": task_id},
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 200:
                return {"success": True, "data": data["data"]}
            else:
                return {"success": False, "error": data.get('msg', 'Unknown error')}
        else:
            return {"success": False, "error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def poll_task_until_complete(api_key, task_id, max_attempts=60, delay=2):
    """Poll task status until completion or timeout."""
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for attempt in range(max_attempts):
        result = check_task_status(api_key, task_id)
        
        if result["success"]:
            task_data = result["data"]
            state = task_data["state"]
            
            progress = min((attempt + 1) / max_attempts, 0.95)
            progress_bar.progress(progress)
            status_text.text(f"Status: {state} | Attempt {attempt + 1}/{max_attempts}")
            
            if state == "success":
                progress_bar.progress(1.0)
                status_text.text("✅ Task completed successfully!")
                return {"success": True, "data": task_data}
            elif state == "fail":
                progress_bar.empty()
                status_text.text("❌ Task failed")
                return {"success": False, "error": task_data.get('failMsg', 'Unknown error'), "data": task_data}
            
            time.sleep(delay)
        else:
            status_text.text(f"⚠️ Error checking status: {result['error']}")
            time.sleep(delay)
    
    progress_bar.empty()
    status_text.text("⏱️ Timeout reached")
    return {"success": False, "error": "Timeout reached"}

def save_and_upload_results(task_id, model, prompt, result_urls):
    """Save results to history and auto-upload to Google Drive if enabled."""
    for i, task in enumerate(st.session_state.task_history):
        if task['id'] == task_id:
            st.session_state.task_history[i]['status'] = 'success'
            st.session_state.task_history[i]['results'] = result_urls
            st.session_state.stats['successful_tasks'] += 1
            
            # Auto-upload to Google Drive if enabled
            if st.session_state.authenticated and st.session_state.auto_upload:
                for j, result_url in enumerate(result_urls):
                    file_name = f"{model.replace('/', '_')}_{task_id}_{j+1}.png"
                    upload_info = upload_to_gdrive(result_url, file_name, task_id)
                    if upload_info:
                        st.session_state.library_images.insert(0, upload_info)
            break

# ============================================================================
# Sidebar
# ============================================================================

def load_persisted_service_account():
    if st.session_state.service_account_info and not st.session_state.authenticated:
        try:
            service_account_json = json.loads(st.session_state.service_account_info)
            authenticate_with_service_account(service_account_json)
        except Exception:
            st.session_state.service_account_info = None
            st.session_state.authenticated = False

load_persisted_service_account()

with st.sidebar:
    st.markdown("# 🎨 AI Image Generator")
    st.markdown("---")
    
    # API Configuration
    st.header("⚙️ API Configuration")
    api_key = st.text_input(
        "API Key",
        type="password",
        value=st.session_state.api_key,
        help="Enter your KIE.AI API key"
    )
    
    if api_key != st.session_state.api_key:
        st.session_state.api_key = api_key
    
    if st.session_state.api_key:
        st.success("✅ API Key configured")
    else:
        st.warning("⚠️ Please enter API key")
    
    st.markdown("---")
    
    # Google Drive Setup
    st.header("☁️ Google Drive")
    
    if not st.session_state.authenticated:
        uploaded_file = st.file_uploader(
            "Service Account JSON",
            type=['json'],
            help="Upload Google service account credentials"
        )
        
        if uploaded_file is not None:
            try:
                service_account_json = json.loads(uploaded_file.getvalue().decode("utf-8"))
                success, message = authenticate_with_service_account(service_account_json)
                
                if success:
                    st.session_state.service_account_info = uploaded_file.getvalue().decode("utf-8")
                    st.success(message)
                    create_app_folder()
                    st.rerun()
                else:
                    st.error(message)
            except Exception as e:
                st.error(f"Error: {str(e)}")
    else:
        st.success("✅ Google Drive Connected")
        
        st.checkbox(
            "Auto Upload",
            value=st.session_state.auto_upload,
            key="auto_upload_checkbox",
            on_change=lambda: setattr(st.session_state, 'auto_upload', st.session_state.auto_upload_checkbox)
        )
        
        if st.button("🔄 Refresh Library", use_container_width=True):
            st.session_state.library_images = list_gdrive_images()
            st.success("Refreshed!")
        
        if st.button("🗑️ Disconnect", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.service = None
            st.session_state.service_account_info = None
            st.rerun()
    
    st.markdown("---")
    
    # Statistics
    st.header("📊 Statistics")
    col1, col2 = st.columns(2)
    col1.metric("Total Tasks", st.session_state.stats['total_tasks'])
    col2.metric("Successful", st.session_state.stats['successful_tasks'])
    col1.metric("Failed", st.session_state.stats['failed_tasks'])
    col2.metric("Uploaded", st.session_state.stats['uploaded_images'])

# ============================================================================
# Main Pages
# ============================================================================

def display_generate_page():
    st.title("✨ Generate Images")
    
    if not st.session_state.api_key:
        st.error("Please configure your API Key in the sidebar.")
        return

    tab1, tab2, tab3 = st.tabs(["Text-to-Image", "Qwen Image Edit", "Seedream V4 Edit"])

    with tab1:
        with st.form("text_to_image_form"):
            prompt = st.text_area("Prompt", "A photorealistic majestic lion wearing a crown, digital art")
            negative_prompt = st.text_area("Negative Prompt", "blurry, low quality")
            
            col1, col2, col3 = st.columns(3)
            model = col1.selectbox("Model", ["stable-diffusion-xl", "dall-e-3"], key="t2i_model")
            width = col2.slider("Width", 512, 1024, 1024, 64, key="t2i_width")
            height = col3.slider("Height", 512, 1024, 1024, 64, key="t2i_height")
            
            num_images = st.slider("Images", 1, 4, 1, key="t2i_num")
            
            if st.form_submit_button("Generate"):
                input_params = {
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "width": width,
                    "height": height,
                    "num_images": num_images
                }
                
                result = create_task(st.session_state.api_key, model, input_params)
                
                if result["success"]:
                    task_id = result["task_id"]
                    st.session_state.task_history.insert(0, {
                        "id": task_id,
                        "model": model,
                        "prompt": prompt,
                        "status": "waiting",
                        "created_at": datetime.now().isoformat(),
                        "results": []
                    })
                    st.session_state.current_task = task_id
                    st.rerun()
                else:
                    st.error(f"Failed: {result['error']}")

    with tab2:
        with st.form("qwen_form"):
            prompt = st.text_area("Edit Prompt", "Make vibrant and colorful", key="qwen_prompt")
            image_url = st.text_input("Image URL", key="qwen_url")
            
            col1, col2 = st.columns(2)
            image_size = col1.selectbox("Size", ["square_hd", "portrait_4_3", "landscape_16_9"], key="qwen_size")
            num_steps = col2.slider("Steps", 2, 49, 25, key="qwen_steps")
            
            if st.form_submit_button("Edit Image"):
                input_params = {
                    "prompt": prompt,
                    "image_url": image_url,
                    "image_size": image_size,
                    "num_inference_steps": num_steps
                }
                
                result = create_task(st.session_state.api_key, "qwen/image-edit", input_params)
                
                if result["success"]:
                    task_id = result["task_id"]
                    st.session_state.task_history.insert(0, {
                        "id": task_id,
                        "model": "qwen/image-edit",
                        "prompt": prompt,
                        "status": "waiting",
                        "created_at": datetime.now().isoformat(),
                        "results": []
                    })
                    st.session_state.current_task = task_id
                    st.rerun()
                else:
                    st.error(f"Failed: {result['error']}")

    with tab3:
        with st.form("seedream_form"):
            prompt = st.text_area("Edit Prompt", "Create a tshirt mockup", key="seedream_prompt")
            image_url = st.text_input("Image URL", key="seedream_url")
            
            col1, col2 = st.columns(2)
            image_size = col1.selectbox("Size", ["square_hd", "landscape_16_9"], key="seedream_size")
            resolution = col2.selectbox("Resolution", ["1K", "2K", "4K"], key="seedream_res")
            
            if st.form_submit_button("Edit Image"):
                input_params = {
                    "prompt": prompt,
                    "image_urls": [image_url],
                    "image_size": image_size,
                    "image_resolution": resolution
                }
                
                result = create_task(st.session_state.api_key, "bytedance/seedream-v4-edit", input_params)
                
                if result["success"]:
                    task_id = result["task_id"]
                    st.session_state.task_history.insert(0, {
                        "id": task_id,
                        "model": "bytedance/seedream-v4-edit",
                        "prompt": prompt,
                        "status": "waiting",
                        "created_at": datetime.now().isoformat(),
                        "results": []
                    })
                    st.session_state.current_task = task_id
                    st.rerun()
                else:
                    st.error(f"Failed: {result['error']}")

    # Auto-poll current task
    if st.session_state.current_task:
        for task in st.session_state.task_history:
            if task['id'] == st.session_state.current_task and task['status'] == 'waiting':
                st.info(f"Processing task {task['id']}...")
                result = poll_task_until_complete(st.session_state.api_key, task['id'])
                
                if result["success"]:
                    try:
                        result_json = json.loads(result['data'].get('resultJson', '{}'))
                        result_urls = result_json.get('resultUrls', [])
                        save_and_upload_results(task['id'], task['model'], task['prompt'], result_urls)
                        st.success("Task completed!")
                    except:
                        task['status'] = 'fail'
                        st.session_state.stats['failed_tasks'] += 1
                else:
                    task['status'] = 'fail'
                    st.session_state.stats['failed_tasks'] += 1
                
                st.session_state.current_task = None
                st.rerun()

def display_library_page():
    st.title("📚 Image Library")
    
    if st.button("⬅️ Back to Generate", use_container_width=False):
        st.session_state.current_page = "Generate"
        st.rerun()
    
    st.markdown("---")
    
    if not st.session_state.authenticated:
        st.error("Please connect Google Drive in the sidebar.")
        return
    
    if not st.session_state.library_images:
        st.session_state.library_images = list_gdrive_images()
    
    if not st.session_state.library_images:
        st.info("No images in library yet.")
        return
    
    st.markdown(f"**{len(st.session_state.library_images)}** images in library")
    
    cols_per_row = 3
    for i, img in enumerate(st.session_state.library_images):
        if i % cols_per_row == 0:
            cols = st.columns(cols_per_row)
        
        with cols[i % cols_per_row]:
            # Display actual image using public URL
            if 'public_url' in img:
                st.image(img['public_url'], use_container_width=True)
            
            file_name = img.get('name', img.get('file_name', 'Unknown'))
            st.caption(file_name)
            
            col1, col2 = st.columns(2)
            
            with col1:
                # Link to open in Google Drive
                web_link = img.get('web_link', img.get('webViewLink', '#'))
                st.markdown(f"[Open in Drive]({web_link})")
            
            with col2:
                # Delete button
                file_id = img.get('id', img.get('file_id'))
                if st.button("🗑️", key=f"del_{file_id}", help="Delete"):
                    if delete_gdrive_file(file_id):
                        st.session_state.library_images = [
                            x for x in st.session_state.library_images 
                            if x.get('id', x.get('file_id')) != file_id
                        ]
                        st.rerun()

# ============================================================================
# Navigation
# ============================================================================

# Main navigation tabs
main_tab1, main_tab2 = st.tabs(["🎨 Generate", "📚 Library"])

with main_tab1:
    display_generate_page()

with main_tab2:
    display_library_page()
