import streamlit as st
import requests
import json
import time
import io
import pickle
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from pathlib import Path
from PIL import Image as PILImage
import cv2
import numpy as np

# Google Drive imports
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload

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
        padding: 15px;
        border-radius: 10px;
        margin: 10px 0;
    }
    .success-box {
        background-color: #d4edda;
        padding: 15px;
        border-radius: 8px;
        border-left: 4px solid #28a745;
    }
    .error-box {
        background-color: #f8d7da;
        padding: 15px;
        border-radius: 8px;
        border-left: 4px solid #dc3545;
    }
    .info-box {
        background-color: #d1ecf1;
        padding: 15px;
        border-radius: 8px;
        border-left: 4px solid #17a2b8;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# Configuration
# ============================================================================

# API Configuration
BASE_URL = "https://api.kie.ai/api/v1/jobs"

# Google Drive Scopes
SCOPES = ['https://www.googleapis.com/auth/drive']

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
        'user_email': None,
        'service': None,
        'credentials': None,
        'generated_images': [],
        'library_images': [],
        'current_page': 'home',
        'selected_image': None,
        'editor_mode': False,
        'gdrive_folder_id': None,
        'last_refresh': None,
        'edit_history': [],
    }
    
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_session_state()

# ============================================================================
# Google Drive Functions (Cloud-Optimized)
# ============================================================================

def get_google_credentials_from_secrets():
    """Get Google credentials from Streamlit secrets."""
    try:
        secrets = st.secrets
        if "google_client_id" in secrets and "google_client_secret" in secrets:
            return {
                "client_id": secrets["google_client_id"],
                "client_secret": secrets["google_client_secret"],
                "redirect_uri": "https://streamlit.io"
            }
    except:
        pass
    return None

def authenticate_google_drive():
    """Authenticate with Google Drive using OAuth."""
    try:
        secrets = st.secrets
        
        # Create OAuth flow
        flow = Flow.from_client_config(
            {
                "installed": {
                    "client_id": secrets["google_client_id"],
                    "client_secret": secrets["google_client_secret"],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["https://streamlit.io"]
                }
            },
            scopes=SCOPES
        )
        
        auth_url, state = flow.authorization_url(access_type='offline', prompt='consent')
        
        st.info("🔐 Click the link below to authenticate with Google Drive:")
        st.markdown(f"[Authenticate with Google]({auth_url})")
        
        auth_code = st.text_input("Paste the authorization code here:")
        
        if auth_code:
            credentials = flow.fetch_token(code=auth_code)
            st.session_state.credentials = credentials
            st.session_state.authenticated = True
            st.session_state.service = build('drive', 'v3', credentials=Credentials.from_authorized_user_info(credentials))
            st.success("✅ Authentication successful!")
            st.rerun()
    except Exception as e:
        st.error(f"Authentication error: {str(e)}")

def create_app_folder():
    """Create or get the app's folder in Google Drive."""
    if not st.session_state.service:
        return None
    
    try:
        results = st.session_state.service.files().list(
            q="name='AI Image Editor Pro' and mimeType='application/vnd.google-apps.folder' and trashed=false",
            spaces='drive',
            fields='files(id, name)',
            pageSize=1
        ).execute()
        
        files = results.get('files', [])
        if files:
            st.session_state.gdrive_folder_id = files[0]['id']
            return files[0]['id']
        
        file_metadata = {
            'name': 'AI Image Editor Pro',
            'mimeType': 'application/vnd.google-apps.folder'
        }
        folder = st.session_state.service.files().create(
            body=file_metadata,
            fields='id'
        ).execute()
        
        st.session_state.gdrive_folder_id = folder.get('id')
        return folder.get('id')
    except Exception as e:
        st.error(f"Error creating folder: {str(e)}")
        return None

