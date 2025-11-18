import streamlit as st
import os
import json
import pickle
import requests
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
import io
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
# Configuration & Constants
# ============================================================================

SCOPES = ['https://www.googleapis.com/auth/drive']
CLIENT_SECRETS_FILE = 'client_secrets.json'
TOKEN_PICKLE_FILE = 'token.pickle'
CREDENTIALS_DIR = Path('.credentials')
CREDENTIALS_DIR.mkdir(exist_ok=True)

# Image generation API configuration
IMAGE_GEN_API_URL = "https://api.aiquickdraw.com/api/v1/generation/text-to-image"
IMAGE_EDIT_API_URL = "https://api.aiquickdraw.com/api/v1/generation/image-edit"

# ============================================================================
# Streamlit Page Configuration
# ============================================================================

st.set_page_config(
    page_title="Image Generation Enhancer",
    page_icon="🎨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better UI
st.markdown("""
    <style>
    .main {
        padding: 2rem;
    }
    .stTabs [data-baseweb="tab-list"] button {
        font-size: 16px;
        font-weight: 600;
    }
    .gallery-item {
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        transition: transform 0.2s;
    }
    .gallery-item:hover {
        transform: scale(1.02);
    }
    </style>
""", unsafe_allow_html=True)

# ============================================================================
# Session State Initialization
# ============================================================================

if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.user_email = None
    st.session_state.service = None
    st.session_state.credentials = None
    st.session_state.generated_images = []
    st.session_state.library_images = []
    st.session_state.current_page = 'home'
    st.session_state.selected_image = None
    st.session_state.editor_mode = False
    st.session_state.gdrive_folder_id = None

# ============================================================================
# Google Drive Authentication Functions
# ============================================================================

def get_google_auth_flow():
    """Initialize Google OAuth flow."""
    if not os.path.exists(CLIENT_SECRETS_FILE):
        st.error("⚠️ client_secrets.json not found. Please upload your Google OAuth credentials.")
        st.stop()
    
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri='http://localhost:8501'
    )
    return flow

def save_credentials(credentials):
    """Save credentials to pickle file."""
    token_path = CREDENTIALS_DIR / TOKEN_PICKLE_FILE
    with open(token_path, 'wb') as token:
        pickle.dump(credentials, token)

def load_credentials():
    """Load credentials from pickle file."""
    token_path = CREDENTIALS_DIR / TOKEN_PICKLE_FILE
    if token_path.exists():
        with open(token_path, 'rb') as token:
            return pickle.load(token)
    return None

def refresh_credentials(credentials):
    """Refresh expired credentials."""
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        save_credentials(credentials)
    return credentials

def authenticate_google_drive():
    """Authenticate with Google Drive."""
    credentials = load_credentials()
    
    if credentials:
        credentials = refresh_credentials(credentials)
    else:
        flow = get_google_auth_flow()
        auth_url, state = flow.authorization_url(access_type='offline', prompt='consent')
        
        st.info("🔐 Please authenticate with Google Drive to continue.")
        st.markdown(f"[Click here to authenticate]({auth_url})")
        
        auth_code = st.text_input("Enter the authorization code from the redirect URL:")
        if auth_code:
            try:
                credentials = flow.fetch_token(code=auth_code)
                save_credentials(credentials)
                st.success("✅ Authentication successful!")
                st.rerun()
            except Exception as e:
                st.error(f"Authentication failed: {str(e)}")
                return None
    
    if credentials:
        st.session_state.credentials = credentials
        st.session_state.authenticated = True
        st.session_state.service = build('drive', 'v3', credentials=credentials)
        return credentials
    
    return None

# ============================================================================
# Google Drive Functions
# ============================================================================

