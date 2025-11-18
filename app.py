import streamlit as st
import requests
import json
import time
import io
from datetime import datetime
from typing import Optional

# Google Drive imports
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
except Exception:
    st.error("Missing Google API packages. Install: google-auth, google-auth-oauthlib, google-auth-httplib2, google-api-python-client")

# ============================================================================
# Configuration
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
    .stApp {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    }
    .main-header {
        background: white;
        padding: 2rem;
        border-radius: 15px;
        box-shadow: 0 8px 16px rgba(0,0,0,0.1);
        margin-bottom: 2rem;
    }
    .image-card {
        background: white;
        border-radius: 12px;
        padding: 1rem;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        transition: transform 0.2s;
    }
    .image-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 6px 20px rgba(0,0,0,0.2);
    }
    .success-badge {
        background: #10b981;
        color: white;
        padding: 0.5rem 1rem;
        border-radius: 20px;
        font-weight: bold;
        display: inline-block;
    }
    .back-button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 0.75rem 1.5rem;
        border-radius: 10px;
        border: none;
        font-weight: bold;
        cursor: pointer;
        transition: all 0.3s;
    }
    .back-button:hover {
        transform: scale(1.05);
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
    }
</style>
""", unsafe_allow_html=True)

BASE_URL = "https://api.kie.ai/api/v1/jobs"
SCOPES = ['https://www.googleapis.com/auth/drive.file']

# ============================================================================
# Session State Initialization
# ============================================================================

def init_session_state():
    """Initialize all session state variables."""
    defaults = {
        'api_key': "",
        'authenticated': False,
        'service': None,
        'gdrive_folder_id': None,
        'library_images': [],
        'task_history': [],
        'current_page': "Generate",
        'service_account_info': None,
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
            q="name='AI_Generated_Images' and mimeType='application/vnd.google-apps.folder' and trashed=false",
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
            'name': 'AI_Generated_Images',
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
        
        # Make the file publicly accessible
        permission = {
            'type': 'anyone',
            'role': 'reader'
        }
        st.session_state.service.permissions().create(
            fileId=file_id,
            body=permission
        ).execute()
        
        # Generate direct public URL for image display
        public_url = f"https://drive.google.com/uc?export=view&id={file_id}"
        
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

def list_gdrive_images():
    """List all images in Google Drive folder."""
    if not st.session_state.service:
        return []
    
    try:
        folder_id = st.session_state.gdrive_folder_id or create_app_folder()
        if not folder_id:
            return []
        
        results = st.session_state.service.files().list(
            q=f"'{folder_id}' in parents and trashed=false and (mimeType='image/png' or mimeType='image/jpeg')",
            spaces='drive',
            fields='files(id, name, webViewLink, createdTime)',
            pageSize=100,
            orderBy='createdTime desc'
        ).execute()
        
        files = results.get('files', [])
        
        # Add public URLs to each file
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

def create_task(api_key, model, input_params):
    """Create a generation task."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "input": input_params
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/createTask",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        data = response.json()
        if response.status_code == 200 and data.get("code") == 200:
            return {"success": True, "task_id": data["data"]["taskId"]}
        else:
            return {"success": False, "error": data.get('msg', 'Unknown error')}
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
        return {"success": False, "error": "Failed to check status"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def poll_task_until_complete(api_key, task_id, max_attempts=60, delay=2):
    """Poll task status until completion."""
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
                status_text.success("✅ Task completed successfully!")
                return {"success": True, "data": task_data}
            elif state == "fail":
                progress_bar.empty()
                status_text.error("❌ Task failed")
                return {"success": False, "error": task_data.get('failMsg', 'Unknown error')}
            
            time.sleep(delay)
    
    progress_bar.empty()
    status_text.warning("⏱️ Timeout reached")
    return {"success": False, "error": "Timeout"}

# ============================================================================
# Sidebar
# ============================================================================

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
    st.session_state.api_key = api_key
    
    if api_key:
        st.success("✅ API Key configured")
    else:
        st.warning("⚠️ Please enter API key")
    
    st.markdown("---")
    
    # Google Drive Setup
    st.header("☁️ Google Drive")
    
    if not st.session_state.authenticated:
        uploaded_file = st.file_uploader(
            "Upload Service Account JSON",
            type=['json'],
            help="Upload your Google service account credentials"
        )
        
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
                        st.success(f"✅ Folder ready")
                    st.rerun()
                else:
                    st.error(message)
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
    else:
        st.success("✅ Google Drive Connected")
        
        if st.button("🔄 Refresh Library", use_container_width=True):
            st.session_state.library_images = list_gdrive_images()
            st.success("Refreshed!")
        
        if st.button("🗑️ Disconnect", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.service = None
            st.session_state.service_account_info = None
            st.rerun()
    
    st.markdown("---")
    
    # Navigation
    st.header("📍 Navigation")
    
    if st.button("✨ Generate", use_container_width=True):
        st.session_state.current_page = "Generate"
        st.rerun()
    
    if st.button("📚 Library", use_container_width=True):
        st.session_state.current_page = "Library"
        st.rerun()
    
    if st.button("📋 History", use_container_width=True):
        st.session_state.current_page = "History"
        st.rerun()

# ============================================================================
# Pages
# ============================================================================

def display_generate_page():
    st.markdown("<div class='main-header'><h1>✨ Generate AI Images</h1></div>", unsafe_allow_html=True)
    
    if not st.session_state.api_key:
        st.error("⚠️ Please configure your API Key in the sidebar")
        return
    
    tab1, tab2, tab3 = st.tabs(["🎨 Text-to-Image", "✏️ Qwen Edit", "🔮 Seedream V4"])
    
    with tab1:
        with st.form("txt2img_form"):
            prompt = st.text_area("Prompt", "A majestic lion wearing a golden crown, photorealistic, 4k", height=100)
            
            col1, col2, col3 = st.columns(3)
            with col1:
                width = st.slider("Width", 512, 1024, 1024, step=64)
            with col2:
                height = st.slider("Height", 512, 1024, 1024, step=64)
            with col3:
                num_images = st.slider("Images", 1, 4, 1)
            
            submitted = st.form_submit_button("🚀 Generate", use_container_width=True)
            
            if submitted:
                input_params = {
                    "prompt": prompt,
                    "width": width,
                    "height": height,
                    "num_images": num_images
                }
                
                with st.spinner("Creating task..."):
                    result = create_task(st.session_state.api_key, "stable-diffusion-xl", input_params)
                
                if result["success"]:
                    task_id = result["task_id"]
                    st.info(f"✅ Task created: {task_id}")
                    
                    # Poll for completion
                    poll_result = poll_task_until_complete(st.session_state.api_key, task_id)
                    
                    if poll_result["success"]:
                        try:
                            result_json = json.loads(poll_result['data'].get('resultJson', '{}'))
                            result_urls = result_json.get('resultUrls', [])
                            
                            if result_urls:
                                st.success(f"🎉 Generated {len(result_urls)} images!")
                                
                                # Display images
                                cols = st.columns(len(result_urls))
                                for idx, url in enumerate(result_urls):
                                    with cols[idx]:
                                        st.image(url, use_column_width=True)
                                
                                # Auto-upload to Google Drive
                                if st.session_state.authenticated:
                                    st.info("📤 Uploading to Google Drive...")
                                    for idx, url in enumerate(result_urls):
                                        file_name = f"txt2img_{task_id}_{idx+1}.png"
                                        upload_info = upload_to_gdrive(url, file_name, task_id)
                                        if upload_info:
                                            st.session_state.library_images.insert(0, upload_info)
                                            st.success(f"✅ Uploaded {file_name}")
                                    
                                    st.success("🎊 All images uploaded to Google Drive!")
                        except Exception as e:
                            st.error(f"Error processing results: {str(e)}")
                    else:
                        st.error(f"Task failed: {poll_result.get('error', 'Unknown error')}")
                else:
                    st.error(f"Failed to create task: {result['error']}")
    
    with tab2:
        with st.form("qwen_form"):
            prompt = st.text_area("Edit Prompt", "Make the image vibrant and colorful", height=100)
            image_url = st.text_input("Image URL", "https://example.com/image.jpg")
            
            col1, col2 = st.columns(2)
            with col1:
                image_size = st.selectbox("Size", ["square_hd", "landscape_16_9", "portrait_4_3"])
            with col2:
                guidance_scale = st.slider("Guidance", 0.0, 20.0, 4.0)
            
            submitted = st.form_submit_button("✏️ Edit Image", use_container_width=True)
            
            if submitted:
                input_params = {
                    "prompt": prompt,
                    "image_url": image_url,
                    "image_size": image_size,
                    "guidance_scale": guidance_scale
                }
                
                with st.spinner("Creating edit task..."):
                    result = create_task(st.session_state.api_key, "qwen/image-edit", input_params)
                
                if result["success"]:
                    task_id = result["task_id"]
                    st.info(f"✅ Task created: {task_id}")
                    
                    poll_result = poll_task_until_complete(st.session_state.api_key, task_id)
                    
                    if poll_result["success"]:
                        try:
                            result_json = json.loads(poll_result['data'].get('resultJson', '{}'))
                            result_urls = result_json.get('resultUrls', [])
                            
                            if result_urls:
                                st.success("🎉 Image edited successfully!")
                                st.image(result_urls[0], use_column_width=True)
                                
                                if st.session_state.authenticated:
                                    file_name = f"qwen_edit_{task_id}.png"
                                    upload_info = upload_to_gdrive(result_urls[0], file_name, task_id)
                                    if upload_info:
                                        st.session_state.library_images.insert(0, upload_info)
                                        st.success(f"✅ Uploaded to Google Drive!")
                        except Exception as e:
                            st.error(f"Error: {str(e)}")
                else:
                    st.error(f"Failed: {result['error']}")
    
    with tab3:
        with st.form("seedream_form"):
            prompt = st.text_area("Prompt", "Create a t-shirt mockup with this design", height=100)
            image_url = st.text_input("Image URL", "https://example.com/design.png")
            
            col1, col2 = st.columns(2)
            with col1:
                image_size = st.selectbox("Size", ["square_hd", "landscape_16_9", "portrait_4_3"], key="seedream_size")
            with col2:
                max_images = st.slider("Max Images", 1, 6, 1)
            
            submitted = st.form_submit_button("🔮 Generate", use_container_width=True)
            
            if submitted:
                input_params = {
                    "prompt": prompt,
                    "image_urls": [image_url],
                    "image_size": image_size,
                    "max_images": max_images
                }
                
                with st.spinner("Creating Seedream task..."):
                    result = create_task(st.session_state.api_key, "bytedance/seedream-v4-edit", input_params)
                
                if result["success"]:
                    task_id = result["task_id"]
                    st.info(f"✅ Task created: {task_id}")
                    
                    poll_result = poll_task_until_complete(st.session_state.api_key, task_id)
                    
                    if poll_result["success"]:
                        try:
                            result_json = json.loads(poll_result['data'].get('resultJson', '{}'))
                            result_urls = result_json.get('resultUrls', [])
                            
                            if result_urls:
                                st.success(f"🎉 Generated {len(result_urls)} variations!")
                                
                                cols = st.columns(min(len(result_urls), 3))
                                for idx, url in enumerate(result_urls):
                                    with cols[idx % 3]:
                                        st.image(url, use_column_width=True)
                                
                                if st.session_state.authenticated:
                                    for idx, url in enumerate(result_urls):
                                        file_name = f"seedream_{task_id}_{idx+1}.png"
                                        upload_info = upload_to_gdrive(url, file_name, task_id)
                                        if upload_info:
                                            st.session_state.library_images.insert(0, upload_info)
                                    st.success("✅ All uploaded to Google Drive!")
                        except Exception as e:
                            st.error(f"Error: {str(e)}")
                else:
                    st.error(f"Failed: {result['error']}")

def display_library_page():
    # Back to Generate button
    if st.button("← Back to Generate", key="back_to_gen", use_container_width=False):
        st.session_state.current_page = "Generate"
        st.rerun()
    
    st.markdown("<div class='main-header'><h1>📚 Image Library</h1></div>", unsafe_allow_html=True)
    
    if not st.session_state.authenticated:
        st.error("⚠️ Please connect Google Drive in the sidebar")
        return
    
    # Refresh images
    if not st.session_state.library_images:
        st.session_state.library_images = list_gdrive_images()
    
    if not st.session_state.library_images:
        st.info("📭 Your library is empty. Generate some images!")
        return
    
    st.markdown(f"### Found **{len(st.session_state.library_images)}** images")
    
    # Display images in grid
    cols_per_row = 3
    
    for i, img in enumerate(st.session_state.library_images):
        if i % cols_per_row == 0:
            cols = st.columns(cols_per_row)
        
        with cols[i % cols_per_row]:
            st.markdown("<div class='image-card'>", unsafe_allow_html=True)
            
            # Display image using public URL
            if 'public_url' in img:
                st.image(img['public_url'], use_column_width=True)
            
            # File name
            file_name = img.get('file_name') or img.get('name', 'Unknown')
            st.markdown(f"**{file_name}**")
            
            # Buttons
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔗 Open", key=f"open_{img.get('file_id') or img.get('id')}", use_container_width=True):
                    web_link = img.get('web_link') or img.get('webViewLink', '#')
                    st.markdown(f'<meta http-equiv="refresh" content="0; url={web_link}">', unsafe_allow_html=True)
            
            with col2:
                file_id = img.get('file_id') or img.get('id')
                if st.button("🗑️ Delete", key=f"del_{file_id}", use_container_width=True):
                    if delete_gdrive_file(file_id):
                        st.success("Deleted!")
                        st.session_state.library_images = [x for x in st.session_state.library_images if (x.get('file_id') or x.get('id')) != file_id]
                        st.rerun()
            
            st.markdown("</div>", unsafe_allow_html=True)

def display_history_page():
    st.markdown("<div class='main-header'><h1>📋 Task History</h1></div>", unsafe_allow_html=True)
    
    if not st.session_state.task_history:
        st.info("📭 No tasks yet")
    else:
        for task in st.session_state.task_history:
            st.markdown(f"**Task ID:** {task['id']}")
            st.markdown(f"**Status:** {task['status']}")
            st.markdown("---")

# ============================================================================
# Main Router
# ============================================================================

if st.session_state.current_page == "Generate":
    display_generate_page()
elif st.session_state.current_page == "Library":
    display_library_page()
elif st.session_state.current_page == "History":
    display_history_page()
else:
    st.session_state.current_page = "Generate"
    st.rerun()
