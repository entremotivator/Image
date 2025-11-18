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
    .image-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
        gap: 20px;
        margin: 20px 0;
    }
    .image-card {
        border: 1px solid #ddd;
        border-radius: 8px;
        padding: 10px;
        background: white;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        transition: transform 0.2s;
    }
    .image-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
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
        'edit_mode': None  # Can be 'qwen' or 'seedream'
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
        # Search for existing folder
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
        
        # Create new folder
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
            fields='id, name, webViewLink, webContentLink'
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
        
        # Update stats
        st.session_state.stats['uploaded_images'] += 1
        
        return {
            'file_id': file_id,
            'file_name': file.get('name'),
            'web_link': file.get('webViewLink'),
            'content_link': file.get('webContentLink'),
            'public_image_url': public_image_url,  # Added public image URL
            'uploaded_at': datetime.now().isoformat(),
            'task_id': task_id,
            'original_url': image_url,
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
            q=f"'{folder_id}' in parents and trashed=false and (mimeType='image/png' or mimeType='image/jpeg' or mimeType='image/webp')",
            spaces='drive',
            fields='files(id, name, webContentLink, webViewLink, createdTime, size)',
            pageSize=100,
            orderBy='createdTime desc'
        ).execute()
        
        files = results.get('files', [])
        
        for file in files:
            file['public_image_url'] = f"https://drive.google.com/uc?export=view&id={file['id']}"
        
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
    # Update task in history
    for i, task in enumerate(st.session_state.task_history):
        if task['id'] == task_id:
            st.session_state.task_history[i]['status'] = 'success'
            st.session_state.task_history[i]['results'] = result_urls
            st.session_state.stats['successful_tasks'] += 1
            st.session_state.stats['total_images'] += len(result_urls)
            
            # Auto-upload to Google Drive if enabled and authenticated
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
    
    # API Configuration
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
    
    # Google Drive Service Account
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
    
    # Statistics
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
    
    # Quick Actions
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

    tab1, tab2, tab3, tab4 = st.tabs(["Text-to-Image", "Image Edit (Qwen)", "Image Edit (Seedream)", "Advanced"])

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
                    # Ensure a default selected image if available
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
                    # Ensure a default selected image if available
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
                    st.image(result_url, caption=f"Result {j+1}", use_column_width=True)
                    
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
    
    if st.button("⬅️ Back to Generate", use_container_width=False):
        st.session_state.current_page = "Generate"
        st.rerun()
    
    st.markdown("---")
    
    if not st.session_state.authenticated:
        st.error("Please connect your Google Drive Service Account in the sidebar to view the library.")
        return
    
    with st.spinner("Loading images from Google Drive..."):
        st.session_state.library_images = list_gdrive_images()
    
    if not st.session_state.library_images:
        st.info("Your Google Drive folder is empty. Start generating images to populate your library!")
        return
    
    valid_images = [img for img in st.session_state.library_images if img and 'name' in img and 'id' in img]
    
    st.markdown(f"Found **{len(valid_images)}** images in your Drive folder.")
    st.markdown("---")
    
    cols_per_row = 3
    
    for i, file_info in enumerate(valid_images):
        if i % cols_per_row == 0:
            cols = st.columns(cols_per_row)
        
        with cols[i % cols_per_row]:
            file_name = file_info.get('name', 'Unknown File')
            web_link = file_info.get('webViewLink', '#')
            file_id = file_info.get('id', f"no_id_{i}")
            public_image_url = file_info.get('public_image_url')
            
            st.markdown(f"**{file_name}**")
            
            if public_image_url:
                try:
                    st.image(public_image_url, use_column_width=True)
                except Exception as e:
                    st.warning("⚠️ Image preview unavailable")
                    st.markdown(f"[Open in Drive]({web_link})")
            else:
                st.info("Image preview not available")
                st.markdown(f"[Open in Drive]({web_link})")
            
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
            
            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                if st.button("🔗 Open in Drive", key=f"open_{file_id}", use_container_width=True):
                    st.markdown(f"[Click here to open]({web_link})")
            
            with btn_col2:
                if st.button("🗑️ Delete", key=f"delete_{file_id}", use_container_width=True):
                    with st.spinner(f"Deleting {file_name}..."):
                        if delete_gdrive_file(file_id):
                            st.success(f"✅ Deleted {file_name}")
                            st.session_state.library_images = [img for img in st.session_state.library_images if img.get('id') != file_id]
                            st.rerun()
                        else:
                            st.error("❌ Failed to delete file.")
            
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
