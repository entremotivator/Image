import streamlit as st
import requests
import json
import time
import io
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

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
        }
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
    """Download image from URL and upload to Google Drive."""
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
            fields='id, webViewLink, webContentLink'
        ).execute()
        
        # Update stats
        st.session_state.stats['uploaded_images'] += 1
        
        return {
            'file_id': file.get('id'),
            'file_name': file_name,
            'web_link': file.get('webViewLink'),
            'content_link': file.get('webContentLink'),
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
            fields='files(id, name, webContentLink, webViewLink, createdTime, size)',
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
# Image Processing Functions
# ============================================================================

def apply_brightness_contrast(image, brightness=0, contrast=0):
    """Apply brightness and contrast adjustments."""
    img_array = np.array(image).astype(float) / 255.0
    img_array = img_array * (1 + contrast / 100)
    img_array = img_array + (brightness / 100)
    img_array = np.clip(img_array, 0, 1)
    return PILImage.fromarray((img_array * 255).astype(np.uint8))

def apply_saturation(image, saturation=0):
    """Apply saturation adjustment."""
    img_array = np.array(image)
    hsv = PILImage.fromarray(img_array).convert('HSV')
    h, s, v = hsv.split()
    s_array = np.array(s).astype(float)
    s_array = s_array * (1 + saturation / 100)
    s_array = np.clip(s_array, 0, 255)
    s = PILImage.fromarray(s_array.astype(np.uint8))
    hsv = PILImage.merge('HSV', (h, s, v))
    return hsv.convert('RGB')

# ============================================================================
# Sidebar Configuration
# ============================================================================

with st.sidebar:
    st.markdown("# 🎨 AI Image Editor Pro")
    st.markdown("---")
    
    # API Configuration
    st.header("⚙️ API Configuration")
    
    api_key_input = st.text_input(
        "API Key",
        type="password",
        value=st.session_state.api_key,
        help="Enter your KIE.AI API key"
    )
    
    if api_key_input:
        st.session_state.api_key = api_key_input
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
            help="Upload your Google service account credentials"
        )
        
        if uploaded_file is not None:
            try:
                service_account_json = json.load(uploaded_file)
                success, message = authenticate_with_service_account(service_account_json)
                
                if success:
                    st.session_state.service_account_info = service_account_json
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
            st.success("✅ History cleared")
            st.rerun()

# ============================================================================
# Main Navigation
# ============================================================================

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🏠 Home",
    "🎨 SeedDream V4",
    "✨ Qwen Edit",
    "📚 Library",
    "📊 History",
    "📖 Documentation"
])

# ============================================================================
# Tab: Home
# ============================================================================

