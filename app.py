import streamlit as st
import requests
import json
import time
import io
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
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
# Streamlit Cloud Configuration
# ============================================================================

st.set_page_config(
    page_title="AI Image Editor Pro",
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
        padding-left: 20px;
        padding-right: 20px;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 12px;
        margin: 10px 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .success-box {
        background-color: #d4edda;
        padding: 15px;
        border-radius: 8px;
        border-left: 4px solid #28a745;
        margin: 10px 0;
    }
    .error-box {
        background-color: #f8d7da;
        padding: 15px;
        border-radius: 8px;
        border-left: 4px solid #dc3545;
        margin: 10px 0;
    }
    .info-box {
        background-color: #d1ecf1;
        padding: 15px;
        border-radius: 8px;
        border-left: 4px solid #17a2b8;
        margin: 10px 0;
    }
    .image-card {
        border: 2px solid #e0e0e0;
        border-radius: 12px;
        padding: 15px;
        background: white;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
        transition: all 0.3s ease;
        margin-bottom: 20px;
        height: 100%;
    }
    .image-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 8px 24px rgba(0,0,0,0.15);
        border-color: #4CAF50;
    }
    .image-container {
        position: relative;
        width: 100%;
        padding-bottom: 75%;
        background: linear-gradient(135deg, #f5f5f5 0%, #e8e8e8 100%);
        border-radius: 8px;
        overflow: hidden;
        margin-bottom: 12px;
        cursor: pointer;
    }
    .image-container img {
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        object-fit: cover;
        transition: transform 0.3s ease;
    }
    .image-container:hover img {
        transform: scale(1.05);
    }
    .image-placeholder {
        position: absolute;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        text-align: center;
        color: #999;
        font-size: 14px;
    }
    .status-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: bold;
    }
    .status-success {
        background-color: #28a745;
        color: white;
    }
    .status-waiting {
        background-color: #ffc107;
        color: black;
    }
    .status-fail {
        background-color: #dc3545;
        color: white;
    }
    .filter-panel {
        background: #f8f9fa;
        padding: 20px;
        border-radius: 12px;
        margin-bottom: 20px;
        border: 1px solid #dee2e6;
    }
    .view-toggle {
        display: flex;
        gap: 10px;
        margin: 10px 0;
    }
    .metadata-badge {
        display: inline-block;
        background: #e9ecef;
        padding: 4px 8px;
        border-radius: 6px;
        font-size: 11px;
        margin: 2px;
        color: #495057;
    }
    .image-info {
        background: #f8f9fa;
        padding: 10px;
        border-radius: 6px;
        margin-top: 8px;
        font-size: 12px;
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
        'generated_images': [],
        'library_images': [],
        'gdrive_folder_id': None,
        'auto_upload': True,
        'polling_active': False,
        'service_account_info': None,
        'upload_queue': [],
        'stats': {
            'total_tasks': 0,
            'successful_tasks': 0,
            'failed_tasks': 0,
            'total_images': 0,
            'uploaded_images': 0
        },
        'current_page': "Generate",
        'selected_image_for_edit': None,
        'edit_mode': None,
        'library_view_mode': 'grid',  # grid or list
        'library_sort_by': 'date_desc',  # date_desc, date_asc, name_asc, name_desc
        'library_search_query': '',
        'library_filter_type': 'all',  # all, png, jpg, webp
        'selected_images': [],  # for batch operations
        'show_image_modal': False,
        'modal_image_data': None
    }
    
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_session_state()

# ============================================================================
# Google Drive Functions with Service Account
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
        results = st.session_state.service.files().list(
            q="name='AI_Image_Editor_Pro' and mimeType='application/vnd.google-apps.folder' and trashed=false",
            spaces='drive',
            fields='files(id, name)',
            pageSize=1
        ).execute()
        
        files = results.get('files', [])
        if files:
            st.session_state.gdrive_folder_id = files[0]['id']
            return files[0]['id']
        
        file_metadata = {
            'name': 'AI_Image_Editor_Pro',
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
        
        response = requests.get(image_url, timeout=30)
        response.raise_for_status()
        image_data = response.content
        
        mime_type = 'image/png'
        if file_name.lower().endswith('.jpg') or file_name.lower().endswith('.jpeg'):
            mime_type = 'image/jpeg'
        elif file_name.lower().endswith('.webp'):
            mime_type = 'image/webp'
        
        file_metadata = {
            'name': file_name,
            'parents': [folder_id]
        }
        
        media = MediaIoBaseUpload(
            io.BytesIO(image_data),
            mimetype=mime_type,
            resumable=True
        )
        
        file = st.session_state.service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name, webViewLink, webContentLink, mimeType'
        ).execute()
        
        file_id = file.get('id')
        
        permission = {
            'type': 'anyone',
            'role': 'reader'
        }
        st.session_state.service.permissions().create(
            fileId=file_id,
            body=permission
        ).execute()
        
        public_image_url = f"https://drive.google.com/uc?export=view&id={file_id}"
        thumbnail_url = f"https://drive.google.com/thumbnail?id={file_id}&sz=w400"
        
        st.session_state.stats['uploaded_images'] += 1
        
        return {
            'file_id': file_id,
            'file_name': file.get('name'),
            'web_link': file.get('webViewLink'),
            'content_link': file.get('webContentLink'),
            'public_image_url': public_image_url,
            'thumbnail_url': thumbnail_url,
            'mime_type': file.get('mimeType'),
            'uploaded_at': datetime.now().isoformat(),
            'task_id': task_id,
            'original_url': image_url,  # Original source URL from generation
            'id': file_id,
            'name': file.get('name')
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
            q=f"'{folder_id}' in parents and trashed=false and (mimeType='image/png' or mimeType='image/jpeg' or mimeType='image/webp' or mimeType='image/jpg')",
            spaces='drive',
            fields='files(id, name, webContentLink, webViewLink, createdTime, size, mimeType, thumbnailLink)',
            pageSize=100,
            orderBy='createdTime desc'
        ).execute()
        
        files = results.get('files', [])
        
        for file in files:
            file_id = file['id']
            file['public_image_url'] = f"https://drive.google.com/uc?export=view&id={file_id}"
            file['thumbnail_url'] = f"https://drive.google.com/thumbnail?id={file_id}&sz=w400"
            file['direct_link'] = f"https://lh3.googleusercontent.com/d/{file_id}"
        
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