def upload_to_gdrive(file_data: bytes, file_name: str, folder_id: Optional[str] = None):
    """Upload a file to Google Drive."""
    if not st.session_state.service:
        return None
    
    try:
        if not folder_id:
            folder_id = create_app_folder()
        
        file_metadata = {
            'name': file_name,
            'parents': [folder_id] if folder_id else []
        }
        
        media = MediaIoBaseUpload(io.BytesIO(file_data), mimetype='image/png')
        file = st.session_state.service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink'
        ).execute()
        
        return {
            'file_id': file.get('id'),
            'file_name': file_name,
            'web_link': file.get('webViewLink'),
            'uploaded_at': datetime.now().isoformat()
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
            folder_id = create_app_folder()
        
        results = st.session_state.service.files().list(
            q=f"'{folder_id}' in parents and trashed=false and (mimeType='image/png' or mimeType='image/jpeg' or mimeType='image/webp')",
            spaces='drive',
            fields='files(id, name, webContentLink, createdTime, size)',
            pageSize=100,
            orderBy='createdTime desc'
        ).execute()
        
        return results.get('files', [])
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
        
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 200:
                return {"success": True, "task_id": data["data"]["taskId"]}
            else:
                return {"success": False, "error": data.get('msg', 'Unknown error')}
        else:
            return {"success": False, "error": f"HTTP {response.status_code}"}
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

# ============================================================================
# Image Processing Functions
# ============================================================================

@st.cache_resource
def get_cv2_resources():
    """Cache CV2 resources."""
    return cv2

def apply_brightness_contrast(image, brightness=0, contrast=0):
    """Apply brightness and contrast adjustments."""
    img_array = np.array(image).astype(float) / 255.0
    img_array = img_array * (1 + contrast / 100)
    img_array = img_array + (brightness / 100)
    img_array = np.clip(img_array, 0, 1)
    return PILImage.fromarray((img_array * 255).astype(np.uint8))

def apply_blur(image, blur_amount=5):
    """Apply Gaussian blur."""
    cv2_module = get_cv2_resources()
    img_cv = cv2_module.cvtColor(np.array(image), cv2_module.COLOR_RGB2BGR)
    blurred = cv2_module.GaussianBlur(img_cv, (blur_amount * 2 + 1, blur_amount * 2 + 1), 0)
    return PILImage.fromarray(cv2_module.cvtColor(blurred, cv2_module.COLOR_BGR2RGB))

def apply_saturation(image, saturation=0):
    """Apply saturation adjustment."""
    cv2_module = get_cv2_resources()
    img_hsv = cv2_module.cvtColor(np.array(image), cv2_module.COLOR_RGB2HSV).astype(float)
    img_hsv[:, :, 1] = img_hsv[:, :, 1] * (1 + saturation / 100)
    img_hsv[:, :, 1] = np.clip(img_hsv[:, :, 1], 0, 255)
    return PILImage.fromarray(cv2_module.cvtColor(img_hsv.astype(np.uint8), cv2_module.COLOR_HSV2RGB))

def apply_rotation(image, angle=0):
    """Apply rotation."""
    return image.rotate(angle, expand=True, fillcolor='white')

# ============================================================================
# Sidebar Navigation
# ============================================================================

with st.sidebar:
    st.markdown("# 🎨 AI Image Editor Pro")
    st.markdown("---")
    
    # API Configuration
    st.header("⚙️ Configuration")
    
    # Get API key from secrets or input
    api_key = st.secrets.get("api_key", "") if "api_key" in st.secrets else ""
    
    if not api_key:
        api_key = st.text_input(
            "API Key",
            type="password",
            value=st.session_state.api_key,
            help="Get from https://kie.ai/api-key"
        )
    
    if api_key:
        st.session_state.api_key = api_key
        st.success("✅ API Key configured")
    else:
        st.warning("⚠️ Please enter API key")
    
    st.markdown("---")
    
    # Google Drive Authentication
    st.header("☁️ Google Drive")
    
    if not st.session_state.authenticated:
        if st.button("🔑 Authenticate Google Drive", use_container_width=True):
            authenticate_google_drive()
    else:
        st.success("✅ Google Drive Connected")
        if st.button("📂 Create App Folder", use_container_width=True):
            folder_id = create_app_folder()
            if folder_id:
                st.success(f"✅ Folder ready")
    
    st.markdown("---")
    
    # Navigation
    st.header("📍 Navigation")
    page = st.radio(
        "Select Page",
        ["🏠 Home", "🎨 SeedDream V4", "✨ Qwen Edit", "📚 Library", "✏️ Editor", "📊 History", "📖 Docs"],
        label_visibility="collapsed"
    )
    
    st.markdown("---")
    
    # Statistics
    st.markdown("### 📊 Statistics")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Tasks", len(st.session_state.task_history))
    with col2:
        success = sum(1 for t in st.session_state.task_history if t.get('status') == 'success')
        st.metric("Success", success)
    
    st.markdown("---")
    
    st.markdown("### 🔗 Quick Links")
    st.markdown("- [Get API Key](https://kie.ai/api-key)")
    st.markdown("- [Documentation](https://kie.ai/docs)")
    st.markdown("- [Support](https://kie.ai/support)")

# ============================================================================
# Pages
# ============================================================================

# Page: Home
if page == "🏠 Home":
    st.title("🎨 AI Image Editor Pro")
    st.markdown("### Transform your images with powerful AI models")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        <div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; border-radius: 15px; color: white;'>
            <h2>🎨 SeedDream V4 Edit</h2>
            <p>Advanced image editing with multiple inputs</p>
            <ul>
                <li>Multi-image input (up to 10)</li>
                <li>Multiple aspect ratios</li>
                <li>Up to 4K resolution</li>
                <li>Batch generation (1-6 images)</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div style='background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); padding: 30px; border-radius: 15px; color: white;'>
            <h2>✨ Qwen Image Edit</h2>
            <p>Fast and precise image editing</p>
            <ul>
                <li>Single image editing</li>
                <li>Acceleration options</li>
                <li>Fine-tuned parameters</li>
                <li>Safety checker</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    st.subheader("🚀 Getting Started")
    st.markdown("""
    1. **Configure API Key**: Enter your API key in the sidebar
    2. **Authenticate Google Drive**: Connect your Google account for auto-upload
    3. **Choose a Model**: Select SeedDream V4 or Qwen Image Edit
    4. **Generate Images**: Create amazing images with AI
    5. **Manage Library**: Organize and edit your generated images
    """)
    
    st.markdown("---")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Tasks", len(st.session_state.task_history))
    with col2:
        successful = sum(1 for t in st.session_state.task_history if t.get('status') == 'success')
        st.metric("Successful", successful)
    with col3:
        failed = sum(1 for t in st.session_state.task_history if t.get('status') == 'fail')
        st.metric("Failed", failed)
    with col4:
        st.metric("Library", len(st.session_state.library_images))

# Page: SeedDream V4 Edit
elif page == "🎨 SeedDream V4":
    st.title("🎨 SeedDream V4 Edit")
    st.markdown("Generate and edit images with multiple inputs and high resolution output")
    
    presets = {
        "Custom": {},
        "Brand Showcase": {
            "prompt": "Create a professional brand showcase with product display, modern design, clean background",
            "image_size": "square_hd",
            "image_resolution": "1K",
            "max_images": 1
        },
        "Product Photography": {
            "prompt": "Professional product photography with studio lighting and clean white background",
            "image_size": "landscape_4_3",
            "image_resolution": "2K",
            "max_images": 2
        },
        "Fashion Design": {
            "prompt": "Modern fashion design concept with elegant styling and contemporary aesthetics",
            "image_size": "portrait_4_3",
            "image_resolution": "2K",
            "max_images": 3
        },
    }
    
    preset = st.selectbox("📋 Choose a preset", list(presets.keys()))
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("📝 Input Parameters")
        
        preset_data = presets.get(preset, {})
        
        prompt = st.text_area(
            "Prompt*",
            value=preset_data.get("prompt", ""),
            height=120,
            max_chars=5000,
            help="Describe how you want to edit the image"
        )
        
        st.markdown("##### Input Images")
        num_images = st.number_input("Number of input images", min_value=1, max_value=10, value=1)
        
        image_urls = []
        for i in range(num_images):
            url = st.text_input(
                f"Image URL {i+1}*",
                key=f"seedream_img_{i}",
                value="https://file.aiquickdraw.com/custom-page/akr/section-images/1757930552966e7f2on7s.png" if i == 0 else "",
            )
            if url:
                image_urls.append(url)
        
        with st.expander("🎛️ Advanced Settings", expanded=True):
            col_a, col_b = st.columns(2)
            
            with col_a:
                image_size = st.selectbox(
                    "Image Size",
                    ["square", "square_hd", "portrait_4_3", "portrait_16_9", "landscape_4_3", "landscape_16_9"],
                    index=1
                )
            
            with col_b:
                image_resolution = st.selectbox(
                    "Resolution",
                    ["1K", "2K", "4K"],
                    index=0
                )
            
            max_images = st.slider("Max Images", 1, 6, preset_data.get("max_images", 1))
        
        generate_btn = st.button("🚀 Generate Images", type="primary", use_container_width=True)
    
    with col2:
        st.subheader("📊 Results")
        
        if generate_btn:
            if not st.session_state.api_key:
                st.error("⚠️ Please enter your API key")
            elif not prompt:
                st.error("⚠️ Please enter a prompt")
            elif not image_urls:
                st.error("⚠️ Please provide image URLs")
            else:
                with st.spinner("Creating generation task..."):
                    input_params = {
                        "prompt": prompt,
                        "image_urls": image_urls,
                        "image_size": image_size,
                        "image_resolution": image_resolution,
                        "max_images": max_images
                    }
                    
                    result = create_task(st.session_state.api_key, "bytedance/seedream-v4-edit", input_params)
                    
                    if result["success"]:
                        task_id = result["task_id"]
                        st.session_state.current_task = {
                            "task_id": task_id,
                            "model": "bytedance/seedream-v4-edit",
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "status": "waiting"
                        }
                        st.session_state.task_history.append(st.session_state.current_task)
                        st.success(f"✅ Task created!")
                        st.code(task_id, language=None)
                    else:
                        st.error(f"❌ Error: {result['error']}")
        
        if st.session_state.current_task:
            st.markdown("---")
            task_id = st.session_state.current_task["task_id"]
            
            col_check, col_clear = st.columns(2)
            with col_check:
                check_btn = st.button("🔄 Check Status", use_container_width=True)
            with col_clear:
                if st.button("🗑️ Clear", use_container_width=True):
                    st.session_state.current_task = None
                    st.rerun()
            
            if check_btn:
                with st.spinner("Checking status..."):
                    result = check_task_status(st.session_state.api_key, task_id)
                    
                    if result["success"]:
                        task_data = result["data"]
                        state = task_data["state"]
                        
                        st.session_state.current_task["status"] = state
                        
                        if state == "success":
                            st.success("✅ Task completed!")
                            result_json = json.loads(task_data.get("resultJson", "{}"))
                            
                            for idx, url in enumerate(result_json.get("resultUrls", [])):
                                st.image(url, caption=f"Image {idx + 1}", use_container_width=True)
                                
                                # Auto-upload to Google Drive
                                if st.session_state.authenticated:
                                    if st.button(f"📤 Upload to Drive", key=f"upload_{idx}"):
                                        with st.spinner("Uploading..."):
                                            img_response = requests.get(url)
                                            upload_result = upload_to_gdrive(
                                                img_response.content,
                                                f"Generated_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{idx}.png"
                                            )
                                            if upload_result:
                                                st.success("✅ Uploaded to Google Drive")
                        
                        elif state == "fail":
                            st.error(f"❌ Task failed: {task_data.get('failMsg', 'Unknown error')}")

# Page: Qwen Image Edit
elif page == "✨ Qwen Edit":
    st.title("✨ Qwen Image Edit")
    st.markdown("Fast and precise image editing with fine control")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("📝 Input Parameters")
        
        prompt = st.text_area(
            "Edit Prompt*",
            height=120,
            max_chars=2000,
            help="Describe the edits you want to make"
        )
        
        image_url = st.text_input(
            "Image URL*",
            value="https://file.aiquickdraw.com/custom-page/akr/section-images/1757930552966e7f2on7s.png",
            help="URL of the image to edit"
        )
        
        with st.expander("Preview"):
            if image_url:
                st.image(image_url, use_container_width=True)
        
        with st.expander("🎛️ Advanced Settings", expanded=True):
            col_a, col_b = st.columns(2)
            
            with col_a:
                acceleration = st.selectbox(
                    "Acceleration",
                    ["none", "regular", "high"],
                    help="Higher = faster generation"
                )
                image_size = st.selectbox(
                    "Image Size",
                    ["square", "square_hd", "portrait_4_3", "landscape_4_3"]
                )
            
            with col_b:
                num_inference_steps = st.slider("Inference Steps", 2, 49, 25)
                guidance_scale = st.slider("Guidance Scale", 0.0, 20.0, 4.0, 0.1)
        
        generate_btn = st.button("🚀 Generate", type="primary", use_container_width=True)
    
    with col2:
        st.subheader("📊 Results")
        
        if generate_btn:
            if not st.session_state.api_key:
                st.error("⚠️ Please enter API key")
            elif not prompt:
                st.error("⚠️ Please enter a prompt")
            else:
                with st.spinner("Creating task..."):
                    input_params = {
                        "prompt": prompt,
                        "image_url": image_url,
                        "acceleration": acceleration,
                        "image_size": image_size,
                        "num_inference_steps": num_inference_steps,
                        "guidance_scale": guidance_scale
                    }
                    
                    result = create_task(st.session_state.api_key, "qwen/image-edit", input_params)
                    
                    if result["success"]:
                        task_id = result["task_id"]
                        st.session_state.current_task = {
                            "task_id": task_id,
                            "model": "qwen/image-edit",
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "status": "waiting"
                        }
                        st.session_state.task_history.append(st.session_state.current_task)
                        st.success("✅ Task created!")
                        st.code(task_id)
                    else:
                        st.error(f"❌ Error: {result['error']}")
        
        if st.session_state.current_task:
            st.markdown("---")
            task_id = st.session_state.current_task["task_id"]
            
            col_check, col_clear = st.columns(2)
            with col_check:
                check_btn = st.button("🔄 Check Status", use_container_width=True, key="qwen_check")
            with col_clear:
                if st.button("🗑️ Clear", use_container_width=True, key="qwen_clear"):
                    st.session_state.current_task = None
                    st.rerun()
            
            if check_btn:
                with st.spinner("Checking..."):
                    result = check_task_status(st.session_state.api_key, task_id)
                    
                    if result["success"]:
                        task_data = result["data"]
                        state = task_data["state"]
                        
                        if state == "success":
                            st.success("✅ Completed!")
                            result_json = json.loads(task_data.get("resultJson", "{}"))
                            
                            for idx, url in enumerate(result_json.get("resultUrls", [])):
                                st.image(url, use_container_width=True)

# Page: Library
elif page == "📚 Library":
    st.title("📚 Image Library")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        search_query = st.text_input("🔍 Search images")
    
    with col2:
        sort_by = st.selectbox("Sort by", ["Newest", "Oldest", "Name"])
    
    with col3:
        st.write("")
        st.write("")
        if st.button("🔄 Refresh", use_container_width=True):
            with st.spinner("Loading..."):
                st.session_state.library_images = list_gdrive_images()
                st.session_state.last_refresh = datetime.now()
    
    if not st.session_state.authenticated:
        st.warning("⚠️ Please authenticate with Google Drive first")
    else:
        images = st.session_state.library_images
        
        if search_query:
            images = [img for img in images if search_query.lower() in img['name'].lower()]
        
        if sort_by == "Oldest":
            images = sorted(images, key=lambda x: x.get('createdTime', ''))
        elif sort_by == "Name":
            images = sorted(images, key=lambda x: x['name'])
        else:
            images = sorted(images, key=lambda x: x.get('createdTime', ''), reverse=True)
        
        if not images:
            st.info("📭 No images found")
        else:
            st.write(f"Found **{len(images)}** images")
            
            cols = st.columns(4)
            for idx, img in enumerate(images):
                col = cols[idx % 4]
                
                with col:
                    st.image(img['webContentLink'], use_container_width=True)
                    st.caption(img['name'][:20])
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        if st.button("✏️", key=f"edit_{img['id']}", use_container_width=True):
                            st.session_state.selected_image = img
                            st.session_state.editor_mode = True
                            st.rerun()
                    with col2:
                        st.markdown(f"[🔗](({img['webContentLink']}))")
                    with col3:
                        if st.button("🗑️", key=f"del_{img['id']}", use_container_width=True):
                            if delete_gdrive_file(img['id']):
                                st.success("✅ Deleted")
                                st.rerun()

# Page: Editor
elif page == "✏️ Editor":
    st.title("✏️ Image Editor")
    
    if not st.session_state.selected_image:
        st.info("Select an image from the Library first")
    else:
        img = st.session_state.selected_image
        st.subheader(f"Editing: {img['name']}")
        
        img_response = requests.get(img['webContentLink'])
        image = PILImage.open(io.BytesIO(img_response.content))
        
        tab1, tab2, tab3, tab4 = st.tabs(["Adjustments", "Filters", "Transform", "Export"])
        
        with tab1:
            col1, col2 = st.columns(2)
            with col1:
                brightness = st.slider("Brightness", -100, 100, 0)
            with col2:
                contrast = st.slider("Contrast", -100, 100, 0)
            
            if brightness != 0 or contrast != 0:
                edited = apply_brightness_contrast(image, brightness, contrast)
                st.image(edited, use_column_width=True)
        
        with tab2:
            col1, col2 = st.columns(2)
            with col1:
                blur = st.slider("Blur", 0, 20, 0)
            with col2:
                saturation = st.slider("Saturation", -100, 100, 0)
            
            if blur > 0 or saturation != 0:
                edited = image
                if blur > 0:
                    edited = apply_blur(edited, blur)
                if saturation != 0:
                    edited = apply_saturation(edited, saturation)
                st.image(edited, use_column_width=True)
        
        with tab3:
            rotation = st.slider("Rotation", -180, 180, 0)
            if rotation != 0:
                edited = apply_rotation(image, rotation)
                st.image(edited, use_column_width=True)
        
        with tab4:
            col1, col2 = st.columns(2)
            with col1:
                if st.button("💾 Save to Drive", use_container_width=True):
                    st.success("✅ Saved")
            with col2:
                buf = io.BytesIO()
                image.save(buf, format="PNG")
                st.download_button(
                    "⬇️ Download",
                    buf.getvalue(),
                    file_name=img['name'],
                    mime="image/png",
                    use_container_width=True
                )

# Page: Task History
elif page == "📊 History":
    st.title("📊 Task History")
    
    if not st.session_state.task_history:
        st.info("No tasks yet")
    else:
        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            filter_model = st.selectbox("Filter Model", ["All", "bytedance/seedream-v4-edit", "qwen/image-edit"])
        with col2:
            filter_status = st.selectbox("Filter Status", ["All", "waiting", "success", "fail"])
        with col3:
            st.write("")
            st.write("")
            if st.button("🗑️ Clear", use_container_width=True):
                st.session_state.task_history = []
                st.rerun()
        
        st.markdown("---")
        
        filtered = st.session_state.task_history
        if filter_model != "All":
            filtered = [t for t in filtered if t.get("model") == filter_model]
        if filter_status != "All":
            filtered = [t for t in filtered if t.get("status") == filter_status]
        
        for i, task in enumerate(reversed(filtered)):
            with st.expander(f"Task {len(filtered) - i}: {task['model']} - {task['status'].upper()}"):
                col1, col2 = st.columns([2, 1])
                with col1:
                    st.markdown(f"**Task ID:** `{task['task_id']}`")
                    st.markdown(f"**Model:** {task['model']}")
                    st.markdown(f"**Time:** {task['timestamp']}")
                with col2:
                    status_emoji = {"waiting": "🟡", "success": "🟢", "fail": "🔴"}
                    st.markdown(f"### {status_emoji.get(task['status'], '⚪')} {task['status'].upper()}")
                
                if st.button(f"🔄 Check", key=f"check_{i}"):
                    result = check_task_status(st.session_state.api_key, task['task_id'])
                    if result["success"]:
                        st.json(result["data"])

# Page: Documentation
elif page == "📖 Docs":
    st.title("📖 Documentation")
    
    tab1, tab2, tab3 = st.tabs(["SeedDream V4", "Qwen Edit", "API"])
    
    with tab1:
        st.markdown("""
        ## SeedDream V4 Edit
        
        Advanced image editing with multiple inputs and high resolution output.
        
        ### Features
        - Multi-image input (up to 10 images)
        - Multiple aspect ratios
        - Up to 4K resolution
        - Batch generation (1-6 images)
        
        ### Best Practices
        1. Use detailed, descriptive prompts
        2. Start with 1K resolution for testing
        3. Use higher resolutions for final output
        4. Batch similar prompts together
        """)
    
    with tab2:
        st.markdown("""
        ## Qwen Image Edit
        
        Fast and precise image editing with fine-tuned control.
        
        ### Features
        - Single image editing
        - Acceleration options (none, regular, high)
        - Fine-tuned parameters
        - Safety checker
        
        ### Parameters
        - **Inference Steps**: 2-49 (higher = better quality)
        - **Guidance Scale**: 0-20 (how closely to follow prompt)
        - **Acceleration**: Speed up generation
        """)
    
    with tab3:
        st.markdown("""
        ## API Usage
        
        ### Authentication
        Use your API key in the Authorization header:
        ```
        Authorization: Bearer YOUR_API_KEY
        ```
        
        ### Create Task
        ```
        POST /api/v1/jobs/createTask
        {
            "model": "bytedance/seedream-v4-edit",
            "input": {...}
        }
        ```
        
        ### Check Status
        ```
        GET /api/v1/jobs/recordInfo?taskId=TASK_ID
        ```
        """)

st.markdown("---")
st.markdown("<center>🎨 AI Image Editor Pro | Powered by Streamlit Cloud</center>", unsafe_allow_html=True)