with tab1:
    st.title("🎨 AI Image Editor Pro")
    st.markdown("### Professional AI-powered image generation and editing")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        <div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; border-radius: 15px; color: white;'>
            <h2>🎨 SeedDream V4 Edit</h2>
            <p style='font-size: 16px;'>Professional-grade image generation</p>
            <ul style='font-size: 14px;'>
                <li>✨ Multi-image input (up to 10)</li>
                <li>📐 Multiple aspect ratios</li>
                <li>🎯 Up to 4K resolution</li>
                <li>🔢 Batch generation (1-6 images)</li>
                <li>⚡ Fast processing</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div style='background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); padding: 30px; border-radius: 15px; color: white;'>
            <h2>✨ Qwen Image Edit</h2>
            <p style='font-size: 16px;'>Precise image editing control</p>
            <ul style='font-size: 14px;'>
                <li>🖼️ Single image focus</li>
                <li>⚙️ Advanced parameters</li>
                <li>🚀 Acceleration modes</li>
                <li>🎛️ Fine-tuned control</li>
                <li>🛡️ Safety features</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    st.subheader("🚀 Quick Start Guide")
    
    with st.expander("1️⃣ Setup API Key", expanded=True):
        st.markdown("""
        - Go to [KIE.AI](https://kie.ai/api-key) to get your API key
        - Enter the API key in the sidebar
        - Your key is stored securely in the session
        """)
    
    with st.expander("2️⃣ Connect Google Drive"):
        st.markdown("""
        - Create a Google Cloud Project
        - Enable Google Drive API
        - Create a service account
        - Download the JSON credentials
        - Upload the JSON file in the sidebar
        - Enable auto-upload for automatic image saving
        """)
    
    with st.expander("3️⃣ Generate Images"):
        st.markdown("""
        - Choose SeedDream V4 or Qwen Edit
        - Enter your creative prompt
        - Configure advanced settings
        - Click Generate
        - Images auto-upload to Google Drive (if enabled)
        """)
    
    st.markdown("---")
    
    # Recent Activity
    st.subheader("📈 Recent Activity")
    
    if st.session_state.task_history:
        recent_tasks = st.session_state.task_history[-5:][::-1]
        
        for task in recent_tasks:
            status_color = {
                'success': '#28a745',
                'waiting': '#ffc107',
                'fail': '#dc3545'
            }.get(task.get('status', 'waiting'), '#6c757d')
            
            st.markdown(f"""
            <div style='background-color: #f8f9fa; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid {status_color};'>
                <strong>Task ID:</strong> {task['task_id'][:20]}...<br>
                <strong>Model:</strong> {task['model'].split('/')[-1]}<br>
                <strong>Status:</strong> <span style='color: {status_color};'>{task['status'].upper()}</span><br>
                <strong>Time:</strong> {task['timestamp']}
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No tasks yet. Start generating!")

# ============================================================================
# Tab: SeedDream V4
# ============================================================================

with tab2:
    st.title("🎨 SeedDream V4 Edit")
    st.markdown("Professional image generation with multi-input support")
    
    # Preset Templates
    presets = {
        "Custom": {},
        "Professional Product": {
            "prompt": "Professional product photography with studio lighting, clean white background, 8K quality, commercial photography",
            "image_size": "square_hd",
            "image_resolution": "2K",
            "max_images": 4
        },
        "Brand Identity": {
            "prompt": "Modern brand showcase with elegant design, premium aesthetic, professional presentation, high-end commercial",
            "image_size": "landscape_16_9",
            "image_resolution": "2K",
            "max_images": 3
        },
        "Fashion Editorial": {
            "prompt": "High fashion editorial photography, professional lighting, magazine quality, contemporary style, elegant composition",
            "image_size": "portrait_16_9",
            "image_resolution": "2K",
            "max_images": 4
        },
        "Creative Art": {
            "prompt": "Creative artistic interpretation, unique style, professional quality, innovative design, contemporary art",
            "image_size": "square_hd",
            "image_resolution": "4K",
            "max_images": 2
        },
    }
    
    col1, col2 = st.columns([2, 1])
    
    with col2:
        preset = st.selectbox("📋 Template", list(presets.keys()))
        
        if preset != "Custom":
            if st.button("📥 Load Template", use_container_width=True):
                st.success(f"✅ Loaded: {preset}")
    
    st.markdown("---")
    
    col1, col2 = st.columns([3, 2])
    
    with col1:
        st.subheader("📝 Generation Settings")
        
        preset_data = presets.get(preset, {})
        
        prompt = st.text_area(
            "Creative Prompt",
            value=preset_data.get("prompt", ""),
            height=150,
            max_chars=5000,
            help="Describe in detail what you want to create or how to edit the image",
            placeholder="Example: Create a modern t-shirt mockup with professional lighting and clean background..."
        )
        
        st.markdown("##### 🖼️ Input Images")
        
        num_images = st.number_input(
            "Number of input images",
            min_value=1,
            max_value=10,
            value=1,
            help="Provide multiple reference images for better results"
        )
        
        image_urls = []
        cols = st.columns(2)
        
        for i in range(num_images):
            col_idx = i % 2
            with cols[col_idx]:
                url = st.text_input(
                    f"Image URL {i+1}",
                    key=f"seed_img_{i}",
                    value="https://file.aiquickdraw.com/custom-page/akr/section-images/1757930552966e7f2on7s.png" if i == 0 else "",
                    help="Direct URL to the image"
                )
                if url:
                    image_urls.append(url)
                    try:
                        st.image(url, width=200)
                    except:
                        st.warning("⚠️ Cannot preview image")
        
        with st.expander("🎛️ Advanced Configuration", expanded=True):
            col_a, col_b, col_c = st.columns(3)
            
            with col_a:
                image_size = st.selectbox(
                    "Aspect Ratio",
                    ["square", "square_hd", "portrait_4_3", "portrait_16_9", "landscape_4_3", "landscape_16_9"],
                    index=1,
                    help="Output image dimensions"
                )
            
            with col_b:
                image_resolution = st.selectbox(
                    "Resolution",
                    ["1K", "2K", "4K"],
                    index=preset_data.get("image_resolution", "1K") if preset != "Custom" else 0,
                    help="Higher resolution = better quality but slower"
                )
            
            with col_c:
                max_images = st.slider(
                    "Batch Size",
                    1, 6,
                    preset_data.get("max_images", 1) if preset != "Custom" else 1,
                    help="Generate multiple variations at once"
                )
            
            st.info(f"💡 Estimated generation time: {5 + max_images * 3}-{10 + max_images * 5} seconds")
    
    with col2:
        st.subheader("🚀 Generation")
        
        st.markdown("##### Preview Settings")
        st.markdown(f"""
        - **Aspect:** `{image_size}`
        - **Resolution:** `{image_resolution}`
        - **Batch:** `{max_images} image(s)`
        - **Auto-upload:** `{'✅ ON' if st.session_state.auto_upload else '❌ OFF'}`
        """)
        
        st.markdown("---")
        
        generate_btn = st.button(
            "🚀 Generate Images",
            type="primary",
            use_container_width=True,
            disabled=not st.session_state.api_key
        )
        
        if st.button("🔄 Reset Form", use_container_width=True):
            st.rerun()
        
        st.markdown("---")
        
        if st.session_state.authenticated:
            st.success("☁️ Auto-upload: Active")
        else:
            st.warning("☁️ Auto-upload: Inactive")
    
    if generate_btn:
        if not st.session_state.api_key:
            st.error("⚠️ Please configure API key in sidebar")
        elif not prompt:
            st.error("⚠️ Please enter a prompt")
        elif not image_urls:
            st.error("⚠️ Please provide at least one image URL")
        else:
            st.markdown("---")
            st.subheader("⏳ Processing")
            
            with st.spinner("🎨 Creating generation task..."):
                input_params = {
                    "prompt": prompt,
                    "image_urls": image_urls,
                    "image_size": image_size,
                    "image_resolution": image_resolution,
                    "max_images": max_images
                }
                
                result = create_task(
                    st.session_state.api_key,
                    "bytedance/seedream-v4-edit",
                    input_params
                )
                
                if result["success"]:
                    task_id = result["task_id"]
                    
                    task_record = {
                        "task_id": task_id,
                        "model": "bytedance/seedream-v4-edit",
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "status": "waiting",
                        "prompt": prompt[:100] + "..." if len(prompt) > 100 else prompt,
                        "settings": input_params
                    }
                    
                    st.session_state.task_history.append(task_record)
                    
                    st.success(f"✅ Task created successfully!")
                    st.code(task_id, language=None)
                    
                    # Auto-poll for completion
                    with st.spinner("🔄 Processing images... This may take 30-120 seconds..."):
                        poll_result = poll_task_until_complete(
                            st.session_state.api_key,
                            task_id,
                            max_attempts=60,
                            delay=2
                        )
                    
                    if poll_result["success"]:
                        task_data = poll_result["data"]
                        
                        # Update task status
                        for task in st.session_state.task_history:
                            if task["task_id"] == task_id:
                                task["status"] = "success"
                                break
                        
                        st.session_state.stats['successful_tasks'] += 1
                        
                        # Parse results
                        result_json = json.loads(task_data.get("resultJson", "{}"))
                        result_urls = result_json.get("resultUrls", [])
                        
                        if result_urls:
                            st.success(f"🎉 Generated {len(result_urls)} image(s) successfully!")
                            
                            # Display results
                            st.subheader("🖼️ Generated Images")
                            
                            cols = st.columns(min(len(result_urls), 3))
                            
                            for idx, url in enumerate(result_urls):
                                col = cols[idx % len(cols)]
                                
                                with col:
                                    st.image(url, use_container_width=True, caption=f"Image {idx + 1}")
                                    
                                    # Download button
                                    try:
                                        img_response = requests.get(url)
                                        st.download_button(
                                            "⬇️ Download",
                                            img_response.content,
                                            file_name=f"seedream_{task_id[:8]}_{idx}.png",
                                            mime="image/png",
                                            key=f"download_seed_{idx}",
                                            use_container_width=True
                                        )
                                    except:
                                        st.error("Download failed")
                                    
                                    # Auto-upload to Google Drive
                                    if st.session_state.authenticated and st.session_state.auto_upload:
                                        with st.spinner("📤 Uploading..."):
                                            file_name = f"SeedDream_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{idx}.png"
                                            upload_result = upload_to_gdrive(url, file_name, task_id)
                                            
                                            if upload_result:
                                                st.success("✅ Uploaded to Drive")
                                                st.session_state.generated_images.append(upload_result)
                                            else:
                                                st.warning("⚠️ Upload failed")
                                    elif st.session_state.authenticated:
                                        if st.button("📤 Upload", key=f"manual_upload_{idx}", use_container_width=True):
                                            file_name = f"SeedDream_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{idx}.png"
                                            upload_result = upload_to_gdrive(url, file_name, task_id)
                                            if upload_result:
                                                st.success("✅ Uploaded!")
                                                st.rerun()
                            
                            # Show task details
                            with st.expander("📋 Task Details"):
                                st.json({
                                    "task_id": task_id,
                                    "state": task_data.get("state"),
                                    "cost_time": f"{task_data.get('costTime', 0)}s",
                                    "complete_time": datetime.fromtimestamp(
                                        task_data.get('completeTime', 0) / 1000
                                    ).strftime("%Y-%m-%d %H:%M:%S") if task_data.get('completeTime') else "N/A",
                                    "images_generated": len(result_urls)
                                })
                        else:
                            st.warning("⚠️ No images returned")
                    else:
                        st.error(f"❌ Task failed: {poll_result.get('error', 'Unknown error')}")
                        st.session_state.stats['failed_tasks'] += 1
                        
                        # Update task status
                        for task in st.session_state.task_history:
                            if task["task_id"] == task_id:
                                task["status"] = "fail"
                                break
                else:
                    st.error(f"❌ Task creation failed: {result['error']}")
                    st.session_state.stats['failed_tasks'] += 1

# ============================================================================
# Tab: Qwen Image Edit
# ============================================================================

with tab3:
    st.title("✨ Qwen Image Edit")
    st.markdown("Fast and precise single-image editing with advanced controls")
    
    col1, col2 = st.columns([3, 2])
    
    with col1:
        st.subheader("📝 Edit Configuration")
        
        prompt = st.text_area(
            "Edit Instructions",
            height=120,
            max_chars=2000,
            help="Describe precisely what changes you want to make",
            placeholder="Example: Change the background to a beach sunset, add professional lighting..."
        )
        
        image_url = st.text_input(
            "Image URL",
            value="https://file.aiquickdraw.com/custom-page/akr/section-images/1757930552966e7f2on7s.png",
            help="Direct URL to the image you want to edit"
        )
        
        if image_url:
            with st.expander("🖼️ Preview Input Image", expanded=True):
                try:
                    st.image(image_url, use_container_width=True)
                except:
                    st.error("❌ Cannot load image preview")
        
        with st.expander("🎛️ Advanced Parameters", expanded=True):
            col_a, col_b = st.columns(2)
            
            with col_a:
                acceleration = st.selectbox(
                    "Processing Speed",
                    ["none", "regular", "high"],
                    index=1,
                    help="Higher acceleration = faster but may reduce quality slightly"
                )
                
                image_size = st.selectbox(
                    "Output Size",
                    ["square", "square_hd", "portrait_4_3", "portrait_16_9", "landscape_4_3", "landscape_16_9"],
                    index=0
                )
                
                enable_safety_checker = st.checkbox(
                    "Safety Checker",
                    value=True,
                    help="Filter inappropriate content"
                )
            
            with col_b:
                num_inference_steps = st.slider(
                    "Quality Steps",
                    2, 49, 25,
                    help="More steps = higher quality but slower"
                )
                
                guidance_scale = st.slider(
                    "Prompt Strength",
                    0.0, 20.0, 4.0, 0.5,
                    help="How closely to follow the prompt"
                )
                
                seed = st.number_input(
                    "Random Seed",
                    min_value=-1,
                    max_value=999999999,
                    value=-1,
                    help="-1 for random, or set specific seed for reproducibility"
                )
            
            st.info(f"💡 Estimated processing: {5 + num_inference_steps // 5}-{10 + num_inference_steps // 3} seconds")
    
    with col2:
        st.subheader("🚀 Generation")
        
        st.markdown("##### Configuration Summary")
        st.markdown(f"""
        - **Speed:** `{acceleration}`
        - **Size:** `{image_size}`
        - **Steps:** `{num_inference_steps}`
        - **Guidance:** `{guidance_scale}`
        - **Safety:** `{'✅' if enable_safety_checker else '❌'}`
        """)
        
        st.markdown("---")
        
        generate_btn = st.button(
            "✨ Edit Image",
            type="primary",
            use_container_width=True,
            disabled=not st.session_state.api_key
        )
        
        if st.button("🔄 Reset", use_container_width=True):
            st.rerun()
    
    if generate_btn:
        if not st.session_state.api_key:
            st.error("⚠️ Please configure API key")
        elif not prompt:
            st.error("⚠️ Please enter edit instructions")
        elif not image_url:
            st.error("⚠️ Please provide image URL")
        else:
            st.markdown("---")
            st.subheader("⏳ Processing")
            
            with st.spinner("✨ Creating edit task..."):
                input_params = {
                    "prompt": prompt,
                    "image_url": image_url,
                    "acceleration": acceleration,
                    "image_size": image_size,
                    "num_inference_steps": num_inference_steps,
                    "guidance_scale": guidance_scale,
                    "enable_safety_checker": enable_safety_checker
                }
                
                if seed >= 0:
                    input_params["seed"] = seed
                
                result = create_task(
                    st.session_state.api_key,
                    "qwen/image-edit",
                    input_params
                )
                
                if result["success"]:
                    task_id = result["task_id"]
                    
                    task_record = {
                        "task_id": task_id,
                        "model": "qwen/image-edit",
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "status": "waiting",
                        "prompt": prompt[:100] + "..." if len(prompt) > 100 else prompt,
                        "settings": input_params
                    }
                    
                    st.session_state.task_history.append(task_record)
                    st.success("✅ Task created!")
                    st.code(task_id)
                    
                    with st.spinner("🔄 Processing edit..."):
                        poll_result = poll_task_until_complete(
                            st.session_state.api_key,
                            task_id,
                            max_attempts=40,
                            delay=2
                        )
                    
                    if poll_result["success"]:
                        task_data = poll_result["data"]
                        
                        for task in st.session_state.task_history:
                            if task["task_id"] == task_id:
                                task["status"] = "success"
                                break
                        
                        st.session_state.stats['successful_tasks'] += 1
                        
                        result_json = json.loads(task_data.get("resultJson", "{}"))
                        result_urls = result_json.get("resultUrls", [])
                        
                        if result_urls:
                            st.success("🎉 Edit completed successfully!")
                            
                            st.subheader("🖼️ Result")
                            
                            col_before, col_after = st.columns(2)
                            
                            with col_before:
                                st.markdown("**Before**")
                                st.image(image_url, use_container_width=True)
                            
                            with col_after:
                                st.markdown("**After**")
                                for idx, url in enumerate(result_urls):
                                    st.image(url, use_container_width=True)
                                    
                                    try:
                                        img_response = requests.get(url)
                                        st.download_button(
                                            "⬇️ Download Result",
                                            img_response.content,
                                            file_name=f"qwen_edit_{task_id[:8]}.png",
                                            mime="image/png",
                                            use_container_width=True
                                        )
                                    except:
                                        st.error("Download failed")
                                    
                                    if st.session_state.authenticated:
                                        if st.button("📤 Upload to Drive", use_container_width=True):
                                            file_name = f"QwenEdit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                                            upload_result = upload_to_gdrive(url, file_name, task_id)
                                            if upload_result:
                                                st.success("✅ Uploaded!")
                                                st.rerun()
                            
                            with st.expander("📋 Processing Details"):
                                st.json({
                                    "task_id": task_id,
                                    "processing_time": f"{task_data.get('costTime', 0)}s",
                                    "parameters": input_params
                                })
                    else:
                        st.error(f"❌ Edit failed: {poll_result.get('error')}")
                        st.session_state.stats['failed_tasks'] += 1
                else:
                    st.error(f"❌ Task creation failed: {result['error']}")

# ============================================================================
# Tab: Library
# ============================================================================

with tab4:
    st.title("📚 Image Library")
    st.markdown("Manage all your generated and uploaded images")
    
    if not st.session_state.authenticated:
        st.warning("⚠️ Please authenticate with Google Drive in the sidebar first")
        st.info("Upload your service account JSON file to connect to Google Drive")
    else:
        col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
        
        with col1:
            search_query = st.text_input("🔍 Search by filename")
        
        with col2:
            sort_by = st.selectbox("📊 Sort by", ["Newest First", "Oldest First", "Name A-Z", "Name Z-A"])
        
        with col3:
            view_mode = st.selectbox("👁️ View", ["Grid", "List"])
        
        with col4:
            st.write("")
            if st.button("🔄 Refresh", use_container_width=True):
                with st.spinner("Loading..."):
                    st.session_state.library_images = list_gdrive_images()
                    st.success("✅")
        
        st.markdown("---")
        
        # Load images if not loaded
        if not st.session_state.library_images:
            with st.spinner("Loading library..."):
                st.session_state.library_images = list_gdrive_images()
        
        images = st.session_state.library_images
        
        # Apply search filter
        if search_query:
            images = [img for img in images if search_query.lower() in img['name'].lower()]
        
        # Apply sorting
        if sort_by == "Oldest First":
            images = sorted(images, key=lambda x: x.get('createdTime', ''))
        elif sort_by == "Name A-Z":
            images = sorted(images, key=lambda x: x['name'])
        elif sort_by == "Name Z-A":
            images = sorted(images, key=lambda x: x['name'], reverse=True)
        else:  # Newest First
            images = sorted(images, key=lambda x: x.get('createdTime', ''), reverse=True)
        
        if not images:
            st.info("📭 No images found in your library")
            st.markdown("Generate images using **SeedDream V4** or **Qwen Edit** tabs")
        else:
            st.success(f"Found **{len(images)}** image(s)")
            
            if view_mode == "Grid":
                # Grid view
                cols = st.columns(4)
                
                for idx, img in enumerate(images):
                    col = cols[idx % 4]
                    
                    with col:
                        st.markdown(f"""
                        <div class='image-card'>
                        """, unsafe_allow_html=True)
                        
                        try:
                            st.image(img.get('webContentLink', ''), use_container_width=True)
                        except:
                            st.error("Preview unavailable")
                        
                        st.caption(img['name'][:25] + "..." if len(img['name']) > 25 else img['name'])
                        
                        # Action buttons
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            if img.get('webViewLink'):
                                st.markdown(f"[🔗]({img['webViewLink']})")
                        
                        with col2:
                            if img.get('webContentLink'):
                                st.markdown(f"[⬇️]({img['webContentLink']})")
                        
                        with col3:
                            if st.button("🗑️", key=f"del_grid_{img['id']}", use_container_width=True):
                                if delete_gdrive_file(img['id']):
                                    st.success("✅")
                                    time.sleep(0.5)
                                    st.rerun()
                        
                        st.markdown("</div>", unsafe_allow_html=True)
            
            else:
                # List view
                for img in images:
                    with st.expander(f"📄 {img['name']}", expanded=False):
                        col1, col2 = st.columns([1, 2])
                        
                        with col1:
                            try:
                                st.image(img.get('webContentLink', ''), use_container_width=True)
                            except:
                                st.error("Preview unavailable")
                        
                        with col2:
                            st.markdown(f"**Name:** {img['name']}")
                            st.markdown(f"**Created:** {img.get('createdTime', 'N/A')}")
                            st.markdown(f"**Size:** {int(img.get('size', 0)) / 1024:.1f} KB")
                            st.markdown(f"**ID:** `{img['id']}`")
                            
                            col_a, col_b, col_c = st.columns(3)
                            
                            with col_a:
                                if img.get('webViewLink'):
                                    st.markdown(f"[🔗 Open]({img['webViewLink']})")
                            
                            with col_b:
                                if img.get('webContentLink'):
                                    st.markdown(f"[⬇️ Download]({img['webContentLink']})")
                            
                            with col_c:
                                if st.button("🗑️ Delete", key=f"del_list_{img['id']}"):
                                    if delete_gdrive_file(img['id']):
                                        st.success("✅ Deleted")
                                        time.sleep(0.5)
                                        st.rerun()

# ============================================================================
# Tab: History
# ============================================================================

with tab5:
    st.title("📊 Task History")
    st.markdown("View and manage all your generation tasks")
    
    if not st.session_state.task_history:
        st.info("📭 No tasks in history")
        st.markdown("Start generating images to see your task history here")
    else:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            filter_model = st.selectbox(
                "🎨 Model",
                ["All Models", "SeedDream V4", "Qwen Edit"]
            )
        
        with col2:
            filter_status = st.selectbox(
                "📊 Status",
                ["All Status", "Success", "Waiting", "Failed"]
            )
        
        with col3:
            sort_order = st.selectbox(
                "📅 Order",
                ["Newest First", "Oldest First"]
            )
        
        with col4:
            st.write("")
            if st.button("🗑️ Clear All", use_container_width=True):
                if st.checkbox("⚠️ Confirm deletion"):
                    st.session_state.task_history = []
                    st.success("✅ History cleared")
                    st.rerun()
        
        st.markdown("---")
        
        # Filter tasks
        filtered = st.session_state.task_history.copy()
        
        if filter_model != "All Models":
            model_map = {
                "SeedDream V4": "bytedance/seedream-v4-edit",
                "Qwen Edit": "qwen/image-edit"
            }
            filtered = [t for t in filtered if t.get("model") == model_map.get(filter_model)]
        
        if filter_status != "All Status":
            status_map = {
                "Success": "success",
                "Waiting": "waiting",
                "Failed": "fail"
            }
            filtered = [t for t in filtered if t.get("status") == status_map.get(filter_status)]
        
        # Sort tasks
        if sort_order == "Oldest First":
            filtered = filtered
        else:
            filtered = filtered[::-1]
        
        st.write(f"Showing **{len(filtered)}** of **{len(st.session_state.task_history)}** tasks")
        
        # Display tasks
        for i, task in enumerate(filtered):
            status_emoji = {
                "waiting": "🟡",
                "success": "🟢",
                "fail": "🔴"
            }
            
            status_class = {
                "waiting": "status-waiting",
                "success": "status-success",
                "fail": "status-fail"
            }
            
            model_short = task['model'].split('/')[-1]
            
            with st.expander(
                f"{status_emoji.get(task['status'], '⚪')} Task #{len(filtered) - i}: {model_short} - {task['status'].upper()}",
                expanded=False
            ):
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.markdown(f"**Task ID:** `{task['task_id']}`")
                    st.markdown(f"**Model:** {task['model']}")
                    st.markdown(f"**Created:** {task['timestamp']}")
                    
                    if 'prompt' in task:
                        st.markdown(f"**Prompt:** {task['prompt']}")
                
                with col2:
                    st.markdown(f"""
                    <div style='text-align: center; padding: 20px;'>
                        <span class='status-badge {status_class.get(task['status'], '')}'>{task['status'].upper()}</span>
                    </div>
                    """, unsafe_allow_html=True)
                
                # Check status button
                if st.button(f"🔄 Check Status", key=f"check_{task['task_id']}_{i}"):
                    with st.spinner("Checking..."):
                        result = check_task_status(st.session_state.api_key, task['task_id'])
                        
                        if result["success"]:
                            task_data = result["data"]
                            st.json(task_data)
                            
                            # Update task status
                            task['status'] = task_data.get('state', task['status'])
                        else:
                            st.error(f"❌ Error: {result['error']}")
                
                # Show settings if available
                if 'settings' in task:
                    with st.expander("⚙️ View Settings"):
                        st.json(task['settings'])

# ============================================================================
# Tab: Documentation
# ============================================================================

with tab6:
    st.title("📖 Documentation")
    st.markdown("Complete guide to using AI Image Editor Pro")
    
    doc_tab1, doc_tab2, doc_tab3, doc_tab4 = st.tabs([
        "🚀 Quick Start",
        "🎨 SeedDream V4",
        "✨ Qwen Edit",
        "☁️ Google Drive"
    ])
    
    with doc_tab1:
        st.markdown("""
        ## 🚀 Quick Start Guide
        
        ### Step 1: Configure API Key
        
        1. Visit [KIE.AI API Portal](https://kie.ai/api-key)
        2. Sign up or log in to your account
        3. Generate a new API key
        4. Copy the API key
        5. Paste it in the sidebar under "API Configuration"
        
        ---
        
        ### Step 2: Set Up Google Drive (Optional but Recommended)
        
        #### Create Service Account:
        
        1. Go to [Google Cloud Console](https://console.cloud.google.com)
        2. Create a new project or select existing
        3. Enable **Google Drive API**
        4. Go to "IAM & Admin" → "Service Accounts"
        5. Click "Create Service Account"
        6. Give it a name (e.g., "AI Image Editor")
        7. Grant role: "Editor" or "Drive File Access"
        8. Click "Done"
        
        #### Download Credentials:
        
        1. Click on your service account
        2. Go to "Keys" tab
        3. Click "Add Key" → "Create New Key"
        4. Choose JSON format
        5. Download the JSON file
        6. Upload this file in the sidebar
        
        ---
        
        ### Step 3: Generate Your First Image
        
        1. Go to **SeedDream V4** or **Qwen Edit** tab
        2. Choose a preset or create custom settings
        3. Enter a creative prompt
        4. Provide image URL(s)
        5. Click "Generate"
        6. Wait for results (auto-uploaded if Drive is connected)
        
        ---
        
        ### Step 4: Manage Your Library
        
        1. Go to **Library** tab
        2. Browse all generated images
        3. Search, sort, and filter
        4. Download or delete images
        
        """)
    
    with doc_tab2:
        st.markdown("""
        ## 🎨 SeedDream V4 Edit
        
        ### Overview
        
        SeedDream V4 is a professional-grade image generation model that supports:
        - Multiple input images (up to 10)
        - High resolution output (up to 4K)
        - Batch generation (1-6 images per task)
        - Multiple aspect ratios
        
        ---
        
        ### Parameters Explained
        
        #### Prompt
        - **Type:** Text (max 5000 characters)
        - **Purpose:** Describe what you want to create or how to edit
        - **Tips:** 
          - Be specific and detailed
          - Include style keywords (e.g., "professional", "artistic")
          - Mention lighting, composition, mood
        
        #### Image URLs
        - **Count:** 1-10 images
        - **Format:** Direct image URLs (PNG, JPG, WebP)
        - **Purpose:** Reference images for generation
        - **Tips:**
          - Use high-quality source images
          - Multiple angles work best
          - Consistent lighting helps
        
        #### Image Size (Aspect Ratio)
        - `square` - 1:1 ratio (1024x1024)
        - `square_hd` - 1:1 HD (1536x1536)
        - `portrait_4_3` - 3:4 ratio (768x1024)
        - `portrait_16_9` - 9:16 ratio (576x1024)
        - `landscape_4_3` - 4:3 ratio (1024x768)
        - `landscape_16_9` - 16:9 ratio (1024x576)
        
        #### Resolution
        - **1K** - Fast, good for testing (≈1024px)
        - **2K** - Balanced quality/speed (≈2048px)
        - **4K** - Maximum quality, slower (≈4096px)
        
        #### Max Images
        - Generate 1-6 variations per task
        - More images = longer processing time
        - Useful for comparing different results
        
        ---
        
        ### Best Practices
        
        1. **Start Small:** Test with 1K resolution first
        2. **Refine Prompts:** Iterate based on results
        3. **Use References:** Multiple input images improve quality
        4. **Batch Similar:** Generate variations together
        5. **Save Settings:** Note what works well
        
        ---
        
        ### Example Prompts
        
        **Product Photography:**
        ```
        Professional product photography of [item], studio lighting,
        clean white background, 8K quality, commercial photography,
        sharp focus, detailed texture, professional color grading
        ```
        
        **Brand Design:**
        ```
        Modern brand identity design, minimalist aesthetic,
        professional presentation, premium quality, elegant composition,
        contemporary style, high-end commercial photography
        ```
        
        **Fashion Editorial:**
        ```
        High fashion editorial photography, dramatic lighting,
        magazine quality, artistic composition, professional styling,
        contemporary fashion, elegant presentation, vibrant colors
        ```
        """)
    
    with doc_tab3:
        st.markdown("""
        ## ✨ Qwen Image Edit
        
        ### Overview
        
        Qwen Image Edit specializes in precise, fast image editing with fine-grained control.
        Perfect for specific edits and modifications.
        
        ---
        
        ### Parameters Explained
        
        #### Prompt (Edit Instructions)
        - **Type:** Text (max 2000 characters)
        - **Purpose:** Describe exact changes to make
        - **Tips:**
          - Be specific about what to change
          - Mention what to keep unchanged
          - Include style and quality keywords
        
        #### Image URL
        - **Count:** 1 image per task
        - **Format:** Direct URL to image
        - **Purpose:** Source image to edit
        
        #### Acceleration
        - **none** - Standard speed, maximum quality
        - **regular** - 2x faster, minimal quality loss
        - **high** - 3x faster, slight quality trade-off
        
        #### Image Size
        - Similar to SeedDream V4
        - Output matches selected aspect ratio
        - Original proportions preserved when possible
        
        #### Quality Steps (num_inference_steps)
        - **Range:** 2-49 steps
        - **Default:** 25 steps
        - **Effect:** More steps = better quality but slower
        - **Tips:**
          - 15-25 for most edits
          - 30-40 for complex changes
          - 40+ for maximum quality
        
        #### Guidance Scale
        - **Range:** 0.0-20.0
        - **Default:** 4.0
        - **Effect:** How closely to follow prompt
        - **Tips:**
          - 3.0-5.0 for natural results
          - 5.0-8.0 for stronger prompt adherence
          - 8.0+ for very specific changes
        
        #### Random Seed
        - **-1:** Random (different each time)
        - **0-999999999:** Specific seed
        - **Purpose:** Reproduce exact results
        - **Tip:** Save seed for results you like
        
        #### Safety Checker
        - Filters inappropriate content
        - Recommended to keep enabled
        - May block some artistic content
        
        ---
        
        ### Best Practices
        
        1. **Clear Instructions:** Be precise about changes
        2. **Incremental Edits:** Make small changes at a time
        3. **Test Settings:** Adjust guidance for desired effect
        4. **Save Seeds:** Record seeds for reproducible results
        5. **Quality Balance:** Use acceleration for speed when testing
        
        ---
        
        ### Example Edit Prompts
        
        **Background Change:**
        ```
        Change the background to a sunny beach at sunset,
        keep the subject unchanged, professional photography,
        natural lighting, seamless integration
        ```
        
        **Style Transfer:**
        ```
        Convert to oil painting style, impressionist technique,
        vibrant colors, artistic brushstrokes, maintain composition,
        professional art quality
        ```
        
        **Object Modification:**
        ```
        Replace the red car with a blue sports car,
        same angle and lighting, photorealistic, high detail,
        seamless integration, professional retouching
        ```
        """)
    
    with doc_tab4:
        st.markdown("""
        ## ☁️ Google Drive Integration
        
        ### Why Use Google Drive?
        
        - **Automatic Backup:** Never lose generated images
        - **Centralized Storage:** Access from anywhere
        - **Organized Library:** All images in one place
        - **Easy Sharing:** Share Drive links
        - **Version Control:** Keep all variations
        
        ---
        
        ### Setting Up Service Account
        
        #### Prerequisites
        - Google account
        - Google Cloud project (free tier available)
        
        #### Detailed Setup Steps
        
        **1. Create Google Cloud Project:**
        ```
        1. Go to: https://console.cloud.google.com
        2. Click "Select Project" → "New Project"
        3. Name: "AI Image Editor" (or your choice)
        4. Click "Create"
        ```
        
        **2. Enable Google Drive API:**
        ```
        1. In Cloud Console, go to "APIs & Services"
        2. Click "Enable APIs and Services"
        3. Search for "Google Drive API"
        4. Click "Enable"
        ```
        
        **3. Create Service Account:**
        ```
        1. Go to "IAM & Admin" → "Service Accounts"
        2. Click "Create Service Account"
        3. Name: "image-editor-service"
        4. Description: "Service account for AI Image Editor"
        5. Click "Create and Continue"
        ```
        
        **4. Grant Permissions:**
        ```
        1. Role: Select "Basic" → "Editor"
           OR
        2. Role: Select "Google Drive" → "Drive File Creator"
        3. Click "Continue" → "Done"
        ```
        
        **5. Create JSON Key:**
        ```
        1. Click on your service account email
        2. Go to "Keys" tab
        3. Click "Add Key" → "Create New Key"
        4. Select "JSON"
        5. Click "Create"
        6. JSON file downloads automatically
        ```
        
        **6. Upload to App:**
        ```
        1. In sidebar, find "Google Drive Setup"
        2. Click "Browse" under "Service Account JSON"
        3. Select downloaded JSON file
        4. App authenticates automatically
        5. Folder created: "AI_Image_Editor_Pro"
        ```
        
        ---
        
        ### Features
        
        #### Auto-Upload
        - Enable in sidebar after authentication
        - Generated images upload automatically
        - Saves time and ensures backup
        - Can toggle on/off anytime
        
        #### Manual Upload
        - Disable auto-upload for manual control
        - Upload button appears for each image
        - Choose which images to save
        
        #### Library Management
        - View all uploaded images
        - Search by filename
        - Sort by date or name
        - Delete unwanted images
        - Direct links to Google Drive
        
        ---
        
        ### Troubleshooting
        
        **Authentication Failed:**
        - Check JSON file is valid
        - Verify Drive API is enabled
        - Ensure service account has permissions
        
        **Upload Failed:**
        - Check internet connection
        - Verify Drive quota not exceeded
        - Re-authenticate if needed
        
        **Can't See Images:**
        - Click "Refresh" in Library
        - Check folder in Google Drive directly
        - Verify file permissions
        
        ---
        
        ### Security Notes
        
        - Service account credentials stored in session only
        - Not saved to disk
        - Re-upload JSON each session
        - Keep JSON file secure
        - Don't share service account credentials
        
        ---
        
        ### Quota Limits
        
        **Google Drive API (Free Tier):**
        - 10,000 queries per day
        - 1 billion queries per 100 seconds
        - Sufficient for normal use
        
        **Storage:**
        - 15 GB free with Google account
        - Images typically 1-5 MB each
        - Can store 3,000-15,000 images
        """)
    
    st.markdown("---")
    
    st.subheader("🔗 Additional Resources")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        ### Official Links
        - [KIE.AI Homepage](https://kie.ai)
        - [API Documentation](https://kie.ai/docs)
        - [Get API Key](https://kie.ai/api-key)
        - [Support](https://kie.ai/support)
        """)
    
    with col2:
        st.markdown("""
        ### Google Resources
        - [Cloud Console](https://console.cloud.google.com)
        - [Drive API Docs](https://developers.google.com/drive)
        - [Service Accounts Guide](https://cloud.google.com/iam/docs/service-accounts)
        """)

# ============================================================================
# Footer
# ============================================================================

st.markdown("---")
st.markdown("""
<div style='text-align: center; padding: 20px; color: #666;'>
    <p><strong>🎨 AI Image Editor Pro</strong></p>
    <p>Powered by KIE.AI | Built with Streamlit</p>
    <p>v2.0.0 | Enhanced Edition</p>
</div>
""", unsafe_allow_html=True)