# ============================================================================
# Helper function to auto-upload and save results
# ============================================================================

def save_and_upload_results(task_id, model, prompt, result_urls):
    """Save results to history and auto-upload to Google Drive if enabled."""
    for i, task in enumerate(st.session_state.task_history):
        if task['id'] == task_id:
            st.session_state.task_history[i]['status'] = 'success'
            st.session_state.task_history[i]['results'] = result_urls
            st.session_state.stats['successful_tasks'] += 1
            st.session_state.stats['total_images'] += len(result_urls)
            
            if st.session_state.authenticated and st.session_state.auto_upload:
                for j, result_url in enumerate(result_urls):
                    file_name = f"{model.replace('/', '_')}_{task_id}_{j+1}.png"
                    upload_info = upload_to_gdrive(result_url, file_name, task_id)
                    if upload_info:
                        st.session_state.library_images.insert(0, upload_info)
                        st.success(f"✅ Auto-uploaded {file_name} to Google Drive!")
            break

# ============================================================================
# Sidebar Configuration
# ============================================================================

def handle_api_key_change():
    """Callback to handle API key change and store it in session state."""
    st.session_state.api_key = st.session_state.api_key_input

def handle_service_account_upload():
    """Callback to handle service account JSON upload."""
    uploaded_file = st.session_state.service_account_uploader
    if uploaded_file is not None:
        try:
            file_content = uploaded_file.getvalue().decode("utf-8")
            service_account_json = json.loads(file_content)
            
            success, message = authenticate_with_service_account(service_account_json)
            
            if success:
                st.session_state.service_account_info = file_content
                st.success(message)
                folder_id = create_app_folder()
                if folder_id:
                    st.success(f"✅ Created/Found Drive folder")
                st.rerun()
            else:
                st.error(message)
        except json.JSONDecodeError:
            st.error("❌ Invalid JSON file")
        except Exception as e:
            st.error(f"❌ Error: {str(e)}")

def load_persisted_service_account():
    if st.session_state.service_account_info and not st.session_state.authenticated:
        try:
            service_account_json = json.loads(st.session_state.service_account_info)
            authenticate_with_service_account(service_account_json)
        except Exception as e:
            st.session_state.service_account_info = None
            st.session_state.authenticated = False
            st.error(f"Failed to re-authenticate with stored service account: {str(e)}")

load_persisted_service_account()