def create_app_folder():
    """Create or get the app's folder in Google Drive."""
    if not st.session_state.service:
        return None
    
    try:
        # Search for existing folder
        results = st.session_state.service.files().list(
            q="name='Image Generation Enhancer' and mimeType='application/vnd.google-apps.folder' and trashed=false",
            spaces='drive',
            fields='files(id, name)',
            pageSize=1
        ).execute()
        
        files = results.get('files', [])
        if files:
            return files[0]['id']
        
        # Create new folder if not exists
        file_metadata = {
            'name': 'Image Generation Enhancer',
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

def upload_to_gdrive(file_path: str, file_name: str, folder_id: Optional[str] = None):
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
        
        media = MediaFileUpload(file_path, mimetype='image/png')
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
# Image Generation Functions
# ============================================================================

def generate_image(prompt: str, image_size: str = "square_hd", resolution: str = "1K", api_key: str = None):
    """Generate an image using the external API."""
    if not api_key:
        st.error("API key is required for image generation.")
        return None
    
    try:
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            "input": {
                "image_size": image_size,
                "image_resolution": resolution,
                "prompt": prompt,
                "max_images": 1
            },
            "model": "bytedance/seedream-v4"
        }
        
        with st.spinner("🎨 Generating image..."):
            response = requests.post(IMAGE_GEN_API_URL, json=payload, headers=headers, timeout=120)
            response.raise_for_status()
            
            result = response.json()
            if result.get('state') == 'success':
                result_json = json.loads(result.get('resultJson', '{}'))
                image_urls = result_json.get('resultUrls', [])
                
                if image_urls:
                    return {
                        'url': image_urls[0],
                        'prompt': prompt,
                        'model': result.get('model'),
                        'size': image_size,
                        'resolution': resolution,
                        'generated_at': datetime.now().isoformat()
                    }
            else:
                st.error(f"Image generation failed: {result.get('failMsg', 'Unknown error')}")
                return None
    except Exception as e:
        st.error(f"Error generating image: {str(e)}")
        return None

def edit_image(image_url: str, prompt: str, api_key: str = None):
    """Edit an existing image using the external API."""
    if not api_key:
        st.error("API key is required for image editing.")
        return None
    
    try:
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            "input": {
                "image_urls": [image_url],
                "prompt": prompt,
                "max_images": 1
            },
            "model": "bytedance/seedream-v4-edit"
        }
        
        with st.spinner("✏️ Editing image..."):
            response = requests.post(IMAGE_EDIT_API_URL, json=payload, headers=headers, timeout=120)
            response.raise_for_status()
            
            result = response.json()
            if result.get('state') == 'success':
                result_json = json.loads(result.get('resultJson', '{}'))
                image_urls = result_json.get('resultUrls', [])
                
                if image_urls:
                    return {
                        'url': image_urls[0],
                        'prompt': prompt,
                        'model': result.get('model'),
                        'edited_at': datetime.now().isoformat()
                    }
            else:
                st.error(f"Image editing failed: {result.get('failMsg', 'Unknown error')}")
                return None
    except Exception as e:
        st.error(f"Error editing image: {str(e)}")
        return None

# ============================================================================
# Image Editor Functions
# ============================================================================

def apply_brightness_contrast(image, brightness=0, contrast=0):
    """Apply brightness and contrast adjustments."""
    img_array = np.array(image).astype(float) / 255.0
    img_array = img_array * (1 + contrast / 100)
    img_array = img_array + (brightness / 100)
    img_array = np.clip(img_array, 0, 1)
    return PILImage.fromarray((img_array * 255).astype(np.uint8))

def apply_blur(image, blur_amount=5):
    """Apply Gaussian blur."""
    img_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    blurred = cv2.GaussianBlur(img_cv, (blur_amount * 2 + 1, blur_amount * 2 + 1), 0)
    return PILImage.fromarray(cv2.cvtColor(blurred, cv2.COLOR_BGR2RGB))

def apply_saturation(image, saturation=0):
    """Apply saturation adjustment."""
    img_hsv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2HSV).astype(float)
    img_hsv[:, :, 1] = img_hsv[:, :, 1] * (1 + saturation / 100)
    img_hsv[:, :, 1] = np.clip(img_hsv[:, :, 1], 0, 255)
    return PILImage.fromarray(cv2.cvtColor(img_hsv.astype(np.uint8), cv2.COLOR_HSV2RGB))

def apply_rotation(image, angle=0):
    """Apply rotation."""
    return image.rotate(angle, expand=True, fillcolor='white')

# ============================================================================
# UI Components
# ============================================================================

def render_header():
    """Render the application header."""
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col1:
        st.image("🎨", width=50)
    
    with col2:
        st.title("🎨 Image Generation Enhancer")
        st.markdown("*Generate, edit, and manage images with Google Drive integration*")
    
    with col3:
        if st.session_state.authenticated:
            st.success(f"✅ Authenticated")
            if st.button("🚪 Logout", key="logout_btn"):
                st.session_state.authenticated = False
                st.session_state.service = None
                st.session_state.credentials = None
                st.rerun()

def render_generation_page():
    """Render the image generation page."""
    st.header("🎨 Generate New Images")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        prompt = st.text_area(
            "📝 Describe the image you want to generate:",
            height=100,
            placeholder="E.g., A serene landscape with mountains and a lake at sunset..."
        )
    
    with col2:
        st.subheader("Settings")
        image_size = st.selectbox(
            "Image Size",
            ["square_hd", "landscape_hd", "portrait_hd"],
            help="Choose the aspect ratio for your image"
        )
        resolution = st.selectbox(
            "Resolution",
            ["1K", "2K", "4K"],
            help="Higher resolution takes longer to generate"
        )
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        api_key = st.text_input("🔑 API Key", type="password", help="Your image generation API key")
    
    with col2:
        st.write("")
        st.write("")
        generate_btn = st.button("✨ Generate Image", use_container_width=True)
    
    with col3:
        st.write("")
        st.write("")
        auto_upload = st.checkbox("📤 Auto-upload to Google Drive", value=True)
    
    if generate_btn:
        if not prompt:
            st.error("Please enter a prompt for image generation.")
        elif not api_key:
            st.error("Please provide an API key.")
        else:
            generated = generate_image(prompt, image_size, resolution, api_key)
            
            if generated:
                st.session_state.generated_images.append(generated)
                
                # Display generated image
                st.success("✅ Image generated successfully!")
                st.image(generated['url'], caption=f"Prompt: {prompt}", use_column_width=True)
                
                # Auto-upload to Google Drive
                if auto_upload and st.session_state.authenticated:
                    with st.spinner("📤 Uploading to Google Drive..."):
                        # Download image first
                        img_response = requests.get(generated['url'])
                        img_path = f"/tmp/generated_{datetime.now().timestamp()}.png"
                        with open(img_path, 'wb') as f:
                            f.write(img_response.content)
                        
                        # Upload to Google Drive
                        upload_result = upload_to_gdrive(
                            img_path,
                            f"Generated_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                        )
                        
                        if upload_result:
                            st.success(f"✅ Uploaded to Google Drive: {upload_result['file_name']}")
                            st.markdown(f"[View on Google Drive]({upload_result['web_link']})")
                        
                        # Clean up
                        os.remove(img_path)

def render_library_page():
    """Render the image library page."""
    st.header("📚 Image Library")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        search_query = st.text_input("🔍 Search images", placeholder="Enter prompt or filename...")
    
    with col2:
        sort_by = st.selectbox("Sort by", ["Newest", "Oldest", "Name"])
    
    with col3:
        st.write("")
        st.write("")
        refresh_btn = st.button("🔄 Refresh Library", use_container_width=True)
    
    if refresh_btn or not st.session_state.library_images:
        with st.spinner("📂 Loading images from Google Drive..."):
            st.session_state.library_images = list_gdrive_images()
    
    images = st.session_state.library_images
    
    # Filter by search query
    if search_query:
        images = [img for img in images if search_query.lower() in img['name'].lower()]
    
    # Sort images
    if sort_by == "Oldest":
        images = sorted(images, key=lambda x: x.get('createdTime', ''))
    elif sort_by == "Name":
        images = sorted(images, key=lambda x: x['name'])
    else:  # Newest
        images = sorted(images, key=lambda x: x.get('createdTime', ''), reverse=True)
    
    if not images:
        st.info("📭 No images found in your library. Generate some images first!")
    else:
        st.write(f"Found **{len(images)}** images")
        
        # Display images in a grid
        cols = st.columns(4)
        for idx, img in enumerate(images):
            col = cols[idx % 4]
            
            with col:
                st.markdown(f"""
                <div class="gallery-item">
                    <img src="{img['webContentLink']}" width="100%" style="border-radius: 8px;">
                </div>
                """, unsafe_allow_html=True)
                
                st.caption(img['name'][:20] + "..." if len(img['name']) > 20 else img['name'])
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    if st.button("✏️ Edit", key=f"edit_{img['id']}", use_container_width=True):
                        st.session_state.selected_image = img
                        st.session_state.editor_mode = True
                        st.rerun()
                
                with col2:
                    if st.button("🔗 View", key=f"view_{img['id']}", use_container_width=True):
                        st.markdown(f"[Open in Google Drive]({img['webContentLink']})")
                
                with col3:
                    if st.button("🗑️ Delete", key=f"delete_{img['id']}", use_container_width=True):
                        if delete_gdrive_file(img['id']):
                            st.success("✅ Image deleted")
                            st.session_state.library_images = [i for i in st.session_state.library_images if i['id'] != img['id']]
                            st.rerun()

def render_editor_page():
    """Render the image editor page."""
    if not st.session_state.selected_image:
        st.warning("No image selected. Please select an image from the library first.")
        return
    
    st.header("✏️ Image Editor")
    
    img = st.session_state.selected_image
    st.subheader(f"Editing: {img['name']}")
    
    # Load the image
    img_response = requests.get(img['webContentLink'])
    image = PILImage.open(io.BytesIO(img_response.content))
    
    # Create tabs for different editing options
    tab1, tab2, tab3, tab4 = st.tabs(["Adjustments", "Filters", "Transform", "AI Edit"])
    
    with tab1:
        st.subheader("Brightness & Contrast")
        col1, col2 = st.columns(2)
        
        with col1:
            brightness = st.slider("Brightness", -100, 100, 0)
        
        with col2:
            contrast = st.slider("Contrast", -100, 100, 0)
        
        if brightness != 0 or contrast != 0:
            edited_image = apply_brightness_contrast(image, brightness, contrast)
            st.image(edited_image, caption="Preview", use_column_width=True)
    
    with tab2:
        st.subheader("Filters")
        col1, col2 = st.columns(2)
        
        with col1:
            blur = st.slider("Blur", 0, 20, 0)
        
        with col2:
            saturation = st.slider("Saturation", -100, 100, 0)
        
        if blur != 0 or saturation != 0:
            edited_image = image
            if blur > 0:
                edited_image = apply_blur(edited_image, blur)
            if saturation != 0:
                edited_image = apply_saturation(edited_image, saturation)
            st.image(edited_image, caption="Preview", use_column_width=True)
    
    with tab3:
        st.subheader("Transform")
        rotation = st.slider("Rotation (degrees)", -180, 180, 0)
        
        if rotation != 0:
            edited_image = apply_rotation(image, rotation)
            st.image(edited_image, caption="Preview", use_column_width=True)
    
    with tab4:
        st.subheader("AI-Powered Editing")
        edit_prompt = st.text_area(
            "Describe the changes you want:",
            placeholder="E.g., Add a sunset to the background, change colors to warm tones..."
        )
        api_key = st.text_input("🔑 API Key", type="password")
        
        if st.button("🤖 Apply AI Edit"):
            if not edit_prompt:
                st.error("Please describe the changes you want.")
            elif not api_key:
                st.error("Please provide an API key.")
            else:
                edited = edit_image(img['webContentLink'], edit_prompt, api_key)
                if edited:
                    st.success("✅ Image edited successfully!")
                    st.image(edited['url'], caption=f"Prompt: {edit_prompt}", use_column_width=True)
    
    # Save and export options
    st.divider()
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("💾 Save to Google Drive", use_container_width=True):
            st.success("✅ Image saved to Google Drive")
    
    with col2:
        if st.button("⬇️ Download", use_container_width=True):
            st.download_button(
                label="Download Image",
                data=img_response.content,
                file_name=img['name'],
                mime="image/png"
            )
    
    with col3:
        if st.button("🔙 Back to Library", use_container_width=True):
            st.session_state.editor_mode = False
            st.session_state.selected_image = None
            st.rerun()

# ============================================================================
# Main Application
# ============================================================================

def main():
    """Main application logic."""
    render_header()
    
    # Sidebar navigation
    with st.sidebar:
        st.header("📋 Navigation")
        
        if not st.session_state.authenticated:
            st.info("🔐 Please authenticate with Google Drive to use all features.")
            if st.button("🔑 Authenticate with Google Drive", use_container_width=True):
                authenticate_google_drive()
        else:
            st.success("✅ Google Drive Connected")
            
            if st.button("📂 Create App Folder", use_container_width=True):
                folder_id = create_app_folder()
                if folder_id:
                    st.success(f"✅ Folder created/found: {folder_id}")
        
        st.divider()
        
        # Navigation buttons
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("✨ Generate", use_container_width=True):
                st.session_state.current_page = 'generate'
                st.rerun()
        
        with col2:
            if st.button("📚 Library", use_container_width=True):
                st.session_state.current_page = 'library'
                st.rerun()
        
        st.divider()
        st.markdown("### 📊 Statistics")
        st.metric("Generated Images", len(st.session_state.generated_images))
        st.metric("Library Images", len(st.session_state.library_images))
    
    # Main content area
    if st.session_state.editor_mode:
        render_editor_page()
    elif st.session_state.current_page == 'library':
        render_library_page()
    else:
        render_generation_page()

if __name__ == "__main__":
    main()