with st.sidebar:
    st.markdown("# 🎨 AI Image Editor Pro")
    st.markdown("---")
    
    st.header("⚙️ API Configuration")
    
    api_key_input = st.text_input(
        "API Key",
        type="password",
        value=st.session_state.api_key,
        key="api_key_input",
        on_change=handle_api_key_change,
        help="Enter your KIE.AI API key"
    )
    
    if st.session_state.api_key:
        st.success("✅ API Key configured")
    else:
        st.warning("⚠️ Please enter API key")
    
    st.markdown("---")
    
    st.header("☁️ Google Drive Setup")
    
    if not st.session_state.authenticated:
        st.info("📤 Upload service account JSON file")
        
        uploaded_file = st.file_uploader(
            "Service Account JSON",
            type=['json'],
            key="service_account_uploader",
            on_change=handle_service_account_upload,
            help="Upload your Google service account credentials"
        )
        
        if st.session_state.service_account_info and not st.session_state.authenticated:
            st.info("Stored service account info found. Attempting re-authentication...")
            
    else:
        st.success("✅ Google Drive Connected")
        
        col1, col2 = st.columns(2)
        with col1:
            auto_upload = st.checkbox(
                "Auto Upload",
                value=st.session_state.auto_upload,
                help="Automatically upload generated images to Google Drive"
            )
            st.session_state.auto_upload = auto_upload
        
        with col2:
            if st.button("🔄 Refresh", use_container_width=True):
                st.session_state.library_images = list_gdrive_images()
                st.success("Refreshed!")
        
        if st.button("🗑️ Disconnect", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.service = None
            st.session_state.credentials = None
            st.session_state.service_account_info = None
            st.rerun()
    
    st.markdown("---")
    
    st.header("📊 Statistics")
    
    stats = st.session_state.stats
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Total Tasks", stats['total_tasks'])
        st.metric("Successful", stats['successful_tasks'])
    with col2:
        st.metric("Failed", stats['failed_tasks'])
        st.metric("Uploaded", stats['uploaded_images'])
    
    success_rate = (stats['successful_tasks'] / stats['total_tasks'] * 100) if stats['total_tasks'] > 0 else 0
    st.metric("Success Rate", f"{success_rate:.1f}%")
    
    st.markdown("---")
    
    st.header("🚀 Quick Actions")
    
    if st.button("📋 View All Tasks", use_container_width=True):
        st.session_state.current_page = "History"
        st.rerun()
    
    if st.button("📚 Open Library", use_container_width=True):
        st.session_state.current_page = "Library"
        st.rerun()
    
    if st.button("🗑️ Clear History", use_container_width=True):
        if st.checkbox("Confirm clear history"):
            st.session_state.task_history = []
            st.success("History cleared!")
            st.rerun()
    
    st.markdown("---")
    st.markdown("Developed by AI Assistant")

# ============================================================================
# Main Application Pages
# ============================================================================

def display_generate_page():
    st.title("✨ Generate New Image")
    
    if st.session_state.selected_image_for_edit and st.session_state.edit_mode:
        st.info(f"📷 Image selected for editing: {st.session_state.selected_image_for_edit.get('name', 'Unknown')}")
        if st.button("❌ Clear Selection"):
            st.session_state.selected_image_for_edit = None
            st.session_state.edit_mode = None
            st.rerun()
    
    if not st.session_state.api_key:
        st.error("Please configure your API Key in the sidebar to start generating images.")
        return

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Text-to-Image", "Image Edit (Qwen)", "Image Edit (Seedream)", "Upload Images", "Advanced"])

    with tab1:
        st.header("Text-to-Image Generation")
        
        with st.form("text_to_image_form"):
            prompt = st.text_area("Prompt", "A photorealistic image of a majestic lion wearing a crown, digital art, highly detailed")
            negative_prompt = st.text_area("Negative Prompt (Optional)", "blurry, low quality, bad anatomy")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                model = st.selectbox("Model", ["stable-diffusion-xl", "dall-e-3", "midjourney-v6"], index=0, key="txt2img_model")
            with col2:
                width = st.slider("Width", 512, 1024, 1024, step=64, key="txt2img_width")
            with col3:
                height = st.slider("Height", 512, 1024, 1024, step=64, key="txt2img_height")
            
            num_images = st.slider("Number of Images", 1, 4, 1, key="txt2img_num")
            
            submitted = st.form_submit_button("Generate Image")
            
            if submitted:
                input_params = {
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "width": width,
                    "height": height,
                    "num_images": num_images
                }
                
                with st.spinner("Creating task..."):
                    result = create_task(st.session_state.api_key, model, input_params)
                
                if result["success"]:
                    task_id = result["task_id"]
                    st.info(f"Task created successfully. Task ID: {task_id}")
                    
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
                    st.error(f"Failed to create task: {result['error']}")

    with tab2:
        st.header("Image Edit - Qwen Model")
        st.info("Edit images using the Qwen Image Edit model")
        
        default_qwen_url = st.session_state.selected_image_for_edit.get('public_image_url', 
            "https://file.aiquickdraw.com/custom-page/akr/section-images/1755603225969i6j87xnw.jpg") if st.session_state.selected_image_for_edit else "https://file.aiquickdraw.com/custom-page/akr/section-images/1755603225969i6j87xnw.jpg"
        
        with st.form("qwen_image_edit_form"):
            prompt = st.text_area("Edit Prompt", "Make the image more vibrant and colorful", key="qwen_prompt")
            negative_prompt = st.text_area("Negative Prompt (Optional)", "blurry, ugly", key="qwen_neg_prompt")
            
            if st.session_state.authenticated and st.session_state.library_images:
                use_library_image = st.checkbox("📚 Use image from library", value=bool(st.session_state.selected_image_for_edit))
                
                if use_library_image:
                    library_options = {img.get('name', f"Image {i}"): img for i, img in enumerate(st.session_state.library_images)}
                    default_selection_name = st.session_state.selected_image_for_edit.get('name') if st.session_state.selected_image_for_edit else None
                    if default_selection_name not in library_options:
                         default_selection_name = list(library_options.keys())[0] if library_options else ""

                    selected_name = st.selectbox("Select Image", options=list(library_options.keys()), 
                                                key="qwen_library_select", index=list(library_options.keys()).index(default_selection_name) if default_selection_name in library_options else 0)
                    selected_img = library_options[selected_name]
                    image_url = selected_img.get('public_image_url', '')
                    st.image(image_url, caption=selected_name, width=200)
                else:
                    image_url = st.text_input("Image URL", default_qwen_url, key="qwen_image_url")
            else:
                image_url = st.text_input("Image URL", default_qwen_url, key="qwen_image_url")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                image_size = st.selectbox("Image Size", ["square", "square_hd", "portrait_4_3", "portrait_16_9", "landscape_4_3", "landscape_16_9"], index=1, key="qwen_size")
            with col2:
                num_steps = st.slider("Inference Steps", 2, 49, 25, key="qwen_steps")
            with col3:
                guidance_scale = st.slider("Guidance Scale", 0.0, 20.0, 4.0, key="qwen_guidance")
            
            acceleration = st.selectbox("Acceleration", ["none", "regular", "high"], index=0, key="qwen_accel")
            
            submitted = st.form_submit_button("Edit Image (Qwen)")
            
            if submitted:
                input_params = {
                    "prompt": prompt,
                    "image_url": image_url,
                    "negative_prompt": negative_prompt,
                    "image_size": image_size,
                    "num_inference_steps": num_steps,
                    "guidance_scale": guidance_scale,
                    "acceleration": acceleration,
                    "enable_safety_checker": True,
                    "output_format": "png"
                }
                
                with st.spinner("Creating edit task..."):
                    result = create_task(st.session_state.api_key, "qwen/image-edit", input_params)
                
                if result["success"]:
                    task_id = result["task_id"]
                    st.info(f"Task created successfully. Task ID: {task_id}")
                    
                    st.session_state.task_history.insert(0, {
                        "id": task_id,
                        "model": "qwen/image-edit",
                        "prompt": prompt,
                        "status": "waiting",
                        "created_at": datetime.now().isoformat(),
                        "results": []
                    })
                    st.session_state.current_task = task_id
                    st.session_state.selected_image_for_edit = None
                    st.session_state.edit_mode = None
                    st.rerun()
                else:
                    st.error(f"Failed to create task: {result['error']}")

    with tab3:
        st.header("Image Edit - Seedream V4 Model")
        st.info("Advanced image editing using Seedream V4 with multiple image inputs")
        
        default_seedream_url = st.session_state.selected_image_for_edit.get('public_image_url',
            "https://file.aiquickdraw.com/custom-page/akr/section-images/1757930552966e7f2on7s.png") if st.session_state.selected_image_for_edit else "https://file.aiquickdraw.com/custom-page/akr/section-images/1757930552966e7f2on7s.png"
        
        with st.form("seedream_image_edit_form"):
            prompt = st.text_area("Edit Prompt", "Create a tshirt mock up with this logo", key="seedream_prompt")
            
            if st.session_state.authenticated and st.session_state.library_images:
                use_library_image = st.checkbox("📚 Use image from library", value=bool(st.session_state.selected_image_for_edit))
                
                if use_library_image:
                    library_options = {img.get('name', f"Image {i}"): img for i, img in enumerate(st.session_state.library_images)}
                    default_selection_name = st.session_state.selected_image_for_edit.get('name') if st.session_state.selected_image_for_edit else None
                    if default_selection_name not in library_options:
                         default_selection_name = list(library_options.keys())[0] if library_options else ""

                    selected_name = st.selectbox("Select Image", options=list(library_options.keys()),
                                                key="seedream_library_select", index=list(library_options.keys()).index(default_selection_name) if default_selection_name in library_options else 0)
                    selected_img = library_options[selected_name]
                    image_url = selected_img.get('public_image_url', '')
                    st.image(image_url, caption=selected_name, width=200)
                else:
                    image_url = st.text_input("Image URL", default_seedream_url, key="seedream_image_url")
            else:
                image_url = st.text_input("Image URL", default_seedream_url, key="seedream_image_url")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                image_size = st.selectbox("Image Size", ["square", "square_hd", "portrait_4_3", "portrait_3_2", "portrait_16_9", "landscape_4_3", "landscape_3_2", "landscape_16_9", "landscape_21_9"], index=1, key="seedream_size")
            with col2:
                image_resolution = st.selectbox("Image Resolution", ["1K", "2K", "4K"], index=0, key="seedream_res")
            with col3:
                max_images = st.slider("Max Images", 1, 6, 1, key="seedream_max_images")
            
            submitted = st.form_submit_button("Edit Image (Seedream V4)")
            
            if submitted:
                input_params = {
                    "prompt": prompt,
                    "image_urls": [image_url],
                    "image_size": image_size,
                    "image_resolution": image_resolution,
                    "max_images": max_images
                }
                
                with st.spinner("Creating Seedream edit task..."):
                    result = create_task(st.session_state.api_key, "bytedance/seedream-v4-edit", input_params)
                
                if result["success"]:
                    task_id = result["task_id"]
                    st.info(f"Task created successfully. Task ID: {task_id}")
                    
                    st.session_state.task_history.insert(0, {
                        "id": task_id,
                        "model": "bytedance/seedream-v4-edit",
                        "prompt": prompt,
                        "status": "waiting",
                        "created_at": datetime.now().isoformat(),
                        "results": []
                    })
                    st.session_state.current_task = task_id
                    st.session_state.selected_image_for_edit = None
                    st.session_state.edit_mode = None
                    st.rerun()
                else:
                    st.error(f"Failed to create task: {result['error']}")

    with tab4:
        st.header("📤 Upload Your Images")
        st.info("Upload images from your computer to Google Drive library")
        
        if not st.session_state.authenticated:
            st.warning("⚠️ Please connect your Google Drive account in the sidebar to upload images.")
        else:
            uploaded_files = st.file_uploader(
                "Choose images to upload",
                type=['png', 'jpg', 'jpeg', 'webp'],
                accept_multiple_files=True,
                key="image_uploader"
            )
            
            if uploaded_files:
                st.markdown(f"**{len(uploaded_files)} file(s) selected**")
                
                preview_cols = st.columns(min(len(uploaded_files), 4))
                for idx, uploaded_file in enumerate(uploaded_files[:4]):
                    with preview_cols[idx]:
                        st.image(uploaded_file, caption=uploaded_file.name, use_container_width=True)
                
                if len(uploaded_files) > 4:
                    st.info(f"And {len(uploaded_files) - 4} more file(s)...")
                
                if st.button("⬆️ Upload All to Google Drive", type="primary", use_container_width=True):
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    success_count = 0
                    for idx, uploaded_file in enumerate(uploaded_files):
                        status_text.text(f"Uploading {uploaded_file.name}... ({idx + 1}/{len(uploaded_files)})")
                        
                        try:
                            folder_id = st.session_state.gdrive_folder_id or create_app_folder()
                            if not folder_id:
                                st.error(f"Failed to get folder ID for {uploaded_file.name}")
                                continue
                            
                            image_data = uploaded_file.getvalue()
                            
                            mime_type = 'image/png'
                            if uploaded_file.name.lower().endswith('.jpg') or uploaded_file.name.lower().endswith('.jpeg'):
                                mime_type = 'image/jpeg'
                            elif uploaded_file.name.lower().endswith('.webp'):
                                mime_type = 'image/webp'
                            
                            file_metadata = {
                                'name': uploaded_file.name,
                                'parents': [folder_id]
                            }
                            
                            media = MediaIoBaseUpload(
                                io.BytesIO(image_data),
                                mimetype=mime_type,
                                resumable=True
                            )
                            
                            file = st.session_state.service.files().create(
                                body=file_metadata,
                                media_body=media,
                                fields='id, name, webViewLink, webContentLink, mimeType, createdTime, size'
                            ).execute()
                            
                            file_id = file.get('id')
                            
                            permission = {
                                'type': 'anyone',
                                'role': 'reader'
                            }
                            st.session_state.service.permissions().create(
                                fileId=file_id,
                                body=permission
                            ).execute()
                            
                            public_image_url = f"https://drive.google.com/uc?export=view&id={file_id}"
                            thumbnail_url = f"https://drive.google.com/thumbnail?id={file_id}&sz=w400"
                            
                            upload_info = {
                                'file_id': file_id,
                                'file_name': file.get('name'),
                                'web_link': file.get('webViewLink'),
                                'content_link': file.get('webContentLink'),
                                'public_image_url': public_image_url,
                                'thumbnail_url': thumbnail_url,
                                'mime_type': file.get('mimeType'),
                                'uploaded_at': datetime.now().isoformat(),
                                'task_id': None,
                                'original_url': public_image_url,
                                'id': file_id,
                                'name': file.get('name'),
                                'createdTime': file.get('createdTime'),
                                'size': file.get('size'),
                                'mimeType': file.get('mimeType'),
                                'thumbnailLink': thumbnail_url,
                                'direct_link': f"https://lh3.googleusercontent.com/d/{file_id}"
                            }
                            
                            st.session_state.library_images.insert(0, upload_info)
                            st.session_state.stats['uploaded_images'] += 1
                            success_count += 1
                            
                        except Exception as e:
                            st.error(f"Error uploading {uploaded_file.name}: {str(e)}")
                        
                        progress_bar.progress((idx + 1) / len(uploaded_files))
                    
                    progress_bar.empty()
                    status_text.empty()
                    
                    if success_count == len(uploaded_files):
                        st.success(f"✅ Successfully uploaded all {success_count} image(s) to Google Drive!")
                    elif success_count > 0:
                        st.warning(f"⚠️ Uploaded {success_count} of {len(uploaded_files)} image(s)")
                    else:
                        st.error("❌ Failed to upload images")
                    
                    if success_count > 0:
                        if st.button("📚 View in Library"):
                            st.session_state.current_page = "Library"
                            st.rerun()
            else:
                st.info("👆 Click 'Browse files' to select images from your computer")
                st.markdown("""
                ### Supported formats:
                - PNG (.png)
                - JPEG (.jpg, .jpeg)
                - WebP (.webp)
                
                Upload multiple images at once to quickly populate your library!
                """)

    with tab5:
        st.header("Advanced Generation Options")
        st.info("Additional generation models and options coming soon!")
        
        st.markdown("""
        ### Available Features:
        - **Inpainting**: Edit specific areas of an image
        - **Outpainting**: Extend image boundaries
        - **Style Transfer**: Apply artistic styles to images
        - **Image Enhancement**: Upscale and enhance image quality
        
        More features will be added soon!
        """)

def display_history_page():
    st.title("📋 Task History")
    
    if not st.session_state.task_history:
        st.info("No tasks in history yet.")
        return
    
    if st.session_state.polling_active:
        st.warning("Polling is currently active for a task. Please wait.")
    
    for i, task in enumerate(st.session_state.task_history):
        st.subheader(f"Task ID: {task['id']}")
        
        col1, col2, col3, col4 = st.columns([1, 2, 1, 1])
        col1.markdown(f"**Model:** {task['model']}")
        col2.markdown(f"**Prompt:** {task['prompt'][:50]}...")
        col3.markdown(f"**Status:** <span class='status-badge status-{task['status']}'>{task['status'].upper()}</span>", unsafe_allow_html=True)
        col4.markdown(f"**Created:** {datetime.fromisoformat(task['created_at']).strftime('%Y-%m-%d %H:%M')}")
        
        if task['status'] == 'waiting' or task['status'] == 'processing':
            if not st.session_state.polling_active:
                if st.button(f"Check Status for {task['id']}", key=f"check_{task['id']}"):
                    st.session_state.polling_active = True
                    st.session_state.current_task = task['id']
                    st.rerun()
            
            if st.session_state.current_task == task['id'] and st.session_state.polling_active:
                st.info("Polling for task status...")
                
                result = poll_task_until_complete(st.session_state.api_key, task['id'])
                
                st.session_state.polling_active = False
                st.session_state.current_task = None
                
                if result["success"]:
                    try:
                        result_json = json.loads(result['data'].get('resultJson', '{}'))
                        result_urls = result_json.get('resultUrls', [])
                        
                        save_and_upload_results(task['id'], task['model'], task['prompt'], result_urls)
                        
                        st.success("Task completed and results saved!")
                        st.rerun()
                    except json.JSONDecodeError:
                        st.error("Failed to parse result JSON")
                        st.session_state.task_history[i]['status'] = 'fail'
                        st.session_state.stats['failed_tasks'] += 1
                        st.rerun()
                else:
                    st.session_state.task_history[i]['status'] = 'fail'
                    st.session_state.task_history[i]['error'] = result['error']
                    st.session_state.stats['failed_tasks'] += 1
                    st.error(f"Task failed: {result['error']}")
                    st.rerun()
        
        elif task['status'] == 'success':
            st.markdown("#### Results")
            cols = st.columns(len(task['results']))
            
            for j, result_url in enumerate(task['results']):
                with cols[j]:
                    st.image(result_url, caption=f"Result {j+1}", use_container_width=True)
                    
                    if st.session_state.authenticated:
                        is_uploaded = any(
                            lib_img.get('original_url') == result_url 
                            for lib_img in st.session_state.library_images
                        )
                        
                        if not is_uploaded:
                            upload_key = f"upload_{task['id']}_{j}"
                            if st.button("⬆️ Upload to Drive", key=upload_key, use_container_width=True):
                                file_name = f"{task['model'].replace('/', '_')}_{task['id']}_{j+1}.png"
                                with st.spinner(f"Uploading {file_name}..."):
                                    upload_info = upload_to_gdrive(result_url, file_name, task['id'])
                                    if upload_info:
                                        st.session_state.library_images.insert(0, upload_info)
                                        st.success(f"Uploaded {file_name} to Drive!")
                                        st.rerun()
                                    else:
                                        st.error("Upload failed.")
                        else:
                            st.success("✅ In Drive")
                    
                    try:
                        img_response = requests.get(result_url, timeout=10)
                        st.download_button(
                            label="⬇️ Download",
                            data=img_response.content,
                            file_name=f"{task['model'].replace('/', '_')}_{task['id']}_{j+1}.png",
                            mime="image/png",
                            key=f"download_{task['id']}_{j}",
                            use_container_width=True
                        )
                    except Exception as e:
                        st.warning(f"Download unavailable: {str(e)}")
        
        elif task['status'] == 'fail':
            st.error(f"Failure reason: {task.get('error', 'Unknown error')}")
        
        st.markdown("---")

def display_library_page():
    st.title("📚 Google Drive Library")
    
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("⬅️ Back to Generate", use_container_width=True):
            st.session_state.current_page = "Generate"
            st.rerun()
    
    with col2:
        if st.button("🔄 Refresh Library", use_container_width=True):
            with st.spinner("Refreshing..."):
                st.session_state.library_images = list_gdrive_images()
                st.success("Library refreshed!")
                st.rerun()
    
    st.markdown("---")
    
    if not st.session_state.authenticated:
        st.error("Please connect your Google Drive Service Account in the sidebar to view the library.")
        return
    
    with st.spinner("Loading images from Google Drive..."):
        if not st.session_state.library_images:
            st.session_state.library_images = list_gdrive_images()
    
    if not st.session_state.library_images:
        st.info("Your Google Drive folder is empty. Start generating images or upload your own images from the 'Upload Images' tab!")
        if st.button("📤 Go to Upload Tab"):
            st.session_state.current_page = "Generate"
            st.rerun()
        return

    valid_images = [img for img in st.session_state.library_images 
                   if img and 'name' in img and 'id' in img]
    
    with st.container():
        st.markdown("<div class='filter-panel'>", unsafe_allow_html=True)
        
        filter_col1, filter_col2, filter_col3, filter_col4 = st.columns([2, 1, 1, 1])
        
        with filter_col1:
            search_query = st.text_input("🔍 Search by filename", 
                                        value=st.session_state.library_search_query,
                                        placeholder="Type to search...",
                                        key="library_search")
            st.session_state.library_search_query = search_query
        
        with filter_col2:
            sort_options = {
                'date_desc': '📅 Newest First',
                'date_asc': '📅 Oldest First',
                'name_asc': '🔤 Name A-Z',
                'name_desc': '🔤 Name Z-A'
            }
            sort_by = st.selectbox("Sort by", 
                                  options=list(sort_options.keys()),
                                  format_func=lambda x: sort_options[x],
                                  index=list(sort_options.keys()).index(st.session_state.library_sort_by),
                                  key="library_sort")
            st.session_state.library_sort_by = sort_by
        
        with filter_col3:
            filter_options = {
                'all': '🖼️ All Types',
                'png': '🖼️ PNG Only',
                'jpg': '🖼️ JPG Only',
                'webp': '🖼️ WebP Only'
            }
            filter_type = st.selectbox("Filter", 
                                      options=list(filter_options.keys()),
                                      format_func=lambda x: filter_options[x],
                                      index=list(filter_options.keys()).index(st.session_state.library_filter_type),
                                      key="library_filter")
            st.session_state.library_filter_type = filter_type
        
        with filter_col4:
            view_options = {
                'grid': '⊞ Grid View',
                'list': '≡ List View'
            }
            view_mode = st.selectbox("View", 
                                    options=list(view_options.keys()),
                                    format_func=lambda x: view_options[x],
                                    index=list(view_options.keys()).index(st.session_state.library_view_mode),
                                    key="library_view")
            st.session_state.library_view_mode = view_mode
        
        st.markdown("</div>", unsafe_allow_html=True)
    
    filtered_images = valid_images
    
    if st.session_state.library_search_query:
        filtered_images = [img for img in filtered_images 
                          if st.session_state.library_search_query.lower() in img.get('name', '').lower()]
    
    if st.session_state.library_filter_type != 'all':
        mime_type_map = {
            'png': 'image/png',
            'jpg': ['image/jpeg', 'image/jpg'],
            'webp': 'image/webp'
        }
        target_mime = mime_type_map[st.session_state.library_filter_type]
        if isinstance(target_mime, list):
            filtered_images = [img for img in filtered_images 
                             if img.get('mimeType') in target_mime]
        else:
            filtered_images = [img for img in filtered_images 
                             if img.get('mimeType') == target_mime]
    
    if st.session_state.library_sort_by == 'date_desc':
        filtered_images = sorted(filtered_images, 
                                key=lambda x: x.get('createdTime', ''), 
                                reverse=True)
    elif st.session_state.library_sort_by == 'date_asc':
        filtered_images = sorted(filtered_images, 
                                key=lambda x: x.get('createdTime', ''))
    elif st.session_state.library_sort_by == 'name_asc':
        filtered_images = sorted(filtered_images, 
                                key=lambda x: x.get('name', '').lower())
    elif st.session_state.library_sort_by == 'name_desc':
        filtered_images = sorted(filtered_images, 
                                key=lambda x: x.get('name', '').lower(), 
                                reverse=True)
    
    st.markdown(f"Showing **{len(filtered_images)}** of **{len(valid_images)}** images")
    st.markdown("---")
    
    if not filtered_images:
        st.info("No images match your search criteria.")
        return
    
    if st.session_state.library_view_mode == 'grid':
        cols_per_row = 3
        
        for i, file_info in enumerate(filtered_images):
            if i % cols_per_row == 0:
                cols = st.columns(cols_per_row)
            
            with cols[i % cols_per_row]:
                file_name = file_info.get('name', 'Unknown File')
                web_link = file_info.get('webViewLink', '#')
                file_id = file_info.get('id', f"no_id_{i}")
                
                original_url = file_info.get('original_url')  # From resultUrls
                public_image_url = file_info.get('public_image_url')
                thumbnail_url = file_info.get('thumbnail_url')
                direct_link = file_info.get('direct_link')
                
                created_time = file_info.get('createdTime', '')
                file_size = file_info.get('size', 0)
                mime_type = file_info.get('mimeType', '')
                
                with st.container():
                    st.markdown(f"<div class='image-card'>", unsafe_allow_html=True)
                    
                    image_displayed = False
                    urls_to_try = [
                        original_url,  # Original generation URL (highest quality)
                        public_image_url,  # Google Drive public URL
                        thumbnail_url,  # Google Drive thumbnail
                        direct_link  # Google Drive direct link
                    ]
                    
                    for url in urls_to_try:
                        if url and not image_displayed:
                            try:
                                st.image(url, use_container_width=True, caption=file_name)
                                image_displayed = True
                                break
                            except Exception:
                                continue
                    
                    if not image_displayed:
                        st.markdown(f"<div class='image-container'><div class='image-placeholder'>🖼️<br>Preview unavailable<br><a href='{web_link}' target='_blank'>Open in Drive</a></div></div>", unsafe_allow_html=True)
                    
                    st.markdown("<div class='image-info'>", unsafe_allow_html=True)
                    
                    if original_url:
                        st.markdown(f"<a href='{original_url}' target='_blank'><span class='metadata-badge' style='background:#4CAF50;color:white;cursor:pointer;'>🔗 Original</span></a>", unsafe_allow_html=True)
                    
                    if public_image_url:
                        st.markdown(f"<a href='{public_image_url}' target='_blank'><span class='metadata-badge' style='background:#4285F4;color:white;cursor:pointer;'>☁️ Drive</span></a>", unsafe_allow_html=True)
                    
                    if created_time:
                        try:
                            created_date = datetime.fromisoformat(created_time.replace('Z', '+00:00'))
                            st.markdown(f"<span class='metadata-badge'>📅 {created_date.strftime('%Y-%m-%d %H:%M')}</span>", unsafe_allow_html=True)
                        except:
                            pass
                    
                    if file_size:
                        try:
                            size_kb = int(file_size) / 1024
                            if size_kb > 1024:
                                size_str = f"{size_kb/1024:.1f} MB"
                            else:
                                size_str = f"{size_kb:.1f} KB"
                            st.markdown(f"<span class='metadata-badge'>💾 {size_str}</span>", unsafe_allow_html=True)
                        except:
                            pass
                    
                    if mime_type:
                        file_ext = mime_type.split('/')[-1].upper()
                        st.markdown(f"<span class='metadata-badge'>📄 {file_ext}</span>", unsafe_allow_html=True)
                    
                    st.markdown("</div>", unsafe_allow_html=True)
                    
                    st.markdown("---")
                    
                    # Edit buttons
                    edit_col1, edit_col2 = st.columns(2)
                    with edit_col1:
                        if st.button("✏️ Edit (Qwen)", key=f"edit_qwen_{file_id}", use_container_width=True):
                            st.session_state.selected_image_for_edit = file_info
                            st.session_state.edit_mode = 'qwen'
                            st.session_state.current_page = "Generate"
                            st.rerun()
                    
                    with edit_col2:
                        if st.button("🎨 Edit (Seedream)", key=f"edit_seedream_{file_id}", use_container_width=True):
                            st.session_state.selected_image_for_edit = file_info
                            st.session_state.edit_mode = 'seedream'
                            st.session_state.current_page = "Generate"
                            st.rerun()
                    
                    # Action buttons
                    btn_col1, btn_col2, btn_col3 = st.columns(3)
                    with btn_col1:
                        st.markdown(f"<a href='{web_link}' target='_blank' style='text-decoration:none;'><button style='width:100%;padding:8px;background:#4285F4;color:white;border:none;border-radius:6px;cursor:pointer;'>🔗 Drive</button></a>", unsafe_allow_html=True)
                    
                    with btn_col2:
                        view_url = original_url if original_url else public_image_url
                        if view_url:
                            st.markdown(f"<a href='{view_url}' target='_blank' style='text-decoration:none;'><button style='width:100%;padding:8px;background:#34A853;color:white;border:none;border-radius:6px;cursor:pointer;'>👁️ View</button></a>", unsafe_allow_html=True)
                    
                    with btn_col3:
                        if st.button("🗑️", key=f"delete_{file_id}", use_container_width=True, help="Delete this image"):
                            with st.spinner(f"Deleting {file_name}..."):
                                if delete_gdrive_file(file_id):
                                    st.success(f"✅ Deleted {file_name}")
                                    st.session_state.library_images = [img for img in st.session_state.library_images if img.get('id') != file_id]
                                    st.rerun()
                                else:
                                    st.error("❌ Failed to delete file.")
                    
                    st.markdown("</div>", unsafe_allow_html=True)
    
    else:  # List view
        for i, file_info in enumerate(filtered_images):
            file_name = file_info.get('name', 'Unknown File')
            web_link = file_info.get('webViewLink', '#')
            file_id = file_info.get('id', f"no_id_{i}")
            
            original_url = file_info.get('original_url')
            public_image_url = file_info.get('public_image_url')
            thumbnail_url = file_info.get('thumbnail_url')
            direct_link = file_info.get('direct_link')
            
            created_time = file_info.get('createdTime', '')
            file_size = file_info.get('size', 0)
            mime_type = file_info.get('mimeType', '')
            
            with st.container():
                st.markdown(f"<div class='image-card'>", unsafe_allow_html=True)
                
                col1, col2 = st.columns([1, 3])
                
                with col1:
                    # Thumbnail - try original first, then Drive thumbnails
                    image_displayed = False
                    urls_to_try = [original_url, thumbnail_url, public_image_url, direct_link]
                    
                    for url in urls_to_try:
                        if url and not image_displayed:
                            try:
                                st.image(url, width=150)
                                image_displayed = True
                                break
                            except Exception:
                                continue
                    
                    if not image_displayed:
                        st.markdown("🖼️ No preview")
                
                with col2:
                    st.markdown(f"### {file_name}")
                    
                    link_badges = ""
                    if original_url:
                        link_badges += f"<a href='{original_url}' target='_blank'><span class='metadata-badge' style='background:#4CAF50;color:white;cursor:pointer;'>🔗 Original</span></a> "
                    if public_image_url:
                        link_badges += f"<a href='{public_image_url}' target='_blank'><span class='metadata-badge' style='background:#4285F4;color:white;cursor:pointer;'>☁️ Drive</span></a> "
                    
                    # Metadata
                    metadata_html = link_badges
                    if created_time:
                        try:
                            created_date = datetime.fromisoformat(created_time.replace('Z', '+00:00'))
                            metadata_html += f"<span class='metadata-badge'>📅 {created_date.strftime('%Y-%m-%d %H:%M')}</span> "
                        except:
                            pass
                    
                    if file_size:
                        try:
                            size_kb = int(file_size) / 1024
                            if size_kb > 1024:
                                size_str = f"{size_kb/1024:.1f} MB"
                            else:
                                size_str = f"{size_kb:.1f} KB"
                            metadata_html += f"<span class='metadata-badge'>💾 {size_str}</span> "
                        except:
                            pass
                    
                    if mime_type:
                        file_ext = mime_type.split('/')[-1].upper()
                        metadata_html += f"<span class='metadata-badge'>📄 {file_ext}</span>"
                    
                    st.markdown(metadata_html, unsafe_allow_html=True)
                    
                    st.markdown("---")
                    
                    # Action buttons in list view
                    btn_col1, btn_col2, btn_col3, btn_col4, btn_col5 = st.columns(5)
                    
                    with btn_col1:
                        if st.button("✏️ Qwen", key=f"list_edit_qwen_{file_id}", use_container_width=True):
                            st.session_state.selected_image_for_edit = file_info
                            st.session_state.edit_mode = 'qwen'
                            st.session_state.current_page = "Generate"
                            st.rerun()
                    
                    with btn_col2:
                        if st.button("🎨 Seedream", key=f"list_edit_seedream_{file_id}", use_container_width=True):
                            st.session_state.selected_image_for_edit = file_info
                            st.session_state.edit_mode = 'seedream'
                            st.session_state.current_page = "Generate"
                            st.rerun()
                    
                    with btn_col3:
                        st.markdown(f"<a href='{web_link}' target='_blank' style='text-decoration:none;'><button style='width:100%;padding:8px;background:#4285F4;color:white;border:none;border-radius:6px;cursor:pointer;'>🔗 Drive</button></a>", unsafe_allow_html=True)
                    
                    with btn_col4:
                        view_url = original_url if original_url else public_image_url
                        if view_url:
                            st.markdown(f"<a href='{view_url}' target='_blank' style='text-decoration:none;'><button style='width:100%;padding:8px;background:#34A853;color:white;border:none;border-radius:6px;cursor:pointer;'>👁️ View</button></a>", unsafe_allow_html=True)
                    
                    with btn_col5:
                        if st.button("🗑️ Delete", key=f"list_delete_{file_id}", use_container_width=True):
                            with st.spinner(f"Deleting {file_name}..."):
                                if delete_gdrive_file(file_id):
                                    st.success(f"✅ Deleted {file_name}")
                                    st.session_state.library_images = [img for img in st.session_state.library_images if img.get('id') != file_id]
                                    st.rerun()
                                else:
                                    st.error("❌ Failed to delete file.")
                
                st.markdown("</div>", unsafe_allow_html=True)
                st.markdown("---")

# ============================================================================
# Main Routing
# ============================================================================

if st.session_state.current_page == "Generate":
    display_generate_page()
elif st.session_state.current_page == "History":
    display_history_page()
elif st.session_state.current_page == "Library":
    display_library_page()
else:
    st.session_state.current_page = "Generate"
    st.rerun()
